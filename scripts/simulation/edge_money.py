"""Phase 2a — money, rounding and business-rule edges across every money surface."""
import sys, random, json, datetime
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes
from vzform import pick, inputs

D = datetime.date.today().isoformat()
K = lambda p: f"{p}-{random.randint(1,10**9)}"

def setup(app):
    """A clinic with stock counted and an owner/patient/visit to bill against."""
    c = Client(app); c.login()
    r = c.post("/audit-history/start", note="audit")
    import re
    sid = re.search(r"/session/(\d+)", r.url)
    if sid:
        sid = sid.group(1)
        pg = c.get(f"/audit-history/session/{sid}")
        ids = sorted(set(re.findall(r'name="stock_(INV\d+)"', pg.text)))
        data = {}
        for i in ids:
            data[f"stock_{i}"] = "9999"; data[f"received_{i}"] = "0"
        if ids:
            c.post(f"/audit-history/session/{sid}/save", data)
            c.post(f"/audit-history/session/{sid}/confirm", data)
    return c

def price(app, p):
    q(app, "UPDATE price_list SET sale_price=%s WHERE id='PL301'", (p,))

def last_sale(app):
    r = q(app, "select id,subtotal,total,cash_received,change_given from sales order by id desc limit 1")
    return r[0] if r else None

