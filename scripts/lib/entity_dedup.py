"""Entity deduplication using Jaro-Winkler similarity.

Ported from cdk-app/lambda/shared/entity-registry.ts.
"""

from __future__ import annotations

from .schemas import Entity


class EntityRegistry:
    """Dedup entities within a document using exact + fuzzy matching.

    Strategy:
    1. Exact match: same type + same label → merge
    2. Fuzzy match: same type + Jaro-Winkler ≥ 0.85 → merge
    3. No match: register as new
    """

    def __init__(self, threshold: float = 0.85):
        self._registry: dict[str, Entity] = {}
        self._threshold = threshold

    def register(self, candidate: Entity) -> Entity:
        # 1. Exact match
        for eid, existing in self._registry.items():
            if existing.type == candidate.type and existing.label == candidate.label:
                merged = self._merge(existing, candidate)
                self._registry[eid] = merged
                return merged

        # 2. Fuzzy match
        for eid, existing in self._registry.items():
            if existing.type == candidate.type:
                sim = jaro_winkler(existing.label, candidate.label)
                if sim >= self._threshold:
                    merged = self._merge(existing, candidate)
                    self._registry[eid] = merged
                    return merged

        # 3. New entity
        self._registry[candidate.id] = candidate
        return candidate

    def get_all(self) -> list[Entity]:
        return list(self._registry.values())

    def _merge(self, existing: Entity, incoming: Entity) -> Entity:
        merged_props = {**existing.properties, **incoming.properties}
        merged_confidence = max(
            existing.provenance.confidence,
            incoming.provenance.confidence,
        )
        return existing.model_copy(
            update={
                "properties": merged_props,
                "provenance": existing.provenance.model_copy(
                    update={"confidence": merged_confidence}
                ),
            }
        )


def jaro_winkler(s1: str, s2: str) -> float:
    """Jaro-Winkler similarity between two strings (0..1)."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    jaro = _jaro_similarity(s1, s2)

    # Winkler: boost for common prefix (up to 4 chars)
    prefix_len = 0
    max_prefix = min(4, len(s1), len(s2))
    for i in range(max_prefix):
        if s1[i] == s2[i]:
            prefix_len += 1
        else:
            break

    return jaro + prefix_len * 0.1 * (1 - jaro)


def _jaro_similarity(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0

    max_dist = max(len(s1), len(s2)) // 2 - 1
    if max_dist < 0:
        return 0.0

    s1_matches = [False] * len(s1)
    s2_matches = [False] * len(s2)
    matches = 0

    for i in range(len(s1)):
        start = max(0, i - max_dist)
        end = min(i + max_dist + 1, len(s2))
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    transpositions = 0
    k = 0
    for i in range(len(s1)):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    return (
        matches / len(s1) + matches / len(s2) + (matches - transpositions / 2) / matches
    ) / 3
