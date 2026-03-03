from pydantic import BaseModel


class HybridScore(BaseModel):
    vector_similarity: float
    graph_context: float
    regulation_weight: float
    final_score: float
    weights: dict[str, float]
