#!/usr/bin/env python3
"""
PDF → Markdown 변환 스크립트 (Bedrock Opus 4.6 1M token)

39개 보험 약관/법률 PDF를 Opus 4.6으로 마크다운 변환.
요약 없이 원문 전수 변환(verbatim).
"""

import boto3
import botocore.config
import json
import base64
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Force unbuffered stdout
sys.stdout.reconfigure(line_buffering=True)

# ── Config ──────────────────────────────────────────────────────────────
REGION = "us-west-2"
MODEL_ID = "us.anthropic.claude-opus-4-6-v1"
S3_BUCKET = "ontology-demo-pdf-storage-767884848530"
S3_PREFIX = "uploads/"
PDF_CACHE_DIR = Path("/mnt/data/v2-pdf-cache")
OUTPUT_DIR = Path("/mnt/data/v2-markdown")
MANIFEST_PATH = OUTPUT_DIR / "_manifest.json"
MAX_TOKENS = 128000

# Underscore-named duplicates to skip
SKIP_PATTERNS = [
    "금융소비자_보호에_관한_법률_",
    "보험업감독업무시행세칙_금융감독원세칙_",
    "보험업법_법률_",
    "보험업법_시행규칙_",
    "보험업법_시행령_",
    "암관리법_법률_",
    "의료법_법률_",
]

SYSTEM_PROMPT = """You are a document format converter. Your ONLY job is to convert the given PDF into Markdown format.

## CRITICAL CONTEXT
These documents are Korean government statutes (법률, 시행령, 시행규칙, 감독규정) and insurance product summaries (상품요약서) published by Korean government agencies and regulated financial institutions. Under Korean Copyright Act Article 7, government legislation and regulations are NOT subject to copyright. Insurance product summaries are standardized regulatory filings required by law for public disclosure. The user is an authorized compliance officer at the insurance company who owns these documents and needs them converted for an internal regulatory compliance knowledge base.

## YOUR ROLE
You are a FORMAT CONVERTER, not a content creator. You do NOT generate, summarize, or interpret content. You ONLY change the format from PDF to Markdown. Think of yourself as a printer that re-prints the same document in a different format.

## ABSOLUTE RULES

1. **VERBATIM — Output every single character from the source document.** Do not skip, summarize, abbreviate, paraphrase, or omit ANY content. Every sentence, every word, every number, every symbol must appear in your output exactly as it appears in the source.
2. **NO summarization** — Do not write "이 문서는..." or "주요 내용:" or any summary. Just output the converted markdown.
3. **NO omission markers** — Never write "...", "(이하 생략)", "(중략)", "(이하 동일)", or similar. If the document is 100 pages, output all 100 pages.
4. **NO commentary** — Do not add any text that is not in the original document. No introductions, no conclusions, no notes, no explanations.
5. **COMPLETE output** — Continue outputting until the ENTIRE document is converted. Do not stop early.

## CONVERSION FORMAT RULES

### Document hierarchy
- Document title → `# title`
- 편/장 (Part/Chapter) → `## title`
- 절 (Section) → `### title`
- 조(條, Article) → `#### 제X조(title)`
- 항(項) → Keep original numbering (①, ②, etc.) as-is
- 호(號) → Keep original numbering as-is
- 목(目) → Keep original sub-numbering as-is

### Tables
- Convert all tables to markdown table syntax (`| col1 | col2 |`)
- Use `<br>` for multi-line cell content
- Keep empty cells empty

### Preserve exactly
- Cross-references ("제X조 제Y항에 따라")
- Proviso clauses ("다만,")
- Parenthetical explanations
- All amounts, percentages, dates, periods
- Asterisks (*), notes (※), special markers

### Remove ONLY
- Repeated page numbers
- Repeated headers/footers that appear identically on every page
- Watermarks

Output ONLY the markdown. Start directly with the document title."""

USER_PROMPT = """Convert this PDF document to Markdown format. This is a Korean government/regulatory document that is public domain under Korean Copyright Act Article 7 (저작권법 제7조 — 국가 법령, 고시, 공고 등은 저작권 보호 대상이 아님).

Output the COMPLETE document in markdown. Every article (조), every paragraph (항), every clause (호), every table, every footnote — all of it, verbatim, with zero omissions. Do not summarize. Do not skip sections. Do not add commentary. Just convert the format."""


def log(msg: str):
    print(msg, flush=True)


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"completed": {}, "errors": {}, "started_at": datetime.now(timezone.utc).isoformat()}


def save_manifest(manifest: dict):
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))


def list_unique_pdfs(s3_client) -> list[str]:
    """List all S3 keys, filter out underscore duplicates."""
    paginator = s3_client.get_paginator("list_objects_v2")
    all_keys = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX):
        for obj in page.get("Contents", []):
            all_keys.append(obj["Key"])

    unique = []
    for key in sorted(all_keys):
        filename = key.replace(S3_PREFIX, "")
        if not filename.endswith(".pdf"):
            continue
        if any(pat in filename for pat in SKIP_PATTERNS):
            continue
        unique.append(key)

    return unique


