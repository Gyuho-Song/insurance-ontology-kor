#!/usr/bin/env python3
"""
PDF → Markdown 변환 2차 패스: 대용량 PDF 분할 처리

1차 패스에서 실패한 7개 PDF를 50페이지 단위로 분할하여 변환 후 병합.
"""

import boto3
import botocore.config
import json
import base64
import io
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from pypdf import PdfReader, PdfWriter

sys.stdout.reconfigure(line_buffering=True)

REGION = "us-west-2"
MODEL_ID = "us.anthropic.claude-opus-4-6-v1"
S3_BUCKET = "ontology-demo-pdf-storage-123456789012"
PDF_CACHE_DIR = Path("/mnt/data/v2-pdf-cache")
OUTPUT_DIR = Path("/mnt/data/v2-markdown")
MANIFEST_PATH = OUTPUT_DIR / "_manifest.json"
MAX_TOKENS = 128000
PAGES_PER_CHUNK = 50  # Safe under both 100-page and 200K token limits

# Failed files from pass 1
FAILED_FILES = [
    "uploads/한화생명 H간병보험 무배당_상품요약서_20260201_2.pdf",
    "uploads/한화생명 H건강플러스보험 무배당_상품요약서_20260201.pdf",
    "uploads/한화생명 간편가입 시그니처H암보험 무배당_상품요약서_20260101.pdf",
    "uploads/한화생명 시그니처 H통합건강보험 무배당(납입면제형)_상품요약서_20260201.pdf",
    "uploads/한화생명 시그니처 H통합건강보험 무배당_상품요약서_20260201.pdf",
    "uploads/한화생명 시그니처H암보험 무배당_상품요약서_20260101.pdf",
    "uploads/한화생명 진심가득H보장보험 무배당_상품요약서_20260201.pdf",
]

SYSTEM_PROMPT = """You are a document format converter. Your ONLY job is to convert the given PDF into Markdown format.

## CRITICAL CONTEXT
These documents are Korean insurance product summaries (상품요약서) — standardized regulatory filings required by law for public disclosure. The user is an authorized compliance officer who owns these documents and needs them converted for an internal regulatory compliance knowledge base. This is a partial chunk of a larger document — convert it completely as-is.

## YOUR ROLE
You are a FORMAT CONVERTER. You ONLY change the format from PDF to Markdown. Think of yourself as a printer that re-prints the same document in a different format.

## ABSOLUTE RULES
1. **VERBATIM — Output every single character.** Do not skip, summarize, abbreviate, paraphrase, or omit ANY content.
2. **NO summarization** — Just output the converted markdown.
3. **NO omission markers** — Never write "...", "(이하 생략)", "(중략)".
4. **NO commentary** — Do not add any text that is not in the original.
5. **COMPLETE output** — Convert the ENTIRE chunk.

## CONVERSION FORMAT RULES
- Document/section titles → markdown headings (`#`, `##`, `###`, `####`)
- 조(條) → `#### 제X조(title)`
- 항(①②③) → Keep original numbering as-is
- Tables → markdown table syntax (`| col | col |`)
- Use `<br>` for multi-line cell content
- Preserve all cross-references, proviso clauses, amounts, dates
- Remove only repeated page numbers/headers/footers/watermarks

Output ONLY the markdown."""

USER_PROMPT_TEMPLATE = """Convert this PDF chunk (pages {start}-{end} of {total}) to Markdown format. This is a Korean insurance regulatory filing, public domain under Korean law.

Output the COMPLETE content verbatim. Do not summarize. Do not skip. Do not add commentary. Just convert the format."""


def log(msg: str):
    print(msg, flush=True)


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"completed": {}, "errors": {}}


def save_manifest(manifest: dict):
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))


