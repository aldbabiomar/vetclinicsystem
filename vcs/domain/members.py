"""
The rewards card: who is a member, the rate and the term, and the
discount a member's bill gets.
"""
from decimal import Decimal

from vcs import clock
from vcs.domain import dates, settings


# ---------------------------------------------------------------------------
# Rewards card — membership, the rate, and the term
# (features/REWARDS_CARD_PLAN.md)
# ---------------------------------------------------------------------------
MEMBER_RATE_MAX = 50            # A6 — 0 means the programme is off


MEMBER_TERM_MONTHS_DEFAULT = 12


MEMBER_TERM_MONTHS_MAX = 120


MEMBER_EXPIRING_SOON_DAYS = 30  # when the owner page starts warning


def is_active_member(owner):
    """Does this owner hold a rewards card that is valid TODAY?

    THE one place that answers this. Everything that prices a bill, badges a
    name or shows the Rewards panel goes through here, so "active member"
    cannot come to mean two different things in two places.

    Deliberately a read-time comparison and NOT a nightly job that flips
    is_member: a job that quietly stops running leaves every lapsed card
    still discounting, and nothing would say so. A comparison cannot stop
    running. is_member therefore stays TRUE on a lapsed card, which is also
    what keeps "lapsed" distinguishable from "never joined".

    NULL member_expires_on means the card never expires. The comparison is
    `>=`, so the card works THROUGH its expiry date — an off-by-one here is a
    card that dies a day early, which nobody reports as a bug.

    clock.today() is naive on purpose, matching every other date site in this
    app: it runs on the clinic's own PC, so local time IS clinic time.
    """
    if owner is None:
        return False
    try:
        if not owner["is_member"]:
            return False
        expires = owner["member_expires_on"]
    except (KeyError, IndexError, TypeError):
        # A row selected without the membership columns is not evidence of
        # membership.
        return False
    if not expires:
        return True
    expires = dates.as_date(expires)
    if not expires:
        return True
    return expires >= clock.today()


def member_discount_rate(db):
    """The clinic's rewards-card percentage. 0 means the programme is off.

    Read through here by all four bill-creation sites so they cannot parse
    the setting four different ways.

    Returns DECIMAL, because this is JO — IQ's copy returns float
    (COMPARISON.md §1.1). Mixing the two raises TypeError here rather than
    silently losing fils, which is the property that makes JO's money code
    safe to change; do not "simplify" this to float.

    A stored value outside the allowed range degrades to 0 (programme off)
    rather than raising: settings can arrive from a restored backup or a
    hand edit, so this fails closed the same way int_setting() does.
    """
    raw = settings.get_setting(db, "member_discount_percent", "0") or "0"
    try:
        rate = Decimal(str(raw))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal(0)
    if not Decimal(0) <= rate <= Decimal(MEMBER_RATE_MAX):
        return Decimal(0)
    return rate


def member_term_months(db):
    """How long a newly issued card lasts, in whole months."""
    n = settings.int_setting(db, "member_term_months", MEMBER_TERM_MONTHS_DEFAULT)
    return n if 1 <= n <= MEMBER_TERM_MONTHS_MAX else MEMBER_TERM_MONTHS_DEFAULT


def member_default_expiry(db, start=None):
    """What the enroll form pre-fills: today + the clinic's term."""
    return dates.add_months(start or clock.today(), member_term_months(db))


def member_expires_in_days(owner):
    """Days until this card lapses, or None if it never does / is not a
    member. Negative once it has lapsed, so a caller can tell the two apart."""
    if owner is None:
        return None
    try:
        if not owner["is_member"]:
            return None
        expires = dates.as_date(owner["member_expires_on"])
    except (KeyError, IndexError, TypeError):
        return None
    if not expires:
        return None
    return (expires - clock.today()).days


def owner_for_patient(db, patient_id):
    """The owner a patient belongs to — how visits, inpatient and boarding
    find the customer whose card applies."""
    return db.execute(
        "SELECT o.* FROM owners o JOIN patients p ON p.owner_id = o.id WHERE p.id=%s",
        (patient_id,)).fetchone()


def member_discount_for(db, owner):
    """(discount_percent, discount_source) for a bill being created for this
    owner. ('staff' defaults when there is no active card, or the programme
    is switched off with a rate of 0.)

    THE one place the card is turned into a discount, called by all four
    bill-creation sites so they cannot disagree about what "a member" means
    or read the rate four different ways.

    Note what does NOT happen here: the rate is never checked against
    auth.discount_cap_for(). That cap exists to bound STAFF discretion, and
    this is clinic policy rather than a staff decision — routing it through
    the cap would stop a receptionist whose cap is below the member rate from
    creating a member's bill at all. See features/REWARDS_CARD_PLAN.md §6.
    """
    if not is_active_member(owner):
        return Decimal(0), "staff"
    rate = member_discount_rate(db)
    if rate <= 0:
        return Decimal(0), "staff"
    return rate, "member"
