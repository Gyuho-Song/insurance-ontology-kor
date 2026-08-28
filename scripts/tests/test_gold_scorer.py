"""U3 — GoldScorer example-based tests (합성 fixture, scorer 독립)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from lib.gold_scorer import GoldScorer, normalize_label  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FIXG = Path(__file__).resolve().parent / "fixtures" / "gold"


def _load_extracted(name):
    return json.loads((FIXG / name).read_text(encoding="utf-8"))


# ── load_gold (strict, _schema.json) ────────────────────────
def test_load_gold_real_dir():
    scorer, docs = GoldScorer.load_gold(REPO / "gold")
    assert scorer.meta.schema_version == 1
    assert scorer.meta.tbox_sha256
    assert any(d["document_id"] == "hwl_signature_h_cancer" for d in docs)

def test_load_gold_missing_schema_hard_fail(tmp_path):
    (tmp_path / "x.jsonl").write_text('{"document_id":"a"}\n')
    with pytest.raises(FileNotFoundError):
        GoldScorer.load_gold(tmp_path)

def test_load_gold_strict_rejects_comment(tmp_path):
    (tmp_path / "_schema.json").write_text('{"schema_version":1,"tbox_sha256":"x"}')
    (tmp_path / "g.jsonl").write_text('// comment\n{"document_id":"a"}\n')
    with pytest.raises(json.JSONDecodeError):
        GoldScorer.load_gold(tmp_path)


# ── normalize_label (whitelist, variant 보존) ───────────────
def test_normalize_preserves_variants():
    assert normalize_label("일반가입형") != normalize_label("간편가입형")
    assert normalize_label("90 세만기") == "90세만기"
    assert normalize_label("5 년납") == "5년납"


# ── 합성 fixture 채점 ───────────────────────────────────────
@pytest.fixture
def scorer():
    s, _ = GoldScorer.load_gold(REPO / "gold")
    return s

def test_perfect_match_p(scorer):
    gold = [json.loads(l) for l in (FIXG / "synthetic_gold.jsonl").read_text().splitlines() if l.strip()]
    gold_p = [g for g in gold if g["document_id"] == "syn_P"]
    ext = {"syn_P": _load_extracted("synthetic_extracted_perfect.json")}
    rep = scorer.score(gold_p, ext)
    assert rep.entity_f1 == 1.0
    assert rep.relation_f1 == 1.0
    assert rep.fact_accuracy["numeric_accuracy"] == 1.0
    assert rep.fact_accuracy["boundary_accuracy"] == 1.0
    assert rep.fact_accuracy["provenance_coverage"] == 1.0
    assert rep.passed is True

def test_missing_entity_fn(scorer):
    gold = [json.loads(l) for l in (FIXG / "synthetic_gold.jsonl").read_text().splitlines() if l.strip()]
    gold_p = [g for g in gold if g["document_id"] == "syn_P"]
    rep = scorer.score(gold_p, {"syn_P": {"entities": [], "relations": []}})
    assert rep.entity_f1 == 0.0   # 추출 0 → FN
    assert rep.passed is False

def test_numeric_wrong_fails_gate(scorer):
    gold = [{"document_id": "d", "entities": [
        {"entity_id": "x", "category": "P", "type": "Eligibility", "label": "나이",
         "properties": {"min_age": 15, "max_age": 80}, "provenance": {}}], "relations": []}]
    # max_age를 틀리게 추출
    ext = {"d": {"entities": [{"id": "X", "type": "Eligibility", "label": "나이",
            "properties": {"min_age": 15, "max_age": 79},
            "provenance": {"table_id": "t", "row_idx": 1}}], "relations": []}}
    rep = scorer.score(gold, ext)
    # 속성 불일치 → 엔티티 매칭 실패(FN), gate 불통과
    assert rep.passed is False

def test_category_aggregation(scorer):
    gold = [json.loads(l) for l in (FIXG / "synthetic_gold.jsonl").read_text().splitlines() if l.strip()]
    rep = scorer.score(gold, {})  # 추출 없음 → 전부 FN
    assert "P" in rep.by_category
    assert "E" in rep.by_category
