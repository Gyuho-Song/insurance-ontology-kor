"""U3 — GoldScorer PBT (PBT-02 round-trip, PBT-03 invariant)."""
import json
import sys
from pathlib import Path

from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from lib.gold_scorer import GoldScorer, GoldMeta  # noqa: E402

META = GoldMeta(schema_version=1, tbox_sha256="x",
                required_props={}, tolerance={"numeric_rate": 0.001})


# 도메인 생성기: gold 엔티티 (PBT-07)
@st.composite
def gold_doc(draw):
    n = draw(st.integers(min_value=0, max_value=5))
    ents = []
    for i in range(n):
        ents.append({
            "entity_id": f"e{i}", "category": "P", "type": "Eligibility",
            "label": f"나이{i}",
            "properties": {"min_age": draw(st.integers(0, 100)),
                           "max_age": draw(st.integers(0, 100))},
            "provenance": {"table_id": "t", "row_idx": i},
        })
    return {"document_id": "d", "entities": ents, "relations": []}


def _to_extracted(gd):
    """gold를 그대로 extracted(GraphReadyData)로 변환 — pred가 각 gold fact 정확히 1회 포함."""
    return {"d": {"entities": [
        {"id": f"X{i}", "type": e["type"], "label": e["label"],
         "properties": dict(e["properties"]),
         "provenance": {"table_id": "t", "row_idx": i}}
        for i, e in enumerate(gd["entities"])], "relations": []}}


@settings(max_examples=100, deadline=None)
@given(gd=gold_doc())
def test_score_idempotent(gd):
    scorer = GoldScorer(META)
    ext = _to_extracted(gd)
    r1 = scorer.score([gd], ext)
    r2 = scorer.score([gd], ext)
    assert r1.entity_f1 == r2.entity_f1
    assert r1.fact_accuracy == r2.fact_accuracy


@settings(max_examples=100, deadline=None)
@given(gd=gold_doc())
def test_recall_1_when_pred_contains_each_gold_fact_once_plus_disjoint_fp(gd):
    # 전제: pred가 각 gold fact를 정확히 1회 포함 (+ FP 없음 케이스)
    scorer = GoldScorer(META)
    ext = _to_extracted(gd)
    rep = scorer.score([gd], ext)
    # 모든 gold 엔티티가 매칭 → recall(=entity precision/recall 분모) 관점에서 FN=0
    assert rep.recall == 1.0
