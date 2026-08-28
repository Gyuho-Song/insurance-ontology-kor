"""U5 — HonestyPolicy: Stage 8 답변생성 *전* deterministic 게이트.

answer_generator 프롬프트 강화로 못 막은 J04/P02/P03/P08 환각을, 생성 전 분기로 차단.
- boundary 우선: 가입연령/BMI/혈압 → eval_boundary deterministic (PRESENT여도 LLM 안 거침)
- CONFIRMED_ABSENT: closed-world 5신호 전부(특히 fallback_used=False) → 확정 부재
- UNCERTAIN: 불확실 시 한계 고지 (대상 intent 실패도 UNCERTAIN, PRESENT 금지)
- 대상 intent만 개입, 그 외 no-op(PRESENT)

LLM 무관 deterministic. tbox는 startup 캐시(TBoxSnapshot).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Stance(str, Enum):
    PRESENT = "PRESENT"                    # 기존 LLM 생성
    CONFIRMED_ABSENT = "CONFIRMED_ABSENT"  # deterministic "없음"
    UNCERTAIN = "UNCERTAIN"                # 한계 고지


# ── ③ TargetIntentContract ──────────────────────────────────
@dataclass(frozen=True)
class IntentContract:
    template_id: str
    target_edge: str
    target_node: str
    boundary: bool = False


TARGET_INTENTS: dict[str, IntentContract] = {
    "premium_waiver": IntentContract("premium_waiver_lookup", "WAIVES_PREMIUM", "Coverage"),
    "eligibility_inquiry": IntentContract("eligibility_lookup", "REQUIRES_ELIGIBILITY", "Eligibility", boundary=True),
    "discount_eligibility": IntentContract("discount_eligibility", "HAS_DISCOUNT", "Premium_Discount"),
    "surrender_value": IntentContract("surrender_value_lookup", "SURRENDER_PAYS", "Surrender_Value"),
    "calculation_inquiry": IntentContract("calculation_lookup", "CALCULATED_BY", "Calculation"),
}


# ── ① TBoxSnapshot ──────────────────────────────────────────
@dataclass(frozen=True)
class AttributeConstraint:
    attribute_name: str
    min: float | None = None
    max: float | None = None
    inclusive: bool = True   # max 경계 포함 여부


@dataclass
class TBoxSnapshot:
    constraints: dict[tuple[str, str], AttributeConstraint] = field(default_factory=dict)

    @classmethod
    def from_tbox_dict(cls, tbox: dict) -> "TBoxSnapshot":
        """tbox.yaml property_schemas → AttributeConstraint 캐시."""
        out: dict[tuple[str, str], AttributeConstraint] = {}
        for etype, props in (tbox.get("property_schemas") or {}).items():
            for attr, meta in props.items():
                if not isinstance(meta, dict):
                    continue
                if meta.get("dtype") in ("int", "float") and ("max" in attr or "min" in attr or "age" in attr or "bmi" in attr or "bp" in attr):
                    out[(etype, attr)] = AttributeConstraint(
                        attribute_name=attr,
                        inclusive=bool(meta.get("inclusive", True)),
                    )
        return cls(out)


# ── ② AbsenceEvidence ───────────────────────────────────────
@dataclass
class AbsenceEvidence:
    target_policy_resolved: bool = False
    target_template_executed: bool = False
    target_edge_checked: bool = False
    fallback_used: bool = True       # 보수적 기본값 (모르면 fallback 가정 → UNCERTAIN)
    u4_gap_complete: bool = False
    retrieval_coverage: bool = False
    # P0-A RC1: 검색이 찾은 target 타입 노드 수(예 Premium_Discount). >0이면 "데이터는 있는데
    # 라우팅이 edge를 못 탄 것"이므로 UNCERTAIN 단락 대신 LLM에 위임. 0이면 진짜 부재 → 보수적.
    entry_node_topic_hits: int = 0

    def closed_world_ok(self) -> bool:
        # P0-A RC1: u4_gap_complete 하드코딩 의존 제거 (신호로 기능 안 함).
        return (self.target_policy_resolved and self.target_template_executed
                and self.target_edge_checked and (not self.fallback_used))


# ── ④ BoundaryQuery ─────────────────────────────────────────
@dataclass
class BoundaryQuery:
    attribute_name: str
    applicant_value: float
    unit: str = ""


_AGE_Q = re.compile(r"만?\s*(\d+)\s*세")
# P0-B RC2: 'BMI가 25.0' 같은 조사/공백 허용 (이전 r'BMI\s*'는 한국어 조사 매칭 실패)
_BMI_Q = re.compile(r"BMI\D{0,3}(\d+(?:\.\d+)?)", re.IGNORECASE)
_BP_Q = re.compile(r"(\d+)\s*mmHg")


def extract_boundary_query(query: str, intent_type: str) -> BoundaryQuery | None:
    """질문에서 boundary 값 추출 (eligibility_inquiry 대상)."""
    if intent_type != "eligibility_inquiry":
        return None
    if (m := _BMI_Q.search(query)):
        return BoundaryQuery("bmi_max", float(m.group(1)), "kg/m2")
    if (m := _BP_Q.search(query)):
        return BoundaryQuery("bp_systolic_max", float(m.group(1)), "mmHg")
    if (m := _AGE_Q.search(query)):
        return BoundaryQuery("max_age", float(m.group(1)), "세")
    return None


@dataclass
class ResponseStance:
    stance: Stance
    boundary_eval: bool | None = None
    deterministic_text: str | None = None
    rationale: str = ""


_ABSENT_LABEL = {"premium_waiver": "보험료 납입면제", "discount_eligibility": "보험료 할인",
                 "surrender_value": "해약환급금 정보", "calculation_inquiry": "계산식 정보"}


class HonestyPolicy:
    def __init__(self, snapshot: TBoxSnapshot):
        self.snapshot = snapshot

    def contract_for(self, intent_type: str) -> IntentContract | None:
        return TARGET_INTENTS.get(intent_type)

    def constraint_for(self, entity_type: str, attribute: str) -> AttributeConstraint | None:
        return self.snapshot.constraints.get((entity_type, attribute))

    def eval_boundary(self, constraint: AttributeConstraint, q: BoundaryQuery) -> bool:
        """applicant_value가 가입 가능 범위인지. max 경계 inclusive 반영."""
        # constraint.max는 subgraph/tbox에서 실제 값 주입 (여기선 q에 동봉된 limit 사용 가정)
        limit = constraint.max
        if limit is None:
            return True
        return q.applicant_value <= limit if constraint.inclusive else q.applicant_value < limit

    def decide(self, intent_type: str, subgraph: dict, evidence: AbsenceEvidence,
               boundary_q: BoundaryQuery | None = None,
               constraint: AttributeConstraint | None = None) -> ResponseStance:
        contract = TARGET_INTENTS.get(intent_type)
        if contract is None:
            return ResponseStance(Stance.PRESENT, rationale="non-target intent (no-op)")

        # (0) boundary 우선
        if contract.boundary and boundary_q is not None:
            # constraint(또는 그 상한값)가 없으면 판정 불가 → UNCERTAIN (수치 추측/환각 금지).
            if constraint is None or constraint.max is None:
                return ResponseStance(Stance.UNCERTAIN,
                                      deterministic_text=self._uncertain_text(intent_type),
                                      rationale="boundary query but no constraint limit")
            ok = self.eval_boundary(constraint, boundary_q)
            # 판정 근거 수치(신청값/약관상한)를 메시지에 명시 — 확정성+근거 제공.
            _unit = boundary_q.unit or ""
            _av = boundary_q.applicant_value
            _av = int(_av) if float(_av).is_integer() else _av
            _lim = constraint.max
            _lim = int(_lim) if (_lim is not None and float(_lim).is_integer()) else _lim
            _bound = "이하" if constraint.inclusive else "미만"
            if ok:
                txt = (f"문의하신 값 {_av}{_unit}은(는) 약관 기준({_lim}{_unit} {_bound})에 해당하여 "
                       f"가입 가능 범위입니다.")
            else:
                txt = (f"문의하신 값 {_av}{_unit}은(는) 약관 기준({_lim}{_unit} {_bound})을 벗어나 "
                       f"가입이 어렵습니다.")
            return ResponseStance(Stance.CONFIRMED_ABSENT if not ok else Stance.PRESENT,
                                  boundary_eval=ok,
                                  deterministic_text=_esc(txt),
                                  rationale="boundary deterministic")

        # (1) edge 존재 → PRESENT
        edges = subgraph.get("edges", []) if subgraph else []
        if any(e.get("type") == contract.target_edge or e.get("label") == contract.target_edge for e in edges):
            return ResponseStance(Stance.PRESENT, rationale="target edge present")

        # (2) P0-A RC1: edge는 없지만 검색이 target 타입 노드를 찾음(topic_hits>0) → "데이터는
        #     있는데 라우팅이 edge를 못 탐". closed-world보다 우선 — topic 존재가 부재 주장보다
        #     강한 증거. UNCERTAIN/CONFIRMED_ABSENT 단락 대신 LLM 위임(deterministic_text=None).
        if evidence.entry_node_topic_hits > 0:
            return ResponseStance(Stance.PRESENT, deterministic_text=None,
                                  rationale="topic node present, routing incomplete → LLM 위임")

        # (3) 부재 + closed-world 전부(topic도 0) → CONFIRMED_ABSENT (진짜 부재)
        if evidence.closed_world_ok():
            lbl = _ABSENT_LABEL.get(intent_type, "해당 정보")
            return ResponseStance(Stance.CONFIRMED_ABSENT,
                                  deterministic_text=_esc(f"해당 상품에는 {lbl}가 없습니다."),
                                  rationale="closed-world absent")

        # (4) 그 외(불완전 증거) → UNCERTAIN
        return ResponseStance(Stance.UNCERTAIN,
                              deterministic_text=self._uncertain_text(intent_type),
                              rationale="incomplete evidence → uncertain")

    @staticmethod
    def _uncertain_text(intent_type: str) -> str:
        lbl = _ABSENT_LABEL.get(intent_type, "해당 정보")
        return _esc(f"현재 구조화된 약관 정보만으로는 {lbl}를 확인하기 어렵습니다.")


def _esc(text: str, max_len: int = 500) -> str:
    """deterministic_text 안전화: 길이 제한 + 제어문자 제거 (#Security Minimal)."""
    t = re.sub(r"[\x00-\x1f]", " ", text).strip()
    return t[:max_len]
