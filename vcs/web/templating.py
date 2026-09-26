"""
What every template can use: the language (Flask-Babel's locale selector),
the display filters (|money, |qty, |tr, |localdate, ...), the globals, and
the context processors that feed base.html: the sidebar, the money setting,
the scripts' sentences, the CSP nonce.
"""
import traceback

from flask import current_app, g, request, session, url_for
from flask_babel import Babel, format_date, get_locale, gettext as _

from vcs import auth, clock, money
from vcs.config import BIND_PORT
from vcs.domain import logic
from vcs.errorlog import error_logger
from vcs.web import js_strings, nav
from vcs.web.core import (cached_dashboard_snapshot, csp_nonce, currency_label, display_date, display_number,
                          get_db, money_setting_label, to_arabic_indic_digits)


SUPPORTED_LOCALES = ("en", "ar")


def _select_locale():
    """The clinic's language, from the `language` setting.

    Clinic-wide rather than per-browser, and set in Settings beside the colour
    palette — the same shape as `theme_palette`, for the same reason: it is a
    property of the clinic, not of whoever happens to be at this screen.

    Wrapped defensively and cached per request. This runs on EVERY render,
    including the 500 page, and the most likely reason a page is failing is
    the database — a locale selector that raises there would replace the error
    page with a second error. It also runs before `/login`, where there is a
    request but no user.
    """
    if "vz_locale" in g:
        return g.vz_locale
    lang = "en"
    try:
        value = logic.get_setting(get_db(), "language", "en")
        if value in SUPPORTED_LOCALES:
            lang = value
    except Exception:
        pass
    g.vz_locale = lang
    return lang


def money_filter(v):
    """The one choke point every displayed money amount already passes
    through, which is why the Arabic-Indic substitution hooks in here rather
    than per template. Display only -- see core.to_arabic_indic_digits()."""
    formatted = money.fmt(v)
    if str(get_locale()) == "ar":
        formatted = to_arabic_indic_digits(formatted)
    return formatted


def qty_filter(v):
    """A count or measurement for display: "12", not "12.000"; "4.5", not
    "4.500"; Arabic-Indic digits under Arabic. Never on an <input> value."""
    formatted = logic.format_quantity(v)
    if str(get_locale()) == "ar":
        formatted = to_arabic_indic_digits(formatted)
    return formatted


def finding_filter(f):
    """Render a self-check finding in the current language.

    A finding is WRITTEN to `self_check_log` when the scheduler runs and READ
    BACK whenever someone opens the dashboard — possibly in a different
    language — so it is translated here rather than at check time. `msgid` is
    the English sentence with %(name)s placeholders and `args` fills them.

    Rows written before selfcheck carried a msgid fall back to `message`,
    which is English: exactly what they already displayed.
    """
    if not isinstance(f, dict):
        return f
    msgid = f.get("msgid") or f.get("message") or ""
    text = _(msgid)
    args = f.get("args") or {}
    if args:
        # Numeric values follow the Arabic-Indic decision like every other
        # number in a message (core.display_number). Anything that is not a
        # plain number is left exactly as it is: %(error)s and %(failures)s
        # carry file paths, OS error text and schema statements, where
        # rewriting the digits would corrupt the one detail that says what
        # went wrong.
        shown = {}
        for k, v in args.items():
            numeric = isinstance(v, (int, float)) or (
                isinstance(v, str) and v.replace(".", "", 1).isdigit())
            shown[k] = display_number(v) if numeric else v
        try:
            text = text % shown
        except (KeyError, TypeError, ValueError):
            # a translation whose placeholders do not match the arguments must
            # not take down the banner that is reporting a problem
            return f.get("message") or msgid
    return text


def tr_filter(v):
    """Translate a value that came out of the DATABASE for display.

    Stored enums -- case_status, payment_status, visit_type, species, sex,
    payment_method and friends -- are written to the database in English and
    read back as-is, so wrapping the template literal does nothing for them:
    the text on the page came from a row, not from the markup. This looks the
    stored value up in the catalogue and falls back to it unchanged when there
    is no entry, which is what keeps a value the clinic typed themselves (a
    custom species, say) from turning into a blank.

    Display only. The stored value is never changed, so every route that
    validates against the English constant keeps working.
    """
    if not v or not isinstance(v, str):
        return v
    return _(v)


def localdate_filter(d):
    """Read-only date display. Named `localdate` rather than `date` so it
    cannot shadow Jinja/Python `date` in a template that also uses it."""
    return display_date(d)


