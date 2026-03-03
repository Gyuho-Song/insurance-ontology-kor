"""Tests for AnswerGenerator (Phase 4F)."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.intent import Intent, IntentType
from app.models.mydata import MergeContext


class TestAnswerGenerator:
    def _make_generator(self, bedrock_mock=None):
        from app.core.answer_generator import AnswerGenerator

        return AnswerGenerator(bedrock=bedrock_mock or AsyncMock())

    def test_select_model_simple(self):
        gen = self._make_generator()
        intent = Intent(
            type=IntentType.COVERAGE_INQUIRY,
            confidence=0.95,
            entities=[],
            requires_regulation=False,
            complexity="simple",
        )
        model = gen.select_model(intent)
        assert "haiku" in model.lower()

    def test_select_model_complex(self):
        gen = self._make_generator()
        intent = Intent(
            type=IntentType.DIVIDEND_CHECK,
            confidence=0.95,
            entities=[],
            requires_regulation=True,
            complexity="complex",
        )
        model = gen.select_model(intent)
        assert "sonnet" in model.lower()

    async def test_generate_stream_yields_chunks(self):
        mock_bedrock = AsyncMock()
        chunks = [
            {"chunk": {"bytes": json.dumps({"type": "content_block_delta", "delta": {"text": "안녕"}}).encode()}},
            {"chunk": {"bytes": json.dumps({"type": "content_block_delta", "delta": {"text": "하세요"}}).encode()}},
            {"chunk": {"bytes": json.dumps({"type": "message_stop"}).encode()}},
        ]
        mock_bedrock.invoke_stream_with_retry.return_value = {"body": chunks}

        gen = self._make_generator(mock_bedrock)
        collected = []
        async for chunk in gen.generate_stream(
            subgraph={"nodes": [], "edges": []},
            query="test",
            model_id="test-model",
        ):
            collected.append(chunk)

        assert "안녕" in collected
        assert "하세요" in collected

    def test_trim_for_llm_filters_properties(self):
        from app.core.answer_generator import _trim_for_llm

        subgraph = {
            "nodes": [
                {
                    "id": "Policy#1",
                    "type": "Policy",
                    "label": "Test",
                    "properties": {
                        "source_text": "약관 내용",
                        "document_id": "doc1",
                        "internal_id": "should_be_removed",
                        "random_field": 123,
                    },
                }
            ],
            "edges": [
                {
                    "source": "Policy#1",
                    "target": "Cov#1",
                    "type": "HAS_COVERAGE",
                    "properties": {
                        "source_text": "엣지 텍스트",
                        "weight": 0.5,
                    },
                }
            ],
        }
        trimmed = _trim_for_llm(subgraph)
        node_props = trimmed["nodes"][0]["properties"]
        assert "source_text" in node_props
        assert "document_id" in node_props
        assert "internal_id" not in node_props
        assert "random_field" not in node_props

        edge_props = trimmed["edges"][0]["properties"]
        assert "source_text" in edge_props
        assert "weight" not in edge_props

    def test_trim_for_llm_truncates_long_values(self):
        from app.core.answer_generator import _trim_for_llm, _MAX_PROP_LEN

        subgraph = {
            "nodes": [
                {
                    "id": "N#1",
                    "type": "Policy",
                    "label": "T",
                    "properties": {"source_text": "x" * 1000},
                }
            ],
            "edges": [],
        }
        trimmed = _trim_for_llm(subgraph)
        val = trimmed["nodes"][0]["properties"]["source_text"]
        assert len(val) == _MAX_PROP_LEN + 3  # 500 + "..."
        assert val.endswith("...")

    async def test_generate_with_fallback_sonnet_to_haiku(self):
        mock_bedrock = AsyncMock()
        call_count = 0

        async def mock_stream(model_id, body):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Sonnet failed")
            return {
                "body": [
                    {"chunk": {"bytes": json.dumps({"type": "content_block_delta", "delta": {"text": "fallback"}}).encode()}},
                    {"chunk": {"bytes": json.dumps({"type": "message_stop"}).encode()}},
                ]
            }

        mock_bedrock.invoke_stream_with_retry.side_effect = mock_stream
        gen = self._make_generator(mock_bedrock)
        intent = Intent(
            type=IntentType.DIVIDEND_CHECK,
            confidence=0.95,
            entities=[],
            requires_regulation=True,
            complexity="complex",
        )

        collected = []
        async for chunk in gen.generate_with_fallback(
            subgraph={"nodes": [], "edges": []},
            query="test",
            intent=intent,
        ):
            collected.append(chunk)

        assert "fallback" in collected


class TestComparisonPrompt:
    """Tests for comparison-specific system prompt."""

    def _make_generator(self, bedrock_mock=None):
        from app.core.answer_generator import AnswerGenerator

        return AnswerGenerator(bedrock=bedrock_mock or AsyncMock())

    def test_comparison_prompt_uses_table_format(self):
        gen = self._make_generator()
        intent = Intent(
            type=IntentType.POLICY_COMPARISON,
            confidence=0.95,
            entities=[],
            requires_regulation=False,
            complexity="complex",
        )
        subgraph = {
            "nodes": [
                {"id": "Policy#a", "type": "Policy", "label": "H보장보험", "properties": {}},
                {"id": "Policy#b", "type": "Policy", "label": "H건강플러스", "properties": {}},
            ],
            "edges": [],
        }
        prompt = gen._build_system_prompt(subgraph, intent=intent)
        assert "비교 항목" in prompt
        assert "H보장보험" in prompt
        assert "H건강플러스" in prompt
        assert "마크다운 표" in prompt

    def test_comparison_prompt_fallback_names(self):
        gen = self._make_generator()
        intent = Intent(
            type=IntentType.POLICY_COMPARISON,
            confidence=0.95,
            entities=[],
            requires_regulation=False,
            complexity="complex",
        )
        prompt = gen._build_system_prompt({"nodes": [], "edges": []}, intent=intent)
        assert "보험상품 A" in prompt
        assert "보험상품 B" in prompt

    def test_non_comparison_uses_standard_prompt(self):
        gen = self._make_generator()
        intent = Intent(
            type=IntentType.COVERAGE_INQUIRY,
            confidence=0.95,
            entities=[],
            requires_regulation=False,
            complexity="simple",
        )
        prompt = gen._build_system_prompt({"nodes": [], "edges": []}, intent=intent)
        assert "비교 항목" not in prompt
        assert "보험 약관 전문 상담 AI" in prompt

    def test_comparison_always_selects_sonnet(self):
        gen = self._make_generator()
        intent = Intent(
            type=IntentType.POLICY_COMPARISON,
            confidence=0.95,
            entities=[],
            requires_regulation=False,
            complexity="complex",
        )
        model = gen.select_model(intent)
        assert "sonnet" in model.lower() or "claude-3" in model.lower()


class TestMyDataPrompt:
    """Tests for MyData-specific system prompt."""

    def _make_generator(self, bedrock_mock=None):
        from app.core.answer_generator import AnswerGenerator

        return AnswerGenerator(bedrock=bedrock_mock or AsyncMock())

    def _make_merge_context(self):
        return MergeContext(
            customer_node={
                "id": "Customer#박지영",
                "type": "Customer",
                "label": "박지영",
                "properties": {"customer_id": "CUSTOMER_PARK"},
            },
            owns_edges=[
                {
                    "source": "Customer#박지영",
                    "target": "Policy#hwl_h_whole_life",
                    "type": "OWNS",
                    "properties": {
                        "product_type": "whole_life",
                        "contract_status": "active",
                        "start_date": "2020-03-15",
                    },
                },
            ],
            activated_policy_ids=["Policy#hwl_h_whole_life"],
        )

    def test_mydata_prompt_includes_customer_name(self):
        gen = self._make_generator()
        intent = Intent(
            type=IntentType.DIVIDEND_CHECK,
            confidence=0.95,
            entities=[],
            requires_regulation=True,
            complexity="complex",
        )
        prompt = gen._build_system_prompt(
            {"nodes": [], "edges": []},
            intent=intent,
            merge_context=self._make_merge_context(),
        )
        assert "박지영" in prompt

    def test_mydata_prompt_includes_contracts(self):
        gen = self._make_generator()
        intent = Intent(
            type=IntentType.DIVIDEND_CHECK,
            confidence=0.95,
            entities=[],
            requires_regulation=True,
            complexity="complex",
        )
        prompt = gen._build_system_prompt(
            {"nodes": [], "edges": []},
            intent=intent,
            merge_context=self._make_merge_context(),
        )
        assert "Policy#hwl_h_whole_life" in prompt
        assert "whole_life" in prompt

    def test_mydata_prompt_includes_exception_rule(self):
        gen = self._make_generator()
        intent = Intent(
            type=IntentType.DIVIDEND_CHECK,
            confidence=0.95,
            entities=[],
            requires_regulation=True,
            complexity="complex",
        )
        prompt = gen._build_system_prompt(
            {"nodes": [], "edges": []},
            intent=intent,
            merge_context=self._make_merge_context(),
        )
        assert "EXCEPTIONALLY_ALLOWED" in prompt

    def test_non_mydata_uses_standard_prompt(self):
        gen = self._make_generator()
        intent = Intent(
            type=IntentType.COVERAGE_INQUIRY,
            confidence=0.95,
            entities=[],
            requires_regulation=False,
            complexity="simple",
        )
        prompt = gen._build_system_prompt(
            {"nodes": [], "edges": []}, intent=intent, merge_context=None
        )
        assert "고객님의 마이데이터 정보가 연동" not in prompt
        assert "보험 약관 전문 상담 AI" in prompt


class TestNaiveRagGenerator:
    """Tests for naive RAG (vector-only) answer generation."""

    def _make_generator(self, bedrock_mock=None):
        from app.core.answer_generator import AnswerGenerator

        return AnswerGenerator(bedrock=bedrock_mock or AsyncMock())

    @pytest.mark.asyncio
    async def test_generate_naive_rag_uses_text_content(self):
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": "무배당 종신보험은 배당금이 없습니다."}]
        }
        gen = self._make_generator(mock_bedrock)
        entry_nodes = [
            {
                "node_id": "Policy#A",
                "node_type": "Policy",
                "node_label": "종신보험",
                "text_content": "무배당 종신보험 약관 텍스트",
                "score": 0.92,
            },
        ]
        result = await gen.generate_naive_rag(entry_nodes, "배당금 있나요?")
        assert result == "무배당 종신보험은 배당금이 없습니다."
        # Verify the prompt included text_content
        call_args = mock_bedrock.invoke_with_retry.call_args
        body = call_args[0][1]
        assert "무배당 종신보험 약관 텍스트" in body["system"]
        assert "종신보험" in body["system"]

    @pytest.mark.asyncio
    async def test_generate_naive_rag_empty_nodes(self):
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": "확인할 수 없습니다."}]
        }
        gen = self._make_generator(mock_bedrock)
        result = await gen.generate_naive_rag([], "배당금 있나요?")
        assert result == "확인할 수 없습니다."
        call_args = mock_bedrock.invoke_with_retry.call_args
        body = call_args[0][1]
        assert "검색 결과 없음" in body["system"]

    @pytest.mark.asyncio
    async def test_naive_rag_uses_haiku(self):
        from app.core.answer_generator import HAIKU_MODEL

        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": "답변"}]
        }
        gen = self._make_generator(mock_bedrock)
        await gen.generate_naive_rag(
            [{"node_id": "P#1", "node_label": "test", "text_content": "text"}],
            "질문",
        )
        call_args = mock_bedrock.invoke_with_retry.call_args
        assert call_args[0][0] == HAIKU_MODEL
