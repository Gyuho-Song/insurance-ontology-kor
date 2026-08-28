"""U4 — PBT-03: _extract_numeric idempotent + invariant."""
import sys
from pathlib import Path
from hypothesis import given, settings, strategies as st
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.table_mapper import _extract_numeric

@settings(max_examples=100, deadline=None)
@given(lo=st.integers(0, 99), hi=st.integers(0, 99))
def test_age_range_idempotent_and_correct(lo, hi):
    text = f"만 {lo} 세 ~{hi} 세"
    r1 = _extract_numeric(text)
    r2 = _extract_numeric(text)
    assert r1 == r2  # idempotent
    fd = {f.field: f.value for f in r1}
    assert fd.get("min_age") == lo and fd.get("max_age") == hi

@settings(max_examples=80, deadline=None)
@given(pct=st.integers(0, 100))
def test_threshold_extracted(pct):
    facts = _extract_numeric(f"{pct}% 이상")
    th = [f for f in facts if f.field == "disability_threshold"]
    assert th and th[0].value == pct
