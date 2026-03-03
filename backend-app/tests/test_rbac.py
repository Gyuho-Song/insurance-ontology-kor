"""Tests for RBAC Middleware (Phase 5) — updated for expanded scopes."""
import pytest


class TestRBAC:
    def test_consultant_scope(self):
        from app.middleware.rbac import get_rbac_scope

        scope = get_rbac_scope("consultant")
        assert "Policy" in scope.accessible_node_types
        assert "Regulation" in scope.accessible_node_types
        assert "Coverage" in scope.accessible_node_types
        assert scope.can_toggle_mock_mode is False
        assert scope.can_view_trace is False

    def test_customer_scope_limited(self):
        from app.middleware.rbac import get_rbac_scope

        scope = get_rbac_scope("customer")
        assert "Policy" in scope.accessible_node_types
        assert "Coverage" in scope.accessible_node_types
        # Customer has limited node types — no Exclusion, Exception, etc.
        assert "Exclusion" not in scope.accessible_node_types
        assert "Exception" not in scope.accessible_node_types
        assert "Rider" not in scope.accessible_node_types

    def test_presenter_scope_full(self):
        from app.middleware.rbac import get_rbac_scope

        scope = get_rbac_scope("presenter")
        assert "Regulation" in scope.accessible_node_types
        assert scope.can_toggle_mock_mode is True
        assert scope.can_view_trace is True

    def test_underwriter_scope(self):
        from app.middleware.rbac import get_rbac_scope

        scope = get_rbac_scope("underwriter")
        assert "Regulation" in scope.accessible_node_types
        assert "Exclusion" in scope.accessible_node_types
        assert scope.can_view_trace is True
        assert scope.can_toggle_mock_mode is False

    def test_unknown_persona_raises(self):
        from fastapi import HTTPException

        from app.middleware.rbac import get_rbac_scope

        with pytest.raises(HTTPException) as exc_info:
            get_rbac_scope("hacker")
        assert exc_info.value.status_code == 400

    def test_filter_subgraph_removes_unauthorized_nodes(self):
        from app.middleware.rbac import filter_subgraph

        subgraph = {
            "nodes": [
                {"id": "n1", "type": "Policy", "label": "P1"},
                {"id": "n2", "type": "Exclusion", "label": "E1"},
                {"id": "n3", "type": "Coverage", "label": "C1"},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "type": "EXCLUDED_IF"},
                {"source": "n1", "target": "n3", "type": "HAS_COVERAGE"},
            ],
        }
        # Customer doesn't have access to Exclusion
        result = filter_subgraph("customer", subgraph)
        node_ids = {n["id"] for n in result["nodes"]}
        assert "n2" not in node_ids  # Exclusion filtered
        assert "n1" in node_ids  # Policy kept
        assert "n3" in node_ids  # Coverage kept
        # Edge to Exclusion should be removed
        assert len(result["edges"]) == 1
        assert result["edges"][0]["type"] == "HAS_COVERAGE"

    def test_filter_subgraph_presenter_keeps_all(self):
        from app.middleware.rbac import filter_subgraph

        subgraph = {
            "nodes": [
                {"id": "n1", "type": "Policy", "label": "P1"},
                {"id": "n2", "type": "Regulation", "label": "R1"},
                {"id": "n3", "type": "Exclusion", "label": "E1"},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "type": "GOVERNED_BY"},
                {"source": "n1", "target": "n3", "type": "EXCLUDED_IF"},
            ],
        }
        result = filter_subgraph("presenter", subgraph)
        assert len(result["nodes"]) == 3
        assert len(result["edges"]) == 2
