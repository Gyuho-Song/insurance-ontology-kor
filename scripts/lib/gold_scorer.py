"""U3 — GoldScorer: gold fact set vs ExtractionOutput(GraphReadyData) 채점.

fact-level metric (FC9 핵심):
- entity_f1 / relation_f1
- numeric_accuracy: 수치 속성을 숫자로 정확히 뽑았나
- boundary_accuracy: inclusive 경계 정답
- provenance_coverage: table_id/row 등 보존

gate (FD §acceptance):
  passed = entity_f1>=0.85 ∧ relation_f1>=0.80 ∧ numeric>=0.95 ∧ boundary==1.0 ∧ provenance==1.0

gold는 self-contained: gold/_schema.json(required_props/tolerance)을 읽어 tbox 재읽기 없음.
strict JSONL (주석/trailing comma 금지).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── label 정규화 (whitelist: 공백/단위만, variant 보존) ──
_UNIT_RE = re.compile(r"\s+")


def normalize_label(s: str) -> str:
    return _UNIT_RE.sub("", s.strip())


@dataclass
class GoldMeta:
    schema_version: int
    tbox_sha256: str
    required_props: dict
    tolerance: dict


@dataclass
class ScoreReport:
    entity_f1: float = 0.0
    relation_f1: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    fact_accuracy: dict = field(default_factory=dict)
    by_category: dict = field(default_factory=dict)
    passed: bool = False
    details: list = field(default_factory=list)


def _f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 1.0
    r = tp / (tp + fn) if (tp + fn) else 1.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


class GoldScorer:
    def __init__(self, meta: GoldMeta):
        self.meta = meta

    @classmethod
    def load_gold(cls, gold_dir: str | Path) -> tuple["GoldScorer", list[dict]]:
        d = Path(gold_dir)
        schema_path = d / "_schema.json"
        if not schema_path.exists():
            raise FileNotFoundError(f"gold/_schema.json 없음 (채점 기준 부재): {schema_path}")
        m = json.loads(schema_path.read_text(encoding="utf-8"))
        meta = GoldMeta(m["schema_version"], m["tbox_sha256"],
                        m.get("required_props", {}), m.get("tolerance", {}))
        docs = []
        for jf in sorted(d.glob("*.jsonl")):
            for line in jf.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    docs.append(json.loads(line))  # strict: 주석 있으면 raise
        return cls(meta), docs

    def _num_eq(self, a, b) -> bool:
        if isinstance(a, float) or isinstance(b, float):
            return abs(float(a) - float(b)) <= self.meta.tolerance.get("numeric_rate", 0.001)
        return a == b

    def score(self, gold_docs: list[dict], extracted_by_doc: dict[str, dict]) -> ScoreReport:
        """gold_docs: list[GoldDoc], extracted_by_doc: {document_id: GraphReadyData dict}."""
        e_tp = e_fp = e_fn = 0
        r_tp = r_fp = r_fn = 0
        num_total = num_ok = 0
        bnd_total = bnd_ok = 0
        prov_total = prov_ok = 0
        by_cat: dict = {}
        details = []

        for gd in gold_docs:
            doc_id = gd["document_id"]
            ext = extracted_by_doc.get(doc_id)
            ext_entities = (ext or {}).get("entities", [])
            # 엔티티 인덱스: (type, normalized label) → extracted entity
            ext_idx: dict = {}
            for e in ext_entities:
                ext_idx[(e["type"], normalize_label(e.get("label", "")))] = e

            gid_to_match: dict = {}  # gold entity_id → matched ext id
            for ge in gd.get("entities", []):
                cat = ge.get("category", "?")
                bc = by_cat.setdefault(cat, {"e_tp": 0, "e_fp": 0, "e_fn": 0, "r_tp": 0, "r_fp": 0, "r_fn": 0})
                key = (ge["type"], normalize_label(ge.get("label", "")))
                me = ext_idx.get(key)
                if me and self._props_match(ge.get("properties", {}), me.get("properties", {})):
                    e_tp += 1; bc["e_tp"] += 1
                    gid_to_match[ge["entity_id"]] = me["id"]
                    # fact-level
                    self._tally_facts(ge, me, counters := {})
                    num_total += counters.get("num_total", 0); num_ok += counters.get("num_ok", 0)
                    bnd_total += counters.get("bnd_total", 0); bnd_ok += counters.get("bnd_ok", 0)
                    prov_total += 1; prov_ok += 1 if self._prov_ok(me) else 0
                else:
                    e_fn += 1; bc["e_fn"] += 1
                    prov_total += 1
                    details.append({"doc": doc_id, "miss_entity": ge["entity_id"]})

            # extracted 중 gold에 없는 것 = FP
            matched_ext_ids = set(gid_to_match.values())
            for e in ext_entities:
                if e["id"] not in matched_ext_ids:
                    e_fp += 1

            # 관계: target_id resolve
            for gr in gd.get("relations", []):
                cat = gr.get("category", "?")
                bc = by_cat.setdefault(cat, {"e_tp": 0, "e_fp": 0, "e_fn": 0, "r_tp": 0, "r_fp": 0, "r_fn": 0})
                tgt_ext = gid_to_match.get(gr["target_id"])
                found = any(
                    r.get("source_id") == gr["source_id"] and r.get("type") == gr["type"]
                    and r.get("target_id") == tgt_ext
                    for r in (ext or {}).get("relations", [])
                ) if tgt_ext else False
                if found:
                    r_tp += 1; bc["r_tp"] += 1
                else:
                    r_fn += 1; bc["r_fn"] += 1

        ep, er, ef = _f1(e_tp, e_fp, e_fn)
        rp, rr, rf = _f1(r_tp, r_fp, r_fn)
        fact = {
            "numeric_accuracy": (num_ok / num_total) if num_total else 1.0,
            "boundary_accuracy": (bnd_ok / bnd_total) if bnd_total else 1.0,
            "provenance_coverage": (prov_ok / prov_total) if prov_total else 1.0,
        }
        passed = (ef >= 0.85 and rf >= 0.80 and fact["numeric_accuracy"] >= 0.95
                  and fact["boundary_accuracy"] == 1.0 and fact["provenance_coverage"] == 1.0)
        return ScoreReport(entity_f1=ef, relation_f1=rf, precision=ep, recall=er,
                           fact_accuracy=fact, by_category=by_cat, passed=passed, details=details)

    def _props_match(self, gold_props: dict, ext_props: dict) -> bool:
        for k, v in gold_props.items():
            if k.endswith("_inclusive"):
                continue  # boundary는 _tally_facts에서
            if isinstance(v, (int, float)):
                if k not in ext_props or not self._num_eq(v, ext_props[k]):
                    return False
        return True

    def _tally_facts(self, ge: dict, me: dict, counters: dict):
        gp, ep = ge.get("properties", {}), me.get("properties", {})
        for k, v in gp.items():
            if isinstance(v, (int, float)) and not k.endswith("_inclusive"):
                counters["num_total"] = counters.get("num_total", 0) + 1
                if k in ep and self._num_eq(v, ep[k]):
                    counters["num_ok"] = counters.get("num_ok", 0) + 1
            if k.endswith("_inclusive"):
                counters["bnd_total"] = counters.get("bnd_total", 0) + 1
                if ep.get(k) == v:
                    counters["bnd_ok"] = counters.get("bnd_ok", 0) + 1

    @staticmethod
    def _prov_ok(ext_entity: dict) -> bool:
        prov = ext_entity.get("provenance", {})
        return bool(prov.get("table_id") and prov.get("row_idx") is not None)
