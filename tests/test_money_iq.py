"""
Money-path tests under the IQ money setting (Iraqi dinar).

Ported from the predecessor IQ app's own test_money.py, whose assertions are
kept one for one — only the API they call changed, because IQ's rules are no
longer separate code: they are money.py's single set of rules applied with
IQ's numbers (whole dinars, a 250-dinar cash unit).

The IQ model every assertion below depends on:
  - Every *payable* figure (total, balance, change, refund) is a multiple of
    the 250-dinar note.
  - Rounding is half-up, NOT Python's default banker's rounding.
  - A non-zero bill must never round down to "free" (a 100% discount is a
    deliberate waiver and stays exempt).
  - Change and refunds round DOWN — money leaving the clinic never exceeds
    what is owed.

The JO counterparts are in test_money.py and test_money_routes.py (JO is the
default setting for the suite); test_money_spec.py holds the rules side by
side for both.
"""
from decimal import Decimal as D

import pytest

from vcs.web import core
from vcs.domain import billing, dates, display
from vcs import money
pytestmark = pytest.mark.money("IQ")

NOTE = money.IQ.cash_unit


# ---------------------------------------------------------------------------
# parse_money — the front door
# ---------------------------------------------------------------------------

def test_parse_money_blank_is_none():
    assert core.parse_money("") is None
    assert core.parse_money("   ") is None
    assert core.parse_money(None) is None


def test_parse_money_blank_but_required_raises():
    with pytest.raises(core.BadNumber):
        core.parse_money("", required=True)


def test_parse_money_accepts_ordinary_amounts():
    assert core.parse_money("10000") == 10000
    assert core.parse_money("0") == 0
    assert core.parse_money(" 250 ") == 250


def test_parse_money_rounds_to_whole_dinars():
    """IQ amounts are entered in whole dinars: a fraction is rounded at the
    door (half-up), so every check downstream sees what will be stored."""
    assert core.parse_money("1234.4") == 1234
    assert core.parse_money("1234.5") == 1235
    assert core.parse_money("0.4") == 0


@pytest.mark.parametrize("hostile", ["nan", "NaN", "inf", "-inf", "Infinity"])
def test_parse_money_rejects_nan_and_infinity(hostile):
    with pytest.raises(core.BadNumber):
        core.parse_money(hostile)


@pytest.mark.parametrize("garbage", ["abc", "1,000", "10.0.0", "$50", "12 34"])
def test_parse_money_rejects_non_numeric(garbage):
    with pytest.raises(core.BadNumber):
        core.parse_money(garbage)


@pytest.mark.parametrize("arabic,expected", [("١٠٠", 100), ("٢٥٠", 250), ("1٠0", 100)])
def test_parse_money_accepts_arabic_indic_digits(arabic, expected):
    """Decimal() parses Arabic-Indic digits, so a clinic can type ٢٥٠ into a
    price field and get 250. Locked in so restricting input to ASCII later is
    a deliberate decision with a failing test to justify it."""
    assert core.parse_money(arabic) == expected


def test_parse_money_allows_negative_by_design():
    """has_negative() is the separate guard where negative is never valid."""
    assert core.parse_money("-500") == -500


def test_parse_money_rejects_absurd_values():
    """The IQ bound is a typo guard (~760,000 USD), not a column limit."""
    cap = money.IQ.max_amount
    assert core.parse_money(str(cap)) == cap
    with pytest.raises(core.BadNumber):
        core.parse_money(str(cap + 1))
    with pytest.raises(core.BadNumber):
        core.parse_money("1000000000000000000")


def test_the_iq_bound_fits_the_money_column():
    """Every money column is NUMERIC(15,3): 12 digits before the point. The
    largest IQ amount must fit, or the typo guard would let through a value
    that then fails in Postgres."""
    assert money.IQ.max_amount < D(10) ** 12


def test_negative_values_are_bounded_by_magnitude_too():
    assert core.parse_money("-1000") == -1000
    with pytest.raises(core.BadNumber):
        core.parse_money("-1000000000000000000")


