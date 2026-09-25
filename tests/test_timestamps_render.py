"""
Every page and export that shows a stored moment, rendered against real rows.

Event times became `timestamptz` in phase 2c: the database hands back an aware
datetime where it used to hand back an ISO string, and every template that
sliced the string (`[:16]`, `[11:19]`, `.replace('T', ' ')`) had to change.
The route smoke test renders every page, but on a nearly empty database —
an inpatient case with no updates never reaches the line that prints an
update's time. This seeds one row of every kind whose time is shown, and
checks two things per page: it renders, and no raw ISO timestamp
("2026-09-25T10:00", "+03:00") leaks into what a person reads.
"""
import re
import uuid
from decimal import Decimal as D

import pytest

import clock
from conftest import new_id, ADMIN_ID, needs_db

pytestmark = needs_db

_RAW_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}|\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{2}:\d{2}")


def _visible(html):
    """The page minus attribute values (a hidden edit token IS an ISO
    string, by design) and minus <script> bodies (data for the page's JS)."""
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S)
    return re.sub(r'value="[^"]*"', "", html)


def test_control_the_leak_check_sees_a_raw_timestamp():
    assert _RAW_ISO.search(_visible("<td>2026-09-25T10:00:00+03:00</td>"))
    assert _RAW_ISO.search(_visible("<td>10:00:00.123456+03:00</td>"))
    assert not _RAW_ISO.search(_visible('<td>2026-09-25 10:00</td><input value="2026-09-25T07:00:00+00:00">'))


