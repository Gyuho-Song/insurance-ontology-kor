"""Tiny validator fixture set for U2 TBoxValidator (NFR-U2-1).

U3 Gold와 무관 — validator 로직 자체를 검증하기 위한 최소 샘플.
각 규칙(R1~R5)·known_exception·profile별 정상/위반 케이스.
"""

# ── 정상 (모든 규칙 통과) ────────────────────────────────────
VALID_ENTITIES = [
    {"id": "Policy#p1", "type": "Policy", "label": "테스트보험",
     "provenance": {"source_text": "약관 1조", "source_section_id": "s1", "confidence": 0.9},
     "properties": {}},
    {"id": "Product_Category#c1", "type": "Product_Category", "label": "건강보험",
     "provenance": {"source_text": "분류", "source_section_id": "s1", "confidence": 0.9},
     "properties": {}},
    {"id": "Premium_Discount#d1", "type": "Premium_Discount", "label": "고액계약할인",
     "provenance": {"source_text": "할인표 2행", "source_section_id": "s3", "confidence": 0.9},
     "properties": {"discount_rate": 0.02, "discount_type": "고액계약"}},
]
VALID_RELATIONS = [
    {"source_id": "Product_Category#c1", "type": "OWNS", "target_id": "Policy#p1",
     "provenance": {"source_text": "분류", "source_section_id": "s1", "confidence": 0.9}},
    {"source_id": "Policy#p1", "type": "HAS_DISCOUNT", "target_id": "Premium_Discount#d1",
     "provenance": {"source_text": "할인", "source_section_id": "s3", "confidence": 0.9}},
]

# ── R1 domain/range 위반: HAS_DISCOUNT의 target이 Coverage(should be Premium_Discount) ──
R1_BAD_RELATIONS = [
    {"source_id": "Policy#p1", "type": "HAS_DISCOUNT", "target_id": "Coverage#x1",
     "provenance": {"source_text": "x", "source_section_id": "s1", "confidence": 0.5}},
]
R1_BAD_ENTITIES = VALID_ENTITIES + [
    {"id": "Coverage#x1", "type": "Coverage", "label": "보장", "provenance":
     {"source_text": "x", "source_section_id": "s1", "confidence": 0.5}, "properties": {}},
]

# ── R2 required 누락: Premium_Discount에 discount_rate 없음 ──
R2_BAD_ENTITIES = [
    {"id": "Premium_Discount#d2", "type": "Premium_Discount", "label": "할인",
     "provenance": {"source_text": "x", "source_section_id": "s1", "confidence": 0.5},
     "properties": {"discount_type": "온라인"}},  # discount_rate 누락
]

# ── R3 type mismatch: discount_rate가 문자열 ──
R3_BAD_ENTITIES = [
    {"id": "Premium_Discount#d3", "type": "Premium_Discount", "label": "할인",
     "provenance": {"source_text": "x", "source_section_id": "s1", "confidence": 0.5},
     "properties": {"discount_rate": "2퍼센트", "discount_type": "고액"}},  # str, should be float
]

# ── R5 provenance 누락 ──
R5_BAD_ENTITIES = [
    {"id": "Policy#p9", "type": "Policy", "label": "무근거",
     "provenance": {"source_text": "", "source_section_id": "", "confidence": 0.5},
     "properties": {}},
]

# ── known_exception: GOVERNED_BY 없는 Policy (cardinality 위반이나 화이트리스트) ──
KNOWN_EXC_ENTITIES = VALID_ENTITIES  # Policy#p1엔 GOVERNED_BY 없음 → known_exception으로 강등돼야

# ── HAS_LOAN: 전역 데이터 부재 (known_exception 아님 → gap에만) ──
# (HAS_LOAN edge가 아예 없는 상태 = VALID_RELATIONS가 그 예)
