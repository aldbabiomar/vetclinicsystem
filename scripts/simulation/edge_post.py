"""Phase 2d — hostile values through POST forms: NaN/inf, unicode, huge text,
stale writes, and the numeric fields that bypass parse_money()."""
import sys, re, json, random, datetime
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes
from vzform import inputs

D = datetime.date.today().isoformat()
PH = lambda app: ("0770" if app == "iq" else "079") + str(random.randint(10**6, 10**7 - 1))


def fresh_audit(c, app):
    r = c.post("/audit-history/start", note="start audit")
    m = re.search(r"/session/(\d+)", r.url)
    return m.group(1) if m else None


def run(app):
    c = Client(app); c.login(); F = c.finding
    print(f"\n=== {app.upper()}: POST-side hostile values ===", flush=True)

    # --- A: stock counts bypass parse_money()'s NaN/inf guard? ---------
    sid = fresh_audit(c, app)
    if sid:
        pg = c.get(f"/audit-history/session/{sid}")
        ids = sorted(set(re.findall(r'name="stock_(INV\d+)"', pg.text)))
        if ids:
            iid = ids[0]
            for val, label in [("nan", "NaN"), ("inf", "Infinity"), ("-inf", "-Infinity"),
                               ("-5", "negative"), ("1e309", "overflow"), ("1e30", "huge")]:
                r = c.post(f"/audit-history/session/{sid}/save",
                           {f"stock_{iid}": val, f"received_{iid}": "0"},
                           note=f"audit count {label}")
                row = q(app, "select stock_counted from audit_session_lines "
                             "where session_id=%s and item_id=%s", (sid, iid))
                stored = row[0][0] if row else None
                s = str(stored)
                if r.status_code >= 500:
                    F("HTTP_5XX_ON_BAD_INPUT", f"audit stock count {label!r} -> {r.status_code}")
                elif stored is not None and (s.lower().find("nan") >= 0 or s.lower().find("infinity") >= 0):
                    F("NONFINITE_STORED",
                      f"audit stock count accepted {label!r} and stored {s!r} — "
                      f"every later stock comparison against this silently evaluates False",
                      dict(item=iid, stored=s))
                elif stored is not None and float(s) < 0 and label == "negative":
                    F("NEGATIVE_STOCK_STORED",
                      f"audit stock count accepted a negative count and stored {s!r}",
                      dict(item=iid, stored=s))

    # --- B: unicode / long / markup in names, and how they come back ----
    marker = "<script>alert('xss')</script>"
    cases = [
        ("Arabic", "أحمد الراشد"),
        ("RTL+LTR", "محمد Ali 123"),
        ("emoji", "Simba \U0001F408\U0001F415"),
        ("markup", marker),
        ("quotes", "O'Brien \"Paddy\" \\ test"),
        ("long", "A" * 600),
        ("zerowidth", "Ah​med"),
        ("newlines", "Line1\nLine2\rLine3"),
    ]
    for label, name in cases:
        r = c.post("/owners/new", {"name": name, "phone": PH(app), "address": "Test",
                                   "notes": "edge"}, note=f"owner name {label}")
        if r.status_code >= 500:
            F("HTTP_5XX_ON_BAD_INPUT", f"owner name {label!r} -> {r.status_code}")
            continue
        if label == "markup":
            lst = c.get("/owners?q=" + "script", note="search markup owner")
            if marker in lst.text:
                F("XSS_UNESCAPED", "owner name containing a <script> tag is rendered unescaped "
                                   "in the owners list")

    # --- C: numbers that are not numbers, into money fields ------------
    for field_route, payload_key, extra in [
        ("/price-list/new", "sale_price", {"name": "Edge", "category": "Retail"}),
        ("/inventory-catalog/new", "cost_price", {"name": "Edge", "category": "Retail",
                                                  "unit": "Each"}),
    ]:
        for val, label in [("nan", "NaN"), ("inf", "inf"), ("1e400", "overflow"),
                           ("-1", "negative"), ("1,000", "thousands comma"),
                           ("١٠٠", "arabic-indic digits"), ("0x10", "hex"),
                           ("  5  ", "padded")]:
            body = dict(extra); body[payload_key] = val
            body["name"] = f"Edge {label} {random.randint(1,10**6)}"
            r = c.post(field_route, body, note=f"{field_route} {payload_key}={label}")
            if r.status_code >= 500:
                F("HTTP_5XX_ON_BAD_INPUT", f"{field_route} {payload_key}={label!r} -> {r.status_code}")
    bad = q(app, "select id,name,sale_price from price_list where sale_price::text ~* 'nan|inf'")
    if bad:
        F("NONFINITE_STORED", f"price_list rows stored a non-finite sale_price: {bad}")
    bad = q(app, "select id,name,cost_price from inventory_list where cost_price::text ~* 'nan|inf'")
    if bad:
        F("NONFINITE_STORED", f"inventory_list rows stored a non-finite cost_price: {bad}")

    # --- D: stale write (two staff editing the same visit) --------------
    r = c.post("/visits/new/new-patient", {
        "owner_name": "Stale Test", "owner_phone": PH(app), "animal_name": "Stale",
        "species": "Dog", "date": D, "doctor": "Dr. A", "complaint": "x",
        "microchip": str(random.randint(10**14, 10**15 - 1)),
    }, note="visit for stale test")
    vid = re.search(r"/visits/(V\d+)", r.url)
    if vid:
        vid = vid.group(1)
        f1 = c.get(f"/visits/{vid}/edit", note="staff A opens")
        stamp = inputs(f1.text).get("expected_updated_at", "")
        base = {"date": D, "doctor": "Dr. A", "visit_type": "Outpatient",
                "complaint": "x", "case_status": "Ongoing"}
        # staff B saves first
        b = dict(base); b["expected_updated_at"] = stamp; b["exam"] = "B was here"
        c.post(f"/visits/{vid}/edit", b, note="staff B saves")
        # staff A saves with the now-stale stamp
        a = dict(base); a["expected_updated_at"] = stamp; a["exam"] = "A overwrote B"
        r = c.post(f"/visits/{vid}/edit", a, note="staff A saves stale")
        msgs = [m for _, m in flashes(r.text)]
        row = q(app, "select exam from visits where id=%s", (vid,))
        cur = row[0][0] if row else None
        if cur == "A overwrote B" and not any("chang" in m.lower() or "reload" in m.lower()
                                              or "someone" in m.lower() for m in msgs):
            F("LOST_UPDATE",
              "a second save with a stale expected_updated_at silently overwrote the "
              "other user's edit with no conflict warning", dict(stored=cur, flashes=msgs))

    print(f"  -- {app}: {len(c.findings)} findings, {len(c.events)} requests")
    return c


if __name__ == "__main__":
    allf = []
    for app in ("iq", "jo"):
        allf += run(app).findings
    json.dump(allf, open(f"{SIM}/../findings_post.json", "w"), indent=2, default=str)
    print(f"\nTOTAL: {len(allf)}")
