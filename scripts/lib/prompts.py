"""Extraction prompts and tool definitions for Bedrock tool_use.

Two-pass approach following cdk-app/lambda/ner-extractor/extraction.ts.
Pass 1: Entity extraction (per section)
Pass 2: Relation extraction (per document, with entity list)
"""

# ── Entity Types ─────────────────────────────────────────────────

ENTITY_TYPES_DESC = """
1. **Policy**: 보험 상품 자체. 문서 당 1개만 추출.
   - properties: provider, product_type, contract_types
   - ID: "Policy#hwl_{short_name}"

2. **Coverage**: 각 보장 항목/급부. 지급사유 테이블의 각 행 = 1개 Coverage.
   - properties: benefit_name(급부명칭), trigger_condition(지급사유), payment_amount(지급금액), rider_code(특약코드)
   - ID: "Coverage#hwl_{product}_{benefit}"

3. **Exclusion**: 면책/지급제한 사유.
   - properties: exclusion_type(고의/사기/전쟁 등), condition_text
   - ID: "Exclusion#hwl_{product}_{exclusion}"

4. **Exception**: 면책 예외 (다만, 단서 조항).
   - properties: exception_condition, referenced_exclusion
   - ID: "Exception#hwl_{product}_{exception}"

5. **Eligibility**: 가입 자격 요건.
   - properties: age_range, health_requirements, contract_types
   - ID: "Eligibility#hwl_{product}_{requirement}"

6. **Dividend_Method**: 배당 구조.
   - properties: dividend_type (무배당/유배당)
   - ID: "Dividend_Method#hwl_{product}_nodividend"

7. **Surrender_Value**: 해약환급금 요약 (테이블 전체가 아닌 핵심 정보).
   - properties: calculation_basis, key_milestones
   - ID: "Surrender_Value#hwl_{product}_{period}"

8. **Rider**: 특약 (상품구성 테이블에서 추출).
   - properties: rider_code, rider_name, rider_type(선택/제도성/의무부가)
   - ID: "Rider#hwl_{product}_{rider_code}"

9. **Premium_Discount**: 보험료 할인.
   - properties: discount_type, discount_rate_text
   - ID: "Premium_Discount#hwl_{product}_{type}"

10. **Product_Category**: 상품 분류.
    - properties: category (종신/건강/암/상해/정기/간병/골절/보장/연금)
    - ID: "Product_Category#{category}"

11. **Regulation**: 규제 조항 (법률 문서에서 주로 추출).
    - properties: article_number, regulation_type(의무/금지/허가/정의/벌칙)
    - ID: "Regulation#{law}_{article}"

12. **Calculation**: 보험금/환급금/보험료 계산 수식. 수학적 공식이 포함된 모든 계산식을 독립 엔티티로 추출.
    - properties: formula_text(전체 수식 원문), formula_type(surrender_value/benefit/premium/discount/loan), applies_to(적용 조건/시점), variables(수식에 사용된 변수 목록)
    - 예: "표준형 기본해약환급금 × 50% + 추가계약자적립액", "기본보험료 × 12 × 납입기간 × 보너스지급률"
    - 수식뿐 아니라 조건부 계산 로직도 포함 (예: "1년 미만: 없음, 1년 이상~2년 미만: 납입보험료 × 50%")
    - ID: "Calculation#hwl_{product}_{formula_short}"
"""

# ── Pass 1: Product Entity Extraction ────────────────────────────

PRODUCT_ENTITY_PROMPT = f"""You are an expert Korean insurance document entity extractor.

Extract structured entities from this section of a Korean insurance product summary (상품요약서).

## Entity Types
{ENTITY_TYPES_DESC}

## Rules
- source_text: 원문에서 해당 엔티티를 도출한 텍스트를 그대로 복사 (최대 300자). 추적 가능성(traceability)을 위해 반드시 포함.
- source_section_id: 마크다운 헤딩 구조 사용 (예: "sec3.나.주계약", "sec2.라")
- confidence: 0.0-1.0 (명시적으로 기술된 경우 0.9 이상)
- 원문에 없는 엔티티를 추측하지 마세요.
- 테이블의 각 행을 별도 Coverage 엔티티로 추출하되, 동일 급부가 여러 특약에서 반복되면 가장 상세한 것 하나만 추출.
- 특약코드가 있으면 (예: KA1.1, TA2.1) rider_code property에 포함.
- ## ■ 헤더로 시작하는 특약 상세 섹션에서 Coverage를 추출할 때, 특약명과 코드를 반드시 포함.
- **계산 수식(Calculation) 추출 중요**: "×", "÷", "%", "=", "합계", "차감" 등이 포함된 수학적 공식은 반드시 Calculation 엔티티로 추출. 해약환급금 계산식, 보험금 산출 공식, 보험료 할인 계산식, 대출이율 계산식 등을 모두 포함. 조건부 계산(예: "1년 미만: A, 1년 이상: B")도 하나의 Calculation으로 추출.

Use the extract_entities tool to return structured JSON."""

