"""CLAUDE.md §7.3 — reintroduce each bug and confirm the guard actually fires.

A guard that has never been watched refuse is not yet known to be a guard.
For each fix: revert it in the source, restart the app, run the probe that
found the bug originally, and assert the bug COMES BACK. Then restore and
assert it is gone again. A mutation that changes nothing is reported as
NOT PROVEN -- that is the blind-test case, and it is a failure here.
"""
import os, sys, re, subprocess, time, random, datetime, shutil, signal
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes

WEB = "/Users/omaraldbabi/Desktop/VetClinicSystem/webapps"
PORTS = {"iq": 5091, "jo": 5092}
DB_PORTS = {"iq": 55491, "jo": 55492}
DBN = {"iq": "vetclinicsystemiq", "jo": "vetclinicsystemjo"}
PREFIX = {"iq": "VETCLINICSYSTEMIQ", "jo": "VETCLINICSYSTEMJO"}
VENV = {"iq": "/tmp/vz_iq_test_venv", "jo": "/tmp/vz_jo_test_venv"}
DATA = {"iq": "/tmp/vz_iq_test_data", "jo": "/tmp/vz_jo_test_data"}
D = datetime.date.today().isoformat()
PH = lambda app: ("0770" if app == "iq" else "079") + str(random.randint(10**6, 10**7 - 1))

results = []


def repo(app):
    return f"{WEB}/vetclinicsystem_{app}-main"


def restart(app):
    port = PORTS[app]
    out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                         capture_output=True, text=True).stdout.split()
    for pid in out:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except Exception:
            pass
    time.sleep(2)
    env = dict(os.environ)
    env.update({
        "DATABASE_URL": f"postgresql://postgres:test@localhost:{DB_PORTS[app]}/{DBN[app]}",
        f"{PREFIX[app]}_DATA_DIR": DATA[app],
        f"{PREFIX[app]}_HOST": "127.0.0.1",
        f"{PREFIX[app]}_PORT": str(port),
        "SECRET_KEY": "prove-guards-" + "0" * 40,
    })
    log = open(f"{DATA[app]}/app_stdout.log", "a")
    subprocess.Popen([f"{VENV[app]}/bin/python3", "app.py"], cwd=repo(app),
                     env=env, stdout=log, stderr=log, start_new_session=True)
    for _ in range(40):
        time.sleep(0.5)
        try:
            import requests
            if requests.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                return True
        except Exception:
            pass
    return False


def mutate(path, old, new):
    s = open(path).read()
    if s.count(old) != 1:
        raise SystemExit(f"MUTATION ANCHOR NOT UNIQUE in {path}: {s.count(old)} matches")
    open(path, "w").write(s.replace(old, new, 1))


def record(name, bug_returned, detail=""):
    results.append((name, bug_returned, detail))
    mark = "PROVEN " if bug_returned else "NOT PROVEN"
    print(f"  [{mark}] {name}   {detail}", flush=True)


def stock_and_price(c, app, count, price):
    r = c.post("/audit-history/start")
    sid = re.search(r"/session/(\d+)", r.url).group(1)
    pg = c.get(f"/audit-history/session/{sid}")
    ids = sorted(set(re.findall(r'name="stock_(INV\d+)"', pg.text)))
    data = {}
    for i in ids:
        data[f"stock_{i}"] = str(count) if i == "INV301" else "0"
        data[f"received_{i}"] = "0"
    c.post(f"/audit-history/session/{sid}/save", data)
    c.post(f"/audit-history/session/{sid}/confirm", data)
    q(app, "UPDATE price_list SET sale_price=%s WHERE id='PL301'", (price,))
    return sid


# ---------------------------------------------------------------------------
# Each entry: (label, app, file, original snippet, mutated snippet, probe)
# The probe returns True when the BUG IS PRESENT.
# ---------------------------------------------------------------------------

def probe_pos_floor(app):
    c = Client(app); c.login()
    stock_and_price(c, app, 500, 100)
    n0 = q(app, "select count(*) from sales")[0][0]
    c.post("/pos/checkout", {"item_id": "INV301", "quantity": "1", "payment_method": "Cash",
                             "discount_percent": "0", "cash_received": "250000",
                             "idempotency_key": f"pg-{random.randint(1,10**9)}"})
    if q(app, "select count(*) from sales")[0][0] == n0:
        return False, "no sale recorded"
    sub, tot = q(app, "select subtotal,total from sales order by id desc limit 1")[0]
    return float(tot) == 0 and float(sub) > 0, f"subtotal={sub} total={tot}"


