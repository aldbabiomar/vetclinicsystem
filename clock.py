"""
The clinic's clock: what "now" and "today" mean, and in which time zone.

The zone is, in order:
  1. the Time Zone setting (settings.time_zone), if an admin chose one;
  2. otherwise the money setting's zone (IQ: Asia/Baghdad, JO: Asia/Amman);
  3. before a money setting is chosen, the computer's own zone.

Every "now" and "today" in the application comes from here — never from
datetime.now() or date.today(), which read the computer's zone and would
disagree with the setting the moment the two differ. Stored event times are
`timestamptz`; the database session is put in the same zone (apply_to), so a
`::date` cast in SQL and clock.today() in Python name the same day.

Active per request (app.py loads it with the money setting) and copied into
background job threads with the rest of the context, like money.py.
"""
import contextvars
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

SETTING_KEY = "time_zone"

_current = contextvars.ContextVar("clinic_time_zone", default=None)


def computer_zone_name():
    """The computer's IANA zone name (tzlocal, which APScheduler already
    depends on, and which knows how to ask Windows as well)."""
    try:
        import tzlocal
        name = tzlocal.get_localzone_name()
        if name and is_valid(name):
            return name
    except Exception:
        pass
    return "UTC"


_VALID = None


def is_valid(name):
    global _VALID
    if _VALID is None:
        _VALID = frozenset(available_timezones())
    return bool(name) and name in _VALID


def all_zone_names():
    return sorted(n for n in available_timezones() if "/" in n or n == "UTC")


def resolve(time_zone_setting, money_setting):
    """The effective zone name from the stored setting and the money setting
    (a money.MoneySetting or None)."""
    if time_zone_setting and is_valid(time_zone_setting.strip()):
        return time_zone_setting.strip()
    if money_setting is not None:
        return money_setting.timezone
    return computer_zone_name()


def load(db, money_setting):
    """The effective zone name for this database."""
    row = db.execute("SELECT value FROM settings WHERE key=?", (SETTING_KEY,)).fetchone()
    return resolve(row["value"] if row else None, money_setting)


def set_current(name):
    return _current.set(name)


def reset_current(token):
    _current.reset(token)


def zone_name():
    return _current.get() or computer_zone_name()


def zone():
    return ZoneInfo(zone_name())


def now():
    """This moment, as an aware datetime in the clinic's zone."""
    return datetime.now(zone())


def today():
    """Today's date in the clinic's zone."""
    return now().date()


def aware(dt):
    """A datetime that may have been stored without an offset (a JSON value
    written before this module existed) — read as clinic time. An aware one
    is converted to the clinic's zone."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=zone())
    return dt.astimezone(zone())


def parse(text):
    """datetime.fromisoformat() for a stored timestamp, always aware."""
    if text is None or text == "":
        return None
    if isinstance(text, datetime):
        return aware(text)
    return aware(datetime.fromisoformat(str(text)))


def apply_to(con, name=None):
    """Put a database session in the clinic's zone. Session-level, so it lasts
    for the connection — but a GUC set inside a transaction that later rolls
    back is rolled back with it, which is why the app re-applies it per
    request rather than trusting a pooled connection to remember."""
    con.execute("SELECT set_config('TimeZone', ?, false)", (name or zone_name(),))
