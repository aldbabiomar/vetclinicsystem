"""Phase 1 — a typical day at the clinic, exercising every feature area.
Everything here is routine staff work; an error flash or 5xx is a real bug."""
import sys, re, json, datetime, random
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, flashes, APPS, q
from vzform import selects, pick, inputs, radios

TODAY = datetime.date.today()
D = TODAY.isoformat()
YEST = (TODAY - datetime.timedelta(days=1)).isoformat()
TOM = (TODAY + datetime.timedelta(days=1)).isoformat()
MON = TODAY.strftime("%Y-%m")

def M(app, whole, frac=0):
    """A realistic charge in that app's currency: IQD whole notes, JOD 3dp."""
    return str(whole * 1000) if app == "iq" else f"{whole}.{frac:03d}"

def uid(app, n=0):
    """A valid local mobile: IQ needs 10 local digits, JO needs 9."""
    r7 = str(random.randint(10**6, 10**7 - 1))
    return ("0770" + r7) if app == "iq" else ("079" + r7)

def priced(app):
    """A priced, active Price List row -- what a vet picks from the billing search."""
    rows = q(app, "select id from price_list where active and sale_price is not null order by id limit 1")
    return str(rows[0][0]) if rows else ""


def idof(r, pat):
    m = re.search(pat, r.url)
    return m.group(1) if m else None


def audit_everything(c, count, counts=None):
    """A shelf count of every item on the audit sheet, saved and confirmed:
    `count` each, or `counts[item_id]` where given."""
    r = c.post("/audit-history/start", note="start stock audit")
    c.expect_success(r, "start audit session")
    sid = idof(r, r"/session/(\d+)")
    if sid:
        pg = c.get(f"/audit-history/session/{sid}", note="audit sheet")
        ids = sorted(set(re.findall(r'name="stock_(\d+)"', pg.text)))
        print(f"  audit sheet items: {ids}", flush=True)
        if ids:
            data = {}
            for i in ids:
                data[f"stock_{i}"] = (counts or {}).get(i, count)
                data[f"received_{i}"] = "0"
                data[f"threshold_{i}"] = "10"
            r = c.post(f"/audit-history/session/{sid}/save", data, note="save counts")
            c.expect_success(r, "save audit counts")
            r = c.post(f"/audit-history/session/{sid}/confirm", data, note="confirm audit")
            c.expect_success(r, "confirm audit")


