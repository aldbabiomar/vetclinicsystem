"""
The request layer's shared pieces: what the blueprints and the app's own
modules (hooks, errors, templating) all need -- the request's database
connection, form parsing and validation (parse_money, clean_date,
normalize_phone, the Bad* exceptions, the MAX_* bounds), pagination,
flashing and display helpers.

A blueprint imports from here and from the rest of `vcs`, never from the
factory that registers it (vcs/web/factory.py): that direction would be
circular.
"""
import os

from vcs.paths import ROOT
import secrets
import re
import socket
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask_babel import gettext as _
from flask import flash as _flask_flash, g, render_template, request, url_for

from vcs.db import pool as dbmod
from vcs import jobs
from vcs.domain import logic
from vcs import messages
from vcs import money
BASE_DIR = ROOT

# On the versioned-release layout (VETCLINICSYSTEM_DATA_DIR set by the
# launcher script — see updater.py / setup.py --enable-updates), the .env, the
# logs and the uploads live in the persistent data dir rather than beside this
# file, whose folder an in-app update replaces and later prunes.
DATA_DIR = os.environ.get("VETCLINICSYSTEM_DATA_DIR")

_version_path = os.path.join(BASE_DIR, "VERSION")
VERSION = open(_version_path).read().strip() if os.path.exists(_version_path) else "unknown"

# Separate from (and shorter than) DB_POOL_TIMEOUT_SECONDS, which the pool
# itself still uses for background/maintenance callers (dbmod.connect()).
# During a full DB outage every request that reaches get_db() would otherwise
# block for the pool's full default wait before failing — tying up one of
# Waitress's worker threads that whole time and making the app look hung rather
# than degraded.
DB_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("DB_REQUEST_TIMEOUT_SECONDS", "4"))


def get_db():
    """The request-scoped connection. Borrowed from the pool on first use and
    returned by close_db() (vcs/web/hooks.py)."""
    if "db" not in g:
        g.db = dbmod.getconn(timeout=DB_REQUEST_TIMEOUT_SECONDS)
    return g.db


