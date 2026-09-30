"""
The clinic's settings table: one row per key, read with a default.
"""

# Settings whose value is a credential: the monitoring ping URL -- anyone
# holding it can send a fake ping and silence the alert that fires when the
# clinic's machine goes dark. The change log records only that one changed,
# the data export and the support bundle leave them out, and the redactor
# removes their values (licensing plan §13).
SECRET_KEYS = frozenset({"heartbeat_url"})


def get_setting(db, key, default=None):
    row = db.execute("SELECT value FROM settings WHERE key=%s", (key,)).fetchone()
    return row["value"] if row else default


def int_setting(db, key, default):
    """Never raises. Settings can arrive unvalidated (a restored backup, a
    hand edit), so a stored non-numeric value must degrade to the default
    rather than take down every page that reads it. See ERROR_500_AUDIT.md
    E-13."""
    try:
        return int(get_setting(db, key, default))
    except (TypeError, ValueError):
        return int(default)


def get_all(db):
    """Every stored setting, as {key: value}."""
    return {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM settings").fetchall()}