def run(app):
    c = Client(app, "admin"); c.login()
    st = {}
    P = lambda *a: print(*a, flush=True)
    P(f"\n=== {app.upper()}: a typical clinic day ===")

    # ---------- 08:30 open up ----------
    c.expect_success(c.get("/", note="dashboard"), "dashboard")
    c.expect_success(c.get("/health", note="health"), "health")

    # ---------- 08:45 stock take so retail can be sold ----------
    audit_everything(c, "40")

    # ---------- 09:00 reception registers clients ----------
    st["owners"] = []
    for name, addr in [("Ahmed Al-Rashid", "Karrada"), ("Fatima Hussein", "Mansour"),
                       ("Omar Khalid", "Zayouna")]:
        r = c.post("/owners/new", {"name": name, "phone": uid(app, 1), "address": addr,
                                   "notes": "New client"}, note=f"register {name}")
        if c.expect_success(r, f"register owner {name}"):
            o = idof(r, r"/owners/(\d+)")
            if o: st["owners"].append(o)
    P(f"  owners: {st['owners']}")
    if st["owners"]:
        c.expect_success(c.get(f"/owners/{st['owners'][0]}", note="owner card"), "owner detail")
        r = c.post(f"/owners/{st['owners'][0]}/edit",
                   {"name": "Ahmed Al-Rashid", "phone": uid(app, 1),
                    "address": "Karrada, near the bridge", "notes": "Prefers morning calls"},
                   note="update owner")
        c.expect_success(r, "edit owner")

    # ---------- 09:15 first consult: new pet, walk-in ----------
    r = c.post("/visits/new/new-patient", {
        "owner_name": "Layla Mahmoud", "owner_phone": uid(app, 2), "owner_address": "Jadriya",
        "animal_name": "Simba", "species": "Cat", "sex": "Male", "repro_status": "Neutered",
        "age_note": "3 years", "housing": "Indoor", "microchip": str(random.randint(10**14, 10**15 - 1)),
        "date": D, "doctor": "Dr. Sara", "complaint": "Not eating for two days",
        "history": "Indoor only, vaccinated", "weight_kg": "4.2", "bcs": "5",
    }, note="walk-in new patient+visit")
    c.expect_success(r, "new-patient visit")
    st["v1"] = idof(r, r"/visits/(\d+)")
    P(f"  visit1={st['v1']}")

    # find the patient id for later
    pr = c.get("/patients", note="patients list")
    m = re.search(r'/patients/(\d+)', pr.text)
    st["p1"] = m.group(1) if m else None
    P(f"  patient1={st['p1']}")

    # ---------- 09:40 vet writes up the consult ----------
    if st["v1"]:
        c.expect_success(c.get(f"/visits/{st['v1']}", note="open visit"), "visit detail")
        ed = c.get(f"/visits/{st['v1']}/edit", note="edit form")
        exp = inputs(ed.text).get("expected_updated_at", "")
        r = c.post(f"/visits/{st['v1']}/edit", {
            "date": D, "doctor": "Dr. Sara", "visit_type": "Outpatient",
            "complaint": "Not eating for two days", "history": "Indoor only",
            "exam": "Mild dehydration, T 39.1C, abdomen soft, MM pink",
            "treatment": "SC fluids 100ml; appetite stimulant; recheck 48h",
            "weight_kg": "4.2", "bcs": "5", "case_status": "Ongoing",
            "expected_updated_at": exp,
            "followup_needed": "Y", "followup_date": TOM, "followup_method": "Phone Call",
            "followup_reason": "Check appetite", "followup_status": "Pending",
            "wellness_needed": "Y", "wellness_type": "Annual Vaccine",
            "wellness_next_dose_date": TOM,
        }, note="vet writes exam/treatment")
        c.expect_success(r, "visit edit (SOAP)")

        # bill the consult from the price list
        pl = priced(app)
        r = c.post(f"/visits/{st['v1']}/billing", {
            "billing_type": "Automatic", "price_id": pl, f"qty_{pl}": "2",
            "date_billed": D, "notes": "Consult + meds",
        }, note="bill visit from price list")
        c.expect_success(r, "visit billing (automatic)")
        # discount for a regular client
        r = c.post(f"/visits/{st['v1']}/discount", {"discount_percent": "10"}, note="10% discount")
        c.expect_success(r, "visit discount")
        # client pays
        r = c.post(f"/visits/{st['v1']}/payment", {
            "amount": M(app, 5), "method": "Cash", "date": D, "notes": "Part payment",
        }, note="part payment")
        c.expect_success(r, "visit payment")
        r = c.get(f"/visits/{st['v1']}/export", note="print visit")
        if r.status_code >= 400:
            c.finding("EXPORT_FAIL", f"visit PDF export -> {r.status_code}")

    # ---------- 10:00 appointment book (the admin adds the clinic's vet first) ----------
    vet_role = q(app, "select id from roles where is_vet_role order by id limit 1")
    if vet_role and not q(app, "select 1 from users u join roles r on r.id=u.role_id where r.is_vet_role and u.active"):
        r = c.post("/admin/users/new", {"username": f"sara{random.randint(1000, 9999)}", "full_name": "Dr. Sara",
                                        "password": "Clinic-Vet-2026!", "role_id": str(vet_role[0][0])},
                   note="admin adds a vet")
        c.expect_success(r, "add vet user")
    ap = c.get("/appointments", note="appointment book")
    c.expect_success(ap, "appointments page")
    # a free slot, as a receptionist would pick -- not always the first one,
    # which an earlier run of this script has already booked
    slots = sorted(set(re.findall(r"data-slot(?:-label)?=\"([^\"]+)\"", ap.text)))
    slot = random.choice(slots) if slots else None
    rid = re.search(r'data-resource-id="([^"]*)"', ap.text)
    r = c.post("/appointments/new", {
        "appt_date": TOM, "owner_name": "Ahmed Al-Rashid", "pet_name": "Rex",
        "appointment_type": "Medical", "reason": "Vaccination booster",
        "resource_type": "vet", "resource_id": (rid.group(1) if rid else ""),
        "slot_label": slot or "10:00",
    }, note="book appointment")
    c.expect_success(r, "book appointment")

    # ---------- 10:30 inpatient admission ----------
    npg = c.get("/inpatient/new", note="admission form")
    vet = pick(npg.text, "attending_vet_id") or pick(npg.text, "supervising_vet_id")
    if st["p1"]:
        r = c.post("/inpatient/new", {
            "patient_id": st["p1"], "admission_date": D, "attending_vet_id": vet or "",
            "supervising_vet_id": vet or "", "complaint": "Severe vomiting, dehydration",
            "exam_findings": "8% dehydrated, lethargic", "weight_kg": "4.0", "bcs": "4",
            "admitted_items": "Blue carrier, collar",
        }, note="admit inpatient")
        c.expect_success(r, "admit inpatient")
        st["case"] = idof(r, r"/inpatient/(\d+)")
        P(f"  inpatient case={st['case']}")
        if st["case"]:
            cid = st["case"]
            c.expect_success(c.get(f"/inpatient/{cid}", note="case board"), "inpatient detail")
            r = c.post(f"/inpatient/{cid}/update", {"note": "08:00 IV fluids started, BAR"},
                       note="nurse round note")
            c.expect_success(r, "inpatient update note")
            r = c.post(f"/inpatient/{cid}/contact", {"notes": "Owner called, updated on progress",
                                                    "picked_up": "Y"}, note="owner contact log")
            c.expect_success(r, "inpatient contact log")
            r = c.post(f"/inpatient/{cid}/billing", {"price_id": priced(app), f"qty_{priced(app)}": "3"},
                       note="bill inpatient items")
            c.expect_success(r, "inpatient billing")
            r = c.post(f"/inpatient/{cid}/discount", {"discount_percent": "5"}, note="inpatient discount")
            c.expect_success(r, "inpatient discount")
            r = c.post(f"/inpatient/{cid}/payment", {"amount": M(app, 3), "method": "Cash",
                                                     "date": D, "notes": "Deposit"},
                       note="inpatient deposit")
            c.expect_success(r, "inpatient payment")
            r = c.get(f"/inpatient/{cid}/export", note="print case")
            if r.status_code >= 400:
                c.finding("EXPORT_FAIL", f"inpatient PDF export -> {r.status_code}")

    # ---------- 11:00 boarding intake ----------
    if st["p1"]:
        r = c.post("/boarding/new", {
            "patient_id": st["p1"], "entry_date": D, "dismissal_date": TOM,
            "price_per_day": M(app, 10), "total": M(app, 10), "room": "K3",
            "admitted_items": "Food bowl, blanket", "special_needs": "Y",
            "special_needs_notes": "Needs medication at 6pm",
        }, note="boarding intake")
        c.expect_success(r, "boarding intake")
        bid = idof(r, r"/boarding/(\d+)") or None
        rows = q(app, "select id from boarding_sessions order by id desc limit 1")
        st["boarding"] = str(rows[0][0]) if rows else bid
        P(f"  boarding={st['boarding']}")
        if st["boarding"]:
            b = st["boarding"]
            r = c.post(f"/boarding/{b}/incident", {
                "issue": "Refused evening meal", "response": "Offered wet food, ate well",
                "contacted": "Y", "contact_method": "Phone"}, note="boarding incident")
            c.expect_success(r, "boarding incident")
            r = c.post(f"/boarding/{b}/payment", {"amount": M(app, 10), "method": "Cash",
                                                  "notes": "Paid in full", "discount_percent": "0"},
                       note="boarding payment")
            c.expect_success(r, "boarding payment")
            r = c.get(f"/boarding/{b}/export", note="boarding sheet")
            if r.status_code >= 400:
                c.finding("EXPORT_FAIL", f"boarding PDF export -> {r.status_code}")

    # ---------- 12:00 inventory & pricing upkeep ----------
    r = c.post("/inventory-catalog/new", {
        "name": "Amoxicillin 250mg", "category": "Medical", "unit": "Tablet",
        "cost_price": M(app, 1), "track_expiry": "on", "notes": "Antibiotic",
    }, note="add stock item")
    c.expect_success(r, "new inventory item")
    r = c.post("/price-list/new", {
        "name": "Amoxicillin 250mg (tab)", "category": "Medicine",
        "cost_price": M(app, 1), "sale_price": M(app, 2), "can_discount": "Y", "notes": "",
    }, note="add price list entry")
    c.expect_success(r, "new price list item")
    for p, l in [("/inventory-catalog", "catalog"), ("/price-list", "price list"),
                 ("/inventory-status", "stock status"), ("/ordering-sheet", "ordering sheet"),
                 ("/audit-history", "audit history")]:
        c.expect_success(c.get(p, note=l), f"{l} page")

    # ---------- 13:00 over-the-counter retail ----------
    c.expect_success(c.get("/pos", note="POS"), "POS page")
    rows = q(app, "select id from inventory_list where name='Test Retail Item'")
    retail = str(rows[0][0]) if rows else ""
    r = c.post("/pos/checkout", {
        "item_id": retail, "quantity": "2", "payment_method": "Cash",
        "discount_percent": "0", "cash_received": M(app, 50),
        "idempotency_key": f"day-{app}-{random.randint(1,10**9)}",
    }, note="retail sale 2 units")
    c.expect_success(r, "POS checkout")
    st["sale"] = idof(r, r"/receipt/(\d+)")
    rows = q(app, "select id from sales order by id desc limit 1")
    st["sale"] = st["sale"] or (str(rows[0][0]) if rows else None)
    P(f"  sale={st['sale']}")
    if st["sale"]:
        c.expect_success(c.get(f"/pos/receipt/{st['sale']}", note="receipt"), "receipt")
        r = c.get(f"/pos/history/{st['sale']}/export", note="print receipt")
        if r.status_code >= 400:
            c.finding("EXPORT_FAIL", f"receipt export -> {r.status_code}")
    c.expect_success(c.get("/pos/history", note="sales history"), "POS history")

    # ---------- 14:00 a customer returns an item ----------
    if st["sale"]:
        rp = c.get(f"/api/sales/{st['sale']}/refundable-items", note="lookup refundables")
        try:
            items = rp.json()
        except Exception:
            items = None
        sii = None
        if isinstance(items, dict):
            lst = items.get("lines") or items.get("items") or []
            if lst:
                sii = str(lst[0].get("sale_item_id") or lst[0].get("id"))
        if sii:
            r = c.post("/refunds/retail", {
                "sale_id": st["sale"], "sale_item_id": sii, "quantity": "1",
                "reason": "Wrong size, unopened", "refund_date": D,
                "refund_method": "Cash", "restock": "on",
            }, note="retail refund 1 unit")
            c.expect_success(r, "retail refund")
        else:
            c.finding("API_SHAPE", f"refundable-items returned no usable items: {str(items)[:200]}")
    if st["v1"]:
        r = c.post("/refunds/service", {
            "visit_id": st["v1"], "amount": M(app, 1), "reason": "Service not performed",
            "refund_date": D, "refund_method": "Cash",
        }, note="service refund")
        c.expect_success(r, "service refund")

    # ---------- 15:00 supplier / consignment work ----------
    r = c.post("/distributors/new", {
        "name": "Baghdad Vet Supplies", "contact_person": "Mr. Salim", "phone": uid(app, 3),
        "email": "sales@bvs.example", "payment_terms": "Net 30", "lead_time_days": "7",
        "notes": "Main supplier", "catalog_link": "https://example.com/catalog",
    }, note="add supplier")
    c.expect_success(r, "new distributor")
    rows = q(app, "select id from distributors where name='Baghdad Vet Supplies' order by id desc limit 1")
    st["dist"] = str(rows[0][0]) if rows else None
    P(f"  distributor={st['dist']}")
    if st["dist"]:
        d = st["dist"]
        c.expect_success(c.get(f"/distributors/{d}", note="supplier card"), "distributor detail")
        r = c.post(f"/distributors/{d}/bills/new", {
            "bill_date": D, "bill_reference": "INV-2026-441", "total_amount": M(app, 100),
            "notes": "Monthly order",
        }, note="record supplier bill")
        c.expect_success(r, "distributor bill")
        rows = q(app, "select id from distributor_bills order by id desc limit 1")
        bill = str(rows[0][0]) if rows else None
        if bill:
            r = c.post(f"/distributors/{d}/bills/{bill}/payments/new", {
                "amount": M(app, 40), "method": "Transfer", "payment_date": D,
                "notes": "Part payment",
            }, note="pay supplier")
            c.expect_success(r, "distributor payment")
        r = c.get(f"/distributors/{d}/export.pdf", note="supplier statement")
        if r.status_code >= 400:
            c.finding("EXPORT_FAIL", f"distributor PDF -> {r.status_code}")

    # consignment stock movements — a supplier-owned line first
    r = c.post("/inventory-catalog/new", {
        "name": f"Flea Collar {random.randint(100,999)}", "category": "Retail", "unit": "Each",
        "cost_price": M(app, 2), "notes": "Supplier-owned stock",
        "distributor_id": st.get("dist") or "",
    }, note="add retail item (supplier stock)")
    c.expect_success(r, "new retail item")
    rows = q(app, "select id from inventory_list where category='Retail' order by id desc limit 1")
    citem = str(rows[0][0]) if rows else ""
    if st.get("dist"):
        rj = c.post_json("/consignment/items/bulk-edit", {"items": [
            {"id": citem, "fields": {"is_consignment": "on", "distributor_id": st["dist"],
                                     "cost_price": M(app, 2)}}]}, note="flag item as consignment")
        try:
            body = rj.json()
        except Exception:
            body = {}
        if not body.get("ok"):
            c.finding("BULK_EDIT_REFUSED", f"flag consignment failed: {str(body)[:200]}")
    rec = c.get("/consignment/receiving", note="receiving page")
    r = c.post("/consignment/receiving/new", {
        "item_id": citem, "quantity": "20", "unit_cost": M(app, 1), "received_date": D,
        "delivery_reference": "DN-8891", "notes": "Consignment delivery",
    }, note="receive consignment stock")
    c.expect_success(r, "consignment receiving")
    # a shelf count before anything goes back: returns and shrinkage are
    # checked against audited stock
    audit_everything(c, "40", counts={citem: "20"})
    # priced, so it can be sold -- the sale is what the supplier is owed for
    r = c.post("/price-list/new", {"name": "Flea Collar (each)", "category": "Retail", "cost_price": M(app, 2),
                                   "sale_price": M(app, 4), "linked_item_id": citem, "can_discount": "Y"},
               note="price the consigned item")
    c.expect_success(r, "price consigned item")
    r = c.post("/pos/checkout", {"item_id": citem, "quantity": "1", "payment_method": "Cash",
                                 "discount_percent": "0", "cash_received": M(app, 10),
                                 "idempotency_key": f"day-c-{app}-{random.randint(1, 10**9)}"},
               note="sell a consigned unit")
    c.expect_success(r, "sell consigned unit")
    r = c.post("/consignment/returns/new", {
        "item_id": citem, "quantity": "2", "reason": "Near expiry", "return_date": D,
        "notes": "Returned to rep",
    }, note="return to supplier")
    c.expect_success(r, "consignment return")
    r = c.post("/consignment/shrinkage/new", {
        "item_id": citem, "quantity": "1", "reason": "Damaged", "liable_party": "Clinic",
        "notes": "Dropped during round",
    }, note="record shrinkage")
    c.expect_success(r, "consignment shrinkage")
    for p, l in [("/consignment", "consignment overview"), ("/consignment/items", "consignment items"),
                 ("/consignment/sales", "consignment sales")]:
        c.expect_success(c.get(p, note=l), f"{l} page")
    if st["dist"]:
        sp = c.get(f"/consignment/settlements/{st['dist']}", note="settlement page")
        c.expect_success(sp, "settlements page")
        r = c.post(f"/consignment/settlements/{st['dist']}/new", {
            "amount_paid": M(app, 1), "payment_method": "Cash", "notes": "Part settlement",
        }, note="settle with supplier")
        c.expect_success(r, "consignment settlement")

    # ---------- 17:00 cash up ----------
    cr = c.get("/cash-register", note="cash register")
    c.expect_success(cr, "cash register page")
    r = c.post("/cash-register/payout", {"day": D, "amount": ("5" if app == "iq" else "1.000"),
                                         "reason": "Petty cash — cleaning supplies"},
               note="petty cash payout")
    c.expect_success(r, "cash payout")
    r = c.post("/cash-register/audit", {"day": D, "counted_cash": ("5" if app == "iq" else "9.000"),
                                        "notes": "End of day count"}, note="end-of-day count")
    c.expect_success(r, "cash count")

    # ---------- 17:30 worklists & follow-ups ----------
    fu = c.get("/followups", note="followups")
    c.expect_success(fu, "followups page")
    if st["v1"]:
        r = c.post(f"/followups/{st['v1']}/status", {"status": "Done"}, note="close followup")
        c.expect_success(r, "followup status")
        r = c.post(f"/wellness/{st['v1']}/update", {"wellness_contacted": "Y",
                                                    "wellness_contact_method": "Phone"},
                   note="wellness call done")
        c.expect_success(r, "wellness update")
    for p, l in [("/wellness", "wellness"), ("/grooming", "grooming"), ("/boarding", "boarding")]:
        c.expect_success(c.get(p, note=l), f"{l} page")

    # ---------- 18:00 owner reviews the numbers ----------
    for p, l in [("/reports", "reports"), ("/reports/yearly", "yearly"), ("/insights", "insights"),
                 ("/retention", "retention"), ("/refunds", "refunds")]:
        c.expect_success(c.get(p, note=l), f"{l} page")
    r = c.post("/reports/opex", {"month": MON, "rent": M(app, 100), "salaries": M(app, 200),
                                 "utilities": M(app, 30), "marketing": M(app, 10),
                                 "other": M(app, 5)}, note="enter monthly costs")
    c.expect_success(r, "opex save")

    # ---------- 18:15 admin housekeeping ----------
    au = c.get("/admin/users", note="staff list")
    c.expect_success(au, "admin users")
    role_recep = pick(au.text, "role_id", contains="Reception") or pick(au.text, "role_id")
    r = c.post("/admin/users/new", {
        "username": f"reception{random.randint(100,999)}", "full_name": "Nour Reception",
        "password": "Str0ngPass!23", "role_id": role_recep or "", "capmode": "role",
    }, note="add staff account")
    c.expect_success(r, "create user")
    r = c.post("/admin/roles/new", {
        "name": f"Night Nurse {random.randint(10,99)}", "description": "Overnight inpatient care",
        "discount_cap": "5", "is_vet_role": "N",
        "permissions": ["view_inpatient", "manage_inpatient"],
    }, note="create custom role")
    c.expect_success(r, "create role")
    c.expect_success(c.get("/admin/logs", note="audit log"), "admin logs")
    c.expect_success(c.get("/settings", note="settings"), "settings page")

    P(f"  -- {app}: {len(c.events)} requests, {len(c.findings)} findings")
    return c, st


if __name__ == "__main__":
    allf = []
    for app in ("iq", "jo"):
        c, st = run(app)
        allf += c.findings
    out = f"{SIM}/../findings_day.json"
    json.dump(allf, open(out, "w"), indent=2, default=str)
    print(f"\nTOTAL day findings: {len(allf)}")
