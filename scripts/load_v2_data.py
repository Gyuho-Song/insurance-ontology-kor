#!/usr/bin/env python3
"""
Load v2 graph-ready JSON data into Neptune and OpenSearch.

Usage:
    python3 scripts/load_v2_data.py                          # Load all
    python3 scripts/load_v2_data.py --neptune-only           # Neptune only
    python3 scripts/load_v2_data.py --opensearch-only        # OpenSearch only
    python3 scripts/load_v2_data.py --file "한화생명*.json"  # Specific files
    python3 scripts/load_v2_data.py --drop-v1                # Drop v1 data first
"""
import argparse
import glob
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from requests_aws4auth import AWS4Auth

# ---------------------------------------------------------------------------
# Config — override via environment variables for different regions
# ---------------------------------------------------------------------------
REGION = os.environ.get("AWS_REGION", "us-west-2")
NEPTUNE_ENDPOINT = os.environ.get(
    "NEPTUNE_ENDPOINT",
    "ontology-demo-neptune-instance.cr8yamuqw57p.us-west-2.neptune.amazonaws.com",
)
NEPTUNE_PORT = int(os.environ.get("NEPTUNE_PORT", "8182"))
NEPTUNE_URL = f"https://{NEPTUNE_ENDPOINT}:{NEPTUNE_PORT}/gremlin"

OPENSEARCH_ENDPOINT = os.environ.get(
    "OPENSEARCH_ENDPOINT",
    "https://svwxdwdbvvoryvl1l1k5.us-west-2.aoss.amazonaws.com",
)
OPENSEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX", "ontology-vectors")

INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/mnt/data/v2-graph-ready"))
MANIFEST_PATH = INPUT_DIR / "_load_manifest.json"

TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
MAX_TEXT_LEN = 500       # Truncate text in Gremlin queries
BATCH_DELAY_MS = 30      # ms between Gremlin queries
MAX_RETRIES = 3
BASE_DELAY_S = 1.0

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
log = logging.getLogger("loader")

# ---------------------------------------------------------------------------
# AWS Auth helpers
# ---------------------------------------------------------------------------
session = boto3.Session(region_name=REGION)
credentials = session.get_credentials().get_frozen_credentials()
bedrock = session.client("bedrock-runtime", region_name=REGION)
aoss_auth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    REGION,
    "aoss",
    session_token=credentials.token,
)


def _sign_request(method: str, url: str, service: str, body: str = "",
                  headers: dict = None) -> dict:
    """Sign an HTTP request with SigV4."""
    req = AWSRequest(method=method, url=url, data=body, headers=headers or {})
    SigV4Auth(credentials, service, REGION).add_auth(req)
    return dict(req.headers)


# ---------------------------------------------------------------------------
# Neptune helpers
# ---------------------------------------------------------------------------
def _esc(value) -> str:
    """Escape value for Gremlin single-quoted string literals."""
    return str(value or "").replace("\\", "\\\\").replace("'", "\\'")


def _truncate(value: str, max_len: int = MAX_TEXT_LEN) -> str:
    return value[:max_len] if len(value) > max_len else value


def gremlin_execute(query: str, retries: int = MAX_RETRIES) -> dict:
    """Execute a Gremlin query against Neptune HTTPS API with SigV4."""
    body = json.dumps({"gremlin": query})
    for attempt in range(retries + 1):
        try:
            headers = {"Content-Type": "application/json"}
            signed = _sign_request("POST", NEPTUNE_URL, "neptune-db",
                                   body, headers)
            resp = requests.post(NEPTUNE_URL, data=body, headers=signed,
                                 timeout=60, verify=False)
            if resp.status_code >= 400:
                raise RuntimeError(f"Neptune HTTP {resp.status_code}: {resp.text[:300]}")
            return resp.json()
        except Exception as e:
            if attempt < retries:
                delay = BASE_DELAY_S * (2 ** attempt)
                log.warning(f"  Gremlin retry {attempt+1}/{retries}: {str(e)[:150]}")
                time.sleep(delay)
            else:
                raise


def build_vertex_query(entity: dict, document_id: str) -> str:
    """Build Gremlin upsert query for a vertex."""
    vid = _esc(entity["id"])
    etype = _esc(entity["type"])
    label = _esc(entity.get("label", ""))
    prov = entity.get("provenance", {})

    q = (f"g.V('{vid}').fold().coalesce(unfold(), "
         f"addV('{etype}').property(id, '{vid}'))")
    q += f".property(single, 'label', '{_esc(label)}')"
    q += f".property(single, 'document_id', '{_esc(document_id)}')"
    q += f".property(single, 'source_section_id', '{_esc(prov.get('source_section_id', ''))}')"
    q += f".property(single, 'source_text', '{_truncate(_esc(prov.get('source_text', '')))}')"
    q += f".property(single, 'confidence', {prov.get('confidence', 0.5)})"

    for key, value in (entity.get("properties") or {}).items():
        if value is None:
            continue
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            q += f".property(single, '{_esc(key)}', '{_truncate(_esc(value))}')"
        elif isinstance(value, (int, float)):
            q += f".property(single, '{_esc(key)}', {value})"

    return q


