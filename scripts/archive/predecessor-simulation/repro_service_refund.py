"""Service refunds use round_to_denomination(amount) — does a small service
refund also round to zero? Control included."""
import sys, re, random, datetime
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes

D = datetime.date.today().isoformat()
PH = lambda app: ("0770" if app == "iq" else "079") + str(random.randint(10**6, 10**7 - 1))

for app in ("iq", "jo"):
    c = Client(app); c.login()
    print(f"\n=== {app.upper()} ===")
    # a visit billed and paid, so there is something to refund
    q(app, "UPDATE price_list SET sale_price=%s WHERE id='PL301'", (10000 if app == "iq" else "100.000",))
    r = c.post("/visits/new/new-patient", {
        "owner_name": f"Refund Test {random.randint(1,10**6)}", "owner_phone": PH(app),
        "animal_name": "Reffy", "species": "Cat", "date": D, "doctor": "Dr. A",
        "complaint": "x", "microchip": str(random.randint(10**14, 10**15 - 1))})
    vid = re.search(r"/visits/(V\d+)", r.url).group(1)
    c.post(f"/visits/{vid}/billing", {"billing_type": "Automatic", "price_id": "PL301",
                                      "qty_PL301": "1", "date_billed": D})
    total = q(app, "select total from billing where visit_id=%s", (vid,))[0][0]
    c.post(f"/visits/{vid}/payment", {"amount": str(total), "method": "Cash", "date": D})
    paid = q(app, "select coalesce(sum(amount),0) from payments where visit_id=%s", (vid,))[0][0]
    print(f"  billed {total}, paid {paid}")

    for amt, tag in ([("240", "small service refund (< one note)"),
                      ("5000", "control: large service refund")] if app == "iq"
                     else [("0.240", "small service refund"), ("50.000", "control: large refund")]):
        n0 = q(app, "select count(*) from refunds where visit_id=%s", (vid,))[0][0]
        r = c.post("/refunds/service", {"visit_id": vid, "amount": amt,
                                        "reason": "Service not performed", "refund_date": D,
                                        "refund_method": "Cash"})
        rows = q(app, "select id,amount from refunds where visit_id=%s order by id desc limit 1", (vid,))
        n1 = q(app, "select count(*) from refunds where visit_id=%s", (vid,))[0][0]
        msgs = [m for _, m in flashes(r.text)][:1]
        if n1 == n0:
            print(f"  requested {amt:>8}  -> refused {msgs}")
        else:
            stored = rows[0][1]
            flag = "  <<< recorded as ZERO" if float(stored) == 0 else ""
            print(f"  requested {amt:>8}  -> stored refund {stored}{flag}   {msgs}")
