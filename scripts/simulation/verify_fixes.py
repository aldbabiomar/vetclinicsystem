"""Re-run every finding's reproduction against the patched apps.
Each case prints BEFORE (what the audit measured) and NOW (what happens today),
and every guard is paired with a control so "refused" can be told apart from
"refused for the right reason". See CLAUDE.md §7.3.
"""
import os, sys, re, random, datetime
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes

D = datetime.date.today().isoformat()
PH = lambda app: ("0770" if app == "iq" else "079") + str(random.randint(10**6, 10**7 - 1))
ok = fail = 0


def check(label, condition, detail=""):
    global ok, fail
    if condition:
        ok += 1
        print(f"    PASS  {label}")
    else:
        fail += 1
        print(f"    FAIL  {label}  {detail}")


def stock_up(c, app, count="500", item="INV301"):
    r = c.post("/audit-history/start")
    sid = re.search(r"/session/(\d+)", r.url).group(1)
    pg = c.get(f"/audit-history/session/{sid}")
    ids = sorted(set(re.findall(r'name="stock_(INV\d+)"', pg.text)))
    data = {}
    for i in ids:
        data[f"stock_{i}"] = count if i == item else "0"
        data[f"received_{i}"] = "0"
    c.post(f"/audit-history/session/{sid}/save", data)
    r = c.post(f"/audit-history/session/{sid}/confirm", data)
    return sid, [m for _, m in flashes(r.text)]


def sell(c, app, qty, disc="0", item="INV301"):
    n0 = q(app, "select count(*) from sales")[0][0]
    r = c.post("/pos/checkout", {"item_id": item, "quantity": str(qty),
                                 "payment_method": "Cash", "discount_percent": disc,
                                 "cash_received": "250000" if app == "iq" else "250.000",
                                 "idempotency_key": f"v-{random.randint(1,10**9)}"})
    made = q(app, "select count(*) from sales")[0][0] > n0
    row = q(app, "select id,subtotal,total,change_given from sales order by id desc limit 1")
    return made, (row[0] if row else None), [m for _, m in flashes(r.text)]


