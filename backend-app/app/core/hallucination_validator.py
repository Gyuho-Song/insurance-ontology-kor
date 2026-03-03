import json
import logging

from app.config import settings
from app.core.template_router import TEMPLATE_POOL
from app.models.template import TemplateExecution
from app.models.traversal import TraversalResult
from app.models.validation import ValidationResult, VerifiedClaim

logger = logging.getLogger("graphrag.validator")


class HallucinationValidator:
    def __init__(self, bedrock):
        self._bedrock = bedrock

    def check_template_only(self, executions: list[TemplateExecution]) -> bool:
        valid_ids = set(TEMPLATE_POOL.keys())
        for exec_item in executions:
            if exec_item.template_id not in valid_ids:
                logger.error(f"Non-template query detected: {exec_item.template_id}")
                return False
        return True

    def topo_faithfulness(
        self,
        verified_claims: list[VerifiedClaim],
        traversal_result: TraversalResult,
    ) -> float:
        answer_relations = set()
        for claim in verified_claims:
            if claim.source_node_id and claim.source_edge_type:
                answer_relations.add((claim.source_node_id, claim.source_edge_type))

        if not answer_relations:
            return 1.0

        graph_relations = set()
        for edge in traversal_result.subgraph_edges:
            graph_relations.add((edge["target"], edge["type"]))

        matched = answer_relations & graph_relations
        return len(matched) / len(answer_relations)

    async def validate(
        self,
        answer_text: str,
        executions: list[TemplateExecution],
        traversal_result: TraversalResult,
    ) -> ValidationResult:
        # Layer 1: Template-only check
        template_only = self.check_template_only(executions)
        templates_used = [e.template_id for e in executions]

        # Layer 2: Claim extraction + source verification
        verified_claims, unverified_claims = await self._verify_sources(
            answer_text, traversal_result
        )
        total_claims = len(verified_claims) + len(unverified_claims)
        source_coverage = (
            len(verified_claims) / total_claims if total_claims > 0 else 1.0
        )

        # Layer 3: Topological faithfulness
        topo_score = self.topo_faithfulness(verified_claims, traversal_result)

        # Determine pass/fail
        passed = template_only and topo_score >= settings.topo_faithfulness_threshold
        if topo_score >= 0.95:
            confidence_label = "high"
        elif topo_score >= 0.85:
            confidence_label = "medium"
        else:
            confidence_label = "low"

        return ValidationResult(
            template_only=template_only,
            templates_used=templates_used,
            verified_claims=verified_claims,
            unverified_claims=unverified_claims,
            source_coverage=source_coverage,
            topo_faithfulness=topo_score,
            answer_relations=len(
                {
                    (c.source_node_id, c.source_edge_type)
                    for c in verified_claims
                    if c.source_node_id and c.source_edge_type
                }
            ),
            graph_relations=len(traversal_result.subgraph_edges),
            matched_relations=int(
                topo_score
                * len(
                    {
                        (c.source_node_id, c.source_edge_type)
                        for c in verified_claims
                        if c.source_node_id and c.source_edge_type
                    }
                )
            ),
            passed=passed,
            confidence_label=confidence_label,
        )

    async def _verify_sources(
        self, answer_text: str, traversal_result: TraversalResult
    ) -> tuple[list[VerifiedClaim], list[str]]:
        claims = await self._extract_claims(answer_text)

        verified = []
        unverified = []
        for claim in claims:
            match = self._find_source_in_subgraph(claim, traversal_result)
            if match:
                verified.append(
                    VerifiedClaim(
                        claim_text=claim,
                        source_node_id=match.get("node_id"),
                        source_edge_type=match.get("edge_type"),
                        source_article=match.get("source_article"),
                        source_text=match.get("source_text"),
                        verified=True,
                    )
                )
            else:
                unverified.append(claim)

        return verified, unverified

    async def _extract_claims(self, answer_text: str) -> list[str]:
        prompt = (
            "다음 답변에서 사실적 주장(Claim)을 추출하세요.\n"
            "각 주장은 검증 가능한 단일 사실이어야 합니다.\n\n"
            f"답변:\n{answer_text}\n\n"
            'JSON 배열로만 출력 (설명 없이):\n["주장1", "주장2", ...]'
        )
        try:
            result = await self._bedrock.invoke_with_retry(
                settings.bedrock_haiku_model_id,
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            raw = result["content"][0]["text"].strip()
            parsed = self._parse_json_array(raw)
            if not isinstance(parsed, list):
                logger.warning(f"Claim extraction returned non-list: {type(parsed)}")
                return []
            return [str(c) for c in parsed]
        except Exception as e:
            logger.warning(f"Claim extraction failed: {e}")
            return []

    @staticmethod
    def _parse_json_array(text: str) -> list:
        """Parse a JSON array from LLM output, tolerating markdown fences."""
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        import re
        fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Extract first [...] from the text
        bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
        if bracket_match:
            try:
                return json.loads(bracket_match.group(0))
            except json.JSONDecodeError:
                pass

        raise json.JSONDecodeError("No valid JSON array found", text, 0)

    def _find_source_in_subgraph(
        self, claim: str, traversal_result: TraversalResult
    ) -> dict | None:
        for node in traversal_result.subgraph_nodes:
            label = node.get("label", "")
            props = node.get("properties", {})
            source_text = props.get("source_text") or label
            if source_text and source_text in claim:
                source_article = props.get("source_article") or props.get(
                    "source_section_id"
                )
                # Find connected edge
                for edge in traversal_result.subgraph_edges:
                    if edge["target"] == node["id"]:
                        return {
                            "node_id": node["id"],
                            "edge_type": edge["type"],
                            "source_article": source_article,
                            "source_text": source_text,
                        }
                return {
                    "node_id": node["id"],
                    "edge_type": None,
                    "source_article": source_article,
                    "source_text": source_text,
                }
        return None
