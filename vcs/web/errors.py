"""
The error handlers. A handler that follows a failed request marks the
transaction failed and rolls it back first (mark_transaction_failed(), audit
B12): the error page then reads the clinic's language and name from a
working connection, and teardown commits nothing half-written.
"""
import re
import traceback
import uuid

from flask import g, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

from vcs import clock, money
from vcs.config import MAX_UPLOAD_MB
from vcs.db import pool as dbmod
from vcs.errorlog import error_logger
from vcs.web.core import BadDate, BadNumber, BadPhone, flash, is_safe_local_path, money_setting_prompt


def mark_transaction_failed():
    """Call from any error handler that runs *after* an exception has been
    caught and turned into a rendered response — @app.errorhandler(Exception)
    swallows the exception before it can reach close_db()'s teardown
    argument, so without this, teardown sees exc=None and commits whatever
    the request had already written, half-finished transaction included.
    See ORPHANED_RECORDS_AUDIT.md F-01.

    It also rolls the transaction back now (audit B12). After an error inside
    Postgres the transaction is aborted, and the error page reads the
    clinic's language and name from that same connection: every read failed
    with InFailedSqlTransaction, so an Arabic clinic got an English error
    page under the default clinic name, and a second traceback was logged for
    every error. Rolled back, those reads work; teardown still rolls back
    whatever they touch."""
    g.db_failed = True
    db = g.get("db")
    if db is not None:
        try:
            db.rollback()
        except Exception:
            # A dead connection cannot be rolled back; the error page falls
            # back to its defaults, as it always did.
            pass


def forbidden(e):
    return render_template("error_403.html"), 403


def not_found(e):
    return render_template("error_404.html"), 404


def too_large(e):
    """Note: deliberately returns a plain 302 (not a 413 body) so this
    plays nicely with the universal upload XHR in upload-progress.js —
    browsers/XHR don't auto-follow a redirect that's paired with a non-3xx
    status code, and we want the flash message to actually surface on the
    page the user lands on, not get silently stranded in the session."""
    flash(_("That file is too large — the limit is %(MAX_UPLOAD_MB)s MB per upload.", MAX_UPLOAD_MB=MAX_UPLOAD_MB), "error")
    from urllib.parse import urlparse
    ref_path = urlparse(request.referrer or "").path
    target = ref_path if is_safe_local_path(ref_path) else None
    return redirect(target or url_for("main.dashboard"))


def _fallback_redirect():
    """Best-effort 'send them back where they came from' for the global
    validation safety net below — falls back to the dashboard if there's
    no safe referrer to bounce to."""
    ref = request.referrer or ""
    # referrer is a full URL; is_safe_local_path only wants the path part
    from urllib.parse import urlparse
    path = urlparse(ref).path if ref else ""
    if is_safe_local_path(path):
        return redirect(path)
    return redirect(url_for("main.dashboard"))


def handle_money_setting_not_chosen(e):
    """Backstop: money was about to be parsed, rounded or stored before an
    admin chose IQ or JO. Money routes are gated before they get this far
    (core.requires_money_setting); this makes a missed one a prompt, not a
    500, and rolls back anything the request had already written."""
    mark_transaction_failed()
    return money_setting_prompt()


def handle_bad_number(e):
    """Safety net for BadNumber. Most routes already catch this themselves
    with a field-specific message (e.g. 'Payment amount must be a valid
    number.'); this exists so a route that forgets to catch it degrades to
    a flashed error instead of an uncaught 500."""
    mark_transaction_failed()
    flash(_("One of the number fields on that form wasn't valid. Please check the amounts and try again."), "error")
    return _fallback_redirect()


def handle_bad_phone(e):
    """Safety net for BadPhone — same idea as handle_bad_number() above."""
    mark_transaction_failed()
    flash(_("That phone number doesn't look valid. Please check it and try again."), "error")
    return _fallback_redirect()


def handle_bad_date(e):
    """Safety net for BadDate — same idea as handle_bad_number() above.
    See ORPHANED_RECORDS_AUDIT.md F-04."""
    mark_transaction_failed()
    flash(str(e), "error")
    return _fallback_redirect()


def handle_http_exception(e):
    """Registered *after* the specific 403/404/413 handlers above, which
    Flask still prefers (exact status-code match beats a class-based one)
    — this only catches HTTPExceptions with no more specific handler:
    plain 400s (BadRequestKeyError from a missing request.form[...] key —
    see E-04), CSRFError (see E-17), and anything else in that family.
    Marks the transaction failed for non-GET requests so close_db()
    doesn't commit whatever a route had already written before aborting —
    see ORPHANED_RECORDS_AUDIT.md F-01. GET requests are excluded since
    they're not expected to have pending writes to roll back."""
    if request.method != "GET":
        mark_transaction_failed()
    if isinstance(e, CSRFError):
        # A CSRF failure is not the same thing as an expired session, and
        # saying it was sent people to a login screen they did not need --
        # after discarding what they had typed. Now that the token lifetime
        # matches the session lifetime this should be rare, but the two can
        # still come apart (a server restart rotates SECRET_KEY on some
        # deployments, invalidating every outstanding token while the browser
        # still holds a valid-looking cookie). Tell the truth about which one
        # happened, and only force a re-login when the session really is gone.
        if session.get("user_id"):
            flash(_("This page had been open too long to submit safely, so nothing was saved. "
                  "Please check what you entered and submit it again."), "error")
            return _fallback_redirect()
        flash(_("You were signed out while this page was open. Please sign in again — "
              "you may need to re-enter what you were working on."), "error")
        return redirect(url_for("main.login"))
    if e.code == 400:
        flash(_("That form was missing something the server needed. "
              "Please reload the page and try again."), "error")
        return _fallback_redirect()
    return e


