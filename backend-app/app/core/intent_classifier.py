import asyncio
import json
import logging
import math
import re

from app.models.intent import Entity, Intent, IntentType

logger = logging.getLogger("graphrag.intent")

KEYWORD_MAP: dict[IntentType, list[str]] = {
    IntentType.DIVIDEND_CHECK: [
        "배당", "배당금", "유배당", "무배당", "상계", "배당 구조",
    ],
    IntentType.COVERAGE_INQUIRY: [
        "보장", "보험금", "사망보험금", "지급", "보장항목",
        "보장내용", "보장범위", "보장 한도", "보장금액",
    ],
    IntentType.EXCLUSION_EXCEPTION: [
        "면책", "보험금 지급 제한", "제외", "예외", "면책사유",
        "면책기간", "부담보", "지급제한",
        "고지의무", "알릴 의무", "통지의무", "계약 전 알릴 의무",
        "고지의무 위반", "알릴 의무 위반",
        "고의", "자해", "심신상실", "자살", "계약 무효",
    ],
    IntentType.SURRENDER_VALUE: [
        "해약", "환급금", "해지", "해약환급금", "해지환급금",
        "중도해지", "환급률",
    ],
    IntentType.DISCOUNT_ELIGIBILITY: [
        "할인", "할인율", "보험료 할인", "할인 조건", "할인 대상", "할인 혜택",
    ],
    IntentType.REGULATION_INQUIRY: [
        "규제", "법률", "법령", "시행령", "시행규칙", "보험업법", "금소법",
        "금융소비자보호법", "암관리법", "감독규정", "적용되는 법", "적용되는 규제",
        "관련 법규", "준수", "위반", "제재", "처벌", "과태료",
        "인가", "허가", "등록 요건", "적합성", "설명의무", "청약철회",
        "보험가격지수", "산출이율", "비교공시", "금지행위",
    ],
    IntentType.LOAN_INQUIRY: [
        "대출", "보험계약대출", "약관대출", "대출금", "대출이자",
        "이자율", "상환", "대출한도", "대출 가능",
    ],
    IntentType.PREMIUM_WAIVER: [
        "납입면제", "보험료 납입 면제", "면제", "납입 면제",
        "보험료 면제", "납입의무 면제",
    ],
    IntentType.POLICY_COMPARISON: [
        "비교", "차이점", "차이", "다른 점", "비교해", "비교해주세요",
        "어떤게 더", "어떤 게 더", "뭐가 더", "둘 중", "두 보험",
        "대비", "versus", "vs", "뭐가 다른", "뭐가 다르",
        "골라야", "어떤 걸", "어떤걸",
        "1종과 2종", "일반형과", "일반형과 간편",
    ],
    IntentType.CALCULATION_INQUIRY: [
        "계산", "계산식", "산출", "공식", "산출방법", "계산방법",
        "산출식", "계산 공식", "어떻게 계산", "산정", "산정방법",
        "어떻게 정해", "계산하나", "산출 기준",
    ],
    IntentType.ELIGIBILITY_INQUIRY: [
        "가입 조건", "가입조건", "가입 자격", "가입자격", "가입 가능",
        "가입할 수", "누가 가입", "몇 살까지", "가입 연령", "가입연령",
        "심사", "심사기준", "건강진단", "간편가입", "가입 심사",
        "가입 제한", "가입 대상", "단체 보험", "단체보험",
    ],
    IntentType.RIDER_INQUIRY: [
        "특약들", "특약은", "특약 목록", "선택특약", "부가특약", "특별약관",
        "추가 특약", "특약 보장", "특약 내용", "특약 종류",
        "지정대리청구", "납입면제특약", "어떤 특약",
    ],
}