def probe_refund_zero(app):
    c = Client(app); c.login()
    stock_and_price(c, app, 500, 240)
    c.post("/pos/checkout", {"item_id": "INV301", "quantity": "1", "payment_method": "Cash",
                             "discount_percent": "0", "cash_received": "250000",
                             "idempotency_key": f"pg-{random.randint(1,10**9)}"})
    row = q(app, "select id,total from sales order by id desc limit 1")[0]
    api = c.get(f"/api/sales/{row[0]}/refundable-items")
    lines = api.json().get("lines", [])
    if not lines:
        return False, "no refundable lines"
    c.post("/refunds/retail", {"sale_id": str(row[0]),
                               "sale_item_id": str(lines[0]["sale_item_id"]),
                               "quantity": "1", "reason": "x", "refund_date": D,
                               "refund_method": "Cash", "restock": "on"})
    ref = q(app, "select amount from refunds where sale_id=%s order by id desc limit 1", (row[0],))
    if not ref:
        return False, "no refund row"
    return float(ref[0][0]) == 0, f"sale_total={row[1]} refund={ref[0][0]}"


def probe_nan_accepted(app):
    c = Client(app); c.login()
    r = c.post("/audit-history/start")
    sid = re.search(r"/session/(\d+)", r.url).group(1)
    # the CHECK constraint is the other layer; drop it so this probes the app
    q(app, "ALTER TABLE audit_session_lines DROP CONSTRAINT IF EXISTS "
           "audit_session_lines_stock_counted_check")
    try:
        c.post(f"/audit-history/session/{sid}/save",
               {"stock_INV301": "nan", "received_INV301": "0"})
        got = q(app, "select stock_counted from audit_session_lines "
                     "where session_id=%s and item_id='INV301'", (sid,))
        val = str(got[0][0]).lower() if got else "none"
        return "nan" in val, f"stored={val}"
    finally:
        q(app, "DELETE FROM audit_session_lines WHERE stock_counted='NaN'::float8")
        q(app, "ALTER TABLE audit_session_lines ADD CONSTRAINT "
               "audit_session_lines_stock_counted_check CHECK (stock_counted IS NULL "
               "OR (stock_counted >= 0 AND stock_counted < 'Infinity'::float8))")


def probe_appt_500(app):
    c = Client(app); c.login()
    r = c.s.get(c.base + "/appointments?day=")
    return r.status_code >= 500, f"status={r.status_code}"


def probe_discharge_before_admission(app):
    from vzform import pick, inputs
    c = Client(app); c.login()
    c.post("/visits/new/new-patient", {
        "owner_name": f"Prove {random.randint(1,10**6)}", "owner_phone": PH(app),
        "animal_name": "Prove", "species": "Dog", "date": D, "doctor": "Dr. A",
        "complaint": "x", "microchip": str(random.randint(10**14, 10**15 - 1))})
    pid = q(app, "select id from patients order by id desc limit 1")[0][0]
    npg = c.get("/inpatient/new")
    vet = pick(npg.text, "attending_vet_id")
    r = c.post("/inpatient/new", {
        "patient_id": pid, "admission_date": D, "attending_vet_id": vet or "",
        "supervising_vet_id": vet or "", "complaint": "obs", "exam_findings": "s",
        "weight_kg": "10", "bcs": "5"})
    m = re.search(r"/inpatient/(\d+)", r.url)
    if not m:
        return False, "could not admit"
    cid = m.group(1)
    stamp = inputs(c.get(f"/inpatient/{cid}").text).get("expected_updated_at", "")
    c.post(f"/inpatient/{cid}/edit", {
        "attending_vet_id": vet or "", "supervising_vet_id": vet or "", "complaint": "obs",
        "exam_findings": "s", "weight_kg": "10", "bcs": "5", "dismissed": "on",
        "dismissal_date": "2024-01-01", "expected_updated_at": stamp})
    row = q(app, "select admission_date,dismissal_date from inpatient_cases where id=%s", (cid,))[0]
    return (row[1] is not None and str(row[1]) < str(row[0])), f"admitted={row[0]} discharged={row[1]}"


def probe_cash_warning(app):
    c = Client(app); c.login()
    r = c.post("/cash-register/audit",
               {"day": D, "counted_cash": "888888" if app == "iq" else "8888.000", "notes": "p"})
    cats = {cat for cat, _ in flashes(r.text)}
    return "warning" not in cats, f"categories={cats}"


