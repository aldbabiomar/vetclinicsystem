"""
A payment against a bill: one function records it, whichever kind of bill
it is -- a visit, an inpatient case or a boarding stay.

The three payment routes each used to carry their own copy of this
sequence, and the copies drifted (docs/SEAM_RULES.md, and
docs/plans/PAYMENT_CENTRALIZATION_PLAN.md §2.2). The rules live here now;
a route parses its form, calls record_payment() and shows the answer.

What differs between the kinds is data, in KINDS below. Nothing here reads
the request or the session, and nothing here commits: the route passes what
it parsed and who is signed in, and commits once (docs/decisions/0003).
A refusal is a PaymentRefused carrying a messages.Msg, raised before
anything is written, so the route can show the form again as it stands.
"""
from dataclasses import dataclass
from typing import Callable

from vcs import auth
from vcs import clock
from vcs import money
from vcs.domain import billing
from vcs.messages import Amount, Currency, Msg, N_

# How money can change hands, as stored: every form that records a payment
# offers exactly these, and the database refuses anything else.
METHODS = ("Cash", "Card", "Transfer")


class PaymentRefused(Exception):
    """The submission was refused and nothing was written. `message` is a
    messages.Msg; the route shows it with core.flash()."""

    def __init__(self, message):
        super().__init__(str(message))
        self.message = message


class BillNotFound(PaymentRefused):
    """There is no such visit, case or stay."""


@dataclass(frozen=True)
class Recorded:
    payment_id: int
    warn_cash_note: bool        # paid in Cash, and not an amount that notes add up to


@dataclass(frozen=True)
class Kind:
    """Everything about a kind of bill that a payment needs to know."""
    table: str                  # the row a payment locks
    column: str                 # payments.<column> points at it
    bill_table: str             # where the bill's discount and Clean Up are stored
    bill_key: str               # ... keyed by this column
    summary: Callable           # (db, id) -> the bill's totals
    not_found: str
    over_balance: str


KINDS = {
    "visit": Kind(
        table="visits", column="visit_id", bill_table="billing", bill_key="visit_id",
        summary=billing.visit_billing_summary,
        not_found=N_("Visit not found."),
        over_balance=N_("That's more than the remaining balance of %(fmt_money)s %(currency)s on this visit.")),
    "inpatient": Kind(
        table="inpatient_cases", column="inpatient_case_id", bill_table="inpatient_cases", bill_key="id",
        summary=billing.inpatient_billing_summary,
        not_found=N_("Inpatient case not found."),
        over_balance=N_("That's more than the remaining balance of %(fmt_money)s %(currency)s on this case.")),
    "boarding": Kind(
        table="boarding_sessions", column="boarding_id", bill_table="boarding_sessions", bill_key="id",
        summary=billing.boarding_billing_summary,
        not_found=N_("Boarding session not found."),
        over_balance=N_("That's more than the remaining balance of %(fmt_money)s %(currency)s on this stay.")),
}
assert set(KINDS) == set(billing.BILL_KINDS)


# ---------------------------------------------------------------------------
# The checks. Each returns a Msg, or None when there is nothing wrong.
# ---------------------------------------------------------------------------
def discount_error(percent, cap):
    """A staff discount must be between 0 and the role's cap."""
    if percent > cap or percent < 0:
        return Msg(N_("Discount must be between 0%% and %(cap)s%% for your role."), cap=cap)
    return None


def cleanup_error(new_amount, existing_amount, balance):
    """A Clean Up must not be negative, must keep the bill's Clean Up within
    the money setting's cap (1,000 under IQ, 1.000 under JO) across every
    submission, and must not be more than `balance` -- what is owed once
    this submission's discount is counted."""
    cap = money.require().cleanup_cap
    if new_amount < 0:
        return Msg(N_("Clean Up amount can't be negative."))
    if existing_amount + new_amount > cap:
        return Msg(N_("Clean Up on this bill can't exceed %(cap)s %(currency)s in total."),
                   cap=Amount(cap), currency=Currency())
    if new_amount > balance:
        return Msg(N_("Clean Up can't exceed the remaining balance."))
    return None


