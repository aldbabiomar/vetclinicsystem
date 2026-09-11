"""Does an inpatient case accept a discharge dated before admission?
(Boarding has an explicit guard; inpatient appears not to.)
Paired with a control so a refusal can't be mistaken for the wrong reason."""
import sys, re, random, datetime
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes
from vzform import pick, inputs

D = datetime.date.today().isoformat()
PH = lambda app: ("0770" if app == "iq" else "079") + str(random.randint(10**6, 10**7 - 1))

for app in ("iq", "jo"):
    c = Client(app); c.login()
    print(f"\n=== {app.upper()} ===")

    # a patient to admit
    c.post("/visits/new/new-patient", {
        "owner_name": f"Date Test {random.randint(1,10**6)}", "owner_phone": PH(app),
        "animal_name": "Datey", "species": "Dog", "date": D, "doctor": "Dr. A",
        "complaint": "x", "microchip": str(random.randint(10**14, 10**15 - 1))})
    pid = q(app, "select id from patients order by id desc limit 1")[0][0]

    npg = c.get("/inpatient/new")
    vet = pick(npg.text, "attending_vet_id")
    r = c.post("/inpatient/new", {
        "patient_id": pid, "admission_date": D, "attending_vet_id": vet or "",
        "supervising_vet_id": vet or "", "complaint": "obs", "exam_findings": "stable",
        "weight_kg": "10", "bcs": "5"})
    cid = re.search(r"/inpatient/(\d+)", r.url)
    if not cid:
        print("  could not admit:", [m for _, m in flashes(r.text)][:2]); continue
    cid = cid.group(1)

    def edit(dismissal, tag):
        page = c.get(f"/inpatient/{cid}")
        stamp = inputs(page.text).get("expected_updated_at", "")
        r = c.post(f"/inpatient/{cid}/edit", {
            "admission_date": D, "attending_vet_id": vet or "", "supervising_vet_id": vet or "",
            "complaint": "obs", "exam_findings": "stable", "weight_kg": "10", "bcs": "5",
            "dismissed": "on", "dismissal_date": dismissal,
            "expected_updated_at": stamp})
        row = q(app, "select admission_date,dismissal_date,dismissed from inpatient_cases where id=%s",
                (cid,))[0]
        print(f"  {tag:28s} flashes={[m for _,m in flashes(r.text)][:1]}")
        print(f"  {'':28s} stored admission={row[0]} dismissal={row[1]} dismissed={row[2]}")
        return row

    # CONTROL: a valid discharge must succeed, so a refusal below means something
    edit(D, "control: discharge today")
    # THE CASE: discharge two years before admission
    row = edit("2024-01-01", "discharge before admission")
    if row[1] and str(row[1]) < str(row[0]):
        print(f"  >>> ACCEPTED: case {cid} is discharged {row[1]}, admitted {row[0]} "
              f"— a negative-length stay")
