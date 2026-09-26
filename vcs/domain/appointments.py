"""
Appointments: the slot grid from the clinic's hours, the week, the
vets, and slot conflicts.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from vcs import clock
from vcs.domain import dates, settings


# ---------------------------------------------------------------------------
# Appointments — dynamic slot grid
# ---------------------------------------------------------------------------
def generate_slots(db):
    start = settings.get_setting(db, "appt_start_time", "09:00")
    end = settings.get_setting(db, "appt_end_time", "18:00")
    try:
        minutes = int(settings.get_setting(db, "appt_slot_minutes", "30"))
    except (TypeError, ValueError):
        minutes = 30
    if minutes <= 0:
        minutes = 30
    try:
        t0 = datetime.strptime(start, "%H:%M")
        t1 = datetime.strptime(end, "%H:%M")
    except (TypeError, ValueError):
        # Settings is the only writer of these and validates HH:MM before
        # saving, but this stays defensive rather than letting a malformed
        # stored value 500 every page that renders the appointment grid
        # (Appointments, New Visit, Grooming, Inpatient's vet picker). See
        # ERROR_500_AUDIT.md E-02.
        t0 = datetime.strptime("09:00", "%H:%M")
        t1 = datetime.strptime("18:00", "%H:%M")
    if t1 <= t0:
        return []
    slots = []
    cur = t0
    while cur < t1:
        nxt = cur + timedelta(minutes=minutes)
        start_str = cur.strftime("%H:%M")
        # The slot's own start time doubles as its identifier (label) — this is
        # what gets stored in appointments.slot_label. It's just as good a key
        # as an arbitrary letter would be for conflict-checking/grouping, and
        # it's self-explanatory if you ever look at the raw data.
        slots.append({"label": start_str, "start": start_str, "end": min(nxt, t1).strftime("%H:%M")})
        cur = nxt
    return slots


def week_dates(anchor_iso):
    anchor = dates.as_date(anchor_iso) or clock.today()
    monday = anchor - timedelta(days=anchor.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def vet_users(db):
    """The staff who can be booked or assigned as the vet: active users whose
    role is marked "can be assigned as a vet". One query for the appointment
    grid, the orphaned-appointment check and every vet picker (audit P19) --
    it was written out three times, and a change to one would have made the
    grid and the pickers disagree about who is a vet."""
    return db.execute("SELECT id, full_name FROM users WHERE role_id IN (SELECT id FROM roles WHERE is_vet_role=true) "
                      "AND active=true ORDER BY full_name").fetchall()


def day_grid(db, day_iso):
    vets = vet_users(db)
    slots = generate_slots(db)
    appts = db.execute("SELECT * FROM appointments WHERE appt_date=?", (day_iso,)).fetchall()

    by_cell = defaultdict(list)
    for a in appts:
        by_cell[(a["slot_label"], a["resource_type"], a["resource_id"])].append(dict(a))

    columns = [{"resource_type": "vet", "resource_id": v["id"], "label": v["full_name"]} for v in vets]
    columns.append({"resource_type": "grooming", "resource_id": None, "label": "Grooming"})

    grid = []
    for slot in slots:
        row = {"slot": slot, "cells": []}
        for col in columns:
            cell_appts = by_cell.get((slot["label"], col["resource_type"], col["resource_id"]), [])
            row["cells"].append({"column": col, "appointments": cell_appts})
        grid.append(row)
    return columns, grid


def orphaned_appointments(db, include_past=False):
    """Upcoming appointments whose (slot_label, resource_type,
    resource_id) no longer matches anything day_grid() currently renders
    — either the vet they're booked against was deactivated since, or
    the slot-length/hours settings changed since they were booked.
    day_grid() only looks a cell up by exact key match against whatever
    generate_slots()/the active-vet list return *right now*, so a row
    like this is still perfectly valid in the database but was
    completely unreachable from the Appointments page — no cell ever
    renders it, and there's no other page listing appointments by id.
    This is the fallback that guarantees one always exists, regardless
    of what caused the mismatch (existing UI also warns at the two
    known trigger points — deactivating a vet, changing
    appt_start_time/appt_end_time/appt_slot_minutes — but this doesn't
    depend on that warning having been heeded, or on every possible
    future cause having been thought of ahead of time)."""
    # include_past=True is a deliberate, explicit opt-in (Appointments'
    # "Show past unreachable bookings" toggle) — a booking that became
    # unreachable *and* whose date has since passed would otherwise be
    # invisible permanently, with no other page listing appointments by
    # id. See ORPHANED_RECORDS_AUDIT.md F-18.
    valid_labels = {s["label"] for s in generate_slots(db)}
    active_vet_ids = {v["id"] for v in vet_users(db)}
    date_filter = "" if include_past else "WHERE a.appt_date >= ?"
    params = () if include_past else (clock.today().isoformat(),)
    rows = db.execute(
        "SELECT a.*, u.full_name AS vet_name FROM appointments a "
        "LEFT JOIN users u ON u.id = a.resource_id "
        f"{date_filter} ORDER BY a.appt_date, a.slot_label",
        params,
    ).fetchall()
    out = []
    for a in rows:
        stale_slot = a["slot_label"] not in valid_labels
        stale_vet = a["resource_type"] == "vet" and a["resource_id"] not in active_vet_ids
        if stale_slot or stale_vet:
            d = dict(a)
            d["reason"] = "Vet no longer active" if stale_vet else "Time slot no longer exists"
            out.append(d)
    return out


def slot_conflict(db, appt_date, slot_label, resource_type, resource_id):
    row = db.execute(
        "SELECT 1 FROM appointments WHERE appt_date=? AND slot_label=? AND resource_type=? AND "
        "(resource_id=? OR (resource_id IS NULL AND ?::text IS NULL))",
        (appt_date, slot_label, resource_type, resource_id, resource_id),
    ).fetchone()
    return bool(row)
