"""Tests for IntentClassifier (Phase 4A) — updated with new intent types."""
import json
from unittest.mock import AsyncMock

import pytest

from app.models.intent import IntentType


class TestIntentClassifier:
    def _make_classifier(self, bedrock_mock=None):
        from app.core.intent_classifier import IntentClassifier

        return IntentClassifier(bedrock=bedrock_mock or AsyncMock())

    # ── Phase 1: Keyword Matching ─────────────────────────────────

    async def test_keyword_coverage_inquiry(self):
        clf = self._make_classifier()
        intent = await clf.classify("이 보험의 보장항목을 알려주세요")
        assert intent.type == IntentType.COVERAGE_INQUIRY

    async def test_keyword_dividend_check(self):
        clf = self._make_classifier()
        intent = await clf.classify("무배당 종신보험에 배당금이 있나요?")
        assert intent.type == IntentType.DIVIDEND_CHECK

    async def test_keyword_exclusion_exception(self):
        clf = self._make_classifier()
        intent = await clf.classify("면책 사유와 예외 조건을 알려주세요")
        assert intent.type == IntentType.EXCLUSION_EXCEPTION

    async def test_keyword_surrender_value(self):
        clf = self._make_classifier()
        intent = await clf.classify("해약환급금은 얼마나 받을 수 있나요?")
        assert intent.type == IntentType.SURRENDER_VALUE

    async def test_keyword_discount_eligibility(self):
        clf = self._make_classifier()
        intent = await clf.classify("보험료 할인 조건이 뭔가요?")
        assert intent.type == IntentType.DISCOUNT_ELIGIBILITY

    async def test_keyword_match_high_confidence(self):
        clf = self._make_classifier()
        intent = await clf.classify("배당금 있나요?")
        assert intent.confidence >= 0.9

    # ── New Intent Types ──────────────────────────────────────────

    async def test_keyword_loan_inquiry(self):
        clf = self._make_classifier()
        intent = await clf.classify(
            "보험계약대출은 얼마까지 가능한가요? 이자율과 상환 조건은?"
        )
        assert intent.type == IntentType.LOAN_INQUIRY

    async def test_keyword_loan_inquiry_simple(self):
        clf = self._make_classifier()
        intent = await clf.classify("대출 한도가 어떻게 되나요?")
        assert intent.type == IntentType.LOAN_INQUIRY

    async def test_keyword_premium_waiver(self):
        clf = self._make_classifier()
        intent = await clf.classify("어떤 경우에 보험료 납입이 면제되나요?")
        assert intent.type == IntentType.PREMIUM_WAIVER

    async def test_keyword_premium_waiver_explicit(self):
        clf = self._make_classifier()
        intent = await clf.classify("납입면제 조건을 알려주세요")
        assert intent.type == IntentType.PREMIUM_WAIVER

    async def test_keyword_obligation_violation_maps_to_exclusion(self):
        """QW4: 고지의무/알릴 의무 위반 → EXCLUSION_EXCEPTION (not REGULATION)."""
        clf = self._make_classifier()
        intent = await clf.classify("계약 전 알릴 의무를 위반하면 어떻게 되나요?")
        assert intent.type == IntentType.EXCLUSION_EXCEPTION

    # ── Disambiguation ────────────────────────────────────────────

    async def test_disambiguation_coverage_plus_exclusion(self):
        """Scenario B: query mentions both coverage and exclusion keywords."""
        clf = self._make_classifier()
        intent = await clf.classify(
            "사망보험금은 어떤 경우에 지급되나요? 면책 사유와 예외 조건도 알려주세요."
        )
        assert intent.type == IntentType.EXCLUSION_EXCEPTION

    # ── Phase 2: LLM Fallback ─────────────────────────────────────

    async def test_llm_fallback_general_inquiry(self):
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [
                {
                    "text": json.dumps(
                        {
                            "intent_type": "general_inquiry",
                            "confidence": 0.7,
                            "entities": [],
                            "requires_regulation": False,
                            "complexity": "simple",
                        }
                    )
                }
            ]
        }
        clf = self._make_classifier(mock_bedrock)
        intent = await clf.classify("이 보험에 대해 알려주세요")
        assert intent.type == IntentType.GENERAL_INQUIRY

    async def test_llm_fallback_with_markdown_code_block(self):
        """LLM sometimes wraps JSON in markdown code blocks."""
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [
                {
                    "text": (
                        "```json\n"
                        '{"intent_type": "loan_inquiry", "confidence": 0.85, '
                        '"entities": [], "requires_regulation": false, '
                        '"complexity": "complex"}\n'
                        "```"
                    )
                }
            ]
        }
        clf = self._make_classifier(mock_bedrock)
        intent = await clf.classify("이 보험에 대해 알려주세요")
        assert intent.type == IntentType.LOAN_INQUIRY
        assert intent.confidence == 0.85

    async def test_llm_fallback_with_extra_text(self):
        """LLM sometimes includes explanatory text around JSON."""
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [
                {
                    "text": (
                        '분석 결과: {"intent_type": "surrender_value", '
                        '"confidence": 0.8, "entities": [], '
                        '"requires_regulation": false, "complexity": "simple"}'
                    )
                }
            ]
        }
        clf = self._make_classifier(mock_bedrock)
        intent = await clf.classify("이 보험에 대해 알려주세요")
        assert intent.type == IntentType.SURRENDER_VALUE

    async def test_llm_fallback_invalid_json(self):
        """LLM returns completely non-JSON response."""
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": "I don't understand the question."}]
        }
        clf = self._make_classifier(mock_bedrock)
        intent = await clf.classify("이 보험에 대해 알려주세요")
        assert intent.type == IntentType.GENERAL_INQUIRY
        assert intent.confidence == 0.5

    async def test_llm_fallback_unknown_intent_type(self):
        """LLM returns an intent_type not in our enum."""
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [
                {
                    "text": json.dumps(
                        {
                            "intent_type": "unknown_type",
                            "confidence": 0.6,
                            "entities": [],
                            "requires_regulation": False,
                            "complexity": "simple",
                        }
                    )
                }
            ]
        }
        clf = self._make_classifier(mock_bedrock)
        intent = await clf.classify("이 보험에 대해 알려주세요")
        assert intent.type == IntentType.GENERAL_INQUIRY

    async def test_llm_fallback_bedrock_exception(self):
        """Bedrock call throws an exception."""
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.side_effect = Exception("Bedrock unavailable")
        clf = self._make_classifier(mock_bedrock)
        intent = await clf.classify("이 보험에 대해 알려주세요")
        assert intent.type == IntentType.GENERAL_INQUIRY
        assert intent.confidence == 0.5

    async def test_llm_fallback_no_bedrock_client(self):
        """Classifier created without Bedrock client."""
        from app.core.intent_classifier import IntentClassifier

        clf = IntentClassifier(bedrock=None)
        intent = await clf.classify("이 보험에 대해 알려주세요")
        assert intent.type == IntentType.GENERAL_INQUIRY

    async def test_llm_fallback_malformed_entities(self):
        """LLM returns entities with missing fields."""
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [
                {
                    "text": json.dumps(
                        {
                            "intent_type": "coverage_inquiry",
                            "confidence": 0.8,
                            "entities": [
                                {"name": "good", "type": "product", "value": "v"},
                                {"bad": "missing fields"},
                            ],
                            "requires_regulation": False,
                            "complexity": "simple",
                        }
                    )
                }
            ]
        }
        clf = self._make_classifier(mock_bedrock)
        intent = await clf.classify("이 보험에 대해 알려주세요")
        assert intent.type == IntentType.COVERAGE_INQUIRY
        # Only the valid entity should be included
        assert len(intent.entities) == 1

    # ── Entity Extraction ─────────────────────────────────────────

    async def test_entity_extraction_product_name(self):
        clf = self._make_classifier()
        intent = await clf.classify("한화생명 상속H종신보험의 보장항목을 알려주세요")
        product_entities = [e for e in intent.entities if e.type == "product_name"]
        assert len(product_entities) >= 1

    # ── Complexity Assessment ─────────────────────────────────────

    async def test_complexity_simple_for_coverage(self):
        clf = self._make_classifier()
        intent = await clf.classify("보장항목 알려주세요")
        assert intent.complexity == "simple"

    async def test_complexity_complex_for_dividend_with_regulation(self):
        clf = self._make_classifier()
        intent = await clf.classify("배당금 규제 관련 상계 처리는?")
        assert intent.complexity == "complex"

    async def test_complexity_complex_for_loan(self):
        clf = self._make_classifier()
        intent = await clf.classify("보험계약대출 이자율과 상환 조건은?")
        assert intent.complexity == "complex"

    # ── requires_regulation Flag ──────────────────────────────────

    async def test_requires_regulation_for_obligation_violation(self):
        clf = self._make_classifier()
        intent = await clf.classify("알릴 의무를 위반하면 어떻게 되나요?")
        assert intent.requires_regulation is True

    # ── JSON Extraction Helper ────────────────────────────────────

    def test_extract_json_direct(self):
        from app.core.intent_classifier import IntentClassifier

        clf = IntentClassifier()
        data = clf._extract_json('{"key": "value"}')
        assert data == {"key": "value"}

    def test_extract_json_markdown_block(self):
        from app.core.intent_classifier import IntentClassifier

        clf = IntentClassifier()
        data = clf._extract_json('```json\n{"key": "value"}\n```')
        assert data == {"key": "value"}

    def test_extract_json_embedded(self):
        from app.core.intent_classifier import IntentClassifier

        clf = IntentClassifier()
        data = clf._extract_json('Result: {"key": "value"} done')
        assert data == {"key": "value"}

    def test_extract_json_no_json(self):
        from app.core.intent_classifier import IntentClassifier

        clf = IntentClassifier()
        assert clf._extract_json("no json here") is None


