"""U5 — HonestyPolicy unit tests (fixture 기반, 선행물 무관)."""
from app.core.honesty_policy import (
    HonestyPolicy, TBoxSnapshot, AttributeConstraint, AbsenceEvidence,
    BoundaryQuery, Stance, extract_boundary_query, TARGET_INTENTS,
)


def _snapshot():
    return TBoxSnapshot({
        ("Eligibility", "max_age"): AttributeConstraint("max_age", max=80, inclusive=True),
        ("Eligibility", "bmi_max"): AttributeConstraint("bmi_max", max=25.0, inclusive=False),
    })


def _policy():
    return HonestyPolicy(_snapshot())


def _complete_evidence():
    return AbsenceEvidence(target_policy_resolved=True, target_template_executed=True,
                           target_edge_checked=True, fallback_used=False,
                           u4_gap_complete=True, retrieval_coverage=True)


# ── non-target intent → no-op ───────────────────────────────
def test_non_target_intent_present():
    r = _policy().decide("coverage_inquiry", {"edges": []}, AbsenceEvidence())
    assert r.stance == Stance.PRESENT


# ── boundary 우선 (P02/P03) ─────────────────────────────────
def test_boundary_age_81_rejected():
    p = _policy()
    bq = BoundaryQuery("max_age", 81, "세")
    c = AttributeConstraint("max_age", max=80, inclusive=True)
    r = p.decide("eligibility_inquiry", {"edges": [{"type": "REQUIRES_ELIGIBILITY"}]},
                 _complete_evidence(), boundary_q=bq, constraint=c)
    assert r.stance == Stance.CONFIRMED_ABSENT  # 81 > 80 → 가입불가
    assert r.boundary_eval is False
    assert "가입이 어렵" in r.deterministic_text

def test_boundary_bmi_25_exclusive_rejected():
    # P03: BMI 25.0, "25 미만"(exclusive) → 25.0 불포함 → 불가
    p = _policy()
    bq = BoundaryQuery("bmi_max", 25.0, "kg/m2")
    c = AttributeConstraint("bmi_max", max=25.0, inclusive=False)
    r = p.decide("eligibility_inquiry", {"edges": []}, _complete_evidence(),
                 boundary_q=bq, constraint=c)
    assert r.boundary_eval is False
    assert r.stance == Stance.CONFIRMED_ABSENT

def test_boundary_age_70_ok_present():
    p = _policy()
    bq = BoundaryQuery("max_age", 70, "세")
    c = AttributeConstraint("max_age", max=80, inclusive=True)
    r = p.decide("eligibility_inquiry", {"edges": []}, _complete_evidence(),
                 boundary_q=bq, constraint=c)
    assert r.boundary_eval is True and r.stance == Stance.PRESENT

def test_boundary_no_constraint_uncertain():
    # 경계메타 없음 → UNCERTAIN (LLM 금지)
    p = _policy()
    bq = BoundaryQuery("max_age", 81, "세")
    r = p.decide("eligibility_inquiry", {"edges": []}, _complete_evidence(),
                 boundary_q=bq, constraint=None)
    assert r.stance == Stance.UNCERTAIN


# ── CONFIRMED_ABSENT vs UNCERTAIN (closed-world, J04) ───────
def test_confirmed_absent_when_closed_world(j_intent="premium_waiver"):
    r = _policy().decide(j_intent, {"edges": []}, _complete_evidence())
    assert r.stance == Stance.CONFIRMED_ABSENT
    assert "없습니다" in r.deterministic_text

def test_fallback_used_forces_uncertain():
    # 빈 결과가 comprehensive fallback 탓 → CONFIRMED 금지
    ev = _complete_evidence()
    ev.fallback_used = True
    r = _policy().decide("premium_waiver", {"edges": []}, ev)
    assert r.stance == Stance.UNCERTAIN

def test_incomplete_evidence_uncertain():
    ev = AbsenceEvidence(target_policy_resolved=True)  # 나머지 False
    r = _policy().decide("premium_waiver", {"edges": []}, ev)
    assert r.stance == Stance.UNCERTAIN


# ── edge 존재 → PRESENT ─────────────────────────────────────
def test_edge_present():
    r = _policy().decide("premium_waiver", {"edges": [{"type": "WAIVES_PREMIUM"}]},
                         AbsenceEvidence())
    assert r.stance == Stance.PRESENT