def code_filter(record_id, prefix):
    """{{ visit.id|code('V') }} -> V-00123 (logic.code)."""
    return logic.code(prefix, record_id)


def localtime_filter(v, fmt="%Y-%m-%d %H:%M"):
    """A stored moment, shown in the clinic's zone (the Time Zone setting),
    Arabic-Indic digits under Arabic. `|localtime("%H:%M:%S")` for a time."""
    formatted = logic.fmt_datetime(v, fmt)
    if formatted and str(get_locale()) == "ar":
        formatted = to_arabic_indic_digits(formatted)
    return formatted


def weekdate_filter(d):
    """Short "Mon 14 Sep" style date, in the current locale.

    strftime's %a/%b are C-locale and stay English no matter what Babel is
    set to, so they cannot be used for anything a user reads."""
    if not d:
        return ""
    # flask_babel.format_date resolves the locale from the request itself;
    # it takes no `locale=` keyword (that is babel.dates.format_date).
    formatted = format_date(d, "EEE d MMM")
    if str(get_locale()) == "ar":
        formatted = to_arabic_indic_digits(formatted)
    return formatted


def pagination_url(page, page_param="page"):
    """Builds a link to another page of the current view, preserving every
    other query-string filter (search terms, sort, date, etc)."""
    args = request.args.to_dict()
    args[page_param] = page
    return url_for(request.endpoint, **args)


def form_value(form, name, default=""):
    """Looks up a field's just-submitted value from `form` (the raw
    request.form MultiDict, passed to render_template only when re-showing
    a form after a validation failure) so a rejected submit can redisplay
    exactly what the person typed instead of a blank/stale field. `form` is
    None on a normal GET (and on any render that isn't redisplaying a
    rejected POST), in which case `default` (usually an existing record's
    DB value, for an edit form) is used instead. Deliberately returns the
    raw submitted string as-is — no int/float/Decimal parsing — so this is
    safe to use for every field type without reintroducing a type-coercion
    bug on a value that failed validation specifically because it wasn't a
    valid number/date in the first place (and without ever turning a
    Decimal-typed money field into a float along the way). Checked with a
    truthiness test rather than `is None` because a template that never
    received a `form=` kwarg at all (the normal GET-request case) gets
    Jinja2's Undefined sentinel here, not Python None — and Undefined has
    no .get() method."""
    if not form:
        return default
    return form.get(name, default)


def nav_active(*endpoints):
    """'active' when the current page is one of these endpoints, for the
    sidebar. Full endpoint names -- a blueprint route is
    'clinical.visits_list' -- checked against the ones the app registers, so
    a name without its prefix raises at the first render instead of quietly
    never matching. That is how every sidebar link to a blueprint page lost
    its highlight when the routes moved into blueprints: base.html compared
    request.endpoint with 'visits_list', which it never is."""
    unknown = [e for e in endpoints if e not in current_app.view_functions]
    if unknown:
        raise ValueError(f"nav_active(): not an endpoint: {unknown}")
    return "active" if request.endpoint in endpoints else ""


def inject_money_setting():
    """The active money setting for templates: `money_setting` (None before
    one is chosen — money forms render a prompt instead), the Clean Up cap,
    and the values money.js needs so live previews in the browser round
    exactly like the server does."""
    m = money.current()
    return dict(
        money_setting=m,
        CLEANUP_CAP=display_number(money.fmt(m.cleanup_cap)) if m else "",
        money_js=({"code": m.code, "minorUnits": m.minor_units, "cashUnit": str(m.cash_unit),
                   "quantum": str(m.quantum), "phoneCountryCode": m.phone_country_code,
                   "phoneLocalLength": m.phone_local_length} if m else None),
    )


def inject_nav():
    """The sidebar's groups and links this person can open (nav.py, audit
    P1). From the session's permissions -- no table read."""
    return dict(nav_groups=nav.visible(session.get("permissions") or []))


def inject_js_strings():
    """The static scripts' sentences, in the clinic's language, for base.html
    to hand them as window.VZ_I18N (audit F2; js_strings.py)."""
    return dict(vz_i18n={s: _(s) for s in js_strings.JS_STRINGS})


def inject_csp_nonce():
    """Deliberately separate from inject_globals().

    That one talks to the database and carries a fallback path for when the
    database is unreachable. A nonce dropped on that fallback path would block
    every script on the 500 page — the page you least want to break, and the
    one least likely to be looked at before release. This processor cannot
    fail for that reason because it touches nothing but `g`.
    """
    return dict(csp_nonce=csp_nonce())


