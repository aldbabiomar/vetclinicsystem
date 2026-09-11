"""Phase 2c — hostile/rare inputs against every GET surface:
bad ids, wildcards, pagination bounds, traversal, injection-shaped strings."""
import sys, json, urllib.parse
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, flashes

ID_ROUTES = [
    "/owners/{}", "/owners/{}/edit", "/patients/{}", "/patients/{}/edit",
    "/patients/{}/history", "/patients/{}/export/billing", "/patients/{}/export/file",
    "/visits/{}", "/visits/{}/edit", "/visits/{}/export",
    "/inpatient/{}", "/inpatient/{}/export",
    "/boarding/{}/export", "/distributors/{}", "/distributors/{}/export.pdf",
    "/consignment/settlements/{}", "/pos/receipt/{}", "/pos/history/{}/export",
    "/api/sales/{}/refundable-items", "/audit-history/session/{}",
    "/inventory-catalog/{}/barcode-label", "/inventory-catalog/{}/barcode/status",
]
BAD_IDS = ["0", "-1", "999999999", "99999999999999999999", "abc", "' OR '1'='1",
           "%27", "../../etc/passwd", "<script>x</script>", "V001'", "null", "NaN",
           " x", "P" * 300]

LIST_ROUTES = [
    "/owners?q={}", "/patients?q={}", "/visits?q={}", "/visits?date={}",
    "/distributors?q={}", "/inventory-status?q={}", "/inventory-status?filter={}",
    "/price-list?q={}", "/pos/history?date={}", "/refunds?date={}",
    "/cash-register?date={}", "/admin/logs?date={}", "/api/patients/search?q={}",
    "/api/inventory/lookup?q={}", "/api/inventory/lookup?barcode={}",
    "/api/price-list/lookup?q={}", "/api/price-list/lookup?category={}",
    "/appointments?day={}", "/appointments?week={}", "/consignment/sales?date_from={}",
    "/consignment/sales?distributor_id={}", "/followups?all={}", "/patients?sort={}",
    "/patients?dir={}", "/jobs/status?job_id={}", "/settings/job-status?job_id={}",
    "/api/browse-folder?path={}",
]
NASTY = ["%", "_", "%%", "''", "' OR 1=1--", "\\", "<script>alert(1)</script>",
         "2026-13-45", "not-a-date", "0000-00-00", "9999-99-99", "1e999",
         "../../../../etc/passwd", "‮", "\U0001F63A" * 20, "A" * 500,
         "-1", "NaN", "", " ", "\t\n", "۱۲۳"]

PAGE_VALUES = ["0", "-1", "1e9", "abc", "99999999", "100001", "2.5", "", "%00"]
PAGED = ["/owners", "/patients", "/visits", "/distributors", "/price-list",
         "/inventory-catalog", "/inventory-status", "/audit-history", "/pos/history",
         "/consignment/items", "/admin/logs", "/followups", "/boarding", "/inpatient"]


def run(app):
    c = Client(app); c.login(); F = c.finding
    print(f"\n=== {app.upper()}: hostile-input sweep ===", flush=True)
    n = 0
    for tpl in ID_ROUTES:
        for bad in BAD_IDS:
            r = c.get(tpl.format(urllib.parse.quote(bad, safe="")), note="bad id"); n += 1
            if r.status_code >= 500:
                F("HTTP_5XX_BAD_ID", f"GET {tpl} with id={bad!r} -> {r.status_code}")
    for tpl in LIST_ROUTES:
        for bad in NASTY:
            r = c.get(tpl.format(urllib.parse.quote(bad, safe="")), note="nasty query"); n += 1
            if r.status_code >= 500:
                F("HTTP_5XX_QUERY", f"GET {tpl} with value={bad!r} -> {r.status_code}")
    for base in PAGED:
        for pv in PAGE_VALUES:
            r = c.get(f"{base}?page={urllib.parse.quote(pv)}", note="page bound"); n += 1
            if r.status_code >= 500:
                F("HTTP_5XX_PAGE", f"GET {base}?page={pv!r} -> {r.status_code}")
    print(f"  -- {app}: {n} probes, {len(c.findings)} findings")
    return c


if __name__ == "__main__":
    allf = []
    for app in ("iq", "jo"):
        allf += run(app).findings
    json.dump(allf, open(f"{SIM}/../findings_sweep.json", "w"), indent=2, default=str)
    print(f"\nTOTAL: {len(allf)}")
