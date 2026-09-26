"""
The money setting, and the one set of rules every amount goes through.

VetClinicSystem runs under one of two money settings, chosen by an admin in
Settings and locked once any money has been recorded:

    IQ — Iraqi dinar. Whole dinars; cash changes hands in 250-dinar notes.
    JO — Jordanian dinar. Three decimals; cash is exact to the fils.

The rules below are written ONCE. They take their numbers from the active
setting, and every IQ-specific behaviour the predecessor IQ app had — round a
payable total to the nearest note, never let a genuinely non-zero bill round
down to free, give change and refunds down to a note, warn when an amount
cannot be paid in notes — is the general rule applied with a cash unit of 250.
Under JO the cash unit is 0.001, the same as the entry precision, and the
same rules change nothing: that IS the predecessor JO app's behaviour. There
is no "if IQ" anywhere; `tests/test_money.py` holds the specification as one
table with a column per setting.

Money is always `Decimal`, never `float` — mixing the two raises `TypeError`,
which is the point: a silent float in money arithmetic is the bug this module
exists to make impossible. Every amount is stored at three decimal places
(NUMERIC(15,3)); IQ amounts are simply whole numbers at that scale.

The active setting lives in a ContextVar set once per request
(vcs/web/hooks.py) and copied into background jobs (jobs.py), so formatting and
rounding helpers can be called anywhere without threading a parameter through
every call site. Code that must not run before a setting is chosen calls
`require()`.

This module has no Flask imports.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP

# Every money column is NUMERIC(15,3); anything computed is kept at this scale.
STORE_PLACES = 3
STORE_QUANTUM = Decimal("0.001")
HUNDRED = Decimal(100)


@dataclass(frozen=True)
class MoneySetting:
    code: str                  # "IQ" / "JO" — the value stored in settings.money_setting
    name: str                  # shown in the Settings dropdown (English; translated in the template)
    currency: str              # ISO code, Latin — PDFs and exports always use this
    label_ar: str              # the Arabic abbreviation shown in the Arabic UI
    minor_units: int           # decimal places an amount is ENTERED and shown with
    cash_unit: Decimal         # smallest amount that physically changes hands
    cleanup_cap: Decimal       # most "Clean Up" write-off allowed per bill, cumulatively
    max_amount: Decimal        # largest single amount accepted — a typo guard, not a column limit
    phone_country_code: str
    phone_local_length: int    # digits after the country code, trunk 0 stripped
    phone_example: str
    timezone: str

    @property
    def quantum(self):
        return Decimal(1).scaleb(-self.minor_units)


IQ = MoneySetting(
    code="IQ", name="IQ — Iraqi dinar (IQD)", currency="IQD", label_ar="د.ع",
    minor_units=0, cash_unit=Decimal(250), cleanup_cap=Decimal(1000),
    # ~760,000 USD at 1310 IQD/USD: far past any real clinic amount, so this
    # catches a typo (a phone number in a price field), not a big invoice.
    max_amount=Decimal("999999999999"),
    phone_country_code="964", phone_local_length=10, phone_example="07701234567",
    timezone="Asia/Baghdad",
)
JO = MoneySetting(
    code="JO", name="JO — Jordanian dinar (JOD)", currency="JOD", label_ar="د.أ",
    minor_units=3, cash_unit=Decimal("0.001"), cleanup_cap=Decimal("1.000"),
    max_amount=Decimal("999999999.999"),
    phone_country_code="962", phone_local_length=9, phone_example="0791234567",
    timezone="Asia/Amman",
)
SETTINGS = {"IQ": IQ, "JO": JO}
SETTING_KEY = "money_setting"

# Every table that holds a money amount. The money setting is locked from the
# moment any of them holds a row with an amount in it: after that, switching
# the setting would reinterpret stored numbers in another currency. Price
# List and catalogue costs count — they are amounts typed in a currency too.
MONEY_TABLES = [
    ("price_list", "sale_price IS NOT NULL OR cost_price IS NOT NULL"),
    ("inventory_list", "cost_price IS NOT NULL"),
    ("billing", None), ("visit_billing_lines", None), ("inpatient_billing", None),
    ("payments", None), ("sales", None), ("refunds", None),
    ("boarding_sessions", "price_per_day IS NOT NULL OR total IS NOT NULL"),
    ("distributor_bills", None), ("distributor_bill_payments", None),
    ("consignment_receipts", None), ("consignment_settlements", None),
    ("cash_register_payouts", None), ("cash_register_audits", None),
    ("monthly_opex", None),
]


class MoneySettingNotChosen(Exception):
    """Raised by require() when money is about to be parsed, rounded or
    stored before an admin has chosen IQ or JO. Routes that record money are
    gated before they get here (core.requires_money_setting); this is the
    backstop so nothing can slip a currency-less amount into the database."""


_current = ContextVar("money_setting", default=None)


def load(db):
    """The setting stored in this database, or None if not chosen yet."""
    row = db.execute("SELECT value FROM settings WHERE key=?", (SETTING_KEY,)).fetchone()
    return SETTINGS.get((row["value"] or "").strip().upper()) if row else None


def set_current(setting):
    """Make `setting` (a MoneySetting or None) active for this context.
    Returns a token for reset_current()."""
    return _current.set(setting)


def reset_current(token):
    _current.reset(token)


def current():
    """The active MoneySetting, or None before one is chosen."""
    return _current.get()


def require():
    m = _current.get()
    if m is None:
        raise MoneySettingNotChosen()
    return m


def is_locked(db):
    """True once any money has been recorded — the setting can no longer
    change. One EXISTS per table, stopping at the first hit."""
    for table, condition in MONEY_TABLES:
        where = f" WHERE {condition}" if condition else ""
        if db.execute(f"SELECT EXISTS(SELECT 1 FROM {table}{where}) AS e").fetchone()["e"]:
            return True
    return False


# ---------------------------------------------------------------------------
# Rounding. Three scales, never confused:
#   store  — 0.001, what the database holds; every computed intermediate
#   entry  — the setting's quantum; what a person can type and is shown
#   cash   — the setting's cash unit; what a payable total is rounded to
# ---------------------------------------------------------------------------
def _d(x):
    if isinstance(x, Decimal):
        return x
    if isinstance(x, float):
        # Money never arrives as a float from this app's own code; if one does,
        # fail loudly here rather than letting binary noise into a total.
        raise TypeError("money must be Decimal, not float")
    return Decimal(x if x is not None else 0)


def to_store(x):
    """Round to the storage scale (0.001), half-up."""
    return _d(x).quantize(STORE_QUANTUM, rounding=ROUND_HALF_UP)


def to_entry(x, m=None):
    """Round to what the active setting lets a person enter (IQ: whole
    dinars, JO: fils), half-up, at storage scale."""
    m = m or require()
    return to_store(_d(x).quantize(m.quantum, rounding=ROUND_HALF_UP))


def round_cash(x, mode="nearest", m=None):
    """Round to a multiple of the cash unit.

    nearest — half-up (Python's round() breaks ties to even, which would round
              exactly half a note either way depending on parity)
    down    — floor: for money LEAVING the clinic (change, refunds), so it
              never hands back more than is owed
    """
    x = _d(x)
    if x == 0:
        # Zero is zero in every currency — and a page listing unpriced
        # records must render before a money setting has been chosen.
        return to_store(0)
    m = m or require()
    unit = m.cash_unit
    rounding = ROUND_HALF_UP if mode == "nearest" else ROUND_FLOOR
    return to_store((_d(x) / unit).quantize(Decimal(1), rounding=rounding) * unit)


def payable(raw_total, discount_percent=0, m=None):
    """The amount actually charged for a bill whose exact figure is
    `raw_total`: rounded to the cash unit, but never rounded down to FREE.

    A genuinely non-zero bill smaller than half the cash unit would round to
    0 — the goods leave free and, at a till, every dinar tendered comes back
    as change. It is charged one cash unit instead. A 100% discount is a
    deliberate waiver, not a rounding accident, so it stays exempt.

    Under JO (cash unit 0.001) the raw total is already at that precision and
    this changes nothing.
    """
    raw = _d(raw_total)
    if raw == 0:
        return to_store(0)
    m = m or require()
    total = round_cash(raw, "nearest", m)
    if 0 < raw <= m.cash_unit / 2 and _d(discount_percent) < HUNDRED:
        return to_store(m.cash_unit)
    return total


def balance_due(total, paid, m=None):
    """What is still owed, rounded to the cash unit: a remainder smaller than
    half a note is not collectable in cash, so it reads as settled."""
    return round_cash(_d(total) - _d(paid), "nearest", m)


def is_settled(balance):
    """A bill is fully paid when nothing collectable remains. There is no
    tolerance constant here on purpose: under IQ the balance is already
    rounded to a note, and under JO a leftover of any size is real money."""
    return _d(balance) <= 0


def change_due(cash_received, total, m=None):
    """Change handed back at the till, rounded DOWN to the cash unit — never
    more than owed; any shortfall is absorbed by the clinic."""
    return max(round_cash(_d(cash_received) - _d(total), "down", m), Decimal(0))


def refund_payout(amount, headroom, m=None):
    """(payout, None) or (None, error) for a refund of `amount` when at most
    `headroom` of the original payment is still refundable.

    Rounded DOWN to the cash unit, like change. But a real return must never
    be settled at zero — the customer would hand the goods back and be paid
    nothing — so a payout that rounds to 0 pays one cash unit instead,
    provided at least that much is still refundable."""
    m = m or require()
    amount = _d(amount)
    payout = round_cash(amount, "down", m)
    if amount > 0 and payout == 0:
        if _d(headroom) < m.cash_unit:
            return None, "no_refundable_unit"
        payout = to_store(m.cash_unit)
    return payout, None


def is_cash_payable(amount, m=None):
    """True if `amount` can be paid exactly in cash (a multiple of the cash
    unit). Drives a gentle warning, never a refusal. Always true under JO."""
    m = m or require()
    return _d(amount) % m.cash_unit == 0


def audit_status(difference, m=None):
    """Result of counting the drawer against the system's figure. Exact:
    'Perfect' means the counts agree to the smallest amount a person can
    enter. (The predecessor JO app kept IQ's `abs(diff) < 1` and so called a
    drawer 999 fils short 'Perfect'.)"""
    diff = to_entry(difference, m)
    if diff == 0:
        return "Perfect"
    return "Deficit" if diff < 0 else "Surplus"


def discounted(subtotal, discountable_subtotal, discount_percent):
    """The bill before rounding: the discount comes off the eligible part of
    the subtotal only; the rest is charged in full."""
    d = _d(discount_percent)
    eligible = _d(discountable_subtotal)
    return eligible * (1 - d / HUNDRED) + (_d(subtotal) - eligible)


# ---------------------------------------------------------------------------
# Parsing and display
# ---------------------------------------------------------------------------
class BadAmount(ValueError):
    """Not a usable amount (core.parse_money turns this into BadNumber)."""


def parse(raw, m=None):
    """A typed amount -> Decimal at the setting's entry precision. Raises
    BadAmount for text, NaN, Infinity, or anything past max_amount.

    Quantized HERE, before any check sees it: an amount the database would
    round to 0.000 must already be 0 when `amount > 0` is tested. (The
    predecessor JO app validated the unrounded value, so 0.0004 passed
    `> 0`, was stored as 0.000 and broke a CHECK constraint.)"""
    m = m or require()
    try:
        val = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise BadAmount(raw)
    if not val.is_finite():
        raise BadAmount(raw)
    val = to_entry(val, m)
    if abs(val) > m.max_amount:
        raise BadAmount(f"{raw} is too large — check for a typo.")
    return val


def fmt(amount, m=None):
    """Display form: the setting's decimal places, thousands separators.
    '—' for None. Before a setting is chosen (nothing can have been recorded
    yet) a value is shown without trailing zeros."""
    if amount is None:
        return "—"
    m = m or current()
    v = _d(amount)
    if m is None:
        return f"{v.normalize():,f}"
    return f"{v.quantize(m.quantum, rounding=ROUND_HALF_UP):,.{m.minor_units}f}"


def input_step(kind="amount", m=None):
    """The HTML `step` for a money input: the entry quantum for a typed
    amount, the cash unit for cash received at the till."""
    m = m or current()
    if m is None:
        return "any"
    unit = m.cash_unit if kind == "cash" else m.quantum
    return format(unit.normalize(), "f")