for app in ("iq", "jo"):
    print(f"\n{'='*66}\n{app.upper()}\n{'='*66}")
    c = Client(app); c.login()

    # ---------- F2: NaN / negative stock counts ----------
    # Uses a DRAFT session. A confirmed one refuses every save regardless of
    # value, so testing against it would pass whether or not the guard exists
    # -- that is exactly the blind test CLAUDE.md §7.3 warns about, and the
    # first version of this script had it.
    print("  F2/F5 — audit counts reject NaN, inf and negatives (draft session)")
    r = c.post("/audit-history/start")
    sid = re.search(r"/session/(\d+)", r.url).group(1)
    draft = q(app, "select status from audit_sessions where id=%s", (sid,))[0][0]
    check(f"session {sid} is a Draft (so a refusal means the VALUE was refused)",
          draft == "Draft", f"status={draft}")
    # seed it with a good value first, so "unchanged" proves the reject
    c.post(f"/audit-history/session/{sid}/save",
           {"stock_INV301": "5", "received_INV301": "0"})
    base = q(app, "select stock_counted from audit_session_lines "
                  "where session_id=%s and item_id='INV301'", (sid,))[0][0]
    check("CONTROL: a valid count of 5 saves into the draft", float(base) == 5.0, f"stored={base}")
    for bad in ("nan", "inf", "-inf", "-5", "1e400"):
        r = c.post(f"/audit-history/session/{sid}/save",
                   {"stock_INV301": bad, "received_INV301": "0"})
        stored = q(app, "select stock_counted from audit_session_lines "
                        "where session_id=%s and item_id='INV301'", (sid,))
        val = str(stored[0][0]) if stored else "none"
        msgs = [m for _, m in flashes(r.text)]
        check(f"count {bad!r} rejected, value still {val}",
              float(val) == 5.0 and any("valid number" in m.lower() for m in msgs),
              f"stored={val!r} msgs={msgs[:1]}")
    # CONTROL 2: a different valid value still saves afterwards, so the draft
    # was never simply locked by the failures above
    c.post(f"/audit-history/session/{sid}/save",
           {"stock_INV301": "7", "received_INV301": "0"})
    stored = q(app, "select stock_counted from audit_session_lines "
                    "where session_id=%s and item_id='INV301'", (sid,))[0][0]
    check("CONTROL: a valid count of 7 still saves after the rejections",
          float(stored) == 7.0, f"stored={stored}")
    # and confirming a draft holding only good values still works
    r = c.post(f"/audit-history/session/{sid}/confirm",
               {"stock_INV301": "7", "received_INV301": "0"})
    st = q(app, "select status from audit_sessions where id=%s", (sid,))[0][0]
    check("CONTROL: a clean draft still confirms", st == "Confirmed", f"status={st}")

    # ---------- F2 layer 2: a NaN already in the DB fails closed ----------
    print("  F2 — a NaN already stored fails closed instead of disabling the guard")
    sid2, _ = stock_up(c, app, "5")
    q(app, "UPDATE price_list SET sale_price=%s WHERE id='PL301'",
      (1000 if app == "iq" else "10.000",))
    # These are defence in depth: the CHECK constraint alone would refuse the
    # poisoned row, so the constraint has to come OFF to prove the application
    # layer independently. CLAUDE.md §7.4 -- disable one layer at a time, or
    # the test never reaches the guard it names.
    q(app, "ALTER TABLE audit_session_lines "
           "DROP CONSTRAINT IF EXISTS audit_session_lines_stock_counted_check")
    try:
        q(app, "UPDATE audit_session_lines SET stock_counted='NaN'::float8 "
               "WHERE session_id=%s AND item_id='INV301'", (sid2,))
        stored = q(app, "select stock_counted from audit_session_lines "
                        "where session_id=%s and item_id='INV301'", (sid2,))[0][0]
        check("constraint dropped, NaN row planted (proves the next check is real)",
              str(stored).lower() == "nan", f"stored={stored}")
        made, row, msgs = sell(c, app, 500)
        check("500 units NOT sold against a NaN count", not made,
              f"sale={row} msgs={msgs[:1]}")
        check("refused with the 'run an audit' message, not a 500",
              any("audit" in m.lower() for m in msgs), f"msgs={msgs[:2]}")
    finally:
        q(app, "DELETE FROM audit_session_lines WHERE stock_counted='NaN'::float8")
        q(app, "ALTER TABLE audit_session_lines ADD CONSTRAINT "
               "audit_session_lines_stock_counted_check CHECK (stock_counted IS NULL "
               "OR (stock_counted >= 0 AND stock_counted < 'Infinity'::float8))")

    # ---------- F1 / F3: IQ money rounding ----------
    if app == "iq":
        print("  F1 — a small POS sale is no longer free")
        stock_up(c, app, "500")
        for price, expect in ((100, 250), (120, 250), (10, 250), (10000, 10000)):
            q(app, "UPDATE price_list SET sale_price=%s WHERE id='PL301'", (price,))
            made, row, msgs = sell(c, app, 1)
            if not made:
                check(f"unit {price}: sold", False, f"refused {msgs[:1]}")
                continue
            _, sub, tot, chg = row
            label = "CONTROL: " if price == 10000 else ""
            check(f"{label}unit {price} -> total {tot} (expected {expect}), change {chg}",
                  float(tot) == expect, f"total={tot}")

        print("  F1 — the discount route is closed too")
        q(app, "UPDATE price_list SET sale_price=2000 WHERE id='PL301'")
        # admin's cap is 25%, so use the cap boundary; the 94% case needs a
        # high-cap role and is covered by repro_discount_role.py
        made, row, msgs = sell(c, app, 1, disc="25")
        check("2000 @25% discount -> non-zero total",
              made and float(row[2]) > 0, f"row={row}")

        print("  F3 — a small retail refund is no longer recorded as zero")
        q(app, "UPDATE price_list SET sale_price=240 WHERE id='PL301'")
        made, row, msgs = sell(c, app, 1)
        if made:
            sale_id = row[0]
            api = c.get(f"/api/sales/{sale_id}/refundable-items")
            lines = api.json().get("lines", [])
            if lines:
                c.post("/refunds/retail", {
                    "sale_id": str(sale_id), "sale_item_id": str(lines[0]["sale_item_id"]),
                    "quantity": "1", "reason": "Returned", "refund_date": D,
                    "refund_method": "Cash", "restock": "on"})
                ref = q(app, "select amount from refunds where sale_id=%s "
                             "order by id desc limit 1", (sale_id,))
                amt = float(ref[0][0]) if ref else None
                check(f"refund of a {row[2]} sale paid out {amt}, not 0",
                      amt is not None and amt > 0, f"refund={amt}")
                check("refund does not exceed what the sale collected",
                      amt is not None and amt <= float(row[2]) + 1e-9, f"{amt} vs {row[2]}")
        # CONTROL: a large refund still works normally
        q(app, "UPDATE price_list SET sale_price=10000 WHERE id='PL301'")
        made, row, msgs = sell(c, app, 1)
        if made:
            api = c.get(f"/api/sales/{row[0]}/refundable-items")
            lines = api.json().get("lines", [])
            if lines:
                c.post("/refunds/retail", {
                    "sale_id": str(row[0]), "sale_item_id": str(lines[0]["sale_item_id"]),
                    "quantity": "1", "reason": "Returned", "refund_date": D,
                    "refund_method": "Cash", "restock": "on"})
                ref = q(app, "select amount from refunds where sale_id=%s "
                             "order by id desc limit 1", (row[0],))
                check("CONTROL: a 10,000 refund still pays 10,000",
                      ref and float(ref[0][0]) == 10000.0, f"refund={ref}")

    # ---------- F4: appointments empty date ----------
    print("  F4 — /appointments?day= no longer 500s")
    for u in ("/appointments?day=", "/appointments?week=", "/appointments?day=&week=",
              "/appointments?day=abc", "/appointments"):
        r = c.s.get(c.base + u)
        check(f"GET {u} -> {r.status_code}", r.status_code < 500, f"status={r.status_code}")

    # ---------- F6: inpatient discharge before admission ----------
    print("  F6 — a discharge cannot predate the admission")
    from vzform import pick, inputs
    c.post("/visits/new/new-patient", {
        "owner_name": f"Verify {random.randint(1,10**6)}", "owner_phone": PH(app),
        "animal_name": "Verify", "species": "Dog", "date": D, "doctor": "Dr. A",
        "complaint": "x", "microchip": str(random.randint(10**14, 10**15 - 1))})
    pid = q(app, "select id from patients order by id desc limit 1")[0][0]
    npg = c.get("/inpatient/new")
    vet = pick(npg.text, "attending_vet_id")
    r = c.post("/inpatient/new", {
        "patient_id": pid, "admission_date": D, "attending_vet_id": vet or "",
        "supervising_vet_id": vet or "", "complaint": "obs", "exam_findings": "stable",
        "weight_kg": "10", "bcs": "5"})
    cid = re.search(r"/inpatient/(\d+)", r.url)
    if cid:
        cid = cid.group(1)

        def discharge(on):
            stamp = inputs(c.get(f"/inpatient/{cid}").text).get("expected_updated_at", "")
            rr = c.post(f"/inpatient/{cid}/edit", {
                "attending_vet_id": vet or "", "supervising_vet_id": vet or "",
                "complaint": "obs", "exam_findings": "stable", "weight_kg": "10",
                "bcs": "5", "dismissed": "on", "dismissal_date": on,
                "expected_updated_at": stamp})
            row = q(app, "select admission_date,dismissal_date from inpatient_cases "
                         "where id=%s", (cid,))[0]
            return row, [m for _, m in flashes(rr.text)]

        row, msgs = discharge("2024-01-01")
        check("discharge dated 2024 rejected", row[1] is None or str(row[1]) >= str(row[0]),
              f"stored dismissal={row[1]} admission={row[0]}")
        check("refused with a date message",
              any("admitted" in m.lower() or "date" in m.lower() for m in msgs), f"{msgs[:1]}")
        row, msgs = discharge(D)
        check("CONTROL: a same-day discharge still saves", str(row[1]) == D,
              f"stored={row[1]} msgs={msgs[:1]}")

    # ---------- Obs 2: cash discrepancy is a warning, not an error ----------
    print("  Obs2 — a saved cash count with a discrepancy flashes as a warning")
    r = c.post("/cash-register/audit", {"day": D, "counted_cash": "999999" if app == "iq" else "9999.000",
                                        "notes": "verify"})
    cats = {cat for cat, _ in flashes(r.text)}
    saved = q(app, "select status from cash_register_audits order by id desc limit 1")
    check("discrepancy flashed as 'warning'", "warning" in cats, f"categories={cats}")
    check("and the audit really was recorded", saved and saved[0][0] in ("Surplus", "Deficit"),
          f"row={saved}")

print(f"\n{'='*66}\nTOTAL: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
