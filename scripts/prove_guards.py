#!/usr/bin/env python3
"""
Prove that each guard test actually catches the bug it guards (CLAUDE.md §5.2,
decision 0009).

For every entry in MUTATIONS: put the bug back (replace one exact, unique
piece of source), run the tests that guard it, and require at least one to
FAIL. Then restore the source and run the same tests again, and require them
to PASS -- the control. A mutation whose tests are skipped or deselected is
NOT PROVEN: a guard that did not run proved nothing.

    TEST_DATABASE_URL=postgresql://postgres:test@localhost:55492/vetclinicsystem \\
        /tmp/vcs_test_venv_jo/bin/python scripts/prove_guards.py [--all | name ...]

With no argument it lists the mutations. Entries marked `db` need the test
database; without TEST_DATABASE_URL they are reported NOT RUN. Entries marked
`browser` also need APP_URL (5091 = iq, 5092 = jo); the app there is restarted
after the bug goes in and again after it comes out, because it caches its
templates and would otherwise go on serving the code from before the change.

The source is always restored, and a backup is written first: if this is
killed mid-run, the next run puts the file back before anything else. The
test database is not: a test run with a bug in writes rows the way the bug
does (a change-log value in the wrong form, say), and a page-wide check in
the next suite run finds them. Reset the environment after proving
(`scripts/isolated_test_env.sh reset iq|jo`) before trusting a suite run.
"""
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP = ROOT / ".prove_guards_backup.json"


@dataclass
class Mutation:
    name: str
    path: str               # relative to the repository
    old: str                # must occur exactly once
    new: str
    tests: list             # pytest node ids or files
    db: bool = False        # needs TEST_DATABASE_URL
    why: str = ""
    browser: bool = False   # drives the live app (APP_URL); it is restarted
                            # around each run, since it caches its templates
    extra: list = field(default_factory=list)   # further (path, old, new) in the same mutation


