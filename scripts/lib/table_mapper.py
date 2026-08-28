"""U4 — TableMapper: U1 ParsedDoc 표 cells → typed GraphReadyData.

rule 중심(deterministic). LLM은 분류 라우팅만(gate numeric은 rule path).
- classify_table: summary/header 키워드 specificity → DomainCategory(들) (multi-label)
- _extract_numeric: 정규식 → ParsedNumericFact (range/operator/inclusive)
- map: 도메인별 row→entity (data cell + header_path + row context 단위)
- reconcile_table_and_llm: source priority(표 override) + evidence 합집합
- to_graph_ready: EntityCandidate → GraphReadyData (properties["_evidence"])

WAIVES_PREMIUM: 면제조건을 Coverage(coverage_kind=premium_waiver)로 생성 + Policy 연결
CALCULATED_BY: formula_type → parent 탐색→생성→gap
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any


def normalize_label(s: str) -> str:
    """라벨 정규화 (id 안정키용): 공백 축약 + 소문자. entity_resolver와 동일 철학,
    의존 회피 위해 로컬 정의(콘텐츠 해시 입력 일관성만 보장하면 됨)."""
    return re.sub(r"\s+", " ", (s or "").strip()).lower()

# ── 도메인 분류 (specificity 높을수록 우선) ──
_DOMAIN_KEYWORDS = [
    ("eligibility_criteria", ["가입나이", "가입연령", "가입자격"], 3),
    ("discount_rate", ["단체취급", "고액계약", "온라인할인", "할인율", "할인"], 3),
    ("waiver_condition", ["납입면제", "면제사유", "면제조건"], 3),
    ("calculation_formula", ["해약환급금", "환급률", "계산식", "산출", "공식"], 2),
]


@dataclass
class ParsedNumericFact:
    field: str
    value: Any
    unit: str = ""
    operator: str = ""        # LT/LTE/GT/GTE/EQ/RANGE
    inclusive: bool | None = None
    raw_text: str = ""


@dataclass
class EntityCandidate:
    type: str
    label: str
    properties: dict
    evidence: list[dict] = field(default_factory=list)
    category: str = ""
    source: str = "table"     # table | llm


@dataclass
class RelationCandidate:
    source_ref: str
    type: str
    target_ref: str
    evidence: list[dict] = field(default_factory=list)
    category: str = ""


# ── 수치 파싱 (deterministic) ──
_AGE_RANGE = re.compile(r"만\s*(\d+)\s*세\s*~\s*(\d+)\s*세")
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_THRESH = re.compile(r"(\d+(?:\.\d+)?)\s*%?\s*이상")
_BMI = re.compile(r"(\d+(?:\.\d+)?)\s*(이상|이하|미만|초과)")
_YEARS = re.compile(r"(\d+)\s*년납")

# RC3: 수식 신호 — 연산자 또는 계산 어휘가 있어야 Calculation 후보.
_FORMULA_OPS = re.compile(r"[×÷*/=]|[+]\s*\d|\d\s*[-]\s*\d")
_FORMULA_WORDS = ("합계", "차감", "공제", "× ", "곱", "나누", "환급률", "적립", "산출", "계산식", "공식")


def _has_formula_signal(text: str) -> bool:
    """셀 텍스트에 실제 수식/계산 신호가 있는지. 단순 라벨·단위·숫자만인 셀 배제."""
    t = (text or "").strip()
    if len(t) < 3:
        return False
    if _FORMULA_OPS.search(t):
        return True
    return any(w in t for w in _FORMULA_WORDS)


def _extract_numeric(text: str) -> list[ParsedNumericFact]:
    out: list[ParsedNumericFact] = []
    t = text.strip()
    m = _AGE_RANGE.search(t)
    if m:
        out.append(ParsedNumericFact("min_age", int(m.group(1)), "세", "GTE", True, t))
        out.append(ParsedNumericFact("max_age", int(m.group(2)), "세", "LTE", True, t))
    if "종신" in t and not m:
        out.append(ParsedNumericFact("max_age", 999, "세", "LTE", True, t))
    # 0세: 단독 "0세" 가입(태아 등). age range가 이미 잡혔으면 제외(80의 "0 세" 오매칭 방지)
    if not m and re.search(r"(?<!\d)0\s*세", t):
        out.append(ParsedNumericFact("min_age", 0, "세", "GTE", True, t))
    my = _YEARS.search(t)
    if my:
        out.append(ParsedNumericFact("payment_period_years", int(my.group(1)), "년", "EQ", None, t))
    mth = _THRESH.search(t)
    if mth:
        out.append(ParsedNumericFact("disability_threshold", int(float(mth.group(1))), "%", "GTE", True, t))
    elif (mp := _PCT.search(t)):
        out.append(ParsedNumericFact("rate", float(mp.group(1)) / 100, "ratio", "EQ", None, t))
    mb = _BMI.search(t)
    if mb and "%" not in t and "세" not in t:
        op = {"이상": ("GTE", True), "이하": ("LTE", True), "미만": ("LT", False), "초과": ("GT", False)}[mb.group(2)]
        out.append(ParsedNumericFact("bmi", float(mb.group(1)), "kg/m2", op[0], op[1], t))
    return out


def classify_table(table) -> list[str]:
    """summary/header/cells 키워드 → DomainCategory(들), multi-label + specificity."""
    text = (table.summary or "") + " " + " ".join(
        c.text for c in table.cells if getattr(c, "is_header", False))
    text += " " + " ".join(c.text for c in table.cells[:6])
    scored = []
    for domain, kws, spec in _DOMAIN_KEYWORDS:
        if any(k in text for k in kws):
            scored.append((spec, domain))
    scored.sort(reverse=True)
    return [d for _, d in scored] or ["generic"]


# 도메인 → (entity type, category, relation type)
_DOMAIN_MAP = {
    "eligibility_criteria": ("Eligibility", "P", "REQUIRES_ELIGIBILITY"),
    "discount_rate": ("Premium_Discount", "E", "HAS_DISCOUNT"),
    "waiver_condition": ("Coverage", "J", "WAIVES_PREMIUM"),
    "calculation_formula": ("Calculation", "G", "CALCULATED_BY"),
}


class TableMapper:
    def __init__(self, policy_id: str):
        self.policy_id = policy_id

    def map(self, parsed_doc) -> tuple[list[EntityCandidate], list[RelationCandidate]]:
        ents: list[EntityCandidate] = []
        rels: list[RelationCandidate] = []
        for table in parsed_doc.tables:
            for domain in classify_table(table):
                if domain not in _DOMAIN_MAP:
                    continue
                e, r = self._map_table(table, domain, parsed_doc)
                ents.extend(e); rels.extend(r)
        return ents, rels

    def _map_table(self, table, domain, pdoc):
        etype, cat, rtype = _DOMAIN_MAP[domain]
        ents: list[EntityCandidate] = []
        rels: list[RelationCandidate] = []
        # data cell 단위로 fact 생성
        rows: dict[int, list] = {}
        for c in table.cells:
            if not c.is_header:
                rows.setdefault(c.row, []).append(c)
        for row_idx, cells in rows.items():
            # row context: 같은 행의 다른 셀 텍스트
            row_ctx = {c.col: c.text for c in cells}
            for c in cells:
                facts = _extract_numeric(c.text)
                if not facts and domain != "calculation_formula":
                    continue
                props: dict = {}
                for f in facts:
                    if f.field == "min_age": props["min_age"] = f.value
                    elif f.field == "max_age":
                        props["max_age"] = f.value; props["max_age_inclusive"] = f.inclusive
                    elif f.field == "rate": props["discount_rate"] = f.value
                    elif f.field == "disability_threshold": props["disability_threshold"] = f.value
                    elif f.field == "payment_period_years": props["payment_period_years"] = f.value
                    elif f.field == "bmi":
                        props["bmi_max" if f.operator in ("LT", "LTE") else "bmi_min"] = f.value
                        props["bmi_max_inclusive"] = f.inclusive
                # 도메인 핵심 속성 없는 셀은 엔티티화 안 함 (예: 가입나이 표의 '5년납'만 든 셀)
                if domain == "eligibility_criteria" and "min_age" not in props and "bmi_max" not in props and "bmi_min" not in props:
                    continue
                if domain == "discount_rate" and "discount_rate" not in props:
                    continue
                if domain == "waiver_condition" and "disability_threshold" not in props:
                    continue
                # RC3 Calculation 과추출 방지: 실제 수식 신호(연산자/계산어휘)가 있는 셀만 Calculation화.
                # 단순 라벨/숫자 셀(예: 표 머리글, 단위) 제외.
                if domain == "calculation_formula" and not _has_formula_signal(c.text):
                    continue
                ev = self._evidence(table, c)
                lbl, props = self._finalize(domain, c, props, row_ctx, table)
                if not props and domain != "calculation_formula":
                    continue
                ent = EntityCandidate(type=etype, label=lbl, properties=props,
                                      evidence=[ev], category=cat, source="table")
                ents.append(ent)
                rels.append(self._make_relation(domain, rtype, lbl, ent, ev, cat, ents))
        return ents, rels

    def _finalize(self, domain, cell, props, row_ctx, table):
        if domain == "eligibility_criteria":
            mat = cell.header_path[0] if cell.header_path else ""
            pay = next((v for v in row_ctx.values() if "년납" in v), "")
            for f in _extract_numeric(pay):
                if f.field == "payment_period_years":
                    props["payment_period_years"] = f.value
            return f"가입나이({mat}/{pay})".strip("/"), props
        if domain == "discount_rate":
            dtype = next((v for v in row_ctx.values() if "%" not in v and v), "")
            props["discount_type"] = dtype
            return f"할인({dtype})", props
        if domain == "waiver_condition":
            props["coverage_kind"] = "premium_waiver"
            props["waiver_condition"] = cell.text
            return "보험료 납입면제", props
        if domain == "calculation_formula":
            props["formula_text"] = cell.text
            props["formula_type"] = "surrender_value" if "환급" in (table.summary or "") else "benefit"
            return f"계산식({cell.text[:10]})", props
        return cell.text[:20], props

    def _make_relation(self, domain, rtype, lbl, ent, ev, cat, ents):
        if domain == "calculation_formula":
            # CALCULATED_BY: parent 탐색→생성→gap
            ptype = {"surrender_value": "Surrender_Value", "discount": "Premium_Discount",
                     "benefit": "Coverage", "premium": "Coverage"}.get(ent.properties.get("formula_type"), "Coverage")
            parent = next((e for e in ents if e.type == ptype), None)
            if parent is None:
                parent = EntityCandidate(type=ptype, label=f"{ptype}(auto)", properties={},
                                         evidence=[ev], category=cat, source="table")
                ents.append(parent)
            return RelationCandidate(parent.label, rtype, lbl, [ev], cat)
        return RelationCandidate(self.policy_id, rtype, lbl, [ev], cat)

    @staticmethod
    def _evidence(table, cell) -> dict:
        return {"table_id": table.table_id, "row_idx": cell.row, "col_idx": cell.col,
                "page_no": table.page_no, "cell_bbox": cell.bbox,
                "source_pdf": getattr(cell.provenance, "source_pdf", "") if cell.provenance else "",
                "parser_version": getattr(cell.provenance, "parser_version", "") if cell.provenance else "",
                "run_id": getattr(cell.provenance, "run_id", "") if cell.provenance else ""}


def _type_str(t) -> str:
    """EntityType enum/문자열 모두 정규화 → "Calculation" (RC1: id 네임스페이스 단일화).
    Enum이면 .value. 'EntityType.X' repr 문자열이 들어와도 enum 이름으로 value 회복."""
    s = getattr(t, "value", None)
    if s is not None:
        return str(s)
    s = str(t)
    if s.startswith("EntityType.") or s.startswith("RelationType."):
        # repr 누수 방어: 'EntityType.CALCULATION' → enum 이름(CALCULATION)으로 .value 회복
        from lib.schemas import EntityType, RelationType
        name = s.split(".", 1)[1]
        enum_cls = EntityType if s.startswith("EntityType.") else RelationType
        member = enum_cls.__members__.get(name)
        return member.value if member is not None else name
    return s


def to_graph_ready(document_id: str, product_name: str,
                   ents: list[EntityCandidate], rels: list[RelationCandidate],
                   policy_id: str | None = None) -> dict:
    """EntityCandidate → GraphReadyData dict (properties._evidence 포함).

    id 계약(U10):
    - C1: id = "{type}#{document_id}_{stable}" — stable은 (type,normalize_label) 콘텐츠 해시.
      enumerate 인덱스 비종속 → 추출 순서/재빌드에 불변(결정론). 동일 (type,label) 충돌 시 -1,-2 suffix.
    - C3: product 문서당 Policy 정확히 1개 — 여러 Policy 엔티티는 첫 1개로 수렴, 나머지는 그 id로 remap.
    - 관계 endpoint는 (type,label)→id remap → dangling 0 (보존 불변식).
    - policy_id(C2): 호출부가 법령이면 None 전달 → 합성 Policy 생략. product면 표 관계 literal 참조 해소.
    """
    # ── C1: 콘텐츠 기반 안정 id ──
    def _stable_id(etype: str, label: str, used: set) -> str:
        key = f"{etype}|{normalize_label(label)}"
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
        eid = f"{etype}#{document_id}_{h}"
        n = 1
        while eid in used:  # 동일 (type,정규화label) 충돌 → 결정론적 suffix
            eid = f"{etype}#{document_id}_{h}-{n}"; n += 1
        used.add(eid)
        return eid

    # ── C3: Policy 1개 수렴 — 모든 Policy 엔티티를 첫 Policy의 label로 통합 ──
    policy_ents = [e for e in ents if _type_str(e.type) == "Policy"]
    canonical_policy_label = policy_ents[0].label if policy_ents else None
    extra_policy_labels = {e.label for e in policy_ents[1:]}  # 흡수 대상

    label_to_id: dict[str, str] = {}
    used_ids: set = set()
    out_entities = []
    seen_policy = False
    for e in ents:
        etype = _type_str(e.type)
        if etype == "Policy":
            if seen_policy:
                continue  # 추가 Policy 엔티티는 노드 생성 안 함(C3) — 아래서 canonical id로 remap
            seen_policy = True
            label_for_id = canonical_policy_label
        else:
            label_for_id = e.label
        eid = _stable_id(etype, label_for_id, used_ids)
        label_to_id[e.label] = eid
        props = dict(e.properties)
        props["_evidence"] = e.evidence
        rep = e.evidence[0] if e.evidence else {}
        out_entities.append({
            "id": eid, "type": etype, "label": e.label, "properties": props,
            "provenance": {"source_section_id": "", "source_text": "", "confidence": 0.9,
                           "table_id": rep.get("table_id"), "row_idx": rep.get("row_idx"),
                           "col_idx": rep.get("col_idx"), "page_no": rep.get("page_no"),
                           "source_pdf": rep.get("source_pdf"), "parser_version": rep.get("parser_version"),
                           "run_id": rep.get("run_id")},
        })

    # C3: 흡수된 추가 Policy label → canonical Policy id 로 remap (관계 endpoint 보존)
    canonical_policy_id = label_to_id.get(canonical_policy_label) if canonical_policy_label else None
    for lbl in extra_policy_labels:
        if canonical_policy_id:
            label_to_id[lbl] = canonical_policy_id

    # Policy 노드 보장 (표 관계 source가 literal policy_id를 참조하므로) — 법령은 policy_id=None
    if policy_id:
        policy_node_id = canonical_policy_id
        if policy_node_id is None:
            policy_node_id = _stable_id("Policy", product_name, used_ids)
            out_entities.append({
                "id": policy_node_id, "type": "Policy", "label": product_name,
                "properties": {"_evidence": [], "policy_id": policy_id, "scope_key": "product"},
                "provenance": {"source_section_id": "", "source_text": "", "confidence": 0.9},
            })
            label_to_id[product_name] = policy_node_id
        label_to_id[policy_id] = policy_node_id
        label_to_id.setdefault(product_name, policy_node_id)

    out_relations = []
    for r in rels:
        tgt = label_to_id.get(r.target_ref, r.target_ref)
        src = label_to_id.get(r.source_ref, r.source_ref)
        out_relations.append({"source_id": src, "type": _type_str(r.type), "target_id": tgt,
                              "properties": {"_evidence": r.evidence},
                              "provenance": {"source_section_id": "", "source_text": "", "confidence": 0.9}})
    return {"document_id": document_id, "product_name": product_name,
            "entities": out_entities, "relations": out_relations,
            # _label_to_id: 흡수된 Policy label 포함 권위 매핑(C3). LLM 관계 remap이 이걸 써야
            # 흡수 Policy를 참조하는 관계가 dangling 되지 않음.
            "_label_to_id": dict(label_to_id),
            "extraction_metadata": {"extracted_at": "", "model_id": "rule",
                                    "entity_count": len(out_entities), "relation_count": len(out_relations)}}


def reconcile_table_and_llm(table_ents: list[EntityCandidate],
                            llm_ents: list[EntityCandidate]) -> tuple[list[EntityCandidate], list[dict]]:
    """source priority: 표 override(같은 type+label), evidence 합집합. conflict_report 반환."""
    by_key: dict[tuple, EntityCandidate] = {}
    conflicts = []
    for e in table_ents + llm_ents:  # 표 먼저 → override 우선
        key = (e.type, e.label)
        if key not in by_key:
            by_key[key] = e
        else:
            exist = by_key[key]
            # 표 우선: table source가 llm 속성 override
            for k, v in e.properties.items():
                if k in exist.properties and exist.properties[k] != v:
                    conflicts.append({"key": key, "prop": k, "kept": exist.properties[k], "dropped": v})
                elif k not in exist.properties:
                    exist.properties[k] = v
            exist.evidence = exist.evidence + e.evidence  # 합집합
    return list(by_key.values()), conflicts
