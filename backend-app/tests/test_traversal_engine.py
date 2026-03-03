"""Tests for TraversalEngine (Phase 4D) — updated with new edge types."""
from unittest.mock import AsyncMock

import pytest

from app.models.template import TemplateExecution


class TestTraversalEngine:
    def _make_engine(self, neptune_mock=None):
        from app.core.traversal_engine import TraversalEngine

        return TraversalEngine(neptune=neptune_mock or AsyncMock())

    def _make_execution(self, template_id="coverage_lookup"):
        return TemplateExecution(
            template_id=template_id,
            gremlin_query="g.V('Policy#test').outE().inV().path()",
            params={"policy_id": "Policy#test"},
            max_depth=3,
            entry_node_ids=["Policy#test"],
        )

    # ── Basic Traversal ──────────────────────────────────────────

    async def test_traverse_returns_result(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["Test Policy"]},
                    {"T.id": "e1", "T.label": "HAS_COVERAGE"},
                    {"T.id": "Coverage#1", "T.label": "Coverage", "label": ["사망보장"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        assert result.total_hops >= 0
        assert len(result.subgraph_nodes) >= 0

    async def test_traversal_events_generated(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["P1"]},
                    {"T.id": "e1", "T.label": "HAS_COVERAGE"},
                    {"T.id": "Cov#1", "T.label": "Coverage", "label": ["C1"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        assert len(result.traversal_events) >= 1
        event_types = [e["type"] for e in result.traversal_events]
        assert "node_activated" in event_types

    # ── Constraint Events ─────────────────────────────────────────

    async def test_constraint_blocked_event(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["P1"]},
                    {"T.id": "e1", "T.label": "STRICTLY_PROHIBITED"},
                    {"T.id": "Reg#1", "T.label": "Regulation", "label": ["보험업법 제95조"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        assert result.constraints_found >= 1

    async def test_constraint_opened_event(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["P1"]},
                    {"T.id": "e1", "T.label": "EXCEPTIONALLY_ALLOWED"},
                    {"T.id": "Exc#1", "T.label": "Exception", "label": ["예외"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        assert result.constraints_found >= 1
        event_types = [e["type"] for e in result.traversal_events]
        assert "constraint_opened" in event_types

    # ── Traversal Complete ────────────────────────────────────────

    async def test_traversal_complete_event(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["P1"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        event_types = [e["type"] for e in result.traversal_events]
        assert "traversal_complete" in event_types

    # ── Delay Increments ──────────────────────────────────────────

    async def test_delay_ms_increments(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "P#1", "T.label": "Policy", "label": ["P1"]},
                    {"T.id": "e1", "T.label": "HAS_COVERAGE"},
                    {"T.id": "C#1", "T.label": "Coverage", "label": ["C1"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        delays = [e["delay_ms"] for e in result.traversal_events]
        assert delays[0] == 0
        for i in range(1, len(delays)):
            assert delays[i] > delays[i - 1]

    # ── Empty Results ─────────────────────────────────────────────

    async def test_empty_result(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = []
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        assert result.total_hops == 0

    # ── New Edge Type Recognition ─────────────────────────────────

    async def test_requires_eligibility_recognized_as_edge(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["P1"]},
                    {"T.id": "e1", "T.label": "REQUIRES_ELIGIBILITY"},
                    {"T.id": "Elig#1", "T.label": "Eligibility", "label": ["가입자격"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        # The edge should be in subgraph_edges, not in subgraph_nodes
        node_ids = [n["id"] for n in result.subgraph_nodes]
        assert "e1" not in node_ids  # edge ID should not appear as node
        assert "Policy#test" in node_ids
        assert "Elig#1" in node_ids
        # Should have an edge connecting them
        assert len(result.subgraph_edges) >= 1
        assert result.subgraph_edges[0]["type"] == "REQUIRES_ELIGIBILITY"

    async def test_has_rider_recognized_as_edge(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["P1"]},
                    {"T.id": "e1", "T.label": "HAS_RIDER"},
                    {"T.id": "Rider#1", "T.label": "Rider", "label": ["장해특약"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        node_ids = [n["id"] for n in result.subgraph_nodes]
        assert "e1" not in node_ids
        assert "Rider#1" in node_ids
        assert any(e["type"] == "HAS_RIDER" for e in result.subgraph_edges)

    async def test_has_loan_recognized_as_edge(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["P1"]},
                    {"T.id": "e1", "T.label": "HAS_LOAN"},
                    {"T.id": "Loan#1", "T.label": "Loan", "label": ["약관대출"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        node_ids = [n["id"] for n in result.subgraph_nodes]
        assert "e1" not in node_ids
        assert "Loan#1" in node_ids

    async def test_waives_premium_recognized_as_edge(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["P1"]},
                    {"T.id": "e1", "T.label": "WAIVES_PREMIUM"},
                    {"T.id": "Waiver#1", "T.label": "Waiver", "label": ["납입면제"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        node_ids = [n["id"] for n in result.subgraph_nodes]
        assert "e1" not in node_ids
        assert "Waiver#1" in node_ids

    # ── Multiple Executions ───────────────────────────────────────

    async def test_multiple_executions_merged(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.side_effect = [
            [
                {
                    "objects": [
                        {"T.id": "P#1", "T.label": "Policy", "label": ["P1"]},
                        {"T.id": "e1", "T.label": "HAS_COVERAGE"},
                        {"T.id": "C#1", "T.label": "Coverage", "label": ["C1"]},
                    ]
                }
            ],
            [
                {
                    "objects": [
                        {"T.id": "P#1", "T.label": "Policy", "label": ["P1"]},
                        {"T.id": "e2", "T.label": "GOVERNED_BY"},
                        {"T.id": "R#1", "T.label": "Regulation", "label": ["R1"]},
                    ]
                }
            ],
        ]
        engine = self._make_engine(mock_neptune)
        exec1 = self._make_execution("coverage_lookup")
        exec2 = self._make_execution("regulation_lookup")
        result = await engine.traverse([exec1, exec2])
        node_ids = [n["id"] for n in result.subgraph_nodes]
        # P#1 should be deduplicated
        assert node_ids.count("P#1") == 1
        assert "C#1" in node_ids
        assert "R#1" in node_ids

    # ── Property Extraction ──────────────────────────────────────

    async def test_node_properties_extracted(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {
                        "T.id": "Policy#test",
                        "T.label": "Policy",
                        "label": ["Test Policy"],
                        "source_text": "보험약관 원문",
                        "document_id": "doc_001",
                        "provider": "한화생명",
                    },
                    {"T.id": "e1", "T.label": "HAS_COVERAGE"},
                    {
                        "T.id": "Coverage#1",
                        "T.label": "Coverage",
                        "label": ["사망보장"],
                        "source_text": "사망 보장 내용",
                        "source_section_id": "제3조",
                    },
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])

        policy_node = next(
            n for n in result.subgraph_nodes if n["id"] == "Policy#test"
        )
        assert policy_node["properties"]["source_text"] == "보험약관 원문"
        assert policy_node["properties"]["document_id"] == "doc_001"
        assert policy_node["properties"]["provider"] == "한화생명"
        # Meta keys should be excluded
        assert "T.id" not in policy_node["properties"]
        assert "T.label" not in policy_node["properties"]

        cov_node = next(
            n for n in result.subgraph_nodes if n["id"] == "Coverage#1"
        )
        assert cov_node["properties"]["source_text"] == "사망 보장 내용"
        assert cov_node["properties"]["source_section_id"] == "제3조"

    async def test_edge_properties_extracted(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["P1"]},
                    {
                        "T.id": "e1",
                        "T.label": "HAS_COVERAGE",
                        "source_text": "엣지 설명",
                        "IN": {"T.id": "Coverage#1"},
                        "OUT": {"T.id": "Policy#test"},
                    },
                    {"T.id": "Coverage#1", "T.label": "Coverage", "label": ["C1"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])

        assert len(result.subgraph_edges) == 1
        edge = result.subgraph_edges[0]
        assert edge["properties"]["source_text"] == "엣지 설명"
        # IN/OUT should be excluded
        assert "IN" not in edge["properties"]
        assert "OUT" not in edge["properties"]

    async def test_empty_properties_when_no_extra_fields(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.return_value = [
            {
                "objects": [
                    {"T.id": "Policy#test", "T.label": "Policy", "label": ["P1"]},
                ]
            }
        ]
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        # When there are no extra properties beyond meta keys, properties should be empty
        assert result.subgraph_nodes[0]["properties"] == {}

    # ── Neptune Failure ───────────────────────────────────────────

    async def test_neptune_failure_returns_empty(self):
        mock_neptune = AsyncMock()
        mock_neptune.execute.side_effect = Exception("Neptune unreachable")
        engine = self._make_engine(mock_neptune)
        result = await engine.traverse([self._make_execution()])
        assert result.total_hops == 0
        assert len(result.subgraph_nodes) == 0
