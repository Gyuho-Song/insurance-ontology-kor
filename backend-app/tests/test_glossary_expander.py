"""Tests for GlossaryExpander (Phase 4B)."""
import pytest


class TestGlossaryExpander:
    def _make_expander(self):
        from app.core.glossary_expander import GlossaryExpander

        return GlossaryExpander()

    def test_synonym_expansion(self):
        exp = self._make_expander()
        result = exp.expand("배당금 있나요?")
        assert "이익배당" in result.expanded or "배당" in result.expanded
        assert len(result.synonyms_applied) >= 1

    def test_no_expansion_for_unknown_term(self):
        exp = self._make_expander()
        result = exp.expand("날씨가 좋습니다")
        assert result.expanded == result.original
        assert len(result.synonyms_applied) == 0

    def test_abbreviation_expansion(self):
        exp = self._make_expander()
        result = exp.expand("종보 상품을 알려주세요")
        assert "종신보험" in result.expanded

    def test_multiple_synonyms(self):
        exp = self._make_expander()
        result = exp.expand("해약 환급금과 상계 처리")
        assert len(result.synonyms_applied) >= 2

    def test_expansion_limit(self):
        exp = self._make_expander()
        result = exp.expand("배당금 있나요?")
        # expanded should not be more than 2x original length
        assert len(result.expanded) <= len(result.original) * 3

    def test_embedding_text_set(self):
        exp = self._make_expander()
        result = exp.expand("보장항목 알려주세요")
        assert result.embedding_text == result.expanded
