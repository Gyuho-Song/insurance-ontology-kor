from pydantic import BaseModel


class ExpandedQuery(BaseModel):
    original: str
    expanded: str
    synonyms_applied: list[dict]
    embedding_text: str


class EntryNode(BaseModel):
    node_id: str
    node_type: str
    node_label: str
    score: float
    text_content: str
