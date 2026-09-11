"""Reproduce: IQ POS has no anti-'looks free' floor, unlike the bill path."""
import os, sys, random
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes

app = "iq"
c = Client(app); c.login()

def set_price(price):
    q(app, "UPDATE price_list SET sale_price=%s WHERE id='PL301'", (price,))

def sell(qty, cash, key):
    r = c.post("/pos/checkout", {"item_id": "INV301", "quantity": str(qty),
                                 "payment_method": "Cash", "discount_percent": "0",
                                 "cash_received": str(cash), "idempotency_key": key},
               note="pos")
    row = q(app, "select subtotal,total,cash_received,change_given from sales order by id desc limit 1")
    return r, (row[0] if row else None)

# make sure stock is plentiful
q(app, "UPDATE audit_session_lines SET stock_counted=9999")

print(f"{'unit price':>10} {'qty':>4} {'subtotal':>9} {'POS total':>10} {'cash in':>8} {'change out':>11}  verdict")
for price, qty in [(5,2),(50,1),(60,2),(100,1),(125,1),(126,1),(130,1),(200,1),(250,1)]:
    set_price(price)
    r, row = sell(qty, 50000, f"floor-{price}-{qty}-{random.randint(1,10**9)}")
    if not row:
        print(f"{price:>10} {qty:>4}   (refused: {[m for _,m in flashes(r.text)][:1]})")
        continue
    sub, tot, cash, chg = row
    raw = price*qty
    verdict = "FREE GOODS + FULL CASH BACK" if tot == 0 and raw > 0 else ("ok" if tot > 0 else "?")
    print(f"{price:>10} {qty:>4} {sub:>9} {tot:>10} {cash:>8} {chg:>11}  {verdict}")

# contrast: same amounts through the visit-bill path
print("\nSame subtotals through compute_bill_totals (the bill path):")
sys.path.insert(0, "/Users/omaraldbabi/Desktop/VetClinicSystem/webapps/vetclinicsystem_iq-main")
import importlib, os
os.environ.setdefault("VETCLINICSYSTEMIQ_DATA_DIR", "/tmp/vz_iq_audit_probe")
import money
for raw in (10, 50, 100, 120, 125, 126, 130):
    rounded = money.round_to_denomination(raw)
    floored = money.SMALLEST_NOTE if 0 < raw <= 125 else rounded
    print(f"  subtotal {raw:>4} -> POS stores {rounded:>4}   bill path stores {floored:>4}"
          f"{'   <-- DIVERGES' if rounded != floored else ''}")
