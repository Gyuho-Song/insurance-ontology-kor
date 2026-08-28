"""U6 — PBT-02/03: normalize idempotent, MERGE 노드수 감소 invariant."""
import sys
from pathlib import Path
from hypothesis import given, settings, strategies as st
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.entity_resolver import EntityResolver, normalize_label, Decision

@settings(max_examples=100, deadline=None)
@given(s=st.text(max_size=20))
def test_normalize_idempotent(s):
    assert normalize_label(normalize_label(s)) == normalize_label(s)

@settings(max_examples=80, deadline=None)
@given(n=st.integers(min_value=1, max_value=10))
def test_legal_merge_reduces_nodes(n):
    # 동일 legal 엔티티 n개 → canonical 1개 (MERGE는 노드수 감소만)
    r = EntityResolver()
    docs = [{"entities": [{"id": f"R{i}", "type": "Regulation", "label": "제95조",
                           "properties": {"_evidence": [{"table_id": f"t{i}"}]}}],
             "relations": []} for i in range(n)]
    rg = r.resolve(docs)
    assert len(rg.canonical_entities) == 1
    assert len(rg.canonical_entities[0]["properties"]["_evidence"]) == n

@settings(max_examples=50, deadline=None)
@given(p1=st.text(min_size=1, max_size=3), p2=st.text(min_size=1, max_size=3))
def test_cross_product_never_merges(p1, p2):
    r = EntityResolver()
    a = {"id": "E1", "type": "Eligibility", "label": "가입나이", "properties": {"policy_id": p1}}
    b = {"id": "E2", "type": "Eligibility", "label": "가입나이", "properties": {"policy_id": p2}}
    d = r.decide_merge(a, b)
    if p1 != p2:
        assert d != Decision.MERGE   # 다른 policy → 절대 MERGE 안 함
