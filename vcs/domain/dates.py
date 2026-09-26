"""
Dates and months: reading a stored value as a date, the clinic's month
and day boundaries, and their display forms. What "today" is comes
from clock.py; these only shape it.
"""
import calendar
from datetime import date, datetime, timedelta

from vcs import clock


def as_date(v):
    """A STORED value as a date: a DATE column's date as is, a timestamptz's
    moment as the clinic-zone day it fell on, or the ISO text of either (a
    date computed in code, a stamp kept in a JSON job result).

    Never for a date that arrives in a request -- that is core.strict_date(),
    which accepts exactly YYYY-MM-DD. This one is lenient on purpose (it
    reads a whole ISO timestamp), and it was the request parser until audit
    B1: since Python 3.11 date.fromisoformat() also accepts 2026-W39-4 and
    20260925, which the routes then passed raw to Postgres (a 500 on four
    pages, silently empty results on three). Renamed from parse_date so the
    two cannot be confused.

    It still validates the whole value, never a prefix: "2026-08-25garbage"
    raises (it once parsed clean from a blind str(v)[:10])."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return clock.aware(v).date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    try:
        return date.fromisoformat(s)
    except ValueError:
        return datetime.fromisoformat(s).date()


def fmt_date(d):
    """A date for display: a date as is, a stored moment (timestamptz) as the
    clinic-zone day it fell on."""
    if not d:
        return None
    if isinstance(d, datetime):
        return clock.aware(d).date().isoformat()
    return d.isoformat()


def fmt_datetime(v, fmt="%Y-%m-%d %H:%M"):
    """A stored moment for display, in the clinic's zone: a timestamptz read
    back, or an ISO string held in a setting or a job result. Digits only —
    the |localtime filter adds Arabic-Indic ones."""
    if not v:
        return ""
    return clock.parse(v).strftime(fmt)


def month_key(d):
    """Returns the 'YYYY-MM' of a date value: an ISO date string, a date, or
    a datetime (a timestamptz read back) — the last taken in the clinic's
    zone, so a sale at 01:00 on the 1st is not filed under last month
    because the connection happened to be in UTC. None for a falsy input."""
    if not d:
        return None
    if isinstance(d, datetime):
        return clock.aware(d).strftime("%Y-%m")
    if hasattr(d, "isoformat"):
        return d.isoformat()[:7]
    return str(d)[:7]


def _first_of_next_month(first):
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1)


def month_dates(month):
    """'YYYY-MM' -> (first day, first day of the next month), for a DATE
    column: `col >= ? AND col < ?`. Never `col::text LIKE 'YYYY-MM%'` — that
    cannot use an index and, on a timestamp, does not work at all."""
    first = date.fromisoformat(f"{month}-01")
    return first, _first_of_next_month(first)


def month_bounds(month):
    """'YYYY-MM' -> the first instant of that month and of the next, in the
    clinic's zone, for a timestamptz column: `col >= ? AND col < ?`."""
    first, nxt = month_dates(month)
    z = clock.zone()
    return (datetime.combine(first, datetime.min.time(), tzinfo=z),
            datetime.combine(nxt, datetime.min.time(), tzinfo=z))


def day_bounds(day):
    """A date (or ISO date string) -> the first instant of that day and of
    the next, in the clinic's zone, for a timestamptz column."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    z = clock.zone()
    start = datetime.combine(day, datetime.min.time(), tzinfo=z)
    return start, datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=z)


def add_months(d, months):
    """Calendar-month arithmetic, clamping the day to the target month.

    31 January + 1 month is 28 (or 29) February, not an invalid date — which
    is what d.replace(month=...) alone would raise on.
    """
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def month_list(months_back):
    """Returns ['YYYY-MM', ...] for the last N months, oldest first (incl. current)."""
    today = clock.today()
    months = []
    y, m = today.year, today.month
    for i in range(months_back - 1, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        months.append(f"{yy:04d}-{mm:02d}")
    return months
