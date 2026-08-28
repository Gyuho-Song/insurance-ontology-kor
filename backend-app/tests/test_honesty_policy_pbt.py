"""U5 — PBT-03: eval_boundary inclusive invariant + decide idempotent."""
from hypothesis import given, settings, strategies as st
from app.core.honesty_policy import HonestyPolicy, TBoxSnapshot, AttributeConstraint, BoundaryQuery

P = HonestyPolicy(TBoxSnapshot({}))

@settings(max_examples=100, deadline=None)
@given(val=st.floats(0, 200, allow_nan=False), lim=st.floats(0, 200, allow_nan=False))
def test_inclusive_boundary_invariant(val, lim):
    c_incl = AttributeConstraint("max_age", max=lim, inclusive=True)
    c_excl = AttributeConstraint("max_age", max=lim, inclusive=False)
    q = BoundaryQuery("max_age", val)
    # inclusive: val<=lim, exclusive: val<lim. val==lim일 때만 다름
    assert P.eval_boundary(c_incl, q) == (val <= lim)
    assert P.eval_boundary(c_excl, q) == (val < lim)

@settings(max_examples=50, deadline=None)
@given(val=st.floats(0, 200, allow_nan=False))
def test_eval_idempotent(val):
    c = AttributeConstraint("max_age", max=80, inclusive=True)
    q = BoundaryQuery("max_age", val)
    assert P.eval_boundary(c, q) == P.eval_boundary(c, q)
