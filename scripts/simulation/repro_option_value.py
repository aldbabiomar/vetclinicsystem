# -*- coding: utf-8 -*-
"""An <option> with no value= submits its TEXT. Translate the text and the
form starts posting Arabic into a column the rest of the app compares against
English constants.

Proves it end to end: render the payment form in Arabic, submit exactly what a
browser would submit, then read the stored row back.
"""
import sys, re
sys.path.insert(0, "/Users/omaraldbabi/Desktop/VetClinicSystem/scripts/simulation")
import vzform
from vzsim import Client, q


def run(app, visit_id):
    c = Client(app); c.login()
    c.post("/set-language/ar", {})
    page = c.s.get(f"{c.base}/visits/{visit_id}").text

    submitted = vzform.pick(page, "method")
    print(f"[{app}] browser would submit method = {submitted!r}")

    tok = re.search(r'name="csrf_token" value="([^"]+)"', page)
    c.post(f"/visits/{visit_id}/payment", {
        "csrf_token": tok.group(1), "amount": "250",
        "method": submitted, "date": "2026-09-11",
    })
    stored = q(app, "select method from payments "
                    "where visit_id=%s order by id desc limit 1" % f"'{visit_id}'")
    print(f"[{app}] STORED in payments.method = {stored}")
    c.post("/set-language/en", {})
    english = q(app, "select count(*) from payments where visit_id='%s' "
                     "and method in ('Cash','Card','Transfer')" % visit_id)
    total = q(app, "select count(*) from payments where visit_id='%s'" % visit_id)
    print(f"[{app}] rows the app can recognise: {english[0][0]} of {total[0][0]}")


if __name__ == "__main__":
    run("iq", "V017")
