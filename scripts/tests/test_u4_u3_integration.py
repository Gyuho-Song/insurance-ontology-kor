"""U4↔U3 integration: TableMapper 산출 → GoldScorer gate 실측.

선행물(gold_scorer) 부재 시 skip — U4 unit RED가 U3에 막히지 않음.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

pytest.importorskip("lib.gold_scorer")
from lib.gold_scorer import GoldScorer, GoldMeta  # noqa: E402
from lib.table_mapper import TableMapper, to_graph_ready  # noqa: E402
from lib.parsed_doc import ParsedDoc  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "tablemapper"


def test_p_extraction_passes_u3_gate():
    # 1) U4: 합성 P fixture → GraphReadyData
    pd = ParsedDoc.from_dict(json.loads((FIX / "synthetic_P.parsed.json").read_text()))
    ents, rels = TableMapper("Policy#syn_P").map(pd)
    gr = to_graph_ready("syn_P", "syn_P", ents, rels)

    # 2) gold (P fact: min15/max80/inclusive, REQUIRES_ELIGIBILITY)
    gold = [{
        "document_id": "syn_P",
        "entities": [{"entity_id": "g1", "category": "P", "type": "Eligibility",
                      "label": gr["entities"][0]["label"],
                      "properties": {"min_age": 15, "max_age": 80},
                      "provenance": {"table_id": "table-001", "row_idx": 1}}],
        "relations": [{"category": "P", "source_id": "Policy#syn_P",
                       "type": "REQUIRES_ELIGIBILITY", "target_id": "g1"}],
    }]
    meta = GoldMeta(1, "x", {}, {"numeric_rate": 0.001})
    rep = GoldScorer(meta).score(gold, {"syn_P": gr})

    # 3) gate 실측 — 추출→채점 루프 첫 폐쇄
    assert rep.entity_f1 == 1.0
    assert rep.relation_f1 == 1.0
    assert rep.fact_accuracy["numeric_accuracy"] == 1.0
    assert rep.fact_accuracy["provenance_coverage"] == 1.0
    assert rep.passed is True