# Keywords that, when combined with ambiguous terms, disambiguate the intent
DISAMBIGUATION_RULES: list[tuple[list[str], list[str], IntentType]] = [
    # Product variant suffix "납입면제형" is not premium waiver intent (A10)
    (
        ["보장", "질병"],
        ["납입면제형"],
        IntentType.COVERAGE_INQUIRY,
    ),
    # Specific 특약 content question → rider, not whatever keyword is in the name (H03, H06)
    (
        ["특약"],
        ["내용은", "내용을", "어떤 보장", "보장을 하"],
        IntentType.RIDER_INQUIRY,
    ),
    # "어떻게 계산/정해" + domain terms → calculation, not coverage (G01, G05, G07)
    (
        ["어떻게 계산", "어떻게 정해", "계산은"],
        ["보험금", "사망보험금", "보장", "적용이율", "보장개시일", "보장부분"],
        IntentType.CALCULATION_INQUIRY,
    ),
    # 해약환급금 + type variants (1종/2종) → surrender, not comparison (C03)
    (
        ["해약환급금", "환급금"],
        ["1종", "2종"],
        IntentType.SURRENDER_VALUE,
    ),
    # 할인 + benefit context → discount, not coverage (E06)
    (
        ["할인"],
        ["혜택", "가족 할인"],
        IntentType.DISCOUNT_ELIGIBILITY,
    ),
    # Regulatory context: 보험업/금지행위 + 예외 → regulation, not exclusion (N03)
    (
        ["보험업", "금지행위"],
        ["예외"],
        IntentType.REGULATION_INQUIRY,
    ),
    # If query has both coverage and exclusion keywords, prefer exclusion
    # because it's a more specific (superset) traversal
    (
        ["보험금", "지급"],
        ["면책", "면책사유", "예외", "제외"],
        IntentType.EXCLUSION_EXCEPTION,
    ),
    # Negation patterns: "못 받는", "안 나오", "미지급" → exclusion
    (
        ["보험금", "보장"],
        ["못 받", "안 받", "못받", "안받", "안 나오", "미지급", "지급 제한", "보장 제외", "보장받지 못"],
        IntentType.EXCLUSION_EXCEPTION,
    ),
    # "면제" alone could be premium waiver, but with coverage context it's different
    (
        ["면제", "납입"],
        ["보험료"],
        IntentType.PREMIUM_WAIVER,
    ),
    # Comparison keywords alongside any domain keyword → comparison intent
    (
        ["비교", "차이점", "차이", "둘 중", "골라", "뭐가 더", "어떤 게 더", "어떤게 더"],
        ["보장", "보험금", "면책", "배당", "할인", "환급", "해약", "보험"],
        IntentType.POLICY_COMPARISON,
    ),
    # "위반" with disclosure-duty keywords → exclusion (not regulation)
    (
        ["고지의무", "알릴 의무", "통지의무"],
        ["위반", "해지", "해제", "거절"],
        IntentType.EXCLUSION_EXCEPTION,
    ),
    # "가입" + "특약" together → rider (not eligibility)
    (
        ["가입할 수", "가입 가능", "가입"],
        ["특약들", "특약은", "특약 목록", "특약 종류", "어떤 특약", "선택특약", "부가특약", "특별약관"],
        IntentType.RIDER_INQUIRY,
    ),
    # "계산식" / "산출 공식" with domain terms → calculation (not the domain intent)
    # Note: "어떻게 계산" alone is ambiguous, only strong formula terms trigger this
    (
        ["환급금", "해약환급금", "보험금", "보험료", "할인", "배당"],
        ["계산식", "산출 공식", "계산 공식", "산출방법", "계산방법", "산출식"],
        IntentType.CALCULATION_INQUIRY,
    ),
    # Exclusion context: intentional harm, suicide, self-harm + insurance payment
    (
        ["보험금", "보장", "지급"],
        ["고의", "자해", "심신상실", "자살", "사기", "범죄"],
        IntentType.EXCLUSION_EXCEPTION,
    ),
]

# Special disambiguation: regulatory terms that overlap with calculation.
# Only apply when no strong calculation keyword (계산식, 공식, etc.) is present.
_REGULATORY_TERMS = {"보험가격지수", "산출이율", "비교공시"}
_STRONG_CALC_TERMS = {"계산식", "산출 공식", "계산 공식", "산출방법", "계산방법", "산출식", "공식"}

# Regex-based negation detection: when negative phrasing + insurance keywords
# appear together, override to exclusion_exception before keyword matching
import re as _re
_NEGATION_PATTERNS = [
    _re.compile(r"보험금[을를]?\s*못\s*받"),
    _re.compile(r"보장[을를]?\s*못\s*받"),
    _re.compile(r"보장받지\s*못"),
    _re.compile(r"보험금[이가]?\s*(안|못)\s*(나오|지급)"),
    _re.compile(r"(지급|보장)[이가을를]?\s*(안|못)\s*(되|받|나)"),
]