class TestCosineAndEmbeddingTier:
    """Tests for cosine similarity and Tier 2 embedding classification."""

    def test_cosine_similarity_identical(self):
        from app.core.intent_classifier import _cosine_similarity
        vec = [1.0, 0.0, 0.0]
        assert _cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        from app.core.intent_classifier import _cosine_similarity
        assert _cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)

    def test_cosine_similarity_zero_vector(self):
        from app.core.intent_classifier import _cosine_similarity
        assert _cosine_similarity([0, 0], [1, 0]) == 0.0

    async def test_exemplar_vectors_initialized_lazily(self):
        from app.core.intent_classifier import IntentClassifier
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = [0.1] * 1024
        clf = IntentClassifier(bedrock=AsyncMock(), embedding_client=mock_embed)
        assert clf._exemplar_vectors is None
        await clf.classify("보장항목 알려주세요", query_vector=[0.1] * 1024)
        assert clf._exemplar_vectors is not None

    async def test_exemplar_vectors_computed_once(self):
        from app.core.intent_classifier import IntentClassifier
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = [0.1] * 1024
        clf = IntentClassifier(bedrock=AsyncMock(), embedding_client=mock_embed)
        await clf.classify("보장항목", query_vector=[0.1] * 1024)
        count_after_first = mock_embed.embed.call_count
        await clf.classify("배당금", query_vector=[0.2] * 1024)
        assert mock_embed.embed.call_count == count_after_first

    async def test_no_embedding_client_skips_tier2(self):
        """Without embedding_client, falls back to old 2-tier behavior."""
        from app.core.intent_classifier import IntentClassifier
        clf = IntentClassifier(bedrock=AsyncMock())
        intent = await clf.classify("보장항목 알려주세요")
        assert intent.type == IntentType.COVERAGE_INQUIRY

    async def test_embedding_match_returns_intent_and_score(self):
        from app.core.intent_classifier import IntentClassifier
        mock_embed = AsyncMock()
        # Return distinct vectors for each exemplar — just use intent index as base
        call_count = [0]
        async def varying_embed(text):
            call_count[0] += 1
            return [float(call_count[0])] * 1024
        mock_embed.embed = varying_embed

        clf = IntentClassifier(bedrock=AsyncMock(), embedding_client=mock_embed)
        await clf._ensure_exemplars()
        assert clf._exemplar_vectors is not None
        # _embedding_match should return a tuple
        intent, score = clf._embedding_match([1.0] * 1024)
        assert intent is not None
        assert isinstance(score, float)


