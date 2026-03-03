"""Tests for all Pydantic data models (Phase 1)."""
import pytest
from pydantic import ValidationError


# === Intent Models ===


class TestIntentModels:
    def test_intent_type_enum_values(self):
        from app.models.intent import IntentType

        assert IntentType.COVERAGE_INQUIRY == "coverage_inquiry"
        assert IntentType.DIVIDEND_CHECK == "dividend_check"
        assert IntentType.EXCLUSION_EXCEPTION == "exclusion_exception"
        assert IntentType.SURRENDER_VALUE == "surrender_value"
        assert IntentType.DISCOUNT_ELIGIBILITY == "discount_eligibility"
        assert IntentType.GENERAL_INQUIRY == "general_inquiry"

    def test_entity_creation(self):
        from app.models.intent import Entity

        entity = Entity(name="한화생명 상속H종신보험", type="product_name", value="hanwha_h")
        assert entity.name == "한화생명 상속H종신보험"
        assert entity.type == "product_name"

    def test_intent_creation(self):
        from app.models.intent import Entity, Intent, IntentType

        intent = Intent(
            type=IntentType.DIVIDEND_CHECK,
            confidence=0.98,
            entities=[Entity(name="test", type="product_name", value="test_val")],
            requires_regulation=True,
            complexity="complex",
        )
        assert intent.type == IntentType.DIVIDEND_CHECK
        assert intent.confidence == 0.98
        assert intent.complexity == "complex"
        assert len(intent.entities) == 1


# === Query Models ===


class TestQueryModels:
    def test_expanded_query(self):
        from app.models.query import ExpandedQuery

        eq = ExpandedQuery(
            original="배당금 있나요?",
            expanded="배당금 이익배당 있나요?",
            synonyms_applied=[{"original": "배당금", "expanded": "이익배당"}],
            embedding_text="배당금 이익배당 있나요?",
        )
        assert eq.original == "배당금 있나요?"
        assert len(eq.synonyms_applied) == 1

    def test_entry_node(self):
        from app.models.query import EntryNode

        node = EntryNode(
            node_id="Policy#test",
            node_type="Policy",
            node_label="Test Policy",
            score=0.92,
            text_content="Policy content",
        )
        assert node.score == 0.92
        assert node.node_type == "Policy"


# === Template Models ===


class TestTemplateModels:
    def test_gremlin_template(self):
        from app.models.template import GremlinTemplate

        tmpl = GremlinTemplate(
            id="coverage_lookup",
            description="보장항목 조회",
            intent_type="coverage_inquiry",
            gremlin="g.V('{policy_id}')",
            params=["policy_id"],
            max_depth=3,
            complexity="simple",
        )
        assert tmpl.id == "coverage_lookup"
        assert tmpl.max_depth == 3

    def test_template_execution(self):
        from app.models.template import TemplateExecution

        exec_item = TemplateExecution(
            template_id="coverage_lookup",
            gremlin_query="g.V('Policy#test')",
            params={"policy_id": "Policy#test"},
            max_depth=3,
            entry_node_ids=["Policy#test"],
        )
        assert exec_item.template_id == "coverage_lookup"

    def test_chain_result(self):
        from app.models.template import ChainResult, TemplateExecution

        chain = ChainResult(
            executions=[
                TemplateExecution(
                    template_id="t1",
                    gremlin_query="g.V('x')",
                    params={},
                    max_depth=2,
                    entry_node_ids=["x"],
                )
            ],
            chain_order=["t1"],
        )
        assert len(chain.executions) == 1


# === Traversal Models ===


class TestTraversalModels:
    def test_constraint_result(self):
        from app.models.traversal import ConstraintResult

        cr = ConstraintResult(
            edge_type="STRICTLY_PROHIBITED",
            blocked=True,
            reason="보험업법 제95조",
            regulation_id="Regulation#95",
            condition_met=None,
        )
        assert cr.blocked is True

    def test_traversal_path(self):
        from app.models.traversal import TraversalPath

        path = TraversalPath(
            nodes=[{"id": "n1", "type": "Policy", "label": "P1", "properties": {}}],
            edges=[{"source": "n1", "target": "n2", "type": "HAS_COVERAGE", "properties": {}}],
            constraints=[],
            depth=1,
        )
        assert len(path.nodes) == 1

    def test_traversal_result(self):
        from app.models.traversal import TraversalResult

        result = TraversalResult(
            paths=[],
            subgraph_nodes=[{"id": "n1", "type": "Policy", "label": "P1", "properties": {}}],
            subgraph_edges=[],
            traversal_events=[],
            total_hops=2,
            constraints_found=1,
        )
        assert result.total_hops == 2
        assert result.constraints_found == 1