PRODUCT_PATTERNS = [
    r"한화생명\s*\S+",
    r"\S+종신보험\S*",
    r"\S+정기보험\S*",
    r"\S+암보험\S*",
    r"\S+건강보험\S*",
    r"[eEHh]\S+보험\S*",
]

COMPLEX_KEYWORDS = ["규제", "상계", "법", "조항", "예외", "단서", "위반", "면책", "계산식", "산출", "가입 조건", "특약"]

# Korean grammatical particles to strip from extracted product names.
# Ordered longest-first so that e.g. "이랑" is tried before "이".
_KOREAN_PARTICLES = sorted(
    ["이랑", "과", "와", "의", "은", "는", "을", "를", "이", "가",
     "에서", "에", "도", "만", "부터", "까지", "에게", "으로", "로",
     "하고", "이나", "나", "보다"],
    key=len,
    reverse=True,
)


def _strip_particle(name: str) -> str:
    """Remove a trailing Korean particle from a product name."""
    for particle in _KOREAN_PARTICLES:
        if name.endswith(particle) and len(name) > len(particle):
            return name[: -len(particle)]
    return name

# Intents that naturally chain to additional templates for richer context
SECONDARY_INTENT_MAP: dict[IntentType, IntentType] = {
    IntentType.COVERAGE_INQUIRY: IntentType.EXCLUSION_EXCEPTION,
}

LLM_SYSTEM_PROMPT = (
    "당신은 보험 약관 질의 의도 분류 전문가입니다. "
    "사용자 질의의 의도를 정확히 분류하고, 핵심 개체를 추출하세요. "
    "반드시 유효한 JSON만 출력하세요. 다른 텍스트는 포함하지 마세요."
)

LLM_CLASSIFY_PROMPT = """사용자 질의를 분석하여 의도를 분류하고 핵심 개체를 추출하세요.

의도 유형 (intent_type):
- coverage_inquiry: 보장항목, 보험금 지급사유, 보험금액 관련 질문
- dividend_check: 배당금, 무배당/유배당 구조 관련 질문
- exclusion_exception: 면책사유, 보험금 지급 제한, 예외 조건, 고지의무 위반, 알릴 의무 위반 관련 질문
- surrender_value: 해약환급금, 해지 시 환급 관련 질문
- discount_eligibility: 보험료 할인 조건, 할인율 관련 질문
- regulation_inquiry: 보험 관련 법규, 규제, 감독규정, 보험업법 관련 질문
- loan_inquiry: 보험계약대출, 약관대출, 대출이자, 상환조건 관련 질문
- premium_waiver: 보험료 납입면제 조건 관련 질문
- policy_comparison: 두 개 이상의 보험상품을 비교하는 질문 (보장 비교, 차이점 등)
- calculation_inquiry: 보험료 계산식, 환급금 산출 공식, 보험금 산정 방법 관련 질문
- eligibility_inquiry: 보험 가입 조건, 가입 자격, 가입 연령, 건강진단, 심사 기준 관련 질문
- rider_inquiry: 보험 특약(선택특약, 부가특약) 종류, 내용, 보장 관련 질문
- general_inquiry: 위에 해당하지 않는 일반 질의

질의: {query}

JSON 형식으로만 출력하세요:
{{"intent_type": "...", "confidence": 0.0, "entities": [], "requires_regulation": false, "complexity": "simple"}}"""

