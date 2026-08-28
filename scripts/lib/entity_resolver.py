"""U6 — Cross-Document Entity Resolution.

전 문서 GraphReadyData → ResolvedGraph. scope-aware merge/link/keep.
- ① 사전정규화 → ② canonical 매핑 → ③ 유사도(JW+embedding cache) → ④ 병합결정 → ⑤ 관계정규화
- cross-product MERGE 코드 guard(테스트 아닌 invariant)
- evidence는 U4 properties["_evidence"] 합집합. 임베딩은 sync + unique text 캐시(테스트 stub)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from lib.entity_dedup import jaro_winkler  # 기존 재사용


class Decision(str, Enum):
    MERGE = "MERGE"
    LINK = "LINK"
    KEEP_SEPARATE = "KEEP_SEPARATE"


LEGAL_TYPES = {"Regulation"}
GLOBAL_TYPES = {"Product_Category"}
# 그 외는 product scope


def scope_of(entity: dict) -> str:
    t = entity.get("type")
    if t in LEGAL_TYPES:
        return "legal"
    if t in GLOBAL_TYPES:
        return "global"
    return "product"


# ── ① 사전정규화 (whitelist: 공백/단위만, variant 보존) ──
_WS = re.compile(r"\s+")
_AMOUNT = re.compile(r"(\d+)\s*천만(?=원)")


def normalize_label(s: str) -> str:
    t = _WS.sub("", s.strip())
    return t


def normalize_amount(s: str) -> str:
    return _AMOUNT.sub(lambda m: str(int(m.group(1)) * 10_000_000), s)


@dataclass
class ResolvedGraph:
    canonical_entities: list[dict] = field(default_factory=list)
    link_edges: list[dict] = field(default_factory=list)
    kept_separate: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)  # 정규화 + link 포함 (U7 입력)
    merge_report: list[dict] = field(default_factory=list)


class EmbeddingCache:
    """unique text → embedding 캐시. embed_fn 주입(테스트 stub / 실제 boto3 sync)."""
    def __init__(self, embed_fn: Callable[[str], list[float]]):
        self._embed = embed_fn
        self._cache: dict[str, list[float]] = {}

    def get(self, text: str) -> list[float]:
        if text not in self._cache:
            self._cache[text] = self._embed(text)
        return self._cache[text]

    @property
    def calls(self) -> int:
        return len(self._cache)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class ScopePolicy:
    similarity_threshold: float = 0.85
    embedding_threshold: float = 0.90
    link_threshold: float = 0.95   # LINK(SIMILAR_TO)는 거의 동일 라벨만 — cross-product 노이즈 방지


class EntityResolver:
    def __init__(self, policy: ScopePolicy | None = None,
                 canonical_terms: dict | None = None,
                 embedding_cache: EmbeddingCache | None = None):
        self.policy = policy or ScopePolicy()
        self.canonical = canonical_terms or {}
        self.emb = embedding_cache

    # ② canonical 매핑
    def _canonical_label(self, label: str) -> str:
        return self.canonical.get(label, {}).get("canonical_label", label) \
            if isinstance(self.canonical.get(label), dict) else self.canonical.get(label, label)

    # ④ 병합 결정 — 무오병합 코드 guard
    def decide_merge(self, a: dict, b: dict) -> Decision:
        if a.get("type") != b.get("type"):
            return Decision.KEEP_SEPARATE
        sa, sb = scope_of(a), scope_of(b)
        la = normalize_label(self._canonical_label(a.get("label", "")))
        lb = normalize_label(self._canonical_label(b.get("label", "")))

        # legal/global: 동일 라벨이면 MERGE
        if sa in ("legal", "global") and sa == sb and la == lb:
            return Decision.MERGE

        # product: same policy_id + 속성 동등만 MERGE, cross-product는 LINK/KEEP
        if sa == "product" and sb == "product":
            pa = a.get("properties", {}).get("policy_id")
            pb = b.get("properties", {}).get("policy_id")
            sim = self._similarity(a, b)
            if pa and pb and pa == pb and self._props_equiv(a, b):
                decision = Decision.MERGE
            elif sim >= self.policy.link_threshold:
                # LINK는 라벨이 거의 동일할 때만(노이즈 방지). 단순 유사는 KEEP
                decision = Decision.LINK
            else:
                decision = Decision.KEEP_SEPARATE
            # ── 코드 guard (NFR-U6-1): cross-product MERGE 구조적 불가 ──
            if decision == Decision.MERGE and (not pa or pa != pb):
                decision = Decision.KEEP_SEPARATE
            return decision

        return Decision.KEEP_SEPARATE

    def _props_equiv(self, a: dict, b: dict) -> bool:
        ka = {k: v for k, v in a.get("properties", {}).items() if not k.startswith("_") and k != "policy_id"}
        kb = {k: v for k, v in b.get("properties", {}).items() if not k.startswith("_") and k != "policy_id"}
        return ka == kb

    def _similarity(self, a: dict, b: dict) -> float:
        la, lb = a.get("label", ""), b.get("label", "")
        jw = jaro_winkler(normalize_label(la), normalize_label(lb))
        if jw >= self.policy.similarity_threshold or self.emb is None:
            return jw
        # 문자 유사도 애매 → 임베딩(unique text 캐시)
        cos = _cosine(self.emb.get(la), self.emb.get(lb))
        return max(jw, cos if cos >= self.policy.embedding_threshold else jw)

    def resolve(self, docs: list[dict]) -> ResolvedGraph:
        """docs: list[GraphReadyData dict]."""
        entities = [e for d in docs for e in d.get("entities", [])]
        relations = [r for d in docs for r in d.get("relations", [])]
        rg = ResolvedGraph(relations=list(relations))

        # blocking: type+scope 그룹 내에서만 비교
        groups: dict[tuple, list[dict]] = {}
        for e in entities:
            groups.setdefault((e.get("type"), scope_of(e)), []).append(e)

        id_remap: dict[str, str] = {}  # merged id → canonical id
        canonical_by_key: dict[tuple, dict] = {}
        for (etype, scope), group in groups.items():
            for e in group:
                merged_into = None
                for canon in [c for k, c in canonical_by_key.items() if k[0] == etype]:
                    if self.decide_merge(canon, e) == Decision.MERGE:
                        merged_into = canon
                        break
                if merged_into is not None:
                    # evidence 합집합 (U4 계약)
                    ev = merged_into["properties"].setdefault("_evidence", [])
                    ev.extend(e.get("properties", {}).get("_evidence", []))
                    id_remap[e["id"]] = merged_into["id"]
                    rg.merge_report.append({
                        "decision": "MERGE", "before_ids": [e["id"]], "after_id": merged_into["id"],
                        "scope_key": f"{etype}/{scope}", "parent_policy": e.get("properties", {}).get("policy_id"),
                        "similarity_score": round(self._similarity(merged_into, e), 3),
                        "evidence_ids": [x.get("table_id") for x in e.get("properties", {}).get("_evidence", [])],
                    })
                    continue
                # MERGE 안 됨 → LINK or KEEP 판정 (기존 canonical과)
                linked = False
                for canon in [c for k, c in canonical_by_key.items() if k[0] == etype]:
                    if self.decide_merge(canon, e) == Decision.LINK:
                        rg.link_edges.append({"source_id": canon["id"], "type": "SIMILAR_TO",
                                              "target_id": e["id"], "properties": {},
                                              "provenance": {"source_section_id": "", "source_text": "", "confidence": 0.7}})
                        rg.merge_report.append({"decision": "LINK", "before_ids": [e["id"]],
                                                "after_id": canon["id"], "scope_key": f"{etype}/{scope}"})
                        linked = True
                        break
                canonical_by_key[(etype, e["id"])] = e
                if linked:
                    rg.kept_separate.append(e)
                else:
                    rg.canonical_entities.append(e)

        # ⑤ 관계 정규화: endpoint remap + 중복 제거 + link 합치기
        seen = set()
        norm_rels = []
        for r in rg.relations + rg.link_edges:
            s = id_remap.get(r["source_id"], r["source_id"])
            t = id_remap.get(r["target_id"], r["target_id"])
            key = (s, r["type"], t)
            if key in seen:
                continue
            seen.add(key)
            nr = dict(r); nr["source_id"] = s; nr["target_id"] = t
            norm_rels.append(nr)
        rg.relations = norm_rels
        return rg
