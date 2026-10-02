"""
One set of rules for a payment against a bill, on every kind of bill
(docs/plans/PAYMENT_CENTRALIZATION_PLAN.md §6.1).

A visit, an inpatient case and a boarding stay each take payments, and each
route used to carry its own copy of the rules. The copies drifted: boarding
checked a payment against the balance its own Clean Up would leave, and the
other two against the balance before it, so "pay in full and write a little
off" overpaid a visit by the write-off, with no route to take a payment back
(plan §2.2). Every one of those routes had its own tests, and they were
green: each tested its route against its own behaviour (SEAM_RULES.md §1).

So this file is organised by RULE, not by route. Each rule runs against all
three kinds through the real routes, each guard beside the control that
shows the valid case still succeeds. The per-kind facts the tests need (the
address, the column, the words) are written out here on purpose, not read
from the code under test.

Unmarked tests run under the run's money setting (conftest.amount() writes
an amount for either); the two about cash notes assert one setting's
behaviour and are marked.
"""
import html
import re
from dataclasses import dataclass
from decimal import Decimal as D

import pytest

from vcs import clock, money
from vcs.domain import billing
from conftest import ADMIN_ID, amount, needs_db, new_id
from test_concurrency import _fresh_client, _run_together

pytestmark = needs_db

KINDS = ("visit", "inpatient", "boarding")
METHODS = ("Cash", "Card", "Transfer")

# What differs per kind, and nothing else does.
FACTS = {
    "visit": dict(url="/visits/{}/payment", column="visit_id", summary=billing.visit_billing_summary,
                  table="billing", key="visit_id", stored_total="total",
                  not_found="Visit not found.", noun="visit"),
    "inpatient": dict(url="/inpatient/{}/payment", column="inpatient_case_id",
                      summary=billing.inpatient_billing_summary,
                      table="inpatient_cases", key="id", stored_total="total",
                      not_found="Inpatient case not found.", noun="case"),
    "boarding": dict(url="/boarding/{}/payment", column="boarding_id", summary=billing.boarding_billing_summary,
                     table="boarding_sessions", key="id", stored_total="billed_total",
                     not_found="Boarding session not found.", noun="stay"),
}

VALID_NUMBER = "Payment amount must be a valid number."
GREATER_THAN_0 = "Payment amount must be greater than 0."
RECORDED = "Payment recorded."
NOTE_WARNING = "isn't a multiple of"
MEMBER_RATE = "This bill carries a rewards-card discount."

# ---------------------------------------------------------------------------
# ABOUT TO CHANGE (plan §2.2, phase 3). Where the three kinds disagree today,
# these record what each does now, so the move into one function (phase 2)
# can be shown to change nothing. Phase 3 makes each one rule and flips it.
# ---------------------------------------------------------------------------
# A3: an empty amount.
EMPTY_AMOUNT_MESSAGE = {"visit": VALID_NUMBER, "inpatient": VALID_NUMBER, "boarding": GREATER_THAN_0}
# P-1: a payment of the whole balance PLUS a Clean Up. Boarding refuses it;
# visits and inpatient accept it and leave the bill overpaid -- the bug.
REFUSES_PAYMENT_PLUS_CLEANUP_OVER_THE_BALANCE = {"visit": False, "inpatient": False, "boarding": True}
# P-6: which methods warn that an amount cannot be paid in 250-dinar notes.
WARNS_ABOUT_NOTES = ("Cash", "Card", "Transfer")


@dataclass
class Bill:
    kind: str
    id: int
    total: D

    @property
    def facts(self):
        return FACTS[self.kind]

    @property
    def url(self):
        return self.facts["url"].format(self.id)

    def payments(self, db):
        return db.execute(f"SELECT * FROM payments WHERE {self.facts['column']}=%s ORDER BY id",
                          (self.id,)).fetchall()

    def summary(self, db):
        return self.facts["summary"](db, self.id)

    def stored(self, db):
        """The bill's own row: what a payment may change besides `payments`."""
        f = self.facts
        return db.execute(
            f"SELECT cleanup_amount, cleanup_applied_by, discount_percent, discount_applied_by, discount_source, "
            f"{f['stored_total']} AS stored_total FROM {f['table']} WHERE {f['key']}=%s", (self.id,)).fetchone()

    def state(self, db):
        """Everything a submission could have written, to compare before and after."""
        row = self.stored(db)
        return (len(self.payments(db)), row["cleanup_amount"], row["discount_percent"], row["stored_total"])

    def log_rows(self, db, field):
        """Change-log entries for a field of this bill's own row."""
        return db.execute(
            "SELECT COUNT(*) AS c FROM audit_log WHERE table_name=%s AND record_id=%s AND field=%s",
            (self.facts["table"], str(self.id), field)).fetchone()["c"]


