from pydantic import BaseModel


class VerifiedClaim(BaseModel):
    claim_text: str
    source_node_id: str | None = None
    source_edge_type: str | None = None
    source_article: str | None = None
    source_text: str | None = None
    verified: bool


class ValidationResult(BaseModel):
    # Layer 1
    template_only: bool
    templates_used: list[str]
    # Layer 2
    verified_claims: list[VerifiedClaim]
    unverified_claims: list[str]
    source_coverage: float
    # Layer 3
    topo_faithfulness: float
    answer_relations: int
    graph_relations: int
    matched_relations: int
    # Overall
    passed: bool
    confidence_label: str  # "high" | "medium" | "low"
