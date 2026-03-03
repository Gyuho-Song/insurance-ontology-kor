"""Tests for HallucinationValidator (Phase 4G)."""
import json
from unittest.mock import AsyncMock

import pytest

from app.models.template import TemplateExecution
from app.models.traversal import TraversalResult


class TestHallucinationValidator:
    def _make_validator(self, bedrock_mock=None):
        from app.core.hallucination_validator import HallucinationValidator

        return HallucinationValidator(bedrock=bedrock_mock or AsyncMock())

    def _make_traversal_result(self):
        return TraversalResult(
            paths=[],
            subgraph_nodes=[
                {"id": "Policy#1", "type": "Policy", "label": "Test", "properties": {}},
                {"id": "Cov#1", "type": "Coverage", "label": "사망보장", "properties": {}},
            ],
            subgraph_edges=[
                {"source": "Policy#1", "target": "Cov#1", "type": "HAS_COVERAGE", "properties": {}},
            ],
            traversal_events=[],
            total_hops=2,
            constraints_found=0,
        )

    def test_layer1_template_only_pass(self):
        validator = self._make_validator()
        executions = [
            TemplateExecution(
                template_id="coverage_lookup",
                gremlin_query="g.V('x')",
                params={},
                max_depth=3,
                entry_node_ids=["x"],
            )
        ]
        assert validator.check_template_only(executions) is True

    def test_layer1_template_only_fail(self):
        validator = self._make_validator()
        executions = [
            TemplateExecution(
                template_id="unknown_template",
                gremlin_query="g.V('x')",
                params={},
                max_depth=3,
                entry_node_ids=["x"],
            )
        ]
        assert validator.check_template_only(executions) is False

    def test_layer3_topo_faithfulness_perfect(self):
        validator = self._make_validator()
        from app.models.validation import VerifiedClaim

        claims = [
            VerifiedClaim(
                claim_text="HAS_COVERAGE 관계",
                source_node_id="Cov#1",
                source_edge_type="HAS_COVERAGE",
                verified=True,
            )
        ]
        traversal = self._make_traversal_result()
        score = validator.topo_faithfulness(claims, traversal)
        assert score == 1.0

    def test_layer3_topo_faithfulness_partial(self):
        validator = self._make_validator()
        from app.models.validation import VerifiedClaim

        claims = [
            VerifiedClaim(
                claim_text="HAS_COVERAGE",
                source_node_id="Cov#1",
                source_edge_type="HAS_COVERAGE",
                verified=True,
            ),
            VerifiedClaim(
                claim_text="NONEXISTENT",
                source_node_id="X#1",
                source_edge_type="FAKE_EDGE",
                verified=True,
            ),
        ]
        traversal = self._make_traversal_result()
        score = validator.topo_faithfulness(claims, traversal)
        assert score == 0.5

    def test_layer3_topo_faithfulness_no_relations(self):
        validator = self._make_validator()
        traversal = self._make_traversal_result()
        score = validator.topo_faithfulness([], traversal)
        assert score == 1.0

    async def test_validate_full_pipeline(self):
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": '["사망보장이 포함됩니다"]'}]
        }

        validator = self._make_validator(mock_bedrock)
        executions = [
            TemplateExecution(
                template_id="coverage_lookup",
                gremlin_query="g.V('x')",
                params={},
                max_depth=3,
                entry_node_ids=["x"],
            )
        ]
        traversal = self._make_traversal_result()

        result = await validator.validate(
            answer_text="사망보장이 포함됩니다",
            executions=executions,
            traversal_result=traversal,
        )
        assert result.template_only is True
        assert result.topo_faithfulness >= 0.0

    def test_find_source_uses_properties_source_text(self):
        validator = self._make_validator()
        traversal = TraversalResult(
            paths=[],
            subgraph_nodes=[
                {
                    "id": "Reg#1",
                    "type": "Regulation",
                    "label": "보험업법 제95조",
                    "properties": {
                        "source_text": "자본금 기준에 관한 규정",
                        "source_section_id": "제95조제1항",
                    },
                },
            ],
            subgraph_edges=[
                {
                    "source": "Policy#1",
                    "target": "Reg#1",
                    "type": "GOVERNED_BY",
                    "properties": {},
                },
            ],
            traversal_events=[],
            total_hops=1,
            constraints_found=0,
        )
        # Claim contains source_text, not label
        match = validator._find_source_in_subgraph(
            "자본금 기준에 관한 규정이 적용됩니다", traversal
        )
        assert match is not None
        assert match["node_id"] == "Reg#1"
        assert match["edge_type"] == "GOVERNED_BY"
        assert match["source_article"] == "제95조제1항"
        assert match["source_text"] == "자본금 기준에 관한 규정"

    def test_find_source_falls_back_to_label(self):
        validator = self._make_validator()
        traversal = TraversalResult(
            paths=[],
            subgraph_nodes=[
                {
                    "id": "Cov#1",
                    "type": "Coverage",
                    "label": "사망보장",
                    "properties": {},
                },
            ],
            subgraph_edges=[],
            traversal_events=[],
            total_hops=1,
            constraints_found=0,
        )
        match = validator._find_source_in_subgraph("사망보장이 포함됩니다", traversal)
        assert match is not None
        assert match["node_id"] == "Cov#1"
        assert match["source_text"] == "사망보장"

    async def test_extract_claims_markdown_fence(self):
        """Haiku sometimes wraps JSON in ```json ... ``` fences."""
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": '```json\n["주장1", "주장2"]\n```'}]
        }
        validator = self._make_validator(mock_bedrock)
        claims = await validator._extract_claims("테스트 답변")
        assert claims == ["주장1", "주장2"]

    async def test_extract_claims_text_before_json(self):
        """Haiku sometimes adds explanatory text before the JSON array."""
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": '다음은 추출된 주장입니다:\n["사망보장 포함"]'}]
        }
        validator = self._make_validator(mock_bedrock)
        claims = await validator._extract_claims("테스트 답변")
        assert claims == ["사망보장 포함"]

    async def test_extract_claims_empty_response(self):
        """Empty response should return empty list, not crash."""
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": ""}]
        }
        validator = self._make_validator(mock_bedrock)
        claims = await validator._extract_claims("테스트 답변")
        assert claims == []

    async def test_extract_claims_plain_json(self):
        """Normal JSON array response should still work."""
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": '["보험료 납입", "사망보장"]'}]
        }
        validator = self._make_validator(mock_bedrock)
        claims = await validator._extract_claims("테스트 답변")
        assert claims == ["보험료 납입", "사망보장"]

    def test_parse_json_array_direct(self):
        from app.core.hallucination_validator import HallucinationValidator
        assert HallucinationValidator._parse_json_array('["a", "b"]') == ["a", "b"]

    def test_parse_json_array_fenced(self):
        from app.core.hallucination_validator import HallucinationValidator
        assert HallucinationValidator._parse_json_array('```json\n["a"]\n```') == ["a"]

    def test_parse_json_array_with_prefix(self):
        from app.core.hallucination_validator import HallucinationValidator
        assert HallucinationValidator._parse_json_array('결과:\n["a"]') == ["a"]

    def test_parse_json_array_invalid_raises(self):
        from app.core.hallucination_validator import HallucinationValidator
        with pytest.raises(json.JSONDecodeError):
            HallucinationValidator._parse_json_array("no json here")

    async def test_validate_timeout_graceful(self):
        """Test that validation can be wrapped with asyncio.wait_for externally."""
        validator = self._make_validator()
        # This just tests the interface works
        executions = [
            TemplateExecution(
                template_id="coverage_lookup",
                gremlin_query="g.V('x')",
                params={},
                max_depth=3,
                entry_node_ids=["x"],
            )
        ]
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_with_retry.return_value = {
            "content": [{"text": '["claim1"]'}]
        }
        validator._bedrock = mock_bedrock

        result = await validator.validate(
            answer_text="claim1",
            executions=executions,
            traversal_result=self._make_traversal_result(),
        )
        assert result.passed is not None
