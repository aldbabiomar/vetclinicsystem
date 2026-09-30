#!/usr/bin/env python3
"""
A clinic's license run out and renewed, against a running app
(docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §16, phase 8).

    /tmp/vcs_test_venv_jo/bin/python scripts/simulation/license_day.py jo     # or iq

It signs keys with the environment's own throwaway vendor key
(<data dir>/test-vendor/private.pem, written by scripts/isolated_test_env.sh)
for its install ID, and enters each on Settings -> License, as a clinic does:

  1. active    -- saving works;
  2. expiring  -- 5 days left: the administrator sees the warning;
  3. grace     -- expired 3 days ago: the grace banner, and saving still works;
  4. read-only -- expired past its grace. The administrator who entered it,
                  still signed in, keeps working (never mid-task). Someone
                  signing in now is read-only: a new owner and a payment are
                  refused; a note on an admitted animal, Back Up Now and the
                  data export are not;
  5. renewed   -- a one-year key: that read-only session saves again without
                  signing out.

Then each key entered, and the Developer Pass, are looked for in the app's
logs and in both audit tables (§13). Rows it makes are removed at the end;
the environment keeps its one-year license.

Exit status 0 when every step behaved; 1 with the findings otherwise.
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "scripts" / "vendor"))

import vzsim  # noqa: E402
import vcs_vendor  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402

DATA = {"iq": Path("/tmp/vcs_test_data_iq"), "jo": Path("/tmp/vcs_test_data_jo")}
# A local number of each setting's length, the last four digits varied: the
# app refuses a second owner with the same number.
PHONES = {"iq": "0770123{:04d}", "jo": "079123{:04d}"}
READ_ONLY_PAGE = "The system is read-only"


def main(app):
    data = DATA[app]
    key = serialization.load_pem_private_key((data / "test-vendor" / "private.pem").read_bytes(), password=None)
    install_id = (data / "install_id").read_text().strip()
    dev_pass = (data / "test-vendor" / "dev_pass.txt").read_text().strip()
    now = datetime.now(timezone.utc)
    problems, entered = [], []

    def check(ok, what):
        print(f"  [{'ok' if ok else 'FAIL'}] {what}", flush=True)
        if not ok:
            problems.append(what)

    def sign(days_from_now):
        payload = vcs_vendor.license_payload(key, install_id, "Test Clinic", now + timedelta(days=days_from_now),
                                             issued_at=now - timedelta(days=400))
        token = vcs_vendor.sign(key, payload)
        entered.append(token)
        return token

    def enter(client, days, label):
        r = client.post("/settings/license", {"license_key": sign(days)})
        check(r.status_code < 400 and "License key saved" in r.text, f"{label}: the key is accepted")
        return r

    serial = [int(time.time()) % 5000]

    def new_owner(client, name):
        serial[0] += 1
        return client.post("/owners/new", {"name": name, "phone": PHONES[app].format(serial[0])})

    # Fixtures: an admitted animal for the welfare note, a visit for a payment,
    # and a backup folder for Back Up Now.
    tag = f"LicenseDay{int(time.time())}"
    backup_dir = Path(f"/tmp/vcs_license_day_{app}")
    backup_dir.mkdir(exist_ok=True)
    with vzsim.db(app) as con:
        owner = con.execute("INSERT INTO owners (name) VALUES (%s) RETURNING id", (tag,)).fetchone()[0]
        pet = con.execute("INSERT INTO patients (owner_id, animal_name, species, sex) VALUES (%s,%s,'Dog','Male') "
                          "RETURNING id", (owner, tag)).fetchone()[0]
        visit = con.execute("INSERT INTO visits (patient_id, date, case_status) VALUES (%s, CURRENT_DATE, 'Ongoing') "
                            "RETURNING id", (pet,)).fetchone()[0]
        case = con.execute("INSERT INTO inpatient_cases (patient_id, admission_date, dismissed, discount_percent, "
                           "total, cleanup_amount) VALUES (%s, CURRENT_DATE, false, 0, 0, 0) RETURNING id",
                           (pet,)).fetchone()[0]
        old_backup_dir = con.execute("SELECT value FROM settings WHERE key='backup_dir'").fetchone()
        con.execute("INSERT INTO settings (key, value) VALUES ('backup_dir', %s) "
                    "ON CONFLICT (key) DO UPDATE SET value=excluded.value", (str(backup_dir),))
        con.commit()

    admin = vzsim.Client(app, "admin")
    try:
        admin.login()
        print(f"{app.upper()} — 1. active")
        check(admin.expect_success(new_owner(admin, tag + " A"), "active: a new owner"), "active: saving works")

        print(f"{app.upper()} — 2. expiring")
        enter(admin, 5, "expiring")
        check("The license expires on" in admin.get("/").text, "expiring: the administrator sees the warning")

        print(f"{app.upper()} — 3. grace")
        enter(admin, -3, "grace")
        check("becomes read-only on" in admin.get("/").text, "grace: the banner gives the read-only date")
        check(admin.expect_success(new_owner(admin, tag + " B"), "grace: a new owner"), "grace: saving works")

        print(f"{app.upper()} — 4. read-only")
        enter(admin, -30, "read-only")
        check(admin.expect_success(new_owner(admin, tag + " C"), "read-only, signed in before"),
              "read-only: the session that was already working keeps working")
        nurse = vzsim.Client(app, "admin, signing in now")
        nurse.login()
        check("so the system is read-only" in nurse.get("/").text, "read-only: the banner says so")
        r = new_owner(nurse, tag + " D")
        check(r.status_code == 403 and READ_ONLY_PAGE in r.text, "read-only: a new owner is refused")
        r = nurse.post(f"/visits/{visit}/payment", {"amount": "1", "method": "Cash"})
        check(r.status_code == 403 and READ_ONLY_PAGE in r.text, "read-only: a payment is refused")
        r = nurse.post(f"/inpatient/{case}/update", {"note": "Ate well, " + tag})
        with vzsim.db(app) as con:
            kept = con.execute("SELECT count(*) FROM inpatient_updates WHERE case_id=%s AND note LIKE %s",
                               (case, "%" + tag)).fetchone()[0]
        check(r.status_code < 400 and READ_ONLY_PAGE not in r.text and kept == 1,
              "read-only: a note on an admitted animal is kept")
        r = nurse.post("/settings/backup-now")
        check(r.status_code == 200 and "job_id" in r.text, "read-only: Back Up Now starts")
        job = r.json().get("job_id")
        for _ in range(120):
            status = nurse.get(f"/settings/job-status?job_id={job}").json()
            if status.get("status") != "running":
                break
            time.sleep(0.5)
        check(status.get("ok") is True, f"read-only: the backup finishes ({status.get('message')})")
        r = nurse.post("/settings/data-export/start")
        check(r.status_code == 200 and "job_id" in r.text, "read-only: the data export starts")
        job = r.json().get("job_id")
        for _ in range(240):
            status = nurse.get(f"/settings/job-status?job_id={job}").json()
            if status.get("status") != "running":
                break
            time.sleep(0.5)
        check(status.get("ok") is True, f"read-only: the export finishes ({status.get('message')})")

        print(f"{app.upper()} — 5. renewed")
        enter(admin, 365, "renewed")
        check(nurse.expect_success(new_owner(nurse, tag + " E"), "renewed: a new owner"),
              "renewed: the read-only session saves again without signing out")

        print(f"{app.upper()} — secrets (§13)")
        logs = "".join(p.read_text(errors="replace") for p in [*(data / "logs").glob("*.log*"), *data.glob("*.log")]
                       if p.is_file())
        with vzsim.db(app) as con:
            audits = " ".join(str(r) for t in ("developer_audit", "audit_log", "login_log")
                              for r in con.execute(f"SELECT * FROM {t} ORDER BY id DESC LIMIT 500").fetchall())
        leaks = [where for token in entered + [dev_pass] for where, text in (("logs", logs), ("audit", audits))
                 if token in text]
        check(not leaks and len(entered) == 4 and logs, f"no key and no pass in the logs or the audit tables {leaks}")
        with vzsim.db(app) as con:
            recorded = con.execute("SELECT count(*) FROM developer_audit WHERE action='license.entered' "
                                   "AND at > now() - interval '10 minutes'").fetchone()[0]
        check(recorded >= 4, f"each key entered is in the Developer Audit ({recorded})")
    finally:
        # The environment keeps a license: a failure above must not leave it read-only.
        (data / "license" / "license.key").write_text(sign(365) + "\n")
        try:
            vzsim.Client(app, "restore").login()        # a sign-in works the state out again
        except Exception as e:
            problems.append(f"the one-year license could not be put back: {e}")
        with vzsim.db(app) as con:
            owners = [r[0] for r in con.execute("SELECT id FROM owners WHERE name LIKE %s", (tag + "%",)).fetchall()]
            con.execute("DELETE FROM inpatient_updates WHERE case_id=%s", (case,))
            con.execute("DELETE FROM inpatient_cases WHERE id=%s", (case,))
            con.execute("DELETE FROM visits WHERE id=%s", (visit,))
            con.execute("DELETE FROM patients WHERE owner_id = ANY(%s)", (owners,))
            con.execute("DELETE FROM owners WHERE id = ANY(%s)", (owners,))
            if old_backup_dir:
                con.execute("UPDATE settings SET value=%s WHERE key='backup_dir'", (old_backup_dir[0],))
            else:
                con.execute("DELETE FROM settings WHERE key='backup_dir'")
            con.commit()

    print(f"\n{app.upper()}: {'every step behaved' if not problems else f'{len(problems)} problem(s)'}")
    for p in problems:
        print(f"  - {p}")
    return 0 if not problems else 1


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in DATA:
        sys.exit(f"usage: {sys.argv[0]} iq|jo")
    sys.exit(main(sys.argv[1]))