def handle_numeric_out_of_range(e):
    """An absurdly large integer reached a numeric database column — a
    crafted `<int:...>` URL segment, a huge quantity/amount, an id nobody
    would legitimately have — instead of a bad-but-plausible value
    BadNumber's validation would have already caught client-side. Same
    friendly-degrade pattern as BadNumber/BadPhone above."""
    flash(_("That number is too large to be a valid value here."), "error")
    return _fallback_redirect()


def handle_pool_timeout(e):
    """The connection pool caps at a fixed size and require_login() calls
    get_db() on every single request — exhaustion doesn't degrade one
    page, it 500s everything at once. See ERROR_500_AUDIT.md E-03."""
    error_logger.error(f"DB pool exhausted on {request.method} {request.path}")
    if request.accept_mimetypes.best == "application/json" or request.path.startswith("/api/"):
        return jsonify({"error": _("The system is busy right now — try again in a moment.")}), 503
    return render_template("error_busy.html"), 503


_REDACT_PATTERNS = [
    # Postgres constraint-violation detail lines look like:
    #   Key (phone)=(0770123456) already exists.
    # Keep the column name (that's genuinely useful for debugging — it
    # tells you *which* field collided) but blank out the actual value.
    (re.compile(r"(Key \([^)]+\)=\()[^)]*(\))"), r"\1REDACTED\2"),
    # Email addresses, anywhere they appear in a message.
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED EMAIL]"),
    # Runs of 6+ digits (with optional spaces/dashes) — catches phone
    # numbers without needing to know the clinic's local phone format.
    (re.compile(r"\b\d[\d\-\s]{5,}\d\b"), "[REDACTED NUMBER]"),
]


def redact_sensitive(text):
    """Masks the specific patterns most likely to carry real patient/owner
    data inside an error message (see _REDACT_PATTERNS above) before that
    text is ever shown on a page or copied into a support message. Used
    only for what's displayed in the browser — logs/errors.log always
    keeps the original, unredacted text for real debugging."""
    if not text:
        return text
    for pattern, repl in _REDACT_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def handle_unexpected_error(e):
    """Catch-all for anything not handled above — a real bug, a DB outage,
    a third-party library error, etc. Flask walks the exception's class
    hierarchy to find the closest registered handler, so this only ever
    fires for exceptions with no more specific handler; 403/404/413/
    BadNumber/BadPhone (and any other HTTPException) are all matched
    before falling through to here and are passed through untouched.

    Design choice: the on-screen copy box is shown to *every* user, not
    gated by role. A reference ID + route + exception type alone isn't
    enough for anyone to actually diagnose a bug from — the real message
    and traceback are what matter, and whoever happens to hit a crash
    (not necessarily an Admin, and not necessarily technical) is the
    person who'll realistically be the one sending it along. Gating the
    useful part behind "Admin only" would defeat the point.

    What IS scrubbed: the raw exception *message* text specifically —
    because Postgres constraint-violation errors sometimes echo the
    actual offending value inline (e.g. "Key (phone)=(0770123456) already
    exists"), which would otherwise put a real patient/owner's data
    on-screen for anyone who hits that crash. redact_sensitive() masks
    those values (keeping the field name, which is what's actually useful
    for debugging) before anything is rendered. The unredacted original
    always goes to logs/errors.log regardless, for whoever has real
    server access and needs the exact value to reproduce something.
    """
    mark_transaction_failed()
    if isinstance(e, HTTPException):
        # No longer reachable now that @app.errorhandler(HTTPException) is
        # registered separately (Flask always prefers the more specific
        # handler) — left as defense-in-depth in case that registration is
        # ever removed.
        return e

    error_id = uuid.uuid4().hex[:8].upper()
    when = clock.now()
    tb_text = traceback.format_exc()

    error_logger.error(
        "\n".join([
            "=" * 78,
            f"Error ID:   {error_id}",
            f"Time:       {when.isoformat(timespec='seconds')}",
            f"User:       {session.get('username') or '(not logged in)'} ({session.get('role') or '-'})",
            f"Request:    {request.method} {request.path}",
            f"Query:      {request.query_string.decode('utf-8', 'replace') or '-'}",
            f"Referrer:   {request.referrer or '-'}",
            "-" * 78,
            tb_text.rstrip(),  # unredacted — this file is for whoever has server access
            "",
        ])
    )

    return render_template(
        "error_500.html",
        error_id=error_id,
        error_time=when.strftime("%Y-%m-%d %H:%M:%S"),
        request_line=f"{request.method} {request.path}",
        exc_type=type(e).__name__,
        exc_message=redact_sensitive(str(e)),
        traceback_text=redact_sensitive(tb_text),
    ), 500


def register(app):
    """Attach this module's hooks to the app, in the order they run."""
    app.register_error_handler(403, forbidden)
    app.register_error_handler(404, not_found)
    app.register_error_handler(413, too_large)
    app.register_error_handler(money.MoneySettingNotChosen, handle_money_setting_not_chosen)
    app.register_error_handler(BadNumber, handle_bad_number)
    app.register_error_handler(BadPhone, handle_bad_phone)
    app.register_error_handler(BadDate, handle_bad_date)
    app.register_error_handler(HTTPException, handle_http_exception)
    app.register_error_handler(dbmod.NumericValueOutOfRange, handle_numeric_out_of_range)
    app.register_error_handler(dbmod.PoolTimeout, handle_pool_timeout)
    app.register_error_handler(Exception, handle_unexpected_error)
