from pydantic import BaseModel


class ConstraintResult(BaseModel):
    edge_type: str
    blocked: bool
    reason: str | None = None
    regulation_id: str | None = None
    condition_met: bool | None = None


class TraversalPath(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    constraints: list[ConstraintResult]
    depth: int


class TraversalResult(BaseModel):
    paths: list[TraversalPath]
    subgraph_nodes: list[dict]
    subgraph_edges: list[dict]
    traversal_events: list[dict]
    total_hops: int
    constraints_found: int
