#!/usr/bin/env python3
"""U7 배치 — doc-parser 출력(final.md) → GraphReadyData (U4 표 경로 + 기존 LLM 텍스트 경로).

흐름 (문서별):
  final.md → DocParserAdapter.parse_file → ParsedDoc
    ├─ 표 경로: TableMapper.map → typed EntityCandidate (deterministic)
    └─ 텍스트 경로: section_splitter + extract_entities_v2(Opus 4.8 LLM)
  → reconcile_table_and_llm(표 우선) → GraphReadyData (properties._evidence)

출력: <out-dir>/{doc}.graph.json  (U6 resolve_entities 입력)
정책 (U4): policy_id/scope_key 주입(ER context), 표 deterministic numeric.

Usage:
  python scripts/build_graph_from_parsed.py --parsed-dir /tmp/dp_opus_full \
      --out-dir /mnt/data/v3-graph-ready --model us.anthropic.claude-opus-4-8
"""
import argparse
import json
import os
import sys
from pathlib import Path

# FC9: LLM 텍스트 추출도 Opus 4.8로 (데이터 정확성 최우선). extract_entities_v2 import 전에 설정.
os.environ.setdefault("EXTRACT_MODEL_ID", "us.anthropic.claude-opus-4-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
from lib.docparser_adapter import DocParserAdapter  # noqa: E402
from lib.table_mapper import TableMapper, to_graph_ready, reconcile_table_and_llm, EntityCandidate, _type_str  # noqa: E402
from lib.section_splitter import split_parsed_doc  # noqa: E402


def _derive_policy_id(doc_id: str) -> str:
    return f"Policy#{doc_id}"


def build_one(final_md: Path, doc_id: str, source_pdf: str,
              use_llm: bool = True) -> dict:
    """final.md → GraphReadyData dict. 표 경로(U4) + LLM 텍스트 경로(extract_entities_v2, Opus4.8) 결합."""
    import extract_entities_v2 as ev2
    from lib.section_splitter import is_law_document

    adapter = DocParserAdapter(parser_version="docling-opus48", run_id=doc_id)
    pdoc = adapter.parse_file(final_md, source_pdf=source_pdf)
    policy_id = _derive_policy_id(doc_id)
    is_law = is_law_document(f"{doc_id}.pdf")
    product_name = ev2.derive_product_name(f"{doc_id}.pdf")

    # 표 경로 (U4 deterministic typed)
    table_ents, table_rels = TableMapper(policy_id).map(pdoc)
    for e in table_ents:
        e.properties.setdefault("policy_id", policy_id)
        e.properties.setdefault("scope_key", e.category or "product")

    # 텍스트 경로 (기존 LLM, Opus4.8) — 법령/본문 엔티티
    llm_entity_dicts: list[dict] = []
    llm_relations: list[dict] = []
    llm_id_to_typelabel: dict[str, tuple] = {}
    if use_llm:
        client = ev2.create_bedrock_client()
        sr = split_parsed_doc(pdoc, f"{doc_id}.md")
        from lib.entity_dedup import EntityRegistry
        reg = EntityRegistry()
        raw_ents = []
        for unit in sr.units:
            re_, _, _ = ev2.extract_entities_from_unit(client, unit, product_name, doc_id, is_law)
            raw_ents.extend(re_)
        ents_parsed = ev2.parse_raw_entities(raw_ents, doc_id)
        for e in ents_parsed:
            reg.register(e)
        ents_final = reg.get_all()
        raw_rels, _, _ = ev2.extract_relations(client, ents_final, sr.units, product_name, doc_id, is_law)
        rels_parsed = ev2.parse_raw_relations(raw_rels, {e.id for e in ents_final})
        # Entity 객체 → dict (reconcile/to_graph_ready 호환)
        for e in ents_final:
            # mode="json": EntityType enum → .value 문자열 ("Calculation"). 안 하면
            # f"{d['type']}" 가 "EntityType.CALCULATION" 누수 → id 네임스페이스 분열(RC1).
            d = e.model_dump(mode="json") if hasattr(e, "model_dump") else dict(e)
            props = dict(d.get("properties") or {})
            props.setdefault("policy_id", policy_id)
            props.setdefault("scope_key", "legal" if is_law else "product")
            props.setdefault("_evidence", [{"source_pdf": source_pdf, "parser_version": "opus48-llm"}])
            llm_entity_dicts.append(EntityCandidate(
                type=d["type"], label=d["label"], properties=props,
                evidence=props["_evidence"], category="", source="llm"))
        llm_relations = [r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r) for r in rels_parsed]
        # RC1: LLM 엔티티 원본 id → (type,label). to_graph_ready 재부여 id로 관계 endpoint remap에 사용.
        for e in ents_final:
            llm_id_to_typelabel[e.id] = (_type_str(e.type), e.label)

    # reconcile (표 우선) — 표 typed + LLM 텍스트
    merged_ents, conflicts = reconcile_table_and_llm(table_ents, llm_entity_dicts)
    # C2: 법령 문서는 합성 Policy 생성 안 함(policy_id=None). product만 literal 참조 해소.
    gr = to_graph_ready(doc_id, product_name, merged_ents, table_rels,
                        policy_id=None if is_law else policy_id)

    # RC1+C3: LLM 관계 endpoint를 재부여 id로 remap. 권위 매핑은 to_graph_ready의 _label_to_id
    # (흡수된 Policy label 포함) → label 기준으로 해소해야 흡수 Policy 참조가 dangling 안 됨.
    label_to_id = gr.get("_label_to_id", {})
    entity_ids = {x["id"] for x in gr["entities"]}
    typelabel_to_newid = {(x["type"], x["label"]): x["id"] for x in gr["entities"]}
    remapped = dropped = 0
    kept_llm_rels = []
    for r in llm_relations:
        ok = True
        for end in ("source_id", "target_id"):
            tl = llm_id_to_typelabel.get(r.get(end))
            new = None
            if tl:
                # 1순위 (type,label) 직접 매칭, 2순위 label_to_id(흡수 Policy 등)
                new = typelabel_to_newid.get(tl) or label_to_id.get(tl[1])
            if new:
                r[end] = new; remapped += 1
            elif r.get(end) not in entity_ids:
                ok = False  # 해소 불가 endpoint → dangling 방지 위해 관계 드롭
        if ok:
            kept_llm_rels.append(r)
        else:
            dropped += 1
    llm_relations = kept_llm_rels
    gr["_llm_rel_dropped"] = dropped
    gr["relations"].extend(llm_relations)

    # ── P1-A RC4: 구조 엣지 결정론적 보강 ──────────────────────────
    # LLM relation recall 편차로 자식 엔티티가 Policy에 안 붙는 고아 대량(54%). 각 자식의
    # 실제 Policy(문서당 1개, C3)로부터 타입별 엣지를 결정론적으로 생성(LLM 의존 제거).
    # 법령 문서(is_law)는 상품 Policy가 없으므로 제외.
    if not is_law:
        policy_node_id = next((e["id"] for e in gr["entities"] if e["type"] == "Policy"), None)
        if policy_node_id:
            _CHILD_EDGE = {
                "Coverage": "HAS_COVERAGE", "Rider": "HAS_RIDER",
                "Eligibility": "REQUIRES_ELIGIBILITY", "Surrender_Value": "SURRENDER_PAYS",
                "Premium_Discount": "HAS_DISCOUNT", "Dividend_Method": "NO_DIVIDEND_STRUCTURE",
            }
            existing = {(r["source_id"], r["type"], r["target_id"]) for r in gr["relations"]}
            added = 0
            for e in gr["entities"]:
                etype = e["type"]; rtype = _CHILD_EDGE.get(etype)
                if not rtype or e["id"] == policy_node_id:
                    continue
                key = (policy_node_id, rtype, e["id"])
                if key in existing:
                    continue
                gr["relations"].append({
                    "source_id": policy_node_id, "type": rtype, "target_id": e["id"],
                    "properties": {"_evidence": [{"source": "structural-deterministic"}]},
                    "provenance": {"source_section_id": "", "source_text": "", "confidence": 0.85},
                })
                existing.add(key); added += 1
            gr["_structural_edges_added"] = added

    gr["_conflicts"] = conflicts
    gr["_llm_rel_remapped"] = remapped
    return gr


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build_graph_from_parsed")
    ap.add_argument("--parsed-dir", required=True, help="doc-parser 출력 루트(각 문서 폴더)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--no-llm", action="store_true", help="텍스트 LLM 경로 생략(표 경로만)")
    args = ap.parse_args(argv)

    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    final_mds = sorted(Path(args.parsed_dir).glob("*/*_final.md"))
    print(f"{len(final_mds)} documents found")

    use_llm = not args.no_llm   # 기본 True(LLM 텍스트 경로 Opus4.8 결합)

    total_e = total_r = 0
    for fmd in final_mds:
        doc_id = fmd.parent.name
        try:
            gr = build_one(fmd, doc_id, source_pdf=f"{doc_id}.pdf", use_llm=use_llm)
        except Exception as e:
            print(f"  {doc_id}: FAIL {type(e).__name__}: {e}")
            continue
        (out / f"{doc_id}.graph.json").write_text(
            json.dumps(gr, ensure_ascii=False, indent=2), encoding="utf-8")
        total_e += len(gr["entities"]); total_r += len(gr["relations"])
        print(f"  {doc_id}: {len(gr['entities'])}E {len(gr['relations'])}R")
    print(f"TOTAL: {total_e} entities, {total_r} relations → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
