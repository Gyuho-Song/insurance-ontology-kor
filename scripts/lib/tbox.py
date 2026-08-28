"""U2 — LPG Graph Contract: TBoxSpec + TBoxValidator (+ CLI).

graph-ready JSON <-> Neptune load 계약. OWL/SHACL 엔진 없음 — 자체 검증.
- TBoxSpec: tbox.yaml(SSOT) 로드. yaml.safe_load만. 로드 실패 = fail-closed(raise).
- TBoxValidator: R1~R5 + known_exception 강등 + profile gate. O(V+E).
- CLI: check-schemas / validate --input --profile
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    KNOWN_EXCEPTION = "KNOWN_EXCEPTION"


@dataclass
class Violation:
    rule: str
    target: str          # entity id 또는 edge 표현
    detail: str
    severity: Severity
    edge: str | None = None


@dataclass
class GapItem:
    entity_id: str
    missing: str         # property 이름 또는 edge label
    category: str        # property | edge | global_absence
    severity: Severity
    evidence_hint: str = ""


@dataclass
class ValidationReport:
    profile: str
    errors: list[Violation] = field(default_factory=list)
    warnings: list[Violation] = field(default_factory=list)
    known_exceptions: list[Violation] = field(default_factory=list)
    gaps: list[GapItem] = field(default_factory=list)
    profile_passed: bool = True

    @property
    def errors_excluding_known(self) -> list[Violation]:
        return self.errors  # errors엔 강등된 known은 이미 제외됨 (아래 로직 참조)

    def summary(self) -> dict:
        return {
            "profile": self.profile,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "known_exceptions": len(self.known_exceptions),
            "gaps": len(self.gaps),
            "profile_passed": self.profile_passed,
        }


@dataclass
class Mismatch:
    kind: str            # node_type | edge_type
    detail: str


_DTYPE_PY = {"float": (int, float), "int": int, "str": str, "list": (list, tuple), "bool": bool,
             # union: LLM이 형을 일관 보장 못하는 자유서술 필드(예: Calculation.variables)
             "str_or_list": (str, list, tuple)}


class TBoxSpec:
    """tbox.yaml(SSOT) 로드 + 조회. 로드 실패는 fail-closed(raise)."""

    def __init__(self, raw: dict):
        self.version = raw.get("version")
        self.node_types: list[str] = list(raw.get("node_types") or [])
        self.edge_types: dict[str, dict] = dict(raw.get("edge_types") or {})
        self.property_schemas: dict[str, dict] = dict(raw.get("property_schemas") or {})
        self.cardinality: list[dict] = list(raw.get("cardinality") or [])
        self.severity_defaults: dict = dict(raw.get("severity_defaults") or {})
        self.known_exceptions: list[dict] = list(raw.get("known_exceptions") or [])
        self.validation_profiles: dict = dict(raw.get("validation_profiles") or {})
        if not self.node_types or not self.edge_types:
            raise ValueError("tbox.yaml invalid: node_types/edge_types required")

    @classmethod
    def load(cls, path: str | Path) -> "TBoxSpec":
        p = Path(path)
        if not p.exists():
            # fail-closed: 계약이 없으면 검증 기준 부재 → hard fail
            raise FileNotFoundError(f"tbox.yaml not found (fail-closed): {p}")
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)  # safe_load only — no arbitrary objects
        if not isinstance(raw, dict):
            raise ValueError(f"tbox.yaml parse failed or not a mapping: {p}")
        return cls(raw)

    def attr_schema(self, node_type: str) -> dict:
        return self.property_schemas.get(node_type, {})

    def check_schemas(self, schemas_module) -> list[Mismatch]:
        """tbox.yaml <-> schemas.py Enum 정합성. mismatch list 반환."""
        out: list[Mismatch] = []
        py_nodes = {t.value for t in schemas_module.EntityType}
        py_edges = {t.value for t in schemas_module.RelationType}
        yaml_nodes = set(self.node_types)
        yaml_edges = set(self.edge_types)
        for n in py_nodes - yaml_nodes:
            out.append(Mismatch("node_type", f"in schemas.py, missing in tbox.yaml: {n}"))
        for n in yaml_nodes - py_nodes:
            out.append(Mismatch("node_type", f"in tbox.yaml, missing in schemas.py: {n}"))
        for e in py_edges - yaml_edges:
            out.append(Mismatch("edge_type", f"in schemas.py, missing in tbox.yaml: {e}"))
        for e in yaml_edges - py_edges:
            out.append(Mismatch("edge_type", f"in tbox.yaml, missing in schemas.py: {e}"))
        return out


class TBoxValidator:
    """R1~R5 검증 + known_exception 강등 + profile gate. O(V+E)."""

    def __init__(self, spec: TBoxSpec):
        self.spec = spec

    def validate(self, entities: list[dict], relations: list[dict], profile: str = "report") -> ValidationReport:
        rep = ValidationReport(profile=profile)
        entity_index = {e["id"]: e for e in entities if "id" in e}

        # R1 domain/range + (edge 단위)
        for rel in relations:
            self._check_r1(rel, entity_index, rep)

        # R2 required, R3 type, R5 provenance (entity 단위)
        for ent in entities:
            self._check_r2_r3(ent, rep)
            self._check_r5(ent, rep)

        # R4 cardinality + gap (entity 단위, edge 집계 기반)
        self._check_cardinality_and_gaps(entities, relations, rep)

        # known_exception 강등: errors에서 화이트리스트 매칭분을 known_exceptions로 이동
        self._apply_known_exceptions(rep)

        # profile gate
        rep.profile_passed = self._eval_profile(rep)
        return rep

    # ── R1 ──
    def _check_r1(self, rel: dict, idx: dict, rep: ValidationReport):
        etype = rel.get("type")
        spec_e = self.spec.edge_types.get(etype)
        if spec_e is None:
            rep.errors.append(Violation("R1", str(etype), f"unknown edge type: {etype}", Severity.ERROR, edge=etype))
            return
        src = idx.get(rel.get("source_id"))
        tgt = idx.get(rel.get("target_id"))
        # FC9 U6: same_type edge (SAME_AS/SIMILAR_TO) — source.type == target.type 검증
        if spec_e.get("same_type"):
            if src and tgt and src.get("type") != tgt.get("type"):
                rep.errors.append(Violation("R1", rel.get("source_id", "?"),
                                  f"{etype} same_type violated: {src.get('type')} != {tgt.get('type')}",
                                  Severity.ERROR, edge=etype))
            return
        if src and src.get("type") not in spec_e.get("domain", []):
            rep.errors.append(Violation("R1", rel.get("source_id", "?"),
                              f"{etype} domain expects {spec_e.get('domain')}, got {src.get('type')}",
                              Severity.ERROR, edge=etype))
        if tgt and tgt.get("type") not in spec_e.get("range", []):
            rep.errors.append(Violation("R1", rel.get("target_id", "?"),
                              f"{etype} range expects {spec_e.get('range')}, got {tgt.get('type')}",
                              Severity.ERROR, edge=etype))

    # ── R2 required + R3 type ──
    def _check_r2_r3(self, ent: dict, rep: ValidationReport):
        schema = self.spec.attr_schema(ent.get("type", ""))
        props = ent.get("properties") or {}
        for name, meta in schema.items():
            val = props.get(name)
            if meta.get("required") and (val is None or val == ""):
                rep.warnings.append(Violation("R2", ent.get("id", "?"),
                                    f"required property missing: {name}", Severity.WARNING))
                rep.gaps.append(GapItem(ent.get("id", "?"), name, "property", Severity.WARNING,
                                        f"{ent.get('type')}.{name}"))
            elif val is not None and val != "":
                py = _DTYPE_PY.get(meta.get("dtype", "str"), str)
                if not isinstance(val, py):
                    rep.errors.append(Violation("R3", ent.get("id", "?"),
                                      f"{name} expects {meta.get('dtype')}, got {type(val).__name__}",
                                      Severity.ERROR))

    # ── R5 provenance ──
    def _check_r5(self, ent: dict, rep: ValidationReport):
        prov = ent.get("provenance") or {}
        if not prov.get("source_text") or not prov.get("source_section_id"):
            rep.warnings.append(Violation("R5", ent.get("id", "?"),
                                "provenance missing source_text/source_section_id", Severity.WARNING))

    # ── R4 cardinality + gaps (edge 부재) ──
    def _check_cardinality_and_gaps(self, entities, relations, rep: ValidationReport):
        # 집계: (in/out, edge_type) per entity
        out_edges: dict[str, set] = {}
        in_edges: dict[str, set] = {}
        for r in relations:
            out_edges.setdefault(r.get("source_id"), set()).add(r.get("type"))
            in_edges.setdefault(r.get("target_id"), set()).add(r.get("type"))
        for rule in self.spec.cardinality:
            node, edge, direction = rule["node"], rule["edge"], rule.get("direction", "out")
            sev = Severity(rule.get("severity", "WARNING"))
            for e in entities:
                if e.get("type") != node:
                    continue
                have = (in_edges if direction == "in" else out_edges).get(e["id"], set())
                if edge not in have:
                    rep.warnings.append(Violation("R4", e["id"],
                                        f"cardinality: {node} expects {direction} {edge}", sev, edge=edge))
                    rep.gaps.append(GapItem(e["id"], edge, "edge", sev, f"{node} missing {edge}"))

    # ── known_exception 강등 (monotone: 강등만) ──
    def _apply_known_exceptions(self, rep: ValidationReport):
        kept_err, kept_warn = [], []
        for pool, keep in ((rep.errors, kept_err), (rep.warnings, kept_warn)):
            for v in pool:
                if self._is_known(v):
                    v.severity = Severity.KNOWN_EXCEPTION
                    rep.known_exceptions.append(v)
                else:
                    keep.append(v)
        rep.errors = kept_err
        rep.warnings = kept_warn

    def _is_known(self, v: Violation) -> bool:
        for ke in self.spec.known_exceptions:
            edge = ke.get("missing") or ke.get("edge")
            if edge and v.edge == edge:
                return True
        return False

    # ── profile gate ──
    def _eval_profile(self, rep: ValidationReport) -> bool:
        prof = self.spec.validation_profiles.get(rep.profile, {"fail_on": []})
        fail_on = prof.get("fail_on", [])
        if "errors_excluding_known" in fail_on and rep.errors:
            return False
        if "warnings" in fail_on and rep.warnings:
            return False
        return True


# ──────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _cmd_check_schemas(args) -> int:
    from lib import schemas
    spec = TBoxSpec.load(_repo_root() / "tbox.yaml")
    mm = spec.check_schemas(schemas)
    if mm:
        for m in mm:
            print(f"MISMATCH [{m.kind}] {m.detail}", file=sys.stderr)
        return 1
    print("check-schemas OK: tbox.yaml <-> schemas.py 일치")
    return 0


def _cmd_validate(args) -> int:
    spec = TBoxSpec.load(_repo_root() / "tbox.yaml")
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rep = TBoxValidator(spec).validate(
        data.get("entities", []), data.get("relations", []), profile=args.profile)
    print(json.dumps(rep.summary(), ensure_ascii=False, indent=2))
    for v in rep.errors:
        print(f"ERROR [{v.rule}] {v.target}: {v.detail}", file=sys.stderr)
    return 0 if rep.profile_passed else 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tbox", description="LPG Graph Contract validator")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-schemas")
    v = sub.add_parser("validate")
    v.add_argument("--input", required=True)
    v.add_argument("--profile", default="report",
                   choices=["report", "phase1_gate", "load_gate", "strict_future"])
    args = p.parse_args(argv)
    if args.cmd == "check-schemas":
        return _cmd_check_schemas(args)
    if args.cmd == "validate":
        return _cmd_validate(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