def inject_globals():
    """Note: wrapped defensively — this context processor runs on every
    single page render (it feeds the sidebar/nav), including error pages.
    If the database itself is the reason a page is failing (its most
    likely failure mode), we still want the 500/403/404 pages to render
    with sane fallback values instead of throwing a second exception while
    trying to *show* the first one."""
    try:
        db = get_db()
        clinic_name = logic.get_setting(db, "clinic_name", "VetClinicSystem")
        clinic_location = logic.get_setting(db, "clinic_location", "Amman, Jordan")
        ctx = dict(clinic_name=clinic_name, clinic_location=clinic_location, today=clock.today().isoformat(),
                   current_role=session.get("role"), current_username=session.get("username"),
                   session_user_id=session.get("user_id"))
        if session.get("user_id"):
            snap = cached_dashboard_snapshot(db)
            ctx["alert_count"] = (
                len(snap["due_today"]) + len(snap["low_stock"]) +
                len(snap["overdue_audit"]) + len(snap["expiring"]) +
                len(snap["wellness_due"])
            )
        else:
            ctx["alert_count"] = 0
        return ctx
    except Exception:
        error_logger.error(
            "inject_globals() itself failed (likely DB unreachable) while "
            "rendering %s %s — falling back to static nav values.\n%s",
            request.method, request.path, traceback.format_exc()
        )
        return dict(
            clinic_name="VetClinicSystem", clinic_location="",
            today=clock.today().isoformat(),
            current_role=session.get("role"), current_username=session.get("username"),
            alert_count=0, session_user_id=session.get("user_id"),
        )


def register(app):
    """Attach this module's hooks to the app, in the order they run."""
    app.add_template_filter(money_filter, "money")
    app.add_template_filter(qty_filter, "qty")
    app.add_template_filter(finding_filter, "finding")
    app.add_template_filter(tr_filter, "tr")
    app.add_template_filter(localdate_filter, "localdate")
    app.add_template_filter(code_filter, "code")
    app.add_template_filter(localtime_filter, "localtime")
    app.add_template_filter(weekdate_filter, "weekdate")
    app.context_processor(inject_money_setting)
    app.context_processor(inject_nav)
    app.context_processor(inject_js_strings)
    app.context_processor(inject_csp_nonce)
    app.context_processor(inject_globals)
    Babel(app, locale_selector=_select_locale)
    # Flask-Babel 4.x does not register get_locale() as a Jinja global on its own,
    # and base.html needs it on the very first line to set <html lang>/<dir>. The
    # symptom of missing it is every page 500-ing at that line, including /login.
    app.jinja_env.globals["get_locale"] = get_locale
    # currency_label() lives in core.py (routes need it for flashed messages too);
    # exposed to every template here. It follows the money setting: IQD / د.ع or
    # JOD / د.أ, and empty before one is chosen.
    app.jinja_env.globals["currency_label"] = currency_label
    app.jinja_env.globals["pagination_url"] = pagination_url
    app.jinja_env.globals["has_permission"] = auth.has_permission
    app.jinja_env.globals["bind_port"] = BIND_PORT
    # A count or measurement as an <input> value or placeholder: "12", not
    # "12.000" — and Western digits, unlike |qty (an input is parsed back).
    app.jinja_env.globals["qty_value"] = logic.format_quantity
    # The hidden expected_updated_at an edit form carries (clock.token).
    app.jinja_env.globals["edit_token"] = clock.token
    # A URL a script completes with a record id at click time is built with this
    # number in the id's place, then .replace()d: an <int:…> route cannot take a
    # text placeholder, and the largest id is never a real one that matters.
    app.jinja_env.globals["ID_SLOT"] = 2147483647
    app.jinja_env.globals["fv"] = form_value
    app.jinja_env.globals["nav_active"] = nav_active
    # logic.format_percent() strips the meaningless decimal tail; display_number()
    # converts to Arabic-Indic digits when the locale is ar. Composed here rather
    # than in logic.py, which deliberately has no Flask imports — and composed at
    # all because core.display_number()'s own docstring is the rule: a number on
    # its way into a user-facing message converts, or one sentence carries two
    # numeral systems.
    app.jinja_env.globals["format_percent"] = lambda v: display_number(logic.format_percent(v))
    app.jinja_env.globals["money_step"] = money.input_step
    app.jinja_env.globals["money_setting_label"] = money_setting_label
