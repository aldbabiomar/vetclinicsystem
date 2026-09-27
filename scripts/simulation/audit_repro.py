"""The reproductions in docs/CODE_AUDIT_2026-09-25.md §9, run against the
live app under both money settings (plan §12, "Done means" item 2).

Each one is the audit's recipe, carried over to this system: numeric ids,
and the P&L computed live from stored bill totals (D-3) where the recipe
read monthly_financial_summary and pressed Rebuild. Each must now be refused
or correct. A check reports FAIL with what it saw; the script exits 1 if any
did.

    scripts/isolated_test_env.sh up iq; scripts/isolated_test_env.sh up jo
    /tmp/vcs_test_venv_jo/bin/python scripts/simulation/audit_repro.py [iq|jo ...]
"""
import os
import random
import re
import sys
from decimal import Decimal

SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
sys.path.insert(0, os.path.dirname(os.path.dirname(SIM)))
from vzsim import APPS, Client, flashes, q, seeded_item  # noqa: E402
from vzform import inputs  # noqa: E402

MONTH = "2002-02"          # an old month of its own, so a delta is only ours
DAY = f"{MONTH}-15"
PASSWORD, NEW_PASSWORD = "Str0ngPass!23", "Changed!Pass99"


def M(app, whole):
    """A whole amount in the setting's terms: 12 -> 12,000 IQD / 12.000 JOD."""
    return str(whole * 1000) if app == "iq" else f"{whole}.000"


def phone(app):
    return ("0770" if app == "iq" else "079") + str(random.randint(10**6, 10**7 - 1))


def month_revenue(app):
    """The month's P&L revenue, as the Reports page computes it."""
    os.environ["DATABASE_URL"] = APPS[app]["db"]
    os.environ.setdefault("SECRET_KEY", "audit-repro-script-not-a-real-key")
    from vcs import clock, money
    from vcs.db import pool
    from vcs.domain import reports
    code = q(app, "select value from settings where key='money_setting'")[0][0]
    money.set_current(money.SETTINGS[code])
    clock.set_current(money.SETTINGS[code].timezone)
    con = pool.connect()
    try:
        return reports.by_month(con, only_month=MONTH).get(MONTH, (Decimal(0), Decimal(0)))[0]
    finally:
        con.close()


def new_visit(c, app):
    r = c.post("/visits/new/new-patient", {
        "owner_name": f"Repro Owner {random.randint(1000, 9999)}", "owner_phone": phone(app),
        "animal_name": "Repro", "species": "Dog", "date": DAY, "doctor": "Dr. Repro",
        "complaint": "audit reproduction", "microchip": str(random.randint(10**14, 10**15 - 1))})
    m = re.search(r"/visits/(\d+)", r.url)
    assert m, f"no visit created: {flashes(r.text)}"
    vid = int(m.group(1))
    pid = q(app, "select patient_id from visits where id=%s", (vid,))[0][0]
    return vid, pid


def narrow_user(admin, app, permission):
    """A role holding one permission, a user in it, signed in past the forced
    password change."""
    role = f"Repro {permission} {random.randint(1000, 9999)}"
    admin.post("/admin/roles/new", {"name": role, "description": "audit reproduction",
                                    "discount_cap": "0", "is_vet_role": "N", "permissions": [permission]})
    role_id = q(app, "select id from roles where name=%s", (role,))[0][0]
    uname = f"repro{random.randint(10**5, 10**6)}"
    admin.post("/admin/users/new", {"username": uname, "full_name": "Repro User", "password": PASSWORD,
                                    "role_id": role_id, "capmode": "role"})
    u = Client(app, uname)
    u.login(uname, PASSWORD)
    u.get("/change-password")
    u.post("/change-password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD,
                                "confirm_password": NEW_PASSWORD})
    uid = q(app, "select id from users where username=%s", (uname,))[0][0]
    return u, uid


def errors(resp):
    """The error messages a response showed: a refusal must say why, or it
    may have been refused for a reason the check is not about."""
    return [m for cat, m in flashes(resp.text) if cat in ("error", "danger")]