def build_edge_query(relation: dict) -> str:
    """Build Gremlin addE query for an edge."""
    src = _esc(relation["source_id"])
    tgt = _esc(relation["target_id"])
    rtype = _esc(relation["type"])
    prov = relation.get("provenance", {})

    q = f"g.V('{src}').addE('{rtype}').to(__.V('{tgt}'))"
    q += f".property('source_section_id', '{_esc(prov.get('source_section_id', ''))}')"
    q += f".property('source_text', '{_truncate(_esc(prov.get('source_text', '')))}')"
    q += f".property('confidence', {prov.get('confidence', 0.5)})"

    for key, value in (relation.get("properties") or {}).items():
        if value is None:
            continue
        if isinstance(value, str):
            q += f".property('{_esc(key)}', '{_truncate(_esc(value))}')"
        elif isinstance(value, (int, float)):
            q += f".property('{_esc(key)}', {value})"

    return q


def load_neptune(data: dict) -> tuple[int, int]:
    """Load one document's entities and relations into Neptune."""
    document_id = data["document_id"]
    entities = data.get("entities", [])
    relations = data.get("relations", [])

    # 1. Cleanup existing data for this document
    cleanup = f"g.V().has('document_id', '{_esc(document_id)}').drop()"
    gremlin_execute(cleanup)
    time.sleep(0.1)

    # 2. Create vertices
    v_ok, v_fail = 0, 0
    for entity in entities:
        try:
            query = build_vertex_query(entity, document_id)
            gremlin_execute(query)
            v_ok += 1
        except Exception as e:
            v_fail += 1
            log.warning(f"  Vertex failed [{entity['id']}]: {str(e)[:100]}")
        time.sleep(BATCH_DELAY_MS / 1000)

    # 3. Create edges
    e_ok, e_fail = 0, 0
    for rel in relations:
        try:
            query = build_edge_query(rel)
            gremlin_execute(query)
            e_ok += 1
        except Exception as e:
            e_fail += 1
            log.warning(f"  Edge failed [{rel['type']}]: {str(e)[:100]}")
        time.sleep(BATCH_DELAY_MS / 1000)

    return (v_ok, v_fail, e_ok, e_fail)


# ---------------------------------------------------------------------------
# OpenSearch helpers
# ---------------------------------------------------------------------------
def opensearch_request(method: str, path: str, body: dict = None) -> dict:
    """Make a signed request to OpenSearch Serverless."""
    url = f"{OPENSEARCH_ENDPOINT}/{path}"
    headers = {"Content-Type": "application/json"}

    resp = requests.request(
        method, url,
        json=body if body else None,
        headers=headers,
        auth=aoss_auth,
        timeout=30,
    )
    if resp.status_code >= 400 and resp.status_code != 404:
        raise RuntimeError(f"OpenSearch {resp.status_code}: {resp.text[:300]}")
    try:
        return resp.json()
    except Exception:
        return {"status": resp.status_code, "text": resp.text[:200]}


def generate_embedding(text: str) -> list[float]:
    """Generate embedding using Bedrock Titan v2."""
    resp = bedrock.invoke_model(
        modelId=TITAN_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text}),
    )
    result = json.loads(resp["body"].read())
    return result["embedding"]


def load_opensearch(data: dict) -> int:
    """Load one document's entities into OpenSearch with embeddings."""
    document_id = data["document_id"]
    product_name = data.get("product_name", "")
    entities = data.get("entities", [])

    # 1. Delete existing docs for this document
    try:
        opensearch_request("POST", f"{OPENSEARCH_INDEX}/_delete_by_query",
                           {"query": {"match": {"document_id": document_id}}})
    except Exception as e:
        log.warning(f"  Delete old docs failed (may not exist): {str(e)[:100]}")

    # 2. Index each entity with embedding
    indexed = 0
    for i, entity in enumerate(entities):
        try:
            # Build embedding text: "{type}: {label}. {source_text}"
            source_text = entity.get("provenance", {}).get("source_text", "")
            text = f"{entity['type']}: {entity.get('label', '')}. {source_text}"

            embedding = generate_embedding(text)

            doc = {
                "entity_id": entity["id"],
                "node_type": entity["type"],
                "node_label": entity.get("label", ""),
                "text_content": text,
                "product_name": product_name,
                "document_id": document_id,
                "embedding": embedding,
            }

            opensearch_request("POST", f"{OPENSEARCH_INDEX}/_doc", doc)
            indexed += 1

            if (i + 1) % 20 == 0:
                log.info(f"    OpenSearch: {i+1}/{len(entities)} indexed")

        except Exception as e:
            log.warning(f"  Index failed [{entity['id']}]: {str(e)[:100]}")

    return indexed


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {}