# ---------------------------------------------------------------------------
# Rounding to the note — the core of the IQ money setting
# ---------------------------------------------------------------------------

def test_round_cash_leaves_exact_multiples_alone():
    for v in (0, 250, 500, 1000, 12_750):
        assert money.round_cash(D(v)) == v


def test_round_cash_is_half_up_not_bankers():
    """Python's round() breaks an exact .5 tie toward the EVEN multiple, so
    125 would round to 0 ("free") while 375 rounds to 500 — the direction
    decided by parity, not intent."""
    assert money.round_cash(D(125)) == 250
    assert money.round_cash(D(375)) == 500
    assert money.round_cash(D(625)) == 750


def test_round_cash_nearest_rounds_both_ways():
    assert money.round_cash(D(124)) == 0
    assert money.round_cash(D(126)) == 250
    assert money.round_cash(D(374)) == 250
    assert money.round_cash(D(376)) == 500


def test_round_cash_down_never_returns_more():
    """Used for CHANGE and REFUNDS: rounding up would have the clinic hand
    back more than it owes, every single time."""
    for v in (1, 124, 125, 249, 250, 251, 9999):
        assert money.round_cash(D(v), "down") <= v


def test_is_cash_payable():
    assert money.is_cash_payable(D(250)) is True
    assert money.is_cash_payable(D(0)) is True
    assert money.is_cash_payable(D(251)) is False


def test_fmt_money_uses_thousands_separator_and_no_decimals():
    assert display.fmt_money(D(1_234_567)) == "1,234,567"
    assert display.fmt_money(D(0)) == "0"
    assert display.fmt_money(None) == "—"


def test_change_is_rounded_down_to_a_note():
    assert money.change_due(D(1100), D(800)) == 250
    assert money.change_due(D(1000), D(750)) == 250
    assert money.change_due(D(750), D(750)) == 0
    assert money.change_due(D(700), D(750)) == 0   # short is not negative change


def test_a_refund_under_one_note_pays_one_note_when_refundable():
    """SIMULATION_AUDIT F3: rounding down must never settle a real return at
    zero — the customer would hand the goods back and be paid nothing."""
    assert money.refund_payout(D(100), D(5000)) == (D(250), None)


def test_a_refund_is_refused_when_not_even_one_note_is_refundable():
    payout, why = money.refund_payout(D(100), D(100))
    assert payout is None and why == "no_refundable_unit"


def test_refunds_round_down():
    assert money.refund_payout(D(1100), D(5000)) == (D(1000), None)


# ---------------------------------------------------------------------------
# compute_bill_totals — the single entry point for every bill
# ---------------------------------------------------------------------------

def _totals(subtotal, discount_percent, paid, cleanup_amount=0, *, discountable_subtotal=None):
    """compute_bill_totals() with discountable_subtotal defaulting to the
    whole subtotal (the case every test below asserts). The real function has
    no such default on purpose — see its docstring and seam rule 6."""
    subtotal, paid, cleanup_amount = D(subtotal), D(paid), D(cleanup_amount)
    total, paid_, balance, status, _pre = billing.compute_bill_totals(
        subtotal, D(discount_percent), paid, cleanup_amount,
        discountable_subtotal=(subtotal if discountable_subtotal is None else D(discountable_subtotal)))
    return total, paid_, balance, status


def test_bill_unpaid():
    assert _totals(10_000, 0, 0) == (10_000, 0, 10_000, "Unpaid")


def test_bill_applies_percentage_discount():
    total, _, balance, _ = _totals(10_000, 10, 0)
    assert total == 9_000 and balance == 9_000


def test_bill_full_waiver_is_free_and_not_floored():
    total, _, _, status = _totals(10_000, 100, 0)
    assert total == 0 and status == "N/A"


@pytest.mark.parametrize("subtotal", [1, 50, 100, 124, 125])
def test_bill_never_presents_a_real_charge_as_free(subtotal):
    total, _, _, status = _totals(subtotal, 0, 0)
    assert total == NOTE and status == "Unpaid"


