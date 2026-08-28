#!/usr/bin/env python3
"""
Connect orphan Regulation nodes to all Policy nodes via GOVERNED_BY edges.

Orphan Regulations are those that have no inbound GOVERNED_BY edges.
These typically come from law documents (보험업법, 금소법, 암관리법, etc.)
and apply to all insurance products, so every Policy should link to them.

Edge direction: Policy --GOVERNED_BY--> Regulation
"""

import json
import logging
import sys
import time
import urllib3

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Suppress InsecureRequestWarning for Neptune's self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NEPTUNE_ENDPOINT = (
    "ontology-demo-neptune.cluster-XXXXXXXXXXXX.us-west-2.neptune.amazonaws.com"
)
NEPTUNE_PORT = 8182
REGION = "us-west-2"
NEPTUNE_URL = f"https://{NEPTUNE_ENDPOINT}:{NEPTUNE_PORT}/gremlin"

# Batch size for creating edges (avoid timeouts on large batches)
BATCH_SIZE = 20


# ---------------------------------------------------------------------------
# GraphSON unwrapper (copied from backend NeptuneClient)
# ---------------------------------------------------------------------------
def _unwrap_graphson(data):
    """Recursively unwrap Neptune GraphSON v3 format to plain Python objects."""
    if not isinstance(data, dict):
        if isinstance(data, list):
            return [_unwrap_graphson(item) for item in data]
        return data

    if "@type" not in data:
        return {k: _unwrap_graphson(v) for k, v in data.items()}

    gtype = data["@type"]
    value = data.get("@value")

    if gtype in ("g:List", "g:Set"):
        return [_unwrap_graphson(item) for item in (value or [])]

    if gtype == "g:Map":
        result = {}
        for i in range(0, len(value), 2):
            k = _unwrap_graphson(value[i])
            v = _unwrap_graphson(value[i + 1])
            result[k] = v
        return result

    if gtype == "g:Path":
        return _unwrap_graphson(value)

    if gtype == "g:T":
        return f"T.{value}"

    if gtype == "g:Direction":
        return value

    if gtype in ("g:Int32", "g:Int64", "g:Double", "g:Float"):
        return value

    return _unwrap_graphson(value) if value is not None else data


# ---------------------------------------------------------------------------
# Neptune HTTP helper
# ---------------------------------------------------------------------------
session = boto3.Session(region_name=REGION)


