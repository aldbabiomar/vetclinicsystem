"""Phase 2f — two staff acting at the same moment, plus auth/CSRF/session."""
import sys, re, json, random, datetime, threading
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes
from vzform import inputs

D = datetime.date.today().isoformat()
PH = lambda app: ("0770" if app == "iq" else "079") + str(random.randint(10**6, 10**7 - 1))


def confirmed_stock(c, app, n):
    r = c.post("/audit-history/start")
    sid = re.search(r"/session/(\d+)", r.url).group(1)
    pg = c.get(f"/audit-history/session/{sid}")
    ids = sorted(set(re.findall(r'name="stock_(INV\d+)"', pg.text)))
    data = {}
    for i in ids:
        data[f"stock_{i}"] = str(n) if i == "INV301" else "0"
        data[f"received_{i}"] = "0"
    c.post(f"/audit-history/session/{sid}/save", data)
    c.post(f"/audit-history/session/{sid}/confirm", data)


def run(app):
    c = Client(app); c.login(); F = c.finding
    print(f"\n=== {app.upper()}: concurrency, auth, CSRF ===", flush=True)
    q(app, "UPDATE price_list SET sale_price=%s WHERE id='PL301'", (1000 if app == "iq" else "10.000",))

    # --- C1: two tills selling the last unit at the same instant -------
    confirmed_stock(c, app, 1)
    tills = [Client(app, f"till{i}") for i in range(2)]
    for t in tills:
        t.login()
    sold_before = q(app, "select count(*) from sales")[0][0]
    results = {}

    def buy(i):
        t = tills[i]
        r = t.post("/pos/checkout", {"item_id": "INV301", "quantity": "1",
                                     "payment_method": "Cash", "discount_percent": "0",
                                     "cash_received": "9999999" if app == "iq" else "99999.000",
                                     "idempotency_key": f"race-{i}-{random.randint(1,10**9)}"})
        results[i] = [m for _, m in flashes(r.text)]

    ts = [threading.Thread(target=buy, args=(i,)) for i in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    sold_after = q(app, "select count(*) from sales")[0][0]
    made = sold_after - sold_before
    print(f"  last-unit race: {made} sale(s) recorded from 2 simultaneous tills")
    if made > 1:
        F("OVERSELL_RACE",
          f"two simultaneous checkouts both sold the last unit — {made} sales for 1 unit of stock",
          dict(messages=results))

    # --- C2: two staff paying the same bill at the same instant --------
    r = c.post("/visits/new/new-patient", {
        "owner_name": "Race Test", "owner_phone": PH(app), "animal_name": "Race",
        "species": "Dog", "date": D, "doctor": "Dr. A", "complaint": "x",
        "microchip": str(random.randint(10**14, 10**15 - 1))}, note="visit")
    m = re.search(r"/visits/(V\d+)", r.url)
    if m:
        vid = m.group(1)
        c.post(f"/visits/{vid}/billing", {"billing_type": "Automatic", "price_id": "PL301",
                                          "qty_PL301": "1", "date_billed": D})
        total = q(app, "select total from billing where visit_id=%s", (vid,))[0][0]
        pay = {}

        def payer(i):
            t = tills[i]
            r = t.post(f"/visits/{vid}/payment", {"amount": str(total), "method": "Cash", "date": D})
            pay[i] = [m2 for _, m2 in flashes(r.text)]

        ts = [threading.Thread(target=payer, args=(i,)) for i in range(2)]
        [t.start() for t in ts]; [t.join() for t in ts]
        paid = q(app, "select coalesce(sum(amount),0) from payments where visit_id=%s", (vid,))[0][0]
        print(f"  double-payment race: bill {total}, recorded payments {paid}")
        if float(paid) > float(total) + 0.51:
            F("OVERPAYMENT_RACE",
              f"two simultaneous payments both landed: bill {total}, paid {paid}",
              dict(messages=pay))

    # --- C3: two receptionists booking the same slot -------------------
    ap = c.get("/appointments")
    rid = re.search(r'data-resource-id="([^"]*)"', ap.text)
    slot = "10:00"
    book = {}

    def booker(i):
        t = tills[i]
        r = t.post("/appointments/new", {
            "appt_date": D, "owner_name": f"Racer{i}", "pet_name": f"Pet{i}",
            "appointment_type": "Medical", "reason": "same slot",
            "resource_type": "vet", "resource_id": (rid.group(1) if rid else ""),
            "slot_label": slot})
        book[i] = [m2 for _, m2 in flashes(r.text)]

    n0 = q(app, "select count(*) from appointments where appt_date=%s and slot_label=%s", (D, slot))[0][0]
    ts = [threading.Thread(target=booker, args=(i,)) for i in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    n1 = q(app, "select count(*) from appointments where appt_date=%s and slot_label=%s", (D, slot))[0][0]
    print(f"  same-slot race: {n1-n0} appointment(s) created in one slot")
    if n1 - n0 > 1:
        F("DOUBLE_BOOKING",
          f"two simultaneous bookings both took the same vet slot ({n1-n0} appointments)",
          dict(messages=book))

    # --- C4: same phone registered twice at once -----------------------
    phone = PH(app)
    dup = {}

    def reg(i):
        t = tills[i]
        r = t.post("/owners/new", {"name": f"Dup{i}", "phone": phone, "address": "x"})
        dup[i] = [m2 for _, m2 in flashes(r.text)]

    ts = [threading.Thread(target=reg, args=(i,)) for i in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    n = q(app, "select count(*) from owners where phone=%s", ("+" + ("964" if app == "iq" else "962") + phone[1:],))
    cnt = n[0][0] if n else 0
    print(f"  duplicate-phone race: {cnt} owner(s) with that number")
    if cnt > 1:
        F("DUPLICATE_OWNER_RACE", f"{cnt} owners share one phone number after a simultaneous register")

    # --- A1: CSRF ------------------------------------------------------
    bare = Client(app, "csrf"); bare.login()
    r = bare.s.post(bare.base + "/owners/new",
                    data={"name": "No CSRF", "phone": PH(app)})
    if r.status_code < 400 and q(app, "select count(*) from owners where name='No CSRF'")[0][0]:
        F("CSRF_MISSING_TOKEN_ACCEPTED", "a POST with no CSRF token created an owner")
    r = bare.s.post(bare.base + "/owners/new",
                    data={"name": "Bad CSRF", "phone": PH(app), "csrf_token": "not-a-real-token"})
    if r.status_code < 400 and q(app, "select count(*) from owners where name='Bad CSRF'")[0][0]:
        F("CSRF_BAD_TOKEN_ACCEPTED", "a POST with a forged CSRF token created an owner")

    # --- A2: unauthenticated access ------------------------------------
    anon = Client(app, "anon")
    for p in ["/patients", "/pos", "/admin/users", "/settings", "/reports", "/cash-register"]:
        r = anon.s.get(anon.base + p, allow_redirects=True)
        if "/login" not in r.url:
            F("UNAUTH_ACCESS", f"{p} served to a logged-out visitor (final url {r.url})")
    r = anon.s.post(anon.base + "/pos/checkout", data={"item_id": "INV301", "quantity": "1"})
    if r.status_code < 400 and "/login" not in r.url:
        F("UNAUTH_WRITE", "POST /pos/checkout accepted from a logged-out visitor")

    # --- A3: brute force lockout ---------------------------------------
    bf = Client(app, "bruteforce")
    bf.csrf("/login")
    outcomes = []
    for i in range(12):
        r = bf.post("/login", {"username": "admin", "password": f"wrong{i}"}, note="bad login")
        outcomes.append([m for _, m in flashes(r.text)][:1])
    locked = any("lock" in str(o).lower() or "too many" in str(o).lower() for o in outcomes)
    print(f"  12 bad logins -> locked out: {locked}")
    if not locked:
        F("NO_LOGIN_LOCKOUT", "12 consecutive failed logins produced no lockout message",
          dict(last=outcomes[-3:]))
    # the real admin must still be able to get in afterwards (or be locked deliberately)
    ok = Client(app, "recheck")
    try:
        ok.login()
        print("  admin can still log in after the burst")
    except RuntimeError:
        print("  admin is locked out after the burst (expected if lockout is on)")

    print(f"  -- {app}: {len(c.findings)} findings")
    return c


if __name__ == "__main__":
    allf = []
    for app in ("iq", "jo"):
        allf += run(app).findings
    json.dump(allf, open(f"{SIM}/../findings_concurrent.json", "w"), indent=2, default=str)
    print(f"\nTOTAL: {len(allf)}")