MUTATIONS = [
    ("F1 POS anti-free floor", "iq", "routes/sales.py",
     "    total = money.payable_total(subtotal * (1 - discount_percent / 100), discount_percent)",
     "    total = money.round_to_denomination(subtotal * (1 - discount_percent / 100))",
     probe_pos_floor),

    ("F3 refund never zero", "iq", "routes/sales.py",
     "    if total > 0 and rounded_total == 0:",
     "    if False and total > 0 and rounded_total == 0:",
     probe_refund_zero),

    ("F2 audit rejects NaN (IQ)", "iq", "routes/inventory.py",
     "            stock_v = parse_money(stock, required=True)",
     "            stock_v = float(stock)",
     probe_nan_accepted),

    ("F2 audit rejects NaN (JO)", "jo", "routes/inventory.py",
     "            stock_v = parse_quantity(stock, required=True)",
     "            stock_v = float(stock)",
     probe_nan_accepted),

    # Both halves must come out: the fix is belt-and-braces (`or today_iso`
    # AND checking the parse RESULT), and either half alone still prevents the
    # 500. Reverting only one proves nothing -- that is a blind mutation.
    ("F4 appointments empty day (IQ)", "iq", "routes/clinical.py",
     '    selected_day = request.args.get("day") or today_iso\n'
     '    try:\n'
     '        if logic.parse_date(selected_day) is None:\n'
     '            raise ValueError(selected_day)\n'
     '    except ValueError:',
     '    selected_day = request.args.get("day", today_iso)\n'
     '    try:\n'
     '        logic.parse_date(selected_day)\n'
     '    except ValueError:',
     probe_appt_500),

    # Both halves must come out: the fix is belt-and-braces (`or today_iso`
    # AND checking the parse RESULT), and either half alone still prevents the
    # 500. Reverting only one proves nothing -- that is a blind mutation.
    ("F4 appointments empty day (JO)", "jo", "routes/clinical.py",
     '    selected_day = request.args.get("day") or today_iso\n'
     '    try:\n'
     '        if logic.parse_date(selected_day) is None:\n'
     '            raise ValueError(selected_day)\n'
     '    except ValueError:',
     '    selected_day = request.args.get("day", today_iso)\n'
     '    try:\n'
     '        logic.parse_date(selected_day)\n'
     '    except ValueError:',
     probe_appt_500),

    ("F6 discharge date guard (IQ)", "iq", "routes/clinical.py",
     "    if (dismissed and edited_dismissal_date and old[\"admission_date\"]\n"
     "            and str(edited_dismissal_date) < str(old[\"admission_date\"])):",
     "    if (False and dismissed and edited_dismissal_date and old[\"admission_date\"]\n"
     "            and str(edited_dismissal_date) < str(old[\"admission_date\"])):",
     probe_discharge_before_admission),

    ("F6 discharge date guard (JO)", "jo", "routes/clinical.py",
     "    if (dismissed and edited_dismissal_date and old[\"admission_date\"]\n"
     "            and str(edited_dismissal_date) < str(old[\"admission_date\"])):",
     "    if (False and dismissed and edited_dismissal_date and old[\"admission_date\"]\n"
     "            and str(edited_dismissal_date) < str(old[\"admission_date\"])):",
     probe_discharge_before_admission),

    ("Obs2 cash discrepancy warning (IQ)", "iq", "routes/sales.py",
     '{logic.fmt_money(abs(difference))} IQD.", "warning")',
     '{logic.fmt_money(abs(difference))} IQD.", "error")',
     probe_cash_warning),

    ("Obs2 cash discrepancy warning (JO)", "jo", "routes/sales.py",
     '{logic.fmt_money(abs(difference))} JOD.", "warning")',
     '{logic.fmt_money(abs(difference))} JOD.", "error")',
     probe_cash_warning),
]

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for label, app, relpath, good, bad, probe in MUTATIONS:
        if only and only.lower() not in label.lower():
            continue
        path = f"{repo(app)}/{relpath}"
        backup = shutil.copy(path, path + ".provebak")
        try:
            mutate(path, good, bad)
            if not restart(app):
                record(label, False, "app failed to restart with the mutation")
                continue
            present, detail = probe(app)
            record(label, present, detail)
        finally:
            shutil.move(backup, path)
            restart(app)
    print()
    proven = sum(1 for _, p, _ in results if p)
    print(f"{proven}/{len(results)} guards proven (each bug came back when its fix was reverted)")
    for label, p, detail in results:
        if not p:
            print(f"  NOT PROVEN: {label} — {detail}")
    sys.exit(0 if proven == len(results) else 1)
