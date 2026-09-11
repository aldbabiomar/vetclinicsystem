"""Second route into the free-goods bug: a role with a high discount cap
(a clinic owner / manager) reaches total=0 at any unit price."""
import sys, re, random
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes

app = "iq"
a = Client(app); a.login()

# a manager role allowed to discount up to 95%
rolename = f"Clinic Owner {random.randint(100,999)}"
perms = [p[0] for p in q(app, "select id from permissions")]
a.post("/admin/roles/new", {"name": rolename, "description": "Full discount authority",
                            "discount_cap": "95", "is_vet_role": "N", "permissions": perms},
       note="manager role")
rid = q(app, "select id from roles where name=%s", (rolename,))[0][0]
uname = f"owner{random.randint(1000,9999)}"
a.post("/admin/users/new", {"username": uname, "full_name": "Clinic Owner",
                            "password": "Str0ngPass!23", "role_id": rid, "capmode": "role"},
       note="manager user")

u = Client(app, uname); u.login(uname, "Str0ngPass!23")
NEW = "Owner!Pass99"
u.get("/change-password")
u.post("/change-password", {"current_password": "Str0ngPass!23",
                            "new_password": NEW, "confirm_password": NEW})

# stock it
r = u.post("/audit-history/start")
sid = re.search(r"/session/(\d+)", r.url).group(1)
pg = u.get(f"/audit-history/session/{sid}")
ids = sorted(set(re.findall(r'name="stock_(INV\d+)"', pg.text)))
data = {}
for i in ids:
    data[f"stock_{i}"] = "500"; data[f"received_{i}"] = "0"
u.post(f"/audit-history/session/{sid}/save", data)
u.post(f"/audit-history/session/{sid}/confirm", data)

print(f"role discount cap = 95%")
print(f"{'unit price':>11} {'disc%':>6} {'raw':>10} {'stored total':>13} {'cash in':>9} {'change out':>11}  verdict")
for unit, disc in [(10000, 95), (5000, 95), (2000, 94), (100000, 95), (250000, 95)]:
    q(app, "UPDATE price_list SET sale_price=%s WHERE id='PL301'", (unit,))
    before = q(app, "select count(*) from sales")[0][0]
    r = u.post("/pos/checkout", {"item_id": "INV301", "quantity": "1",
                                 "payment_method": "Cash", "discount_percent": str(disc),
                                 "cash_received": "250000",
                                 "idempotency_key": f"role-{unit}-{disc}-{random.randint(1,10**9)}"})
    if q(app, "select count(*) from sales")[0][0] == before:
        print(f"{unit:>11} {disc:>6}   refused: {[m for _,m in flashes(r.text)][:1]}")
        continue
    sub, d, tot, cash, chg = q(app, "select subtotal,discount_percent,total,cash_received,"
                                    "change_given from sales order by id desc limit 1")[0]
    raw = float(sub) * (1 - float(d) / 100)
    verdict = "FREE — full cash returned" if float(tot) == 0 and raw > 0 else "ok"
    print(f"{unit:>11} {disc:>6} {raw:>10.1f} {float(tot):>13.1f} {float(cash):>9.0f} {float(chg):>11.0f}  {verdict}")