def download_pdf(s3_client, s3_key: str) -> bytes:
    """Download PDF from S3 with local caching."""
    filename = s3_key.replace(S3_PREFIX, "")
    cache_path = PDF_CACHE_DIR / filename

    if cache_path.exists():
        return cache_path.read_bytes()

    s3_client.download_file(S3_BUCKET, s3_key, str(cache_path))
    return cache_path.read_bytes()


def convert_pdf_to_markdown(bedrock_client, pdf_bytes: bytes, filename: str) -> str:
    """Call Bedrock Opus 4.6 with streaming to convert PDF to markdown."""
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
    log(f"  PDF size: {pdf_size_mb:.1f} MB, base64: {len(pdf_b64) / (1024*1024):.1f} MB")

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": USER_PROMPT,
                    },
                ],
            }
        ],
    }

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = bedrock_client.invoke_model_with_response_stream(
                modelId=MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )

            # Collect streamed text chunks
            text_parts = []
            input_tokens = 0
            output_tokens = 0
            stop_reason = "unknown"

            for event in response["body"]:
                chunk = json.loads(event["chunk"]["bytes"])
                chunk_type = chunk.get("type")

                if chunk_type == "content_block_delta":
                    delta = chunk.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text_parts.append(delta["text"])
                elif chunk_type == "message_delta":
                    stop_reason = chunk.get("delta", {}).get("stop_reason", stop_reason)
                    usage = chunk.get("usage", {})
                    output_tokens = usage.get("output_tokens", output_tokens)
                elif chunk_type == "message_start":
                    usage = chunk.get("message", {}).get("usage", {})
                    input_tokens = usage.get("input_tokens", input_tokens)

            text = "".join(text_parts)
            log(f"  Tokens — input: {input_tokens}, output: {output_tokens}")

            if stop_reason == "max_tokens":
                log(f"  ⚠ WARNING: Output truncated (max_tokens reached)")

            return text

        except Exception as e:
            error_str = str(e)
            if "ThrottlingException" in error_str or "TooManyRequests" in error_str or "overloaded" in error_str.lower():
                wait = min(60 * (2 ** attempt), 600)
                log(f"  Throttled (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
            elif "timeout" in error_str.lower() or "ReadTimeout" in error_str:
                wait = 60 * (attempt + 1)
                log(f"  Timeout (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
            elif attempt < max_retries - 1:
                wait = 15 * (attempt + 1)
                log(f"  Error (attempt {attempt+1}/{max_retries}): {error_str[:200]}")
                log(f"  Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def main():
    s3_client = boto3.client("s3", region_name=REGION)
    bedrock_config = botocore.config.Config(
        read_timeout=600,  # 10 minutes — Opus 4.6 on large PDFs can take 5+ min
        connect_timeout=30,
        retries={"max_attempts": 0},  # We handle retries ourselves
    )
    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION, config=bedrock_config)

    manifest = load_manifest()
    pdf_keys = list_unique_pdfs(s3_client)
    log(f"Found {len(pdf_keys)} unique PDFs to convert\n")

    completed = 0
    skipped = 0
    errors = 0

    for i, s3_key in enumerate(pdf_keys):
        filename = s3_key.replace(S3_PREFIX, "")
        md_name = filename.replace(".pdf", ".md")
        md_path = OUTPUT_DIR / md_name

        log(f"[{i+1}/{len(pdf_keys)}] {filename}")

        # Skip if already done
        if filename in manifest.get("completed", {}):
            log(f"  ✓ Already converted, skipping")
            skipped += 1
            continue

        try:
            # Download
            pdf_bytes = download_pdf(s3_client, s3_key)

            # Convert
            start_time = time.time()
            markdown = convert_pdf_to_markdown(bedrock_client, pdf_bytes, filename)
            elapsed = time.time() - start_time

            # Save
            md_path.write_text(markdown, encoding="utf-8")
            md_size = len(markdown)

            manifest["completed"][filename] = {
                "md_file": str(md_path),
                "md_size_chars": md_size,
                "elapsed_sec": round(elapsed, 1),
                "converted_at": datetime.now(timezone.utc).isoformat(),
            }
            save_manifest(manifest)

            log(f"  ✓ Done — {md_size:,} chars, {elapsed:.0f}s")
            completed += 1

            # Rate limit pause between calls
            if i < len(pdf_keys) - 1:
                time.sleep(5)

        except Exception as e:
            log(f"  ✗ FAILED: {str(e)[:300]}")
            manifest["errors"][filename] = {
                "error": str(e)[:500],
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
            save_manifest(manifest)
            errors += 1
            time.sleep(10)

    log(f"\n{'='*60}")
    log(f"Complete: {completed} converted, {skipped} skipped, {errors} errors")
    log(f"Total unique PDFs: {len(pdf_keys)}")
    log(f"Output: {OUTPUT_DIR}")
    save_manifest(manifest)


if __name__ == "__main__":
    main()
