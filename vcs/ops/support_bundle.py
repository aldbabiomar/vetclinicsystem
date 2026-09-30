"""
The support bundle: a ZIP the vendor downloads from Developer -> Support to
see what is wrong without a remote session
(docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §11.2).

What goes in is chosen, never what stays out: the settings by an allowlist,
so a secret setting added later is left out without anyone remembering to
exclude it; system facts from system_info, which reads no clinic data; the
license's state, never the key. Every file then passes through the redactor
(redact.py), and the logs through its stricter pass for quoted values.
"""
import io
import json
import zipfile

from vcs import clock

# Settings safe to send: how the clinic is set up, not what it records and
# not a credential. Anything not listed stays out, including every setting
# added after this list was written.
ALLOWED_SETTINGS = (
    "clinic_name", "language", "time_zone", "money_setting", "theme_palette",
    "opening_date", "appt_start_time", "appt_end_time", "appt_slot_minutes",
    "audit_overdue_days", "expiry_soon_days", "member_discount_percent", "member_term_months",
    "backup_time", "backup_retention", "log_retention_days",
    "selfcheck_enabled", "selfcheck_backup_max_age_days", "heartbeat_install_id",
    "permissions_version", "license_max_seen_at",
)
LOG_LINES = 500

README = """\
VetClinicSystem support bundle
==============================

Made {made} for installation {install_id}, version {version}.

What is in it
- system.json        version, Python, operating system, database version and mode,
                     where the PostgreSQL tools were found, uptime
- settings.json      the clinic's settings from a fixed list of safe ones
- license.json       the license's state, its ID and dates, and the installation ID
- self_check.json    the latest daily self-check and its findings
- backups.json       the last backup, the last successful one, recent restores and the
                     last restore verification (file names only, never folders)
- schema.json        the database changes applied, and any still missing
- errors.log         the last {lines} lines of the error log
- updates.log        the last {lines} lines of the updates log

What is not in it
- No clinic records: no owners, patients, visits, bills, payments, sales, refunds,
  stock, users, or the clinic's change and sign-in logs.
- No secrets: not the license key, a Developer Pass, the update access token, the
  monitoring ping address, the database password, the app's secret key or its
  .env file.

Every file was passed through a redaction step that replaces these with
[redacted]: token-shaped strings, passwords inside web addresses, e-mail
addresses, long runs of digits (phone numbers), and in the logs anything in
quotes and the values the database quotes in its error details -- an error can
quote a name.

Redaction is careful but not perfect. You may open this ZIP and read every file
before sending it.
"""


def _settings(db):
    rows = db.execute("SELECT key, value FROM settings WHERE key = ANY(%s)", (list(ALLOWED_SETTINGS),)).fetchall()
    return {r["key"]: r["value"] for r in rows}


def _license():
    from vcs.licensing import state
    status = state.current()
    payload = status.payload or {}
    return {"state": status.state, "license_id": payload.get("license_id"),
            "issued_at": payload.get("issued_at"), "expires_at": payload.get("expires_at"),
            "warn_days": payload.get("warn_days"), "grace_days": payload.get("grace_days"),
            "install_id": payload.get("install_id")}


def build(db):
    """The bundle, as bytes. Reads nothing it does not name above."""
    from vcs import config
    from vcs.ops import redact, system_info
    from vcs.web.core import VERSION

    info = system_info.gather(db)
    secrets = redact.known_secrets(db)
    files = {
        "README.txt": README.format(made=clock.now().isoformat(timespec="seconds"),
                                    install_id=config.INSTALL_ID or "-", version=VERSION, lines=LOG_LINES),
        "system.json": {"app": info["app"], "database": info["database"]},
        "settings.json": _settings(db),
        "license.json": _license(),
        "self_check.json": info["self_check"],
        "backups.json": {**(info["backups"] if isinstance(info["backups"], dict) else {}),
                         "restore_verification": info["restore_verification"]},
        "schema.json": info["schema"],
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            if isinstance(content, str):
                z.writestr(name, redact.text(content, secrets))
            else:
                content = json.loads(json.dumps(content, default=str))      # moments and paths as text
                z.writestr(name, json.dumps(redact.structure(content, secrets), indent=2, ensure_ascii=False))
        for name, path in (("errors.log", system_info.error_log_path()),
                           ("updates.log", system_info.updates_log_path())):
            z.writestr(name, redact.log(redact.tail(path, LOG_LINES), secrets))
    return out.getvalue()


def filename():
    from vcs import config
    stamp = clock.now().strftime("%Y%m%d-%H%M%S")
    return f"vcs-support-{(config.INSTALL_ID or 'install')[:8]}-{stamp}.zip"
