from pydantic import BaseModel


class GremlinTemplate(BaseModel):
    id: str
    description: str
    intent_type: str | None
    gremlin: str
    params: list[str]
    max_depth: int
    complexity: str  # "simple" | "complex"
    target_node_types: list[str] = []  # If non-empty, fallback only when NONE of these types found


class TemplateExecution(BaseModel):
    template_id: str
    gremlin_query: str
    params: dict[str, str]
    max_depth: int
    entry_node_ids: list[str]


class ChainResult(BaseModel):
    executions: list[TemplateExecution]
    chain_order: list[str]
