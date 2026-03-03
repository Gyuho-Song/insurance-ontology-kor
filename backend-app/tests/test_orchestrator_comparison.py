"""Tests for RAG comparison toggle in Orchestrator."""
import json
from unittest.mock import AsyncMock

import pytest

from app.models.response import ChatRequest


class TestNaiveRagMode:
    """Tests for rag_mode='naive' — vector-only pipeline."""

    def _make_orchestrator(self):
        from app.core.orchestrator import Orchestrator

        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["Test"]},
                ]
            }
        ]

        mock_opensearch = AsyncMock()
        mock_opensearch.search_knn.return_value = [
            {
                "node_id": "Policy#test",
                "node_type": "Policy",
                "node_label": "Test Policy",
                "score": 0.92,
                "text_content": "테스트 보험 약관 텍스트",
            }
        ]
        mock_opensearch.search_text.return_value = []

        mock_bedrock = AsyncMock()
        # For naive RAG (non-streaming invoke_with_retry)
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": "Naive RAG 답변입니다."}]
        }
        # For GraphRAG streaming (should NOT be called in naive mode)
        mock_bedrock.invoke_stream_with_retry.return_value = {
            "body": [
                {"chunk": {"bytes": json.dumps(
                    {"type": "content_block_delta", "delta": {"text": "GraphRAG"}}
                ).encode()}},
                {"chunk": {"bytes": json.dumps({"type": "message_stop"}).encode()}},
            ]
        }

        mock_embedding = AsyncMock()
        mock_embedding.embed.return_value = [0.1] * 1024

        return Orchestrator(
            neptune=mock_neptune,
            opensearch=mock_opensearch,
            bedrock=mock_bedrock,
            embedding=mock_embedding,
        ), mock_neptune, mock_bedrock

    def _make_request(self, rag_mode="naive"):
        return ChatRequest(
            messages=[{"role": "user", "content": "보장항목 알려주세요"}],
            persona="consultant",
            rag_mode=rag_mode,
        )

    @pytest.mark.asyncio
    async def test_naive_mode_skips_graph_stages(self):
        """In naive mode, Neptune (graph DB) should never be called."""
        orch, mock_neptune, _ = self._make_orchestrator()
        request = self._make_request(rag_mode="naive")

        async for _ in orch.run_stream(request):
            pass

        mock_neptune.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_naive_mode_yields_text_and_annotation(self):
        """Naive mode should yield data events + text + annotation."""
        orch, _, _ = self._make_orchestrator()
        request = self._make_request(rag_mode="naive")

        events = []
        async for event_type, data in orch.run_stream(request):
            events.append((event_type, data))

        # data events (security+understand+classify+search) + text + annotation
        text_events = [e for e in events if e[0] == "text"]
        ann_events = [e for e in events if e[0] == "annotation"]
        assert len(text_events) == 1
        assert text_events[0][1] == "Naive RAG 답변입니다."
        assert len(ann_events) == 1

    @pytest.mark.asyncio
    async def test_naive_mode_annotation_has_empty_subgraph(self):
        """Naive mode annotation should have no subgraph or traversal events."""
        orch, _, _ = self._make_orchestrator()
        request = self._make_request(rag_mode="naive")

        annotation = None
        async for event_type, data in orch.run_stream(request):
            if event_type == "annotation":
                annotation = data

        assert annotation is not None
        assert annotation["subgraph"] == {"nodes": [], "edges": []}
        assert annotation["traversalEvents"] == []
        assert annotation["topoFaithfulness"] is None
        assert annotation["templatesUsed"] == []
        assert annotation["validationStatus"] == "skipped"

    @pytest.mark.asyncio
    async def test_naive_mode_annotation_has_sources(self):
        """Naive mode annotation sources come from vector search results."""
        orch, _, _ = self._make_orchestrator()
        request = self._make_request(rag_mode="naive")

        annotation = None
        async for event_type, data in orch.run_stream(request):
            if event_type == "annotation":
                annotation = data

        assert len(annotation["sources"]) == 1
        assert annotation["sources"][0]["node_id"] == "Policy#test"
        assert annotation["sources"][0]["node_label"] == "Test Policy"


class TestComparisonMode:
    """Tests for rag_mode='comparison' — dual GraphRAG + Naive RAG."""

    def _make_orchestrator(self):
        from app.core.orchestrator import Orchestrator

        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["Test"]},
                    {"T.id": "e1", "T.label": "HAS_COVERAGE"},
                    {"T.id": "Cov#1", "T.label": "Coverage", "label": ["사망보장"]},
                ]
            }
        ]

        mock_opensearch = AsyncMock()
        mock_opensearch.search_knn.return_value = [
            {
                "node_id": "Policy#test",
                "node_type": "Policy",
                "node_label": "Test Policy",
                "score": 0.92,
                "text_content": "테스트 보험 약관 텍스트",
            }
        ]
        mock_opensearch.search_text.return_value = []

        mock_bedrock = AsyncMock()
        # For intent classification + naive RAG (invoke_with_retry called multiple times)
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": "Naive RAG 답변입니다."}]
        }
        # For GraphRAG streaming
        mock_bedrock.invoke_stream_with_retry.return_value = {
            "body": [
                {"chunk": {"bytes": json.dumps(
                    {"type": "content_block_delta", "delta": {"text": "GraphRAG 답변"}}
                ).encode()}},
                {"chunk": {"bytes": json.dumps({"type": "message_stop"}).encode()}},
            ]
        }

        mock_embedding = AsyncMock()
        mock_embedding.embed.return_value = [0.1] * 1024

        return Orchestrator(
            neptune=mock_neptune,
            opensearch=mock_opensearch,
            bedrock=mock_bedrock,
            embedding=mock_embedding,
        )

    def _make_request(self, rag_mode="comparison"):
        return ChatRequest(
            messages=[{"role": "user", "content": "보장항목 알려주세요"}],
            persona="consultant",
            rag_mode=rag_mode,
        )

    @pytest.mark.asyncio
    async def test_comparison_mode_includes_naive_rag_in_annotation(self):
        """Comparison annotation must include naiveRag with answer and sources."""
        orch = self._make_orchestrator()
        request = self._make_request(rag_mode="comparison")

        annotation = None
        async for event_type, data in orch.run_stream(request):
            if event_type == "annotation":
                annotation = data

        assert annotation is not None
        assert "naiveRag" in annotation
        assert annotation["naiveRag"]["answer"] == "Naive RAG 답변입니다."
        assert len(annotation["naiveRag"]["sources"]) >= 1
        assert "responseTimeMs" in annotation["naiveRag"]
        assert annotation["comparisonMode"] is True
        assert "graphRagResponseTimeMs" in annotation

    @pytest.mark.asyncio
    async def test_comparison_mode_shares_vector_search(self):
        """Vector search (OpenSearch) should be called exactly once (shared)."""
        orch = self._make_orchestrator()
        request = self._make_request(rag_mode="comparison")

        async for _ in orch.run_stream(request):
            pass

        # OpenSearch k-NN is called once in _run_shared_stages
        assert orch._opensearch.search_knn.call_count == 1

    @pytest.mark.asyncio
    async def test_default_rag_mode_is_graphrag(self):
        """Default request (no rag_mode specified) should not include naiveRag."""
        orch = self._make_orchestrator()
        request = ChatRequest(
            messages=[{"role": "user", "content": "보장항목 알려주세요"}],
            persona="consultant",
        )

        annotation = None
        async for event_type, data in orch.run_stream(request):
            if event_type == "annotation":
                annotation = data

        assert annotation is not None
        assert "naiveRag" not in annotation
        assert "comparisonMode" not in annotation
