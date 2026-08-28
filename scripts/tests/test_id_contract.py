"""U10 — id 계약(C1~C5) 단위테스트.

수정 전 RED로 작성(현 코드 기준): C1(콘텐츠기반 안정 id)·C2(법령 Policy 0)·C3(문서당 Policy 1)는 RED,
보존 불변식(dangling 0)은 GREEN이어야 정상. 코드 수정(P1-A) 후 전부 GREEN.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from lib.table_mapper import to_graph_ready, EntityCandidate, RelationCandidate  # noqa: E402


def _ev(tid="t1"):
    return [{"table_id": tid, "row_idx": 0, "col_idx": 0}]


def _product_ents():
    """product 문서 합성: Policy 1 + Coverage 2 (서로 다른 label)."""
    return [
        EntityCandidate("Policy", "한화생명 시그니처H암보험 무배당", {}, _ev(), "", "llm"),
        EntityCandidate("Coverage", "암진단보험금", {"amount": 1000}, _ev(), "", "table"),
        EntityCandidate("Coverage", "입원보험금", {"amount": 50}, _ev(), "", "table"),
    ]


def _rels():
    return [
        RelationCandidate("한화생명 시그니처H암보험 무배당", "HAS_COVERAGE", "암진단보험금", _ev(), ""),
        RelationCandidate("한화생명 시그니처H암보험 무배당", "HAS_COVERAGE", "입원보험금", _ev(), ""),
    ]


# ── 보존 불변식 (반드시 GREEN — 되돌리면 안 됨) ─────────────────
def test_dangling_zero_preserved():
    """관계 endpoint가 전부 엔티티 id 집합 안에 있어야 한다(dangling 0)."""
    gr = to_graph_ready("sig_cancer", "한화생명 시그니처H암보험 무배당",
                        _product_ents(), _rels(), policy_id="Policy#hwl_signature_h_cancer")
    ids = {e["id"] for e in gr["entities"]}
    dangling = [r for r in gr["relations"]
                if r["source_id"] not in ids or r["target_id"] not in ids]
    assert dangling == [], f"dangling 발생: {dangling}"


def test_no_enum_leak_preserved():
    """id/type에 'EntityType.' repr 누수가 없어야 한다."""
    gr = to_graph_ready("sig", "P", _product_ents(), _rels(), policy_id="Policy#x")
    bad = [e for e in gr["entities"]
           if str(e["id"]).startswith("EntityType.") or str(e["type"]).startswith("EntityType.")]
    assert bad == []


# ── C1: id는 콘텐츠 기반 안정키 (위치 인덱스 비종속) ────────────
def test_c1_id_stable_across_reorder():
    """같은 엔티티 집합이면 순서가 바뀌어도 같은 엔티티는 같은 id를 받아야 한다(C1).
    현 코드는 enumerate(i) 기반이라 순서 바뀌면 id가 바뀜 → RED 예상."""
    ents = _product_ents()
    gr1 = to_graph_ready("sig", "P", ents, _rels(), policy_id="Policy#x")
    reordered = [ents[2], ents[0], ents[1]]  # 순서만 섞음
    gr2 = to_graph_ready("sig", "P", reordered, _rels(), policy_id="Policy#x")
    id1 = {e["label"]: e["id"] for e in gr1["entities"]}
    id2 = {e["label"]: e["id"] for e in gr2["entities"]}
    assert id1 == id2, f"순서에 따라 id 변동(C1 위반): {id1} vs {id2}"


# ── C2: 법령 문서는 Policy 0개 ─────────────────────────────────
def test_c2_law_no_policy():
    """is_law 문서(policy_id=None)는 합성 Policy를 만들지 않는다(C2)."""
    law_ents = [
        EntityCandidate("Regulation", "보험업법 제1조", {}, _ev(), "", "llm"),
        EntityCandidate("Regulation", "보험업법 제2조", {}, _ev(), "", "llm"),
    ]
    gr = to_graph_ready("ins_law", "보험업법", law_ents, [], policy_id=None)
    policies = [e for e in gr["entities"] if e["type"] == "Policy"]
    assert policies == [], f"법령에 Policy 생성됨(C2 위반): {[p['id'] for p in policies]}"


# ── C3: product 문서당 Policy 정확히 1개 ───────────────────────
def test_c3_single_policy():
    """LLM이 같은 상품 Policy를 여러 label로 추출해도 최종 Policy는 1개여야 한다(C3)."""
    ents = [
        EntityCandidate("Policy", "한화생명 시그니처H암보험 무배당", {}, _ev(), "", "llm"),
        EntityCandidate("Policy", "시그니처H암보험", {}, _ev(), "", "llm"),  # 같은 상품 변형
        EntityCandidate("Coverage", "암진단보험금", {}, _ev(), "", "table"),
    ]
    gr = to_graph_ready("sig", "한화생명 시그니처H암보험 무배당", ents, [],
                        policy_id="Policy#hwl_signature_h_cancer")
    policies = [e for e in gr["entities"] if e["type"] == "Policy"]
    assert len(policies) == 1, f"Policy {len(policies)}개(C3 위반): {[p['label'] for p in policies]}"