# ---------------------------------------------------------------------------
# The one writer of payments
# ---------------------------------------------------------------------------
def record_payment(db, kind, bill_id, *, amount, method, user_id, cleanup_amount=0, notes=None,
                   staff_discount=None, discount_cap=None):
    """Record a payment of `amount` by `method` against a bill, with the
    Clean Up and (on boarding) the staff discount that arrive with it.

    `kind` is "visit", "inpatient" or "boarding"; `bill_id` the visit, the
    case or the stay. Amounts are Decimals the route parsed; `method` is one
    the route cleaned. `staff_discount` is None unless this submission sets
    the discount -- only boarding's form does (P-2) -- and then
    `discount_cap` is the signed-in user's cap.

    Raises BillNotFound or PaymentRefused; returns Recorded. Does not commit.
    Every check comes before the first write.
    """
    if kind not in KINDS:
        raise ValueError(f"record_payment(): not a kind of bill: {kind!r}")
    spec = KINDS[kind]

    # 1. Lock, before anything is read: two payments on one bill queue here,
    #    and the second reads what the first paid. There is no route that
    #    takes a payment back, so an overpayment could only be refunded around.
    if not db.execute(f"SELECT id FROM {spec.table} WHERE id=%s FOR UPDATE", (bill_id,)).fetchone():
        raise BillNotFound(Msg(spec.not_found))

    # 3. Amount.
    if amount is None or amount <= 0:
        raise PaymentRefused(Msg(N_("Payment amount must be greater than 0.")))

    # 4. The bill as it stands.
    summary = spec.summary(db, bill_id)
    existing_cleanup = summary["cleanup_amount"]

    # 5. Discount. On a rewards-card bill the card's rate is the only one;
    #    otherwise a staff discount is bounded by the role's cap.
    discount = summary["discount_percent"]
    if staff_discount is not None:
        if summary["discount_source"] == "member":
            if staff_discount != summary["discount_percent"]:
                raise PaymentRefused(Msg(N_(
                    "This bill carries a rewards-card discount. A staff discount can't be added on top of it, "
                    "and can't replace it.")))
        else:
            error = discount_error(staff_discount, discount_cap)
            if error:
                raise PaymentRefused(error)
            discount = staff_discount

    # The payable total before Clean Up, under this submission's discount: the
    # bill's own figure unless the discount is changing.
    pre_cleanup_total = summary["pre_cleanup_total"]
    if discount != summary["discount_percent"]:
        pre_cleanup_total = billing.compute_bill_totals(
            summary["subtotal"], discount, summary["paid"], existing_cleanup,
            discountable_subtotal=summary["discountable_subtotal"])[4]

    def balance_with(cleanup):
        """What is owed with this submission's discount and `cleanup` on the bill."""
        return billing.total_and_balance(pre_cleanup_total, cleanup, summary["paid"])[2]

    # 6. Clean Up, against what is owed once this submission's discount is
    #    counted: a discount and a Clean Up in one click cannot write off
    #    more than the discounted bill.
    error = cleanup_error(cleanup_amount, existing_cleanup, balance_with(existing_cleanup))
    if error:
        raise PaymentRefused(error)

    # 7. Payment, against what is owed once the discount AND the Clean Up are
    #    counted (P-1). The three arrive together and the first two change
    #    what the third may be: checked against the bill as it stands,
    #    "pay in full and write a little off" overpays it by the write-off.
    owed = balance_with(existing_cleanup + cleanup_amount)
    if amount > owed:
        raise PaymentRefused(Msg(spec.over_balance, fmt_money=Amount(owed), currency=Currency()))

    # 8. Method. The route cleaned it (core.clean_payment_method); a caller
    #    that did not must not reach the table. NULL passes the CHECK there.
    if method not in METHODS:
        raise ValueError(f"record_payment(): not a payment method: {method!r}")

    # 10. Write. A payment is dated the day it is taken (audit B16).
    payment_id = db.execute(
        f"INSERT INTO payments ({spec.column}, amount, method, date, user_id, notes) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
        (bill_id, amount, method, clock.today().isoformat(), user_id, notes)).fetchone()["id"]
    auth.log_change(db, "payments", str(payment_id), "create")
    if discount != summary["discount_percent"]:
        db.execute(f"UPDATE {spec.bill_table} SET discount_percent = %s, discount_applied_by = %s "
                   f"WHERE {spec.bill_key} = %s", (discount, user_id, bill_id))
        auth.log_change(db, spec.bill_table, str(bill_id), "update", changes={
            "discount_percent": (summary["discount_percent"], discount)})
    if cleanup_amount > 0:
        db.execute(f"UPDATE {spec.bill_table} SET cleanup_amount = cleanup_amount + %s, cleanup_applied_by = %s "
                   f"WHERE {spec.bill_key} = %s", (cleanup_amount, user_id, bill_id))
        auth.log_change(db, spec.bill_table, str(bill_id), "update", changes={
            "cleanup_amount": (existing_cleanup, existing_cleanup + cleanup_amount)})

    # 11. The bill changed: store its new total, which every report reads.
    if cleanup_amount > 0 or discount != summary["discount_percent"]:
        billing.bill_changed(db, kind, bill_id)

    # 12. Only cash is handed over in notes (P-6): a Card or Transfer payment of
    #     an odd amount leaves the drawer as it was.
    return Recorded(payment_id=payment_id,
                    warn_cash_note=method == "Cash" and not money.is_cash_payable(amount))
