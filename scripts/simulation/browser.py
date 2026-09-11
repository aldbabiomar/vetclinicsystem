"""Phase 3 — drive both apps in a real browser: console errors, CSP violations,
broken handlers, dialogs, and the interactive pieces HTTP tests can't see."""
import sys, json, re, time
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from playwright.sync_api import sync_playwright

BASE = {"iq": "http://127.0.0.1:5091", "jo": "http://127.0.0.1:5092"}

PAGES = ["/", "/patients", "/owners", "/visits", "/appointments", "/inpatient",
         "/boarding", "/followups", "/wellness", "/grooming", "/pos", "/pos/history",
         "/refunds", "/cash-register", "/inventory-catalog", "/price-list",
         "/inventory-status", "/ordering-sheet", "/audit-history", "/consignment",
         "/consignment/items", "/consignment/receiving", "/consignment/returns",
         "/consignment/shrinkage", "/consignment/sales", "/distributors",
         "/reports", "/reports/yearly", "/insights", "/retention",
         "/admin/users", "/admin/logs", "/settings"]


def run(app, findings):
    base = BASE[app]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        console, pageerrors, csp, failed = [], [], [], []
        page.on("console", lambda m: console.append((m.type, m.text, page.url))
                if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: pageerrors.append((str(e), page.url)))
        page.on("requestfailed", lambda r: failed.append((r.url, r.failure, page.url)))

        def note(kind, summary, detail=None):
            findings.append(dict(app=app, kind=kind, summary=summary, detail=detail))
            print(f"  [!] {app.upper()} {kind}: {summary}", flush=True)

        # CSP violations are reported to the page, not the console, unless we listen
        page.add_init_script("""
          window.__cspViolations = [];
          document.addEventListener('securitypolicyviolation', function (e) {
            window.__cspViolations.push({
              directive: e.violatedDirective, blocked: e.blockedURI,
              sample: (e.sample || '').slice(0, 120), url: location.pathname });
          });
        """)

        # --- login -----------------------------------------------------
        page.goto(base + "/login", wait_until="networkidle")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "Admin12345!")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")
        if "/login" in page.url:
            note("BROWSER_LOGIN_FAILED", f"could not log in: {page.url}")
            browser.close(); return

        # --- walk every page -------------------------------------------
        for path in PAGES:
            try:
                page.goto(base + path, wait_until="networkidle", timeout=30000)
            except Exception as e:
                note("PAGE_LOAD_ERROR", f"{path}: {str(e)[:120]}")
                continue
            time.sleep(0.15)
            v = page.evaluate("window.__cspViolations || []")
            for x in v:
                csp.append((path, x))
            # an element that should never appear
            if page.locator("text=Internal Server Error").count():
                note("SERVER_ERROR_PAGE", f"{path} rendered an error page")
            # inline handlers are a documented convention violation
            inline = page.evaluate("""() => {
              const out = [];
              document.querySelectorAll('*').forEach(el => {
                for (const a of el.attributes || []) {
                  if (a.name.startsWith('on')) out.push(el.tagName + '[' + a.name + ']');
                }
              });
              return out.slice(0, 20);
            }""")
            if inline:
                note("INLINE_HANDLER", f"{path} has inline on*= handler(s): {inline[:5]} "
                                       f"— CSP nonce does not authorise these, so they do nothing",
                     dict(path=path, handlers=inline))
            page.evaluate("window.__cspViolations = []")

        # --- interactive: POS ------------------------------------------
        page.goto(base + "/pos", wait_until="networkidle")
        search = page.locator('input[type="search"], input[name="q"], #pos-search').first
        if search.count():
            try:
                search.fill("Test")
                page.wait_for_timeout(900)
                results = page.locator(".search-result, .pos-result, [data-item-id]").count()
                if results == 0:
                    note("POS_SEARCH_EMPTY",
                         "typing a known item name into POS search returned no visible results")
            except Exception as e:
                note("POS_SEARCH_ERROR", str(e)[:150])

        # --- interactive: sidebar collapse persists --------------------
        page.goto(base + "/", wait_until="networkidle")
        tog = page.locator(".nav-group-toggle").first
        if tog.count():
            try:
                tog.click()
                page.wait_for_timeout(250)
                collapsed_before = page.locator(".nav-group.collapsed").count()
                page.goto(base + "/patients", wait_until="networkidle")
                collapsed_after = page.locator(".nav-group.collapsed").count()
                if collapsed_before and not collapsed_after:
                    note("SIDEBAR_STATE_LOST",
                         "a collapsed sidebar group re-expands after navigating to another page")
            except Exception as e:
                note("SIDEBAR_ERROR", str(e)[:150])

        # --- interactive: styled confirm dialog on a delete ------------
        page.goto(base + "/price-list", wait_until="networkidle")
        native_dialog = {"fired": False}
        page.on("dialog", lambda d: (native_dialog.__setitem__("fired", True), d.dismiss()))
        delbtn = page.locator("button:has-text('Delete'), a:has-text('Delete')").first
        if delbtn.count():
            try:
                delbtn.click()
                page.wait_for_timeout(600)
                if native_dialog["fired"]:
                    note("NATIVE_DIALOG",
                         "a Delete control used the browser's native confirm() instead of VZDialog")
            except Exception:
                pass

        # --- mobile viewport -------------------------------------------
        mob = ctx.new_page()
        mob.goto(base + "/", wait_until="networkidle")
        mob.set_viewport_size({"width": 375, "height": 812})
        mob.wait_for_timeout(400)
        overflow = mob.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        if overflow and overflow > 4:
            note("MOBILE_OVERFLOW",
                 f"dashboard scrolls horizontally by {overflow}px at 375px wide")
        mob.close()

        # --- roll up console/CSP noise ---------------------------------
        real_errors = [c for c in console if c[0] == "error"]
        if real_errors:
            note("CONSOLE_ERRORS", f"{len(real_errors)} console error(s) across the walk",
                 dict(sample=[list(x) for x in real_errors[:8]]))
        if pageerrors:
            note("UNCAUGHT_JS", f"{len(pageerrors)} uncaught JS exception(s)",
                 dict(sample=[list(x) for x in pageerrors[:8]]))
        if csp:
            note("CSP_VIOLATION", f"{len(csp)} CSP violation(s)",
                 dict(sample=[[p_, x] for p_, x in csp[:8]]))
        bad_failed = [f for f in failed if "favicon" not in f[0]]
        if bad_failed:
            note("REQUEST_FAILED", f"{len(bad_failed)} request(s) failed to load",
                 dict(sample=[list(map(str, x)) for x in bad_failed[:8]]))

        browser.close()


if __name__ == "__main__":
    findings = []
    for app in ("iq", "jo"):
        print(f"\n=== {app.upper()}: browser walk ===", flush=True)
        run(app, findings)
        print(f"  -- {app}: done")
    json.dump(findings, open(f"{SIM}/../findings_browser.json", "w"), indent=2, default=str)
    print(f"\nTOTAL browser findings: {len(findings)}")
