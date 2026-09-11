"""IQ's bill-mutating routes do not all take the visit/case row lock, so the
two guards that protect "a discount must never apply to a non-discountable
item" validate against snapshots the other has already invalidated.

visit_billing_save() takes `SELECT ... FOR UPDATE` and its comment says the
lock is there "so a concurrent discount save on the same visit serialises
behind this one". A lock only serialises if BOTH sides take it;
visit_discount_save() never does. JO takes it on all four bill-mutating
routes and documents why on each.

The bad end state this produces: a bill carrying a discount AND a line marked
non-discountable — the exact combination both guards exist to prevent.
"""
import os, sys, re, random, threading, datetime
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes

D = datetime.date.today().isoformat()
PH = lambda app: ("0770" if app == "iq" else "079") + str(random.randint(10**6, 10**7 - 1))
TRIALS = 25


def setup_items(app):
    """One discountable item and one that must never be discounted."""
    ok_id = f"PLOK{random.randint(1000,9999)}"
    no_id = f"PLNO{random.randint(1000,9999)}"
    price = 10000 if app == "iq" else "10.000"
    for pid, can in ((ok_id, True), (no_id, False)):
        q(app, "INSERT INTO price_list (id,name,category,sale_price,active,can_discount) "
               "VALUES (%s,%s,'Service',%s,true,%s)", (pid, f"Race {pid}", price, can))
    return ok_id, no_id


def new_visit(c, app):
    r = c.post("/visits/new/new-patient", {
        "owner_name": f"Race {random.randint(1,10**6)}", "owner_phone": PH(app),
        "animal_name": "Racer", "species": "Dog", "date": D, "doctor": "Dr. A",
        "complaint": "x", "microchip": str(random.randint(10**14, 10**15 - 1))})
    m = re.search(r"/visits/(V\d+)", r.url)
    return m.group(1) if m else None


def run(app):
    print(f"\n=== {app.upper()} ===")
    admin = Client(app); admin.login()
    ok_id, no_id = setup_items(app)
    a = Client(app, "A"); a.login()
    b = Client(app, "B"); b.login()

    bad = 0
    for trial in range(TRIALS):
        vid = new_visit(admin, app)
        if not vid:
            continue
        # a bill containing ONLY the discountable item
        admin.post(f"/visits/{vid}/billing", {
            "billing_type": "Automatic", "price_id": ok_id, f"qty_{ok_id}": "1",
            "date_billed": D})

        def apply_discount():
            a.post(f"/visits/{vid}/discount", {"discount_percent": "20"})

        def add_non_discountable():
            # re-saves the cart WITH the non-discountable line added
            b.post(f"/visits/{vid}/billing", {
                "billing_type": "Automatic",
                "price_id": [ok_id, no_id],
                f"qty_{ok_id}": "1", f"qty_{no_id}": "1", "date_billed": D})

        t1 = threading.Thread(target=apply_discount)
        t2 = threading.Thread(target=add_non_discountable)
        t1.start(); t2.start(); t1.join(); t2.join()

        disc = q(app, "SELECT discount_percent FROM billing WHERE visit_id=%s", (vid,))
        lines = q(app, "SELECT price_id FROM visit_billing_lines WHERE visit_id=%s", (vid,))
        has_no = any(r[0] == no_id for r in (lines or []))
        pct = float(disc[0][0]) if disc and disc[0][0] is not None else 0.0
        if pct > 0 and has_no:
            bad += 1
            if bad == 1:
                print(f"  trial {trial}: visit {vid} ended with a {pct:.0f}% discount AND "
                      f"the non-discountable line {no_id} on the same bill")

    print(f"  {bad}/{TRIALS} trials produced a discounted bill containing a "
          f"non-discountable item")
    for pid in (ok_id, no_id):
        q(app, "DELETE FROM visit_billing_lines WHERE price_id=%s", (pid,))
        q(app, "DELETE FROM price_list WHERE id=%s", (pid,))
    return bad


if __name__ == "__main__":
    results = {app: run(app) for app in ("iq", "jo")}
    print(f"\n{'='*60}")
    for app, bad in results.items():
        verdict = "RACE REPRODUCED" if bad else "held"
        print(f"  {app.upper()}: {bad}/{TRIALS}  {verdict}")