INTENT_EXEMPLARS: dict[IntentType, list[str]] = {
    IntentType.COVERAGE_INQUIRY: [
        "이 보험의 보장항목은 무엇인가요?",
        "사망보험금은 얼마나 지급되나요?",
        "보장 범위와 보장 한도를 알려주세요",
        "어떤 경우에 보험금이 지급되나요?",
        "이 보험은 어떤 질병을 보장해주나요?",
        "진단금은 얼마나 받을 수 있어요?",
        "입원비 보장은 어떻게 되나요?",
        "수술비 보장 내용을 알려주세요",
    ],
    IntentType.DIVIDEND_CHECK: [
        "이 보험에 배당금이 있나요?",
        "무배당 보험과 유배당 보험의 차이점은?",
        "배당금 구조와 상계 처리는 어떻게 되나요?",
        "배당금은 어떻게 계산되나요?",
        "배당금을 받을 수 있는 조건은 무엇인가요?",
        "이 보험 배당이 나오는 건가요?",
        "배당금이 보험료에서 차감되나요?",
        "유배당 상품의 장점이 무엇인가요?",
    ],
    IntentType.EXCLUSION_EXCEPTION: [
        "면책 사유에는 어떤 것들이 있나요?",
        "보험금 지급이 제한되는 경우는 언제인가요?",
        "면책기간은 얼마나 되나요?",
        "부담보 조건과 예외 사항을 알려주세요",
        "계약 전 알릴 의무를 위반하면 어떻게 되나요?",
        "고지의무 위반 시 계약 해지가 가능한가요?",
        "보험금이 나오나요?",
        "보험금을 받을 수 있나요?",
        "이런 경우에도 보장이 되나요?",
        "보험금 청구가 거절될 수 있나요?",
        "보험금을 못 받는 경우가 있나요?",
        "보장받지 못하는 질병이 있나요?",
    ],
    IntentType.SURRENDER_VALUE: [
        "해약환급금은 얼마나 받을 수 있나요?",
        "중도해지 시 환급률은 어떻게 되나요?",
        "해지환급금 계산 방법을 알려주세요",
        "가입 후 3년차에 해약하면 얼마를 받나요?",
        "해지하면 돈을 얼마나 돌려받을 수 있어요?",
        "저해지환급금형이 뭔가요?",
        "해약환급금 지급 기준이 어떻게 되나요?",
        "납입기간 중 해지하면 손해가 큰가요?",
    ],
    IntentType.DISCOUNT_ELIGIBILITY: [
        "보험료 할인을 받을 수 있는 조건은 무엇인가요?",
        "할인율은 얼마나 되나요?",
        "단체 할인이나 우량체 할인이 가능한가요?",
        "할인 대상과 할인 조건을 알려주세요",
        "건강체 할인은 어떻게 받나요?",
        "온라인 가입하면 보험료가 싸지나요?",
        "고액 할인이 적용되나요?",
        "보험료를 줄일 수 있는 방법이 있나요?",
    ],
    IntentType.REGULATION_INQUIRY: [
        "이 보험에 적용되는 법률과 규제는 무엇인가요?",
        "보험업법에서 정한 의무사항은 무엇인가요?",
        "금융소비자보호법상 설명의무는 무엇인가요?",
        "이 보험에 적용되는 감독규정은 무엇인가요?",
        "보험가격지수란 무엇인가요?",
        "보험 산출이율의 기준은 무엇인가요?",
        "보험상품 비교공시 제도가 뭔가요?",
        "보험업 허가와 금지행위에 대해 알려주세요",
        "교차모집이란 무엇이며 관련 규제는 무엇인가요?",
        "청약철회 관련 규정을 알려주세요",
    ],
    IntentType.LOAN_INQUIRY: [
        "보험계약대출은 얼마까지 가능한가요?",
        "약관대출 이자율은 어떻게 되나요?",
        "대출금 상환 조건과 방법을 알려주세요",
        "보험대출 한도와 이자율을 알고 싶어요",
        "보험으로 대출을 받을 수 있나요?",
        "약관대출 신청은 어떻게 하나요?",
        "대출 이자는 어떻게 계산되나요?",
        "해약환급금 범위 내에서 대출이 가능한가요?",
    ],
    IntentType.PREMIUM_WAIVER: [
        "보험료 납입면제 조건은 무엇인가요?",
        "어떤 경우에 보험료 납입이 면제되나요?",
        "납입면제 사유와 절차를 알려주세요",
        "장해 발생 시 보험료 면제가 되나요?",
        "암 진단 받으면 보험료를 안 내도 되나요?",
        "납입면제 혜택이 있는 보험인가요?",
        "보험료 면제 받으려면 어떤 조건이 필요한가요?",
        "50% 장해 시 납입면제가 가능한가요?",
    ],
    IntentType.POLICY_COMPARISON: [
        "H보장보험이랑 H건강플러스보험의 보장항목을 비교해주세요",
        "두 보험의 차이점이 뭐야?",
        "e건강보험과 e암보험 중 어떤게 더 좋아?",
        "상속H종신보험과 e정기보험의 보장 범위를 비교해 주세요",
        "이 두 상품 중에서 뭐가 더 나은가요?",
        "종신보험이랑 정기보험 차이가 뭔가요?",
        "시그니처H암보험과 e암보험 비교해줘",
        "1종과 2종의 차이점을 알려주세요",
    ],
    IntentType.CALCULATION_INQUIRY: [
        "해약환급금은 어떻게 계산되나요?",
        "보험료 산출 공식을 알려주세요",
        "환급금 계산 방법이 궁금합니다",
        "보험금 산정 기준은 무엇인가요?",
        "사망보험금은 어떻게 계산되나요?",
        "보장개시일은 어떻게 정해지나요?",
        "갱신 시 보험료 재계산은 어떻게 하나요?",
        "보험료는 어떤 공식으로 산출되나요?",
        "적용이율은 어떻게 결정되나요?",
        "환급률은 어떤 기준으로 산정하나요?",
    ],
    IntentType.ELIGIBILITY_INQUIRY: [
        "이 보험은 누가 가입할 수 있나요?",
        "가입 연령 조건은 어떻게 되나요?",
        "건강진단 없이 가입할 수 있나요?",
        "간편가입 보험의 심사 기준은 무엇인가요?",
        "몇 살까지 가입이 가능한가요?",
        "단체보험 가입 조건이 어떻게 되나요?",
        "가입할 때 건강진단을 받아야 하나요?",
        "기존 질병이 있으면 가입이 안 되나요?",
    ],
    IntentType.RIDER_INQUIRY: [
        "이 보험에 가입할 수 있는 특약은 뭐가 있나요?",
        "지정대리청구서비스특약이 뭔가요?",
        "어떤 특약에 가입해야 치매 보장을 받을 수 있나요?",
        "납입면제특약의 내용은 무엇인가요?",
        "선택할 수 있는 특약 종류를 알려주세요",
        "부가특약으로 어떤 것들이 있나요?",
        "특약 보험료는 별도인가요?",
        "특약을 추가하면 어떤 혜택이 더 있나요?",
    ],
    IntentType.GENERAL_INQUIRY: [
        "이 보험 상품에 대해 전반적으로 알려주세요",
        "보험 가입 절차는 어떻게 되나요?",
        "이 보험의 특징은 무엇인가요?",
        "보험 계약 내용을 요약해주세요",
        "이 상품의 주요 장점이 뭔가요?",
        "보험 계약 시 주의사항을 알려주세요",
    ],
}