MUTATIONS = [
    # --- restructure R2/R3 ---------------------------------------------------
    Mutation("skip list names real endpoints", "tests/test_routes_smoke.py",
             '    "settings.settings_updates_check",', '    "settings_updates_check",',
             ["tests/test_routes_smoke.py::test_every_skipped_endpoint_exists"], db=True,
             why="a skip entry that names no endpoint skips nothing"),
    Mutation("a domain module is not rebound", "vcs/web/blueprints/settings.py",
             '    stored = {r["key"]: r["value"] for r in rows}',
             '    settings = {r["key"]: r["value"] for r in rows}',
             ["tests/test_domain_imports.py"], why="UnboundLocalError on the one path"),
    Mutation("no Flask in the domain", "vcs/domain/refunds.py",
             "from vcs import money\n", "from vcs import money\nfrom flask import g\n",
             ["tests/test_domain_imports.py"]),
    Mutation("job step labels are translated", "vcs/web/blueprints/settings.py",
             '[_("Checking backup folder"), _("Dumping database"),',
             '["Checking backup folder", _("Dumping database"),',
             ["tests/test_progress_panels.py"]),
    # --- R4 -----------------------------------------------------------------
    Mutation("no ? placeholder", "vcs/web/blueprints/main.py",
             '"SELECT * FROM users WHERE username=%s"', '"SELECT * FROM users WHERE username=?"',
             ["tests/test_sql_placeholders.py"], why="audit D7"),
    Mutation("no bare % with parameters", "vcs/web/blueprints/main.py",
             '"SELECT * FROM users WHERE username=%s"',
             '"SELECT * FROM users WHERE username=%s AND username NOT LIKE \'x%\'"',
             ["tests/test_sql_placeholders.py"]),
    Mutation("placeholder lists are lists", "vcs/web/blueprints/sales.py",
             '",".join(["%s"] * len(qty_by_item))', '",".join("%s" * len(qty_by_item))',
             ["tests/test_sql_placeholders.py"]),
    Mutation("latest audit is the latest by date", "vcs/domain/inventory.py",
             "ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY audit_date DESC, id DESC) AS recency",
             "ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY confirmed_order DESC, id DESC) AS recency",
             ["tests/test_inventory_latest_state.py"], db=True, why="audit D3/D4"),
    Mutation("thresholds carry forward", "vcs/domain/inventory.py",
             "           FIRST_VALUE(reorder_threshold) OVER (PARTITION BY item_id, threshold_group ORDER BY confirmed_order, id)\n",
             "           reorder_threshold\n",
             ["tests/test_inventory_latest_state.py"], db=True),
    Mutation("item_ids scopes the status", "vcs/domain/inventory.py",
             'items = db.execute("SELECT * FROM inventory_list WHERE active=true AND id = ANY(%s) ORDER BY name",\n'
             '                           (list(item_ids),)).fetchall()',
             'items = db.execute("SELECT * FROM inventory_list WHERE active=true ORDER BY name").fetchall()',
             ["tests/test_inventory_latest_state.py"], db=True),
    Mutation("wellness window is a superset of due", "vcs/domain/clinical.py",
             "params += [today - timedelta(days=MISSED_WINDOW_DAYS), ",
             "params += [today - timedelta(days=MISSED_WINDOW_DAYS - 2), ",
             ["tests/test_dashboard_snapshot_bounds.py"], db=True),
    Mutation("dashboard reads tomorrow's follow-ups", "vcs/domain/alerts.py",
             "on_dates=[today, tomorrow]", "on_dates=[today]",
             ["tests/test_dashboard_snapshot_bounds.py"], db=True),
    Mutation("every write to a bill stores its total", "vcs/web/blueprints/clinical.py",
             '               (dismissal_date, final_total, now, boarding_id))\n    billing.bill_changed(db, "boarding", boarding_id)',
             '               (dismissal_date, final_total, now, boarding_id))\n    pass',
             ["tests/test_seam_rules.py::test_every_write_to_a_bills_inputs_stores_its_new_total"],
             why="audit D2, seam rule 12"),
    Mutation("helpers do not commit", "vcs/domain/billing.py",
             "    _REFRESH[kind](db, record_id)\n", "    _REFRESH[kind](db, record_id)\n    db.commit()\n",
             ["tests/test_no_hidden_commits.py"], why="audit D11"),
    Mutation("a visit bill skips an unpriced item", "vcs/web/blueprints/clinical.py",
             '            if price_row["sale_price"] is None:\n                had_unpriced = True',
             '            if False:\n                had_unpriced = True',
             ["tests/test_unpriced_items.py"], db=True),
    Mutation("an inpatient bill skips an unpriced item", "vcs/web/blueprints/clinical.py",
             '        if price_row["sale_price"] is None:\n            had_unpriced = True',
             '        if False:\n            had_unpriced = True',
             ["tests/test_unpriced_items.py"], db=True),
    # --- found by the simulation sweeps (tooling) ------------------------------
    Mutation("an amount too long to round is refused", "vcs/money.py",
             "    if abs(val) > m.max_amount + m.quantum:\n", "    if False:\n",
             ["tests/test_money.py", "tests/test_money_iq.py"], why="a 500 on the Price List form"),
    Mutation("a sign-in's own second still counts", "vcs/auth.py",
             "(user_id, username, 1 if success else 0, clock.now(), ip, ua),",
             '(user_id, username, 1 if success else 0, clock.now().isoformat(timespec="seconds"), ip, ua),',
             ["tests/test_login_lockout.py"], db=True, why="failures beside a success were not counted"),
    Mutation("a consignment shortfall is a warning", "vcs/web/blueprints/inventory.py",
             "items=list_join(shortfalls)), \"warning\")", "items=list_join(shortfalls)), \"error\")",
             ["tests/test_audit_shortfall.py"], db=True),
    Mutation("a stored constant is shown through |tr", "vcs/templates/boarding.html",
             "{{ s.billing.status|tr }}", "{{ s.billing.status }}",
             ["tests/test_enum_labels.py::test_a_stored_constant_is_shown_through_tr"]),
    Mutation("a logged moment is shown in the clinic's time", "vcs/templates/admin_logs.html",
             '{{ (c.old_value|logvalue) or "—" }} → {{ (c.new_value|logvalue) or "—" }}',
             '{{ c.old_value or "—" }} → {{ c.new_value or "—" }}',
             ["tests/test_timestamps_render.py"], db=True),
    # --- palettes -----------------------------------------------------------
    Mutation("heatmap text stays AA", "vcs/web/palettes.py",
             "HEATMAP_MAX_MIX = 0.40", "HEATMAP_MAX_MIX = 0.95", ["tests/test_palettes.py"], why="D-12"),
    Mutation("an unknown palette is refused", "vcs/web/blueprints/settings.py",
             "if palette_val is not None and not palettes.is_palette(palette_val):", "if False:",
             ["tests/test_palettes.py"], db=True),
    Mutation("the favicon follows the palette", "vcs/web/blueprints/main.py",
             'brand.favicon_svg(palettes.PALETTES[key].light["primary"])', 'brand.favicon_svg("#B21C43")',
             ["tests/test_palettes.py"], db=True),
    Mutation("style.css uses only palette colours", "vcs/static/style.css",
             ".page-sub { color: var(--ink-soft);", ".page-sub { color: var(--accent-alt);",
             ["tests/test_palettes.py"]),
    Mutation("palettes.css is generated", "vcs/static/palettes.css",
             "   Do not edit: change the palette there and regenerate. */", "   Edited by hand. */",
             ["tests/test_palettes.py"]),
    # --- moments -------------------------------------------------------------
    Mutation("a case status change is stamped with its moment", "vcs/web/blueprints/clinical.py",
             "            status_changed_at = clock.now()", "            status_changed_at = clock.today().isoformat()",
             ["tests/test_workflow_routes.py::test_a_case_status_change_is_stamped_with_the_moment_it_was_made"],
             db=True, why="today's date string is the clinic's midnight"),
    Mutation("the change log writes a moment as ISO", "vcs/auth.py",
             "    if isinstance(v, date):             # a datetime is a date too\n        return v.isoformat()\n",
             "",
             ["tests/test_workflow_routes.py::test_a_case_status_change_is_stamped_with_the_moment_it_was_made"],
             db=True, why="str() writes a space, which the log page printed raw"),
    # --- localization and layout ---------------------------------------------
    Mutation("a script's number survives Arabic", "vcs/templates/audit_session_view.html",
             "  const totalItems = {{ items|length }};", "  const totalItems = {{ items|length|qty }};",
             ["tests/test_browser.py::test_no_page_raises_a_javascript_error_in_arabic",
              "tests/test_browser.py::test_no_page_raises_a_javascript_error_or_fails_an_asset"],
             browser=True, why="Arabic-Indic digits in a script are a SyntaxError in Arabic only"),
    Mutation("a modal is not shown by display alone once CSS drives its opacity", "vcs/static/style.css",
             ".modal-overlay { position: fixed; inset: 0;", ".modal-overlay { opacity: 0; position: fixed; inset: 0;",
             ["tests/test_modal_visibility.py"], why="the test used to skip under this stylesheet"),
    Mutation("the barcode label draws its barcode", "vcs/templates/barcode_label.html",
             "\nrenderBarcodeLabel();\n",
             "\ndocument.querySelector('script[src*=\"JsBarcode\"]').addEventListener('load', renderBarcodeLabel);\n",
             ["tests/test_browser.py::test_the_barcode_label_actually_draws_a_barcode"], browser=True,
             why="the original bug; the test used to skip in every database"),
    Mutation("a date is shown in Arabic-Indic digits under Arabic", "vcs/web/core.py",
             "    return display_number(formatted) if formatted else formatted\n",
             "    return formatted\n",
             ["tests/test_localization.py::test_dates_render_in_arabic_indic_digits_when_arabic"], db=True,
             why="the test once skipped when the page had no dated row"),
    Mutation("a PDF names the Latin currency code", "vcs/web/pdf_export.py",
             '    return m.currency if m else ""', '    return m.label_ar if m else ""',
             ["tests/test_localization.py::test_pdf_export_still_uses_the_latin_currency_code"],
             why="the test once held only because a docstring said JOD"),
    Mutation("text in an attribute goes through _()", "vcs/templates/refunds.html",
             'placeholder="{{ _(\'e.g. %(example)s\', example=\'1042\') }}"', 'placeholder="e.g. 1042"',
             ["tests/test_catalogue.py"]),
    Mutation("a constant behind a fallback goes through |tr", "vcs/templates/distributor_detail.html",
             '{{ p.method|tr if p.method else "—" }}', '{{ p.method or "—" }}',
             ["tests/test_enum_labels.py"]),
    Mutation("a one-column panel grid lets its card shrink", "vcs/static/style.css",
             "@media (max-width: 900px) { .panel-grid { grid-template-columns: minmax(0, 1fr); }",
             "@media (max-width: 900px) { .panel-grid { grid-template-columns: 1fr; }",
             ["tests/test_browser.py::test_no_page_scrolls_sideways_in_arabic"], browser=True,
             extra=[("vcs/static/style.css", "  .panel-grid { grid-template-columns: minmax(0, 1fr); }",
                     "  .panel-grid { grid-template-columns: 1fr; }")],
             why="Arabic /refunds: 397px of content on a 390px phone"),
    Mutation("a growing input gives way to its button", "vcs/static/style.css",
             ".u-grow        { flex: 1; min-width: 0; }", ".u-grow        { flex: 1; }",
             ["tests/test_browser.py::test_no_page_scrolls_sideways_in_arabic"], browser=True,
             why="Arabic /refunds: the Find Sale row spills out of its card"),
    Mutation("a bill's payment row wraps", "vcs/templates/visit_detail.html",
             'class="bill-form bill-pay">',
             'style="margin-top:16px; padding-top:14px; border-top:1px solid var(--line); '
             'display:flex; gap:8px; align-items:flex-end;">',
             ["tests/test_browser.py::test_no_detail_page_scrolls_sideways"], browser=True,
             extra=[("vcs/templates/visit_detail.html",
                     '<div class="field"><label for="visitdetail-5-amount">',
                     '<div class="field" style="flex:1;"><label for="visitdetail-5-amount">')],
             why="the original markup: /visits/<id>, 1195px of content in a 1024px window"),
    Mutation("a distributor's payments table scrolls in its card", "vcs/templates/distributor_detail.html",
             '  <div class="table-wrap"><table>', "  <div><table>",
             ["tests/test_browser.py::test_no_detail_page_scrolls_sideways"], browser=True),
]