@pytest.fixture
def timed_rows(db):
    """One row of every kind whose time some page prints."""
    tag = uuid.uuid4().hex[:8].upper()
    now = clock.now()
    o, p, v, dist, inv = new_id(), new_id(), new_id(), f"TD{tag}", f"TI{tag}"
    ids = {"tag": tag}
    db.execute("INSERT INTO owners (id, name) VALUES (?,?)", (o, f"Time Owner {tag}"))
    db.execute("INSERT INTO patients (id, owner_id, animal_name) VALUES (?,?,?)", (p, o, f"Time Pet {tag}"))
    db.execute("INSERT INTO visits (id, patient_id, date, case_status, updated_at, case_status_changed_at) "
               "VALUES (?,?,?,?,?,?)", (v, p, clock.today(), "Ongoing", now, now))
    ids["case_id"] = db.execute(
        "INSERT INTO inpatient_cases (patient_id, visit_id, admission_date, dismissed, discount_percent, total, "
        "cleanup_amount, updated_at) VALUES (?,?,?,?,?,?,?,?) RETURNING id",
        (p, v, clock.today(), False, D(0), D(0), D(0), now)).fetchone()["id"]
    db.execute("INSERT INTO inpatient_updates (case_id, timestamp, note, user_id) VALUES (?,?,?,?)",
               (ids["case_id"], now, "Eating well", ADMIN_ID))
    db.execute("INSERT INTO inpatient_contact_log (case_id, timestamp, picked_up, staff_user_id) VALUES (?,?,?,?)",
               (ids["case_id"], now, 1, ADMIN_ID))
    ids["boarding_id"] = db.execute(
        "INSERT INTO boarding_sessions (patient_id, entry_date, special_needs, total_is_auto, cleanup_amount, "
        "discount_percent, dismissed, total, updated_at) VALUES (?,?,?,?,?,?,?,?,?) RETURNING id",
        (p, clock.today(), False, False, D(0), D(0), False, D(10), now)).fetchone()["id"]
    db.execute("INSERT INTO boarding_incidents (boarding_id, timestamp, issue, user_id) VALUES (?,?,?,?)",
               (ids["boarding_id"], now, "Scratched the door", ADMIN_ID))
    db.execute("INSERT INTO distributors (id, name) VALUES (?,?)", (dist, f"Time Dist {tag}"))
    db.execute("INSERT INTO inventory_list (id, name, category, unit, track_expiry, cost_price, distributor_id, "
               "ownership_type, consignment_since, active) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (inv, f"Time Item {tag}", "Retail", "unit", False, D(1), dist, "Consignment", now, True))
    db.execute("INSERT INTO consignment_shrinkage (item_id, distributor_id, quantity, reason, liable_party, "
               "unit_cost, logged_by, logged_at) VALUES (?,?,?,?,?,?,?,?)",
               (inv, dist, D(1), "Damaged", "Clinic", D(1), ADMIN_ID, now))
    ids["settlement_id"] = db.execute(
        "INSERT INTO consignment_settlements (distributor_id, period_start, period_end, amount_owed, amount_paid, "
        "payment_method, settled_by, created_at) VALUES (?,?,?,?,?,?,?,?) RETURNING id",
        (dist, now, now, D(5), D(5), "Cash", ADMIN_ID, now)).fetchone()["id"]
    ids["sale_id"] = db.execute(
        "INSERT INTO sales (sold_at, cashier_id, subtotal, discount_percent, total, payment_method) "
        "VALUES (?,?,?,?,?,?) RETURNING id", (now, ADMIN_ID, D(5), D(0), D(5), "Card")).fetchone()["id"]
    ids["backup_id"] = db.execute(
        "INSERT INTO backup_log (started_at, finished_at, status, triggered_by) VALUES (?,?,?,?) RETURNING id",
        (now, now, "success", "manual")).fetchone()["id"]
    ids["restore_id"] = db.execute(
        "INSERT INTO restore_log (started_at, finished_at, status, triggered_by) VALUES (?,?,?,?) RETURNING id",
        (now, now, "success", "manual")).fetchone()["id"]
    ids["check_id"] = db.execute(
        "INSERT INTO self_check_log (ran_at, status, findings) VALUES (?,?,?) RETURNING id",
        (now, "ok", "[]")).fetchone()["id"]
    ids["audit_id"] = db.execute(
        "INSERT INTO cash_register_audits (audit_date, system_cash, system_card, system_transfer, counted_cash, "
        "difference, status, performed_by, created_at) VALUES (?,?,?,?,?,?,?,?,?) RETURNING id",
        (clock.today(), D(0), D(0), D(0), D(0), D(0), "Perfect", ADMIN_ID, now)).fetchone()["id"]
    ids.update(owner=o, patient=p, visit=v, dist=dist, item=inv, now=now)
    db.commit()
    yield ids
    for sql, arg in (
        ("DELETE FROM cash_register_audits WHERE id=?", ids["audit_id"]),
        ("DELETE FROM self_check_log WHERE id=?", ids["check_id"]),
        ("DELETE FROM restore_log WHERE id=?", ids["restore_id"]),
        ("DELETE FROM backup_log WHERE id=?", ids["backup_id"]),
        ("DELETE FROM sales WHERE id=?", ids["sale_id"]),
        ("DELETE FROM consignment_settlements WHERE id=?", ids["settlement_id"]),
        ("DELETE FROM consignment_shrinkage WHERE item_id=?", inv),
        ("DELETE FROM inventory_list WHERE id=?", inv),
        ("DELETE FROM distributors WHERE id=?", dist),
        ("DELETE FROM boarding_incidents WHERE boarding_id=?", ids["boarding_id"]),
        ("DELETE FROM boarding_sessions WHERE id=?", ids["boarding_id"]),
        ("DELETE FROM inpatient_contact_log WHERE case_id=?", ids["case_id"]),
        ("DELETE FROM inpatient_updates WHERE case_id=?", ids["case_id"]),
        ("DELETE FROM inpatient_cases WHERE id=?", ids["case_id"]),
        ("DELETE FROM visits WHERE id=?", v),
        ("DELETE FROM patients WHERE id=?", p),
        ("DELETE FROM owners WHERE id=?", o),
    ):
        db.execute(sql, (arg,))
    db.commit()


def _pages(ids):
    return [
        f"/inpatient/{ids['case_id']}",
        "/boarding",
        f"/consignment/settlements/{ids['dist']}",
        "/consignment/shrinkage",
        "/admin/logs",
        "/settings",
        "/",
        "/pos/history",
        f"/pos/receipt/{ids['sale_id']}",
        "/cash-register",
        f"/visits/{ids['visit']}",
    ]


def _exports(ids):
    return [
        f"/inpatient/{ids['case_id']}/export",
        f"/boarding/{ids['boarding_id']}/export",
        f"/consignment/settlements/export/{ids['settlement_id']}",
        f"/pos/history/{ids['sale_id']}/export",
        f"/visits/{ids['visit']}/export",
    ]


def test_every_page_that_shows_a_stored_moment_renders_it_for_people(client, timed_rows):
    """GUARD. Renders, and shows no raw ISO timestamp."""
    problems = []
    for url in _pages(timed_rows):
        resp = client.get(url)
        if resp.status_code != 200:
            problems.append(f"{url} -> HTTP {resp.status_code}")
            continue
        leak = _RAW_ISO.search(_visible(resp.get_data(as_text=True)))
        if leak:
            problems.append(f"{url} shows a raw timestamp: {leak.group(0)!r}")
    assert not problems, "\n  ".join([""] + problems)


def test_the_seeded_moments_actually_reached_the_pages(client, timed_rows):
    """CONTROL for the guard above: it only means something if the rows it
    seeded are on the pages it read."""
    assert "Eating well" in client.get(f"/inpatient/{timed_rows['case_id']}").get_data(as_text=True)
    assert clock.today().isoformat() in client.get(
        f"/consignment/settlements/{timed_rows['dist']}").get_data(as_text=True)
    # The backup row's start, as a person reads it — the minute, clinic zone.
    # (Boarding incidents are only printed in the stay's PDF, rendered below.)
    import logic
    assert logic.fmt_datetime(timed_rows["now"]) in client.get("/settings").get_data(as_text=True)


def test_every_export_that_prints_a_stored_moment_renders(client, timed_rows):
    failures = []
    for url in _exports(timed_rows):
        resp = client.get(url)
        if resp.status_code != 200 or not resp.data.startswith(b"%PDF"):
            failures.append(f"{url} -> HTTP {resp.status_code}, {resp.headers.get('Content-Type')}")
    assert not failures, "\n  ".join([""] + failures)