# ── Pass 1: Law Entity Extraction ────────────────────────────────

LAW_ENTITY_PROMPT = """You are an expert Korean legal/regulatory entity extractor.

Extract entities from this chapter of a Korean law/regulation document.

## Entity Types
1. **Regulation**: 주요 조항 (의무/금지/허가/정의/벌칙/경과규정)
   - properties: article_number(조문번호), article_title, regulation_type
   - 보험업에 영향을 미치는 조항에 집중
   - ID: "Regulation#{law_short}_art{N}"

2. **Exclusion**: 금지/제한 사항
   - ID: "Exclusion#{law_short}_art{N}_prohibition"

3. **Exception**: 예외/단서 (다만, 단 등)
   - ID: "Exception#{law_short}_art{N}_exception"

4. **Eligibility**: 자격/등록/인가 요건
   - ID: "Eligibility#{law_short}_art{N}_requirement"

5. **Coverage**: 법적 보호/보장 범위 규정
   - ID: "Coverage#{law_short}_art{N}_protection"

6. **Product_Category**: 규제 대상 보험 상품 분류
   - ID: "Product_Category#{category}"

## Rules
- source_text: 조문 원문 그대로 복사 (최대 300자)
- source_section_id: "artN" 또는 "artN.parM" 형식
- 보험업과 무관한 일반 행정 조항은 제외
- 정의 규정(제N조)에서 핵심 용어 정의를 Regulation으로 추출

Use the extract_entities tool to return structured JSON."""

# ── Pass 2: Product Relation Extraction ──────────────────────────

PRODUCT_RELATION_PROMPT = """You are an expert insurance ontology relation extractor.

Given a list of entities and the document sections, extract relations between entities.

## Relation Types
1. **HAS_COVERAGE**: Policy → Coverage (상품이 보유한 보장항목)
2. **EXCLUDED_IF**: Coverage → Exclusion (보장의 면책 조건)
3. **EXCEPTION_ALLOWED**: Exclusion → Exception (면책의 단서 예외)
4. **GOVERNED_BY**: Policy → Regulation (적용 법규)
5. **STRICTLY_PROHIBITED**: Regulation → Exclusion (법적 금지)
6. **EXCEPTIONALLY_ALLOWED**: Regulation → Exception (법적 예외 허용)
7. **NO_DIVIDEND_STRUCTURE**: Policy → Dividend_Method (배당 구조)
8. **HAS_DISCOUNT**: Policy → Premium_Discount (할인)
9. **SURRENDER_PAYS**: Policy → Surrender_Value (해약환급금)
10. **REQUIRES_ELIGIBILITY**: Policy → Eligibility (가입 자격 요구)
11. **HAS_RIDER**: Policy → Rider (특약 부가)
12. **HAS_LOAN**: Policy → Coverage (대출 관련 보장)
13. **WAIVES_PREMIUM**: Policy → Coverage (보험료 납입면제 보장)
14. **OWNS**: Policy → Product_Category (상품 분류 소속)
15. **CALCULATED_BY**: Coverage/Surrender_Value/Premium_Discount → Calculation (계산 수식 연결)

## Rules
- 모든 Coverage는 Policy로부터 HAS_COVERAGE 관계가 있어야 합니다.
- 면책 사유(Exclusion)는 관련 Coverage에 EXCLUDED_IF로 연결.
- "다만," 예외(Exception)는 해당 Exclusion에 EXCEPTION_ALLOWED로 연결.
- Calculation 엔티티는 해당 Coverage, Surrender_Value, 또는 Premium_Discount에 CALCULATED_BY로 연결.
- source_text: 관계를 증거하는 원문 (최대 200자)
- source/target ID는 제공된 엔티티 목록의 ID를 정확히 사용.
- 존재하지 않는 엔티티 ID를 참조하지 마세요.

Use the extract_relations tool to return structured JSON."""

# ── Pass 2: Law Relation Extraction ──────────────────────────────