# === Scoring Models ===


class TestScoringModels:
    def test_hybrid_score(self):
        from app.models.scoring import HybridScore

        score = HybridScore(
            vector_similarity=0.92,
            graph_context=0.88,
            regulation_weight=1.0,
            final_score=0.92,
            weights={"vector": 0.3, "graph": 0.5, "regulation": 0.2},
        )
        assert score.final_score == 0.92
        assert score.weights["vector"] == 0.3


# === Validation Models ===


class TestValidationModels:
    def test_verified_claim(self):
        from app.models.validation import VerifiedClaim

        claim = VerifiedClaim(
            claim_text="무배당 상품입니다",
            source_node_id="Policy#test",
            source_edge_type="NO_DIVIDEND_STRUCTURE",
            source_article="제5조①",
            source_text="이 보험은 무배당...",
            verified=True,
        )
        assert claim.verified is True

    def test_validation_result(self):
        from app.models.validation import ValidationResult

        result = ValidationResult(
            template_only=True,
            templates_used=["coverage_lookup"],
            verified_claims=[],
            unverified_claims=[],
            source_coverage=0.95,
            topo_faithfulness=0.985,
            answer_relations=10,
            graph_relations=12,
            matched_relations=10,
            passed=True,
            confidence_label="high",
        )
        assert result.passed is True
        assert result.topo_faithfulness == 0.985


# === Response Models ===


class TestResponseModels:
    def test_source_reference(self):
        from app.models.response import SourceReference

        ref = SourceReference(
            node_id="Clause#test",
            node_type="Clause",
            node_label="제5조①",
            source_article="제5조①",
            source_text="이 보험은 무배당...",
        )
        assert ref.source_article == "제5조①"

    def test_chat_request_valid(self):
        from app.models.response import ChatRequest

        req = ChatRequest(
            messages=[{"role": "user", "content": "배당금 있나요?"}],
            persona="consultant",
        )
        assert req.persona == "consultant"
        assert req.mock_mode is False

    def test_chat_request_invalid_persona(self):
        from app.models.response import ChatRequest

        with pytest.raises(ValidationError):
            ChatRequest(
                messages=[{"role": "user", "content": "test"}],
                persona="invalid_role",
            )

    def test_chat_request_message_too_long(self):
        from app.models.response import ChatRequest

        with pytest.raises(ValidationError):
            ChatRequest(
                messages=[{"role": "user", "content": "x" * 2001}],
                persona="consultant",
            )

    def test_message_annotation(self):
        from app.models.response import MessageAnnotation

        ann = MessageAnnotation(
            sources=[],
            traversalEvents=[],
            subgraph={"nodes": [], "edges": []},
            topoFaithfulness=0.985,
            templatesUsed=["coverage_lookup"],
            validationStatus="completed",
        )
        assert ann.validationStatus == "completed"

    def test_message_annotation_timeout(self):
        from app.models.response import MessageAnnotation

        ann = MessageAnnotation(
            sources=[],
            traversalEvents=[],
            subgraph={"nodes": [], "edges": []},
            topoFaithfulness=None,
            templatesUsed=[],
            validationStatus="timeout",
        )
        assert ann.topoFaithfulness is None
        assert ann.validationStatus == "timeout"


# === Persona Models ===


class TestPersonaModels:
    def test_rbac_scope(self):
        from app.models.persona import RbacScope

        scope = RbacScope(
            accessible_node_types=["Policy", "Coverage"],
            can_toggle_mock_mode=False,
            can_view_trace=False,
            can_view_regulations=False,
        )
        assert "Policy" in scope.accessible_node_types

    def test_persona(self):
        from app.models.persona import Persona, RbacScope

        persona = Persona(
            id="consultant",
            name="김민수",
            role="보험 상담원",
            description="3년차 보험 상담원",
            rbac_scope=RbacScope(
                accessible_node_types=["Policy"],
                can_toggle_mock_mode=False,
                can_view_trace=False,
                can_view_regulations=False,
            ),
            avatar="consultant",
        )
        assert persona.id == "consultant"

    def test_scenario(self):
        from app.models.persona import Scenario

        scenario = Scenario(
            id="A",
            title="무배당 배당금 상계",
            description="테스트 시나리오",
            query="무배당 종신보험에 배당금이 있나요?",
            personas=["consultant", "presenter"],
            category="basic",
        )
        assert scenario.id == "A"
        assert "consultant" in scenario.personas
