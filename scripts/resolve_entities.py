#!/usr/bin/env python3
"""U6 CLI — cross-document ER: GraphReadyData dir → ResolvedGraph (U7 입력).

Usage:
  python scripts/resolve_entities.py --input-dir <graph_ready/> \
      --output resolved_graph.json --merge-report merge_report.json \
      --glossary backend-app/app/data/glossary.json

ResolvedGraph.relations에 SAME_AS/SIMILAR_TO 포함(U7 load_v2_data가 일반 edge로 적재).
임베딩은 sync(boto3) — 실행 시에만 로드(테스트 무관).
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
from lib.entity_resolver import EntityResolver, ScopePolicy, EmbeddingCache  # noqa: E402


def _load_canonical(glossary_path: str | None) -> dict:
    """glossary → {variant: {canonical_label}} 평탄화 (P1-B RC5).
    기존엔 data.get('canonical_terms')만 봤는데 그 키가 없어 no-op이었음.
    synonyms({canon:[variants]}) + abbreviations({abbr:full})를 EntityResolver가
    기대하는 {variant:{'canonical_label':canon}} 형태로 변환."""
    if not glossary_path or not Path(glossary_path).exists():
        return {}
    data = json.loads(Path(glossary_path).read_text(encoding="utf-8"))
    out: dict = dict(data.get("canonical_terms", {}))  # 명시 canonical_terms 우선
    for canon, variants in (data.get("synonyms") or {}).items():
        for v in variants:
            out.setdefault(v, {"canonical_label": canon})
        out.setdefault(canon, {"canonical_label": canon})
    for abbr, full in (data.get("abbreviations") or {}).items():
        out.setdefault(abbr, {"canonical_label": full})
    return out


_BEDROCK = None


def _get_bedrock():
    """모듈 단위 client 재사용 + adaptive retry (RC2: 호출당 client 생성/throttle 미처리로 A3 폴백 방지)."""
    global _BEDROCK
    if _BEDROCK is None:
        import boto3, botocore.config
        cfg = botocore.config.Config(read_timeout=60, connect_timeout=10,
                                     retries={"max_attempts": 8, "mode": "adaptive"})
        _BEDROCK = boto3.client("bedrock-runtime", region_name="us-west-2", config=cfg)
    return _BEDROCK


def _sync_embed(text: str) -> list[float]:
    """boto3 Titan sync. throttle 시 지수 백오프 — embedding 폴백(no-embedding) 회피."""
    import time
    last = None
    for attempt in range(6):
        try:
            resp = _get_bedrock().invoke_model(
                modelId="amazon.titan-embed-text-v2:0",
                body=json.dumps({"inputText": text[:8000]}),
            )
            return json.loads(resp["body"].read())["embedding"]
        except Exception as e:  # noqa: BLE001
            last = e
            es = str(e)
            if "Throttl" in es or "TooManyRequests" in es or "ServiceUnavailable" in es:
                time.sleep(min(2 ** attempt, 30))
                continue
            raise
    raise last  # type: ignore[misc]


def _drop_invalid_edges(entities, relations, tbox_path):
    """tbox domain/range(R1) 위반 엣지를 적재 전 제거. same_type 엣지는 type 일치로 검증.
    LLM 관계가 tbox 위반(예: Rider→HAS_COVERAGE, Regulation→HAS_COVERAGE)을 만들 수 있어
    그래프 traversal 정확도를 위해 결정론적으로 거른다."""
    from lib.tbox import TBoxSpec
    spec = TBoxSpec.load(tbox_path)
    etype = {e["id"]: e.get("type") for e in entities}
    edge_spec = spec.edge_types
    kept, dropped = [], 0
    for r in relations:
        et = r.get("type")
        spec_e = edge_spec.get(et)
        if spec_e is None:  # 미정의 엣지타입은 R1 단계서 손대지 않음(별도 규칙)
            kept.append(r); continue
        st, tt = etype.get(r.get("source_id")), etype.get(r.get("target_id"))
        if st is None or tt is None:  # dangling은 여기서 판단 안 함
            kept.append(r); continue
        if spec_e.get("same_type"):
            ok = (st == tt)
        else:
            ok = st in (spec_e.get("domain") or []) and tt in (spec_e.get("range") or [])
        if ok:
            kept.append(r)
        else:
            dropped += 1
    return kept, dropped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="resolve_entities")
    ap.add_argument("--input-dir", required=True, help="GraphReadyData JSON 디렉토리")
    ap.add_argument("--output", required=True, help="ResolvedGraph 출력 경로")
    ap.add_argument("--merge-report", help="merge_report 출력 경로")
    ap.add_argument("--glossary", help="canonical_terms 소스(backend glossary.json)")
    ap.add_argument("--no-embedding", action="store_true", help="임베딩 비활성(Jaro-Winkler만)")
    ap.add_argument("--tbox", default="tbox.yaml", help="R1 엣지 검증용 tbox (domain/range)")
    ap.add_argument("--keep-invalid-edges", action="store_true",
                    help="domain/range 위반 엣지 유지(기본: 적재 전 제거)")
    args = ap.parse_args(argv)

    docs = []
    for f in sorted(Path(args.input_dir).glob("*.json")):
        if f.name.startswith("_"):
            continue
        docs.append(json.loads(f.read_text(encoding="utf-8")))

    cache = None if args.no_embedding else EmbeddingCache(_sync_embed)
    resolver = EntityResolver(ScopePolicy(), _load_canonical(args.glossary), cache)
    rg = resolver.resolve(docs)

    entities = rg.canonical_entities + rg.kept_separate
    relations = rg.relations
    if not args.keep_invalid_edges:
        relations, dropped = _drop_invalid_edges(entities, relations, args.tbox)
        if dropped:
            print(f"R1 필터: domain/range 위반 엣지 {dropped}건 제거 (적재 정확도)")

    out = {"document_id": "_resolved", "product_name": "_resolved",
           "entities": entities,
           "relations": relations,
           "extraction_metadata": {"extracted_at": "", "model_id": "er",
                                   "entity_count": len(entities),
                                   "relation_count": len(relations)}}
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.merge_report:
        Path(args.merge_report).write_text(json.dumps(rg.merge_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"resolved: {len(entities)} entities, {len(relations)} relations, "
          f"{len(rg.merge_report)} merge ops → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