def run(app):
    c = setup(app)
    F = c.finding
    print(f"\n=== {app.upper()}: money & business-rule edges ===", flush=True)
    unit = 100 if app == "iq" else "0.100"

    # --- E1: POS anti-"looks free" floor (IQ) -------------------------
    price(app, unit)
    before = last_sale(app)
    r = c.post("/pos/checkout", {"item_id": "INV301", "quantity": "1", "payment_method": "Cash",
                                 "discount_percent": "0", "cash_received": "50000" if app=="iq" else "50.000",
                                 "idempotency_key": K("floor")}, note="tiny-value POS sale")
    s = last_sale(app)
    if s and (not before or s[0] != before[0]):
        sid_, sub, tot, cash, chg = s
        if float(sub) > 0 and float(tot) == 0:
            F("MONEY_FREE_GOODS",
              f"POS sale of subtotal {sub} recorded total 0 — goods free; change_given={chg} of cash_received={cash}",
              dict(sale_id=sid_, subtotal=str(sub), total=str(tot), change=str(chg)))

    # --- E2: retail refund rounding to zero ---------------------------
    price(app, 400 if app == "iq" else "0.400")
    r = c.post("/pos/checkout", {"item_id": "INV301", "quantity": "1", "payment_method": "Cash",
                                 "discount_percent": "0", "cash_received": "50000" if app=="iq" else "50.000",
                                 "idempotency_key": K("refund-src")}, note="sale to refund")
    s = last_sale(app)
    if s:
        sale_id = s[0]
        api = c.get(f"/api/sales/{sale_id}/refundable-items")
        try: lines = api.json().get("lines", [])
        except Exception: lines = []
        if lines:
            sii = str(lines[0]["sale_item_id"])
            r = c.post("/refunds/retail", {"sale_id": str(sale_id), "sale_item_id": sii,
                                           "quantity": "1", "reason": "Returned unopened",
                                           "refund_date": D, "refund_method": "Cash", "restock": "on"},
                       note="refund a sub-note-value item")
            ref = q(app, "select id,amount,sale_id from refunds where sale_id=%s order by id desc limit 1", (sale_id,))
            if ref and float(ref[0][1]) == 0:
                F("MONEY_ZERO_REFUND",
                  f"Retail refund of a {s[2]} sale recorded amount 0 — customer returns goods and is paid nothing",
                  dict(sale_id=sale_id, refund=str(ref[0][1]), sale_total=str(s[2])))

    # --- E3: cash received less than total is refused -----------------
    price(app, 1000 if app == "iq" else "10.000")
    r = c.post("/pos/checkout", {"item_id": "INV301", "quantity": "1", "payment_method": "Cash",
                                 "discount_percent": "0", "cash_received": "1" if app=="iq" else "0.001",
                                 "idempotency_key": K("short")}, note="underpayment")
    c.expect_refusal(r, "POS: cash received below total")

    # --- E4: negative / zero / absurd quantities ----------------------
    for qty, label in [("0", "zero"), ("-3", "negative"), ("999999999", "absurd"),
                       ("2.5", "fractional"), ("1e3", "exponent"), ("abc", "text")]:
        r = c.post("/pos/checkout", {"item_id": "INV301", "quantity": qty, "payment_method": "Cash",
                                     "discount_percent": "0", "idempotency_key": K(f"qty{qty}")},
                   note=f"POS qty {label}")
        if r.status_code >= 500:
            F("HTTP_5XX_ON_BAD_INPUT", f"POS quantity {label!r} -> {r.status_code}")
        else:
            s2 = last_sale(app)
            if s2 and float(s2[1]) < 0:
                F("MONEY_NEGATIVE_SALE", f"POS quantity {label!r} produced a negative subtotal {s2[1]}")

    # --- E5: discount above 100 / negative ----------------------------
    for dp, label in [("-10", "negative"), ("150", "over 100"), ("100", "full waiver"),
                      ("abc", "text"), ("NaN", "NaN"), ("Infinity", "infinity")]:
        r = c.post("/pos/checkout", {"item_id": "INV301", "quantity": "1", "payment_method": "Cash",
                                     "discount_percent": dp, "cash_received": "50000" if app=="iq" else "50.000",
                                     "idempotency_key": K(f"disc{label}")}, note=f"POS discount {label}")
        if r.status_code >= 500:
            F("HTTP_5XX_ON_BAD_INPUT", f"POS discount {label!r} -> {r.status_code}")
        else:
            s3 = last_sale(app)
            if s3 and float(s3[2]) < 0:
                F("MONEY_NEGATIVE_TOTAL", f"POS discount {label!r} produced total {s3[2]}")

    # --- E6: double-submit (idempotency) ------------------------------
    price(app, 1000 if app == "iq" else "10.000")
    key = K("dbl")
    n0 = q(app, "select count(*) from sales")[0][0]
    r1 = c.post("/pos/checkout", {"item_id": "INV301", "quantity": "1", "payment_method": "Cash",
                                  "discount_percent": "0", "cash_received": "50000" if app=="iq" else "50.000",
                                  "idempotency_key": key}, note="checkout")
    r2 = c.post("/pos/checkout", {"item_id": "INV301", "quantity": "1", "payment_method": "Cash",
                                  "discount_percent": "0", "cash_received": "50000" if app=="iq" else "50.000",
                                  "idempotency_key": key}, note="same submit again (double-click)")
    n1 = q(app, "select count(*) from sales")[0][0]
    if n1 - n0 != 1:
        F("IDEMPOTENCY", f"double-submit with one key created {n1-n0} sales (expected 1)")

    # --- E7: overselling stock ----------------------------------------
    q(app, "UPDATE audit_session_lines SET stock_counted=3")
    r = c.post("/pos/checkout", {"item_id": "INV301", "quantity": "10", "payment_method": "Cash",
                                 "discount_percent": "0", "cash_received": "50000" if app=="iq" else "50.000",
                                 "idempotency_key": K("oversell")}, note="sell more than in stock")
    c.expect_refusal(r, "POS: oversell blocked")
    st = q(app, "select stock_counted from audit_session_lines limit 1")
    q(app, "UPDATE audit_session_lines SET stock_counted=9999")

    # --- E8: cash payout larger than the drawer -----------------------
    r = c.post("/cash-register/payout", {"day": D, "amount": "999999" if app=="iq" else "999999.000",
                                         "reason": "Test overdraw"}, note="payout over drawer")
    c.expect_refusal(r, "cash payout beyond drawer")
    # negative payout
    r = c.post("/cash-register/payout", {"day": D, "amount": "-500", "reason": "negative"},
               note="negative payout")
    c.expect_refusal(r, "negative payout")
    # negative counted cash
    r = c.post("/cash-register/audit", {"day": D, "counted_cash": "-100", "notes": "neg"},
               note="negative cash count")
    c.expect_refusal(r, "negative counted cash")

    print(f"  -- {app}: {len(c.findings)} findings, {len(c.events)} requests")
    return c

if __name__ == "__main__":
    allf = []
    for app in ("iq", "jo"):
        allf += run(app).findings
    json.dump(allf, open(f"{SIM}/../findings_edge_money.json", "w"), indent=2, default=str)
    print(f"\nTOTAL: {len(allf)}")
