#!/usr/bin/env python3
"""Warmup script for GraphRAG Engine.

Sends a lightweight health check + embedding warm query on container startup
to pre-initialize connections and populate the embedding LRU cache.

Usage:
    python scripts/warmup.py [--base-url http://localhost:8000]
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error


def check_health(base_url: str) -> bool:
    """Hit /v1/health and verify all backends are reachable."""
    url = f"{base_url}/v1/health"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            status = data.get("status")
            print(f"[warmup] health: {status} — checks: {data.get('checks')}")
            return status == "healthy"
    except urllib.error.URLError as e:
        print(f"[warmup] health check failed: {e}")
        return False


def warmup_chat(base_url: str) -> bool:
    """Send a minimal chat request to warm up embedding cache + Gremlin pool."""
    url = f"{base_url}/v1/chat"
    payload = json.dumps({
        "messages": [{"role": "user", "content": "보험 상품 안내"}],
        "persona": "presenter",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            lines = body.strip().split("\n")
            text_chunks = [l for l in lines if l.startswith("0:")]
            annotation_chunks = [l for l in lines if l.startswith("8:")]
            print(f"[warmup] chat: {len(text_chunks)} text chunks, {len(annotation_chunks)} annotations")
            return len(text_chunks) > 0
    except urllib.error.URLError as e:
        print(f"[warmup] chat warmup failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="GraphRAG Engine warmup")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--delay", type=float, default=3.0)
    args = parser.parse_args()

    print(f"[warmup] target: {args.base_url}")

    # Wait for health endpoint with retries
    healthy = False
    for attempt in range(1, args.retries + 1):
        print(f"[warmup] health check attempt {attempt}/{args.retries}")
        if check_health(args.base_url):
            healthy = True
            break
        if attempt < args.retries:
            time.sleep(args.delay)

    if not healthy:
        print("[warmup] WARNING: service not fully healthy, proceeding with warmup anyway")

    # Warm up the pipeline
    t0 = time.monotonic()
    ok = warmup_chat(args.base_url)
    elapsed = int((time.monotonic() - t0) * 1000)
    print(f"[warmup] pipeline warmup {'succeeded' if ok else 'failed'} in {elapsed}ms")

    if not ok:
        print("[warmup] WARNING: warmup chat failed — service may be degraded")
        sys.exit(1)

    print("[warmup] done")


if __name__ == "__main__":
    main()
