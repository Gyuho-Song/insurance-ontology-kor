"""Tests for Orchestrator MyData integration (Stage 5.5 + 6.7)."""
import json
from unittest.mock import AsyncMock

import pytest

from app.models.mydata import MergeContext
from app.models.traversal import TraversalResult
from app.services.mydata_service import reset_consent_store


@pytest.fixture(autouse=True)
def _clean_consent():
    reset_consent_store()
    yield
    reset_consent_store()


def _make_traversal_result():
    """Minimal traversal result with a Policy and Coverage node."""
    return TraversalResult(
        paths=[],
        subgraph_nodes=[
            {"id": "Policy#hwl_h_whole_life", "type": "Policy", "label": "한화생명 H종신보험 무배당", "properties": {}},
            {"id": "Cov#1", "type": "Coverage", "label": "사망보장", "properties": {}},
        ],
        subgraph_edges=[
            {"source": "Policy#hwl_h_whole_life", "target": "Cov#1", "type": "HAS_COVERAGE", "properties": {}},
        ],
        traversal_events=[
            {"type": "node_activated", "hop": 0, "delay_ms": 0, "data": {"node_id": "Policy#hwl_h_whole_life"}},
            {"type": "edge_traversed", "hop": 0, "delay_ms": 200, "data": {"edge_type": "HAS_COVERAGE"}},
            {"type": "node_activated", "hop": 1, "delay_ms": 500, "data": {"node_id": "Cov#1"}},
            {"type": "traversal_complete", "hop": 1, "delay_ms": 700, "data": {}},
        ],
        total_hops=1,
        constraints_found=0,
    )


def _make_merge_context():
    return MergeContext(
        customer_node={
            "id": "Customer#박지영",
            "type": "Customer",
            "label": "박지영",
            "properties": {"customer_id": "CUSTOMER_PARK", "customer_name": "박지영", "contract_count": 1},
        },
        owns_edges=[
            {
                "source": "Customer#박지영",
                "target": "Policy#hwl_h_whole_life",
                "type": "OWNS",
                "properties": {
                    "contract_id": "CONTRACT_001",
                    "start_date": "2020-03-15",
                    "product_type": "whole_life",
                    "contract_status": "active",
                    "premium_amount": 300000,
                },
            },
        ],
        activated_policy_ids=["Policy#hwl_h_whole_life"],
    )


class TestApplyMydataMerge:
    def _get_orchestrator(self):
        from app.core.orchestrator import Orchestrator

        return Orchestrator(
            neptune=AsyncMock(),
            opensearch=AsyncMock(),
            bedrock=AsyncMock(),
            embedding=AsyncMock(),
        )

    def test_mydata_merge_adds_customer_node(self):
        orch = self._get_orchestrator()
        result = orch._apply_mydata_merge(
            _make_traversal_result(), _make_merge_context()
        )
        node_ids = [n["id"] for n in result.subgraph_nodes]
        assert "Customer#박지영" in node_ids

    def test_mydata_merge_adds_owns_edges(self):
        orch = self._get_orchestrator()
        result = orch._apply_mydata_merge(
            _make_traversal_result(), _make_merge_context()
        )
        owns_edges = [e for e in result.subgraph_edges if e["type"] == "OWNS"]
        assert len(owns_edges) == 1
        assert owns_edges[0]["source"] == "Customer#박지영"
        assert owns_edges[0]["target"] == "Policy#hwl_h_whole_life"

    def test_mydata_merge_generates_events(self):
        orch = self._get_orchestrator()
        result = orch._apply_mydata_merge(
            _make_traversal_result(), _make_merge_context()
        )
        merge_events = [e for e in result.traversal_events if e["type"] == "merge_node_added"]
        assert len(merge_events) >= 1  # At least Customer node event
        # Should have Customer node + OWNS edge events
        assert len(merge_events) == 2  # 1 customer + 1 OWNS edge

    def test_mydata_merge_preserves_existing_nodes(self):
        orch = self._get_orchestrator()
        original = _make_traversal_result()
        original_node_count = len(original.subgraph_nodes)
        result = orch._apply_mydata_merge(original, _make_merge_context())
        # All original nodes should still be present
        original_ids = {"Policy#hwl_h_whole_life", "Cov#1"}
        result_ids = {n["id"] for n in result.subgraph_nodes}
        assert original_ids.issubset(result_ids)
        # Plus Customer node
        assert len(result.subgraph_nodes) == original_node_count + 1

    def test_mydata_merge_event_delay_ordering(self):
        orch = self._get_orchestrator()
        result = orch._apply_mydata_merge(
            _make_traversal_result(), _make_merge_context()
        )
        delays = [e["delay_ms"] for e in result.traversal_events]
        # Delays should be monotonically non-decreasing
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1], (
                f"delay at {i} ({delays[i]}) < delay at {i-1} ({delays[i-1]})"
            )

    def test_mydata_merge_ends_with_traversal_complete(self):
        orch = self._get_orchestrator()
        result = orch._apply_mydata_merge(
            _make_traversal_result(), _make_merge_context()
        )
        assert result.traversal_events[-1]["type"] == "traversal_complete"

    def test_mydata_merge_preserves_hops_and_constraints(self):
        orch = self._get_orchestrator()
        original = _make_traversal_result()
        result = orch._apply_mydata_merge(original, _make_merge_context())
        assert result.total_hops == original.total_hops
        assert result.constraints_found == original.constraints_found


class TestOrchestratorMydataIntegration:
    """Test MyData flow through the full orchestrator pipeline."""

    def _make_orchestrator(self):
        from app.core.orchestrator import Orchestrator

        neptune_results = [
            {
                "objects": [
                    {"T.id": "Policy#hwl_h_whole_life", "T.label": "Policy", "label": ["e연금보험"]},
                    {"T.id": "e1", "T.label": "HAS_COVERAGE"},
                    {"T.id": "Cov#1", "T.label": "Coverage", "label": ["사망보장"]},
                ]
            }
        ]

        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = neptune_results

        mock_opensearch = AsyncMock()
        mock_opensearch.search_knn.return_value = [
            {
                "node_id": "Policy#hwl_h_whole_life",
                "node_type": "Policy",
                "node_label": "e연금보험",
                "score": 0.92,
                "text_content": "content",
            }
        ]
        mock_opensearch.search_text.return_value = []

        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": '["답변"]'}]
        }
        mock_bedrock.invoke_stream_with_retry.return_value = {
            "body": [
                {
                    "chunk": {
                        "bytes": json.dumps(
                            {"type": "content_block_delta", "delta": {"text": "답변 텍스트"}}
                        ).encode()
                    }
                },
                {
                    "chunk": {
                        "bytes": json.dumps({"type": "message_stop"}).encode()
                    }
                },
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

    def _make_request(self, with_mydata=True):
        from app.models.response import ChatRequest
        from app.services.mydata_service import MyDataService

        if with_mydata:
            # Grant consent first
            svc = MyDataService()
            svc.grant_consent("CUSTOMER_PARK")

        return ChatRequest(
            messages=[{"role": "user", "content": "배당금 받을 수 있나요?"}],
            persona="consultant",
            mydata_consent=(
                {"customer_id": "CUSTOMER_PARK", "consented": True}
                if with_mydata
                else None
            ),
        )

    async def test_mydata_no_consent_skips_merge(self):
        orch = self._make_orchestrator()
        request = self._make_request(with_mydata=False)
        result = await orch.run(request)
        # No Customer node in subgraph
        node_types = [n.get("type") for n in result.subgraph.get("nodes", [])]
        assert "Customer" not in node_types
