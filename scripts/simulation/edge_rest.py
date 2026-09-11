"""Phase 2g — the remaining features: attachments, barcodes, record lifecycles,
deletes with children, settings/backup, and the update check."""
import sys, re, json, random, datetime, io
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes
from vzform import pick, inputs

D = datetime.date.today().isoformat()
TOM = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
PH = lambda app: ("0770" if app == "iq" else "079") + str(random.randint(10**6, 10**7 - 1))
PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


def run(app):
    c = Client(app); c.login(); F = c.finding
    print(f"\n=== {app.upper()}: attachments, lifecycles, deletes, settings ===", flush=True)

    # a visit to hang things off
    r = c.post("/visits/new/new-patient", {
        "owner_name": "Rest Test", "owner_phone": PH(app), "animal_name": "Rest",
        "species": "Dog", "date": D, "doctor": "Dr. A", "complaint": "x",
        "microchip": str(random.randint(10**14, 10**15 - 1))}, note="visit")
    m = re.search(r"/visits/(V\d+)", r.url)
    vid = m.group(1) if m else None
    pid = q(app, "select id from patients order by id desc limit 1")
    pid = pid[0][0] if pid else None
    print(f"  visit={vid} patient={pid}")

    # --- attachments ---------------------------------------------------
    if vid:
        cases = [
            ("normal.png", PNG, "image/png", False),
            ("../../escape.png", PNG, "image/png", True),
            ("shell;rm -rf.png", PNG, "image/png", True),
            ("no-extension", PNG, "application/octet-stream", True),
            ("script.svg", b"<svg onload=alert(1)></svg>", "image/svg+xml", True),
            ("huge.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024), "image/png", False),
            ("empty.png", b"", "image/png", True),
            ("‮np.gnp.exe", PNG, "image/png", True),
        ]
        for fname, data, ctype, risky in cases:
            r = c.post(f"/visits/{vid}/attachments", {},
                       files={"file": (fname, io.BytesIO(data), ctype)},
                       note=f"upload {fname!r}")
            if r.status_code >= 500:
                F("HTTP_5XX_UPLOAD", f"upload {fname!r} -> {r.status_code}")
        rows = q(app, "select relative_path,original_name from attachments order by id desc limit 10")
        for stored, orig in (rows or []):
            s = str(stored)
            if ".." in s or s.startswith("/") or "\\" in s:
                F("ATTACHMENT_PATH", f"attachment stored under a traversal-shaped name {s!r}")
        # serving them back
        rows = q(app, "select id from attachments order by id desc limit 1")
        if rows:
            for bad in ["../../../../etc/passwd", "..%2f..%2fetc%2fpasswd", "nonexistent.png"]:
                r = c.get(f"/files/{bad}", note="attachment traversal")
                if r.status_code == 200 and b"root:" in r.content[:400]:
                    F("PATH_TRAVERSAL", f"/files/{bad} served a system file")
                elif r.status_code >= 500:
                    F("HTTP_5XX_BAD_ID", f"/files/{bad} -> {r.status_code}")

    # --- barcodes --------------------------------------------------------
    inv = q(app, "select id from inventory_list where active=true order by id limit 1")
    if inv:
        iid = inv[0][0]
        r = c.post(f"/inventory-catalog/{iid}/barcode/generate", {}, note="generate barcode")
        c.expect_success(r, "generate barcode")
        r = c.get(f"/inventory-catalog/{iid}/barcode/status", note="barcode status")
        r = c.get(f"/inventory-catalog/{iid}/barcode-label", note="barcode label")
        if r.status_code >= 500:
            F("HTTP_5XX", f"barcode label -> {r.status_code}")
        for bad, label in [("", "empty"), ("abc", "letters"), ("-1", "negative"),
                           ("9" * 40, "overlong"), ("<script>", "markup")]:
            r = c.post(f"/inventory-catalog/{iid}/barcode/manual", {"barcode": bad},
                       note=f"manual barcode {label}")
            if r.status_code >= 500:
                F("HTTP_5XX_ON_BAD_INPUT", f"manual barcode {label!r} -> {r.status_code}")
        r = c.post(f"/inventory-catalog/{iid}/barcode/remove", {}, note="remove barcode")
        r = c.get("/inventory-catalog/barcodes/generated", note="generated barcodes")
        c.expect_success(r, "generated barcode list")

    # --- inpatient lifecycle --------------------------------------------
    if pid:
        npg = c.get("/inpatient/new")
        vet = pick(npg.text, "attending_vet_id")
        r = c.post("/inpatient/new", {
            "patient_id": pid, "admission_date": D, "attending_vet_id": vet or "",
            "supervising_vet_id": vet or "", "complaint": "obs", "exam_findings": "stable",
            "weight_kg": "10", "bcs": "5"}, note="admit")
        cid = re.search(r"/inpatient/(\d+)", r.url)
        if cid:
            cid = cid.group(1)
            ed = c.get(f"/inpatient/{cid}")
            stamp = inputs(ed.text).get("expected_updated_at", "")
            # discharge
            r = c.post(f"/inpatient/{cid}/edit", {
                "admission_date": D, "attending_vet_id": vet or "", "complaint": "obs",
                "dismissed": "Y", "dismissal_date": D, "expected_updated_at": stamp,
                "weight_kg": "10"}, note="discharge")
            c.expect_success(r, "discharge inpatient")
            # discharge dated before admission
            r = c.post(f"/inpatient/{cid}/edit", {
                "admission_date": D, "attending_vet_id": vet or "", "complaint": "obs",
                "dismissed": "Y", "dismissal_date": "2020-01-01",
                "expected_updated_at": inputs(c.get(f"/inpatient/{cid}").text).get("expected_updated_at", ""),
                "weight_kg": "10"}, note="discharge before admission")
            c.expect_refusal(r, "discharge dated before admission")
            # billing a discharged case
            r = c.post(f"/inpatient/{cid}/billing", {"price_id": "PL301", "qty_PL301": "1"},
                       note="bill after discharge")

    # --- boarding lifecycle ---------------------------------------------
    if pid:
        r = c.post("/boarding/new", {
            "patient_id": pid, "entry_date": D, "dismissal_date": TOM,
            "price_per_day": "1000" if app == "iq" else "10.000",
            "total": "1000" if app == "iq" else "10.000", "room": "K9"}, note="boarding")
        c.expect_success(r, "boarding intake")
        b = q(app, "select id from boarding_sessions order by id desc limit 1")
        if b:
            bid = b[0][0]
            # dismissal before entry
            r = c.post(f"/boarding/{bid}/edit", {
                "entry_date": D, "dismissal_date": "2020-01-01",
                "price_per_day": "1000" if app == "iq" else "10.000",
                "total": "1000" if app == "iq" else "10.000", "room": "K9",
                "expected_updated_at": ""}, note="boarding end before start")
            if r.status_code >= 500:
                F("HTTP_5XX_ON_BAD_INPUT", f"boarding end-before-start -> {r.status_code}")
            r = c.post(f"/boarding/{bid}/dismiss", {}, note="dismiss boarding")
            c.expect_success(r, "dismiss boarding")
            r = c.post(f"/boarding/{bid}/dismiss", {}, note="dismiss twice")
            if r.status_code >= 500:
                F("HTTP_5XX", f"double dismiss -> {r.status_code}")

    # --- deletes with children (orphan guards) ---------------------------
    dist = q(app, "select id from distributors order by id limit 1")
    if dist:
        did = dist[0][0]
        r = c.post(f"/distributors/{did}/delete", {}, note="delete distributor with history")
        still = q(app, "select count(*) from distributors where id=%s", (did,))[0][0]
        orph = q(app, "select count(*) from inventory_list where distributor_id=%s", (did,))[0][0]
        if still == 0 and orph:
            F("ORPHANED_ROWS",
              f"distributor {did} was deleted leaving {orph} inventory row(s) pointing at it")
    pl = q(app, "select id from price_list where id<>'PL301' order by id limit 1")
    if pl:
        r = c.post(f"/price-list/{pl[0][0]}/delete", {}, note="delete price list item")
        if r.status_code >= 500:
            F("HTTP_5XX", f"price list delete -> {r.status_code}")

    # --- settings / backup ------------------------------------------------
    s = c.get("/settings", note="settings")
    palette = pick(s.text, "theme_palette")
    r = c.post("/settings", {"theme_palette": palette or "vetzone",
                             "appt_start_time": "09:00", "appt_end_time": "18:00",
                             "backup_time": "00:30", "selfcheck_present": "1",
                             "selfcheck_enabled": "on"}, note="save settings")
    c.expect_success(r, "save settings")
    # nonsense times
    for st, en, label in [("25:00", "18:00", "hour 25"), ("18:00", "09:00", "end before start"),
                          ("abc", "def", "not times"), ("", "", "blank")]:
        r = c.post("/settings", {"theme_palette": palette or "vetzone",
                                 "appt_start_time": st, "appt_end_time": en,
                                 "backup_time": "00:30", "selfcheck_present": "1"},
                   note=f"settings times {label}")
        if r.status_code >= 500:
            F("HTTP_5XX_ON_BAD_INPUT", f"settings times {label!r} -> {r.status_code}")
    r = c.post("/settings", {"theme_palette": palette or "vetzone", "appt_start_time": "09:00",
                             "appt_end_time": "18:00", "backup_time": "99:99",
                             "selfcheck_present": "1"}, note="bad backup time")
    if r.status_code >= 500:
        F("HTTP_5XX_ON_BAD_INPUT", f"settings backup_time 99:99 -> {r.status_code}")
    r = c.post("/settings/backup-now", {}, note="backup now")
    if r.status_code >= 500:
        F("HTTP_5XX", f"backup-now -> {r.status_code}")
    r = c.get("/settings/updates/check", note="check for updates")
    if r.status_code >= 500:
        F("HTTP_5XX", f"updates/check -> {r.status_code}")
    r = c.get("/settings/updates/status", note="update status")
    r = c.post("/settings/restore-now", {"source_file": "/etc/passwd"}, note="restore from a system file")
    c.expect_refusal(r, "restore from an arbitrary path")
    r = c.post("/settings/restore-now", {"source_file": "../../../../etc/shadow"},
               note="restore traversal")
    c.expect_refusal(r, "restore traversal")

    print(f"  -- {app}: {len(c.findings)} findings, {len(c.events)} requests")
    return c


if __name__ == "__main__":
    allf = []
    for app in ("iq", "jo"):
        allf += run(app).findings
    json.dump(allf, open(f"{SIM}/../findings_rest.json", "w"), indent=2, default=str)
    print(f"\nTOTAL: {len(allf)}")
