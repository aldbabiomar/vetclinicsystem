"""
The clinic's settings table: one row per key, read with a default.
"""



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
