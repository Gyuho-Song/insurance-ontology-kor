"""U6 — EntityResolver unit tests (fixture, U2/실데이터 무관)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from lib.entity_resolver import (  # noqa: E402
    EntityResolver, Decision, ScopePolicy, scope_of, normalize_label,
    normalize_amount, EmbeddingCache,
)
from lib.entity_dedup import EntityRegistry  # noqa: E402
from lib.schemas import Entity, EntityProvenance, EntityType, RelationType  # noqa: E402


def _e(eid, etype, label, **props):
    return {"id": eid, "type": etype, "label": label, "properties": props}


# ── schema append ──────────────────────────────────────────
def test_same_as_relation_type_added():
    assert RelationType.SAME_AS == "SAME_AS"
    assert RelationType.SIMILAR_TO == "SIMILAR_TO"


# ── scope / normalize ──────────────────────────────────────
def test_scope_of():
    assert scope_of({"type": "Regulation"}) == "legal"
    assert scope_of({"type": "Product_Category"}) == "global"
    assert scope_of({"type": "Eligibility"}) == "product"

def test_normalize_amount():
    assert normalize_amount("3천만원") == "30000000원"

def test_normalize_label_idempotent():
    assert normalize_label(normalize_label("90 세만기")) == normalize_label("90 세만기")


# ── decide_merge: legal MERGE ──────────────────────────────
def test_legal_same_article_merge():
    r = EntityResolver()
    a = _e("R1", "Regulation", "보험업법 제95조")
    b = _e("R2", "Regulation", "보험업법 제95조")
    assert r.decide_merge(a, b) == Decision.MERGE


# ── decide_merge: product ──────────────────────────────────
def test_product_same_policy_props_equiv_merge():
    r = EntityResolver()
    a = _e("E1", "Eligibility", "가입나이", policy_id="P1", min_age=15, max_age=80)
    b = _e("E2", "Eligibility", "가입나이", policy_id="P1", min_age=15, max_age=80)
    assert r.decide_merge(a, b) == Decision.MERGE

def test_cross_product_never_merge_guard():
    # 같은 라벨+속성이라도 다른 policy → MERGE 금지 (코드 guard)
    r = EntityResolver()
    a = _e("E1", "Eligibility", "가입나이", policy_id="P1", min_age=15, max_age=80)
    b = _e("E2", "Eligibility", "가입나이", policy_id="P2", min_age=15, max_age=80)
    assert r.decide_merge(a, b) != Decision.MERGE   # KEEP or LINK

def test_product_no_policy_id_never_merge():
    r = EntityResolver()
    a = _e("E1", "Eligibility", "가입나이", min_age=15)
    b = _e("E2", "Eligibility", "가입나이", min_age=15)
    assert r.decide_merge(a, b) != Decision.MERGE


# ── resolve: evidence 합집합 + merge_report ────────────────
def test_resolve_legal_merge_evidence_union():
    r = EntityResolver()
    docs = [
        {"entities": [_e("R1", "Regulation", "제95조", _evidence=[{"table_id": "t1"}])], "relations": []},
        {"entities": [_e("R2", "Regulation", "제95조", _evidence=[{"table_id": "t2"}])], "relations": []},
    ]
    rg = r.resolve(docs)
    assert len(rg.canonical_entities) == 1
    ev = rg.canonical_entities[0]["properties"]["_evidence"]
    assert len(ev) == 2  # 합집합
    assert any(m["decision"] == "MERGE" for m in rg.merge_report)

def test_resolve_cross_product_kept():
    r = EntityResolver()
    docs = [
        {"entities": [_e("E1", "Eligibility", "가입나이", policy_id="P1")], "relations": []},
        {"entities": [_e("E2", "Eligibility", "가입나이", policy_id="P2")], "relations": []},
    ]
    rg = r.resolve(docs)
    # cross-product → MERGE 안 됨 (canonical 2개, MERGE 0)
    assert not any(m["decision"] == "MERGE" for m in rg.merge_report)


# ── entity_dedup product hard guard ────────────────────────
def _ent(eid, etype, label):
    return Entity(id=eid, type=etype, label=label,
                  provenance=EntityProvenance(source_section_id="s", source_text="t", confidence=0.9))

def test_dedup_product_no_fuzzy_merge():
    reg = EntityRegistry()
    reg.register(_ent("c1", EntityType.COVERAGE, "암진단보험금"))
    reg.register(_ent("c2", EntityType.COVERAGE, "암진단보험금A"))  # JW 높음
    # product type → fuzzy merge 안 함 → 2개 유지
    assert len(reg.get_all()) == 2

def test_dedup_legal_fuzzy_still_merges():
    reg = EntityRegistry()
    reg.register(_ent("r1", EntityType.REGULATION, "보험업법제95조"))
    reg.register(_ent("r2", EntityType.REGULATION, "보험업법제95조항"))  # JW 높음
    # legal type → fuzzy merge 유지
    assert len(reg.get_all()) == 1
