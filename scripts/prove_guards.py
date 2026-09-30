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
    Mutation("an unknown palette is refused", "vcs/web/vendor_settings.py",
             "    if not palettes.is_palette(value):", "    if False:",
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
    # --- licensing: tokens and trust (plan §4) ------------------------------
    Mutation("a token's signature is checked", "vcs/licensing/tokens.py",
             "            Ed25519PublicKey.from_public_bytes(public).verify(signature, payload)\n",
             "            Ed25519PublicKey.from_public_bytes(public)\n",
             ["tests/test_licensing_tokens.py"], why="any payload would verify"),
    Mutation("a token binds to its install", "vcs/licensing/tokens.py",
             '    if payload["install_id"] != install_id:', "    if False:",
             ["tests/test_licensing_tokens.py"]),
    Mutation("a pass is not a license", "vcs/licensing/tokens.py",
             '    if payload.get("kind") != kind:', "    if False:",
             ["tests/test_licensing_tokens.py"]),
    Mutation("a pass lasts at most twelve hours", "vcs/licensing/tokens.py",
             "    if expires - issued > timedelta(hours=MAX_PASS_HOURS):", "    if False:",
             ["tests/test_licensing_tokens.py"], why="plan A2"),
    Mutation("a pass from the future is refused", "vcs/licensing/tokens.py",
             "    if issued > now + PASS_FUTURE_SLACK:", "    if False:",
             ["tests/test_licensing_tokens.py"]),
    Mutation("an expired pass is refused", "vcs/licensing/tokens.py",
             "    if now >= expires:", "    if False:",
             ["tests/test_licensing_tokens.py"]),
    Mutation("no production entry point trusts a key", "vcs/web/factory.py",
             "def create_app():\n",
             "def create_app():\n    from vcs.licensing.tokens import trust_for_tests\n    trust_for_tests('k', b'')\n",
             ["tests/test_licensing_tokens.py"], why="a run-time trust list is a free-license switch"),
    Mutation("the trusted keys are source constants", "vcs/licensing/trusted_keys.py",
             "TRUSTED_KEYS = {}\n", "import os\nTRUSTED_KEYS = dict(os.environ.get('VCS_KEYS', {}))\n",
             ["tests/test_licensing_tokens.py"]),
    Mutation("the app never signs", "vcs/licensing/tokens.py",
             "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey\n",
             "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey, Ed25519PrivateKey\n",
             ["tests/test_licensing_tokens.py"]),
    Mutation("the vendor tool keeps keys out of the repository", "scripts/vendor/vcs_vendor.py",
             "    if resolved == REPO or REPO in resolved.parents:", "    if False:",
             ["tests/test_licensing_tokens.py"]),
    Mutation("an install ID is never replaced", "setup.py",
             "    if found:\n        install_id = found.group(1)\n",
             "    if False:\n        install_id = found.group(1)\n",
             ["tests/test_install_ports.py"], why="a new ID would invalidate the license"),
    # --- licensing: developer access (plan §7) ------------------------------
    Mutation("the system Admin cannot reach the Developer area", "vcs/web/devsession.py",
             "        if current() is None:\n",
             "        if current() is None and not session.get('user_id'):\n",
             ["tests/test_developer_access.py"], db=True, why="a role or permission must not open it"),
    Mutation("there is no developer permission", "vcs/auth.py",
             '    ("manage_owners", "Manage Owners", "Patients & Visits"),\n',
             '    ("manage_owners", "Manage Owners", "Patients & Visits"),\n    ("developer_area", "Developer Area", "Admin"),\n',
             ["tests/test_developer_access.py::test_there_is_no_developer_permission"]),
    Mutation("a developer session ends with its pass", "vcs/web/devsession.py",
             '        expired = clock.now() >= clock.parse(dev["expires_at"])', "        expired = False",
             ["tests/test_developer_access.py"], db=True),
    Mutation("developer sign-in shares the sign-in limit", "vcs/web/blueprints/developer.py",
             "        if not login_rate_limit_check(request.remote_addr):", "        if False:",
             ["tests/test_developer_access.py"], db=True),
    Mutation("a refused developer sign-in is recorded", "vcs/web/blueprints/developer.py",
             '            developer_audit.record(db, "developer.login_failed", actor="dev:?", outcome="refused",\n',
             '            (lambda *a, **k: None)(db, "developer.login_failed", actor="dev:?", outcome="refused",\n',
             ["tests/test_developer_access.py"], db=True),
    Mutation("the developer audit is never pruned", "vcs/domain/logs.py",
             '    ("audit_log", "timestamp"),\n', '    ("audit_log", "timestamp"),\n    ("developer_audit", "at"),\n',
             ["tests/test_developer_access.py::test_nothing_prunes_or_deletes_the_developer_audit"]),
    Mutation("the Developer group is drawn only for a developer", "vcs/web/nav.py",
             "        if group.developer_only and not developer:", "        if False:",
             ["tests/test_developer_access.py"], db=True),
    # --- licensing: the license and read-only mode (plan §5-§6) -------------
    Mutation("a write is refused while read-only", "vcs/web/readonly.py",
             '    return render_template("read_only.html", status=status), 403', "    return None",
             ["tests/test_license.py"], db=True, why="seam rule 1: one hook, every writing endpoint"),
    Mutation("read-only begins at a sign-in, not mid-task", "vcs/web/readonly.py",
             "    if session.get(SESSION_KEY) in state.WRITABLE:\n        return None\n", "",
             ["tests/test_license.py"], db=True),
    Mutation("a renewal unlocks at once", "vcs/licensing/state.py",
             "    _write_atomically(_key_path(), key + \"\\n\")\n    return refresh(db, now)",
             "    _write_atomically(_key_path(), key + \"\\n\")\n    return evaluate(db, now)",
             ["tests/test_license.py"], db=True),
    Mutation("a clock wound back is noticed", "vcs/licensing/state.py",
             "    if seen is not None and now < seen - CLOCK_SLACK:", "    if False:",
             ["tests/test_license.py"], db=True),
    Mutation("payments stay refused while read-only", "vcs/web/readonly.py",
             '    "clinical.inpatient_update_add",', '    "clinical.inpatient_update_add", "clinical.inpatient_payment_add",',
             ["tests/test_license.py"], db=True, why="A7: the reason to renew"),
    Mutation("the nightly backup ignores the license", "vcs/ops/scheduler.py",
             '            backup.run_backup(db, triggered_by="nightly")',
             '            __import__("vcs.licensing.state", fromlist=["s"]).current().writable and '
             'backup.run_backup(db, triggered_by="nightly")',
             ["tests/test_license.py"], db=True),
    Mutation("the expiry warning is for those who can renew", "vcs/templates/_license_banner.html",
             "  {% if license_status.state == 'expiring' %}\n    {% if can_manage %}",
             "  {% if license_status.state == 'expiring' %}\n    {% if true %}",
             ["tests/test_license.py"], db=True),
    Mutation("setup does not finish without a license", "setup.py",
             '"then run setup again with --license-key.")\n        sys.exit(1)',
             '"then run setup again with --license-key.")\n        return status',
             ["tests/test_license.py"], db=True, why="L-7"),
    # --- licensing: what the vendor sets (plan §9-§10) ----------------------
    Mutation("the clinic's Settings refuses the vendor's settings", "vcs/web/blueprints/settings.py",
             "    **{key: vendor_settings.DEVELOPER for key in vendor_settings.KEYS},\n", "",
             ["tests/test_vendor_settings.py::test_the_system_admin_cannot_set_a_vendor_setting"], db=True,
             extra=[("vcs/web/blueprints/settings.py", '"member_discount_percent", "member_term_months"]:',
                     '"member_discount_percent", "member_term_months", "theme_palette"]:')],
             why="audit S1: a field the template hides is still saved by the POST -- both layers out"),
    Mutation("the money setting's lock holds for the vendor too", "vcs/web/vendor_settings.py",
             "    if current is not None and money.is_locked(db):", "    if False:",
             ["tests/test_vendor_settings.py"], db=True, why="L-3 moved the control, not the rule"),
    Mutation("the ping URL is https", "vcs/web/vendor_settings.py",
             '    if value and not value.lower().startswith("https://"):', "    if False:",
             ["tests/test_vendor_settings.py"], db=True),
    Mutation("the ping URL is never written to the change log", "vcs/web/vendor_settings.py",
             "    change = (_secret_state(old), _secret_state(value))", "    change = (old, value)",
             ["tests/test_vendor_settings.py", "tests/test_heartbeat.py"], db=True,
             why="anyone holding it can silence the alert"),
    Mutation("the update token is read at every call", "vcs/ops/updater.py",
             "def read_token():\n", '@__import__("functools").lru_cache(maxsize=None)\ndef read_token():\n',
             ["tests/test_vendor_settings.py::test_the_token_is_read_at_every_call"],
             why="read once at import, a replaced token did nothing until a restart"),
    Mutation("the update token file is its owner's only", "vcs/ops/updater.py",
             "    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)",
             "    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)",
             ["tests/test_vendor_settings.py::test_the_token_file_is_readable_only_by_its_owner"],
             extra=[("vcs/ops/updater.py", "    os.chmod(path, 0o600)\n", "")]),
    Mutation("the update token is never audited", "vcs/web/blueprints/developer.py",
             'detail={"token": "set" if updater.read_token() else "not set",',
             'detail={"token": updater.read_token() or "not set",',
             ["tests/test_vendor_settings.py"], db=True),
    Mutation("without a token, updates say so", "vcs/web/update_jobs.py",
             "    refused = _no_token(updater)\n    if refused:\n        return refused\n", "",
             ["tests/test_vendor_settings.py::test_without_a_token_updates_say_so"], db=True,
             why="otherwise a private repo answers 404, which reads as no release"),
    # --- the money setting's one home ----------------------------------------
    Mutation("nothing outside money.py compares the setting's code", "vcs/web/blueprints/clinical.py",
             '        if new_case_status != visit["case_status"]:',
             '        if new_case_status != visit["case_status"] and money.current().code != "IQ":',
             ["tests/test_money_home.py"]),
    Mutation("nothing outside money.py rounds money", "vcs/domain/reports.py",
             "        net_margin = round(net_profit / revenue, 4) if revenue else None",
             '        net_margin = (net_profit / revenue).quantize(Decimal("0.0001")) if revenue else None',
             ["tests/test_money_home.py"]),
    Mutation("no country literal outside money.py", "vcs/web/pdf_export.py",
             '    return m.currency if m else ""', '    return m.currency if m else "JOD"',
             ["tests/test_money_home.py"]),
    Mutation("the nightly restore check applies the clinic's own money rules", "vcs/ops/selfverify.py",
             "    places, unit = setting.minor_units, setting.cash_unit",
             '    places, unit = 3, "0.001"',
             ["tests/test_selfverify.py"], db=True, why="JO's rules verified an IQ backup"),
    # --- a fresh install -----------------------------------------------------
    Mutation("the launcher serves on the port in .env", "setup.py",
             'PORT="${VETCLINICSYSTEM_PORT:-}"\nif [ -z "$PORT" ] && [ -f "$DATA_DIR/.env" ]; then',
             'PORT="${VETCLINICSYSTEM_PORT:-5050}"\nif false; then',
             ["tests/test_install_ports.py"], why="the launcher overrode .env with 5050"),
    Mutation("a new install counts other containers' ports", "setup.py",
             "    claimed = docker_claimed_ports()\n", "    claimed = set()\n",
             ["tests/test_install_ports.py"], why="compose up failed: port is already allocated"),
    Mutation("docker publishes the port in .env", "setup.py",
             '    if not url:\n        from dotenv import dotenv_values\n',
             '    if False:\n        from dotenv import dotenv_values\n',
             ["tests/test_install_ports.py"], why="found by a real first install"),
    Mutation("setup run again finds the install's .env", "setup.py",
             '    if os.path.isfile(os.path.join(sibling, "active_release.txt")):',
             "    if False:",
             ["tests/test_install_ports.py"], why="a second run wrote a new .env with new ports"),
    Mutation("the first double-click hands over to the install's launcher", "Start VetClinicSystem.command",
             'if [ -f "$MANAGED" ]; then', "if false; then",
             ["tests/test_install_ports.py"], why="SECRET_KEY is not set, on the first double-click"),
    Mutation("the chosen app port is written into .env", "setup.py",
             '    line = f"VETCLINICSYSTEM_PORT={app_port}"', '    line = "#VETCLINICSYSTEM_PORT=5050"',
             ["tests/test_install_ports.py"]),
    Mutation("the Desktop shortcut opens the install's port", "vcs/ops/desktop_shortcut.py",
             "launcher=_sh_quote(launcher), port=install_port(data_dir)))",
             "launcher=_sh_quote(launcher), port=DEFAULT_PORT))",
             ["tests/test_desktop_shortcut_target.py"]),
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