def _form(data):
    return {k: str(v) for k, v in data.items() if v is not None}


def pay(client, bill, **data):
    """Post the payment form and follow it to the page that shows the result."""
    return client.post(bill.url, data=_form(data), follow_redirects=True)


def flashes(resp):
    """[(category, text)] of the messages the page shows."""
    return [(category, html.unescape(text).strip()) for category, text in
            re.findall(r'<div class="flash (\w+)">(.*?)</div>', resp.get_data(as_text=True), re.S)]


def errors(resp):
    return [text for category, text in flashes(resp) if category == "error"]


def step():
    """The smallest Clean Up worth typing in either setting: 0.250 / 250."""
    return amount("0.250")


def cap():
    return money.current().cleanup_cap


def currency():
    return money.current().currency


@pytest.fixture(params=KINDS)
def kind(request):
    return request.param


@pytest.fixture
def bill(kind, client, db):
    """An unpaid bill of 100.000 (100,000 under IQ) of the kind under test,
    billed the way staff bill it."""
    owner, patient, visit, price = new_id(), new_id(), new_id(), new_id()
    total = amount("100.000")
    today = clock.today().isoformat()
    db.execute("INSERT INTO owners (id, name) VALUES (%s,%s)", (owner, f"Payment Owner {owner}"))
    db.execute("INSERT INTO patients (id, owner_id, animal_name) VALUES (%s,%s,%s)",
               (patient, owner, f"Payment Pet {patient}"))
    case = stay = None
    if kind == "visit":
        db.execute("INSERT INTO visits (id, patient_id, date, case_status) VALUES (%s,%s,%s,%s)",
                   (visit, patient, today, "Ongoing"))
        db.commit()
        resp = client.post(f"/visits/{visit}/billing", data={"billing_type": "Manual", "manual_amount": str(total)})
        assert resp.status_code == 302, "the visit could not be billed — the test would prove nothing"
        made = Bill(kind, visit, total)
    elif kind == "inpatient":
        db.execute("INSERT INTO price_list (id, name, category, cost_price, sale_price, active, can_discount) "
                   "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                   (price, f"Payment Service {price}", "Service", amount("40.000"), total, True, True))
        case = db.execute(
            "INSERT INTO inpatient_cases (patient_id, admission_date, dismissed, discount_percent, total, "
            "cleanup_amount) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (patient, today, False, D(0), D(0), D(0))).fetchone()["id"]
        db.commit()
        resp = client.post(f"/inpatient/{case}/billing", data={"price_id": price, f"qty_{price}": "1"})
        assert resp.status_code == 302, "the case could not be billed — the test would prove nothing"
        made = Bill(kind, case, total)
    else:
        stay = db.execute(
            "INSERT INTO boarding_sessions (patient_id, entry_date, special_needs, total_is_auto, cleanup_amount, "
            "discount_percent, dismissed, total, billed_total) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (patient, today, False, False, D(0), D(0), False, total, total)).fetchone()["id"]
        db.commit()
        made = Bill(kind, stay, total)
    assert made.summary(db)["balance"] == total, "the fixture's bill is not what the tests assume"
    # Billing it flashed "Billing saved.", which the next page would show
    # beside whatever the payment says.
    with client.session_transaction() as sess:
        sess.pop("_flashes", None)
    yield made
    db.rollback()
    for sql, arg in (
        ("DELETE FROM payments WHERE visit_id=%s", visit),
        ("DELETE FROM payments WHERE inpatient_case_id=%s", case),
        ("DELETE FROM payments WHERE boarding_id=%s", stay),
        ("DELETE FROM billing WHERE visit_id=%s", visit),
        ("DELETE FROM inpatient_billing WHERE case_id=%s", case),
        ("DELETE FROM inpatient_cases WHERE id=%s", case),
        ("DELETE FROM boarding_sessions WHERE id=%s", stay),
        ("DELETE FROM visits WHERE id=%s", visit),
        ("DELETE FROM price_list WHERE id=%s", price),
        ("DELETE FROM patients WHERE id=%s", patient),
        ("DELETE FROM owners WHERE id=%s", owner),
    ):
        if arg is not None:
            db.execute(sql, (arg,))
    db.commit()


# ---------------------------------------------------------------------------
# Missing bill
# ---------------------------------------------------------------------------

def test_a_payment_on_a_bill_that_does_not_exist_is_refused_in_its_own_words(client, db, kind):
    """GUARD. The payload is a valid one, so the only thing wrong is the bill."""
    facts, missing = FACTS[kind], 2_000_000_001
    resp = client.post(facts["url"].format(missing), data={"amount": str(amount("10.000")), "method": "Cash"},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert errors(resp) == [facts["not_found"]]
    assert db.execute(f"SELECT COUNT(*) AS c FROM payments WHERE {facts['column']}=%s",
                      (missing,)).fetchone()["c"] == 0


# ---------------------------------------------------------------------------
# Amount
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("typed, message", [
    ("0", GREATER_THAN_0), ("-5", GREATER_THAN_0),
    ("abc", VALID_NUMBER), ("nan", VALID_NUMBER), ("inf", VALID_NUMBER), ("1e400", VALID_NUMBER),
])
def test_an_amount_that_is_not_a_payment_is_refused(client, db, bill, typed, message):
    """GUARD."""
    before = bill.state(db)
    resp = pay(client, bill, amount=typed, method="Cash")
    assert errors(resp) == [message]
    assert bill.state(db) == before, "a refused payment wrote something"


@pytest.mark.parametrize("typed", ["", "   ", None])        # None: the field left out entirely
def test_an_empty_amount_is_refused(client, db, bill, typed):
    """GUARD. ABOUT TO CHANGE (A3): the three kinds do not say the same thing today."""
    before = bill.state(db)
    resp = pay(client, bill, amount=typed, method="Cash")
    assert errors(resp) == [EMPTY_AMOUNT_MESSAGE[bill.kind]]
    assert bill.state(db) == before


def test_control_a_valid_payment_is_recorded(client, db, bill):
    part = amount("40.000")
    resp = client.post(bill.url, data=_form(dict(amount=part, method="Card", notes="first instalment")))
    assert resp.status_code == 302, "a recorded payment redirects"
    rows = bill.payments(db)
    assert len(rows) == 1
    row = rows[0]
    assert (row["amount"], row["method"], row["notes"]) == (part, "Card", "first instalment")
    assert row["user_id"] == ADMIN_ID, "the payment does not say who took it"
    assert row["date"] == clock.today(), "a payment is dated the day it is taken"
    assert bill.summary(db)["balance"] == bill.total - part


def test_a_payment_is_dated_today_whatever_the_form_says(client, db, bill):
    """GUARD (audit B16). No form sends a date; a crafted one must not book
    the payment into another month."""
    pay(client, bill, amount=amount("10.000"), method="Cash", date="2020-01-01")
    assert [r["date"] for r in bill.payments(db)] == [clock.today()]


def test_the_page_says_the_payment_was_recorded(client, db, bill):
    resp = pay(client, bill, amount=amount("10.000"), method="Card")
    assert flashes(resp) == [("success", RECORDED)]


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------

def test_a_payment_of_more_than_is_owed_is_refused(client, db, bill):
    """GUARD. There is no route that takes a payment back, so an overpayment
    can only be refunded around."""
    before = bill.state(db)
    resp = pay(client, bill, amount=bill.total + step(), method="Cash")
    assert errors(resp) == [f"That's more than the remaining balance of {money.fmt(bill.total)} {currency()} "
                            f"on this {bill.facts['noun']}."]
    assert bill.state(db) == before


def test_control_a_payment_of_exactly_what_is_owed_settles_the_bill(client, db, bill):
    pay(client, bill, amount=bill.total, method="Cash")
    summary = bill.summary(db)
    assert [r["amount"] for r in bill.payments(db)] == [bill.total]
    assert (summary["balance"], summary["status"]) == (0, "Fully Paid")


def test_instalments_are_checked_against_what_is_left(client, db, bill):
    """GUARD. Each is within the bill; the one that would tip it over is not."""
    part = amount("40.000")
    for _ in range(2):
        pay(client, bill, amount=part, method="Cash")
    resp = pay(client, bill, amount=part, method="Cash")
    left = bill.total - 2 * part
    assert errors(resp) == [f"That's more than the remaining balance of {money.fmt(left)} {currency()} "
                            f"on this {bill.facts['noun']}."]
    assert sum(r["amount"] for r in bill.payments(db)) == 2 * part


# ---------------------------------------------------------------------------
# P-1 — a payment and a Clean Up in one submission
# ---------------------------------------------------------------------------

def test_a_payment_plus_a_clean_up_cannot_exceed_what_is_owed(client, db, bill):
    """GUARD (P-1). The whole balance is paid AND a Clean Up is written off
    in the same submission. Each is within its own limit; together they are
    more than the bill.

    ABOUT TO CHANGE: boarding refuses it. A visit and an inpatient case
    accept it today and are left OVERPAID by the Clean Up -- plan §2.2,
    reproduced here through the routes."""
    before = bill.state(db)
    resp = pay(client, bill, amount=bill.total, cleanup_amount=cap(), method="Cash")
    if REFUSES_PAYMENT_PLUS_CLEANUP_OVER_THE_BALANCE[bill.kind]:
        assert errors(resp) == [f"That's more than the remaining balance of {money.fmt(bill.total - cap())} "
                                f"{currency()} on this {bill.facts['noun']}."]
        assert bill.state(db) == before, "a refused payment wrote something"
    else:
        summary = bill.summary(db)
        assert flashes(resp)[0] == ("success", RECORDED)
        assert summary["total"] == bill.total - cap() and summary["paid"] == bill.total, (
            "the overpayment this test pins is gone — flip REFUSES_PAYMENT_PLUS_CLEANUP_OVER_THE_BALANCE")


def test_control_a_payment_plus_a_clean_up_equal_to_what_is_owed_settles_the_bill(client, db, bill):
    resp = pay(client, bill, amount=bill.total - cap(), cleanup_amount=cap(), method="Cash")
    assert flashes(resp)[0] == ("success", RECORDED)
    summary = bill.summary(db)
    assert [r["amount"] for r in bill.payments(db)] == [bill.total - cap()]
    assert bill.stored(db)["cleanup_amount"] == cap()
    assert (summary["total"], summary["balance"], summary["status"]) == (bill.total - cap(), 0, "Fully Paid")


# ---------------------------------------------------------------------------
# Clean Up
# ---------------------------------------------------------------------------

def test_clean_up_is_capped_across_submissions(client, db, bill):
    """GUARD. The cap is per bill, not per click: two submissions that each
    stay under it must not add up to more."""
    pay(client, bill, amount=amount("10.000"), cleanup_amount=cap() - step(), method="Cash")
    before = bill.state(db)
    assert before[:2] == (1, cap() - step()), "the first Clean Up was not recorded — the test would prove nothing"
    resp = pay(client, bill, amount=amount("10.000"), cleanup_amount=2 * step(), method="Cash")
    assert errors(resp) == [f"Clean Up on this bill can't exceed {money.fmt(cap())} {currency()} in total."]
    assert bill.state(db) == before


def test_control_clean_up_reaches_the_cap_exactly(client, db, bill):
    pay(client, bill, amount=amount("10.000"), cleanup_amount=cap() - step(), method="Cash")
    resp = pay(client, bill, amount=amount("10.000"), cleanup_amount=step(), method="Cash")
    assert flashes(resp)[0] == ("success", RECORDED)
    row = bill.stored(db)
    assert row["cleanup_amount"] == cap()
    assert row["cleanup_applied_by"] == ADMIN_ID, "a write-off must record who applied it"
    assert len(bill.payments(db)) == 2


@pytest.mark.parametrize("typed, message", [
    ("-1", "Clean Up amount can't be negative."),
    ("abc", "Clean Up amount must be a valid number."),
    ("nan", "Clean Up amount must be a valid number."),
])
def test_a_clean_up_that_is_not_an_amount_is_refused(client, db, bill, typed, message):
    """GUARD."""
    before = bill.state(db)
    resp = pay(client, bill, amount=amount("10.000"), cleanup_amount=typed, method="Cash")
    assert errors(resp) == [message]
    assert bill.state(db) == before


def test_clean_up_cannot_exceed_what_is_still_owed(client, db, bill):
    """GUARD. Within the cap, but more than is left on the bill."""
    pay(client, bill, amount=bill.total - step(), method="Cash")
    before = bill.state(db)
    resp = pay(client, bill, amount=step(), cleanup_amount=2 * step(), method="Cash")
    assert errors(resp) == ["Clean Up can't exceed the remaining balance."]
    assert bill.state(db) == before


def test_control_a_payment_without_a_clean_up_leaves_it_alone(client, db, bill):
    """Every form posts the field whether or not it was used: 0, and blank."""
    for typed in ("0", ""):
        pay(client, bill, amount=amount("10.000"), cleanup_amount=typed, method="Cash")
    assert len(bill.payments(db)) == 2
    assert bill.stored(db)["cleanup_amount"] == 0
    assert bill.log_rows(db, "cleanup_amount") == 0


def test_the_stored_total_follows_a_clean_up(client, db, bill):
    """GUARD (seam rule 12). Every report reads the stored total; a Clean Up
    taken with a payment changes the bill, so it must be stored again."""
    pay(client, bill, amount=amount("10.000"), cleanup_amount=step(), method="Cash")
    assert bill.stored(db)["stored_total"] == bill.summary(db)["total"] == bill.total - step()


# ---------------------------------------------------------------------------
# Method
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", ["Bitcoin", "cash", "", None])
def test_a_payment_needs_one_of_the_three_methods(client, db, bill, method):
    """GUARD (audit B10). The Cash Register sums the drawer by method."""
    before = bill.state(db)
    resp = pay(client, bill, amount=amount("10.000"), method=method)
    assert errors(resp) == ["Pick how this was paid: Cash, Card, Transfer."]
    assert bill.state(db) == before


@pytest.mark.parametrize("method", METHODS)
def test_control_each_method_is_recorded(client, db, bill, method):
    pay(client, bill, amount=amount("10.000"), method=method)
    assert [r["method"] for r in bill.payments(db)] == [method]


# ---------------------------------------------------------------------------
# P-6 — the cash-note warning
# ---------------------------------------------------------------------------

def _warned_about_notes(resp):
    return any(category == "warning" and NOTE_WARNING in text for category, text in flashes(resp))


@pytest.mark.money("IQ")
@pytest.mark.parametrize("method", METHODS)
def test_an_amount_that_is_not_in_notes_warns(client, db, bill, method):
    """1,100 dinars cannot be handed over in 250-dinar notes. The payment is
    recorded as typed either way; the warning is about counting the drawer.

    ABOUT TO CHANGE (P-6): it fires for every method today."""
    resp = pay(client, bill, amount="1100", method=method)
    assert [r["amount"] for r in bill.payments(db)] == [D("1100")]
    assert _warned_about_notes(resp) == (method in WARNS_ABOUT_NOTES)


@pytest.mark.money("IQ")
def test_control_an_amount_in_notes_does_not_warn(client, db, bill):
    resp = pay(client, bill, amount="1250", method="Cash")
    assert flashes(resp) == [("success", RECORDED)]


@pytest.mark.money("JO")
@pytest.mark.parametrize("method", METHODS)
def test_jo_never_warns_about_notes(client, db, bill, method):
    """The fils is JO's cash unit: every amount a person can type is payable."""
    resp = pay(client, bill, amount="1.101", method=method)
    assert flashes(resp) == [("success", RECORDED)]


# ---------------------------------------------------------------------------
# The change log
# ---------------------------------------------------------------------------

def _payment_log(db, payment_id):
    return db.execute("SELECT action, user_id FROM audit_log WHERE table_name='payments' AND record_id=%s",
                      (str(payment_id),)).fetchall()


def test_a_payment_and_its_clean_up_are_in_the_change_log(client, db, bill):
    """GUARD."""
    pay(client, bill, amount=amount("10.000"), cleanup_amount=step(), method="Cash")
    payment = bill.payments(db)[0]
    log = _payment_log(db, payment["id"])
    assert [(r["action"], r["user_id"]) for r in log] == [("create", ADMIN_ID)]
    assert bill.log_rows(db, "cleanup_amount") == 1


# ---------------------------------------------------------------------------
# P-2 — a staff discount is taken with the payment on boarding, and only there
# ---------------------------------------------------------------------------

@pytest.fixture
def stay(client, db):
    """A boarding bill, for the rules only boarding has."""
    gen = bill.__wrapped__("boarding", client, db)
    made = next(gen)
    yield made
    next(gen, None)


@pytest.fixture
def low_cap(client):
    """The signed-in user's discount cap, lowered to 5% for one test."""
    with client.session_transaction() as sess:
        original = sess.get("discount_cap")
        sess["discount_cap"] = 5
    yield 5
    with client.session_transaction() as sess:
        sess["discount_cap"] = original


def test_a_discount_above_the_roles_cap_is_refused_with_the_payment(client, db, stay, low_cap):
    """GUARD."""
    before = stay.state(db)
    resp = pay(client, stay, amount=amount("10.000"), discount_percent="10", method="Cash")
    assert errors(resp) == ["Discount must be between 0% and 5% for your role."]
    assert stay.state(db) == before


def test_control_a_discount_within_the_cap_is_applied_with_the_payment(client, db, stay):
    discounted = stay.total * D("0.9")
    resp = pay(client, stay, amount=discounted, discount_percent="10", method="Cash")
    assert flashes(resp)[0] == ("success", RECORDED)
    row, summary = stay.stored(db), stay.summary(db)
    assert (row["discount_percent"], row["discount_applied_by"]) == (10, ADMIN_ID)
    assert row["stored_total"] == summary["total"] == discounted
    assert (summary["balance"], summary["status"]) == (0, "Fully Paid")
    assert stay.log_rows(db, "discount_percent") == 1


def test_a_payment_is_checked_against_the_discounted_balance(client, db, stay):
    """GUARD. "Apply 10% and pay the undiscounted total" overpays the bill."""
    before = stay.state(db)
    resp = pay(client, stay, amount=stay.total, discount_percent="10", method="Cash")
    assert errors(resp) == [f"That's more than the remaining balance of {money.fmt(stay.total * D('0.9'))} "
                            f"{currency()} on this stay."]
    assert stay.state(db) == before, "a refused payment must not leave its discount applied"


def test_a_discount_that_is_not_a_number_is_refused(client, db, stay):
    """GUARD."""
    before = stay.state(db)
    resp = pay(client, stay, amount=amount("10.000"), discount_percent="lots", method="Cash")
    assert errors(resp) == ["Discount must be a valid number."]
    assert stay.state(db) == before


def test_control_an_unchanged_discount_is_not_logged_again(client, db, stay):
    pay(client, stay, amount=amount("10.000"), discount_percent="0", method="Cash")
    assert len(stay.payments(db)) == 1
    assert stay.log_rows(db, "discount_percent") == 0


@pytest.fixture
def member_stay(db, stay):
    """The stay of a rewards-card member: its discount is the card's."""
    db.execute("UPDATE boarding_sessions SET discount_percent=10, discount_source='member' WHERE id=%s", (stay.id,))
    billing.bill_changed(db, "boarding", stay.id)
    db.commit()
    return stay


def test_a_members_rate_cannot_be_changed_with_a_payment(client, db, member_stay):
    """GUARD. The card's discount is the only one a member's bill carries."""
    before = member_stay.state(db)
    for typed in ("5", "0", "20"):
        resp = pay(client, member_stay, amount=amount("10.000"), discount_percent=typed, method="Cash")
        assert len(errors(resp)) == 1 and errors(resp)[0].startswith(MEMBER_RATE)
    assert member_stay.state(db) == before


def test_control_a_members_stay_is_still_paid(client, db, member_stay):
    """The form hides the discount field on a member's stay, so it is not
    posted at all; and a submission that repeats the card's own rate changes
    nothing. Both are payments, not refusals."""
    pay(client, member_stay, amount=amount("10.000"), method="Cash")
    pay(client, member_stay, amount=amount("10.000"), discount_percent="10", method="Cash")
    row = member_stay.stored(db)
    assert len(member_stay.payments(db)) == 2
    assert (row["discount_percent"], row["discount_source"]) == (10, "member")


@pytest.mark.parametrize("which", ["visit", "inpatient"])
def test_a_visit_or_inpatient_payment_takes_no_discount(client, db, which):
    """GUARD (P-2). Their discount is its own step, with its own checks (a
    non-discountable line refuses it). A discount field posted with a payment
    must not reach the bill."""
    gen = bill.__wrapped__(which, client, db)
    made = next(gen)
    try:
        pay(client, made, amount=amount("10.000"), discount_percent="50", method="Cash")
        assert len(made.payments(db)) == 1
        assert made.stored(db)["discount_percent"] == 0
        assert made.summary(db)["total"] == made.total
    finally:
        next(gen, None)


# ---------------------------------------------------------------------------
# Two at once
# ---------------------------------------------------------------------------

def test_two_simultaneous_payments_cannot_overpay_a_bill(flask_app, db, bill):
    """GUARD. Each is within the balance; together they exceed it. Without
    the row lock both read the same "already paid" and both pass.
    (tests/test_concurrency.py holds this for a visit; here, every kind.)"""
    part = amount("75.000")

    def one(_i):
        return _fresh_client(flask_app).post(bill.url, data={"amount": str(part), "method": "Cash"}).status_code

    results, raised = _run_together(one, 2)
    assert not any(raised), f"a payment thread raised: {[e for e in raised if e]}"
    assert sorted(results) == [200, 302], "one is recorded and the other refused"
    assert [r["amount"] for r in bill.payments(db)] == [part]