def save_manifest(manifest: dict):
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Load v2 data into Neptune and OpenSearch")
    parser.add_argument("--neptune-only", action="store_true", help="Load Neptune only")
    parser.add_argument("--opensearch-only", action="store_true", help="Load OpenSearch only")
    parser.add_argument("--file", type=str, help="Glob pattern for specific files")
    parser.add_argument("--drop-v1", action="store_true", help="Drop all v1 data first")
    parser.add_argument("--force", action="store_true", help="Re-process already loaded files")
    args = parser.parse_args()

    do_neptune = not args.opensearch_only
    do_opensearch = not args.neptune_only

    # Suppress urllib3 SSL warnings for Neptune self-signed cert
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Find JSON files
    if args.file:
        json_files = sorted(glob.glob(str(INPUT_DIR / args.file)))
    else:
        json_files = sorted(glob.glob(str(INPUT_DIR / "*.json")))
    json_files = [f for f in json_files if not os.path.basename(f).startswith("_")]

    log.info(f"Found {len(json_files)} JSON files to load")
    log.info(f"Neptune: {'YES' if do_neptune else 'SKIP'}, "
             f"OpenSearch: {'YES' if do_opensearch else 'SKIP'}")

    # Optional: drop all v1 data
    if args.drop_v1 and do_neptune:
        log.info("Dropping ALL existing vertices in Neptune...")
        try:
            gremlin_execute("g.V().drop()")
            log.info("  Done — Neptune cleared")
        except Exception as e:
            log.error(f"  Drop failed: {e}")

    # Load manifest
    manifest = load_manifest() if not args.force else {}

    total_vertices = 0
    total_edges = 0
    total_vectors = 0
    errors = 0

    for idx, fpath in enumerate(json_files):
        fname = os.path.basename(fpath)
        doc_key = fname.replace(".json", "")

        # Check manifest
        entry = manifest.get(doc_key, {})
        neptune_done = entry.get("neptune_loaded", False)
        opensearch_done = entry.get("opensearch_loaded", False)

        skip_neptune = do_neptune and neptune_done and not args.force
        skip_opensearch = do_opensearch and opensearch_done and not args.force

        if skip_neptune and skip_opensearch:
            log.info(f"[{idx+1}/{len(json_files)}] {fname}")
            log.info(f"  Already done, skipping")
            continue

        # Load JSON
        with open(fpath) as f:
            data = json.load(f)

        n_entities = len(data.get("entities", []))
        n_relations = len(data.get("relations", []))
        log.info(f"[{idx+1}/{len(json_files)}] {fname}")
        log.info(f"  Entities: {n_entities}, Relations: {n_relations}")

        t0 = time.time()

        # Neptune
        v_ok = v_fail = e_ok = e_fail = 0
        if do_neptune and not skip_neptune:
            try:
                v_ok, v_fail, e_ok, e_fail = load_neptune(data)
                log.info(f"  Neptune: {v_ok} vertices ({v_fail} failed), "
                         f"{e_ok} edges ({e_fail} failed)")
                total_vertices += v_ok
                total_edges += e_ok
                if v_fail > 0 or e_fail > 0:
                    errors += 1
            except Exception as e:
                log.error(f"  Neptune load FAILED: {e}")
                errors += 1
                continue
        elif skip_neptune:
            log.info(f"  Neptune: already loaded, skipping")

        # OpenSearch
        n_indexed = 0
        if do_opensearch and not skip_opensearch:
            try:
                n_indexed = load_opensearch(data)
                log.info(f"  OpenSearch: {n_indexed} vectors indexed")
                total_vectors += n_indexed
            except Exception as e:
                log.error(f"  OpenSearch load FAILED: {e}")
                errors += 1

        elif skip_opensearch:
            log.info(f"  OpenSearch: already loaded, skipping")

        elapsed = time.time() - t0
        log.info(f"  Done in {elapsed:.1f}s")

        # Update manifest
        manifest[doc_key] = {
            "neptune_loaded": do_neptune and not skip_neptune or neptune_done,
            "opensearch_loaded": do_opensearch and not skip_opensearch or opensearch_done,
            "vertices": v_ok,
            "edges": e_ok,
            "vectors": n_indexed if do_opensearch and not skip_opensearch else entry.get("vectors", 0),
            "loaded_at": datetime.now(timezone.utc).isoformat(),
        }
        save_manifest(manifest)

    log.info("")
    log.info("=" * 60)
    log.info(f"Complete: {len(json_files)} files, Errors: {errors}")
    if do_neptune:
        log.info(f"Neptune: {total_vertices} vertices, {total_edges} edges")
    if do_opensearch:
        log.info(f"OpenSearch: {total_vectors} vectors indexed")


if __name__ == "__main__":
    main()
