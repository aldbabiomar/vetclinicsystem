"""Phase 2b — refund rounding boundary + the bill-path money surfaces."""
import sys, re, random, json, datetime
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes
from vzform import pick, inputs

D = datetime.date.today().isoformat()
K = lambda p: f"{p}-{random.randint(1,10**9)}"

def setup(app):
    c = Client(app); c.login()
    r = c.post("/audit-history/start")
    sid = re.search(r"/session/(\d+)", r.url)
    if sid:
        sid = sid.group(1)
        pg = c.get(f"/audit-history/session/{sid}")
        ids = sorted(set(re.findall(r'name="stock_(INV\d+)"', pg.text)))
        data = {f"stock_{i}": "9999" for i in ids}
        data.update({f"received_{i}": "0" for i in ids})
        if ids:
            c.post(f"/audit-history/session/{sid}/save", data)
            c.post(f"/audit-history/session/{sid}/confirm", data)
    return c

def price(app, p): q(app, "UPDATE price_list SET sale_price=%s WHERE id='PL301'", (p,))
def last_sale(app):
    r = q(app, "select id,subtotal,total from sales order by id desc limit 1"); return r[0] if r else None

def run(app):
    c = setup(app); F = c.finding
    print(f"\n=== {app.upper()}: refund rounding + bill surfaces ===", flush=True)
    iq = app == "iq"

    # --- R1: refund of a line worth less than one note -----------------
    for unit in ([240, 200, 130] if iq else ["0.240"]):
        price(app, unit)
        c.post("/pos/checkout", {"item_id": "INV301", "quantity": "1", "payment_method": "Cash",
                                 "discount_percent": "0", "cash_received": "50000" if iq else "50.000",
                                 "idempotency_key": K("rf")}, note=f"sale @{unit}")
        s = last_sale(app)
        if not s: continue
        sale_id, sub, tot = s
        api = c.get(f"/api/sales/{sale_id}/refundable-items")
        try: lines = api.json().get("lines", [])
        except Exception: lines = []
        if not lines: continue
        r = c.post("/refunds/retail", {"sale_id": str(sale_id), "sale_item_id": str(lines[0]["sale_item_id"]),
                                       "quantity": "1", "reason": "Returned unopened", "refund_date": D,
                                       "refund_method": "Cash", "restock": "on"},
                   note=f"refund @{unit}")
        ref = q(app, "select id,amount from refunds where sale_id=%s order by id desc limit 1", (sale_id,))
        msgs = [m for _, m in flashes(r.text)]
        if ref and float(ref[0][1]) == 0:
            F("MONEY_ZERO_REFUND",
              f"unit {unit}: sale collected {tot} but the refund was recorded as 0 — "
              f"goods taken back, customer paid nothing",
              dict(sale_total=str(tot), refund_amount=str(ref[0][1]), flashes=msgs))
        elif not ref:
            print(f"    unit {unit}: refund refused -> {msgs[:1]}")
        else:
            print(f"    unit {unit}: sale total {tot}, refund {ref[0][1]}")

    # --- R2: a visit bill, its payment ceiling and discount cap --------
    ow = c.post("/owners/new", {"name": "Edge Tester", "phone": ("0770" if iq else "079") + str(random.randint(10**6,10**7-1)),
                                "address": "x"}, note="owner")
    r = c.post("/visits/new/new-patient", {
        "owner_name": "Edge Tester2", "owner_phone": ("0770" if iq else "079") + str(random.randint(10**6,10**7-1)),
        "animal_name": "Edge", "species": "Dog", "date": D, "doctor": "Dr. X",
        "complaint": "edge", "microchip": str(random.randint(10**14, 10**15-1)),
    }, note="visit")
    vid = re.search(r"/visits/(V\d+)", r.url)
    vid = vid.group(1) if vid else None
    if vid:
        price(app, 1000 if iq else "10.000")
        c.post(f"/visits/{vid}/billing", {"billing_type": "Automatic", "price_id": "PL301",
                                          "qty_PL301": "1", "date_billed": D}, note="bill")
        bal = q(app, "select total,discount_percent from billing where visit_id=%s", (vid,))
        # overpayment must be refused
        r = c.post(f"/visits/{vid}/payment", {"amount": "999999" if iq else "999999.000",
                                              "method": "Cash", "date": D}, note="overpay")
        c.expect_refusal(r, "visit payment above balance")
        # negative payment
        r = c.post(f"/visits/{vid}/payment", {"amount": "-500", "method": "Cash", "date": D},
                   note="negative payment")
        c.expect_refusal(r, "negative visit payment")
        # discount over 100 and negative
        for dp in ("150", "-5", "abc", "NaN"):
            r = c.post(f"/visits/{vid}/discount", {"discount_percent": dp}, note=f"discount {dp}")
            c.expect_refusal(r, f"visit discount {dp}")
        row = q(app, "select discount_percent from billing where visit_id=%s", (vid,))
        if row and row[0][0] is not None and (float(row[0][0]) > 100 or float(row[0][0]) < 0):
            F("DISCOUNT_OUT_OF_RANGE", f"visit discount stored as {row[0][0]}")
        # cleanup write-off beyond the documented cap
        r = c.post(f"/visits/{vid}/payment", {"amount": "0", "cleanup_amount": "999999" if iq else "999999.000",
                                              "method": "Cash", "date": D}, note="cleanup over cap")
        c.expect_refusal(r, "cleanup above cap")
        # pay exactly the balance, then try to pay again
        tot = q(app, "select total from billing where visit_id=%s", (vid,))
        amt = str(tot[0][0] if tot else 0)
        c.post(f"/visits/{vid}/payment", {"amount": amt, "method": "Cash", "date": D}, note="pay in full")
        r = c.post(f"/visits/{vid}/payment", {"amount": amt, "method": "Cash", "date": D},
                   note="pay again after settled")
        c.expect_refusal(r, "second full payment on a settled bill")
        paid = q(app, "select coalesce(sum(amount),0) from payments where visit_id=%s", (vid,))
        billed = q(app, "select total from billing where visit_id=%s", (vid,))
        if paid and billed and float(paid[0][0]) > float(billed[0][0]) + 0.51:
            F("OVERPAYMENT_STORED", f"visit {vid}: paid {paid[0][0]} against a bill of {billed[0][0]}")

    print(f"  -- {app}: {len(c.findings)} findings")
    return c

if __name__ == "__main__":
    allf = []
    for app in ("iq", "jo"):
        allf += run(app).findings
    json.dump(allf, open(f"{SIM}/../findings_edge_money2.json","w"), indent=2, default=str)
    print(f"\nTOTAL: {len(allf)}")
