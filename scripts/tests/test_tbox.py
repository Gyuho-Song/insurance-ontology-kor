"""U2 TBoxValidator — example-based tests (pytest).

TDD: 구현(scripts/lib/tbox.py) 전 작성. 초기엔 import 실패(RED).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from lib.tbox import TBoxSpec, TBoxValidator, Severity  # noqa: E402
from lib import schemas  # noqa: E402
from tests.fixtures import tbox_fixtures as fx  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TBOX_PATH = REPO_ROOT / "tbox.yaml"


@pytest.fixture
def spec():
    return TBoxSpec.load(TBOX_PATH)


# ── Load / fail-closed ──────────────────────────────────────
def test_load_ok(spec):
    assert "Policy" in spec.node_types
    assert len(spec.node_types) == 12
    assert len(spec.edge_types) == 17  # 15 + FC9 U6 SAME_AS/SIMILAR_TO

def test_load_missing_file_hard_fail():
    with pytest.raises((FileNotFoundError, OSError)):
        TBoxSpec.load(REPO_ROOT / "no_such_tbox.yaml")

def test_load_uses_safe_load(tmp_path):
    # arbitrary object tag must NOT be constructed (safe_load only)
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 1\nnode_types: !!python/object/apply:os.system ['echo hi']\n")
    with pytest.raises(Exception):
        TBoxSpec.load(bad)

def test_load_broken_yaml_hard_fail(tmp_path):
    bad = tmp_path / "broken.yaml"
    bad.write_text("version: 1\n  bad: : :\n")
    with pytest.raises(Exception):
        TBoxSpec.load(bad)


# ── check_schemas (SSOT 정합성) ─────────────────────────────
def test_check_schemas_matches(spec):
    mismatches = spec.check_schemas(schemas)
    assert mismatches == [], f"tbox.yaml <-> schemas.py mismatch: {mismatches}"


# ── R1~R5 ───────────────────────────────────────────────────
def test_valid_passes(spec):
    rep = TBoxValidator(spec).validate(fx.VALID_ENTITIES, fx.VALID_RELATIONS, profile="report")
    assert [e for e in rep.errors] == []

def test_r1_domain_range_violation(spec):
    rep = TBoxValidator(spec).validate(fx.R1_BAD_ENTITIES, fx.R1_BAD_RELATIONS, profile="report")
    assert any(v.rule == "R1" and v.severity == Severity.ERROR for v in rep.errors)

def test_r2_required_missing(spec):
    rep = TBoxValidator(spec).validate(fx.R2_BAD_ENTITIES, [], profile="report")
    assert any(v.rule == "R2" for v in rep.warnings + rep.errors)

def test_r3_type_mismatch(spec):
    rep = TBoxValidator(spec).validate(fx.R3_BAD_ENTITIES, [], profile="report")
    assert any(v.rule == "R3" and v.severity == Severity.ERROR for v in rep.errors)

def test_r5_provenance_missing(spec):
    rep = TBoxValidator(spec).validate(fx.R5_BAD_ENTITIES, [], profile="report")
    assert any(v.rule == "R5" for v in rep.warnings + rep.errors)


# ── known_exception 강등 + monotone ─────────────────────────
def test_known_exception_demotes(spec):
    rep = TBoxValidator(spec).validate(fx.KNOWN_EXC_ENTITIES, fx.VALID_RELATIONS, profile="report")
    # GOVERNED_BY 부재는 known_exception으로 → errors_excluding_known에 없어야
    assert len(rep.errors_excluding_known) <= len(rep.errors)

def test_has_loan_is_gap_not_known_exception(spec):
    # HAS_LOAN 전역 부재는 gap에 잡히되 known_exceptions 목록엔 없음
    rep = TBoxValidator(spec).validate(fx.VALID_ENTITIES, fx.VALID_RELATIONS, profile="report")
    assert not any(getattr(k, "edge", None) == "HAS_LOAN" for k in rep.known_exceptions)


# ── profile별 pass ──────────────────────────────────────────
def test_report_profile_never_fails(spec):
    rep = TBoxValidator(spec).validate(fx.R1_BAD_ENTITIES, fx.R1_BAD_RELATIONS, profile="report")
    assert rep.profile_passed is True  # report는 비차단

def test_load_gate_fails_on_error(spec):
    rep = TBoxValidator(spec).validate(fx.R1_BAD_ENTITIES, fx.R1_BAD_RELATIONS, profile="load_gate")
    assert rep.profile_passed is False


# ── validate CLI ────────────────────────────────────────────
def test_validate_cli_exit_code(tmp_path):
    graph = tmp_path / "g.json"
    graph.write_text(json.dumps({"entities": fx.R1_BAD_ENTITIES, "relations": fx.R1_BAD_RELATIONS}))
    r = subprocess.run(
        [sys.executable, "-m", "lib.tbox", "validate", "--input", str(graph), "--profile", "load_gate"],
        cwd=str(REPO_ROOT / "scripts"), capture_output=True, text=True,
    )
    assert r.returncode != 0  # load_gate + R1 error → 실패

def test_check_schemas_cli_ok():
    r = subprocess.run(
        [sys.executable, "-m", "lib.tbox", "check-schemas"],
        cwd=str(REPO_ROOT / "scripts"), capture_output=True, text=True,
    )
    assert r.returncode == 0