def split_pdf(pdf_bytes: bytes, pages_per_chunk: int) -> list[bytes]:
    """Split PDF into chunks of N pages, return list of PDF bytes."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    chunks = []

    for start in range(0, total_pages, pages_per_chunk):
        end = min(start + pages_per_chunk, total_pages)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])
        buf = io.BytesIO()
        writer.write(buf)
        chunks.append((start + 1, end, total_pages, buf.getvalue()))

    return chunks


def convert_chunk(bedrock_client, chunk_bytes: bytes, start: int, end: int, total: int) -> str:
    """Convert a PDF chunk to markdown via streaming."""
    pdf_b64 = base64.standard_b64encode(chunk_bytes).decode("utf-8")

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{
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
                    "text": USER_PROMPT_TEMPLATE.format(start=start, end=end, total=total),
                },
            ],
        }],
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
            log(f"    Pages {start}-{end}: {input_tokens} in, {output_tokens} out, {len(text)} chars"
                + (f" ⚠ TRUNCATED" if stop_reason == "max_tokens" else ""))
            return text

        except Exception as e:
            error_str = str(e)
            if "ThrottlingException" in error_str or "TooManyRequests" in error_str:
                wait = min(60 * (2 ** attempt), 600)
                log(f"    Throttled (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
            elif attempt < max_retries - 1:
                wait = 15 * (attempt + 1)
                log(f"    Error (attempt {attempt+1}/{max_retries}): {error_str[:150]}")
                time.sleep(wait)
            else:
                raise


def main():
    s3_client = boto3.client("s3", region_name=REGION)
    bedrock_config = botocore.config.Config(
        read_timeout=600,
        connect_timeout=30,
        retries={"max_attempts": 0},
    )
    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION, config=bedrock_config)

    manifest = load_manifest()

    for i, s3_key in enumerate(FAILED_FILES):
        filename = s3_key.replace("uploads/", "")
        md_name = filename.replace(".pdf", ".md")
        md_path = OUTPUT_DIR / md_name

        log(f"\n[{i+1}/{len(FAILED_FILES)}] {filename}")

        # Skip if already done
        if filename in manifest.get("completed", {}):
            log(f"  ✓ Already converted, skipping")
            continue

        try:
            # Download PDF
            cache_path = PDF_CACHE_DIR / filename
            if cache_path.exists():
                pdf_bytes = cache_path.read_bytes()
            else:
                s3_client.download_file(S3_BUCKET, s3_key, str(cache_path))
                pdf_bytes = cache_path.read_bytes()

            # Split into chunks
            chunks = split_pdf(pdf_bytes, PAGES_PER_CHUNK)
            log(f"  Split into {len(chunks)} chunks ({PAGES_PER_CHUNK} pages each)")

            # Convert each chunk
            all_markdown = []
            start_time = time.time()
            for j, (start, end, total, chunk_bytes) in enumerate(chunks):
                log(f"  Chunk {j+1}/{len(chunks)} (pages {start}-{end}/{total})")
                chunk_md = convert_chunk(bedrock_client, chunk_bytes, start, end, total)
                all_markdown.append(chunk_md)
                if j < len(chunks) - 1:
                    time.sleep(5)

            elapsed = time.time() - start_time

            # Merge: first chunk as-is, subsequent chunks remove duplicate title if any
            merged = all_markdown[0]
            for part in all_markdown[1:]:
                # Add a separator comment between chunks
                merged += f"\n\n<!-- chunk boundary -->\n\n{part}"

            md_path.write_text(merged, encoding="utf-8")
            md_size = len(merged)

            # Update manifest (remove from errors, add to completed)
            manifest["completed"][filename] = {
                "md_file": str(md_path),
                "md_size_chars": md_size,
                "elapsed_sec": round(elapsed, 1),
                "chunks": len(chunks),
                "converted_at": datetime.now(timezone.utc).isoformat(),
            }
            if filename in manifest.get("errors", {}):
                del manifest["errors"][filename]
            save_manifest(manifest)

            log(f"  ✓ Done — {md_size:,} chars, {len(chunks)} chunks, {elapsed:.0f}s")

        except Exception as e:
            log(f"  ✗ FAILED: {str(e)[:300]}")
            manifest["errors"][filename] = {
                "error": str(e)[:500],
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
            save_manifest(manifest)

    # Summary
    completed = len([f for f in FAILED_FILES if f.replace("uploads/", "") in manifest.get("completed", {})])
    log(f"\n{'='*60}")
    log(f"Split conversion: {completed}/{len(FAILED_FILES)} completed")
    log(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