def lan_address():
    """This machine's address on the clinic LAN, for the Settings page's
    "reach it from another device at ..." line. Falls back to loopback rather
    than raising when there is no route out."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# Shared request-layer helpers
# ---------------------------------------------------------------------------
# Form parsing and validation, pagination, and the background-job render shell.
# They live here, not beside the factory, because a blueprint must never import
# the module that registers it. They are pure helpers over `request` and the parsed
# values -- no route, no database of their own.
#
# Money is parsed through money.py, which takes its precision, bounds and
# rounding from the clinic's money setting (IQ or JO). Nothing here knows which
# one is active. See money.py for the rules and COMPARISON.md §1.1 for why the
# two predecessor apps' money models used to differ.
class BadNumber(ValueError):
    """Raised by parse_money() when a submitted field isn't blank but also
    isn't a valid number — lets the route catch it once and show a friendly
    error instead of a raw ValueError (Python) or invalid-input-syntax
    error (Postgres) turning into an uncaught 500."""


def parse_money(raw, required=False):
    """A typed money amount -> Decimal, at the money setting's precision
    (whole dinars under IQ, fils under JO). Blank collapses to None (or
    BadNumber when required). Text, NaN, Infinity and anything past the
    setting's max_amount raise BadNumber — NaN in particular, because every
    `x > cap` check downstream silently evaluates False against it.

    The value is rounded to the entry precision BEFORE any caller compares
    it, so `amount > 0` sees what the database will store.

    Raises money.MoneySettingNotChosen if no money setting has been chosen —
    money routes are gated before this (requires_money_setting), so reaching
    it means a route was missed; vcs/web/errors.py turns it into a prompt, not a 500.

    Only for MONEY. Percentages go through parse_percent(), and counts and
    measurements (quantities, weights, stock) through parse_quantity() —
    rounding a 4.2 kg weight to a whole number because the clinic works in
    whole dinars would be a bug.
    """
    if raw is None or str(raw).strip() == "":
        if required:
            raise BadNumber("required")
        return None
    try:
        return money.parse(raw)
    except money.BadAmount as e:
        raise BadNumber(str(e))


PERCENT_QUANTUM = Decimal("0.01")  # discount_percent is NUMERIC(5,2)


def parse_percent(raw, required=False):
    """A typed percentage -> Decimal to two places (the column's scale), so a
    discount is computed with exactly the value that gets stored. Range
    checks (0-100, the role cap) stay with the caller."""
    if raw is None or str(raw).strip() == "":
        if required:
            raise BadNumber("required")
        return None
    try:
        val = Decimal(str(raw).strip())
    except InvalidOperation:
        raise BadNumber(raw)
    if not val.is_finite() or abs(val) > 1000:
        raise BadNumber(raw)
    return val.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


MAX_INT = 2_147_483_647  # widest value any INTEGER column in this schema can hold


# In logic.py (which core imports); re-exported so routes keep importing it here.
parse_id = logic.parse_id


def parse_int(raw, required=False):
    """Same shape as parse_money(), for INTEGER columns (e.g. lead_time_days).
    Blank collapses to None; non-numeric input raises BadNumber instead of
    reaching the DB and surfacing as a raw Postgres cast error. Bounded at
    MAX_INT so an oversized value degrades to a flash instead of a raw
    Postgres overflow error. See ERROR_500_AUDIT.md E-06."""
    if raw is None or str(raw).strip() == "":
        if required:
            raise BadNumber("required")
        return None
    try:
        val = int(raw)
    except ValueError:
        raise BadNumber(raw)
    if abs(val) > MAX_INT:
        raise BadNumber(f"{raw} is too large — check for a typo.")
    return val


class BadDate(ValueError):
    """Raised by clean_date() when a submitted date field isn't blank but
    also isn't a valid ISO date — lets the route catch it once and show a
    friendly error instead of a raw ValueError/Postgres 'invalid input
    syntax for type date' turning into an uncaught 500. More importantly:
    this is what stops an empty string ('') from ever reaching a date
    column. '' is not NULL, so a downstream query that assumes a date
    column is only ever 'a real date or NULL' (e.g. `WHERE date IS NOT
    NULL` followed by `date::date`) breaks the moment it meets one. That is
    not hypothetical: a blank date reaching a nullable date column is what
    made reports skip bills entirely and comparisons behave as though the
    row had no date at all."""


def clean(v):
    """Collapse '' / whitespace-only to None; otherwise return the
    trimmed value. Use this on read-side filters and any field where
    blank-vs-missing are supposed to mean the same thing but format
    validation would be too strict (e.g. a bad ?date= query param should
    degrade to 'no results', not a hard error)."""
    if v is None:
        return None
    v = v.strip()
    return v or None


def strict_date(v):
    """The one parser for a date that arrives in a request (audit B1):
    exactly YYYY-MM-DD naming a real day, as a `date`; None when absent or
    blank; ValueError for anything else.

    Not date.fromisoformat(): since Python 3.11 it accepts the whole ISO 8601
    family -- 2026-W39-4 (an ISO week), 20260925, 2026-09-25T10:00 -- and
    routes that validated with it passed the raw text on to Postgres, which
    rejects the week form (a 500) and matches the others against nothing (an
    empty page read as "no data"). Not strptime() alone either: it accepts
    2026-9-5. The value must be the date's own ISO spelling.

    Stored values (a DATE or timestamptz column, already a date/datetime)
    are read with logic.as_date(), never this."""
    v = clean(v) if isinstance(v, str) or v is None else v
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError(f"not a YYYY-MM-DD date: {v!r}")
    d = datetime.strptime(v, "%Y-%m-%d").date()
    if d.isoformat() != v:
        raise ValueError(f"not a YYYY-MM-DD date: {v!r}")
    return d


def strict_month(v):
    """A month from a request: exactly YYYY-MM naming a real month (01-12),
    returned as that text; None when absent or blank; ValueError otherwise."""
    v = clean(v) if isinstance(v, str) or v is None else v
    if v is None:
        return None
    if not isinstance(v, str) or len(v) != 7:
        raise ValueError(f"not a YYYY-MM month: {v!r}")
    strict_date(v + "-01")
    return v


def clean_date(v, field="date"):
    """Same as clean(), but also validates the value is a real
    YYYY-MM-DD date if present (strict_date). Use this on WRITE paths (form
    -> DB) where a bad value should be rejected outright."""
    try:
        d = strict_date(v)
    except ValueError:
        # The field's label, translated where the catalogue has it ("Entry
        # Date", "Dismissal Date", ...), in a translated sentence (audit F1).
        raise BadDate(_("%(field)s must be a valid date (YYYY-MM-DD).", field=_(field.replace("_", " ").title())))
    return d.isoformat() if d else None


def has_negative(*values):
    """True if any of the given already-parsed numbers (None is fine —
    skipped, since an absent value isn't a negative one) is below zero.
    Used to reject negative cost/sale prices, weights, and unit costs at
    the point of entry — parse_money()/parse_int() already reject NaN/
    Infinity/non-numeric input, but a plain negative number passes those
    checks fine, so this is the separate guard for fields where negative
    is never a valid real-world value."""
    return any(v is not None and v < 0 for v in values)


# The phone format follows the money setting: an IQ clinic's local numbers
# are +964 with 10 digits after the trunk 0, a JO clinic's +962 with 9 (see
# money.MoneySetting). A small self-contained normalizer rather than a
# general-purpose library — simpler, and no extra dependency to install.
# Before the money setting is chosen there is no local format to assume, so
# only a full international number (+964..., 00962...) is accepted.
class BadPhone(ValueError):
    """Raised by normalize_phone() when a submitted phone number isn't blank
    but also can't be confidently normalized to E.164 — lets the route show
    a friendly error instead of silently saving something WhatsApp/wa.me
    links won't be able to use later."""


def normalize_phone(raw):
    """
    Normalizes a phone number to E.164 (+<countrycode><number>). Returns
    None for a blank/optional field. Accepts a local number with a leading
    trunk 0 (e.g. "0791234567"), a number already carrying the country
    code (with or without a leading + or 00), or raises BadPhone if what
    was typed doesn't resemble a real phone number at all.

    A number with no explicit +/00 prefix is ambiguous — there's no way to
    tell "a local number, missing its usual leading 0" from "a foreign
    number, typed without its country code" from the digits alone — so
    that case is held to the money setting's strict local digit count (a real
    local mobile number's actual length) rather than just "looks like
    *some* valid-length phone number." Without this, an implausibly short
    entry (a typo, a truncated paste) or a foreign number missing its
    country code both silently normalize into *something* that passes a
    generic E.164 length check, just not the number anyone actually meant
    — and it's stored with no error, discovered only when a WhatsApp
    message to it fails later. A number given WITH an explicit +/00 is
    unambiguous (the owner is intentionally recording a foreign contact
    number), so that case only needs the general E.164 sanity check.
    """
    if raw is None or not str(raw).strip():
        return None
    raw = str(raw).strip()
    m = money.current()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        raise BadPhone(raw)
    if raw.startswith("+"):
        candidate = "+" + digits
        if re.fullmatch(r"\+[1-9]\d{7,14}", candidate):
            return candidate
    elif digits.startswith("00"):
        candidate = "+" + digits[2:]
        if re.fullmatch(r"\+[1-9]\d{7,14}", candidate):
            return candidate
    elif m is not None:
        code, length = m.phone_country_code, m.phone_local_length
        if digits.startswith("0"):
            local = digits[1:]
        elif digits.startswith(code) and len(digits) == len(code) + length:
            local = digits[len(code):]
        else:
            local = digits
        if len(local) == length:
            return "+" + code + local
    raise BadPhone(raw)


# ---------------------------------------------------------------------------
# Pagination — 50 rows/page across every list view in the system
# ---------------------------------------------------------------------------
PER_PAGE = 50


MAX_PAGE = 100_000  # generous for any realistic list size; keeps page_offset() well inside Postgres's integer range


def get_page():
    try:
        p = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        p = 1
    return min(max(1, p), MAX_PAGE)


def page_count(total, per_page=PER_PAGE):
    return max(1, (total + per_page - 1) // per_page)


def page_offset(page, per_page=PER_PAGE):
    return (page - 1) * per_page


# ---------------------------------------------------------------------------
# Slow report pages (Insights, Retention, Consignment Overview): background
# job + loading shell
# ---------------------------------------------------------------------------
def _render_with_progress(template_name, step_labels, compute_fn, page_title, page_note=None):
    """
    Shared pattern for report pages slow enough to need a progress bar
    (Insights, Retention, Consignment Overview). On first visit, starts a
    background job running compute_fn(update) (which must return the dict
    of template variables the real page needs) and renders a lightweight
    loading shell instead; once the client's poll reports the job done,
    the shell redirects back to this same URL with ?job_id=..., and THIS
    SAME route then picks up the finished job's already-computed result
    and renders the real page.

    The slow part only ever runs once, in the background thread; the
    actual page render always happens inside a normal request, so
    session/g/url_for/current-user context all work exactly as they
    always do (rendering from a background thread would have none of
    that, which is why the heavy lifting and the rendering are kept in
    two separate steps like this rather than trying to render from the
    thread directly).
    """
    job_id = request.args.get("job_id")
    if job_id:
        result = jobs.take_result(job_id)
        if result is not None:
            return render_template(template_name, **result)
        # Not found / not finished yet / already consumed (a stale or
        # reloaded link) — fall through and start a fresh job below
        # rather than erroring, since any of those are recoverable just
        # by trying again.

    new_job_id = jobs.start(step_labels, compute_fn)
    # Preserve whatever other query params got here (e.g. ?page=2 on
    # Retention) rather than dropping them — built as a real url_for() call
    # so the client just navigates to a finished URL rather than having to
    # reconstruct it with string concatenation.
    other_args = {k: v for k, v in request.args.items() if k != "job_id"}
    reload_url = url_for(request.endpoint, job_id=new_job_id, **other_args)
    return render_template("_loading_shell.html", job_id=new_job_id, reload_url=reload_url,
                            page_title=page_title, page_note=page_note)


def required_field(f, key, label):
    """Returns the stripped value, or None (with a flash already set) if
    it's missing or blank. Covers both the KeyError case (f[key] on a
    missing key raises BadRequestKeyError) and the empty-string case,
    which NOT NULL alone does not. See ERROR_500_AUDIT.md E-04."""
    val = (f.get(key) or "").strip()
    if not val:
        flash(_("%(label)s is required.", label=label), "error")
        return None
    return val


# How money can change hands, as stored. Every form that records a payment,
# a sale, a refund or a supplier payment offers exactly these, and the
# database refuses anything else (CHECK constraints in the baseline).
PAYMENT_METHODS = ["Cash", "Card", "Transfer"]


class BadPaymentMethod(ValueError):
    """Raised by clean_payment_method()."""


def clean_payment_method(v, required=True):
    """The one check on how money changed hands (audit B10): one of
    PAYMENT_METHODS, or None for a blank one when the field is optional (a
    supplier payment may leave it unrecorded). Anything else raises
    BadPaymentMethod.

    Only the refund routes used to check it; the POS, the three bill payment
    routes and the two supplier payment routes stored whatever was posted,
    including nothing. The Cash Register sums the drawer by method, so a
    value outside the list was money in no bucket: the day's cash total was
    wrong with nothing on screen to say so."""
    v = clean(v) if isinstance(v, str) or v is None else v
    if v is None and not required:
        return None
    if v not in PAYMENT_METHODS:
        raise BadPaymentMethod(v)
    return v


def payment_method_message():
    """The refusal for a payment without a valid method."""
    return _("Pick how this was paid: %(methods)s.", methods=", ".join(_(m) for m in PAYMENT_METHODS))


def discount_percent_error(percent, cap):
    """Range-checks an already-parsed discount percent against the current
    user's role cap. Shared by the visit/inpatient/boarding/POS discount-save
    routes so the bound comparison lives in exactly one place — it was written
    out four times, which is four chances to change three of them."""
    if percent > cap or percent < 0:
        return _("Discount must be between 0%% and %(cap)s%% for your role.", cap=display_number(cap))
    return None


def cleanup_amount_error(new_amount, existing_amount, balance):
    """Range-checks a Clean Up submission. Returns an error string, or None.

    Shared by the four payment surfaces, which were each carrying their own
    copy of these three checks. The two legitimate per-site differences are
    arguments rather than special cases:

      * POS passes existing_amount=0 — a brand-new sale has no prior Clean Up
        to accumulate against, unlike the other three, which can be paid off
        across several submissions.
      * Boarding passes the balance as it would stand AFTER this submission's
        discount, not before, so a discount-and-clean-up in one click cannot
        write off more than the discounted bill.

    The cap comes from the money setting (1,000 under IQ, 1.000 under JO).
    """
    cap = money.require().cleanup_cap
    if new_amount < 0:
        return _("Clean Up amount can't be negative.")
    if existing_amount + new_amount > cap:
        return _("Clean Up on this bill can't exceed %(cap)s %(currency)s in total.",
                 cap=display_money(cap), currency=currency_label())
    if new_amount > balance:
        return _("Clean Up can't exceed the remaining balance.")
    return None


def currency_label():
    """The currency as it should READ in the active language: the Arabic
    abbreviation in Arabic (د.ع / د.أ), the Latin ISO code otherwise (IQD /
    JOD). Empty before a money setting is chosen. PDFs never use this — they
    stay English with the Latin code (ARABIC_LOCALIZATION_PLAN.md §0)."""
    m = money.current()
    if m is None:
        return ""
    from flask_babel import get_locale
    return m.label_ar if str(get_locale()) == "ar" else m.currency


def money_setting_label(code):
    """The translated name of a money setting, for Settings and messages.
    Spelled out here (not built from money.py's data) so the extractor sees
    both strings."""
    if code == "IQ":
        return _("IQ — Iraqi dinar (IQD)")
    if code == "JO":
        return _("JO — Jordanian dinar (JOD)")
    return code or ""


def display_money(amount):
    """money.fmt() with Arabic-Indic digits when the locale is Arabic — the
    same choke point as the |money template filter, for amounts that go into
    a flashed message."""
    return display_number(money.fmt(amount))


def flash_cash_denomination_warning(amount):
    """A gentle, non-blocking heads-up when a typed payment, refund or payout
    can't be paid exactly in cash (under IQ: not a multiple of the 250-dinar
    note). It still saves as entered; this exists because the Cash Register's
    end-of-day audit compares against physically counted notes, so an odd
    amount can make an otherwise-correct day look slightly off. Never fires
    under JO, whose cash unit is the fils."""
    m = money.current()
    if m is not None and amount is not None and not money.is_cash_payable(amount, m):
        flash(_("Heads up: this amount isn't a multiple of %(unit)s %(currency)s. It'll still save "
                "as entered, but the Cash Register's end-of-day audit compares against physical "
                "notes, so an odd amount here can make an otherwise-correct day look slightly off.",
                unit=display_money(m.cash_unit), currency=currency_label()), "warning")


def flash_price_rounding_notice(sale_price):
    """After saving a Price List price that can't be paid exactly in cash
    (under IQ: not a multiple of the 250-dinar note): totals including it are
    rounded at checkout automatically, but the admin should know. Never fires
    under JO."""
    m = money.current()
    if m is not None and sale_price is not None and not money.is_cash_payable(sale_price, m):
        flash(_("Heads up: this price isn't a multiple of %(unit)s %(currency)s — totals including this "
                "item are rounded to it at checkout (this is handled automatically).",
                unit=display_money(m.cash_unit), currency=currency_label()), "warning")


def requires_money_setting(view):
    """Gate for every route that records or shows money.

    Until an admin chooses IQ or JO in Settings, money cannot be recorded —
    it would have no currency. A request that needs it is sent to Settings
    (anyone who can change it) or back to the dashboard (everyone else) with
    a message saying why, instead of reaching money.require() and failing
    deeper down."""
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if money.current() is None:
            return money_setting_prompt()
        return view(*args, **kwargs)
    return wrapped


def money_setting_prompt():
    """The response for a money screen opened before the money setting is
    chosen. Shared by requires_money_setting and the error handler (vcs/web/errors.py) for
    money.MoneySettingNotChosen, so both say the same thing."""
    from flask import redirect, session
    if "manage_settings" in (session.get("permissions") or []):
        flash(_("Choose the clinic's money setting (IQ or JO) first — nothing with a price or "
                "an amount can be recorded until it is set."), "error")
        return redirect(url_for("settings.settings_page") + "#money-setting")
    flash(_("Billing, payments and prices aren't available yet: an admin needs to choose the "
            "clinic's money setting in Settings first."), "error")
    return redirect(url_for("main.dashboard"))


def parse_quantity(raw, required=False):
    """Same shape as parse_money(), for NUMERIC(10,3) quantity columns
    (POS cart, refund lines, inpatient billing) — bounded at that column
    type's own ceiling rather than a money amount's wider one. See
    ERROR_500_AUDIT.md E-06."""
    if raw is None or str(raw).strip() == "":
        if required:
            raise BadNumber("required")
        return None
    try:
        val = Decimal(str(raw).strip())
    except InvalidOperation:
        raise BadNumber(raw)
    if not val.is_finite():
        raise BadNumber(raw)
    if abs(val) > MAX_QUANTITY:
        raise BadNumber(f"{raw} is too large — check for a typo.")
    return val


def clean_date_filter(v):
    """For a read-side ?date= filter that's about to be compared against a
    real DATE column (or used as a LIKE prefix against a text timestamp) —
    clean()'s intent ("a bad filter should degrade to no hard error") isn't
    actually met by clean() alone, since a malformed-but-non-empty string
    still reaches the query. A DATE column then raises a raw Postgres cast
    error instead of degrading to anything. Returns the value only if it's
    a real YYYY-MM-DD date; a malformed one is silently dropped (treated
    the same as no filter at all) rather than either crashing or being
    passed through as a broken filter."""
    try:
        d = strict_date(v)
    except ValueError:
        return None
    return d.isoformat() if d else None


def date_filter_arg(name="date", message=None):
    """clean_date_filter() with a heads-up for the user.

    Dropping a malformed filter silently is the right default for a shared
    context builder that several routes re-render through (see
    _refunds_page_context) — a stray ?date= shouldn't add noise on top of a
    real validation error. But on the page the user actually asked for,
    silence is indistinguishable from "the filter worked and there's just a
    lot of data". IQ has always said so on these pages; this is what brings
    JO's list pages in line. Only speaks up when something was actually
    thrown away — an absent or empty ?date= is not an error."""
    raw = request.args.get(name)
    value = clean_date_filter(raw)
    if value is None and clean(raw) is not None:
        flash(message or _("That date wasn't valid — showing all dates instead."), "error")
    return value


MAX_QUANTITY = Decimal("9999999.999")  # widest value any NUMERIC(10,3) column can hold


def flash(message, category="message"):
    """flask.flash, with a messages.Msg put into the clinic's language first
    (audit F1). A flashed message is stored in the session as plain text, so
    a Msg -- from a backup, a restore, an upload -- has to be translated on
    the way in, or it shows in English. Every route imports flash from here;
    tests/test_untranslated_messages.py holds them to it."""
    _flask_flash(shown(message), category)


def list_join(items):
    """Names joined for a sentence, with the comma of the clinic's language
    ("، " in Arabic)."""
    from flask_babel import get_locale
    try:
        sep = "، " if str(get_locale()) == "ar" else ", "
    except RuntimeError:
        sep = ", "
    return sep.join(str(i) for i in items)


def shown(message):
    """A message for the page, in the clinic's language (audit F1). A
    messages.Msg -- made by code that has no request, or is shown later -- is
    translated now; anything else is shown as it is."""
    if isinstance(message, messages.Msg):
        args = {k: shown(v) if isinstance(v, messages.Msg)
                else display_number(v) if isinstance(v, (int, Decimal)) and not isinstance(v, bool) else v
                for k, v in message.args.items()}
        return _(message.msgid, **args)
    return message


def display_date(d):
    """A date for a message or a page: the clinic-zone day, in Arabic-Indic
    digits when the clinic's language is Arabic. The |localdate filter is
    this function."""
    formatted = logic.fmt_date(d) if not isinstance(d, str) else d
    return display_number(formatted) if formatted else formatted


def csp_nonce():
    """The per-request nonce that lets the Content-Security-Policy drop
    'unsafe-inline' from script-src.

    Generated on first use and cached on `g`, so the value the templates
    render into `<script nonce="...">` and the value `add_security_headers()`
    writes into the header are necessarily the same one — deriving them
    separately is the classic way to ship a policy that blocks every script on
    the page. Templates reach it through the `csp_nonce` context variable.

    A nonce does NOT authorise inline event handlers, and a browser that sees a
    nonce ignores 'unsafe-inline' entirely, so `on*=` attributes had to go
    first; `static/behaviors.js` is what they became.
    """
    value = getattr(g, "_csp_nonce", None)
    if value is None:
        value = secrets.token_urlsafe(16)
        g._csp_nonce = value
    return value


# ---------------------------------------------------------------------------
# Arabic-Indic numerals — display only
# ---------------------------------------------------------------------------
# Defined in logic.py (which cannot import this module — core imports it)
# and re-exported here, so there is one digit table.
to_arabic_indic_digits = logic.to_arabic_indic_digits


def display_quantity(v):
    """A count or measurement on its way into a message: trailing zeros
    dropped (logic.format_quantity), Arabic-Indic digits under Arabic."""
    return display_number(logic.format_quantity(v))


def display_number(v):
    """A number on its way INTO a user-facing message.

    The Arabic-Indic decision covers display text, and a flash message is
    display text -- without this, "الخصم بين ٠٪ و 25٪" mixes both numeral
    systems in one sentence. Same boundary as to_arabic_indic_digits(): this
    is for messages only, never for a value that will be parsed back.
    """
    from flask_babel import get_locale
    try:
        if str(get_locale()) == "ar":
            return to_arabic_indic_digits(str(v))
    except RuntimeError:
        pass          # outside a request context: plain digits
    return v


def is_safe_local_path(path):
    """Only allow redirects to relative, in-app paths (no scheme/host)."""
    if not path:
        return False
    if not path.startswith("/"):
        return False
    if path.startswith("//"):
        return False
    if "\\" in path:
        return False
    return True


def cached_dashboard_snapshot(db):
    """dashboard_snapshot() scans several tables. It's needed on every page
    (for the nav alert badge) and again on the dashboard route itself —
    cache it per-request so it only runs once."""
    if "dash_snap" not in g:
        g.dash_snap = logic.dashboard_snapshot(db)
    return g.dash_snap
