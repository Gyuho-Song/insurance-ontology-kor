"""U4 — TableMapper unit tests (U3 무관, 합성 fixture)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from lib.table_mapper import (  # noqa: E402
    TableMapper, classify_table, _extract_numeric, to_graph_ready,
    reconcile_table_and_llm, EntityCandidate,
)
from lib.parsed_doc import ParsedDoc  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "tablemapper"


def _load(name) -> ParsedDoc:
    import json
    return ParsedDoc.from_dict(json.loads((FIX / name).read_text(encoding="utf-8")))


# ── _extract_numeric (deterministic) ───────────────────────
def test_age_range():
    facts = _extract_numeric("만 15 세 ~80 세")
    fd = {f.field: f for f in facts}
    assert fd["min_age"].value == 15
    assert fd["max_age"].value == 80 and fd["max_age"].inclusive is True

def test_bmi_exclusive():
    facts = _extract_numeric("25 미만")
    bmi = [f for f in facts if f.field == "bmi"][0]
    assert bmi.value == 25.0 and bmi.inclusive is False and bmi.operator == "LT"

def test_threshold_50():
    facts = _extract_numeric("50% 이상")
    th = [f for f in facts if f.field == "disability_threshold"][0]
    assert th.value == 50 and th.inclusive is True

def test_percent_rate():
    facts = _extract_numeric("2%")
    assert [f for f in facts if f.field == "rate"][0].value == 0.02

def test_extract_idempotent():
    assert _extract_numeric("만 15 세 ~80 세") == _extract_numeric("만 15 세 ~80 세")


# ── classify_table ─────────────────────────────────────────
def test_classify_p():
    assert "eligibility_criteria" in classify_table(_load("synthetic_P.parsed.json").tables[0])

def test_classify_e():
    assert "discount_rate" in classify_table(_load("synthetic_E.parsed.json").tables[0])

def test_classify_j():
    assert "waiver_condition" in classify_table(_load("synthetic_J.parsed.json").tables[0])


# ── map: 도메인별 typed 엔티티 ──────────────────────────────
def test_map_p_typed_eligibility():
    pd = _load("synthetic_P.parsed.json")
    ents, rels = TableMapper("Policy#syn_P").map(pd)
    elig = [e for e in ents if e.type == "Eligibility"]
    assert elig and elig[0].properties["min_age"] == 15
    assert elig[0].properties["max_age"] == 80
    assert elig[0].properties["max_age_inclusive"] is True
    assert any(r.type == "REQUIRES_ELIGIBILITY" for r in rels)

def test_map_e_discount():
    ents, _ = TableMapper("Policy#syn_E").map(_load("synthetic_E.parsed.json"))
    pd_ent = [e for e in ents if e.type == "Premium_Discount"]
    assert pd_ent and pd_ent[0].properties["discount_rate"] == 0.02

def test_map_j_waiver_coverage_kind():
    ents, rels = TableMapper("Policy#syn_J").map(_load("synthetic_J.parsed.json"))
    cov = [e for e in ents if e.type == "Coverage"]
    assert cov and cov[0].properties["coverage_kind"] == "premium_waiver"
    assert cov[0].properties["disability_threshold"] == 50
    assert any(r.type == "WAIVES_PREMIUM" for r in rels)

def test_map_g_calculated_by_parent():
    ents, rels = TableMapper("Policy#syn_G").map(_load("synthetic_G.parsed.json"))
    calc = [e for e in ents if e.type == "Calculation"]
    assert calc
    cb = [r for r in rels if r.type == "CALCULATED_BY"]
    assert cb  # parent resolution → relation 존재 (dangling 아님)


# ── evidence shape + to_graph_ready ─────────────────────────
def test_evidence_in_properties():
    pd = _load("synthetic_P.parsed.json")
    ents, rels = TableMapper("Policy#syn_P").map(pd)
    gr = to_graph_ready("syn_P", "syn_P", ents, rels)
    e0 = gr["entities"][0]
    assert "_evidence" in e0["properties"]
    ev = e0["properties"]["_evidence"][0]
    assert ev["table_id"] == "table-001" and ev["row_idx"] is not None


# ── reconcile (source priority) ─────────────────────────────
def test_reconcile_table_overrides_llm():
    t = [EntityCandidate("Eligibility", "가입나이", {"max_age": 80}, [{"table_id": "t"}], "P", "table")]
    l = [EntityCandidate("Eligibility", "가입나이", {"max_age": 79, "extra": "x"}, [{"src": "llm"}], "P", "llm")]
    merged, conflicts = reconcile_table_and_llm(t, l)
    assert len(merged) == 1
    assert merged[0].properties["max_age"] == 80         # 표 우선
    assert merged[0].properties["extra"] == "x"          # llm 보완
    assert len(merged[0].evidence) == 2                  # evidence 합집합
    assert any(c["prop"] == "max_age" for c in conflicts)
