from pydantic import BaseModel, Field, field_validator


class SourceReference(BaseModel):
    node_id: str
    node_type: str
    node_label: str
    source_article: str
    source_text: str


class ChatRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1, max_length=50)
    persona: str = Field(..., pattern=r"^(consultant|customer|underwriter|presenter)$")
    mock_mode: bool = False
    mydata_consent: dict | None = None  # {customer_id: str, consented: bool}
    rag_mode: str = Field(default="graphrag", pattern=r"^(graphrag|naive|comparison)$")

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v):
        for msg in v:
            if msg.get("role") == "user" and "content" in msg and len(msg["content"]) > 2000:
                raise ValueError("Message content exceeds 2000 character limit")
        return v


class MessageAnnotation(BaseModel):
    sources: list[SourceReference]
    traversalEvents: list[dict]
    subgraph: dict
    topoFaithfulness: float | None = None
    templatesUsed: list[str]
    validationStatus: str = "completed"