class TestAllSixScenarios:
    """Test that all 6 demo scenarios classify to the correct intent type
    via Phase 1 keyword matching (no LLM call needed)."""

    def _make_classifier(self):
        from app.core.intent_classifier import IntentClassifier

        return IntentClassifier(bedrock=None)

    async def test_scenario_a_dividend(self):
        clf = self._make_classifier()
        intent = await clf.classify(
            "무배당 종신보험에 배당금이 있나요? 상계 처리는 어떻게 되나요?"
        )
        assert intent.type == IntentType.DIVIDEND_CHECK
        assert intent.confidence >= 0.9

    async def test_scenario_b_coverage_exclusion(self):
        clf = self._make_classifier()
        intent = await clf.classify(
            "사망보험금은 어떤 경우에 지급되나요? 면책 사유와 예외 조건도 알려주세요."
        )
        assert intent.type == IntentType.EXCLUSION_EXCEPTION
        assert intent.confidence >= 0.9

    async def test_scenario_c_premium_waiver(self):
        clf = self._make_classifier()
        intent = await clf.classify("어떤 경우에 보험료 납입이 면제되나요?")
        assert intent.type == IntentType.PREMIUM_WAIVER
        assert intent.confidence >= 0.9

    async def test_scenario_d_obligation_violation(self):
        """QW4: Scenario D now correctly maps to EXCLUSION_EXCEPTION."""
        clf = self._make_classifier()
        intent = await clf.classify(
            "계약 전 알릴 의무를 위반하면 어떻게 되나요?"
        )
        assert intent.type == IntentType.EXCLUSION_EXCEPTION
        assert intent.confidence >= 0.9

    async def test_scenario_e_surrender(self):
        clf = self._make_classifier()
        intent = await clf.classify(
            "해약환급금은 어떻게 계산되나요? 가입 후 기간에 따라 어떻게 달라지나요?"
        )
        assert intent.type == IntentType.SURRENDER_VALUE
        assert intent.confidence >= 0.9

    async def test_scenario_f_loan(self):
        clf = self._make_classifier()
        intent = await clf.classify(
            "보험계약대출은 얼마까지 가능한가요? 이자율과 상환 조건은 어떻게 되나요?"
        )
        assert intent.type == IntentType.LOAN_INQUIRY
        assert intent.confidence >= 0.9


