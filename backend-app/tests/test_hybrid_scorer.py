"""Tests for HybridScorer (Phase 4E)."""
import pytest


class TestHybridScorer:
    def _make_scorer(self):
        from app.core.hybrid_scorer import HybridScorer

        return HybridScorer()

    def test_score_calculation_default_weights(self):
        scorer = self._make_scorer()
        score = scorer.score(vector_similarity=0.9, graph_context=0.8, regulation_weight=1.0)
        expected = 0.9 * 0.3 + 0.8 * 0.5 + 1.0 * 0.2
        assert abs(score.final_score - expected) < 0.001

    def test_score_with_no_regulation(self):
        scorer = self._make_scorer()
        score = scorer.score(vector_similarity=0.9, graph_context=0.8, regulation_weight=0.0)
        expected = 0.9 * 0.3 + 0.8 * 0.5 + 0.0 * 0.2
        assert abs(score.final_score - expected) < 0.001

    def test_score_with_zero_vector(self):
        scorer = self._make_scorer()
        score = scorer.score(vector_similarity=0.0, graph_context=0.8, regulation_weight=0.0)
        assert score.final_score > 0  # graph_context still contributes

    def test_weights_in_result(self):
        scorer = self._make_scorer()
        score = scorer.score(vector_similarity=0.9, graph_context=0.8, regulation_weight=0.5)
        assert score.weights == {"vector": 0.3, "graph": 0.5, "regulation": 0.2}
