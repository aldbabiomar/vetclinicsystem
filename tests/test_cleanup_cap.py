"""
"Clean Up" writes off part of a bill. Two rules bound it — a per-bill ceiling
and the remaining balance — and until 2026-09-10 neither had a single test in
either app.

That was found by extracting the checks into one helper and then removing one
of them: nothing failed. Four copies of a rule, none of them covered, is worse
than one copy uncovered, because it also hides how far the copies had drifted.

The rules are the same under both money settings, with the setting's values:
the cap (1.000 JOD, 1,000 IQD), and the smallest amount a person can enter
(0.001 JOD, 1 IQD). Every test here runs under the run's setting.
"""
import source_files
import pytest

from decimal import Decimal

from vcs import money
from vcs.domain.payments import cleanup_error
from conftest import amount


def cap():
    return money.current().cleanup_cap


def step():
    """The smallest amount a person can enter: 0.001 JOD, 1 IQD."""
    return Decimal(1).scaleb(-money.current().minor_units)


# ---------------------------------------------------------------------------
# GUARDS
# ---------------------------------------------------------------------------

def test_a_negative_write_off_is_refused():
    """A negative Clean Up would ADD to what the client owes, under a control
    labelled as a write-off."""
    assert "negative" in cleanup_error(-step(), 0, amount("100.000"))


def test_a_write_off_over_the_cap_is_refused():
    assert "exceed" in cleanup_error(cap() + step(), 0, amount("100.000"))


def test_the_cap_accumulates_across_submissions():
    """GUARD. A bill can be cleaned up more than once; the ceiling is on the
    total, not on each submission. Checking only the new amount would let an
    unlimited write-off through in small pieces."""
    assert cleanup_error(cap(), cap(), amount("100.000")) is not None
    assert cleanup_error(step(), cap(), amount("100.000")) is not None


def test_a_write_off_larger_than_the_balance_is_refused():
    """GUARD. Writing off more than is owed would turn a bill negative."""
    err = cleanup_error(amount("0.500"), 0, amount("0.250"))
    assert err is not None and "remaining balance" in err


# ---------------------------------------------------------------------------
# CONTROLS — the feature still works
# ---------------------------------------------------------------------------

def test_an_ordinary_write_off_is_allowed():
    """Without this, 'refuse everything' passes every guard above."""
    assert cleanup_error(amount("0.250"), 0, amount("100.000")) is None


def test_exactly_the_cap_is_allowed():
    """Boundary: the rule is 'may not exceed', not 'must be under'."""
    assert cleanup_error(cap(), 0, amount("100.000")) is None


def test_exactly_the_balance_is_allowed():
    """Boundary: clearing the remainder exactly is the common case."""
    assert cleanup_error(amount("0.250"), 0, amount("0.250")) is None


def test_zero_is_allowed():
    """Every payment form posts this field whether or not it was used."""
    assert cleanup_error(0, 0, amount("100.000")) is None


def test_a_new_sale_has_nothing_to_accumulate_against():
    """CONTROL for POS, which passes existing_amount=0 — a brand-new sale has
    no prior Clean Up, unlike the three surfaces paid off over time."""
    assert cleanup_error(cap(), 0, amount("100.000")) is None


# ---------------------------------------------------------------------------
# The helper is actually wired to a route
# ---------------------------------------------------------------------------

def test_the_helper_is_used_by_every_payment_surface():
    """GUARD. The rules being right is worth nothing if a surface still
    carries its own copy — which is how the four drifted in the first place.

    The check lives in vcs/domain/payments.py. A visit, an inpatient case and
    a boarding stay reach it through payments.record_payment(), the one
    function that records their payments; the point of sale calls it itself.
    Seam rule 18 (tests/test_seam_rules.py) holds the same thing from the
    other side: nothing else compares a Clean Up against a cap or a balance."""
    import ast

    module = source_files.module("payments").read_text(encoding="utf-8")
    functions = {n.name: ast.get_source_segment(module, n) for n in ast.parse(module).body
                 if isinstance(n, ast.FunctionDef)}
    assert "cleanup_error(" in functions["record_payment"], "record_payment() no longer checks the Clean Up"
    sales = source_files.blueprint("sales").read_text(encoding="utf-8")
    checkout = sales.split("def pos_checkout(", 1)[1].split("\n@bp.route", 1)[0]
    assert "payments.cleanup_error(" in checkout, "the point of sale no longer checks the Clean Up"
    src = "\n".join(p.read_text(encoding="utf-8") for p in
                    [*source_files.web_modules(), source_files.module("core"), *source_files.domain_modules()])
    assert src.count("Clean Up can't exceed the remaining balance") == 1, (
        "more than one copy of the balance message — it should live only in payments.cleanup_error()")
    assert "remaining balance" in functions["cleanup_error"]
