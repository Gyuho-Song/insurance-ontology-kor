#!/usr/bin/env python3
"""v2 Entity/Relation Extraction: Markdown → GraphReadyData JSON.

Two-pass extraction using Bedrock Sonnet 4 with tool_use:
  Pass 1: Entity extraction per section
  Pass 1.5: Entity deduplication (local)
  Pass 2: Relation extraction per document

Usage:
  python3 scripts/extract_entities_v2.py                 # all files
  python3 scripts/extract_entities_v2.py --file "포켓골절"  # single file (substring match)
"""

import argparse
import boto3
import botocore.config
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.schemas import (
    Entity, EntityProvenance, EntityType,
    ExtractionMetadata, GraphReadyData, Relation, RelationType,
)
from lib.section_splitter import ExtractionUnit, is_law_document, split_document
from lib.entity_dedup import EntityRegistry
from lib.prompts import (
    PRODUCT_ENTITY_PROMPT, LAW_ENTITY_PROMPT,
    PRODUCT_RELATION_PROMPT, LAW_RELATION_PROMPT,
    ENTITY_USER_PROMPT, RELATION_USER_PROMPT,
    ENTITY_EXTRACTION_TOOL, RELATION_EXTRACTION_TOOL,
)

sys.stdout.reconfigure(line_buffering=True)

# ── Config ──────────────────────────────────────────────────────────────

REGION = "us-west-2"
MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"
INPUT_DIR = Path("/mnt/data/v2-markdown")
OUTPUT_DIR = Path("/mnt/data/v2-graph-ready")
MANIFEST_PATH = OUTPUT_DIR / "_manifest.json"
MAX_TOKENS = 32_000

LAW_KEYWORDS = [
    "법률", "시행령", "시행규칙", "세칙", "관리법", "의료법",
    "보호에 관한 법률", "보험업법",
]

ENTITY_TYPE_VALUES = {t.value for t in EntityType}
RELATION_TYPE_VALUES = {t.value for t in RelationType}


def log(msg: str):
    print(msg, flush=True)


# ── Manifest ────────────────────────────────────────────────────────────

def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"completed": {}, "errors": {}}


def save_manifest(manifest: dict):
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))


# ── Bedrock API ─────────────────────────────────────────────────────────

def create_bedrock_client():
    config = botocore.config.Config(
        read_timeout=300,
        connect_timeout=30,
        retries={"max_attempts": 0},
    )
    return boto3.client("bedrock-runtime", region_name=REGION, config=config)


