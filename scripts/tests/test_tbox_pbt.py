"""U2 TBoxValidator — property-based tests (Hypothesis, PBT-03).

적용 속성:
- idempotent: 같은 입력 재검증 → 동일 결과
- monotone: known_exception은 위반을 강등만 (errors_excluding_known <= errors)
"""
import sys
from pathlib import Path

from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from lib.tbox import TBoxSpec, TBoxValidator  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = TBoxSpec.load(REPO_ROOT / "tbox.yaml")

NODE_TYPES = list(SPEC.node_types)
EDGE_TYPES = list(SPEC.edge_types)


# 도메인 생성기: 현실적 엔티티/관계 (PBT-07 generator quality)
@st.composite
def entity(draw):
    et = draw(st.sampled_from(NODE_TYPES))
    i = draw(st.integers(min_value=0, max_value=50))
    return {
        "id": f"{et}#n{i}", "type": et, "label": f"l{i}",
        "provenance": {"source_text": draw(st.sampled_from(["t", ""])),
                       "source_section_id": "s", "confidence": 0.7},
        "properties": {},
    }


@st.composite
def relation(draw):
    rt = draw(st.sampled_from(EDGE_TYPES))
    a = draw(st.integers(min_value=0, max_value=50))
    b = draw(st.integers(min_value=0, max_value=50))
    return {"source_id": f"Policy#n{a}", "type": rt, "target_id": f"Coverage#n{b}",
            "provenance": {"source_text": "t", "source_section_id": "s", "confidence": 0.7}}


@settings(max_examples=100, deadline=None)
@given(ents=st.lists(entity(), max_size=20), rels=st.lists(relation(), max_size=20))
def test_validate_idempotent(ents, rels):
    v = TBoxValidator(SPEC)
    r1 = v.validate(ents, rels, profile="report")
    r2 = v.validate(ents, rels, profile="report")
    assert len(r1.errors) == len(r2.errors)
    assert len(r1.warnings) == len(r2.warnings)
    assert len(r1.gaps) == len(r2.gaps)


@settings(max_examples=100, deadline=None)
@given(ents=st.lists(entity(), max_size=20), rels=st.lists(relation(), max_size=20))
def test_known_exception_monotone(ents, rels):
    rep = TBoxValidator(SPEC).validate(ents, rels, profile="report")
    # known_exception은 강등만 — 진짜 ERROR를 새로 만들거나 늘리지 않음
    assert len(rep.errors_excluding_known) <= len(rep.errors)
