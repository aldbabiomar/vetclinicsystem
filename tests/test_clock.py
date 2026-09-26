"""
The clinic's clock and the Time Zone setting (clock.py).

"Today" and every time the app records follow, in order: the Time Zone
setting, the money setting's zone, the computer's zone. These pin the order,
the setting's validation, and — the part that would go wrong silently — that
a page actually uses it rather than the computer's clock.
"""
import source_files
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from vcs import clock
from vcs import money
from conftest import needs_db


# ---------------------------------------------------------------------------
# Resolution (no database)
# ---------------------------------------------------------------------------

def test_the_setting_wins_over_the_money_setting():
    assert clock.resolve("Asia/Tokyo", money.JO) == "Asia/Tokyo"


def test_automatic_follows_the_money_setting():
    assert clock.resolve(None, money.IQ) == "Asia/Baghdad"
    assert clock.resolve("", money.JO) == "Asia/Amman"


def test_before_a_money_setting_the_computers_zone_is_used():
    assert clock.resolve(None, None) == clock.computer_zone_name()


def test_a_stored_zone_that_is_not_a_zone_is_ignored_not_trusted():
    """A value the setting route would refuse, arriving some other way (a
    restored backup, a hand edit), falls back rather than crashing every
    page on ZoneInfo()."""
    assert clock.resolve("Mars/Olympus_Mons", money.JO) == "Asia/Amman"


def test_now_is_aware_and_in_the_active_zone():
    token = clock.set_current("Asia/Tokyo")
    try:
        n = clock.now()
        assert n.tzinfo is not None and n.utcoffset() == timedelta(hours=9)
    finally:
        clock.reset_current(token)


def test_a_timestamp_stored_without_an_offset_is_read_as_clinic_time():
    token = clock.set_current("Asia/Amman")
    try:
        t = clock.parse("2026-09-25T10:00:00")
        assert t.tzinfo is not None and t.hour == 10
        assert t.utcoffset() == timedelta(hours=3)
        # An aware one keeps its instant, converted to clinic time.
        u = clock.parse("2026-09-25T07:00:00+00:00")
        assert u == datetime(2026, 9, 25, 7, tzinfo=timezone.utc) and u.hour == 10
    finally:
        clock.reset_current(token)


# ---------------------------------------------------------------------------
# The setting, through Settings (database)
# ---------------------------------------------------------------------------

def _save(client, **fields):
    return client.post("/settings", data=fields, follow_redirects=False)


def _stored(db):
    row = db.execute("SELECT value FROM settings WHERE key=?", (clock.SETTING_KEY,)).fetchone()
    return row["value"] if row else None


@pytest.fixture
def time_zone_left_as_found(db):
    before = _stored(db)
    yield
    if before is None:
        db.execute("DELETE FROM settings WHERE key=?", (clock.SETTING_KEY,))
    else:
        db.execute("UPDATE settings SET value=? WHERE key=?", (before, clock.SETTING_KEY))
    db.commit()


@needs_db
def test_a_valid_zone_is_saved(client, db, time_zone_left_as_found):
    assert _save(client, time_zone="Asia/Tokyo").status_code == 302
    assert _stored(db) == "Asia/Tokyo"
    assert clock.load(db, money.JO) == "Asia/Tokyo"


@needs_db
def test_blank_means_automatic_and_removes_the_key(client, db, time_zone_left_as_found):
    _save(client, time_zone="Asia/Tokyo")
    _save(client, time_zone="")
    assert _stored(db) is None
    assert clock.load(db, money.JO) == "Asia/Amman"


@needs_db
def test_a_zone_that_does_not_exist_is_refused(client, db, time_zone_left_as_found):
    _save(client, time_zone="Asia/Tokyo")
    resp = client.post("/settings", data={"time_zone": "Mars/Olympus_Mons"}, follow_redirects=True)
    assert "Not a valid time zone." in resp.get_data(as_text=True)
    assert _stored(db) == "Asia/Tokyo", "the refused value replaced the saved one"


def _a_zone_whose_date_differs_from(reference_zone):
    """At any instant, UTC+14 or UTC-11 is on a different date from UTC+3."""
    ref = datetime.now(ZoneInfo(reference_zone)).date()
    for z in ("Pacific/Kiritimati", "Pacific/Pago_Pago"):
        if datetime.now(ZoneInfo(z)).date() != ref:
            return z, datetime.now(ZoneInfo(z)).date()
    raise AssertionError("no zone with a different date — the arithmetic above is wrong")


@needs_db
def test_a_page_says_today_in_the_chosen_zone(client, db, time_zone_left_as_found):
    """GUARD. The Cash Register opens on "today". With the setting on a zone
    whose date is not the computer's, the page must open on the ZONE's date —
    a page reading date.today() would still show the computer's."""
    zone, zone_today = _a_zone_whose_date_differs_from(clock.computer_zone_name())
    assert _save(client, time_zone=zone).status_code == 302
    html = client.get("/cash-register").get_data(as_text=True)
    assert f'name="date" value="{zone_today.isoformat()}"' in html


@needs_db
def test_control_on_automatic_the_page_says_the_money_settings_today(client, db, time_zone_left_as_found):
    _save(client, time_zone="")
    amman_today = datetime.now(ZoneInfo("Asia/Amman")).date()
    html = client.get("/cash-register").get_data(as_text=True)
    assert f'name="date" value="{amman_today.isoformat()}"' in html


@needs_db
def test_the_database_session_is_put_in_the_chosen_zone(client, db, time_zone_left_as_found):
    """The pooled connection a request uses must carry the zone, or a
    `::date` in SQL names a different day from clock.today() in Python."""
    import app as app_module
    _save(client, time_zone="Asia/Tokyo")
    with app_module.app.test_request_context("/"):
        app_module._load_money_setting()
        try:
            row = app_module.get_db().execute("SELECT current_setting('TimeZone') AS tz").fetchone()
            assert row["tz"] == "Asia/Tokyo"
            assert clock.zone_name() == "Asia/Tokyo"
        finally:
            app_module._unload_money_setting(None)


# ---------------------------------------------------------------------------
# Nothing reads the computer's clock directly
# ---------------------------------------------------------------------------

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DIRECT = re.compile(r"\b(?:datetime\.(?:now|utcnow|today)|date\.today)\(\s*\)")


def _direct_clock_reads(text):
    code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    return _DIRECT.findall(code)


def test_control_the_scan_finds_a_direct_read():
    assert _direct_clock_reads("x = datetime.now()\ny = date.today()  # z") == ["datetime.now()", "date.today()"]
    assert _direct_clock_reads("x = clock.now()  # not datetime.now()") == []


def test_no_application_code_reads_the_computers_clock():
    """GUARD. datetime.now() / date.today() read the computer's zone; the
    Time Zone setting only reaches code that asks clock.py."""
    files = [p for p in source_files.all_python() if p.name != "clock.py"]
    assert len(files) > 20, "the scan is not looking at the application"
    offenders = [f"{p.relative_to(_ROOT)}: {hit}" for p in files
                 for hit in _direct_clock_reads(p.read_text(encoding="utf-8"))]
    assert not offenders, "read the clock through clock.now()/clock.today():\n  " + "\n  ".join(offenders)
