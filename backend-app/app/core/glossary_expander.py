import json
import logging
import re
from pathlib import Path

from app.models.query import ExpandedQuery

logger = logging.getLogger("graphrag.glossary")

DATA_DIR = Path(__file__).parent.parent / "data"


class GlossaryExpander:
    def __init__(self):
        with open(DATA_DIR / "glossary.json", encoding="utf-8") as f:
            data = json.load(f)
        self._synonyms: dict[str, list[str]] = data.get("synonyms", {})
        self._abbreviations: dict[str, str] = data.get("abbreviations", {})

    def expand(self, query: str) -> ExpandedQuery:
        expanded = query
        synonyms_applied = []

        # Abbreviation expansion (P3-C: 단어경계 매칭 — '정보'가 '해약환급금 정보'의 일반어를
        # '정기보험'으로 오확장하던 버그 방지. 약어 앞뒤가 한글/영문/숫자가 아닐 때만 치환).
        for abbr, full in self._abbreviations.items():
            pat = r"(?<![가-힣A-Za-z0-9])" + re.escape(abbr) + r"(?![가-힣A-Za-z0-9])"
            if re.search(pat, expanded):
                expanded = re.sub(pat, full, expanded)
                synonyms_applied.append({"original": abbr, "expanded": full})

        # Synonym expansion
        for term, syns in self._synonyms.items():
            if term in expanded:
                # Add first synonym that's not already present
                for syn in syns:
                    if syn not in expanded:
                        expanded = expanded + f" {syn}"
                        synonyms_applied.append({"original": term, "expanded": syn})
                        break

        # Limit expansion to 3x original
        max_len = len(query) * 3
        if len(expanded) > max_len:
            expanded = expanded[:max_len]

        return ExpandedQuery(
            original=query,
            expanded=expanded,
            synonyms_applied=synonyms_applied,
            embedding_text=expanded,
        )