# ── BoundaryQueryExtractor ──────────────────────────────────
def test_extract_age():
    q = extract_boundary_query("만 81세인데 가입 가능한가요?", "eligibility_inquiry")
    assert q.attribute_name == "max_age" and q.applicant_value == 81

def test_extract_bmi():
    q = extract_boundary_query("BMI 25.0인 사람 건강체 가입?", "eligibility_inquiry")
    assert q.attribute_name == "bmi_max" and q.applicant_value == 25.0

def test_extract_non_eligibility_none():
    assert extract_boundary_query("만 81세", "coverage_inquiry") is None


# ── 안전화 ──────────────────────────────────────────────────
def test_deterministic_text_length_capped():
    r = _policy().decide("premium_waiver", {"edges": []}, _complete_evidence())
    assert len(r.deterministic_text) <= 500


# ── P0-A RC1: topic-hit 게이팅 ───────────────────────────────
def test_p0a_topic_hit_present_routes_to_llm():
    """edge 부재 + topic_hits>0 → PRESENT(LLM 위임, deterministic_text=None)."""
    ev = AbsenceEvidence(entry_node_topic_hits=3)  # Premium_Discount 3개 검색됨
    r = _policy().decide("discount_eligibility", {"edges": [], "nodes": []}, ev)
    assert r.stance == Stance.PRESENT
    assert r.deterministic_text is None  # LLM 우회 안 함


def test_p0a_no_topic_hit_stays_uncertain():
    """edge 부재 + topic_hits=0(진짜 부재) → UNCERTAIN 유지(환각 차단)."""
    ev = AbsenceEvidence(entry_node_topic_hits=0)
    r = _policy().decide("discount_eligibility", {"edges": [], "nodes": []}, ev)
    assert r.stance == Stance.UNCERTAIN
    assert r.deterministic_text is not None


def test_p0a_edge_present_still_present():
    """edge 존재 → PRESENT (기존 동작 보존)."""
    r = _policy().decide("discount_eligibility",
                         {"edges": [{"type": "HAS_DISCOUNT"}]}, AbsenceEvidence())
    assert r.stance == Stance.PRESENT


def test_p0a_closed_world_absent():
    """closed-world 충족 → CONFIRMED_ABSENT (topic_hit보다 우선)."""
    ev = AbsenceEvidence(target_policy_resolved=True, target_template_executed=True,
                         target_edge_checked=True, fallback_used=False,
                         entry_node_topic_hits=0)
    r = _policy().decide("discount_eligibility", {"edges": []}, ev)
    assert r.stance == Stance.CONFIRMED_ABSENT


# ── P0-B RC2: boundary max 주입 + 경계 평가 ──────────────────
def test_p0b_boundary_age_within():
    """80세 ≤ 80 (inclusive) → PRESENT."""
    c = AttributeConstraint("max_age", max=80, inclusive=True)
    assert _policy().eval_boundary(c, BoundaryQuery("max_age", 80)) is True


def test_p0b_boundary_age_over():
    """81세 > 80 → 가입 불가(False)."""
    c = AttributeConstraint("max_age", max=80, inclusive=True)
    assert _policy().eval_boundary(c, BoundaryQuery("max_age", 81)) is False


def test_p0b_boundary_bp_over():
    """140 > 139 → 불가."""
    c = AttributeConstraint("bp_systolic_max", max=139, inclusive=True)
    assert _policy().eval_boundary(c, BoundaryQuery("bp_systolic_max", 140)) is False


def test_p0b_boundary_bmi_exclusive():
    """BMI 25 < 25 (exclusive) → False (경계 배타)."""
    c = AttributeConstraint("bmi_max", max=25.0, inclusive=False)
    assert _policy().eval_boundary(c, BoundaryQuery("bmi_max", 25.0)) is False


def test_p0b_bmi_regex_with_particle():
    """'BMI가 25.0' 조사 포함 매칭(P03 경로 진입)."""
    bq = extract_boundary_query("BMI가 25.0인 경우 가입 가능?", "eligibility_inquiry")
    assert bq is not None and bq.attribute_name == "bmi_max" and bq.applicant_value == 25.0
