#!/usr/bin/env python3
"""U3 — Extraction quality CLI: gold fact set vs extracted(GraphReadyData) 채점.

Usage:
  python scripts/eval_extraction.py --gold gold/ --extracted out.json
  python scripts/eval_extraction.py --gold gold/ --extracted-dir out/ --glob '*.graph.json' \
      --category E,G,J,P --report-json report.json

gate 미통과 시 exit 2.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
from lib.gold_scorer import GoldScorer  # noqa: E402


def _load_extracted_files(args) -> dict[str, dict]:
    out: dict[str, dict] = {}
    files = []
    if args.extracted:
        files = [Path(args.extracted)]
    elif args.extracted_dir:
        files = sorted(Path(args.extracted_dir).glob(args.glob))
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d["document_id"]] = d
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="eval_extraction")
    ap.add_argument("--gold", required=True, help="gold/ 디렉토리 (_schema.json + *.jsonl)")
    ap.add_argument("--extracted", help="단일 GraphReadyData JSON")
    ap.add_argument("--extracted-dir", help="GraphReadyData 디렉토리")
    ap.add_argument("--glob", default="*.json")
    ap.add_argument("--category", help="쉼표구분 카테고리 필터 (예: E,G,J,P)")
    ap.add_argument("--report-json", help="ScoreReport JSON 출력 경로")
    args = ap.parse_args(argv)

    scorer, gold_docs = GoldScorer.load_gold(args.gold)
    if args.category:
        cats = set(args.category.split(","))
        for gd in gold_docs:
            gd["entities"] = [e for e in gd.get("entities", []) if e.get("category") in cats]
            gd["relations"] = [r for r in gd.get("relations", []) if r.get("category") in cats]

    extracted = _load_extracted_files(args)
    rep = scorer.score(gold_docs, extracted)

    summary = {
        "entity_f1": round(rep.entity_f1, 4), "relation_f1": round(rep.relation_f1, 4),
        "fact_accuracy": rep.fact_accuracy, "by_category": rep.by_category,
        "passed": rep.passed,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.report_json:
        Path(args.report_json).write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    return 0 if rep.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
