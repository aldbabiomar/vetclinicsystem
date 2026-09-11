# -*- coding: utf-8 -*-
"""How much English is still on each page when the app is set to Arabic.

Counts distinct English words in the rendered text of every page, excluding
words that are DATA — owner names, patient names, item names, stored file
paths, the clinic's own name. What is left is untranslated UI.

Shares check_rendered_js's page discovery and loading-shell handling, and for
the same reasons: a hand-written page list silently omits pages, and a heavy
report returns a placeholder whose English is not the page's English.
"""
import html
import re
import sys

sys.path.insert(0, "/Users/omaraldbabi/Desktop/VetClinicSystem/scripts/simulation")
from check_rendered_js import pages, _follow_loading_shell  # noqa: E402
from vzsim import Client, q, set_language  # noqa: E402

# words that are legitimately Latin on an Arabic page
ALWAYS_LATIN = {
    "VetClinicSystem", "English", "PDF", "WhatsApp", "http", "https", "localhost",
    "python", "reconcile", "attachments", "com", "www", "csv", "xlsx", "dump",
    # clinic_location's seeded default — a setting the clinic edits, and the
    # single biggest contributor to this count because it is in the header of
    # every page
    "Baghdad", "Iraq", "Amman", "Jordan",
    # theme palette names and browser/OS names are proper nouns
    "Vetzone", "ChamPet", "Chrome", "Safari", "Firefox", "Edge", "Mac", "Windows",
    "Linux", "Android", "iOS", "iPhone", "iPad",
}

DATA_QUERIES = (
    # names and free text a clinic types. Anything here is data, not UI, and a
    # word that appears in one of these columns is not evidence of missing
    # translation — the change log alone accounts for ~250 "English words" per
    # app, every one of them a value somebody typed or an id the app generated.
    "select name from owners", "select animal_name from patients",
    "select name from price_list", "select name from inventory_list",
    "select name from distributors", "select doctor from visits",
    "select value from settings", "select full_name from users",
    "select username from users", "select species from patients",
    "select sex from patients", "select unit from inventory_list",
    "select address from owners",
    "select reason from refunds", "select reason from cash_register_payouts",
    "select name from roles", "select description from roles",
    "select id from inventory_list", "select id from price_list",
    # the change log renders the before/after of every edit, plus record ids
    "select old_value from audit_log", "select new_value from audit_log",
    "select field from audit_log", "select record_id from audit_log",
    "select table_name from audit_log",
    # backup/restore rows show the file path they wrote
    "select filepath from backup_log",
)


def data_words(app):
    words = set()
    for sql in DATA_QUERIES:
        try:
            for row in (q(app, sql) or []):
                if row[0]:
                    words.update(re.findall(r"[A-Za-z]{3,}", str(row[0])))
        except Exception as e:
            # A wrong column name here silently inflates the "untranslated"
            # count with row data — exactly the kind of quiet miscount this
            # script exists to avoid, so it is loud.
            raise SystemExit(f"data query failed, fix it before trusting the "
                             f"numbers:\n  {sql}\n  {type(e).__name__}: {e}")
    return words | ALWAYS_LATIN


def run(app):
    skip = data_words(app)
    c = Client(app)
    c.login()
    set_language(app, "ar")
    findings = {}
    for page in pages(app):
        r = _follow_loading_shell(c, c.s.get(c.base + page))
        if r.status_code != 200:
            continue
        # only HTML pages carry UI text; a JSON API or an icon is not a page
        if "text/html" not in r.headers.get("content-type", ""):
            continue
        body = re.sub(r"<script.*?</script>|<style.*?</style>", "", r.text, flags=re.S)
        text = html.unescape(re.sub(r"<[^>]+>", " ", body))
        left = sorted({w for w in re.findall(r"[A-Za-z]{3,}", text) if w not in skip})
        if left:
            findings[page] = left
    set_language(app, "en")
    return findings


if __name__ == "__main__":
    grand = 0
    for app in sys.argv[1:] or ["iq", "jo"]:
        f = run(app)
        n = sum(len(v) for v in f.values())
        grand += n
        print(f"=== {app}: {len(f)} page(s) with English, {n} word instance(s) ===")
        for page, words in sorted(f.items(), key=lambda kv: -len(kv[1])):
            print(f"  {page:28s} {len(words):3d}  {words[:14]}")
    print(f"TOTAL {grand}")
