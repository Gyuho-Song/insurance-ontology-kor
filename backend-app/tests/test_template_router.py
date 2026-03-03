"""Tests for TemplateRouter (Phase 4C) — updated with fallback builders."""
import pytest

from app.models.intent import Entity, Intent, IntentType


class TestTemplateRouter:
    def _make_router(self):
        from app.core.template_router import TemplateRouter

        return TemplateRouter()

    # ── Intent-to-Template Mapping ────────────────────────────────

    def test_coverage_intent_maps_to_coverage_lookup(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.COVERAGE_INQUIRY,
            confidence=0.95,
            entities=[Entity(name="test", type="product_name", value="Policy#test")],
            requires_regulation=False,
            complexity="simple",
        )
        result = router.route(intent, entry_node_ids=["Policy#test"])
        assert result.executions[0].template_id == "coverage_lookup"

    def test_dividend_intent_with_product_maps_to_dividend_check(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.DIVIDEND_CHECK,
            confidence=0.95,
            entities=[Entity(name="H종신보험", type="product_name", value="H종신보험")],
            requires_regulation=True,
            complexity="complex",
        )
        result = router.route(intent, entry_node_ids=["Policy#test"])
        assert result.executions[0].template_id == "dividend_eligibility_check"

    def test_dividend_intent_without_product_maps_to_portfolio(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.DIVIDEND_CHECK,
            confidence=0.95,
            entities=[],
            requires_regulation=True,
            complexity="complex",
        )
        result = router.route(intent, entry_node_ids=["Policy#test"])
        assert result.executions[0].template_id == "dividend_portfolio_check"

    def test_exclusion_intent_maps_correctly(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.EXCLUSION_EXCEPTION,
            confidence=0.95,
            entities=[Entity(name="자해", type="exclusion_type", value="자해")],
            requires_regulation=False,
            complexity="complex",
        )
        result = router.route(intent, entry_node_ids=["Policy#test"])
        assert result.executions[0].template_id == "exclusion_exception_traverse"

    def test_loan_intent_maps_to_comprehensive(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.LOAN_INQUIRY,
            confidence=0.95,
            entities=[],
            requires_regulation=False,
            complexity="complex",
        )
        result = router.route(intent, entry_node_ids=["Policy#test"])
        assert result.executions[0].template_id == "comprehensive_lookup"

    def test_premium_waiver_intent_maps_to_premium_waiver_lookup(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.PREMIUM_WAIVER,
            confidence=0.92,
            entities=[],
            requires_regulation=False,
            complexity="simple",
        )
        result = router.route(intent, entry_node_ids=["Policy#test"])
        assert result.executions[0].template_id == "premium_waiver_lookup"

    # ── Parameter Binding ─────────────────────────────────────────

    def test_param_binding_with_policy_id(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.SURRENDER_VALUE,
            confidence=0.95,
            entities=[],
            requires_regulation=False,
            complexity="simple",
        )
        result = router.route(intent, entry_node_ids=["Policy#hanwha_h"])
        assert "Policy#hanwha_h" in result.executions[0].gremlin_query

    def test_gremlin_injection_escape(self):
        from app.core.template_router import escape_gremlin_param

        assert escape_gremlin_param("test'value") == "test\\'value"
        assert escape_gremlin_param("test\\value") == "test\\\\value"
        assert escape_gremlin_param("test`value") == "test\\`value"

    # ── Chaining ──────────────────────────────────────────────────

    def test_chain_trigger_for_coverage_with_exclusion(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.COVERAGE_INQUIRY,
            confidence=0.95,
            entities=[
                Entity(name="면책", type="exclusion_type", value="면책"),
            ],
            requires_regulation=False,
            complexity="complex",
        )
        result = router.route(intent, entry_node_ids=["Policy#test"])
        assert len(result.executions) >= 1
        template_ids = [e.template_id for e in result.executions]
        assert "coverage_lookup" in template_ids

    # ── Fallback Routing ──────────────────────────────────────────

    def test_general_inquiry_gets_coverage_fallback(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.GENERAL_INQUIRY,
            confidence=0.5,
            entities=[],
            requires_regulation=False,
            complexity="simple",
        )
        result = router.route(intent, entry_node_ids=["Policy#test"])
        assert len(result.executions) >= 1

    # ── Comprehensive Fallback Builder ────────────────────────────

    def test_comprehensive_fallback_with_policy_nodes(self):
        router = self._make_router()
        result = router.build_comprehensive_fallback(
            ["Policy#a", "Policy#b", "Regulation#r"]
        )
        assert result is not None
        # Should use up to 2 Policy nodes
        assert len(result.executions) == 2
        assert all(
            e.template_id == "comprehensive_lookup" for e in result.executions
        )

    def test_comprehensive_fallback_none_without_policy(self):
        router = self._make_router()
        result = router.build_comprehensive_fallback(
            ["Regulation#a", "Coverage#b"]
        )
        assert result is None

    def test_comprehensive_fallback_empty_list(self):
        router = self._make_router()
        result = router.build_comprehensive_fallback([])
        assert result is None

    # ── Neighborhood Fallback Builder ─────────────────────────────

    def test_neighborhood_fallback_with_nodes(self):
        router = self._make_router()
        result = router.build_neighborhood_fallback(
            ["Regulation#a", "Exception#b"]
        )
        assert result is not None
        assert len(result.executions) == 1
        assert result.executions[0].template_id == "neighborhood_lookup"
        # Should include both node IDs in the query
        query = result.executions[0].gremlin_query
        assert "Regulation#a" in query
        assert "Exception#b" in query

    def test_neighborhood_fallback_limits_to_5_nodes(self):
        router = self._make_router()
        ids = [f"Node#{i}" for i in range(10)]
        result = router.build_neighborhood_fallback(ids)
        assert result is not None
        # Should only include first 5
        query = result.executions[0].gremlin_query
        assert "Node#0" in query
        assert "Node#4" in query
        assert "Node#5" not in query

    def test_neighborhood_fallback_none_for_empty(self):
        router = self._make_router()
        assert router.build_neighborhood_fallback([]) is None

    def test_neighborhood_fallback_none_for_unknown(self):
        router = self._make_router()
        assert router.build_neighborhood_fallback(["Policy#unknown"]) is None

    def test_neighborhood_fallback_escapes_special_chars(self):
        router = self._make_router()
        result = router.build_neighborhood_fallback(["Node#test'val"])
        assert result is not None
        assert "\\'" in result.executions[0].gremlin_query

    # ── Regulation Routing ────────────────────────────────────────

    def test_regulation_forward_from_policy(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.REGULATION_INQUIRY,
            confidence=0.95,
            entities=[],
            requires_regulation=True,
            complexity="complex",
        )
        result = router.route(intent, entry_node_ids=["Policy#test"])
        assert any(
            e.template_id == "regulation_lookup" for e in result.executions
        )

    def test_regulation_reverse_from_regulation(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.REGULATION_INQUIRY,
            confidence=0.95,
            entities=[],
            requires_regulation=True,
            complexity="complex",
        )
        result = router.route(intent, entry_node_ids=["Regulation#test"])
        assert any(
            e.template_id == "regulation_reverse_lookup"
            for e in result.executions
        )

    def test_regulation_bidirectional(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.REGULATION_INQUIRY,
            confidence=0.95,
            entities=[],
            requires_regulation=True,
            complexity="complex",
        )
        result = router.route(
            intent,
            entry_node_ids=["Policy#test", "Regulation#test"],
        )
        template_ids = [e.template_id for e in result.executions]
        assert "regulation_lookup" in template_ids
        assert "regulation_reverse_lookup" in template_ids


