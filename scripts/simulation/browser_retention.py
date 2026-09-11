"""What happens on /retention, /insights and /consignment in a real browser —
these are the job-polling 'progress shell' pages."""
import sys, time
from playwright.sync_api import sync_playwright

BASE = {"iq": "http://127.0.0.1:5091", "jo": "http://127.0.0.1:5092"}

for app in ("iq", "jo"):
    base = BASE[app]
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        errors, failed = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed", lambda r: failed.append((r.url, r.failure)))
        page.goto(base + "/login")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "Admin12345!")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")
        print(f"\n=== {app.upper()} ===")
        for path in ("/retention", "/insights", "/consignment"):
            errors.clear(); failed.clear()
            try:
                page.goto(base + path, wait_until="domcontentloaded", timeout=20000)
            except Exception as e:
                print(f"  {path}: goto raised {str(e)[:80]}")
            # the shell polls a background job; give it time to finish
            for _ in range(30):
                time.sleep(0.5)
                txt = page.inner_text("body")[:200].replace("\n", " ")
                if "loading" not in txt.lower() and "working" not in txt.lower():
                    break
            title = page.title()
            body = page.inner_text("body")
            has_content = len(body.strip()) > 200
            print(f"  {path:14s} url={page.url.replace(base,'')!r:28s} title={title[:28]!r} "
                  f"body={len(body)}b content={'yes' if has_content else 'NO'}")
            if errors:
                print(f"      JS errors: {errors[:2]}")
            bad = [f for f in failed if "favicon" not in f[0]]
            if bad:
                print(f"      failed requests: {[(u.replace(base,''), str(f)) for u, f in bad[:3]]}")
            if "error" in body.lower()[:400] and "Internal" in body:
                print(f"      >>> page shows a server error")
        b.close()