def form_as_submitted(page):
    """A form's inputs as a browser would send them: an unticked checkbox is
    not sent (vzform.inputs would send it)."""
    data = inputs(page)
    for m in re.finditer(r"<input\b([^>]*)>", page, re.I):
        a = m.group(1)
        name = re.search(r'name="([^"]+)"', a)
        if name and 'type="checkbox"' in a and "checked" not in a:
            data.pop(name.group(1), None)
    return data


def run(app):
    c = Client(app)
    c.login()
    results = []

    def check(name, ok, saw):
        results.append((name, ok))
        print(f"  [{'PASS' if ok else 'FAIL'}] {app.upper()} {name}" + ("" if ok else f" — {saw}"), flush=True)

    # B1 -- dates Postgres rejects: a clean page, and a word about the filter
    for path in ("/visits?date=2026-W39-4", "/cash-register?date=2026-W39-4", "/admin/logs?date=20260925"):
        r = c.get(path)
        said = [m for _, m in flashes(r.text)]
        check(f"B1 {path}", r.status_code < 500 and (path.startswith("/visits") or bool(said)),
              f"HTTP {r.status_code}, messages {said}")

    # B2 -- a Clean Up taken with a payment reaches the month at once
    vid, pid = new_visit(c, app)
    c.post(f"/visits/{vid}/billing", {"billing_type": "Manual", "manual_amount": M(app, 100), "date_billed": DAY})
    before = month_revenue(app)
    c.post(f"/visits/{vid}/payment", {"amount": M(app, 99), "method": "Cash", "cleanup_amount": M(app, 1)})
    after = month_revenue(app)
    check("B2 visit Clean Up lowers the month", after - before == -Decimal(M(app, 1)),
          f"revenue {before} -> {after}")

    # B2/B3 -- a boarding discount taken with a payment is booked discounted
    before = month_revenue(app)
    r = c.post("/boarding/new", {"patient_id": pid, "entry_date": DAY, "dismissal_date": f"{MONTH}-17",
                                 "price_per_day": M(app, 50), "total": M(app, 100), "room": "R1"})
    bid = q(app, "select id from boarding_sessions where patient_id=%s order by id desc limit 1", (pid,))
    if bid:
        c.post(f"/boarding/{bid[0][0]}/payment", {"amount": M(app, 10), "discount_percent": "10", "method": "Cash"})
    after = month_revenue(app)
    check("B2/B3 boarding discount is booked discounted", bool(bid) and after - before == Decimal(M(app, 90)),
          f"stay {bid}, revenue {before} -> {after} (expected +{M(app, 90)})")

    # S1 -- manage_settings cannot write the maintenance settings
    u, _ = narrow_user(c, app, "manage_settings")
    keys = ("backup_retention", "log_retention_days")
    was = dict(q(app, "select key, value from settings where key = any(%s)", (list(keys),)))
    u.get("/settings")
    said = errors(u.post("/settings", {"backup_retention": "1", "log_retention_days": "90"}))
    now = dict(q(app, "select key, value from settings where key = any(%s)", (list(keys),)))
    check("S1 manage_settings cannot change maintenance settings",
          now == was and any("log-retention" in m for m in said), f"{was} -> {now}; said {said}")

    # S2 -- manage_users_roles cannot make itself Admin
    u, uid = narrow_user(c, app, "manage_users_roles")
    admin_role = q(app, "select id from roles where name='Admin'")[0][0]
    said = errors(u.post(f"/admin/users/{uid}/role", {"role_id": admin_role}))
    role_now = q(app, "select role_id from users where id=%s", (uid,))[0][0]
    check("S2 manage_users_roles cannot promote itself",
          role_now != admin_role and any("don't hold yourself" in m for m in said),
          f"role is now {role_now}; said {said}")

    # B4 -- a second Save with the old token is refused, and so is the
    # conflict page's own form, unless "save my version" is ticked
    edit = c.get(f"/visits/{vid}/edit").text
    t0 = inputs(edit).get("expected_updated_at", "")
    base = {"date": DAY, "case_status": "Ongoing", "visit_type": "Outpatient", "doctor": "Dr. Repro",
            "complaint": "", "history": "", "exam": "", "treatment": ""}
    c.post(f"/visits/{vid}/edit", dict(base, complaint="First save", expected_updated_at=t0))
    page = c.post(f"/visits/{vid}/edit", dict(base, complaint="Stale save", expected_updated_at=t0)).text
    shown = "Saved by someone else" in page

    def resubmit(page, tick):
        data = dict(base, complaint="Stale save")
        data.update({k: v for k, v in form_as_submitted(page).items()
                     if k in ("expected_updated_at", "overwrite_updated_at")})
        if tick:
            data["overwrite_confirm"] = "1"
        return c.post(f"/visits/{vid}/edit", data).text

    page = resubmit(page, tick=False)
    kept = q(app, "select complaint from visits where id=%s", (vid,))[0][0]
    resubmit(page, tick=True)       # CONTROL: the explicit override does save
    overridden = q(app, "select complaint from visits where id=%s", (vid,))[0][0]
    check("B4 a stale save and the conflict page's resubmit are refused",
          shown and kept == "First save" and overridden == "Stale save",
          f"conflict shown: {shown}; after resubmit {kept!r}; after ticking the override {overridden!r}")

    # B5 -- a deactivated item is not sold
    item = seeded_item(app)
    q(app, "update inventory_list set active=false where id=%s", (item,))
    try:
        sold_before = q(app, "select count(*) from sale_items where item_id=%s", (item,))[0][0]
        r = c.post("/pos/checkout", {"item_id": item, "quantity": "999", "payment_method": "Cash",
                                     "idempotency_key": f"repro-{random.randint(1, 10**9)}"})
        sold_after = q(app, "select count(*) from sale_items where item_id=%s", (item,))[0][0]
        check("B5 a deactivated item is refused at the till",
              r.status_code < 500 and sold_after == sold_before and errors(r),
              f"HTTP {r.status_code}, sale lines {sold_before} -> {sold_after}, said {errors(r)}")
    finally:
        q(app, "update inventory_list set active=true where id=%s", (item,))

    # B6 -- a payment below the smallest unit is refused, not a 500
    c.post("/distributors/new", {"name": f"Repro Dist {random.randint(1000, 9999)}", "phone": phone(app)})
    dist = q(app, "select id from distributors order by id desc limit 1")[0][0]
    c.post(f"/distributors/{dist}/bills/new", {"bill_date": DAY, "total_amount": M(app, 10)})
    bill = q(app, "select id from distributor_bills where distributor_id=%s", (dist,))
    r = c.post(f"/distributors/{dist}/bills/{bill[0][0]}/payments/new",
               {"amount": "0.0004", "method": "Cash", "payment_date": DAY}) if bill else None
    paid = q(app, "select count(*) from distributor_bill_payments where bill_id=%s", (bill[0][0],))[0][0] if bill else None
    check("B6 a payment below the smallest unit is refused",
          bool(bill) and r.status_code < 500 and paid == 0 and errors(r),
          f"bill {bill}, HTTP {r and r.status_code}, payments {paid}, said {r is not None and errors(r)}")

    # B7 -- a drawer 0.9 off is not "Perfect"
    c.post("/cash-register/audit", {"day": "2020-01-01", "counted_cash": "0.9", "notes": "audit reproduction"})
    status = q(app, "select status from cash_register_audits where audit_date='2020-01-01' order by id desc limit 1")
    check("B7 a drawer 0.9 off is not Perfect", bool(status) and status[0][0] != "Perfect", f"recorded {status}")

    # B11 -- a POST to a missing parent is a clean refusal
    for path in ("/distributors/NOPE/bills/new", "/distributors/2000000001/bills/new"):
        r = c.post(path, {"total_amount": M(app, 5), "bill_date": DAY})
        check(f"B11 POST {path}", r.status_code < 500, f"HTTP {r.status_code}")

    return results


if __name__ == "__main__":
    apps = sys.argv[1:] or ["iq", "jo"]
    failed = 0
    for app in apps:
        print(f"\n=== {app.upper()} ===", flush=True)
        failed += sum(1 for _, ok in run(app) if not ok)
    print(f"\n{failed} reproduction(s) not refused or correct." if failed else "\nEvery reproduction refused or correct.")
    sys.exit(1 if failed else 0)