class TestComparisonRouting:
    """Tests for cross-policy comparison routing."""

    def _make_router(self):
        from app.core.template_router import TemplateRouter

        return TemplateRouter()

    def test_comparison_routes_two_policies(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.POLICY_COMPARISON,
            confidence=0.95,
            entities=[],
            requires_regulation=False,
            complexity="complex",
        )
        result = router.route(
            intent, entry_node_ids=["Policy#a", "Policy#b"]
        )
        assert len(result.executions) == 2
        assert result.executions[0].template_id == result.executions[1].template_id
        assert result.executions[0].params["policy_id"] == "Policy#a"
        assert result.executions[1].params["policy_id"] == "Policy#b"

    def test_comparison_with_one_policy(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.POLICY_COMPARISON,
            confidence=0.85,
            entities=[],
            requires_regulation=False,
            complexity="complex",
        )
        result = router.route(
            intent, entry_node_ids=["Policy#a", "Coverage#c1"]
        )
        assert len(result.executions) >= 1
        assert result.executions[0].params["policy_id"] == "Policy#a"

    def test_comparison_limits_to_two(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.POLICY_COMPARISON,
            confidence=0.95,
            entities=[],
            requires_regulation=False,
            complexity="complex",
        )
        result = router.route(
            intent,
            entry_node_ids=["Policy#a", "Policy#b", "Policy#c"],
        )
        assert len(result.executions) == 2

    def test_comparison_uses_comprehensive_for_general(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.POLICY_COMPARISON,
            confidence=0.95,
            entities=[],
            requires_regulation=False,
            complexity="complex",
        )
        result = router.route(
            intent, entry_node_ids=["Policy#a", "Policy#b"]
        )
        assert all(
            e.template_id == "comprehensive_lookup"
            for e in result.executions
        )

    def test_comparison_always_uses_comprehensive(self):
        """Comparison always uses comprehensive_lookup even with aspect keywords,
        because not all policies have the same edge types."""
        router = self._make_router()
        intent = Intent(
            type=IntentType.POLICY_COMPARISON,
            confidence=0.95,
            entities=[
                Entity(name="보장", type="keyword", value="보장항목"),
            ],
            requires_regulation=False,
            complexity="complex",
        )
        result = router.route(
            intent, entry_node_ids=["Policy#a", "Policy#b"]
        )
        assert all(
            e.template_id == "comprehensive_lookup"
            for e in result.executions
        )

    def test_comparison_with_zero_policies(self):
        router = self._make_router()
        intent = Intent(
            type=IntentType.POLICY_COMPARISON,
            confidence=0.7,
            entities=[],
            requires_regulation=False,
            complexity="complex",
        )
        result = router.route(
            intent, entry_node_ids=["Regulation#r1"]
        )
        assert len(result.executions) >= 1
