"""Is the POS free-goods bug reachable at REALISTIC IQD prices, via the
discount field rather than a toy unit price?"""
import sys, re, random
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes

app = "iq"
c = Client(app); c.login()

# a realistic retail line: 10,000 IQD, plenty in stock
r = c.post("/audit-history/start")
sid = re.search(r"/session/(\d+)", r.url).group(1)
pg = c.get(f"/audit-history/session/{sid}")
ids = sorted(set(re.findall(r'name="stock_(INV\d+)"', pg.text)))
data = {}
for i in ids:
    data[f"stock_{i}"] = "500"; data[f"received_{i}"] = "0"
c.post(f"/audit-history/session/{sid}/save", data)
c.post(f"/audit-history/session/{sid}/confirm", data)

print(f"{'unit price':>11} {'qty':>4} {'disc%':>6} {'raw':>9} {'stored total':>13} {'change out':>11}  verdict")
for unit, qty, disc in [(10000, 1, 99), (10000, 1, 100), (5000, 1, 98),
                        (1000, 1, 90), (250, 1, 50), (2000, 1, 95),
                        (10000, 1, 0), (10000, 1, 50)]:
    q(app, "UPDATE price_list SET sale_price=%s WHERE id='PL301'", (unit,))
    before = q(app, "select count(*) from sales")[0][0]
    r = c.post("/pos/checkout", {"item_id": "INV301", "quantity": str(qty),
                                 "payment_method": "Cash", "discount_percent": str(disc),
                                 "cash_received": "50000",
                                 "idempotency_key": f"disc-{unit}-{disc}-{random.randint(1,10**9)}"})
    after = q(app, "select count(*) from sales")[0][0]
    if after == before:
        print(f"{unit:>11} {qty:>4} {disc:>6}  (refused: {[m for _,m in flashes(r.text)][:1]})")
        continue
    row = q(app, "select subtotal,discount_percent,total,cash_received,change_given "
                 "from sales order by id desc limit 1")[0]
    sub, d, tot, cash, chg = row
    raw = float(sub) * (1 - float(d) / 100)
    verdict = ("FREE — full cash returned" if float(tot) == 0 and raw > 0
               else ("waived (100% discount, intended)" if float(d) >= 100 else "ok"))
    print(f"{unit:>11} {qty:>4} {disc:>6} {raw:>9.1f} {float(tot):>13.1f} {float(chg):>11.1f}  {verdict}")