class TestComparisonIntent:
    """Tests for POLICY_COMPARISON intent classification."""

    def _make_classifier(self):
        from app.core.intent_classifier import IntentClassifier

        return IntentClassifier(bedrock=None)

    async def test_keyword_comparison_explicit(self):
        clf = self._make_classifier()
        intent = await clf.classify(
            "H보장보험이랑 H건강플러스보험의 보장항목을 비교해주세요"
        )
        assert intent.type == IntentType.POLICY_COMPARISON
        assert intent.confidence >= 0.9

    async def test_keyword_comparison_difference(self):
        clf = self._make_classifier()
        intent = await clf.classify("두 보험의 차이점이 뭐야?")
        assert intent.type == IntentType.POLICY_COMPARISON
        assert intent.confidence >= 0.9

    async def test_keyword_comparison_which_better(self):
        clf = self._make_classifier()
        intent = await clf.classify("e건강보험과 e암보험 중 어떤게 더 좋아?")
        assert intent.type == IntentType.POLICY_COMPARISON
        assert intent.confidence >= 0.9

    async def test_disambiguation_comparison_over_coverage(self):
        """Query with both 비교 and 보장 should resolve to COMPARISON."""
        clf = self._make_classifier()
        intent = await clf.classify("보장항목 비교해주세요")
        assert intent.type == IntentType.POLICY_COMPARISON

    async def test_disambiguation_comparison_over_dividend(self):
        clf = self._make_classifier()
        intent = await clf.classify("배당금 구조 차이점을 알려주세요")
        assert intent.type == IntentType.POLICY_COMPARISON

    async def test_comparison_always_complex(self):
        clf = self._make_classifier()
        intent = await clf.classify("비교해주세요")
        assert intent.complexity == "complex"

    async def test_comparison_extracts_two_products(self):
        clf = self._make_classifier()
        intent = await clf.classify(
            "H보장보험과 H건강플러스보험의 보장 범위를 비교해 주세요"
        )
        product_entities = [e for e in intent.entities if e.type == "product_name"]
        assert len(product_entities) >= 2

    async def test_entity_strips_korean_particles(self):
        """Product names should have trailing Korean particles removed."""
        clf = self._make_classifier()
        intent = await clf.classify(
            "H보장보험이랑 H건강플러스보험의 보장항목을 비교해주세요"
        )
        product_entities = [e for e in intent.entities if e.type == "product_name"]
        values = {e.value for e in product_entities}
        assert "H보장보험" in values
        assert "H건강플러스보험" in values
        # Particles should be stripped
        assert not any(v.endswith("이랑") for v in values)
        assert not any(v.endswith("의") for v in values)

    async def test_llm_fallback_comparison(self):
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [
                {
                    "text": json.dumps(
                        {
                            "intent_type": "policy_comparison",
                            "confidence": 0.9,
                            "entities": [],
                            "requires_regulation": False,
                            "complexity": "complex",
                        }
                    )
                }
            ]
        }
        from app.core.intent_classifier import IntentClassifier

        clf = IntentClassifier(bedrock=mock_bedrock)
        intent = await clf.classify("이 보험이 저 보험보다 좋나요?")
        assert intent.type == IntentType.POLICY_COMPARISON

    async def test_single_coverage_not_comparison(self):
        """Regression: '보장항목 알려주세요' should NOT be POLICY_COMPARISON."""
        clf = self._make_classifier()
        intent = await clf.classify("보장항목 알려주세요")
        assert intent.type == IntentType.COVERAGE_INQUIRY

    # ── Disambiguation edge cases ────────────────────────────────

    async def test_disambiguate_납입면제형_is_coverage(self):
        """A10: 납입면제형 product variant suffix → coverage, not premium_waiver."""
        clf = self._make_classifier()
        intent = await clf.classify(
            "시그니처 H통합건강보험 납입면제형에서 어떤 질병들을 보장하나요?"
        )
        assert intent.type == IntentType.COVERAGE_INQUIRY

    async def test_disambiguate_1종_2종_환급금_is_surrender(self):
        """C03: 1종/2종 해약환급금 차이 within same product → surrender_value."""
        clf = self._make_classifier()
        intent = await clf.classify(
            "제로백H종신보험의 1종과 2종 해약환급금 차이는?"
        )
        assert intent.type == IntentType.SURRENDER_VALUE

    async def test_disambiguate_할인혜택_is_discount(self):
        """E06: 할인 혜택 should be discount, not coverage from product name."""
        clf = self._make_classifier()
        intent = await clf.classify(
            "진심가득 보장보험의 가족 할인 혜택이 있나요?"
        )
        assert intent.type == IntentType.DISCOUNT_ELIGIBILITY

    async def test_disambiguate_어떻게계산_is_calculation(self):
        """G01: 사망보험금은 어떻게 계산 → calculation, not coverage."""
        clf = self._make_classifier()
        intent = await clf.classify("H종신보험의 사망보험금은 어떻게 계산되나요?")
        assert intent.type == IntentType.CALCULATION_INQUIRY

    async def test_disambiguate_적용이율_정해진_is_calculation(self):
        """G05: 적용이율 어떻게 정해진 → calculation, not coverage."""
        clf = self._make_classifier()
        intent = await clf.classify(
            "보장부분 적용이율 2.75%는 어떻게 정해진 건가요?"
        )
        assert intent.type == IntentType.CALCULATION_INQUIRY

    async def test_disambiguate_보장개시일_계산_is_calculation(self):
        """G07: 보장개시일 계산 → calculation, not coverage."""
        clf = self._make_classifier()
        intent = await clf.classify(
            "치매 보장은 언제부터 시작되나요? 보장개시일 계산은?"
        )
        assert intent.type == IntentType.CALCULATION_INQUIRY

    async def test_disambiguate_특약_내용_is_rider(self):
        """H03: 특약의 내용 → rider, not premium_waiver."""
        clf = self._make_classifier()
        intent = await clf.classify("50%장해보험료납입면제특약의 내용은?")
        assert intent.type == IntentType.RIDER_INQUIRY

    async def test_disambiguate_특약_보장_is_rider(self):
        """H06: 특약 어떤 보장 → rider, not coverage."""
        clf = self._make_classifier()
        intent = await clf.classify(
            "간호/간병서비스지원금특약은 어떤 보장을 하나요?"
        )
        assert intent.type == IntentType.RIDER_INQUIRY

    async def test_disambiguate_금지행위_예외_is_regulation(self):
        """N03: 보험업 금지행위와 예외 → regulation, not exclusion."""
        clf = self._make_classifier()
        intent = await clf.classify(
            "보험업 허가와 관련된 금지행위와 그 예외는?"
        )
        assert intent.type == IntentType.REGULATION_INQUIRY

    async def test_disambiguate_비교공시_is_regulation(self):
        """O08: 비교공시 is regulatory term, not policy comparison."""
        clf = self._make_classifier()
        intent = await clf.classify(
            "보험업법 제95조의3에서 정하는 보험상품 비교공시란?"
        )
        assert intent.type == IntentType.REGULATION_INQUIRY