def test_bill_fully_paid():
    _, _, balance, status = _totals(10_000, 0, 10_000)
    assert balance == 0 and status == "Fully Paid"


def test_bill_partially_paid():
    _, _, balance, status = _totals(10_000, 0, 5_000)
    assert balance == 5_000 and status == "Partially Paid"


def test_a_remainder_under_half_a_note_reads_as_paid():
    """9,900 paid on a 10,000 bill leaves 100 — not collectable in notes, so
    the balance rounds to 0 and the bill is settled."""
    _, _, balance, status = _totals(10_000, 0, 9_900)
    assert balance == 0 and status == "Fully Paid"


def test_bill_overpayment_reads_as_paid_with_negative_balance():
    _, _, balance, status = _totals(10_000, 0, 10_250)
    assert balance == -250 and status == "Fully Paid"


def test_cleanup_writes_off_after_rounding():
    assert _totals(10_000, 0, 0, cleanup_amount=1_000)[0] == 9_000


def test_cleanup_cannot_drive_a_bill_negative():
    total, _, _, status = _totals(500, 0, 0, cleanup_amount=1_000)
    assert total == 0 and status == "N/A"


def test_discount_and_cleanup_apply_in_that_order():
    total = _totals(10_000, 10, 0, cleanup_amount=1_000)[0]
    assert total == 8_000          # 10000 -10% = 9000, then -1000


def test_cleanup_cap_is_one_thousand_dinars():
    assert money.IQ.cleanup_cap == 1_000


def test_cleanup_error_uses_the_iq_cap():
    from vcs.web.core import cleanup_amount_error
    assert cleanup_amount_error(D(1000), D(0), D(50_000)) is None
    assert cleanup_amount_error(D(1001), D(0), D(50_000)) is not None
    assert cleanup_amount_error(D(250), D(900), D(50_000)) is not None


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subtotal", [0, 1, 137, 999, 10_000, 33_333, 1_000_000])
@pytest.mark.parametrize("discount", [0, 7, 33, 50, 99, 100])
def test_every_payable_figure_lands_on_a_real_note(subtotal, discount):
    total, _, balance, _ = _totals(subtotal, discount, 0)
    assert total % NOTE == 0
    assert balance % NOTE == 0


@pytest.mark.parametrize("subtotal", [0, 250, 10_000])
@pytest.mark.parametrize("cleanup", [0, 250, 1_000, 99_999])
def test_total_is_never_negative(subtotal, cleanup):
    assert _totals(subtotal, 0, 0, cleanup_amount=cleanup)[0] >= 0


@pytest.mark.parametrize("subtotal", [250, 1_000, 10_000, 77_777])
def test_paying_the_stated_total_always_settles_the_bill(subtotal):
    total = _totals(subtotal, 0, 0)[0]
    _, _, balance, status = _totals(subtotal, 0, total)
    assert status == "Fully Paid" and balance <= 0


def test_a_float_is_refused_outright():
    """The predecessor IQ app ran on float and relied on the 250-rounding to
    scrub binary dust (0.1 + 0.2 != 0.3). Money is Decimal everywhere now; a
    float reaching the money rules is a bug and must fail loudly."""
    with pytest.raises(TypeError):
        money.payable(0.1 + 0.2)


def test_status_is_always_one_of_the_four_known_values():
    seen = set()
    for subtotal in (0, 125, 10_000):
        for paid in (0, 100, 10_000, 99_999):
            seen.add(_totals(subtotal, 0, paid)[3])
    assert seen <= {"N/A", "Unpaid", "Partially Paid", "Fully Paid"}


def test_regression_exactly_half_a_note_rounds_up_not_to_free():
    assert money.round_cash(D(125)) != 0
    assert _totals(125, 0, 0)[0] == 250


def test_regression_as_date_validates_the_whole_value_not_a_prefix():
    with pytest.raises(ValueError):
        dates.as_date("2026-08-25garbage")
    assert dates.as_date("2026-08-25").isoformat() == "2026-08-25"
    assert dates.as_date("2026-08-25T02:00:00").isoformat() == "2026-08-25"