def invoke_with_tool_use(
    client, system_prompt: str, user_content: str, tool: dict, max_tokens: int = MAX_TOKENS
) -> tuple[dict, int, int]:
    """Call Bedrock with tool_use and return (tool_input, input_tokens, output_tokens)."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool["name"]},
        "messages": [{"role": "user", "content": user_content}],
    }

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.invoke_model(
                modelId=MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )

            result = json.loads(response["body"].read())
            input_tokens = result.get("usage", {}).get("input_tokens", 0)
            output_tokens = result.get("usage", {}).get("output_tokens", 0)

            # Extract tool_use content block
            for block in result.get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == tool["name"]:
                    return block["input"], input_tokens, output_tokens

            # No tool_use block found — return empty
            log(f"    ⚠ No tool_use block in response (stop_reason={result.get('stop_reason')})")
            return {tool["name"].replace("extract_", ""): []}, input_tokens, output_tokens

        except Exception as e:
            error_str = str(e)
            if "ThrottlingException" in error_str or "TooManyRequests" in error_str:
                wait = min(60 * (2 ** attempt), 600)
                log(f"    Throttled (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
            elif attempt < max_retries - 1:
                wait = 15 * (attempt + 1)
                log(f"    Error (attempt {attempt+1}/{max_retries}): {error_str[:200]}")
                time.sleep(wait)
            else:
                raise


# ── Pass 1: Entity Extraction ──────────────────────────────────────────

def extract_entities_from_unit(
    client, unit: ExtractionUnit, product_name: str, document_id: str, is_law: bool
) -> tuple[list[dict], int, int]:
    """Extract entities from a single section."""
    system_prompt = LAW_ENTITY_PROMPT if is_law else PRODUCT_ENTITY_PROMPT
    user_content = ENTITY_USER_PROMPT.format(
        product_name=product_name,
        document_id=document_id,
        section_id=unit.section_id,
        section_title=unit.section_title,
        section_content=unit.content,
    )

    result, in_tok, out_tok = invoke_with_tool_use(
        client, system_prompt, user_content, ENTITY_EXTRACTION_TOOL,
    )
    entities = result.get("entities", [])
    return entities, in_tok, out_tok


# ── Pass 2: Relation Extraction ────────────────────────────────────────

def extract_relations(
    client, entities: list[Entity], units: list[ExtractionUnit],
    product_name: str, document_id: str, is_law: bool,
) -> tuple[list[dict], int, int]:
    """Extract relations from the full document given entity list."""
    system_prompt = LAW_RELATION_PROMPT if is_law else PRODUCT_RELATION_PROMPT

    entity_list = "\n".join(
        f"- {e.id} ({e.type.value}): {e.label}" for e in entities
    )

    # Build section summaries (truncate to avoid exceeding context)
    section_parts = []
    total_chars = 0
    for u in units:
        # Include up to 100K chars of section content for relation context
        if total_chars + u.char_count > 100_000:
            remaining = 100_000 - total_chars
            if remaining > 1000:
                section_parts.append(
                    f"[{u.section_id}] {u.section_title}\n{u.content[:remaining]}..."
                )
            break
        section_parts.append(f"[{u.section_id}] {u.section_title}\n{u.content}")
        total_chars += u.char_count

    section_summaries = "\n\n".join(section_parts)

    user_content = RELATION_USER_PROMPT.format(
        product_name=product_name,
        document_id=document_id,
        entity_list=entity_list,
        section_summaries=section_summaries,
    )

    result, in_tok, out_tok = invoke_with_tool_use(
        client, system_prompt, user_content, RELATION_EXTRACTION_TOOL,
    )
    relations = result.get("relations", [])
    return relations, in_tok, out_tok


# ── Parsing + Validation ───────────────────────────────────────────────

def parse_raw_entities(raw_entities: list[dict], document_id: str) -> list[Entity]:
    """Parse raw entity dicts from LLM into validated Entity models."""
    parsed = []
    for raw in raw_entities:
        try:
            etype = raw.get("type", "")
            if etype not in ENTITY_TYPE_VALUES:
                log(f"    ⚠ Unknown entity type '{etype}', skipping")
                continue

            prov = raw.get("provenance", {})
            entity = Entity(
                id=raw.get("id", "unknown"),
                type=EntityType(etype),
                label=raw.get("label", ""),
                properties=raw.get("properties", {}),
                provenance=EntityProvenance(
                    source_section_id=prov.get("source_section_id", "unknown"),
                    source_text=str(prov.get("source_text", ""))[:500],
                    confidence=min(max(float(prov.get("confidence", 0.5)), 0.0), 1.0),
                ),
            )
            parsed.append(entity)
        except Exception as e:
            log(f"    ⚠ Failed to parse entity: {e}")
    return parsed


def parse_raw_relations(
    raw_relations: list[dict], entity_ids: set[str]
) -> list[Relation]:
    """Parse raw relation dicts, dropping those with dangling references."""
    parsed = []
    dangling = 0
    for raw in raw_relations:
        try:
            rtype = raw.get("type", "")
            if rtype not in RELATION_TYPE_VALUES:
                continue

            src = raw.get("source_id", "")
            tgt = raw.get("target_id", "")
            if src not in entity_ids or tgt not in entity_ids:
                dangling += 1
                continue

            prov = raw.get("provenance", {})
            relation = Relation(
                source_id=src,
                target_id=tgt,
                type=RelationType(rtype),
                properties=raw.get("properties", {}),
                provenance=EntityProvenance(
                    source_section_id=prov.get("source_section_id", "unknown"),
                    source_text=str(prov.get("source_text", ""))[:500],
                    confidence=min(max(float(prov.get("confidence", 0.5)), 0.0), 1.0),
                ),
            )
            parsed.append(relation)
        except Exception as e:
            log(f"    ⚠ Failed to parse relation: {e}")

    if dangling > 0:
        log(f"    ⚠ Dropped {dangling} relations with dangling references")
    return parsed


def validate_graph_data(data: GraphReadyData) -> list[str]:
    """Run validation checks, return list of warnings."""
    warnings = []

    # Check Policy count
    policies = [e for e in data.entities if e.type == EntityType.POLICY]
    if len(policies) > 1:
        warnings.append(f"Multiple Policy entities: {len(policies)}")

    # Check for orphan entities (not in any relation)
    connected = set()
    for r in data.relations:
        connected.add(r.source_id)
        connected.add(r.target_id)
    orphans = [
        e for e in data.entities
        if e.type != EntityType.POLICY
        and e.type != EntityType.PRODUCT_CATEGORY
        and e.id not in connected
    ]
    if orphans:
        warnings.append(f"{len(orphans)} orphan entities (not connected)")

    # Check empty source_text
    empty_prov = [e for e in data.entities if not e.provenance.source_text.strip()]
    if empty_prov:
        warnings.append(f"{len(empty_prov)} entities with empty source_text")

    return warnings


# ── Main ────────────────────────────────────────────────────────────────

def derive_product_name(filename: str) -> str:
    """Derive a clean product name from the markdown filename."""
    name = filename.replace(".md", "")
    # Remove date suffixes like _20260101, _20260201 etc.
    parts = name.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
        name = parts[0]
    # Remove trailing _N suffixes (e.g., _1, _2)
    parts = name.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) <= 2:
        name = parts[0]
    return name


def process_document(
    client, md_path: Path, manifest: dict,
) -> dict | None:
    """Process a single markdown file through the full extraction pipeline."""
    filename = md_path.name
    doc_id = md_path.stem
    product_name = derive_product_name(filename)
    is_law = is_law_document(filename)
    doc_type = "law" if is_law else "insurance"

    log(f"  Type: {doc_type}, Size: {md_path.stat().st_size:,} bytes")

    content = md_path.read_text(encoding="utf-8")
    start_time = time.time()
    total_in_tokens = 0
    total_out_tokens = 0
    api_calls = 0

    # Phase 1: Split into extraction units
    units = split_document(content, filename)
    log(f"  Split into {len(units)} sections: {', '.join(u.section_id for u in units)}")

    # Phase 2: Pass 1 — Entity extraction per section
    all_raw_entities: list[dict] = []
    for i, unit in enumerate(units):
        log(f"  Pass 1 [{i+1}/{len(units)}] {unit.section_id} ({unit.char_count:,} chars)")
        raw_entities, in_tok, out_tok = extract_entities_from_unit(
            client, unit, product_name, doc_id, is_law,
        )
        all_raw_entities.extend(raw_entities)
        total_in_tokens += in_tok
        total_out_tokens += out_tok
        api_calls += 1
        log(f"    → {len(raw_entities)} entities, {in_tok} in / {out_tok} out")

        # Rate limit between sections
        if i < len(units) - 1:
            time.sleep(2)

    # Phase 3: Parse + deduplicate entities
    parsed_entities = parse_raw_entities(all_raw_entities, doc_id)
    log(f"  Parsed {len(parsed_entities)} entities from {len(all_raw_entities)} raw")

    registry = EntityRegistry()
    for entity in parsed_entities:
        registry.register(entity)
    deduped = registry.get_all()
    log(f"  After dedup: {len(deduped)} entities")

    # Phase 4: Pass 2 — Relation extraction
    log(f"  Pass 2: Relation extraction ({len(deduped)} entities, {len(units)} sections)")
    entity_ids = {e.id for e in deduped}

    raw_relations, in_tok, out_tok = extract_relations(
        client, deduped, units, product_name, doc_id, is_law,
    )
    total_in_tokens += in_tok
    total_out_tokens += out_tok
    api_calls += 1
    log(f"    → {len(raw_relations)} raw relations, {in_tok} in / {out_tok} out")

    # Phase 5: Parse + validate relations
    relations = parse_raw_relations(raw_relations, entity_ids)
    log(f"  Valid relations: {len(relations)}")

    elapsed = time.time() - start_time

    # Build GraphReadyData
    graph_data = GraphReadyData(
        document_id=doc_id,
        product_name=product_name,
        entities=deduped,
        relations=relations,
        extraction_metadata=ExtractionMetadata(
            extracted_at=datetime.now(timezone.utc).isoformat(),
            model_id=MODEL_ID,
            entity_count=len(deduped),
            relation_count=len(relations),
            sections_processed=len(units),
            api_calls=api_calls,
            total_input_tokens=total_in_tokens,
            total_output_tokens=total_out_tokens,
        ),
    )

    # Validate
    warnings = validate_graph_data(graph_data)
    for w in warnings:
        log(f"  ⚠ {w}")

    # Save
    output_path = OUTPUT_DIR / f"{doc_id}.json"
    output_path.write_text(
        graph_data.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # Entity type breakdown
    type_counts: dict[str, int] = {}
    for e in deduped:
        type_counts[e.type.value] = type_counts.get(e.type.value, 0) + 1
    type_summary = ", ".join(f"{t}:{c}" for t, c in sorted(type_counts.items()))

    log(f"  ✓ Done — {len(deduped)} entities, {len(relations)} relations, "
        f"{elapsed:.0f}s, {total_in_tokens+total_out_tokens:,} tokens")
    log(f"    Types: {type_summary}")

    return {
        "entities": len(deduped),
        "relations": len(relations),
        "elapsed_sec": round(elapsed, 1),
        "api_calls": api_calls,
        "input_tokens": total_in_tokens,
        "output_tokens": total_out_tokens,
        "warnings": warnings,
        "type_counts": type_counts,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="v2 Entity/Relation Extraction")
    parser.add_argument("--file", type=str, help="Substring to match a single file")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    client = create_bedrock_client()
    manifest = load_manifest()

    # Get markdown files, sorted by size (smallest first)
    md_files = sorted(
        [f for f in INPUT_DIR.glob("*.md") if f.name != "_manifest.json"],
        key=lambda f: f.stat().st_size,
    )

    # Filter if --file specified
    if args.file:
        md_files = [f for f in md_files if args.file in f.name]
        if not md_files:
            log(f"No files matching '{args.file}'")
            return

    log(f"Processing {len(md_files)} markdown files\n")

    completed = 0
    errors = 0

    for i, md_path in enumerate(md_files):
        filename = md_path.name
        doc_id = md_path.stem

        log(f"[{i+1}/{len(md_files)}] {filename}")

        # Skip if already done
        if doc_id in manifest.get("completed", {}):
            log(f"  ✓ Already done, skipping")
            completed += 1
            continue

        try:
            result = process_document(client, md_path, manifest)
            if result:
                manifest["completed"][doc_id] = result
                if doc_id in manifest.get("errors", {}):
                    del manifest["errors"][doc_id]
                save_manifest(manifest)
                completed += 1

            # Rate limit between documents
            if i < len(md_files) - 1:
                time.sleep(3)

        except Exception as e:
            log(f"  ✗ FAILED: {str(e)[:300]}")
            manifest.setdefault("errors", {})[doc_id] = {
                "error": str(e)[:500],
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
            save_manifest(manifest)
            errors += 1
            time.sleep(5)

    # Summary
    total_entities = sum(
        v.get("entities", 0) for v in manifest.get("completed", {}).values()
    )
    total_relations = sum(
        v.get("relations", 0) for v in manifest.get("completed", {}).values()
    )
    log(f"\n{'='*60}")
    log(f"Complete: {completed}/{len(md_files)}, Errors: {errors}")
    log(f"Total: {total_entities:,} entities, {total_relations:,} relations")
    log(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