LAW_RELATION_PROMPT = """You are an expert Korean legal/regulatory relation extractor.

Given entities from a law document, extract relations between them.
**목표: 모든 엔티티가 최소 1개의 관계에 연결되도록 최대한 추출하라.**

## Relation Types
- GOVERNED_BY: Regulation → Regulation. 다음 모든 경우에 사용:
  (1) 상위법 → 하위법 위임 ("…대통령령으로 정한다", "…총리령으로 정하는 바에 따라")
  (2) 같은 법률 내 조항 간 상호참조 ("제X조에 따른", "제X조의 규정에 의한")
  (3) 총칙/정의 조항 → 이를 인용하는 개별 조항
  (4) 벌칙/과태료 조항 → 해당 위반 조항
- STRICTLY_PROHIBITED: Regulation → Exclusion (법적 금지행위)
- EXCEPTIONALLY_ALLOWED: Regulation → Exception (예외 허용, 단서 조항)
- EXCLUDED_IF: Regulation/Coverage → Exclusion (적용 제외 조건)
- EXCEPTION_ALLOWED: Regulation → Exception (단서 조건부 예외, "다만,..." 조항)
- REQUIRES_ELIGIBILITY: Regulation/Coverage → Eligibility (자격 요건 충족 요구)
- HAS_COVERAGE: Regulation → Coverage (법적 보호 범위 규정)

## Rules
- 금지-예외 쌍: STRICTLY_PROHIBITED + EXCEPTIONALLY_ALLOWED를 함께 추출
- 위임 관계: "…에 따른", "…에 의한", "…으로 정한다" 등의 표현이 있으면 GOVERNED_BY
- 같은 장(章) 내 총칙이나 정의 조항은 해당 장의 다른 조항과 GOVERNED_BY로 연결
- Regulation 엔티티끼리도 적극적으로 GOVERNED_BY를 사용하여 연결
- Orphan(연결 없는) 엔티티가 최소화되도록 관계를 빠짐없이 추출
- source/target ID는 엔티티 목록의 ID를 정확히 사용

Use the extract_relations tool to return structured JSON."""

# ── User Prompt Templates ────────────────────────────────────────

ENTITY_USER_PROMPT = """Document: {product_name} (document_id: {document_id})
Section: [{section_id}] {section_title}

---

{section_content}

---

Extract all entities from the above section. For benefit tables, extract each distinct
benefit (급부명칭) as a separate Coverage entity with trigger_condition and payment_amount."""

RELATION_USER_PROMPT = """Document: {product_name} (document_id: {document_id})

## Entities (extracted in previous pass)
{entity_list}

## Document Sections
{section_summaries}

---

Extract relations between the entities listed above. Every Coverage should have
HAS_COVERAGE from the Policy. Every Exclusion should link to relevant Coverages
via EXCLUDED_IF. Every Exception should link via EXCEPTION_ALLOWED.
Every Calculation should link to its parent entity (Coverage/Surrender_Value/Premium_Discount) via CALCULATED_BY."""

# ── Tool Definitions ─────────────────────────────────────────────

ENTITY_EXTRACTION_TOOL = {
    "name": "extract_entities",
    "description": "Extract structured entities from insurance/legal document section",
    "input_schema": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "description": "Array of extracted entities",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Unique entity ID: {Type}#short_identifier"},
                        "type": {
                            "type": "string",
                            "enum": [
                                "Policy", "Coverage", "Exclusion", "Exception",
                                "Dividend_Method", "Regulation", "Premium_Discount",
                                "Surrender_Value", "Eligibility", "Rider", "Product_Category",
                                "Calculation",
                            ],
                        },
                        "label": {"type": "string", "description": "Short Korean label"},
                        "properties": {"type": "object", "description": "Type-specific properties"},
                        "provenance": {
                            "type": "object",
                            "properties": {
                                "source_section_id": {"type": "string"},
                                "source_text": {"type": "string", "description": "Verbatim Korean text (max 300 chars)"},
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            },
                            "required": ["source_section_id", "source_text", "confidence"],
                        },
                    },
                    "required": ["id", "type", "label", "provenance"],
                },
            },
        },
        "required": ["entities"],
    },
}

RELATION_EXTRACTION_TOOL = {
    "name": "extract_relations",
    "description": "Extract relations between entities",
    "input_schema": {
        "type": "object",
        "properties": {
            "relations": {
                "type": "array",
                "description": "Array of extracted relations",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "target_id": {"type": "string"},
                        "type": {
                            "type": "string",
                            "enum": [
                                "HAS_COVERAGE", "EXCLUDED_IF", "EXCEPTION_ALLOWED",
                                "GOVERNED_BY", "STRICTLY_PROHIBITED", "EXCEPTIONALLY_ALLOWED",
                                "NO_DIVIDEND_STRUCTURE", "HAS_DISCOUNT", "SURRENDER_PAYS",
                                "REQUIRES_ELIGIBILITY", "HAS_RIDER", "HAS_LOAN",
                                "WAIVES_PREMIUM", "OWNS", "CALCULATED_BY",
                            ],
                        },
                        "properties": {"type": "object"},
                        "provenance": {
                            "type": "object",
                            "properties": {
                                "source_section_id": {"type": "string"},
                                "source_text": {"type": "string"},
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            },
                            "required": ["source_section_id", "source_text", "confidence"],
                        },
                    },
                    "required": ["source_id", "target_id", "type", "provenance"],
                },
            },
        },
        "required": ["relations"],
    },
}
