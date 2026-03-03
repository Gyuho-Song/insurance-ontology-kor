from app.models.scoring import HybridScore

WEIGHTS = {"vector": 0.3, "graph": 0.5, "regulation": 0.2}


class HybridScorer:
    def score(
        self,
        vector_similarity: float,
        graph_context: float,
        regulation_weight: float,
    ) -> HybridScore:
        final = (
            vector_similarity * WEIGHTS["vector"]
            + graph_context * WEIGHTS["graph"]
            + regulation_weight * WEIGHTS["regulation"]
        )
        return HybridScore(
            vector_similarity=vector_similarity,
            graph_context=graph_context,
            regulation_weight=regulation_weight,
            final_score=round(final, 4),
            weights=WEIGHTS,
        )