def submit_gremlin(query: str, timeout: int = 60) -> list:
    """Submit a Gremlin query via Neptune HTTP API with SigV4 auth."""
    data = json.dumps({"gremlin": query})
    credentials = session.get_credentials().get_frozen_credentials()
    request = AWSRequest(
        method="POST",
        url=NEPTUNE_URL,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(credentials, "neptune-db", REGION).add_auth(request)
    headers = dict(request.headers)

    response = requests.post(
        NEPTUNE_URL, headers=headers, data=data, timeout=timeout, verify=False
    )
    response.raise_for_status()
    result = response.json()
    raw = result.get("result", {}).get("data", {})
    return _unwrap_graphson(raw)


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------
def main():
    logger.info("=== Connect Orphan Regulations to Policy Nodes ===")

    # Step 1: Verify connectivity
    logger.info("Verifying Neptune connectivity...")
    try:
        count_result = submit_gremlin("g.V().count()")
        logger.info("Total vertices in graph: %s", count_result)
    except Exception as e:
        logger.error("Failed to connect to Neptune: %s", e)
        sys.exit(1)

    # Step 2: Get all Regulation node IDs
    logger.info("Fetching all Regulation nodes...")
    all_regulations = submit_gremlin(
        "g.V().hasLabel('Regulation').project('id','name')"
        ".by(id).by(values('name').fold())"
    )
    logger.info("Total Regulation nodes: %d", len(all_regulations))

    # Step 3: Get Regulation nodes that DO have inbound GOVERNED_BY edges
    logger.info("Fetching Regulation nodes with existing GOVERNED_BY inbound edges...")
    connected_regulations = submit_gremlin(
        "g.V().hasLabel('Regulation')"
        ".filter(inE('GOVERNED_BY').count().is(gt(0)))"
        ".id()"
    )
    connected_ids = set(str(r) for r in connected_regulations)
    logger.info(
        "Regulation nodes with GOVERNED_BY inbound edges: %d", len(connected_ids)
    )

    # Step 4: Find orphan Regulations
    orphan_regulations = [
        r for r in all_regulations if str(r.get("id")) not in connected_ids
    ]
    logger.info("Orphan Regulation nodes (no GOVERNED_BY inbound): %d", len(orphan_regulations))

    if not orphan_regulations:
        logger.info("No orphan Regulation nodes found. Nothing to do.")
        return

    # Print the orphans for visibility
    for reg in orphan_regulations:
        name = reg.get("name", ["(unnamed)"])
        if isinstance(name, list):
            name = name[0] if name else "(unnamed)"
        logger.info("  Orphan: id=%s  name=%s", reg["id"], name)

    # Step 5: Get all Policy node IDs
    logger.info("Fetching all Policy nodes...")
    policy_ids = submit_gremlin("g.V().hasLabel('Policy').id()")
    logger.info("Total Policy nodes: %d", len(policy_ids))

    if not policy_ids:
        logger.info("No Policy nodes found. Nothing to do.")
        return

    # Step 6: Create GOVERNED_BY edges: Policy --> Regulation
    # Build edge creation queries in batches.
    # Each query adds edges from ALL policies to one batch of orphan regulations.
    total_edges_to_create = len(policy_ids) * len(orphan_regulations)
    logger.info(
        "Will create %d edges (%d policies x %d orphan regulations)",
        total_edges_to_create,
        len(policy_ids),
        len(orphan_regulations),
    )

    total_created = 0

    # Batch by orphan regulation to keep queries manageable
    for batch_start in range(0, len(orphan_regulations), BATCH_SIZE):
        batch = orphan_regulations[batch_start : batch_start + BATCH_SIZE]
        batch_num = (batch_start // BATCH_SIZE) + 1
        total_batches = (len(orphan_regulations) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info("Processing batch %d/%d (%d regulations)...", batch_num, total_batches, len(batch))

        # For each regulation in this batch, create edges from all policies
        for reg in batch:
            reg_id = reg["id"]
            reg_name = reg.get("name", ["(unnamed)"])
            if isinstance(reg_name, list):
                reg_name = reg_name[0] if reg_name else "(unnamed)"

            # Escape the regulation ID for Gremlin string
            reg_id_escaped = str(reg_id).replace("'", "\\'")

            # Build a Gremlin query that creates edges from ALL Policy nodes
            # to this specific Regulation node.
            # Using coalesce to avoid creating duplicate edges.
            query = (
                f"g.V().hasLabel('Policy').as('p')"
                f".V('{reg_id_escaped}').as('r')"
                f".select('p')"
                f".coalesce("
                f"  outE('GOVERNED_BY').where(inV().hasId('{reg_id_escaped}')),"
                f"  addE('GOVERNED_BY').to('r')"
                f")"
                f".count()"
            )

            try:
                result = submit_gremlin(query, timeout=120)
                edge_count = result[0] if result else 0
                logger.info(
                    "  -> %s: %d edges (created or existing)",
                    reg_name,
                    edge_count,
                )
                total_created += edge_count
            except Exception as e:
                logger.error("  -> FAILED for %s (id=%s): %s", reg_name, reg_id, e)
                # Try one-by-one if bulk fails
                logger.info("  -> Falling back to individual edge creation...")
                for pid in policy_ids:
                    pid_escaped = str(pid).replace("'", "\\'")
                    individual_query = (
                        f"g.V('{pid_escaped}')"
                        f".coalesce("
                        f"  outE('GOVERNED_BY').where(inV().hasId('{reg_id_escaped}')),"
                        f"  addE('GOVERNED_BY').to(V('{reg_id_escaped}'))"
                        f")"
                        f".count()"
                    )
                    try:
                        submit_gremlin(individual_query, timeout=30)
                        total_created += 1
                    except Exception as e2:
                        logger.error(
                            "    -> FAILED edge %s -> %s: %s", pid, reg_id, e2
                        )

        # Small delay between batches to be gentle on Neptune
        if batch_start + BATCH_SIZE < len(orphan_regulations):
            time.sleep(0.5)

    logger.info("=== DONE ===")
    logger.info("Total edges created/verified: %d", total_created)

    # Step 7: Verify - count GOVERNED_BY edges now
    logger.info("Verifying final state...")
    final_governed_count = submit_gremlin("g.E().hasLabel('GOVERNED_BY').count()")
    logger.info("Total GOVERNED_BY edges in graph: %s", final_governed_count)

    orphan_check = submit_gremlin(
        "g.V().hasLabel('Regulation')"
        ".filter(inE('GOVERNED_BY').count().is(eq(0)))"
        ".count()"
    )
    logger.info("Remaining orphan Regulation nodes: %s", orphan_check)


if __name__ == "__main__":
    main()
