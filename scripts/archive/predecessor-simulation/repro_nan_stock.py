"""Prove the consequence: a NaN stock count, confirmed, defeats the POS oversell guard."""
import sys, re, random
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes

ITEM = "INV301"          # the seeded Retail item that has a sale price

for app in ("iq", "jo"):
    c = Client(app); c.login()
    print(f"\n=== {app.upper()} ===")
    q(app, "UPDATE price_list SET sale_price=%s WHERE id='PL301'", (1000 if app == "iq" else "10.000",))

    def new_audit(counts):
        r = c.post("/audit-history/start")
        sid = re.search(r"/session/(\d+)", r.url).group(1)
        pg = c.get(f"/audit-history/session/{sid}")
        ids = sorted(set(re.findall(r'name="stock_(INV\d+)"', pg.text)))
        data = {}
        for i in ids:
            data[f"stock_{i}"] = counts if i == ITEM else "0"
            data[f"received_{i}"] = "0"
        c.post(f"/audit-history/session/{sid}/save", data)
        r = c.post(f"/audit-history/session/{sid}/confirm", data)
        return sid, [m for _, m in flashes(r.text)]

    def try_sell(qty, tag):
        n0 = q(app, "select count(*) from sales")[0][0]
        r = c.post("/pos/checkout", {"item_id": ITEM, "quantity": str(qty),
                                     "payment_method": "Cash", "discount_percent": "0",
                                     "cash_received": "9999999" if app == "iq" else "999999.000",
                                     "idempotency_key": f"{tag}-{random.randint(1,10**9)}"})
        n1 = q(app, "select count(*) from sales")[0][0]
        return (n1 > n0), [m for _, m in flashes(r.text)]

    sid, msgs = new_audit("5")
    sold, m = try_sell(500, "sane")
    print(f"  counted 5   -> sell 500: {'SOLD' if sold else 'blocked'}   {m[:1]}")

    sid, msgs = new_audit("nan")
    stored = q(app, "select stock_counted,status from audit_session_lines l "
                    "join audit_sessions s on s.id=l.session_id "
                    "where l.session_id=%s and l.item_id=%s", (sid, ITEM))
    print(f"  counted NaN -> stored {stored[0][0]!r}, session {stored[0][1]!r}, confirm said {msgs[:1]}")

    sold, m = try_sell(500, "nan")
    print(f"  counted NaN -> sell 500: {'SOLD — OVERSELL GUARD DEFEATED' if sold else 'blocked'}   {m[:1]}")
    if sold:
        row = q(app, "select id,subtotal,total from sales order by id desc limit 1")[0]
        print(f"     sale id={row[0]} subtotal={row[1]} total={row[2]}  (nothing was in stock)")
