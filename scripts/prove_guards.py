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
             '    "main.logout",', '    "logout",',
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
    Mutation("a wrong passphrase is a plain message", "scripts/vendor/vcs_vendor.py",
             "    except (ValueError, TypeError):\n        raise SystemExit(f\"That passphrase",
             "    except ():\n        raise SystemExit(f\"That passphrase",
             ["tests/test_licensing_tokens.py::test_a_wrong_passphrase_is_a_plain_message"],
             why="it ended in a traceback: ValueError: Incorrect password, could not decrypt key"),
    Mutation("a license ends on the clinic's day", "scripts/vendor/vcs_vendor.py",
             "    end = datetime.combine(day, time(23, 59, 59), tzinfo=zone)",
             "    end = datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)",
             ["tests/test_licensing_tokens.py::test_a_license_ends_on_the_date_the_vendor_gave_at_the_clinic"],
             why="--expires 2027-09-30 showed as 2027-10-01 in Iraq and Jordan"),
    Mutation("an end date is exactly YYYY-MM-DD", "scripts/vendor/vcs_vendor.py",
             "            if not _ISO_DAY.fullmatch(text):", "            if False:",
             ["tests/test_licensing_tokens.py::test_a_mistyped_end_date_is_a_plain_message"],
             why="fromisoformat also takes 20270930 and 2027-W39-4"),
    Mutation("the end date is checked before the passphrase", "scripts/vendor/vcs_vendor.py",
             "            expires = _expiry(args)\n", "            expires = None\n",
             ["tests/test_licensing_tokens.py::test_the_end_date_is_checked_before_the_passphrase_is_asked"],
             extra=[("scripts/vendor/vcs_vendor.py",
                     "payload = license_payload(key, args.install_id, args.clinic_name, expires,",
                     "payload = license_payload(key, args.install_id, args.clinic_name, _expiry(args),")]),
    # --- the Vendor Console and setup codes (VENDOR_CONSOLE_PLAN.md) ----------
    Mutation("the console answers this computer only", "scripts/vendor/console.py",
             "        if host not in LOOPBACK:\n            abort(400)\n", "",
             ["tests/test_vendor_console.py::test_it_answers_this_computer_only"], why="DNS rebinding"),
    Mutation("every console form needs its CSRF token", "scripts/vendor/console.py",
             "    CSRFProtect(app)\n", "",
             ["tests/test_vendor_console.py::test_every_form_needs_its_csrf_token"],
             why="any page in the vendor's browser can post to 127.0.0.1"),
    Mutation("the console signs nothing while locked", "scripts/vendor/console.py",
             "            if not unlocked():\n", "            if False:\n",
             ["tests/test_vendor_console.py::test_nothing_is_signed_while_locked"]),
    Mutation("the console locks when idle", "scripts/vendor/console.py",
             '            if time.monotonic() - state["last"] > app.config["IDLE_SECONDS"]:', "            if False:",
             ["tests/test_vendor_console.py::test_the_key_locks_when_idle_and_on_lock"]),
    Mutation("the console never writes down a secret", "scripts/vendor/console.py",
             "                (name, str(uuid.uuid4()), money_setting, palette,",
             "                (name, str(uuid.uuid4()), money_setting, palette + token,",
             ["tests/test_vendor_console.py::test_the_console_never_writes_down_a_secret"], why="V-3"),
    Mutation("a damaged setup code is refused", "setup.py",
             "    if hashlib.sha256(data).hexdigest()[:12] != parts[2]:", "    if False:",
             ["tests/test_setup_code.py::test_a_damaged_setup_code_is_refused_before_anything_is_written"]),
    Mutation("a setup code for another installation is refused", "setup.py",
             '    if code and install_id != code["install_id"]:', "    if False:",
             ["tests/test_setup_code.py::test_a_setup_code_for_another_installation_is_refused"]),
    Mutation("the update token moves into the data folder", "setup.py",
             '    for name, is_there in (("license", os.path.isdir), ("github_token", os.path.isfile)):',
             '    for name, is_there in (("license", os.path.isdir),):',
             ["tests/test_setup_code.py::test_the_token_moves_into_the_data_folder_with_the_license"]),
    Mutation("a setup code longer than a terminal line can be pasted", "setup.py",
             "        import readline  # noqa: F401 -- loading it is the effect",
             "        pass",
             ["tests/test_setup_code.py::test_a_setup_code_longer_than_a_terminal_line_can_be_pasted"]),
    Mutation("a setup code pasted in pieces is put back together", "setup.py",
             "            text += more",
             "            break",
             ["tests/test_setup_code.py::test_a_setup_code_pasted_in_pieces_is_put_back_together"]),
    Mutation("setup never prints a secret from the code", "setup.py",
             '        print("  Update access token saved.")',
             '        print(f"  Update access token saved: {code[\'github_token\']}")',
             ["tests/test_setup_code.py::test_a_secret_from_the_code_is_never_printed"], db=True),
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
             "                  if k in request.form and not auth.has_permission(perm)]",
             "                  if k in request.form and not auth.has_permission(perm) "
             "and perm != vendor_settings.DEVELOPER]",
             ["tests/test_vendor_settings.py::test_the_system_admin_cannot_set_any_vendor_setting"], db=True,
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
    Mutation("a new key ends a lockout from a clock that was ahead", "vcs/licensing/state.py",
             "        _remember_seen(db, now)\n        accepted = seen\n", "        accepted = seen\n",
             ["tests/test_license.py::test_a_new_key_ends_a_lockout_from_a_clock_that_was_ahead",
              "tests/test_license.py::test_the_license_page_ends_the_lockout_and_records_it"], db=True,
             why="the owner's report, 2026-10-02: read-only with a correct clock, and a new key changed nothing"),
    Mutation("a key replayed on a wound-back clock does not vouch for it", "vcs/licensing/state.py",
             '    newer = held is None or issued > clock.parse(held["issued_at"])', "    newer = True",
             ["tests/test_license.py::test_a_key_that_does_not_vouch_for_the_clock_leaves_the_lockout"], db=True),
    Mutation("only a key just signed vouches for the clock", "vcs/licensing/state.py",
             "    return newer and issued - CLOCK_SLACK <= now <= issued + FRESH_KEY", "    return newer",
             ["tests/test_license.py::test_a_key_that_does_not_vouch_for_the_clock_leaves_the_lockout"], db=True),
    Mutation("the clinic's Settings page has no update controls", "vcs/templates/settings.html",
             """<div class="settings-card-head"><h2>{{ _('Startup & Shutdown') }}</h2>""",
             """<button type="button" id="updCheckBtn">{{ _('Check for Updates') }}</button>
<div class="settings-card-head"><h2>{{ _('Startup & Shutdown') }}</h2>""",
             ["tests/test_admin_routes.py::test_the_clinics_settings_page_has_no_update_controls"], db=True,
             why="updates are the vendor's (L-8 reversed, 2026-10-02)"),
    Mutation("Restore Now sits beside Browse", "vcs/templates/settings.html",
             """        <button class="btn" type="submit" id="restoreSubmitBtn" data-saving-label="Restoring…" disabled>{{ _('Restore Now') }}</button>
      </div>""",
             """      </div>
        <button class="btn" type="submit" id="restoreSubmitBtn" data-saving-label="Restoring…" disabled>{{ _('Restore Now') }}</button>""",
             ["tests/test_admin_routes.py::test_the_backup_cards_buttons_sit_beside_what_they_act_on"], db=True),
    Mutation("the clinic has no update route", "vcs/web/blueprints/settings.py",
             '@bp.route("/settings/job-status")\n',
             '@bp.route("/settings/updates/check")\n@auth.permission_required("manage_maintenance")\n'
             'def settings_updates_check():\n    return jsonify(update_jobs.check()[0])\n\n\n'
             '@bp.route("/settings/job-status")\n',
             ["tests/test_admin_routes.py::test_the_clinics_update_routes_are_gone"], db=True),
    Mutation("no button is painted outside the palette's main colour", "vcs/static/style.css",
             "   the one they were drawn for. tests/test_button_colours.py holds it. */\n",
             "   the one they were drawn for. tests/test_button_colours.py holds it. */\n"
             ".btn.danger { background: var(--danger); }\n",
             ["tests/test_button_colours.py::test_no_button_rule_paints_outside_the_main_colour"]),
    Mutation("no button is given a colour class", "vcs/templates/settings.html",
             '<button class="btn" type="submit" id="restoreSubmitBtn"',
             '<button class="btn danger" type="submit" id="restoreSubmitBtn"',
             ["tests/test_button_colours.py::test_no_button_is_given_a_colour_class"]),
    Mutation("without a token, updates say so", "vcs/web/update_jobs.py",
             "    refused = _no_token(updater)\n    if refused:\n        return refused\n", "",
             ["tests/test_vendor_settings.py::test_without_a_token_updates_say_so"], db=True,
             why="otherwise a private repo answers 404, which reads as no release"),
    # --- licensing: the vendor's tools (plan §11) ----------------------------
    Mutation("the support bundle takes settings by allowlist", "vcs/ops/support_bundle.py",
             'rows = db.execute("SELECT key, value FROM settings WHERE key = ANY(%s)", (list(ALLOWED_SETTINGS),))',
             'rows = db.execute("SELECT key, value FROM settings")',
             ["tests/test_developer_tools.py::test_the_bundle_takes_settings_by_allowlist_not_by_exclusion"],
             db=True, why="a secret setting added later must stay out without anyone remembering"),
    Mutation("the support bundle's logs are redacted", "vcs/ops/support_bundle.py",
             "            z.writestr(name, redact.log(redact.tail(path, LOG_LINES), secrets))",
             "            z.writestr(name, redact.tail(path, LOG_LINES))",
             ["tests/test_developer_tools.py::test_the_support_bundle_carries_no_secret_and_no_clinic_data"],
             db=True),
    Mutation("a secret is redacted by its value", "vcs/ops/redact.py",
             "    for secret in secrets:\n        value = value.replace(secret, MARK)\n", "",
             ["tests/test_developer_tools.py::test_the_support_bundle_carries_no_secret_and_no_clinic_data"],
             db=True, why="SECRET_KEY has no shape to recognise it by"),
    Mutation("quoted values are redacted from a log's message lines", "vcs/ops/redact.py",
             "    return QUOTED.sub(lambda m: m.group(0)[0] + MARK + m.group(0)[0], line)", "    return line",
             ["tests/test_developer_tools.py::test_the_support_bundle_carries_no_secret_and_no_clinic_data"],
             db=True, why="an error message can quote a patient's name"),
    Mutation("PostgreSQL's DETAIL values are redacted", "vcs/ops/redact.py",
             "    line = PG_DETAIL.sub(lambda m: (m.group(1) or m.group(3)) + MARK + (m.group(2) or m.group(4)), line)\n",
             "", ["tests/test_developer_tools.py::test_the_support_bundle_carries_no_secret_and_no_clinic_data"],
             db=True, why="Failing row contains (…, Bella, …) quotes nothing"),
    Mutation("the export leaves out the password hash", "vcs/ops/data_export.py",
             '    ("users", "password_hash"): N_(', '    ("users", "password_hash_gone"): N_(',
             ["tests/test_developer_tools.py::test_the_export_holds_no_password_hash_and_no_ping_url"], db=True),
    Mutation("the export leaves out the secret settings", "vcs/ops/data_export.py",
             '    "settings": ("key", sorted(settings.SECRET_KEYS),', '    "settings_gone": ("key", sorted(settings.SECRET_KEYS),',
             ["tests/test_developer_tools.py::test_the_export_holds_no_password_hash_and_no_ping_url"], db=True),
    Mutation("the export takes every live table", "vcs/ops/data_export.py",
             "    tables = [t for t in live_tables(db) if t not in EXCLUDED_TABLES]",
             "    tables = [t for t in live_tables(db)[1:] if t not in EXCLUDED_TABLES]",
             ["tests/test_developer_tools.py::test_every_table_is_exported_or_excluded"], db=True,
             why="a hard-coded list forgets the table added next"),
    Mutation("the export runs while read-only", "vcs/web/readonly.py",
             ' "settings.settings_data_export_start",', "",
             ["tests/test_developer_tools.py::test_the_export_runs_while_read_only"], db=True,
             why="A7: an expired clinic can still take its own data"),
    Mutation("a download is only an export by name", "vcs/ops/data_export.py",
             '    if not NAME.match(name or ""):\n        return None\n', "",
             ["tests/test_developer_tools.py::test_a_download_is_only_an_export_this_install_made"], db=True),
    Mutation("a reset clears the sign-in lockout", "vcs/auth.py",
             '        "  (SELECT password_changed_at FROM users WHERE username=%s),"\n', "",
             ["tests/test_developer_tools.py::test_restoring_admin_access"], db=True,
             extra=[("vcs/auth.py", "        (username, username, lookback_cutoff),", "        (username, lookback_cutoff),")]),
    Mutation("only a system administrator's access is restored", "vcs/web/blueprints/developer.py",
             '    target = next((u for u in _system_admins(db) if u["id"] == user_id), None)',
             '    target = db.execute("SELECT id, username, full_name, active FROM users WHERE id=%s", (user_id,)).fetchone()',
             ["tests/test_developer_tools.py::test_only_a_system_administrator_can_be_restored"], db=True),
    Mutation("the temporary password is never written down", "vcs/web/blueprints/developer.py",
             '    _audit("admin.recovered", target=str(user_id), detail={"username": target["username"]})\n',
             '    _audit("admin.recovered", target=str(user_id), detail={"username": target["username"], '
             '"password": password})\n',
             ["tests/test_developer_tools.py::test_restoring_admin_access", "tests/test_secrets.py"], db=True,
             why="shown once, stored nowhere (§11.3)"),
    Mutation("the vendor's message is escaped", "vcs/templates/_vendor_message.html",
             "{{ vendor_message.text }}", "{{ vendor_message.text|safe }}",
             ["tests/test_developer_tools.py::test_the_message_is_shown_escaped_and_labelled"], db=True, why="A13"),
    Mutation("the vendor's message ends after its last day", "vcs/domain/vendor_message.py",
             ' or expired(message, today):', ":",
             ["tests/test_developer_tools.py::test_the_message_shows_while_on_and_until_its_last_day"], db=True),
    Mutation("a Developer Pass is never written down", "vcs/web/blueprints/developer.py",
             'pass_id=payload["pass_id"], detail={"expires_at": payload["expires_at"]},',
             'pass_id=payload["pass_id"], detail={"expires_at": payload["expires_at"], '
             '"pass": request.form.get("dev_pass")},',
             ["tests/test_secrets.py"], db=True, why="seam rule 15"),
    # --- licensing: native PostgreSQL (plan §12) -----------------------------
    Mutation("only pgtools finds the client tools", "vcs/ops/backup.py",
             '        cmd = [tool.path, "-w", "-h", host, "-p", port, "-U", user, "-F", "c", "-f", out_path, dbname]',
             '        cmd = ["pg_dump", "-w", "-h", host, "-p", port, "-U", user, "-F", "c", "-f", out_path, dbname]',
             ["tests/test_seam_rules.py::test_only_pgtools_finds_the_postgresql_client_tools"], why="seam rule 16"),
    Mutation("native mode never falls back to Docker", "vcs/ops/pgtools.py",
             '    if mode() == "native":', "    if False:",
             ["tests/test_native_postgres.py::test_docker_mode_falls_back_to_the_container_but_native_never_does"],
             db=True),
    Mutation("a bin dir is the only place looked", "vcs/ops/pgtools.py",
             "        found = _executable(bin_dir, name)\n        return [found] if found else []\n",
             "        found = _executable(bin_dir, name)\n",
             ["tests/test_native_postgres.py"], db=True),
    Mutation("a tool older than the server is refused", "vcs/ops/pgtools.py",
             "        if server is None or (version is not None and version >= server):", "        if True:",
             ["tests/test_native_postgres.py::test_a_tool_older_than_the_server_is_refused"], db=True),
    Mutation("setup refuses a server older than 16", "setup.py",
             "    if version < MIN_SERVER_VERSION:", "    if False:",
             ["tests/test_native_postgres.py::test_setup_refuses_a_server_older_than_16"], db=True),
    Mutation("native setup never asks Docker for ports", "setup.py",
             '    claimed = docker_claimed_ports() if mode == "docker" else set()',
             "    claimed = docker_claimed_ports()",
             ["tests/test_native_postgres.py::test_setup_in_native_mode_writes_its_env_and_never_runs_docker"],
             db=True),
    Mutation("the self-check names a missing CREATEDB", "vcs/ops/selfcheck.py",
             '    if ctx["can_create_databases"]:', "    if True:",
             ["tests/test_native_postgres.py::test_the_self_check_says_the_role_cannot_create_databases"],
             db=True, why="rather than a generic verification failure (§12.1)"),
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
             '    claimed = docker_claimed_ports() if mode == "docker" else set()\n', "    claimed = set()\n",
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
    Mutation("a Developer page's button is in its section's corner row", "vcs/templates/developer_system.html",
             """    <div class="form-actions"><button class="btn secondary" type="submit">{{ _('Run the self-check now') }}</button></div>""",
             """    <button class="btn secondary" type="submit">{{ _('Run the self-check now') }}</button>""",
             ["tests/test_developer_layout.py::test_every_developer_button_is_in_its_sections_corner_row"], db=True),
    Mutation("a Developer section's buttons share one row", "vcs/templates/developer_updates.html",
             """      <button class="btn secondary" type="submit" form="devupd-2-test">{{ _('Test connection') }}</button>
    </div>""",
             """    </div>
    <div class="form-actions"><button class="btn secondary" type="submit" form="devupd-2-test">{{ _('Test connection') }}</button></div>""",
             ["tests/test_developer_layout.py::test_every_developer_button_is_in_its_sections_corner_row",
              "tests/test_developer_layout.py::test_the_updates_sections_buttons_share_one_row"], db=True),
    Mutation("the Developer area's button row is at the far end", "vcs/static/style.css",
             ".dev-area .form-actions { justify-content: flex-end; flex-wrap: wrap; align-items: center; }",
             ".dev-area .form-actions { flex-wrap: wrap; align-items: center; }",
             ["tests/test_developer_layout.py::test_the_corner_row_is_the_far_end"]),
    Mutation("Save license key is in the corner on the clinic's own License page", "vcs/templates/_license_panel.html",
             '<div class="form-actions form-actions-end">', '<div class="form-actions">',
             ["tests/test_developer_layout.py::test_the_panels_the_clinic_shares_keep_their_button_in_the_corner_there_too"]),
    Mutation("a page's tabs look like the filter chips", "vcs/static/style.css",
             ".chip, .tabs a {\n  padding: 6px 14px;", ".chip {\n  padding: 6px 14px;",
             ["tests/test_browser.py::test_a_pages_tabs_look_like_the_filter_chips"], browser=True),
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
    # --- one payment function (plans/PAYMENT_CENTRALIZATION_PLAN.md, decision 0013) ---
    Mutation("only record_payment writes a payment", "vcs/web/blueprints/clinical.py",
             '    _flash_payment_recorded(done, amount)\n    return redirect(url_for("clinical.visit_detail", visit_id=visit_id))',
             '    db.execute("INSERT INTO payments (visit_id, amount, method, date) VALUES (%s,%s,%s,%s)",\n'
             '               (visit_id, amount, method, clock.today()))\n'
             '    _flash_payment_recorded(done, amount)\n    return redirect(url_for("clinical.visit_detail", visit_id=visit_id))',
             ["tests/test_seam_rules.py::test_rule17_only_record_payment_writes_a_payment"], why="seam rule 17"),
    Mutation("a payment locks its bill (the rule)", "vcs/domain/payments.py",
             'f"SELECT id FROM {spec.table} WHERE id=%s FOR UPDATE"', 'f"SELECT id FROM {spec.table} WHERE id=%s"',
             ["tests/test_seam_rules.py::test_every_bill_mutation_takes_the_parent_row_lock"], why="seam rule 1"),
    Mutation("a payment locks its bill (two at once)", "vcs/domain/payments.py",
             'f"SELECT id FROM {spec.table} WHERE id=%s FOR UPDATE"', 'f"SELECT id FROM {spec.table} WHERE id=%s"',
             ["tests/test_payments_shared.py::test_two_simultaneous_payments_cannot_overpay_a_bill",
              "tests/test_concurrency.py::test_two_simultaneous_payments_cannot_overpay_one_visit"], db=True),
    Mutation("a payment's Clean Up stores the bill's new total (the rule)", "vcs/domain/payments.py",
             "        billing.bill_changed(db, kind, bill_id)\n", "        pass\n",
             ["tests/test_seam_rules.py::test_every_write_to_a_bills_inputs_stores_its_new_total"],
             why="seam rule 12"),
    Mutation("a payment's Clean Up stores the bill's new total (the bills)", "vcs/domain/payments.py",
             "        billing.bill_changed(db, kind, bill_id)\n", "        pass\n",
             ["tests/test_payments_shared.py::test_the_stored_total_follows_a_clean_up",
              "tests/test_reports_live.py"], db=True, why="audit B2"),
    Mutation("a member's rate is not changed with a payment", "vcs/domain/payments.py",
             '        if summary["discount_source"] == "member":', "        if False:",
             ["tests/test_payments_shared.py::test_a_members_rate_cannot_be_changed_with_a_payment"], db=True,
             why="the card's discount is the only one a member's bill carries"),
    Mutation("a payment's discount is within the role's cap", "vcs/domain/payments.py",
             "            error = discount_error(staff_discount, discount_cap)\n", "            error = None\n",
             ["tests/test_payments_shared.py::test_a_discount_above_the_roles_cap_is_refused_with_the_payment"],
             db=True),
    Mutation("a visit payment takes no discount", "vcs/web/blueprints/clinical.py",
             '            db, "visit", visit_id, amount=amount, method=method, user_id=session["user_id"],\n'
             '            cleanup_amount=cleanup_amount, notes=f.get("notes"))',
             '            db, "visit", visit_id, amount=amount, method=method, user_id=session["user_id"],\n'
             '            cleanup_amount=cleanup_amount, notes=f.get("notes"),\n'
             '            staff_discount=parse_percent(f.get("discount_percent")), discount_cap=100)',
             ["tests/test_payments_shared.py::test_a_visit_or_inpatient_payment_takes_no_discount"], db=True,
             why="P-2: a visit's discount is its own step, which refuses a non-discountable line"),
    Mutation("a payment plus its Clean Up cannot exceed what is owed", "vcs/domain/payments.py",
             "    owed = balance_with(existing_cleanup + cleanup_amount)\n",
             "    owed = balance_with(existing_cleanup)\n",
             ["tests/test_payments_shared.py::test_a_payment_plus_a_clean_up_cannot_exceed_what_is_owed"], db=True,
             why="P-1: a visit and an inpatient case were overpaid by the Clean Up"),
    Mutation("a payment is checked against the discounted balance", "vcs/domain/payments.py",
             '    if discount != summary["discount_percent"]:\n        pre_cleanup_total',
             '    if False:\n        pre_cleanup_total',
             ["tests/test_payments_shared.py::test_a_payment_is_checked_against_the_discounted_balance",
              "tests/test_money_routes.py::test_boarding_payment_is_checked_against_the_POST_DISCOUNT_balance"],
             db=True, why="apply 10% and pay the undiscounted total"),
    Mutation("an empty amount says the same on every bill", "vcs/web/blueprints/clinical.py",
             '        amount = parse_money(f.get("amount"), required=True)\n    except BadNumber:\n'
             '        return refuse(_("Payment amount must be a valid number."))\n'
             '    # The discount arrives in the SAME submission',
             '        amount = parse_money(f.get("amount")) or 0\n    except BadNumber:\n'
             '        return refuse(_("Payment amount must be a valid number."))\n'
             '    # The discount arrives in the SAME submission',
             ["tests/test_payments_shared.py::test_an_empty_amount_is_refused"], db=True, why="A3"),
    Mutation("a payment of nothing is refused", "vcs/domain/payments.py",
             "    if amount is None or amount <= 0:", "    if False:",
             ["tests/test_payments_shared.py::test_an_amount_that_is_not_a_payment_is_refused"], db=True),
    Mutation("only a cash payment warns about notes", "vcs/domain/payments.py",
             'warn_cash_note=method == "Cash" and not money.is_cash_payable(amount))',
             "warn_cash_note=not money.is_cash_payable(amount))",
             ["tests/test_payments_shared.py::test_a_card_or_transfer_payment_does_not_warn_about_notes"], db=True,
             why="P-6"),
    Mutation("a cash payment not in notes warns", "vcs/web/blueprints/clinical.py",
             "    if done.warn_cash_note:\n", "    if False:\n",
             ["tests/test_payments_shared.py::test_control_a_cash_payment_that_is_not_in_notes_warns"], db=True),
    Mutation("a payment's Clean Up is checked", "vcs/domain/payments.py",
             "    error = cleanup_error(cleanup_amount, existing_cleanup, balance_with(existing_cleanup))\n",
             "    error = None\n",
             ["tests/test_payments_shared.py::test_clean_up_is_capped_across_submissions",
              "tests/test_payments_shared.py::test_clean_up_cannot_exceed_what_is_still_owed"], db=True),
    Mutation("the Clean Up cap counts what is already written off", "vcs/domain/payments.py",
             "    if existing_amount + new_amount > cap:", "    if new_amount > cap:",
             ["tests/test_cleanup_cap.py", "tests/test_payments_shared.py::test_clean_up_is_capped_across_submissions"],
             db=True),
    Mutation("a payment needs one of the three methods", "vcs/domain/payments.py",
             "    if method not in METHODS:", "    if False:",
             ["tests/test_payments_shared.py::test_record_payment_refuses_a_method_the_route_did_not_clean"], db=True,
             why="NULL passes the column's CHECK"),
    Mutation("a payment is dated today", "vcs/domain/payments.py",
             "(bill_id, amount, method, clock.today().isoformat(), user_id, notes)",
             '(bill_id, amount, method, "2020-01-01", user_id, notes)',
             ["tests/test_payments_shared.py::test_a_payment_is_dated_today_whatever_the_form_says"], db=True,
             why="audit B16"),
    Mutation("the updated_at rule reads record_payment's writes", "tests/test_edit_conflicts.py",
             "    return out + _payment_updates()\n", "    return out\n",
             ["tests/test_edit_conflicts.py::test_the_rule_reads_the_payment_functions_writes"],
             why="its UPDATEs name their table from KINDS; a scan of string constants passes without seeing them"),
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