KEYWORD_HIGH_CONFIDENCE = 0.95
EMBEDDING_MATCH_THRESHOLD = 0.75


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class IntentClassifier:
    def __init__(self, bedrock=None, embedding_client=None):
        self._bedrock = bedrock
        self._embedding = embedding_client
        self._exemplar_vectors: dict[IntentType, list[list[float]]] | None = None
        self._centroid_vectors: dict[IntentType, list[float]] | None = None
        self._exemplar_init_lock = asyncio.Lock()

    async def _ensure_exemplars(self):
        if self._exemplar_vectors is not None:
            return
        if self._embedding is None:
            return
        async with self._exemplar_init_lock:
            if self._exemplar_vectors is not None:
                return
            vectors: dict[IntentType, list[list[float]]] = {}
            for intent_type, sentences in INTENT_EXEMPLARS.items():
                intent_vecs = []
                for sentence in sentences:
                    vec = await self._embedding.embed(sentence)
                    intent_vecs.append(vec)
                vectors[intent_type] = intent_vecs
            self._exemplar_vectors = vectors

            # Compute centroid (mean vector) per intent for Semantic Router
            centroids: dict[IntentType, list[float]] = {}
            for intent_type, vecs in vectors.items():
                dim = len(vecs[0])
                n = len(vecs)
                centroid = [sum(v[i] for v in vecs) / n for i in range(dim)]
                centroids[intent_type] = centroid
            self._centroid_vectors = centroids

            logger.info(
                f"Exemplar vectors initialized: {sum(len(v) for v in vectors.values())} vectors, "
                f"{len(centroids)} centroids"
            )

    async def classify(self, query: str, query_vector: list[float] | None = None) -> Intent:
        # Tier 1: Keyword match (high confidence only)
        keyword_intent, keyword_confidence = self._keyword_match(query)

        if keyword_intent and keyword_confidence >= KEYWORD_HIGH_CONFIDENCE:
            return self._build_intent(query, keyword_intent, keyword_confidence)

        # Tier 2: Semantic Router (centroid + exemplar combined matching)
        embedding_intent, embedding_score = None, 0.0
        if query_vector is not None:
            await self._ensure_exemplars()
            if self._exemplar_vectors:
                embedding_intent, embedding_score = self._semantic_match(
                    query_vector
                )

        # Decision logic
        if keyword_intent and keyword_confidence >= 0.8:
            keyword_intent = self._disambiguate(query, keyword_intent)
            if embedding_intent == keyword_intent:
                # Both agree — boost confidence
                return self._build_intent(
                    query, keyword_intent, min(keyword_confidence + 0.05, 1.0)
                )
            elif embedding_score >= EMBEDDING_MATCH_THRESHOLD:
                # Disagree — defer to LLM
                return await self._llm_classify(query)
            else:
                # Embedding has no strong opinion — trust keyword
                return self._build_intent(query, keyword_intent, keyword_confidence)

        if embedding_intent and embedding_score >= EMBEDDING_MATCH_THRESHOLD:
            # Keyword missed but embedding is confident
            return self._build_intent(query, embedding_intent, embedding_score)

        # Tier 3: LLM fallback
        return await self._llm_classify(query)

    def _embedding_match(
        self, query_vector: list[float]
    ) -> tuple[IntentType | None, float]:
        best_intent = None
        best_score = 0.0
        for intent_type, exemplar_vecs in self._exemplar_vectors.items():
            for ev in exemplar_vecs:
                sim = _cosine_similarity(query_vector, ev)
                if sim > best_score:
                    best_score = sim
                    best_intent = intent_type
        return best_intent, best_score

    def _semantic_match(
        self, query_vector: list[float]
    ) -> tuple[IntentType | None, float]:
        """Semantic Router: centroid + exemplar combined matching.

        Uses centroid similarity for stable category-level matching and
        individual exemplar similarity to catch edge-case phrasings.
        """
        # Centroid match (category-level)
        best_centroid_intent, best_centroid_score = None, 0.0
        if self._centroid_vectors:
            for intent_type, centroid in self._centroid_vectors.items():
                sim = _cosine_similarity(query_vector, centroid)
                if sim > best_centroid_score:
                    best_centroid_score = sim
                    best_centroid_intent = intent_type

        # Exemplar match (individual edge-case coverage)
        best_exemplar_intent, best_exemplar_score = self._embedding_match(query_vector)

        # Combined scoring
        if best_centroid_intent == best_exemplar_intent:
            # Both agree — weighted average (centroid 60%, exemplar 40%)
            combined = 0.6 * best_centroid_score + 0.4 * best_exemplar_score
            return best_centroid_intent, combined
        elif best_exemplar_score > best_centroid_score + 0.05:
            # Exemplar strongly disagrees — trust exemplar (edge-case phrasings)
            return best_exemplar_intent, best_exemplar_score
        else:
            # Default to centroid (more stable)
            return best_centroid_intent, best_centroid_score

    def _build_intent(
        self, query: str, intent_type: IntentType, confidence: float
    ) -> Intent:
        intent_type = self._disambiguate(query, intent_type)
        entities = self._extract_entities(query)
        complexity = self._assess_complexity(query, intent_type)
        requires_regulation = intent_type in (
            IntentType.DIVIDEND_CHECK,
            IntentType.EXCLUSION_EXCEPTION,
            IntentType.REGULATION_INQUIRY,
        ) or any(kw in query for kw in ["규제", "법", "의무", "위반"])
        logger.info(
            f"Intent classified: intent={intent_type.value}, "
            f"confidence={confidence:.2f}"
        )
        return Intent(
            type=intent_type,
            confidence=confidence,
            entities=entities,
            requires_regulation=requires_regulation,
            complexity=complexity,
        )

    def _keyword_match(self, query: str) -> tuple[IntentType | None, float]:
        # Pre-check: negation patterns override to exclusion
        for pattern in _NEGATION_PATTERNS:
            if pattern.search(query):
                return IntentType.EXCLUSION_EXCEPTION, 0.95

        scores: dict[IntentType, float] = {}

        for intent_type, keywords in KEYWORD_MAP.items():
            matches = sum(1 for kw in keywords if kw in query)
            if matches > 0:
                score = min(0.9 + matches * 0.02, 1.0)
                scores[intent_type] = score

        if not scores:
            return None, 0.0

        # Pick the intent with highest score; on tie, prefer more specific
        # (non-GENERAL) intents
        best_intent = max(scores, key=lambda k: scores[k])
        return best_intent, scores[best_intent]

    def _disambiguate(
        self, query: str, primary_intent: IntentType
    ) -> IntentType:
        """Resolve ambiguity when a query matches multiple intent types."""
        # Highest priority: regulatory terms (비교공시, 산출이율, 보험가격지수)
        # must be checked BEFORE disambiguation rules to avoid "비교" triggering
        # policy_comparison when "비교공시" is a regulatory term (O08)
        has_reg_term = any(t in query for t in _REGULATORY_TERMS)
        has_strong_calc = any(t in query for t in _STRONG_CALC_TERMS)
        if has_reg_term and not has_strong_calc:
            return IntentType.REGULATION_INQUIRY

        for group_a, group_b, resolved_intent in DISAMBIGUATION_RULES:
            has_a = any(kw in query for kw in group_a)
            has_b = any(kw in query for kw in group_b)
            if has_a and has_b:
                return resolved_intent

        # Multi-product detection: 3+ product names → comparison
        products = self._extract_entities(query)
        if len(products) >= 3 and primary_intent != IntentType.POLICY_COMPARISON:
            return IntentType.POLICY_COMPARISON

        return primary_intent

    def _extract_entities(self, query: str) -> list[Entity]:
        entities = []
        seen: set[str] = set()
        for pattern in PRODUCT_PATTERNS:
            matches = re.findall(pattern, query)
            for match in matches:
                cleaned = _strip_particle(match.strip())
                if cleaned not in seen:
                    seen.add(cleaned)
                    entities.append(
                        Entity(name=cleaned, type="product_name", value=cleaned)
                    )
        return entities

    def _assess_complexity(self, query: str, intent_type: IntentType) -> str:
        if intent_type in (
            IntentType.DIVIDEND_CHECK,
            IntentType.EXCLUSION_EXCEPTION,
            IntentType.REGULATION_INQUIRY,
            IntentType.LOAN_INQUIRY,
            IntentType.POLICY_COMPARISON,
            IntentType.CALCULATION_INQUIRY,
        ):
            return "complex"
        if any(kw in query for kw in COMPLEX_KEYWORDS):
            return "complex"
        return "simple"

    async def _llm_classify(self, query: str) -> Intent:
        if not self._bedrock:
            logger.warning("No Bedrock client, defaulting to GENERAL")
            return self._default_intent(query)

        prompt = LLM_CLASSIFY_PROMPT.format(query=query)
        try:
            from app.config import settings

            result = await self._bedrock.invoke_with_retry(
                settings.bedrock_haiku_model_id,
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 512,
                    "system": LLM_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            raw_text = result["content"][0]["text"]
            data = self._extract_json(raw_text)
            if data is None:
                logger.warning(
                    f"LLM returned non-JSON response, defaulting to GENERAL: "
                    f"{raw_text[:200]}"
                )
                return self._default_intent(query)

            intent_type_str = data.get("intent_type", "general_inquiry")
            try:
                intent_type = IntentType(intent_type_str)
            except ValueError:
                logger.warning(
                    f"LLM returned unknown intent type '{intent_type_str}', "
                    f"defaulting to GENERAL"
                )
                intent_type = IntentType.GENERAL_INQUIRY

            intent = Intent(
                type=intent_type,
                confidence=data.get("confidence", 0.7),
                entities=[
                    Entity(**e) for e in data.get("entities", [])
                    if isinstance(e, dict)
                    and all(k in e for k in ("name", "type", "value"))
                ],
                requires_regulation=data.get("requires_regulation", False),
                complexity=data.get("complexity", "simple"),
            )
            logger.info(
                f"LLM classify: intent={intent.type.value}, "
                f"confidence={intent.confidence:.2f}"
            )
            return intent

        except Exception as e:
            logger.warning(f"LLM classification failed, defaulting to GENERAL: {e}")
            return self._default_intent(query)

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from LLM response, handling markdown code blocks."""
        # Try direct parse first
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        brace_match = re.search(r"\{[^{}]*\}", text)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _default_intent(self, query: str) -> Intent:
        """Build a safe default intent when classification fails."""
        return Intent(
            type=IntentType.GENERAL_INQUIRY,
            confidence=0.5,
            entities=self._extract_entities(query),
            requires_regulation=False,
            complexity="simple",
        )