def _recover():
    """Put back any file a killed run left mutated."""
    if BACKUP.exists():
        saved = json.loads(BACKUP.read_text(encoding="utf-8"))
        for rel, text in saved.items():
            (ROOT / rel).write_text(text, encoding="utf-8")
            print(f"restored {rel} from an interrupted run")
        BACKUP.unlink()


def _run(tests):
    """(failed, passed, skipped) of a pytest run of `tests`."""
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as fh:
        report = fh.name
    subprocess.run([sys.executable, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider", f"--junitxml={report}"],
                   cwd=ROOT, capture_output=True, text=True)
    suite = ET.parse(report).getroot()
    suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
    os.unlink(report)
    total = int(suite.get("tests", 0))
    failed = int(suite.get("failures", 0)) + int(suite.get("errors", 0))
    skipped = int(suite.get("skipped", 0))
    return failed, total - failed - skipped, skipped


def _restart_app():
    """Restart the test app APP_URL names, by port (isolated_test_env.sh)."""
    port = os.environ["APP_URL"].rstrip("/").rsplit(":", 1)[-1]
    env = {"5091": "iq", "5092": "jo"}[port]
    subprocess.run([str(ROOT / "scripts" / "isolated_test_env.sh"), "restart", env],
                   cwd=ROOT, capture_output=True, check=True)


def prove(m):
    if (m.db or m.browser) and not os.environ.get("TEST_DATABASE_URL"):
        return "NOT RUN", "needs TEST_DATABASE_URL"
    if m.browser and os.environ.get("APP_URL", "").rstrip("/").rsplit(":", 1)[-1] not in ("5091", "5092"):
        return "NOT RUN", "needs APP_URL=http://127.0.0.1:5091 (or 5092)"
    changes = [(m.path, m.old, m.new), *m.extra]
    originals = {}
    for rel, old, _new in changes:
        text = originals.get(rel) or (ROOT / rel).read_text(encoding="utf-8")
        if text.count(old) != 1:
            return "BROKEN", f"anchor occurs {text.count(old)} times in {rel} — update the mutation"
        originals[rel] = text
    BACKUP.write_text(json.dumps(originals), encoding="utf-8")
    try:
        mutated = dict(originals)
        for rel, old, new in changes:
            mutated[rel] = mutated[rel].replace(old, new, 1)
        for rel, text in mutated.items():
            (ROOT / rel).write_text(text, encoding="utf-8")
        if m.browser:
            _restart_app()
        failed, passed, skipped = _run(m.tests)
    finally:
        for rel, text in originals.items():
            (ROOT / rel).write_text(text, encoding="utf-8")
        BACKUP.unlink()
        if m.browser:
            _restart_app()
    if failed == 0:
        why = ("no test ran" if not (passed or skipped) else
               "its tests were skipped" if not passed else "its tests still passed")
        return "NOT PROVEN", f"{why} with the bug back ({passed} passed, {skipped} skipped)"
    c_failed, c_passed, c_skipped = _run(m.tests)
    if c_failed or not c_passed:
        return "CONTROL FAILED", f"on the restored code: {c_failed} failed, {c_passed} passed, {c_skipped} skipped"
    return "PROVEN", f"{failed} test(s) failed with the bug back; {c_passed} pass without it"


def main(argv):
    _recover()
    if not argv:
        for m in MUTATIONS:
            print(f"  {m.name}{'  [db]' if m.db else ''}{'  [browser]' if m.browser else ''}")
        print("\nRun with --all, or name some.")
        return 0
    chosen = MUTATIONS if argv == ["--all"] else [m for m in MUTATIONS if m.name in argv]
    unknown = set(argv) - {m.name for m in MUTATIONS} - {"--all"}
    if unknown:
        print(f"no such mutation: {sorted(unknown)}")
        return 2
    bad = 0
    for m in chosen:
        verdict, detail = prove(m)
        bad += verdict != "PROVEN"
        print(f"  [{verdict:>14}] {m.name} — {detail}", flush=True)
    print(f"\n{len(chosen) - bad} of {len(chosen)} proven.")
    if any(m.db or m.browser for m in chosen):
        print("The test database holds rows written while bugs were in: reset it "
              "(scripts/isolated_test_env.sh reset iq|jo) before the next suite run.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
