# IQ vs JO — structural & behavioral comparison

Original baseline: **VetClinicSystem_IQ v1.5.0** (Iraq) vs
**VetClinicSystem_JO v1.1.0** (Jordan), as of 2026-08-23.

> **This header is the ORIGINAL baseline and is deliberately not bumped.**
> This document is append-only dated notes (`CLAUDE.md` §4), so the sections
> below run well past these versions — §26 is dated 2026-08-26, by which
> point the apps were at IQ v1.10.8 / JO v1.8.9. **Never infer the current
> version from this line; read the live `VERSION` file.** An index of every
> section and what it covers is at the very bottom of this file.

IQ is the reference — it's the more tested, more refined codebase, and JO was originally forked from it. This document is organized around **IQ's own module structure** (matching its README), noting for each module how JO differs, what JO is missing, and what's genuinely tailored on purpose vs. what's just drift.

This is a snapshot, not a rulebook — see `CLAUDE.md` in this folder for the standing ground rules on how to act on these differences when adding a feature or fixing a bug. Re-run/extend this comparison whenever either app changes in a way that might affect the other; don't assume it stays accurate indefinitely.

Sources for this pass: direct code comparison (routes, schema, permission decorators, `logic.py`/`auth.py`/`money.py` equivalents) done today, plus three prior investigation documents that shipped as real fixes in JO — `PORTING_CHECKLIST.md`, `IQ_AUDIT_APPLICABILITY_REVIEW.md`, `FULL_SWEEP_FINDINGS.md` (removed from JO's repo 2026-08-23 as stale planning docs now that this file supersedes them) — whose "not yet fixed" claims were re-verified against JO's current code rather than trusted as still true.

---

## 1. Read this first — the differences that touch nearly every module

### 1.1 Money model — the single biggest divergence in the whole codebase

| | IQ | JO |
|---|---|---|
| Currency | IQD — practically a whole-number currency (smallest real note: 250 IQD) | JOD — a genuine 3-decimal currency (fils subunit, in everyday real use) |
| Python type | `float` throughout | `Decimal` throughout (`parse_money()` returns `Decimal`) |
| DB column type | `DOUBLE PRECISION` | `NUMERIC(12,3)` / `NUMERIC(10,3)` / `NUMERIC(5,2)` depending on field |
| Denomination rounding | `money.py` — `round_to_denomination()`, rounds to nearest 250 IQD note, floors on change/refunds | **Does not exist.** No `money.py` in JO at all. Amounts are exact `Decimal` arithmetic, no note-rounding concept |
| JSON serialization | N/A (float is natively JSON-safe) | Custom Flask JSON provider converts `Decimal` → `float` only at the `jsonify()` boundary (Flask's default provider raises `TypeError` on a bare `Decimal`) |

**Ground rule implication:** never port a money-handling diff between these two apps verbatim. `float`/`Decimal` mixing raises `TypeError` immediately in JO (which is what made JO's own currency-conversion sweep reliable) — but it means any IQ money code copied in as-is will either crash or silently do float math where Decimal was intended. Re-derive the fix against whichever app's actual type system you're touching.

One JOD-specific bug this asymmetry already produced and JO already fixed: `compute_bill_totals()`'s `balance <= 0.5` "fully paid" threshold was a no-op safety margin under IQ's 250-denomination rounding (250 IQD's smallest note dwarfs 0.5), but the same literal threshold ported to JOD's exact 3-decimal arithmetic meant "forgive up to half a Dinar of real debt." Fixed in JO to `balance <= 0` (exact). **Watch for this class of bug specifically** — a threshold or rounding constant that was safe under one currency's precision and silently wrong under the other's.

### 1.2 Roles & permissions model

Both apps share the identical ~28-key `auth.PERMISSIONS` list (same keys, same categories: Patients & Visits, Inpatient, Inventory, Sales & Billing, Consignment, Admin) and the identical `roles`/`role_permissions` schema shape. The divergence is in **what's built on top**:

- **IQ**: full custom-role CRUD — `/admin/roles/new`, `/admin/roles/<id>/edit`, `/admin/roles/<id>/delete` — an admin can create an arbitrary role with any subset of permissions and any discount cap, in addition to the 3 seeded defaults (Admin/Vet/Reception).
- ~~**JO**: **no custom-role creation UI or routes at all.** Only the 3 seeded roles exist; `/admin/users/<id>/role` lets you assign a user to one of them, but there's no way to create a 4th role or edit an existing role's permission set from the UI.~~ — **shipped 2026-08-23 (§5 item 2), so this is no longer true.** JO has `admin_role_new`/`admin_role_edit`/`admin_role_delete` and a live "+ Add Role" UI. Flagged here because the stale wording actively misled work later: `audits/ORPHANED_RECORDS_AUDIT.md` scoped finding F-25 as IQ-only on the strength of it, and that had to be caught and corrected against the real code on 2026-08-24 (§6).

**Practical consequence:** until today, JO had ~90 of ~130 routes with no `@auth.permission_required` decorator at all (only login was checked) — a real gap, but not yet *exploitable* in JO specifically, because both non-admin roles (Vet, Reception) are seeded with every non-admin-only permission by default, so nothing was actually being denied that should have been. Fixed today by mapping every JO route 1:1 against IQ's own permission mapping. If JO ever gets custom-role creation, this fix becomes load-bearing rather than defense-in-depth.

**2026-08-23 decision:** it's getting custom-role creation — confirmed as a real gap, not by design, and now in scope for parity with IQ. See §5.

### 1.3 Frontend / design system

- **IQ** has a small custom JS framework: `static/toast.js` (`VZToast` — styled notifications), `ui.js` (`VZDialog` — styled confirm dialogs replacing native `confirm()`), `motion.js`, `progress.js`, `rebuild.js`, and vendors `htmx.min.js`. It also has a `_render_with_progress()` pattern (`templates/_loading_shell.html`) — a background-job-with-polling UI used for anything slow enough to need one: Insights, Retention, Consignment Overview.
- ~~**JO** has none of this. It uses native browser `confirm()`/`alert()` throughout, plain `fetch()` calls with no htmx, and every page (including Insights/Retention/Consignment Overview) renders **synchronously** — no job-polling loading shell exists in JO at all. This was a deliberate choice during porting ("fast enough at Jordan's scale — O(distributors), not O(catalog)"), not an oversight~~ — **2026-08-23 correction: this "deliberate choice" framing was wrong.** Re-confirmed with the user: it was never an intentional decision, just never built. **2026-08-23: the gap itself is now closed** (§5 item 1) — JO has its own `toast.js`/`ui.js`/`motion.js`/`progress.js` (byte-identical to IQ's), and gained the job-polling loading shell for Insights/Retention/Consignment Overview. **2026-08-24: re-confirmed by a full sweep of both apps** (`alert(`/`confirm(`/`prompt(`/`window.confirm`/`window.alert`/`hx-confirm` across every template and static JS file, both apps) — zero native browser dialogs remain in either app's own code; the only matches anywhere are inside the vendored, unused `htmx.min.js` and in code comments describing the old behavior being replaced. Both apps now consistently route every user-facing message through `VZToast`/`VZDialog`, not just for the routes ported in the 2026-08-23 pass. No code changes were needed — this was a confirmation pass, not a fix.

**2026-08-24: sidebar collapsible groups — gap closed, JO now matches IQ.** The 2026-08-23 framework port brought `ui.js` across byte-identical, which meant JO had been carrying a fully working `initCollapsibleGroups()` (correct `vetclinicsystemjo-navgroup-*` localStorage prefix and all) that nothing in JO's markup ever activated — the function ran on every page and found zero `.nav-group[data-collapsible]` elements. Only the CSS block and the markup were missing. Both added: JO's `static/style.css` gained the same `.nav-group-toggle`/`.chevron`/`.nav-group.collapsed` rules (using JO's own `--sidebar-muted` token, so it themes itself), and `templates/base.html`'s Inventory / Consignment / Sales & Billing / Admin groups became collapsible — **the same four IQ collapses, with Dashboard, Patients & Visits and Inpatient deliberately left always-expanded in both**. JO's own permission-gating inside each group was left exactly as written rather than reshaped to match IQ's `{% set x_perms %}` idiom, per this section's own ground rule. Verified live in JO's isolated test environment: all four groups toggle, state persists across navigation via localStorage under the JO-prefixed key, chevrons rotate, and the toggle picks up the right themed colour in dark mode.

**Ground rule implication:** ~~don't port a UI/JS feature by copying IQ's toast/dialog/progress-shell code into JO — JO has its own simpler conventions (`alert()`, plain modals with `display:flex`/`none` toggling, no toast system) and every prior port deliberately matched those conventions rather than importing IQ's framework.~~ **2026-08-23: superseded for this specific feature** — porting IQ's toast/dialog/progress-shell framework into JO is now an active parity project (§5), not something to avoid. This ground rule still holds for every *other* UI convention difference — don't casually reshape JO's simpler modals/forms to match IQ's beyond what the toast/dialog/progress-shell port itself requires. The reverse also still holds: don't simplify IQ's UI to match JO's without being asked.

### 1.4 Self-update mechanism

Both apps have the **same** in-app updater as of JO v1.0.0 (`updater.py`, `jobs.py`, `/health`, `setup.py --enable-updates`, Settings → Check for Updates/Update Now/Rollback), pulling tagged GitHub Releases from their own respective repos (`aldbabiomar/vetclinicsystem_iq` / `aldbabiomar/vetclinicsystem_jo`). This part is genuinely at parity and should be kept that way — see `RELEASE_WORKFLOW.md`.

Two small file-level differences remain:
- IQ has `autostart.py` (OS-level launch-on-boot registration) and `reconcile_attachments.py` (a standalone maintenance script). **JO has neither.** Not flagged as a bug anywhere in JO's own investigation history — just never built. ~~Worth a deliberate decision if JO ever wants launch-on-boot or an attachment-reconciliation tool, not an oversight to silently fix.~~ **2026-08-23 decision: yes to both** — confirmed not by design, now in scope for parity with IQ. See §5.
- `attachments.py`'s `UPLOAD_ROOT` and `app.py`'s `ERROR_LOG_PATH` resolving against `*_DATA_DIR` under the versioned-release layout: **JO got this right from the start** when it ported the updater; IQ had (per this session's memory) a gap here that was flagged separately and should be double-checked as fixed in IQ's current code before relying on it. (Resolved a few sections later, same pass — see §4: checked directly, IQ and JO are at parity here. Leaving this note as-is rather than deleting it, since §4 is the actual resolution and this is just where the question first got raised.)

### 1.5 Security & robustness posture

As of today, these are **at parity** — both apps independently converged on the same fixes (IQ via `AUDIT_FINDINGS.md` + today's `QA_RESULTS.md` work; JO via its own `IQ_AUDIT_APPLICABILITY_REVIEW.md` → `FULL_SWEEP_FINDINGS.md` → v1.0.3, plus today's QA port + permission-gate fix):

- Escalating account lockout (not sliding), `password_changed_at`-based session invalidation, `session.clear()` at login, `logout` exempted from the forced-password-change gate
- Per-IP login rate limiting
- Baseline CSP header, `X-Content-Type-Options`/`X-Frame-Options`/`Referrer-Policy`
- Backup dump files `chmod 0600`
- Updater tarball extraction uses `filter="data"`
- Oversized `?page=` clamped, null byte in path/query/form rejected with a clean 400 (JO's guard is actually written slightly differently — checks decoded `request.args` directly rather than raw `request.query_string` bytes — but achieves the same coverage IQ's now does after today's fix)
- POS/refund/payment/consignment/cash-register overpayment and below-total caps, all row-locked
- POS oversell race (row lock + now microsecond-precision timestamps), duplicate-owner creation, double-charge-via-double-click, DB-outage raw error page — all fixed in both today

~~One asymmetry still open, JO-specific, not yet raised to the user: `backup.py`'s dump-staging implementation differs structurally enough from IQ's (writes directly via `pg_dump -f` vs. IQ's `/tmp/<basename>` staging path) that IQ's specific symlink-race concern (if IQ has one — not independently re-verified this pass) doesn't transfer as-written. Flagged for a dedicated look if backup security is ever audited again, not assumed safe or unsafe.~~ — **2026-08-23 correction: this was wrong.** Read both apps' current `backup.py` in full: `_run_pg_dump()` is byte-for-byte the same pattern in both — local `pg_dump -f out_path` writes directly to the destination, no `/tmp` staging anywhere in the *backup* path in either app. The `/tmp/<basename>` staging that does exist is in `_run_pg_restore()`'s Docker fallback (`docker cp` the dump into the container before running `pg_restore` inside it, since `docker exec` can't read a file straight off the host) — also identical in both apps, since JO's restore was ported from IQ's this session. The earlier note conflated the restore-side Docker staging with the backup-side dump-writing and flagged a difference that doesn't exist. The one real (harmless) difference: IQ applies `os.chmod(0o600)` once in `_run_backup_locked()` right after `_run_pg_dump()` returns; JO applies it inside `_run_pg_dump()` itself at each return point. Same resulting permissions either way, just organized differently — not a security-relevant asymmetry.

### 1.6 Form data loss on validation failure — fixed in both, 2026-08-24

A user reported a QoL bug: filling in a multi-field form (e.g. Log Visit →
New Patient), making one mistake (an invalid phone number, a bad date),
and submitting lost every other field they'd typed — the server flashed
an error and redirected to a blank form. Investigation found this was
systemic: ~60 `except Bad*` (`BadDate`/`BadNumber`/`BadPhone`) sites per
app, almost all `flash(msg); return redirect(...)` on failure, discarding
`request.form` entirely. A related, more serious bug rode along with it:
`visit_new_patient()` in both apps committed the owner+patient rows
*before* the visit's own fields were validated, so a later validation
failure left a permanently orphaned owner+patient, and retrying created a
duplicate patient.

Fixed in both apps, same pattern, implemented separately per app per
CLAUDE.md §1 (not copy-pasted — each app's actual field names/route
structure/money type were read fresh):

- **Ordering fix**: `visit_new_patient()` now validates the visit's
  date/weight/bcs (via a new `_parse_visit_fields()`/pure-validation
  helper) *before* the owner+patient commit, in both apps.
- **Client-side phone validation**: new `static/phone-validate.js` per
  app (exact JS port of each app's own `normalize_phone()` — different
  country code/length per app, not shared) flags an invalid phone inline
  on blur, before submit, on all 4 phone fields per app (owner form,
  visit-log-new-patient, distributor new/edit).
- **Server-side redisplay**: a new `fv(form, name, default)` Jinja global
  in each app's `app.py` looks up a field's just-submitted value on a
  validation-failure redisplay, falling back to the existing DB value (or
  blank) otherwise. ~35 routes per app converted from `redirect` to
  `render_template(..., form=f)` on their `except Bad*` paths — every
  multi-field creation/edit form across visits, owners, distributors,
  boarding, appointments, inpatient, billing/discount/payment panels,
  price list, inventory catalog, audit sessions, reports opex. A handful
  of JS-built dynamic-cart forms (POS checkout, visit billing's Automatic
  item cart) deliberately keep only their top-level fields (not full cart
  contents) — restoring a JS cart's line items server-side was judged
  disproportionate effort for this pass, noted inline in each route.

One real regression caught during verification, JO only: an agent-drafted
`inpatient_payment_add()` called `_inpatient_detail_context(case_id)` — a
helper that was never actually defined anywhere in the file, since JO's
`inpatient_detail()` GET route had never been factored into one (IQ's
had). Any payment validation failure would have thrown `NameError` — a
crash, worse than the original bug — until caught by live curl testing
and fixed by adding the missing helper (mirroring IQ's own factoring).
Serves as a concrete instance of why CLAUDE.md §2's "verify live, don't
trust from inspection alone" discipline exists.

Verified live in both apps' isolated test environments: all ~14
directly-authored routes tested via curl (bad-value POST → 200 direct
render with every other field preserved verbatim + correct error message;
good-value POST → succeeds, DB state correct, JOD 3-decimal precision
intact in JO) plus a spot-check of ~8 agent-authored routes (boarding,
appointments, distributor bills/payments, refunds, consignment, POS) for
crashes. Zero errors in either app's error log across the full test pass.

---

## 2. Module-by-module

For each module: what routes/permission exist in each app, and any schema or behavior difference. Modules with no meaningful difference beyond the money-model note above are marked accordingly rather than repeating it.

### Dashboard
Parity, including the missed-items panel's sort order. Same permission-based (not role-name-literal) gating and alert composition (patients, active cases, follow-ups, wellness, grooming queue, low stock, audit/expiry alerts) in both. ~~Same missed-items panel~~ — **2026-08-23 correction: was not quite true at the time.** `missed_items()` diverged on ordering: IQ (`logic.py:823-833`) did an explicit final sort of the combined list by deadline, newest-first; JO (`logic.py:791-812`) had no equivalent final sort, plus the underlying `followups()` helper each app calls sorted in opposite directions (IQ `reverse=True` newest-first vs. JO ascending oldest-first). **2026-08-23, fixed:** ported IQ's sort behavior into JO's `logic.py` — `followups()` now sorts `reverse=True` with a `date.min` fallback (was ascending with `date.max`), and `missed_items()` gained the same final `_deadline_key`-based `reverse=True` sort IQ already had. `dashboard_snapshot()`'s `due_today`/`reminders_tomorrow` (also built from `followups()`, identical structure in both apps) inherit the same fix, so it's not just `missed_items()` that's now aligned. Verified live in JO's isolated test environment: seeded three visits with distinct missed follow-up deadlines directly against the real `logic.py` functions on a live DB connection — `followups()` and `missed_items()` both now return newest-deadline-first, matching IQ. Test data removed, environment torn down after.

### Owners & Patients
Parity in routes and behavior, including today's fix (owner dedup by phone, `idx_owners_phone_unique`). Phone normalization differs by design: `PHONE_COUNTRY_CODE`/`PHONE_LOCAL_LENGTH` are `"964"`/10 in IQ, `"962"`/9 in JO (Jordan mobile numbers are 9 digits after the trunk 0).

### Visits
Parity in routes, case-status vocabulary, and today's fix (new-patient form linking to an existing owner on phone match). `_create_visit()`'s error handling differs cosmetically (JO handles `BadDate`/`BadNumber` inline with its own flash+redirect; IQ raises and lets the caller handle it) — not a behavior difference, just a refactor difference worth knowing before diffing the two functions naively.

### Follow-ups / Wellness / Grooming
Parity. Both paginate at the SQL level (JO's B-6 port), both sort newest-first, both have the N/A follow-up status option.

### Inpatient
Parity, including a `?view=balance_due` filter on the inpatient list (any discharged case with an unpaid balance, regardless of discharge date). ~~JO's own addition — IQ doesn't have this view. Worth checking whether IQ wants it too, or whether it's Jordan-specific.~~ — **2026-08-23 correction: wrong, IQ already has it.** Checked IQ's current code directly: `app.py:4359-4391`'s `inpatient_list()` has the identical `view=balance_due` branch and paid-join SQL, and `templates/inpatient_list.html:12` has the same "Balance Due" chip — byte-for-byte the same logic as JO's (`app.py:4277-4309`, `templates/inpatient_list.html:11`). This is parity, not a JO-only feature; the earlier claim was never re-checked against IQ's actual code.

### Boarding
Parity. Both lock-after-pickup, both compute totals live while active (nights × price/day) rather than trusting a stale stored total, both cap payments against the live balance with a row lock.

### Appointments
Parity, including the DB-level unique index (not just a check-then-insert race), forced-null `resource_id` for grooming bookings, and the "needs attention" orphaned-appointment fallback list (a vet deactivated or a slot invalidated by a schedule change). Both warn on the settings/user-toggle pages that would orphan existing bookings.

### Point of Sale
Parity in routes and today's fixes (idempotency key, microsecond-precision stock-race fix). Behavior differs by currency model only: JO has no Cash Received/Change Due "round to nearest note" step — change is exact `Decimal` subtraction; the receipt/cart-preview JS shows 3 decimals in JO vs whole numbers in IQ.

### Inventory (Price List, Inventory Catalog, Audit History, Barcodes)
Mostly parity, with real feature gaps in JO:
- **Manual barcode entry** (`inventory_catalog_barcode_manual`/`_generate`/`_remove`/`_status`, a `barcode_source` column distinguishing manual vs. generated) — **IQ only.** JO has a single `create-barcode` route; every barcode is machine-generated, no manual-entry path, no `barcode_source` concept. **2026-08-23 decision:** confirmed not by design, now in scope for parity with IQ. See §5.
- **Bulk barcode printing** — parity. ~~JO's implementation renders `JsBarcode` inline per label rather than using IQ's `vzRenderBarcode()`/`barcode-render.js` wrapper (JO doesn't have that file) — same feature, different rendering mechanism, matches JO's no-shared-JS-framework convention from §1.3.~~ — **2026-08-23: stale, superseded by §5 item 6.** `barcode-render.js` was ported into JO as part of manual-barcode-entry work, and `templates/barcode_bulk_print.html` was updated at the same time to call `vzRenderBarcode(svg, svg.dataset.code)` — confirmed both apps' current templates use the identical wrapper call. Now parity in mechanism too, not just outcome.
- Both use `_txn_qty_since_batch()`'s batched, timestamp-based (not date-only) stock-since-audit calculation — today's microsecond-precision fix applies identically to both.

### Distributors & Consignment
Parity in routes, schema, and business logic (row-locked overpay/shortfall guards, settlement residual carry-forward, item-lock-on-any-past-sale fix, `consignment_since` floor). The only difference is JO's Consignment Overview page rendering synchronously instead of via the background-job loading shell (§1.3) — same data, same correctness, just no progress UI while it computes.

### Billing
Parity in structure (Automatic priced line-items vs. Manual lump amount, snapshotted at save time via `visit_billing_lines`/cached totals). Rounding differs per §1.1 — IQ's `round_to_denomination()` step doesn't exist in JO's `compute_bill_totals()`.

### Refunds
Parity, including the discount-adjusted-price refund fix (refund at the price actually charged, not today's Price List price) and the sale-linked/remaining-quantity cap via `refundable_sale_items()`.

### Cash Register
Parity in routes and ledger logic. ~~JO's "Cash Register Health" section on Insights reuses JO's existing pooled-connection `jobs` dict (Phase A.2 infra) rather than IQ's separate `_render_with_progress`/`as_completed` runner — same result, different plumbing, per §1.3.~~ — **2026-08-23: stale, superseded by §5 item 1.** JO's `insights()` now wraps `cash_register_health` as one job in the same `job_defs`/`ThreadPoolExecutor`/`as_completed` list run through `_render_with_progress()`, line-for-line the same pattern as IQ's `insights()` — confirmed against both apps' current `app.py`. Same plumbing now, not just same result.

### Reports / P&L / Insights / Retention
Parity in what's computed (revenue by category, vet performance, client value, weekday load, occupancy, payment mix, cash register health, cohort retention). ~~Rendering differs per §1.3 — IQ backgrounds these behind a progress UI; JO renders them synchronously inline. Worth revisiting if JO's dataset ever grows enough to make that noticeably slow.~~ — **2026-08-23: stale, superseded by §5 item 1.** JO's `insights()` and `retention()` now both call `_render_with_progress(...)`, same as IQ's `insights()` — confirmed against both apps' current `app.py`. Now parity in rendering too, not just computation.

### Logins and Changes (audit trail)
Parity. Both fixed the same historical bug class (audit log no longer self-commits ahead of its own mutation; payment-audit logs the payment's own id, not the parent visit/case/boarding id).

### Settings
Real feature gaps, all in JO (JO is missing, not IQ):
- **In-app database restore** — IQ has `/settings/restore-now` and a documented `pg_restore` fallback. ~~**JO has no restore feature at all** — backup only, restore is manual-only, undocumented as a UI action. (This also means IQ's audit finding about restore-path validation genuinely doesn't apply to JO — there's no restore endpoint to have the bug.)~~ **2026-08-23 decision:** in scope for parity with IQ — **and shipped the same day** (§5 item 3). JO now has `/settings/restore-now` with the same provenance check and progress UI as IQ, so the restore-path validation finding *does* apply to it and was applied.
- **Backup-folder browser** — IQ has `/api/browse-folder` + `/api/browse-folder/new-folder`, an in-app filesystem browser for picking the backup destination. **JO's equivalent field is a plain text input** — no browse UI, no folder-creation-from-the-app. **2026-08-23 decision:** in scope for parity with IQ. See §5.
- **Autostart toggle** — `/settings/autostart` exists in IQ only (ties to `autostart.py`, §1.4). **2026-08-23 decision:** in scope for parity with IQ. See §5.
- **Color palette / clinic branding** — IQ has a multi-palette theming system (`theme_palette` setting, ChamPet-branded asset variants across every logo/favicon/error-page image). **JO has one fixed *palette*** — single favicon/logo set, no palette switcher, no `-champet` asset variants. **2026-08-23: explicitly left out of the current parity round**, and still is. ~~JO keeps its single fixed look for now~~ — **but note the narrower wording as of 2026-08-24:** it is the per-clinic *branding* axis that stays IQ-only. JO gained light/dark theming in §12, so "one fixed look" is no longer accurate as written.

Both apps share: clinic name/location settings, numeric thresholds (audit-overdue days, expiry-soon days, appointment slot length), nightly backup folder/time/retention, and the self-update section (§1.4).

---

## 3. Feature inventory — what exists in one app but not the other

**IQ-only:** — ⚠️ **most of this list went out of date on 2026-08-23; corrected below rather than rewritten, per §4's own rule.**
- ~~Custom role creation/editing (§1.2)~~ — **in both since 2026-08-23** (§5 item 2)
- ~~Manual barcode entry (Inventory)~~ — **in both since 2026-08-23** (§5 item 6)
- ~~In-app backup restore, backup-folder browser, autostart toggle (Settings)~~ — **all three in both since 2026-08-23** (§5 items 3–5)
- Multi-palette theming/branding — **still IQ-only, and still a deliberate divergence.** Note this is the *palette* axis only: light/dark is now in both apps (§12).
- ~~`autostart.py`, `reconcile_attachments.py`, `money.py`~~ — **only `money.py` is still IQ-only** (the genuine currency-model divergence, §1.1). JO gained `autostart.py` on 2026-08-23 (§5 item 5) and `reconcile_attachments.py` the same day (§5 item 7).
- ~~Background-job progress UI (`_render_with_progress`, `_loading_shell.html`) and its consumers (Insights, Retention, Consignment Overview all block synchronously in JO instead)~~ — **in both since 2026-08-23** (§5 item 1)
- ~~`VZToast`/`VZDialog` JS framework, htmx~~ — **in both since 2026-08-23** (§5 item 1)
- `--accent-alt` (the shared chart/grooming accent, §9) — IQ-only, because it only exists to be distinguishable across IQ's four palettes

**JO-only:**
- Inpatient `?view=balance_due` filter
- ~~`generate_test_data.py` (a synthetic large-dataset generator, used to stress-test the Decimal conversion and billing-snapshot work — no IQ equivalent found)~~ — **removed from JO's repo 2026-08-23** at the user's request, its one-time stress-testing purpose already served.
- `tests/test_no_raw_form_dates.py` — an actual automated test. ~~**IQ has no `tests/` directory or automated tests at all.**~~ — **no longer true as of 2026-08-24:** IQ gained its first `tests/` directory with `test_desktop_shortcut_target.py` (§7), which JO has too. `test_no_raw_form_dates.py` itself is still JO-only.

---

## 4. Known still-open items (neither app, as of this pass)

> **Status 2026-08-24: everything originally listed here is closed** — all
> three items below are struck through and resolved. Kept rather than deleted
> because the resolutions record *why* two of them were never real problems in
> the first place. **The genuinely open items now live in §18**, not here; this
> section is history.

- ~~`backup.py`'s dump-staging path difference (§1.5) — not confirmed safe or unsafe in either direction, just not re-verified this pass.~~ — **resolved 2026-08-23, it wasn't real.** See §1.5's correction: both apps' dump-writing code is identical; no staging-path asymmetry exists.
- ~~IQ's `_render_with_progress` pattern doesn't exist in JO; if JO's data volume ever makes Insights/Retention/Consignment Overview noticeably slow, building that infrastructure (or a lighter version of it) is a real, not-yet-scoped project.~~ — **resolved 2026-08-23, §5 item 1.** JO now has `_render_with_progress()` and uses it to wrap `/consignment`, `/insights`, and `/retention`, identically to IQ.
- ~~Whether IQ's `attachments.py`/`ERROR_LOG_PATH` `*_DATA_DIR` resolution has been fixed~~ — **confirmed fixed**, checked directly this pass: both `attachments.py`'s `UPLOAD_ROOT` and `app.py`'s `ERROR_LOG_PATH` resolve against `VETCLINICSYSTEMIQ_DATA_DIR` when set. IQ and JO are at parity on this.

---

## 5. Planned parity work (JO catching up to IQ) — decided 2026-08-23

Every item below was reviewed with the user and confirmed as a real gap —
**not** a deliberate design divergence — so JO is getting each one ported
from IQ, one at a time, each going through `CLAUDE.md` §2's full checklist
(diff current code in both apps, verify money/currency implications don't
apply, build and verify live in JO's isolated test environment, re-verify
against JO's actual 3-fixed-role permission model, tear down). This
section itself is the definition of scope — update the item's status
inline (`done, 2026-XX-XX`, with a note on what actually shipped) as each
one lands, rather than deleting the line.

In planned order:

1. **`VZToast`/`VZDialog`/htmx + background-job progress UI framework**
   (§1.3) — starting point; other items below may end up depending on it
   for consistent UI (e.g. the restore/folder-browser flows). Corrects the
   earlier "deliberate choice" framing in §1.3, which was wrong.
   **Done, 2026-08-23.**
2. **Custom role creation & editing** (§1.2) — full role CRUD ported from
   IQ's `/admin/roles/*` routes. Once this lands, JO's today-fixed
   permission-decorator coverage (§1.2) stops being defense-in-depth and
   becomes load-bearing. **Done, 2026-08-23.**
3. **In-app backup restore** (§2 Settings) — a real `/settings/restore-now`
   flow for JO, matching IQ, replacing manual-only `pg_restore`.
   **Done, 2026-08-23** — built after item 4 below (swapped order; see the
   note preceding item 4's writeup).
4. **Backup-folder browser** (§2 Settings) — in-app filesystem browser
   for the backup destination, replacing JO's plain text field.
   **Done, 2026-08-23** — built before item 3, since item 3's file picker
   depends on it.
5. **Autostart toggle** (§1.4, §2 Settings) — port `autostart.py` +
   `/settings/autostart`. **Done, 2026-08-23.**
6. **Manual barcode entry** (§2 Inventory) — add JO's missing manual-entry
   path and `barcode_source` column alongside its existing
   machine-generated-only route. **Done, 2026-08-23.**
7. **`reconcile_attachments.py`** (§1.4) — port IQ's standalone
   attachment-reconciliation maintenance script. **Done, 2026-08-23.**

**Item 1 — done, 2026-08-23.** Ported `VZToast`/`VZDialog`/`VZSpring`/
`VZProgress` into JO: new `static/toast.js`, `motion.js`, `progress.js`,
`ui.js` (byte-identical to IQ except the localStorage key prefix),
`static/vendor/htmx.min.js` (vendored + wired, still unused in either app —
ported for parity, not because anything uses it), matching CSS additions to
`static/style.css` (JO's own token values apply automatically — no color
mapping needed), `templates/_loading_shell.html`, and `_render_with_progress()`
+ a new generic `/jobs/status` route in `app.py` (JO's existing
`/settings/job-status` was left untouched — separate route, same pattern
IQ itself uses). `/consignment`, `/insights`, and `/retention` now go
through the loading-shell/job-progress pattern, matching IQ exactly. All
~29 `confirm()`/`alert()` call sites across templates and
`unsaved-changes.js` converted to `data-confirm`/`VZDialog.confirm()`/
`VZToast.show()`. Verified live in JO's isolated test environment: toast
(flash-conversion and validation toasts), styled confirm dialog (Price
List delete, and Settings Update/Rollback code path — inactive in the
test env since it isn't on the versioned-release layout, but reviewed),
all three progress-wrapped pages (including the direct-reload fallback
path), and the existing `#addModal`-style modals still open/close
correctly (confirming the `.modal-overlay { opacity: 0 }` CSS exclusion
was the right call). Zero new console errors across every page touched.
One pre-existing, unrelated stale process from `~/.Trash/VetClinicSystem_JO`
was found squatting on port 5092 during setup and killed — unconnected to
this app or this change.

**Item 2 — done, 2026-08-23.** Ported full custom role creation/editing
into JO: `_active_admin_count()`/`_role_or_404()` helpers, `admin_users()`
rewritten to build `perm_categories`/`role_perms`/`staff_counts` (matching
IQ), and the three new routes `admin_role_new`/`admin_role_edit`/
`admin_role_delete`, copied verbatim from IQ's already-audited
implementation (same uniqueness/cap-range/`is_system`-protection guards,
same reassign-before-delete flow). Added `auth.PERMISSION_CATEGORIES`
(JO's `PERMISSIONS` list was already byte-identical to IQ's — only the
category-grouping constant was missing). `templates/admin_users.html`
rewritten to IQ's tabbed Staff / Roles & Permissions layout, using the
`VZDialog`/`data-open-modal`/`data-confirm` primitives item 1 landed;
matching CSS block ported to `static/style.css`. Nav label "Users" →
"Users & Roles" in `base.html`.

Two things surfaced and fixed as direct, in-scope consequences of enabling
custom roles, not scope creep:
- JO's `admin_user_toggle`/`admin_user_role` guards only protected against
  *self*-demotion/disable of the last Admin (string-compared on
  `role_name == "Admin"`), because until now only Admins could reasonably
  hold `manage_users_roles`. Once an arbitrary custom role can be granted
  that permission, a non-Admin holder could disable or reassign *someone
  else's* last-Admin account with no self-check to stop them. Upgraded
  both routes to IQ's `_active_admin_count(db) <= 1` + `is_system`-based
  guards, which protect the invariant regardless of who's acting. Verified
  live: demoting/disabling the sole remaining Admin is blocked; the same
  action succeeds once a second Admin exists.
- JO's Settings page had 3 hardcoded `discount_cap_admin/vet/reception`
  fields writing straight to those roles' `discount_cap` by name — the
  same responsibility the new role-edit form now owns generically for any
  role. Confirmed IQ removed the equivalent fields when it added role
  editing (grepped IQ's `settings.html`/`app.py` — zero matches), so
  removed JO's copy the same way rather than leaving two places that edit
  the same value.
- Also ported IQ's per-user `custom_discount_cap` override (New User
  modal's inherit-vs-custom radio) — JO's schema and `discount_cap_for()`
  session logic already fully supported it, just missing the admin UI to
  set it; leaving it out would have meant deliberately not matching IQ's
  actual New User modal while rewriting that exact template.

Verified live in JO's isolated test environment: create/edit/delete a
custom role (including permission-grid and discount-cap changes
persisting correctly); Admin role's edit/delete blocked server-side even
via a direct POST bypassing the disabled UI; deleting a role with
assigned staff blocked without a `reassign_to` target, succeeds and moves
staff once one is given; last-active-Admin disable/reassign guards
verified both ways (blocked at 1 active Admin, allowed at 2); custom
per-user discount override create-and-display round-trip. Zero console
errors. `down jo` left one process still bound to port 5092 under a PID
that didn't match the one `up` printed (cwd confirmed it was this same
test run, not unrelated) — killed directly; worth a look if `up`/`down`'s
PID tracking does this again.

**Order note:** items 3 and 4 were swapped from the original plan.
IQ's restore file-picker reuses the same `/api/browse-folder` endpoint and
modal as the Backup Folder picker — building restore first would have
meant a placeholder file-path input, then redoing it once the browser
landed. Did the folder/file browser (originally item 4) first, then
restore (item 3) on top of it, so restore only needed to be built once.

**Item 4 — done, 2026-08-23.** Ported the server-side folder/file browser:
`GET /api/browse-folder` (lists subfolders, and matching files when
`?ext=` is given, of a path on the server's own filesystem — deliberately
server-side, not a browser file input, since `pg_dump`/`pg_restore` run on
the server) and `POST /api/browse-folder/new-folder`, both gated on
`manage_settings`, copied verbatim from IQ. Added the shared
`folderBrowserModal` + JS (`openFolderBrowser`/`loadFolderBrowser`/
`folderBrowserSelect(File)`/`folderBrowserNewFolder`) to
`templates/settings.html`, wired to the existing Backup Folder field (a
`--paper-alt`-styled path readout in IQ was mapped to JO's real
`--muted-tint` token instead, since `--paper-alt` turned out to be
undefined in IQ too — always falling back to a literal hex — not an
intentional token JO needed to add). `folderBrowserSelectFile()` already
carries the restore-specific branch (checks for `restoreFileInput`) per
IQ's own single-function design; harmless dead code until item 3 landed
moments later in the same session. Verified live: navigating into a real
subfolder, creating a new folder through the modal, and selecting it
populates the target field with the correct absolute path.

**Item 3 — done, 2026-08-23.** Ported in-app database restore:
`backup.resolve_restorable_backup()` (path-confinement + provenance
safety gate — a restore source must resolve inside the configured
`backup_dir` AND be recorded in `backup_log` with `status='success'`,
closing the arbitrary-file-path hole a bare folder browser would
otherwise open), `run_restore()`/`_run_restore_locked()`/`_run_pg_restore()`
(+ TOC-count/streamed-progress helpers), `_try_log_restore()`, and
`recent_restores()` — all copied from IQ, adapted in two places that
actually differ between the apps (see below). New `restore_log` table
(IQ's schema, added directly to `schema_postgres.sql` — JO's `apply_schema()`
re-runs the whole file idempotently on every launch, so existing installs
pick up a brand-new table with no separate migration entry needed, unlike
a column added to an existing table). New `/settings/restore-now` route
(same request-connection-release + pool-close sequence as IQ, needed
because `pg_restore --clean` drops every table including ones the
in-flight request already holds a read lock on) and a `kind=restore`
branch on `/settings/job-status` that clears the polling browser's
session on success. Settings template gained the Restore From Backup
section, Recent Restores table, and an async submit handler (POSTs,
gets a `job_id`, polls via `VZProgress` — added `progress.js` to
`settings.html` for this, since JO's existing Update/Rollback flow uses
its own hand-rolled `runUpdateJob()` text panel, not `VZProgress`).

Two real divergences caught by diffing JO's actual code instead of
assuming symmetry with IQ (per `CLAUDE.md` §2):
- IQ's `_run_restore_locked()` calls `setup.apply_schema()` *and*
  `setup.apply_incremental_migrations()` as two independent top-level
  calls. JO's `apply_schema()` already calls
  `apply_incremental_migrations(con)` internally as its last step — and
  JO's version of that function requires a connection argument IQ's
  zero-arg version doesn't take. Calling both separately in JO would have
  been redundant at best and a `TypeError` at worst. Restore calls only
  `setup.apply_schema()`.
- IQ's `run_backup()`/`run_restore()` both self-acquire `maintenance_lock`
  internally. JO's existing `run_backup()` doesn't — its caller
  (`settings_backup_now()`) acquires the lock at the route level instead,
  since that call is synchronous within one request. Restore can't follow
  that pattern: it runs inside a background job (`jobs.start()`), and the
  request that starts it returns almost immediately, long before the
  actual `pg_restore` finishes — so `run_restore()` acquires the lock
  itself, inside the code that actually executes in the background
  thread. `run_backup()` was left untouched.

Verified live end-to-end in JO's isolated test environment: real Back Up
Now (see below for a test-environment-only wrinkle this surfaced), then
changed a setting, then restored from the pre-change backup and confirmed
the change was actually reverted — not just a success response. Both
safety guards confirmed via direct POST: a path outside `backup_dir`
blocked ("isn't inside the configured backup folder"), and a real `.dump`
file placed inside `backup_dir` but never logged as a successful backup
blocked separately ("isn't in this app's own backup history"). Confirmed
the `data-confirm` dialog shows the exact right warning, the progress
panel runs, and — the important one — `session.clear()` + redirect to
`/login` actually fires on success. Recent Restores table shows the
logged entry. Zero new console errors (one stale error in the console
buffer traced to my own test scaffolding calling `.json()` on a
redirect-followed HTML response, not app code).

Two things found and fixed as test-environment friction, not app bugs:
- Local `pg_dump`/`pg_restore` need `PGPASSWORD` (or `.pgpass`) to
  authenticate against the isolated test container — JO's
  `_pg_conn_parts()`/`_run_pg_dump()` (pre-existing, untouched by this
  port) extract user/db/host/port from `DATABASE_URL` but never extract
  the password for the subprocess env. The app itself connects fine
  (psycopg parses the full URL), but a local `pg_dump` binary on PATH
  doesn't inherit it. Worked around for testing by launching the test app
  with `PGPASSWORD` exported; not fixed in `backup.py` since it's
  unrelated to restore and pre-dates this session. Worth a dedicated look
  if backup ever gets audited — it would presumably hit the same wall on
  a real install with a password-protected local Postgres and no
  `.pgpass` configured, not just this sandbox.
- Two more unrelated stale processes were found and killed this session:
  one from `~/.Trash/VetClinicSystem_JO` squatting on port 5092 again,
  and one from `~/.Trash/VetClinicSystem_IQ` squatting on port 5091 (IQ's
  isolated-test port) for nearly 4 hours. Both were orphaned (`PPID 1`,
  `cwd` inside `~/.Trash`), unconnected to any work in this session.

**Item 5 — done, 2026-08-23.** Ported the autostart toggle: new
`autostart.py` (macOS: a per-user LaunchAgent plist in
`~/Library/LaunchAgents`, loaded via `launchctl`; Windows: a `.bat` in the
current user's Startup folder; unsupported elsewhere) — a verbatim port of
IQ's already-shipped module, retargeted to JO's app name/launcher
filenames (`com.vetclinicsystemjo.autostart`, `Start VetClinicSystem
JO.command`/`.bat`, confirmed those exact filenames exist at JO's repo
root). New `/settings/autostart` route and `autostart_supported`/
`autostart_enabled` context on `settings_page()`'s GET branch, both
matching IQ exactly. New "Startup & Shutdown" section in
`templates/settings.html` — a single checkbox, its own standalone form
(deliberately separate from the tracked-changes settings form above it,
so toggling it doesn't trip that form's unsaved-changes guard), submitting
immediately on change via `requestSubmit()`, no `data-confirm`/`VZDialog`
(matches IQ — this toggle applies immediately, no confirmation prompt).

One thing caught, not copy-pasted through: IQ's help text under the
checkbox claims a final backup gets taken on shutdown. Checked JO's own
`_graceful_shutdown()` (`app.py`) before shipping that line — it only
closes the DB connection pool and exits; **it does not take a backup**,
unlike IQ's version, which explicitly does (`backup_mod.run_backup(db,
triggered_by="shutdown")`). Copying IQ's text as-is would have been
inaccurate for JO. Reworded to describe what JO's shutdown handler
actually does (closes connections cleanly) instead. **Flagging this as a
newly-discovered, real feature gap** — ~~JO has no shutdown-triggered
backup safety net at all — separate from and not fixed by this port;
worth its own decision later, not silently added here.~~ — **closed
2026-08-24 on request, see §17.** Porting it also surfaced that JO's
`backup_log` had no `triggered_by` column at all, so no JO backup of any
kind had ever recorded what started it.

Verification note: `autostart.enable()` writes a real macOS LaunchAgent
plist and runs `launchctl load` against the actual machine — a genuine
OS-level system-settings change, not something confined to the isolated
test container the way every other port this session was. Per the
standing rule against modifying system/security settings, did not
invoke the real `enable()` path even inside the test env (that constraint
isn't about the sandbox, it's about not making real system changes
autonomously) or ask the user to confirm doing so, and it wasn't needed:
verified live instead that the Settings page correctly reads real
`is_supported()`/`is_enabled()` state (checkbox unchecked, enabled,
correct help text, confirmed no plist exists on disk), and exercised the
one code path with zero OS-level side effects — `disable()` when nothing
is registered, which short-circuits to "Automatic startup is already
off." before touching the filesystem — end-to-end through the real route
(right flash message, right redirect). The `enable()`/`_macos_enable()`/
`_windows_enable()` logic itself is otherwise unmodified from IQ's own
already-shipped implementation (string/label substitutions only), so its
correctness is inherited from that, not freshly re-verified here.

**Item 6 — done, 2026-08-23.** Ported manual barcode entry: new
`barcode_source TEXT CHECK (barcode_source IN ('manual','generated'))`
column on `inventory_list` (added to `schema_postgres.sql` for fresh
installs and to `setup.py`'s `INCREMENTAL_SCHEMA_STATEMENTS` for existing
ones, plus a one-time backfill setting `barcode_source='generated'` on any
row that already has a barcode — every pre-existing JO barcode was created
via the old auto-generate-only route, so this is unconditionally correct,
not a guess). New `/inventory-catalog/<id>/barcode/manual` (format-checked
`^[A-Za-z0-9 .\-_]+$`, ≤64 chars — deliberately freer than a generated
code's format, since this represents a real manufacturer barcode),
`/barcode/remove`, and `/barcode/status` routes; the existing
`/create-barcode` route converted from flash+redirect to JSON and now sets
`barcode_source='generated'`. Both the pre-check duplicate lookup and the
`IntegrityError`-on-`UNIQUE`-violation catch (the actual guarantee) ported
for the manual route, mirroring the generate route's existing pattern.
`inventory_catalog_barcodes_generated` (bulk-print picker feed) and
`inventory_catalog_barcodes_bulk_print`'s server-side re-check both
updated to filter on `barcode_source='generated'` instead of "any
barcode" — manual entries are deliberately excluded from bulk printing,
since that feature exists to produce labels for barcodes this app made
up, not to reprint a manufacturer's own packaging barcode.

Replaced the per-row "Create Barcode" inline form in
`templates/inventory_catalog.html` with a single "Manage Barcode"/"Add
Barcode" button opening a small modal (manual-entry field + Save/Remove,
Create/Print/Remove for the generated side, whichever side is inactive
dimmed to `opacity:0.45`) — ported from IQ's equivalent modal but using
JO's own inline `style.display` open/close convention (matching this same
file's existing Bulk Barcode Print modal) rather than IQ's imperative
`VZSpring.present()` calls, for consistency within the file. Removal goes
through `VZDialog.confirm()`.

**A required dependency, not an optional nice-to-have, surfaced during
this port:** both of JO's barcode-print templates
(`barcode_label.html`/`barcode_bulk_print.html`) hardcoded
`JsBarcode(..., {format: 'EAN13', ...})`. A manually entered barcode is
exactly the case that breaks under that hardcoding — a real manufacturer
code is routinely UPC-A (12 digits), EAN-8, or alphanumeric, none of which
JsBarcode will render as EAN13; it throws instead of printing something
wrong. Ported IQ's `static/barcode-render.js`
(`vzBarcodeFormat()`/`vzRenderBarcode()` — checksum-validates against
EAN13/UPC/EAN8 in turn, falling back to checksum-free CODE128 for
anything else, including alphanumeric codes) and updated both templates
to call it instead of hardcoding the format. Without this, manual entry
would have shipped a feature that fails at the one thing it's for.

**Found, not fixed, out of scope — a real, pre-existing, shared bug in
both apps' `generate_barcode()`:** the random body is `"20" + 9 random
digits` (11-digit body) + 1 check digit = **12 digits total**, not real
EAN-13's 13 (12-digit body + check digit) — the code's own comment even
says "12 digits + 1 check digit" while generating one digit short. Grepped
IQ's `barcode.py`: byte-for-byte identical, including the same misleading
"# 11 digits" comment — this predates the JO/IQ fork, not something either
app introduced independently. Practical consequence confirmed live: every
auto-generated barcode in JO, past and present, would fail to render under
the old hardcoded `format:'EAN13'` JsBarcode call (13 digits required,
strictly validated) — meaning barcode label printing for *every*
generated barcode has likely been silently broken in JO's real installs
already. This port's `vzRenderBarcode` addition happens to paper over the
symptom (a 12-digit code fails EAN13, fails UPC-A's different checksum
weighting, falls through to CODE128, which has no length/checksum
requirement — so it now prints fine, just as CODE128 rather than true
EAN-13). Left `generate_barcode()` itself unfixed — correcting the actual
generation length is unrelated to manual entry and affects both apps
identically; worth its own dedicated fix, not a drive-by change bundled
into this port.

**2026-08-23 follow-up: fixed in both apps.** The user asked for this
directly once it came up. Changed `range(9)` → `range(10)` random digits
in both `barcode.py`s (so the body is a true 12 digits, +1 check digit =
13 total) and corrected the misleading `# 11 digits` comment to `# 12
digits`. Forward-only — existing 12-digit codes already in either app's
real data are untouched and keep working via the `vzRenderBarcode`
CODE128 fallback either way, so no migration was needed. Verified live in
both apps' isolated test environments: newly generated codes are now 13
digits with a genuinely valid EAN-13 check digit (hand-verified the
checksum arithmetic, not just the length), and render as true `EAN13`
(confirmed via `vzBarcodeFormat()` directly) rather than falling through
to the `CODE128` fallback.

Verified live in JO's isolated test environment: manual entry with a
realistic alphanumeric code (`ROYAL-CANIN-3KG-001`) saved and printed
correctly as CODE128; mutual exclusivity confirmed both directions
(generate blocked with a manual barcode set, manual blocked with a
generated one set) via direct route calls; remove-then-generate cycle
confirmed, including confirming the generated (12-digit) code still
prints correctly via the CODE128 fallback; duplicate-barcode collision
correctly named the conflicting item; the format-validation guard
rejected disallowed characters; Bulk Barcode Print button appearance and
its picker feed both confirmed correctly scoped to `generated`-source
items only. No new console errors (all logged 400/404s were my own
deliberate negative-path test calls).

**Item 7 — done, 2026-08-23.** Ported `reconcile_attachments.py`, IQ's
standalone post-restore maintenance script — near-verbatim, since JO's
`attachments`/`restore_log` schemas are byte-identical to IQ's. Retargeted
`VETCLINICSYSTEMIQ_DATA_DIR` → `VETCLINICSYSTEMJO_DATA_DIR` and the backup
filename regex to `vetclinicsystemjo_backup_...` (matching `backup.py`'s
own `FILENAME_PREFIX`). Added the pointer sentence to `templates/
settings.html`'s Restore From Backup copy (`run python3
reconcile_attachments.py from the app folder afterward...`) — JO's
existing copy stopped short of mentioning the script at all, since it
didn't exist yet.

**One real, load-bearing divergence caught before it shipped broken:**
IQ's `resolve_record_key()` (the part of the script that reverses a disk
folder name back into a record type + id) assumes visit folders are
double-prefixed — `"VV0042"` — because IQ's `record_key()` always
prepends `"V"` even though a visit's `record_id` is already `"V0042"`.
Read JO's actual `attachments.py`: JO's `record_key()` explicitly
special-cases visits to avoid exactly that doubling — `return
str(record_id)`, no second prefix — so JO's visit folders are named
`"V0042"`, single-V. Copying IQ's `resolve_record_key()` unchanged would
have made the script treat every visit-attachment folder in JO as an
"unrecognized folder name" and silently do nothing for the majority of
real attachments (visit files are more common than inpatient-case files).
Fixed to match JO's actual convention (`key.startswith("V")` after the
`"IC"` check, not `key.startswith("VV")`) before ever testing it live —
this is exactly the class of bug `CLAUDE.md` §2 exists to catch (verify
by reading the other app's actual current code, not by assuming the
surrounding code looks the same so it must work the same way).

**2026-08-23 follow-up: IQ's own `record_key()` fixed too, at the user's
request.** IQ's `attachments.py` module docstring already documents the
*intended* folder name as `"V0042"` (single V) — the double-prefix was a
genuine bug against IQ's own stated contract, not a deliberate choice
JO happened to diverge from. Changed IQ's `record_key()` to match (return
`str(record_id)` for visits instead of unconditionally prepending `"V"`),
and updated IQ's own `reconcile_attachments.py`'s `resolve_record_key()`
to match the new single-V output — at the user's explicit direction, this
does **not** special-case the old double-V folders real IQ installs may
already have on disk from before this fix; only the new naming going
forward is recognized. Verified live end-to-end against IQ's own isolated
test environment: uploaded a real attachment through the actual app
upload route (not a simulated file) and confirmed the resulting folder
and `attachments.relative_path` are `PAT001/V0001/...`, single-V; deleted
the DB row and confirmed `reconcile_attachments.py` correctly found and
re-linked the single-V folder; confirmed the file serves correctly
through the real `/files/<path>` route afterward.

Verified live end-to-end against JO's real isolated test environment
(not just read-through): seeded a real owner/patient/visit and an
inpatient case via direct SQL, placed real files on disk matching
`attachments.py`'s exact `_safe_name()` output pattern in both a visit
folder (`PAT001/V0001/...`) and an inpatient folder (`PAT001/IC2/...`),
then ran the script. Confirmed: dry run correctly identified both as
"would readopt" without writing anything; `--apply` inserted both rows
with the right columns (`visit_id` set/`inpatient_case_id` NULL for the
visit file and vice versa for the inpatient one — confirming the
`record_key()` fix above actually works, not just parses); re-running
`--apply` was correctly idempotent (both files reported "already linked,"
zero re-inserts); an unrecognized folder name was correctly left alone
and reported as "no home," never deleted; the restore-cutoff logic was
exercised with a real `restore_log` row and a file timestamped after that
snapshot, correctly landing in "needs manual review" instead of being
auto-readopted; the dedicated log file
(`<data_dir>/logs/reconcile_attachments.log`) recorded both real
readoptions with the right format. Two of my own test-setup mistakes
(invalid hex characters in a test filename, a missing underscore in a
simulated backup filename) were caught immediately by the script's own
`FILENAME_RE`/`BACKUP_FILENAME_RE` correctly rejecting malformed input —
itself a small confirmation those patterns are working as designed, not
just present. Test data was entirely contained in the isolated
container/data dir and removed by `down jo`'s normal teardown, same as
every other item this session.

**This closes out all 7 items in the JO-parity project** (§5's ordered
list above) — every item that was reviewed and confirmed as a real,
not-by-design gap is now shipped and verified live. Two items were
explicitly declined rather than ported (multi-palette theming,
`money.py`/denomination rounding — see below); one pre-existing, unrelated
bug was found and documented but deliberately left unfixed (the shared
12-digit `generate_barcode()` — item 6's writeup) since fixing it isn't
what was asked and affects both apps identically, not something specific
to closing JO's gap with IQ.

**Explicitly out of scope for this round** (reviewed and declined, not
overlooked):
- Multi-palette theming/branding (§2 Settings) — ~~JO keeps its single
  fixed look for now.~~ **Half of this was superseded on 2026-08-24 (§12):**
  the *palette* axis (ChamPet-style per-clinic branding) is still IQ-only and
  still declined, but the *light/dark* axis is a separate thing and JO now
  has dark mode. Spelled out because the original wording reads as "JO has no
  theming at all", which is the same kind of stale absolute that made the
  audit mis-scope F-25 off §1.2.
- `money.py` / denomination rounding (§1.1) — genuine currency-model
  difference (JOD is exact 3-decimal, no note-rounding concept); not a
  gap, stays divergent by design.

---

## 6. Clean Up feature + full audit-finding rollout — 2026-08-24

Both `features:audits/CLEANUP_FEATURE_PLAN.md`,
`features:audits/ERROR_500_AUDIT.md` (18 findings, E-01–E-18), and
`features:audits/ORPHANED_RECORDS_AUDIT.md` (25 findings, F-01–F-25) are
now **fully implemented and live-verified in both apps.** Per `CLAUDE.md`
§1–2, every fix was built by reading each app's own current code first,
not copy-pasted — IQ's `float`/250-rounding vs. JO's exact `Decimal`
Clean Up math, JO's inline-per-route validation convention vs. IQ's
shared helpers, JO's own `VZDialog`/`VZToast`/`jobs.py` framework (see
§5 item 1) for anything UI-facing, etc.

**Clean Up feature** — a bounded manual write-off/rounding amount
(`CLEANUP_CAP`) addable to visit/inpatient/boarding bills and POS
checkout, threaded through `compute_bill_totals()`, refund caps,
dashboard/PDF exports, and receipts in both apps.

**Both audits, all 43 findings** — crash-prevention (missing/invalid
field validation across ~14 more routes via a new `required_field()`
helper, bounded numeric parsing for BCS/quantity/money, `/insights`
thread-pool cap, a dedicated 503 page for DB pool exhaustion) and
orphaned-record prevention (visit↔inpatient-case status sync, audit
session confirm/discard guards, attachment/payment/refund one-anchor DB
CHECK constraints, consignment distributor-snapshot-at-sale-time,
RESTRICT FKs replacing 19 previously-unconstrained user/staff/resource
foreign keys, backup/restore safety markers + stale-running reaper,
migration-failure isolation, role/permission orphaning warnings). Full
finding-by-finding detail is in the audit docs themselves, not repeated
here — this note is the "what shipped and how it was verified" record
the audits don't carry.

**Live-verified in both apps' isolated test environments** (fresh
Postgres + venv each, `scripts/isolated_test_env.sh`, torn down after):
all new DB constraints confirmed present via direct `pg_constraint`
queries (104 in IQ, 23 new/relevant in JO); spot-checked via real HTTP
requests against seeded test data — form-validation rejections (blank
required fields, BCS=0, missing refund anchor), the visit↔inpatient
status-sync guard in both directions, discount-needs-a-bill guard, audit
session empty-confirm rejection and the new discard route, and (JO
specifically, since its custom-role feature didn't exist when the audit
was written — see the F-25 note below) the full role-vet-flag-flip →
orphaned-appointment-warning chain end to end.

**One deliberate safety property worth calling out explicitly**: several
of the new CHECK/FK constraints (attachment/payment/refund anchors,
consignment-needs-distributor, the 19 RESTRICT FKs) could, in principle,
fail to apply on a real clinic's live database if it already has
historical rows that violate them — the exact class of pre-existing bad
data F-19/F-13/F-14/etc. exist to prevent *going forward*. This isn't
theoretical risk left unaddressed: F-22's fix in this same batch
(`setup.py`'s `apply_incremental_migrations()`, isolated per-statement
savepoints) means a single failing constraint statement no longer aborts
the whole migration or blocks the app from starting — it's recorded in
a `migration_failures` setting, surfaced as a Dashboard admin banner, and
every other statement still applies. A clinic with pre-existing
orphaned/inconsistent data simply won't get that *one* new guarantee
enforced until the underlying row is fixed, instead of being bricked on
update.

**F-25 correction** — the audit doc frames F-25 (role-level vet-flag-flip
warning) as IQ-only, since JO had no custom-role feature when the audit
was written. That's no longer true: JO gained real, UI-wired custom role
creation on 2026-08-23 (§5 item 2). Verified directly against JO's
current `app.py` (`admin_role_new`/`admin_role_edit`/`admin_role_delete`
are real, reachable routes with a live "+ Add Role" UI), per `CLAUDE.md`'s
instruction to check current code rather than trust a doc's framing —
F-25's fix is applied to **both** apps, not just IQ. Live-verified in JO:
created a custom vet-eligible role, assigned a staff member, booked them
an appointment, flipped the role's vet flag off via the real route, and
got the correct warning; confirmed the appointment then showed up under
Appointments' "needs attention" (orphaned) list (F-17/F-18/F-25 chain,
end to end).

**F-24 correction** — initially shipped in JO as a smaller,
behaviorally-equivalent fix (fresh DB connection, kept the route
synchronous) rather than the audit's suggested shape (a background job
with progress polling, matching IQ's `settings_backup_now`). At the
user's explicit request, re-did it to match IQ's actual shape for
apps-stay-identical-except-money-logic reasons: `run_backup()` now
acquires `maintenance_lock` internally and reports progress through
`jobs.py`, `settings_backup_now()` returns a `job_id` and polls via the
existing `/settings/job-status` endpoint (already used by JO's Restore
Now), and Back Up Now in Settings now shows the same `VZProgress`/
`VZToast` panel Restore Now already had. **One real bug caught and fixed
during the port**, not just a copy: JO's `maintenance_lock` was a plain
`threading.Lock()`. IQ's is deliberately an `RLock()`, because
`updater.py`'s `apply_update()`/rollback hold the lock for their whole
run and, on the same thread, call into `run_backup()` as their own first
step — porting the internal-lock-acquisition pattern without also
switching to `RLock()` would have made every in-app update/rollback in
JO falsely report "another backup is already running" on its own
reentrant call. Changed JO's `maintenance_lock` to `RLock()` to match.
Live-verified in JO's isolated test environment: no-folder-configured
rejection, a real end-to-end backup (job completes, dump file written
0600, `backup_log` row correct), two concurrent Backup Now clicks (one
wins the lock and succeeds, the other cleanly rejects), and a direct
simulation of the reentrant scenario (hold the lock, call `run_backup()`
on the same thread) succeeding instead of falsely rejecting — confirming
the `RLock` fix specifically, not just the job/polling plumbing around
it.

**Custom flash/dialog sweep** — see the 2026-08-24 addition to §1.3: both
apps swept for native `alert()`/`confirm()`/`prompt()`/`hx-confirm`
usage; confirmed zero remain in either app's own code, everything already
routes through `VZToast`/`VZDialog`. No changes needed.

**Shipped as IQ `v1.6.0`, JO `v1.3.0`** — MINOR bumps in both (Clean Up
is a genuinely new feature; every schema change is additive) per
`RELEASE_WORKFLOW.md`. See each app's own `CHANGELOG.md` for the
clinic-facing release notes.

**2026-08-24 follow-up, PATCH `v1.6.1`/`v1.3.1` — autostart launcher
targeting bug.** While helping the user debug a real downloaded JO
install's Settings page, found that `autostart.py`'s
`_macos_launcher_path()`/`_windows_launcher_path()` resolved relative to
`BASE_DIR = os.path.dirname(os.path.abspath(__file__))` — wherever the
*currently running* copy of `autostart.py` happens to live, which is
never the same folder as the update-aware supervisor launcher
`enable_updates()` writes into `vetclinicsystem{iq,jo}-data/`. Toggling
"Start automatically when this computer starts" always pinned the
LaunchAgent/Startup shortcut to whatever specific code copy was running
at that moment — the original checkout, or (since each versioned release
snapshot carries its own static copy of both files) one specific frozen
release folder — never the one file that actually re-reads
`active_release.txt` on every start. Practical effect: enable autostart,
then a later update ships and flips the pointer; the *next real reboot*
silently keeps launching the old pinned version, invisibly to
`updater.py`'s own health-check/rollback safety net since nothing about
that mechanism is involved in a plain OS boot. A manual "Update Now"
still worked fine in the moment (the process itself restarts directly),
so this only ever showed up on an actual computer restart — easy to miss
entirely without an install that had both updates and autostart enabled
at once, which is exactly the state the user's JO install was in when
this got noticed.

Fixed with a new `_managed_data_dir()` in both apps' `autostart.py`,
identical logic: prefer the `VETCLINICSYSTEMIQ_DATA_DIR`/
`VETCLINICSYSTEMJO_DATA_DIR` env var the supervisor launcher sets when
running (fast path), falling back to a structural check of the sibling
folder layout on disk (so toggling autostart from a not-yet-switched-over
process — e.g. the original checkout, after `enable_updates()` already
ran from somewhere else — still finds the right target). Verified
against a **real** managed-release layout already on disk (the user's
own `~/Downloads` JO install, not a synthetic fixture): unmanaged
checkout, original checkout with a genuine managed sibling, running from
inside the actual `app_v1.3.0` release folder, and the supervisor
launcher's env var path all resolve correctly; same test structurally
ported to IQ against a synthetic equivalent layout, since no live IQ
managed install exists to test against directly.

---

## 7. Desktop shortcut — added to both, 2026-08-24

A double-clickable **VetClinicSystem IQ** / **VetClinicSystem JO** icon on
the Desktop, carrying the clinic's own house-and-cross glyph, added to both
apps as `desktop_shortcut.py` (structurally identical, naming aside).

**Why it exists:** an explicitly-requested *fail-safe for autostart*. The
autostart toggle registers a real OS login item, but a login item can fail
or be disabled in ways the app can't see or fix from inside itself. A
Desktop icon is the manual path that always works, and — as the whole point
— one that keeps working across updates, shutdowns and restarts.

**How it stays correct across updates:** it points at
`vetclinicsystem{iq,jo}-data/Start VetClinicSystem*.command`, the supervisor
launcher, and never at a `vetclinicsystem{iq,jo}-releases/app_vX.Y.Z/` copy.
That is the same resolution `autostart.py` needs, so rather than a second
implementation the helper was promoted to `autostart.managed_data_dir()` and
is now shared by both — one place to be right, and the §6 `v1.6.1`/`v1.3.1`
bug can't be reintroduced independently in the new module. A pytest
regression guard in each app (`tests/test_desktop_shortcut_target.py`, and
IQ's first `tests/` folder) pins exactly that: create the shortcut while
running from inside a release folder, and the generated launcher line must
still name the data dir.

**Platform mechanics** (they differ, unavoidably, since neither OS lets a
plain script file carry an icon):
- **macOS** — a real `.app` bundle, because Finder only reads a custom icon
  from a bundle's `Info.plist`/`Resources`. Its executable is a small shell
  script; `LSUIElement` keeps the stub out of the Dock and app switcher.
- **Windows** — a `.lnk` with `IconLocation` set, created through the same
  `WScript.Shell` COM object Explorer itself uses (no pywin32 dependency).
  The `.ico` is copied into the data dir first, since a `.lnk` stores an
  absolute icon path and release folders get pruned two updates later. The
  Desktop is located via `[Environment]::GetFolderPath('Desktop')`, which
  follows OneDrive Known Folder redirection — `%USERPROFILE%\Desktop` does
  not, and would silently write to a folder nobody is looking at.

**Behaviour when double-clicked:** if the app is already answering on its
port, it just opens the browser rather than starting a second copy — a
Desktop icon gets clicked whenever someone wants the app *in front of them*,
which isn't the same as wanting another instance. Otherwise it opens the
supervisor launcher in Terminal, exactly as double-clicking that launcher
would. If the install was moved or renamed so the launcher is gone, it says
so in a dialog instead of failing silently.

**When it's created:** by `setup.py`, idempotently, on *every* run once the
versioned-release layout exists — not only the first — so a shortcut that
was dragged to the Trash comes back, and one left pointing at an old path
gets corrected. Also available standalone as
`python3 setup.py --desktop-shortcut`. Never fatal: an install that can't
get a Desktop icon is still a working install, so failures are reported and
setup continues.

**Icons.** Both apps use the same user-supplied glyph, each tinted to its
own `--primary` token (`#B21C43` JO, `#B97A7D` IQ) so two shortcuts sitting
on one Desktop are told apart at a glance rather than being identical
twins distinguished only by filename. Committed as
`installer_assets/appicon.{icns,ico,png}` per app — pre-generated rather
than rasterized at install time, since no clinic machine can be assumed to
have an SVG renderer (and Windows has none at all). The recipe lives in this
workspace at `scripts/make_app_icons.py`; it rasterizes via macOS QuickLook
and recovers the glyph's alpha analytically, QuickLook having composited it
onto opaque white.

---

## 8. Off-palette colour literals — swept and tokenized in both, 2026-08-24

Reported against JO's Settings page: the **Restore Now** button used a
colour that isn't in JO's palette. Root cause and everything found with it:

**`.btn.danger:hover { background: #8f4a41; }`** — a hardcoded literal in
*both* apps. It reads as a plausible darkening of IQ's muted
`--danger: #BD7568`, which is where it was written; copied across to JO it
sat against `--danger: #B8452E`, a far more saturated orange-red, so the
button shifted hue on hover instead of just darkening. Fixed the way the
codebase already handles the primary button (`.btn:hover` →
`var(--primary-dark)`): a new **`--danger-dark`** token per palette, with
`.btn.danger:hover` pointing at it. Values are derived from each palette's
own `--primary` → `--primary-dark` relationship rather than eyeballed —
light palettes darken, dark palettes *lighten*, since IQ's dark palettes
deliberately flip that direction.

**JO `tbody tr:hover { background: #FCF6F3; }`** — same story, and here IQ
was already correct: it uses `var(--line-soft)`. `#FCF6F3` is a warm cream
from IQ's rose/tan family; JO's `--line-soft` is `#F5EEF0`, pink-tinted.
JO now uses the token, making the two apps identical on this rule.

**`var(--paper-alt, #f5f5f5)`** — in IQ's `audit_session_view.html` and
`settings.html`, and JO's `audit_session_view.html`. **`--paper-alt` is
defined nowhere in either app**, so the `#f5f5f5` fallback is what actually
rendered: a flat neutral grey inside two otherwise warm-tinted palettes.
All three now use `var(--muted-tint)`.

**IQ `.appt-chip.grooming { color: #8A5E4D; }`** — pinned its ink as a
literal, then patched two of the four palettes back with two more literals
(`#F1D9CD`, `#E4DEF2`) in separate override rules. ChamPet *light* was never
patched, so it inherited the default's brown on ChamPet's lavender
`--accent-tan-tint: #EFEBF7` — a real mismatch nobody had noticed. Replaced
with one **`--accent-tan-ink`** token per palette; the two override rules
(and the two comments introducing them) are now redundant and removed.
Verified across all four IQ palettes: default light/dark and champet dark
resolve byte-identically to before, and champet light changes from `#8A5E4D`
brown to `#4E4478` purple. Note ChamPet's accent is still flagged
"placeholder — needs sign-off" in the palette itself; the new ink is derived
from it and should be signed off together with it.

**Deliberately left alone:** bare `#fff` for text on a coloured background
(sidebar brand, `.nav-link.active`, `.btn`, `.nav-badge`, `.chip.active`).
It's used identically in both apps, it isn't a palette decision, and
tokenizing it would be churn without a behavioural change.

**Guard for the future:** the `--paper-alt` case is the nastiest of these,
because a `var()` pointing at a token nobody defined fails silently and
renders the fallback. Both stylesheets now pass a check that every `var()`
reference resolves to a definition, and that check is worth re-running after
any palette work.

---

## 9. ChamPet accent signed off, and the folder-browser action row — 2026-08-24

**`--accent-tan` renamed to `--accent-alt`, ChamPet's value signed off (IQ
only — JO has no such token).** §8 fixed the *value* problems around this
token; this closes the two questions it left open. The name was
Vetzone-specific: `#D7BBB2` genuinely is a tan, but ChamPet's `#8478B0` is a
purple, so the name described only half the palettes it covered. Renamed
across all four palettes plus its two chart call sites in `insights.html`.
The purple is now signed off rather than carrying a "needs sign-off"
placeholder comment — and deliberately so, with the reasoning recorded in
the palette itself: this token's main job is a chart series colour that has
to stay distinguishable from `--primary` (teal), `--sidebar-bg` (navy),
`--warn` (amber) and `--muted` (grey) simultaneously, which a variant of
ChamPet's own teal could not do. Worth noting the old comment pointed at
"the plan's gap note" — a document since removed as stale planning
material, so that sign-off context was already unrecoverable; the reasoning
now lives next to the value instead of in a doc that can disappear.

**Folder-browser modal action row (both apps).** The New Folder field and
its button sat on one short, left-aligned row while Cancel / Select This
Folder sat right-aligned on another, so nothing shared an edge with the
folder list above and the block read as jumbled. All four controls now sit
on a single row that runs flush with the list, with the name field flexing
to fill. Three things fell out of doing it properly:

- The row is allowed to **wrap** rather than overflow. Cancel and Select
  are grouped so they wrap and centre as one unit instead of breaking
  apart, and the name field carries a real `min-width` so the wrap happens
  while it is still usable rather than after it has been squeezed to
  nothing.
- **`.modal-box` gained `min-width: 0`** — and this one was a genuine
  pre-existing bug affecting *every* modal in both apps, not just this one.
  `.modal-overlay` is a flex container, so each `.modal-box` is a flex item
  whose default `min-width: auto` (min-content) silently overrides
  `max-width`. On a phone the modal rendered wider than the screen. Adding
  `min-width: 0` is what actually lets it shrink; `.modal-overlay` also
  gained `padding: 16px` so a clamped modal keeps a margin rather than
  touching the bezel.
- One behaviour change worth knowing: in file-picker mode (Restore), where
  the name field and Select are both hidden, the lone Cancel button is now
  **centred** rather than right-aligned. That follows from centring the
  action group and reads as deliberate for a single button.

Verified live in both apps at 1280px and 375px: desktop is one row flush
with the list; mobile wraps to the field on one line and the two actions
centred beneath it, with the modal inside the viewport and no horizontal
page scroll.

---

## 10. Backups asked for a password in the Terminal — fixed in both, 2026-08-24

Reported by the user: taking a backup appeared to hang, and only by chance
did they notice `pg_dump` was sitting at a `Password:` prompt in the
launcher's Terminal window. Their account password didn't work there either.

**Root cause.** `backup.py`'s `_pg_conn_parts()` parsed `DATABASE_URL` for
user/db/host/port and **threw the password away** — the docstring said as
much, so it read as intentional. `_run_pg_dump()`/`_run_pg_restore()` then
handed the child `dict(os.environ)`, which carries no `PGPASSWORD`, so libpq
did what it always does with no credential: prompt. And libpq reads that
prompt from the **controlling terminal**, not stdin, so `capture_output=True`
didn't intercept it — the process just blocked forever behind a prompt in
whatever Terminal the launcher owned. From the app's side it looked like a
backup that never finished; from the user's side, a hang.

The password it wanted was the **Postgres** one (`POSTGRES_PASSWORD`, in
`docker-compose.yml` / `.env`), never the clinic login — which is why
entering an account password failed.

**Why it survived this long:** installs *without* the Postgres client tools
never hit it. `_run_pg_dump()` falls back to `docker exec`, which connects
over the container's local socket under trust auth and needs no password.
Only a machine with `pg_dump` on `PATH` takes the failing branch — and both
dev machines and the isolated test environment happened to be in that state
without anyone connecting the two. (Earlier in this same session the harness
hit exactly this error and it was worked around with a manual `PGPASSWORD`
export instead of being recognised as the product bug it was.)

**Blast radius — every backup path in both apps**, not just the button:
manual Back Up Now, the nightly scheduled job, the pre-update backup in
`updater.py` (the worst one — an update stalling behind an invisible prompt),
IQ's shutdown backup, and Restore.

**Fix.** `_pg_conn_parts()` now returns the password too, parsed with
`urllib.parse.urlsplit`/`unquote` rather than by hand so a percent-encoded
password survives; a new `_pg_env()` puts it in `PGPASSWORD` for the child.
Both `docker exec` paths pass it through as well, for a container not on
trust auth. Every `pg_dump`/`pg_restore` invocation also gains **`-w`**
(never prompt): with the password present it never fires, and if a password
is ever wrong or missing the command fails immediately with a clear error
instead of hanging. That last part is the durable guarantee — the failure
mode simply can no longer be "silently waiting".

**Two related fixes to the same report:**
- Back Up Now with **no backup folder set** used to start a job, run the
  progress panel through its steps and then report failure — reading as "the
  backup broke" rather than "not set up yet". The route now refuses upfront
  (400 + a specific message), the button is disabled with a hint until a
  folder is saved, and the client surfaces the server's actual reason instead
  of a generic "Could not start the backup."
- That same case no longer writes a `failed` row to `backup_log`. Nothing was
  attempted, and a nightly job with no folder configured would otherwise fill
  Recent Backups with failures and bury real ones. `logic.backup_alert_message()`
  already reports this state on the Dashboard on its own, with a better
  message ("No database backup has ever run yet — set a backup folder").

Verified live in an isolated environment deliberately shaped like the real
install — `pg_dump` on `PATH`, a password in `DATABASE_URL`, and **no**
`PGPASSWORD` in the app's environment: backup and restore both complete end
to end; the no-folder case is refused with a 400 before any job starts; and
`pg_dump -w` was confirmed to fail immediately on both a wrong password and
no password rather than prompting.

---

## 11. Sticky table headers — JO brought up to IQ's coverage, 2026-08-24

Reported as "there are tables in IQ that have their header sticky — find
which and do the same in JO". The mechanism was already identical in both
apps: `thead th { position: sticky; top: 0 }` plus
`.table-wrap.sticky-scroll { overflow: visible }`, which drops the wrapper's
own scroll so the header pins against the *page* scroll on a long list.
Both apps also had the same 45 `.table-wrap` usages across the same 35
templates, and the same three height-constrained tables.

The gap was purely which tables opted in: **IQ marked 21, JO only 6** — and
JO's six were all Consignment pages plus the audit session view, i.e.
whatever happened to be carried across when those screens were ported. The
15 JO was missing: Owners, Patients, Visits, Follow-Ups, Wellness, Grooming,
Boarding, Inpatient, Price List, Inventory Catalog, Audit Sessions, Sales
History, Refunds, Yearly P&L, and the Dashboard's missed-items table.

Each of those templates contains exactly one `.table-wrap` in both apps, so
the mapping was unambiguous. JO now marks the same 21 templates as IQ —
verified as an identical set, not just an equal count.

**A pre-existing bug surfaced by doing this, fixed in both.** Below 760px
`.mobile-topbar` is `position: fixed` at the top of the viewport, but
`thead th` pinned to `top: 0` — so on a phone the sticky header parked
*behind* the bar and was simply invisible. It was already wrong in IQ; JO
adding it to 15 more pages would have made it far more visible. Both apps
now carry a `--topbar-h` token used by the bar's own height and by the
sticky offset inside the mobile media query, so the two cannot drift apart,
and the mobile brand text gained `nowrap`/ellipsis so a long clinic name
cannot change that height out from under the offset.

Verified live in JO with 60 seeded owners: on desktop the header pins to the
top of the viewport (offset `0px`, bar not rendered); at 375px the bar is
62px and the header pins at exactly 62px, fully visible with rows scrolling
beneath it.

---

## 12. Dark mode for JO, and a dark-mode contrast fix for IQ — 2026-08-24

This supersedes §5's "multi-palette theming/branding — JO keeps its single
fixed look for now". That decision was about the *palette* axis (ChamPet-style
per-clinic branding), which stays IQ-only. The light/dark axis is a separate
thing and JO now has it.

**JO's dark palette is derived from JO's own light values, not copied from
IQ's.** Two reasons it had to be:
- JO's neutrals are plum-tinted (`--ink: #2B1620`), so the dark greys are
  plum-dark rather than IQ's rose-warm ones.
- **JO's sidebar is already dark navy (`#051335`) in light mode**, unlike
  IQ's light dusty blue. So it is *deepened* (`#030B21`), not inverted —
  the same call IQ's own ChamPet dark palette documents for the same reason.

JO's brand mark is an inline SVG on `currentColor` sitting on a
permanently-dark sidebar, so unlike IQ there are no light/dark logo assets
to swap — one less moving part.

**The filled-control contrast problem, and why the obvious fix was wrong.**
Every palette lifts its accent colours in dark mode so they read as *text*
against a dark page. That is exactly what makes white text *on top of* them
fail — measured across every existing palette: 2.26:1 (IQ default), 2.32:1
(ChamPet), and 2.0–2.8:1 for danger/ok. All well under the 4.5:1 needed.

The first plan was to deepen `--primary` for buttons and add a separate
`--link` token for text. Working the numbers showed that is both unnecessary
and worse: a single rule flipping the *label* to the page colour scores
6.5–9.2:1 across every palette and every filled variant, needs no new
tokens, and — importantly — **leaves IQ's dark colours exactly as they
were**, where deepening the fills would have visibly changed a shipped
palette. It is also the better look: white on a pastel rose fill was washed
out to begin with.

```
html[data-theme="dark"] .btn:not(.secondary),
html[data-theme="dark"] .nav-badge,
html[data-theme="dark"] .chip.active { color: var(--bg); }
```

`.secondary` is excluded because it is not a filled control — it sits on
`--paper` and keeps `--ink`.

**`color-scheme: dark` was missing from both apps.** Without it the browser
renders its own chrome light — date/time pickers, select dropdowns,
scrollbars — punching white holes in a dark page. Added to both; the ChamPet
dark palette inherits it, since that element still matches
`html[data-theme="dark"]`.

**Deliberately not changed: IQ's light-mode button contrast.** The sweep
turned up that IQ's *light* palettes are also marginal — 3.42:1 (default),
3.21:1 (ChamPet), and `.btn.ok` at 3.00:1. Fixing those means darkening
IQ's signature dusty rose and ChamPet's teal, i.e. changing each clinic's
brand colour, which is a decision for the user rather than a contrast
cleanup. Recorded here so it is not rediscovered as new. JO's light palette
is already fine (6.69:1).

Verified live in both apps. JO: the toggle round-trips and persists to
`vetclinicsystemjo-theme`, sun/moon icons swap, and **light mode resolves
byte-identically to the pre-change palette** — no regression to the shipped
look. Measured in the running app, dark mode gives body text 16.11:1,
primary button label 6.20:1, table header 6.45:1, nav badge 6.20:1. IQ:
default dark now 8.16/7.14/9.15:1 for primary/danger/ok buttons and ChamPet
dark 7.94/6.55/8.35:1, with `.btn.secondary` correctly untouched at 13.5–14.2:1.

---

## 13. Light-palette contrast brought to AA in both apps — 2026-08-24

Closes the item §12 deliberately left open. Fixing it turned out to be
wider than "IQ's buttons", because these tokens carry two jobs at once:

- **as a button fill** under white label text (`.btn`, `.btn.danger`, `.btn.ok`)
- **as badge text on their own tint** (`.badge.primary/.ok/.warn/.danger`)

Both were failing, and the badges were worse than the buttons — in IQ's
default light palette every badge sat at **2.24–2.98:1**, i.e. barely
legible, which is what the "Never audited" chip on the Dashboard had been
all along. The two uses pull the same direction (darker), so one change per
token fixes both; that is the opposite of the dark-mode situation in §12,
where they pulled apart and the label had to flip instead.

Changed, minimally — hue and saturation are untouched, only lightness, by
scaling each token's channels uniformly until it clears 4.55:1 on the
stricter of its two constraints:

| | IQ default | IQ ChamPet | JO |
|---|---|---|---|
| `--primary` | `#B97A7D` → `#895A5D` | `#1B9CBE` → `#157792` | unchanged |
| `--danger` | `#BD7568` → `#935B51` | `#C15B4E` → `#AA5045` | `#B8452E` → `#B5442D` |
| `--ok` | `#7C9D82` → `#5A725F` | `#4C9B79` → `#3C795F` | `#4B8F6B` → `#3F7759` |
| `--warn` | `#C99A5C` → `#87673E` | `#C08A3C` → `#8E662D` | `#B5791F` → `#956319` |

**Each `-dark` hover had to be re-derived too.** Two of the new bases landed
at or past their own hover value — IQ's new `--danger` was exactly the old
`--danger-dark`, and the new `--primary` was *darker* than `--primary-dark`,
which would have made hovering lighten the button. Every affected hover is
now 0.82× its new base, so it stays deeper and passes on its own.

Only the accent tokens moved. Neutrals, sidebars, tints and shadows are
untouched, which is why both apps still read as themselves — IQ's accents
are deeper within the same rose/teal families rather than a different
palette. JO's changes are small (its crimson already passed at 6.69:1);
IQ's are the visible ones.

Verified by probing every component in the running apps across all six
palette/theme combinations — 4 button variants × 4 badge variants each,
48 checks: **nothing below AA anywhere**, and `.btn.secondary` untouched at
13.5–17.0:1. Dark-mode figures from §12 are unaffected, since only light
palettes changed.

---

## 14. Amber restored via a `--warn-ink` split — 2026-08-24

Follow-up to §13, where `--warn` was darkened far enough that the amber
read as ochre. The ask was to lighten `--warn-tint` instead. **That alone
cannot work, and the arithmetic says so plainly:** even against pure white
the original `#C99A5C` reaches only 2.54:1 against the 4.5:1 needed — its
luminance is about twice the maximum any 4.5:1 pairing allows, and
`--warn-tint` was already at `#F8F0E1`, near the top of its range. There is
no tint bright enough to rescue that gold behind text.

What *did* work is that `--warn` was doing two unrelated jobs:

- **text** — `.badge.warn`, `.stat-card.warn .num`, `.reassign-note strong`,
  `.role-card-dirty-note`, the Dashboard's inline warn flashes, and (JO only)
  `.appt-chip.grooming`
- **decorative shapes** — `.row-flag-mismatch`'s 3px left border, the
  `.vz-toast-warn` icon fill, `.reassign-note`'s border, and the legend
  swatches on Price List / Inventory Catalog / Appointments

Only the first needs 4.5:1. So `--warn` is now back to its **original gold**
for the shapes, and a new `--warn-ink` carries the text — the same pattern
`--accent-alt-ink` already established in IQ. `--warn-tint` was lightened as
asked (`#F8F0E1` → `#FCF7EC`, and equivalently in the other palettes), which
buys a marginally lighter ink and a paler chip; on its own it moved the ink
only from `#87673E` to `#8C6B40`, which is the measured proof that the tint
was never the lever.

In dark palettes `--warn-ink` simply mirrors `--warn`: the lifted amber
already reads at 6.8–7.3:1 on its dark tint, so nothing needed to split
there.

| | `--warn` (shapes) | `--warn-ink` (text) | `--warn-tint` |
|---|---|---|---|
| IQ default | `#C99A5C` restored | `#8C6B40` | `#FCF7EC` |
| IQ ChamPet | `#C08A3C` restored | `#936A2E` | `#FDF8ED` |
| JO | `#B5791F` restored | `#9B671B` | `#FDF8EC` |

Verified across all six palette/theme combinations: badge text 4.56–7.26:1
and stat numbers 4.83–8.46:1, nothing below AA, with the gold back on every
decorative use. The §13 figures for primary/danger/ok are unchanged.

---

## 15. Inventory refresh — what 2026-08-24 put in both apps

§3's list is corrected in place above, but it predates today entirely, so
this is the running total of what this session added to **both** apps
(details in §6–§14):

- **Clean Up** on visit / inpatient / boarding bills and POS (§6) — tailored
  per app's money model, not shared code
- **Desktop shortcut** (`desktop_shortcut.py`, `installer_assets/`) and the
  shared `autostart.managed_data_dir()` helper (§7)
- **Dark mode** — now in both, with `color-scheme: dark` (§12). The
  *palette* axis (ChamPet) stays IQ-only.
- **Collapsible sidebar groups** — JO's markup finally opting into the
  `ui.js` logic it had been carrying unused (§11 preamble, and the
  2026-08-24 note in §1.3)
- **Sticky table headers** on the same 21 templates, plus the `--topbar-h`
  offset fix (§11)
- **`tests/`** in both, with `test_desktop_shortcut_target.py` (§7)
- **`--warn-ink`** in both; **`--accent-alt`** in IQ only (§9, §14)
- **Shutdown-triggered backup** and the `backup_log.triggered_by` column
  behind it (§17) — the last item §4 had listed as open
- All 18 `audits/ERROR_500_AUDIT.md` + 25 `audits/ORPHANED_RECORDS_AUDIT.md` findings (§6)

**Still genuinely divergent, by design:** `money.py` and the currency model
(§1.1), the phone-number format, and multi-palette branding (§3).

**Head of both apps as of this section's last edit:** IQ `v1.8.3`,
JO `v1.6.5`. Anything after §14 is listed in its own section rather than
here, so treat the per-section "shipped as" lines as authoritative — this
one goes stale by design every time either app ships.

---

## 16. Mobile / tablet pass — 2026-08-24

Deliberately narrow in scope: desktop remains the primary target, so every
change here either sits inside a max-width media query or is inert on a wide
viewport. No layout redesign, no cards-instead-of-tables, no template edits.

**Two things were actually breaking layout, both about horizontal overflow.**

*Wide tables dragged the whole page sideways.* `.table-wrap` normally has
`overflow: auto` so a wide table scrolls inside its card; `.sticky-scroll`
sets `overflow: visible` so the header can pin against the page instead.
Measured natural widths against a phone's ~343px content area: Price List
805px, Monthly P&L 717px, Visits 636px, Sales History 540px, Patients 453px,
Inpatient 412px. With `overflow: visible` all of those push the page, taking
the sidebar and top bar with them. **Partly self-inflicted:** IQ has had this
on all 21 tables for a long time, but JO only had 6 until §11 added the other
15. Fixed by restoring the card's own scroll below 1120px — a threshold
derived from the widest table (805px + 240px sidebar + 72px padding ≈ 1117),
not picked by feel. This cannot be done per-table: an element cannot scroll
on one axis and stay `overflow: visible` on the other, so horizontal
scrolling and page-level sticky headers are mutually exclusive.

*Tablet portrait overflowed on its own.* At 768px the shell computed to
`240px + 710px = 950px` inside a 768px viewport. `.main` is a grid item, and
a grid item's default `min-width: auto` lets its widest content inflate the
column — the same trap `.modal-box` hit in §9. `.main { min-width: 0 }` fixes
it (measured: 950px → 768px) and is inert on desktop, where there is slack.

**Two touch/usability fixes.** Inputs were `font-size: 14px`; iOS Safari
zooms the page on focus for anything under 16px and never zooms back, so
every form entry left the page magnified — now 16px below 760px only, desktop
keeps 14px. And touch targets were well under the 44px standard: `.nav-link`
32px (×35, the most-tapped thing on a phone), `.hamburger-btn` 34px that
opens them, `.btn` 34px, `.nav-group-toggle` 25px. All now 44px via
`min-height` — these elements are already flex with centred content, so the
hit area grows without moving any text. ~~`.theme-toggle-btn` is deliberately
40px, not 44: it is a secondary icon control and 44 would inflate the sidebar
brand row.~~ — **raised to 44px on request the same day**, so nothing is under
44 anywhere. The brand row does grow (63px → 67px), but the clinic name was
already wrapping to two lines before that: measured, the wrap comes from the
toggle existing at all (name height 20px → 39px when it is present), which
§12 introduced in JO. IQ has carried the toggle far longer, so a two-line
clinic name is simply its existing look and JO now matches it.

**Checked and found already fine** (worth recording so it is not re-swept):
no hover-only affordances anywhere — every `:hover` rule is visual feedback
only, nothing is hidden behind hover, so nothing is unreachable by touch; POS
already collapses to one column at 900px; the appointments grid already
scrolls; the viewport meta tag is correct; modals were fixed in §9.

Verified live at 375/483px, 768px, 1280px: no page-level horizontal scroll at
any width, tables scroll within their card below 1120px, page-level sticky
headers still working at 1280px, inputs computing to 16px, and — after the
toggle correction above — **zero interactive elements under 44px**, counted
with the sidebar drawer open so the 36 nav links are measured too.

**Shipped as** IQ `v1.8.2` / JO `v1.6.3` (the four changes), then IQ `v1.8.3`
/ JO `v1.6.4` (the toggle raised to 44px).

---

## 17. Shutdown-triggered backup ported to JO — 2026-08-24

Closes the last gap §4 still listed as open. IQ takes one final backup on
SIGTERM/SIGINT/SIGBREAK — the signals the OS sends on shutdown, restart or
logout, and what a person closing the launcher window produces. Not because
writes are in flight (every write is already committed per request) but
because Postgres, in Docker or as a local service, gets killed in the same
shutdown sequence and this leaves something recent to fall back on.

**JO already had most of the scaffolding** — `_graceful_shutdown` registered
on all three signals, closing the pool and exiting — so only the backup step
itself was missing from the handler. But porting just that would have half
worked, because of what the check turned up:

**JO's `backup_log` had no `triggered_by` column at all.** `run_backup()`
accepted the argument and `_log()` silently dropped it, so *every* JO backup
ever taken — manual, nightly, pre-update — recorded no trigger. IQ has had
the column since the table was created. Interestingly JO's `restore_log`
*does* have it and its Recent Restores table displays it; only the backup
side was missing, which is why it went unnoticed.

So the port is five pieces, not one:
- `backup_log.triggered_by` in `schema_postgres.sql`, plus an
  `ADD COLUMN IF NOT EXISTS` migration for existing installs (older rows stay
  NULL, and the Settings table renders that as "—")
- `_log()` accepting and writing it, and `_run_backup_locked()` threading it
  through all three of its call sites
- `scheduler.py` labelling its nightly run, which it never did
- Recent Backups in `settings.html` gaining the **Triggered By** column IQ
  already shows
- the shutdown backup itself in `_graceful_shutdown`

Verified live on a throwaway install: the migration applied cleanly with no
`migration_failures` row; a manual backup logged as `manual`; then a real
`SIGTERM` produced a second backup logged as `shutdown`, 120KB written to
disk, and the process exited cleanly. Settings renders both as "Manual" and
"Shutdown".

---

## 18. Still open, as of the end of 2026-08-24

Replaces §4, whose items are all closed. Nothing here is a defect; each is a
decision waiting on the user rather than work someone forgot.

**Divergent on purpose — not gaps:**
- `money.py` / denomination rounding (§1.1). IQD rounds to notes, JOD is exact
  3-decimal. The single largest structural difference between the apps and the
  reason a money-adjacent fix can never be copied across untested.
- Phone-number format and validation (§1.5).
- Multi-palette branding — the ChamPet palette and its `-champet` asset set
  (§3, §5). IQ-only and staying that way. Note this is the *palette* axis
  only; light/dark is in both since §12.
- `--accent-alt` (IQ-only, §9) — exists only to stay distinguishable across
  IQ's four palettes, so JO has no use for it.

**Waiting on a decision:**
- ~~**ChamPet's accent is signed off but its source is still a placeholder.**
  §9 signed off `--accent-alt: #8478B0` with reasoning recorded in the palette,
  but the palette's own comment still flags `--accent-tan`'s origin as needing
  brand sign-off. Worth settling before ChamPet goes live at a real clinic.~~
  — **2026-08-26 correction: this was already closed when it was written, and
  there is nothing outstanding.** Checked IQ's live `static/style.css`: the
  ChamPet block's comment reads "Signed off 2026-08-24" (line ~126) and carries
  the full reasoning — the token has to stay distinguishable from `--primary`
  (teal), `--sidebar-bg` (navy), `--warn` (amber) and `--muted` (grey) at once,
  which a variant of ChamPet's own teal could not do. **No "needs sign-off"
  placeholder comment exists anywhere in the file**, and `--accent-tan` is not
  a token in either app any more — the only occurrence of that string in the
  whole IQ tree is inside that same comment, explaining why the token was
  renamed to `--accent-alt`. §9 did this on 2026-08-24 and §18 was written the
  same day describing the pre-§9 state. Nothing to decide before ChamPet goes
  live at a real clinic.
- **IQ's light-mode `.btn.ok` and friends were fixed to AA in §13**, but that
  changed IQ's signature dusty rose and ChamPet's teal. If either clinic
  objects to the deeper accents, the alternative is the `-ink` split §14 used
  for amber — more tokens, closer to the original colours.
- **The workspace itself is not version controlled.** `COMPARISON.md`,
  `CLAUDE.md`, `RELEASE_WORKFLOW.md` and `scripts/` have no history, no
  backup and no diff. This file alone grew by roughly two-thirds in a single
  day. Deciding whether to `git init` it (and whether it gets a remote) is
  outstanding.

**Known-and-accepted behaviour, recorded so it is not re-reported as a bug:**
- The shutdown backup (§17) makes shutdown take as long as `pg_dump` does. On
  a large database, or a machine the OS is force-quitting, it may not finish.
  It is a best-effort safety net, not a guarantee — true of IQ as well.
- Below 1120px, tables trade page-level sticky headers for scrolling inside
  their own card (§16). CSS cannot do both on one element.
- JO has no shutdown *restore* equivalent, and neither app has one; restore is
  always a deliberate admin action.

---

## 19. Boarding discount, and two over-narrow modals — 2026-08-24

**Modal width (both apps, identical).** Reported against JO's New User form,
confirmed byte-identical in IQ. `.modal-box` defaults to `max-width: 420px`
and neither `#userModal` nor `#roleModal` overrode it, while both hold a
two-column `.form-grid` — leaving ~182px per field. `#roleModal` was worse:
`.perm-grid` packs at `minmax(200px, 1fr)`, so all ~28 permission checkboxes
rendered in a single very tall column.

Fixed to 560px and 640px respectively. **`max-width` alone did nothing** —
`.modal-box` carries `min-width: 0` (added in §16 so modals can shrink below
the viewport on a phone), which also means the box sizes to its *content*, so
a larger cap is never reached. `width: 100%` alongside it is what actually
widens them. Measured after: New User 438px → 560px with fields 182px →
243px; Add Role 550px → 640px with permissions now in two columns. Both still
clamp to 343px on a 375px phone with no page scroll.

**Boarding discount (new, both apps).** Boarding was the only billed entity
without one — `boarding_billing_summary_from_fields()` passed a hardcoded `0`
into `compute_bill_totals()`, where visits and inpatient cases both pass a
real `discount_percent`. Added as a field in the Record Payment dialog beside
the existing Clean Up, and persisted on the stay:

- `boarding_sessions.discount_percent` + `discount_applied_by`, typed per app
  (`DOUBLE PRECISION` in IQ, `NUMERIC(5,2)` in JO) with a RESTRICT FK, plus an
  `ADD COLUMN IF NOT EXISTS` migration and the DROP/ADD constraint pair
  Postgres requires
- `logic.py` threads it through, and now returns `subtotal`/`discount_percent`
  in the summary so callers can recompute
- the route validates against each app's own cap helper —
  `discount_percent_error(percent, auth.discount_cap_for(db))` in IQ, the
  inline range check in JO — because those genuinely differ
- both boarding PDFs gained Subtotal/Discount rows in the shape the visit and
  inpatient PDFs already use

**The money-model difference is handled by not reimplementing it.** Both apps
pass the percent into their own `compute_bill_totals()`, so IQ gets its
250-note rounding and anti-"looks free" floor while JO stays exact to 3
decimals. Verified with the same stay in each: 60,000 IQD at 7% → raw 55,800
→ **55,750** (nearest 250 note) in IQ; 60.000 JOD at 10% → **54.000** exactly
in JO.

**One ordering trap worth recording.** The discount, the Clean Up and the
payment all arrive in the *same* submission, and the first two change the
balance the third is checked against. Validating the payment against the
pre-submission balance would let "apply 10% and pay in full" through at the
undiscounted figure, overpaying a bill that can never be un-paid (there is no
delete route for a boarding payment). The route now simulates the bill as the
submission would leave it before accepting the payment. Verified: paying the
pre-discount 60.000 with a 10% discount is refused against the discounted
54.000, and nothing is written.

---

## 20. Full line-by-line divergence audit, and findings 7.1–7.5 closed — 2026-08-25

`audits/IQ_JO_DIVERGENCE_AUDIT.md` is a phase-by-phase sweep of both
trees — every module, the money model included — produced by normalizing the
naming tokens in each tree before diffing, so only genuine divergence surfaced
rather than every `IQ`/`JO` string. It is a **snapshot dated 2026-08-25**, the
same caveat this file carries: treat it as a starting point once either app
moves. Its §8 lists the divergences that are deliberate and must not be
"fixed"; that list agrees with §18 above.

Five of its six findings were implemented and verified live, then the test
environments were torn down. Shipped as **IQ v1.9.1 / JO v1.7.1**.

**Closed in JO (all three were IQ-parity gaps, no money surface):**
- **Keyboard focus was invisible.** JO had zero `:focus-visible` rules; IQ's 12
  ported verbatim, including the `tr[tabindex="0"]` inset outline. A Tab-focused
  input now renders `2px solid var(--primary)` at `2px` offset.
- **No `NumericValueOutOfRange` handler.** An absurd number reaching a numeric
  column — a crafted `<int:...>` URL, a huge quantity — produced a raw 500 in JO
  where IQ friendly-degrades. Exception re-exported from `db.py`, handler added
  at IQ's exact position. JO's handler count is now 13, matching IQ.
- **Folder-browser rows were unstyled**, the last loose end from §9's popup work.

**Closed in JO — a deliberate new divergence, decided rather than defaulted:**
- **The weekend is no longer hardcoded.** `WEEKDAY_IS_WEEKEND` became
  `DEFAULT_WEEKEND_DAYS = {5, 6}` plus `weekday_is_weekend(db)`, reading an
  optional `settings.weekend_days` row (comma-separated 0-6, same numbering as
  `EXTRACT(DOW)`; malformed values fall back rather than raise). Behaviour with
  no setting is byte-identical to the old constant — Jordan's Fri/Sat. There is
  **no Settings UI for it**; it is a settings row on purpose, for a deployment
  outside Jordan. **IQ still hardcodes its own weekend** — this is now a real
  divergence, and porting it to IQ is a separate decision, not a follow-up.

**Closed in IQ — the one with a live-user hazard:**
- **`users.password_changed_at` aligned to JO's `TEXT NOT NULL DEFAULT ''`.**
  Cosmetic on its face, but the session-invalidation check in `require_login()`
  had been relying on `NULL == None` comparing equal. Tightening the column
  without also adding JO's truthiness guard would have compared `None != ''` and
  **logged out every existing IQ user once, on their next request.** The guard
  moved with the schema change, as the finding required. Migration is three
  idempotent statements in `INCREMENTAL_SCHEMA_STATEMENTS` — backfill NULLs,
  `SET DEFAULT`, then `SET NOT NULL`, in that order, because `SET NOT NULL`
  fails outright on any surviving NULL. Verified by simulating an existing
  install (column dropped back to nullable, a real NULL row inserted) and
  re-running the migrations: converged to `not null / ''::text`, zero NULLs, 73
  statements applied, no `migration_failures` entry.

**Left open, not requested:** the audit's 7.6 — JO's
`tests/test_no_raw_form_dates.py` guards a real past incident and applies
equally to IQ, which still has no equivalent. Both apps do have
`tests/test_desktop_shortcut_target.py`.

---

## 21. `parse_date()` validated a prefix, not the value — fixed in both, 2026-08-25

Found while assessing whether the divergence audit's finding 7.6 was worth
acting on. **The audit itself missed this**, in exactly the way `CLAUDE.md` §2.2
warns about: IQ's code *looked* like it had equivalent protection, so the sweep
accepted it without running it.

`logic.parse_date()` — **byte-identical in both apps**, no money surface — did
`datetime.strptime(str(v)[:10], "%Y-%m-%d")`. It truncated *before* validating,
so any value with a valid 10-character prefix parsed clean:
`"2026-08-25garbage"` returned a real `date` and raised nothing.

That matters because several routes guard a user-supplied `?date=` with a bare
`try: logic.parse_date(x) / except ValueError:`. A prefix-valid value slipped
through the guard untouched and reached the query, where a real `DATE` column
made Postgres raise a cast error — **a reproducible 500**:

| route | `?date=2026-08-25garbage` (before) |
|---|---|
| IQ `/visits` | **500** |
| IQ `/refunds` | **500** |
| IQ `/pos/history` | 200 — escaped only because it `LIKE`s a text column |
| JO `/cash-register`, appointments `week=`/`day=` | same bare-guard shape |

> **Correction, §22:** the row above originally also named JO `/retention` as a
> silently-degrading page. It has no date filter; the third site is `/refunds`.

Not SQL injection — the queries are parameterized; `2026-08-25'; DROP--`
produced the same harmless cast error. Not reachable through normal UI use
either: it needs a hand-edited query string, and the routes are
permission-gated.

**Why IQ looked safe and wasn't.** JO's 2026-08-23 sweep (commit `9034cf6`)
fixed *two* halves of this. The write-side half is what 7.6's test guards. The
read-side half added `clean_date_filter()`, which validates the **whole**
string. **IQ never received that half** — it has zero occurrences of
`clean_date_filter`. IQ instead guards inline with `try: parse_date(...)`,
which reads as equivalent and has *better* UX (IQ flashes "That date wasn't
valid"; JO silently drops the filter) — but inherited `parse_date`'s
truncation, so it wasn't equivalent at all.

**The fix, applied identically to both** (same function, same change — this is
one of the cases where "identical" is correct, not a shortcut): validate the
whole string via `date.fromisoformat()`, falling back to
`datetime.fromisoformat().date()`. The fallback is load-bearing — two **TEXT**
columns store a full `isoformat()` stamp and legitimately depended on the
truncation: `backup_log.started_at` (read by `backup_alert_message()` on the
Dashboard) and `visits.case_status_changed_at`. Every `*_date` column is a real
`DATE`, so psycopg hands back `date` objects that hit the existing early return.

Fixing the shared helper closes the class in both apps rather than patching the
three IQ call sites, so IQ keeps its flash-message UX and JO keeps
`clean_date_filter` as its read-side belt-and-braces.

Verified live in both isolated environments: all previously-500ing routes now
flash and degrade, a 25-page sweep returned no non-200s, and
`backup_alert_message()` still parses a real `2026-08-25T02:00:00` stamp.

**One deliberate behaviour change worth knowing:** a *corrupt* value in those
two TEXT columns now raises instead of being silently truncated. Only reachable
by editing the database directly — the app always writes them with
`.isoformat(timespec="seconds")`. Left strict on purpose; silently accepting
malformed data is what created this bug.

Shipped as **IQ v1.10.1 / JO v1.8.1**.

**Audit 7.6 itself remains open and is still judged low-value**: IQ already
passes that test (0 offenders across 21 date fields), and its docstring cites
`data_integrity_framework.md`, which exists in neither repo.

---

## 22. JO's date-filter warnings made consistent — 2026-08-25

Follow-on from §21. JO was inconsistent **with itself**: `/cash-register`
warned when an unusable `?date=` was discarded, while `/visits`,
`/pos/history` and `/refunds` degraded to "no filter" in silence — which on a
list page is indistinguishable from "the filter worked and there's a lot of
data". IQ has always warned on all of them. Not a defect either app
introduced; a seam left by the two halves of the date fix landing on
different dates (see §21).

**A correction to §21's table:** it listed JO's third silent page as
`/retention`. That was wrong — JO's Retention page has no date filter at all.
The third site is `/refunds`, reached through `_refunds_page_context()`; the
line looked like Retention's only because the nearest preceding `@app.route`
in the file is Retention's.

Added `date_filter_arg()` — `clean_date_filter()` plus a flash, firing only
when something was actually discarded, so an absent or empty `?date=` stays
quiet. Message matches IQ's wording exactly.

**`/refunds` was the one that needed thought, and it is a genuine structural
divergence, not drift:**

| | IQ | JO |
|---|---|---|
| `_refunds_page_context` signature | `(db, date_filter, page)` | `()` |
| who reads `?date=` | the route | the builder itself |
| save-failure re-render passes | `None` explicitly | re-reads the request |

Because JO's builder re-reads the request, and
`refund_retail_save()`/`refund_service_save()` re-render through it on a
validation failure, flashing inside the builder would have stacked a date
warning on top of the real error. The warning therefore lives in
`refunds_page()`; the builder still parses in silence. Restructuring JO's
builder to IQ's signature was the alternative — rejected as three call sites
of churn for a cosmetic fix. **This asymmetry is now deliberate; don't
"unify" it without re-reading this note.**

Verified live across all four pages: malformed dates warn, valid and absent
dates stay silent, and an invalid retail refund POSTed with
`?date=2026-08-25garbage` renders **only** its real validation error. 25-route
sweep clean, 6 tests pass.

Shipped as **JO v1.8.2**. IQ unchanged — it already behaved this way.

**Still divergent, deliberately:** both apps use a comma rather than an em
dash in the appointments `week=`/`day=` message ("That date wasn't valid,
showing today instead."). It is identically inconsistent in both, so it was
left alone — fixing it in one would create a divergence, not close one.

---

## 23. Test coverage and a restore drill — 2026-08-25

Three pieces of work from the same assessment: the apps scored well on
schema discipline and security posture, and badly on having almost nothing
automated. 5 tests guarded 13,838 lines of Python, none of them touching
money, and there were no frontend tests at all.

### 23.1 Money-path tests — both apps

`tests/test_money.py` in each app, plus a shared `tests/conftest.py` that
sets `SECRET_KEY` and `sys.path` so `import app` works. **No database, no
Docker, no running app** — the money math is what most deserves checking on
every change, so checking it had to be free.

The two files make **deliberately opposite assertions** and must never be
merged or copied across:

| | IQ | JO |
|---|---|---|
| a 100-unit subtotal | asserts it becomes **250** (never show a real charge as free) | asserts **0.100 stays 0.100** (inflating it overcharges) |
| rounding | half-up to a 250 note, explicitly *not* banker's | none; exact to 3dp |
| float | tolerated, because rounding scrubs the dust | **must raise TypeError** |
| leftover 0.5 | rounding artifact, reads as paid | **real debt, must read Partially Paid** |

Each suite ends with named regression guards for bugs that actually
happened, and JO's includes one guarding the copy-paste that would do the
most damage: if IQ's 250-rounding were ever ported across, 20 tests fail.

### 23.2 Frontend tests — both apps

`tests/test_frontend.py`, 16 tests each. Static analysis of `style.css` and
`templates/` — **not a browser**, and it cannot tell you a page looks right.
What it does is catch the classes of breakage that had only ever been found
by a person noticing them: a hardcoded colour outside the palette (§8), a
`var(--token)` that no longer resolves (renders as *nothing*, not as an
obviously wrong colour), a token defined only inside a theme block, the
palette blocks drifting apart (§12), the `min-width: 0` flex/grid guards
being deleted (§19, §16), and `focus-visible` / `folder-browser-row` / the
44px targets / the 16px mobile input size being dropped — every one of
which is invisible on a desktop browser.

IQ's version additionally asserts all four palette/theme combinations
define the same token set; JO's asserts its single dark theme covers every
colour token. That is the one place the two files genuinely diverge.

**Every assertion in all four files was mutation-checked** — the bug each
guard describes was deliberately reintroduced and confirmed to fail the
suite. Two findings came out of writing them:

- **IQ had no upper bound on money input**, where JO rejects anything above
  `MAX_MONEY`. IQ accepted `1e18` as a price and relied on the reactive
  `NumericValueOutOfRange` handler downstream. Now bounded at
  999,999,999,999 IQD — a deliberate sanity check rather than a column limit
  (IQ's money columns are `DOUBLE PRECISION` and have no structural
  ceiling), sized to mirror JO's twelve significant digits and to stay
  ~9000x below 2**53, where float64 stops representing integers exactly.
  That margin matters here specifically because IQ's model does integer
  arithmetic on these values (`% 250`).
- **One assertion was wrong, not the code.** Python parses Arabic-Indic
  digits, so `٢٥٠` is a valid 250 in *both* apps. Correct for the clinics
  this was built for, so it is now locked in deliberately rather than left
  as an accident.

Totals: IQ 130 tests / 0.51s, JO 112 tests / 0.35s.

### 23.3 Restore drill — shared workspace tooling

`scripts/restore_drill.sh {iq|jo}` — see `CLAUDE.md` §6 for what it checks.
Backups were the remaining gap that could cost real data: both apps back up
diligently and nothing had ever restored one.

**First drill run, 2026-08-25 — JO PASSED.** Newest backup restored: 44/44
tables, 78 foreign keys, 98 rows across the core tables, 5 user accounts, no
orphaned patients, `billing.total` back as `numeric` with nothing exceeding
3 decimal places, and the app connected and queried it.

**IQ FAILED — and correctly so: there is no IQ backup anywhere on this
machine.** That is a real finding, not a script problem. IQ's backups have
never been exercised because no IQ install is running here.

The drill was validated against three deliberately broken backups: a
truncated file, a correctly-sized file of random bytes, and a
*structurally perfect* archive containing no rows — which restores cleanly,
keeps all 78 foreign keys and lets the app boot. All three fail. A check
that cannot run is treated as a failure rather than skipped, after the
first version of the money check silently skipped on a wrong column name
and still reported a pass.

---

## 24. Real-data damage audit and drill on the ~/Downloads JO install — 2026-08-26

Read-only audit of the actual install at `~/Downloads/vetclinicsystemjo-data`
(Postgres in `vetclinicsystemjo_postgres`, active release `app_v1.8.2`),
checking whether the bugs fixed on 2026-08-25/26 had already written bad
data before the guards existed.

**All 16 checks returned zero.** Nothing to clean up.

| checked | rows found |
|---|---|
| negative inventory cost, visit weight, inpatient weight (§v1.8.4 gaps) | 0 |
| negative operating cost (§v1.8.6) | 0 |
| boarding stay ending before it began (§v1.8.6) | 0 |
| negative distributor lead time (§v1.8.6) | 0 |
| settlement with a null period (§v1.8.5 crash) | 0 |
| bills where paid exceeds total | 0 |
| money values beyond 3 decimals | 0 |
| negative payments; sale total above subtotal; change above cash received | 0 |
| orphaned patients, visits, or payments | 0 |

**What this does and does not prove.** The visit data spans 2026-07-27 to
2026-08-23 and is the demo set seeded on 2026-08-25 — a clean result on
data this young and this synthetic is close to expected. It is real evidence
that nothing in the app *wrote* bad rows during normal use, and no evidence
at all about a database carrying years of real clinic history. Re-run the
same queries against a genuine deployment before drawing any comfort from
them.

**Backup posture, observed rather than assumed:** nightly and manual backups
land in `~/Desktop/backups`, pre-update snapshots in the install's own
`backups/pre_update/`, retention 30, and `backup_log` shows five consecutive
successes with no errors. The install is on `app_v1.8.2` against a current
`v1.8.8`, and it carries `sales.idempotency_key`, so it sits on the safe
side of the migration bug fixed in v1.8.7 — it can take the update.

**Monthly restore drill, run 2026-08-26 against the newest real backup
(`vetclinicsystemjo_backup_20260825_105340.dump`): PASSED.** 44 tables, 78
foreign keys, 98 rows across the core tables, 5 accounts, no orphans,
`billing.total` back as `numeric` with nothing over 3 decimals, and the app
connected and queried it. The drill notes 44 restored against a schema that
now defines 46 — expected, since the backup predates the two most recent
migrations.

---

## 25. Updater tested end to end against a real GitHub repo — 2026-08-26

The in-app updater sat at 0% coverage throughout, and I declined to fake it:
mocking a GitHub download and a health probe only proves the mocks behave
like the mocks. With a scratch repo available (`aldbabiomar/scratchup`) it
could be exercised for real instead.

**Method.** A throwaway "clinic" was built to the real versioned-release
layout — a `clinic-data/` with `.env` and `active_release.txt`, a
`clinic-releases/app_v9.0.0/` with its own venv, and a disposable Postgres
— pointed at the scratch repo via `GITHUB_REPO`. Four genuine releases were
published there and the updater was driven against each. Nothing was mocked
and nothing touched either real repo.

| scenario | expected | result |
|---|---|---|
| v9.0.0 → v9.0.1, a normal update | applies | **applied**, all six steps |
| rollback to the previous release | reverts | **reverted** |
| v9.0.2 — tag `v9.0.2`, VERSION file `8.8.8` | refused at validation | **refused**, download cleaned up |
| v9.0.3 — valid metadata, app raises at import | refused at the health probe | **refused**, never switched |

**What was verified after the successful update**, rather than taken from
the "ok" it returned: `active_release.txt` moved to `app_v9.0.1`; the new
`VERSION` read 9.0.1; a marker file present only in 9.0.1 was on disk in the
live release, proving the new files are what actually run; the previous
release was kept for rollback; a new venv was built; a pre-update backup was
written to `clinic-data/backups/pre_update/`; and the updater then reported
no update available.

**Both failure paths left the install exactly as it was** — same active
release, same two release folders, no partial directory abandoned. The
health-probe refusal is the important one: it means a release that installs
but cannot boot never becomes the running version.

**Caveat worth keeping.** This exercised the mechanism, not every
environment. It ran on macOS with a local Postgres and a fast network; it
says nothing about Windows, a proxy, a half-downloaded tarball, or a machine
that loses power mid-switch. The four scenarios above are the ones that can
be reproduced on demand.

The scratch repo still holds `v9.0.0`–`v9.0.3` and the app source at those
tags. They are inert test artifacts; delete the repo's releases whenever
convenient. Neither real repo was written to — verified afterwards: IQ still
at `v1.10.8`, JO at `v1.8.9`.

---

## 26. IQ now has a backup, and the drill passes for both apps — 2026-08-26

Since `scripts/restore_drill.sh` was written it had never passed for IQ, for
the honest reason that no IQ backup existed anywhere on this machine. That
is now closed.

**Method.** The isolated IQ environment was seeded through the app's own
routes — ten owners, patients and visits with bills and payments, created
by POSTing the real forms rather than by writing SQL, so every stored total
went through `compute_bill_totals()` and the 250-rounding. A backup was then
taken through `backup.run_backup()` itself, not by calling `pg_dump` by
hand, and written to `~/Downloads/vetclinicsystemiq-data/backups/` mirroring
JO's layout.

**First IQ drill: PASSED.** 44/44 tables, 78 foreign keys, 132 rows, 2
accounts, no orphans, `billing.total` back as `double precision`, every
non-zero bill a whole multiple of 250 IQD, and the app connected and
queried it.

**Two bugs in the drill script itself, both found by that run and both
mine:**

- `q()` piped psql output through `tr -d ' '`, which strips spaces
  *inside* values as well as around them. `double precision` came back as
  `doubleprecision` and the money-type check failed against a database that
  was entirely correct. Now trims only leading and trailing whitespace.
- the expected table count used `grep -c 'CREATE TABLE'`, which counts
  prose: comments in `schema_postgres.sql` mention "CREATE TABLE IF NOT
  EXISTS" when explaining why something lives where it does. IQ read 49
  against 44 real statements, JO 46 against 44 — so a complete restore
  reported as short, with a reassuring "expected if the backup predates
  recent migrations" note that was simply wrong. Now anchored to the start
  of a line.

Both drills now report 44 restored against 44 defined, with no spurious
note. **JO re-verified after the fix: still passes.**

A drill that says PASSED for the wrong reason is the same failure mode as a
test that passes while testing nothing — worth recording, because both of
these made the output *look* more reassuring than the truth.

---

## 27. POS "Complete Sale" did nothing — and every test passed — 2026-08-26

The user reported Complete Sale might be silently broken. It was, in **both
apps, for every sale**, since IQ v1.5.0 / JO v1.1.0 (2026-08-23) — 25 of 41
IQ releases and 29 of 33 JO releases.

**Cause.** `prepareSubmit()`, the button's own `onclick`, ended with
`btn.disabled = true; return true;`. A submit button disabled *during its own
click handler* cannot submit its form: the browser reads the submitter's
disabled state when it processes the submit, by which point the handler has
already set it. The line was added as double-submit protection and prevented
every submit instead. No request, no navigation, no console error — the cart
stayed put and the button greyed out, so it read as a hang.

Confirmed by driving Chromium: zero POSTs, zero rows in `sales`. Neutralising
only that one line made the identical click POST and write the sale. Fixed by
moving the disabling into the form's own `submit` handler, which runs once
submission is under way; the `if (btn.disabled) return false` guard stays, so
a triple-click still yields exactly one POST and one sale. Shipped as IQ
v1.10.9 / JO v1.8.10.

### 27.1 Why 371 passing tests missed it

This is the part worth carrying forward.

| Layer | Why it passed |
|---|---|
| Route tests | POST to `/pos/checkout` **directly**; never touch the button |
| Browser tests | loaded `/pos`, asserted no JS errors, no overflow, no collapsed controls — all true, all irrelevant: **they never clicked anything** |
| Frontend tests | read templates as text |

**A page that loads perfectly can still have a button that does nothing.**
Coverage measured 68% and the POS checkout route was among the best-covered
code in the app. Neither fact had any bearing on whether a cashier could ring
up a sale.

Two interaction tests now exist in `tests/test_browser.py` — one asserting the
click produces a real POST and leaves the page, one asserting a triple-click
yields exactly one checkout request. Both mutation-checked: reintroducing the
line fails the first with a message naming the cause.

### 27.2 The sweep for other instances

Every submit button in both apps was then checked, two ways.

**Statically:** four buttons carry an `onclick="return prepare*Submit()"`
gate. Only POS's disabled a submitter. `settings.html` disables a button
inside `checkForUpdates()`, but that is a `fetch`, not a form submit, so it is
correct. The barcode print buttons are `type="button"`. **POS was the only
instance.**

**Dynamically:** a detector was written for the *signature* rather than the
known cause — click every submit button and require that **something**
observable happened: a POST, a navigation, HTML5 validation, or a visible
message. None of those means silent failure.

- 13 (IQ) and 14 (JO) directly visible submit buttons — all clean.
- Half of all submit buttons sit inside modals and are invisible until one is
  opened. A second pass opened each modal first: 7 (IQ) and 9 (JO) more, all
  clean.

**⚠ That dynamic sweep is destructive.** It clicks real submit buttons, so it
performs real actions — it deactivated the test item mid-run, which then made
POS search return nothing and briefly looked like a second bug. It is a
throwaway-database tool only. The scripts were not kept for that reason; the
two targeted interaction tests were.


---

## 28. Divergence audit 7.6 closed — the date-field guard, strengthened — 2026-08-26

The last open finding in `audits/IQ_JO_DIVERGENCE_AUDIT.md`. JO had
`tests/test_no_raw_form_dates.py`, a static guard against a date form field
reaching a query without `clean_date()`; IQ had nothing equivalent. It was
assessed on 2026-08-25 and deliberately left open as low value, because
porting it as written would have copied three weaknesses. All three are now
fixed, in **both** apps.

**What was wrong with the original, demonstrated rather than asserted.** A
throwaway probe ran the old rule and the new one against ten synthetic cases.
The old rule got three wrong:

| Case | Old | New |
|---|---|---|
| `request.form.get("visit_date")` read directly | **missed** | flagged |
| a form alias not named `f` (`g = request.form`) | **missed** | flagged |
| a legitimate `clean_date(` call split across two lines | **false positive** | accepted |
| the other seven (bare `.get`, default arg, subscript, ternary bug shape, wrapped, non-date field, non-form object) | correct | correct |

The two misses matter because both idioms are live in these apps — there are
37 direct `request.form.get(`/`request.form[` reads per app that the old rule
could not see at all. The false positive matters because it would have
blocked a reasonable refactor.

**The fix, tailored per app rather than shared** (`CLAUDE.md` §1). It scans
every root `*.py` module instead of `app.py` alone; it captures the form
object in the regex instead of assuming the variable is named `f`, resolving
aliases per module from the actual `x = request.form` bindings; and it matches
the whole source rather than line by line, so a wrapped call spanning lines is
recognised. The allowed-wrapper list differs on purpose: **IQ's is
`clean_date(` only; JO's also allows `clean_date_filter(`**, its read-side
`?date=` filter helper from §22, which IQ has no equivalent of. The docstring's
citation of `data_integrity_framework.md` — a file that exists in neither repo —
is replaced by a pointer to §21, the real incident.

**Anti-vacuity, which is the actual point.** The first version of the probe
reported "0 offenders" for both apps, and it was wrong: it was matching
*nothing at all*, because the object-name backtracking was broken. The real
answer happens to be 0 offenders too, so the vacuous result and the true
result were identical on the surface — caught only by instrumenting the probe
to report how many date reads it had *seen* (21 per app) rather than how many
it rejected. That is `CLAUDE.md` §7.3 in its purest form, hit while writing a
test whose whole purpose is to prevent it.

The shipped test therefore carries three things the original did not:
- **two control tests** — six known-bad shapes must all be flagged, five
  known-good shapes must all be accepted;
- **an anti-vacuity floor** — the scan must see at least 10 date form reads,
  so a detector that quietly stops matching fails instead of passing;
- **mutation proof**, below.

**Mutation-checked, both apps** (`CLAUDE.md` §7.3, and `TRANSITION_NOTES.md`
trap #6 — the mutation was confirmed to have actually changed the file, and
trap #7 — `app.py` was backed up by copy, never reverted with `git checkout`):

| Mutation | Result |
|---|---|
| unwrap a real `clean_date(f.get("date"))` in IQ `app.py:2146` | **fails**, naming `app.py:2146: date field 'date' read from f without clean_date()` |
| the same in JO `app.py:2156` | **fails**, naming `app.py:2156` |
| break the detector regex so it matches nothing | **fails twice** — the anti-vacuity floor ("found only 0 date form reads across 17 modules") *and* a control ("detector missed a real offender: bare .get") |

Both `app.py` files were restored and verified byte-identical to their
backups, and all three tests pass green in both apps afterwards.

**Result: 3 tests per app, pure tier, no database, ~0.1s.** Both apps report 0
offenders across 21 date form reads — the codebases were already correct, as
the 2026-08-25 assessment said. The value is the tripwire, and unlike the
original it has now been shown to trip.

---

## 29. Operational monitoring, Layer 1 — the local self-check — 2026-08-26

First of the four layers in `features/MONITORING_FEATURE_PLAN.md`, built in
both apps. **Not released** — the plan ships all four layers in one release
per app (§6), and the pre-release soak (§6.1) has not been run. `main` is
deployable in both apps either way.

**What exists now:** `selfcheck.py` per app, a `self_check_log` table, two
scheduler jobs (daily at backup time + 20 minutes, and one 30 seconds after
startup), two settings, a Dashboard banner, and a Dashboard modal at three
consecutive failing days. Nine checks: `backup_never`, `backup_stale`,
`backup_failing`, `backup_stranded`, `backup_dir_missing`,
`backup_dir_unwritable`, `disk_low`, `migration_failed`,
`update_rolled_back`, `restore_unverified`, plus `db_unreachable`.

### 29.1 Two claims in the plan's §0.2 are wrong

The plan says to diff these before editing. Diffing them is what showed the
plan itself was overstating the divergence — recorded here per its own §7.

| Plan's claim | Actual |
|---|---|
| `logic.backup_alert_message()` "**differs from IQ**; do not copy one over the other" | **Byte-identical in both apps.** Extracted and diffed the full function: 25 lines, zero differences. |
| `scheduler.py` "77 lines / 78 lines — **files differ**; diff before editing" | Line counts are right, but the *only* difference is one comment line in JO (`See ERROR_500_AUDIT.md E-01.`). No functional divergence. |

The advice ("diff first") was right; the implied conclusion ("these are
meaningfully different") was not. Worth knowing before someone writes a
branch to paper over a divergence that does not exist.

### 29.2 Decisions the plan did not settle

- **"Not applicable" is not the same as "could not run."** The plan says a
  check that cannot run must record a `warn` rather than pass quietly. Taken
  literally, `update_rolled_back` would warn every single day on any install
  not using the versioned-release layout, which is a permanent and
  by-design state — precisely the cry-wolf noise §6.0 warns against. So a
  check whose *precondition does not apply* returns no finding, while a check
  that genuinely fails still warns. Both paths are tested.
- **`selfcheck_enabled` could not go through the generic settings loop.** That
  loop treats a missing key as "leave unchanged", and an unchecked checkbox
  submits nothing at all — so the setting could be switched on and never off.
  It gets a hidden `selfcheck_present` companion field and explicit handling.
  Verified live in both apps: off → `0`, on → `1`, banner follows.
- **The Dashboard reads the last *recorded* result, it does not run a fresh
  check.** `run_self_check()` probes the disk and write-tests the backup
  folder; doing that on every dashboard load would be absurd.
- **The modal streak counts calendar days, not runs**, so a machine restarted
  six times in a morning cannot escalate by lunchtime; and the streak ends at
  the most recent *recorded* day rather than at today, because a machine
  that was off for two days has no rows for those days. The Dashboard
  additionally requires the latest result itself to be `fail`, so a stale
  streak alone cannot raise a modal.
- **`backup_dir_missing` and `backup_dir_unwritable` are one function.** They
  are one question asked in two stages; reporting both at once would
  double-count a single fault.

### 29.3 Verified live, both apps

Not inferred from tests — driven against both running apps in their isolated
environments:

- the **startup job fired on its own** and recorded a real verdict 30s after
  boot: `backup_never` + `backup_dir_missing` (fail), `restore_unverified`
  (warn) — all true for a fresh install
- the Dashboard banner rendered with those findings; no modal at one failing
  day; the modal appeared once three consecutive failing days existed
- settings round-trip including the checkbox off/on, and the range guard
  (`99` rejected with "must be between 1 and 30", nothing stored)
- **the healthy path clears**: after a real backup written by the app's own
  `run_backup()`, plus a verified-restore result, both apps report `ok` with
  **zero findings** and a completely clean Dashboard
- JO additionally showed the designed intermediate state — `warn` carrying
  only `restore_unverified` — after a real backup but before Layer 4 exists

Full suites green with a database: **IQ 396 passed / 1 skipped, JO 378 passed
/ 1 skipped**, zero failures. (A `PythonFinalizationError` from
`psycopg_pool` at interpreter shutdown appears in both — it reproduces on
test files untouched by this work, so it is pre-existing and unrelated.)

### 29.4 Mutation checks, and the one that did not apply

23 tests per app. Mutation-proven per `CLAUDE.md` §7.3:

| Mutation | Result |
|---|---|
| the self-check runs no checks at all (always `ok`) | **10 of 23 fail** |
| `backup_stale` ignores the configured threshold | **fails**, naming the setting |
| `record()` does not prune the log | **fails** — "expected the log pruned to 5 rows, found 12" |

The third one is the lesson. Its first attempt **silently failed to apply** —
the anchor did not match, the mutation script raised, and the suite passed
23/23. That looks exactly like a test that cannot catch the bug
(`TRANSITION_NOTES.md` trap #6). Checking *why* it passed revealed there was
no retention test at all; one was written, and only then did the mutation
fail as it should. A retention bug is not hypothetical here — `backup_retention`
of 0 meaning `files[0:]`, i.e. delete every backup, shipped as IQ v1.10.7.

---

## 30. Operational monitoring, Layer 4 — the self-verifying backup — 2026-08-26

Second of the four layers. **Still not released** — Layers 2 and 3 remain, and
the §6.1 soak has not run. Built before Layers 2/3 per the plan's dependency
order: `selfcheck`'s `restore_unverified` finding and the heartbeat payload's
`verified_*` fields both read this layer's output.

**What it does.** Once a month (backup time + 45 minutes, on the 1st) it
restores the newest successful backup into a throwaway database and asks
whether what came back is actually a clinic's records: schema restored,
foreign keys present, core tables populated, at least one account that could
log in, no orphaned patients, and the money column intact. The result is
stored in `settings.last_verified_restore`, and the same job re-runs the
self-check so the finding clears in the same pass.

**A Python port of `scripts/restore_drill.sh`, with one deliberate
difference:** the drill restores into a throwaway *container*, which needs
Docker. This restores into a throwaway *database on the Postgres server the
app is already talking to*, so it works on a clinic machine where nobody has
Docker permissions.

**Guard rails**, all tested: it never touches the live database (the only
statements issued there are `CREATE`/`DROP DATABASE` for the throwaway); it
never deletes or modifies a backup file; the throwaway is dropped in a
`finally` **including on timeout and on a failed restore**; a 10-minute hard
timeout; and if `pg_restore` is unavailable it records a **warning, never a
pass**.

### 30.1 The money divergence — the one place it shows in this feature

This is the only module in the monitoring work where IQ and JO genuinely
differ, and they differ in the same way `test_money.py` does:

| | IQ | JO |
|---|---|---|
| `MONEY_EXPECTED_TYPE` | `double precision` | `numeric` |
| Extra invariant | every non-zero bill is a whole multiple of **250 IQD** | no bill exceeds **3 decimal places** (1 fils) |

JO's copy additionally asserts `DENOMINATION` does **not exist** in its
module, so IQ's note-rounding can never be ported across silently.

### 30.2 A real bug, found by a test that had to be written twice

The first version of the money test asserted only that the money check *ran* —
its name appeared in the results. That is not the same as the check being able
to **fail**, and the mutation proved it: making the type check accept anything
left all 10 tests passing.

Rewriting it to build a structurally valid database whose *only* fault is the
money column's type — every other check arranged to pass, so a failure
isolates the money assertion — then caught a genuine bug **in JO only**:

> Postgres's `scale()` accepts only `numeric`. On the one input the check
> exists to catch — a backup whose `total` came back as `double precision` —
> the bare `scale(total)` **raised**. The broad handler turned that into
> `warn` ("could not run") instead of `fail`, and discarded the type-check
> failure that had just been recorded. The single most important negative
> result in this layer became a shrug.

IQ was unaffected because its 250-check already casts (`total::numeric`).
Fixed with an explicit `::numeric` cast, and separately: **a check that raises
is now recorded as a failed check rather than escaping to the "could not run"
handler** — the inputs most likely to make a check raise are exactly the
malformed backups this layer exists to reject, so an exception is evidence
*against* the backup, not an inconclusive result.

### 30.3 Verified

The three deliberately-broken backups `restore_drill.sh` was validated
against (§23.3) are now automated tests, and all three fail verification:

| Backup | Result |
|---|---|
| truncated file | not a pass, throwaway dropped |
| correctly-sized file of random bytes | not a pass, throwaway dropped |
| **structurally perfect, zero rows** — restores cleanly, keeps every foreign key, app would boot | **fail**, on `core tables populated` |

Plus: a wrong-money-type backup fails on exactly the money check, with a
control proving the identical database with the *right* type passes.

Mutation-checked, both apps — always-pass, never-drop-the-throwaway,
money-check-accepts-anything, and (JO) removing the `::numeric` cast all fail
the suite. **Zero leaked throwaway databases** in either app: counted before
and after a full run, 0 → 0. The five that did appear were the deliberate
never-drop mutation's doing, which is what that mutation was for.

Scheduler wiring verified live: all four jobs registered with the right
triggers, and `reschedule()` moves all three cron jobs including the wrap past
midnight (23:50 → self-check 00:10 → verify 00:35).

End to end in both apps: `fail` → real backup → verification `pass` (7 checks)
→ setting stored → self-check `ok` with zero findings.

Suites green with a database: **IQ 409 passed / 1 skipped, JO 390 / 1.**

---

## 31. Operational monitoring, Layers 2 & 3 — the heartbeat and its payload — 2026-08-26

The last two layers. All four are now built in both apps. **Still not
released** — the §6.1 soak has not run, and that is the only remaining gate.

**What it does.** After the daily self-check, in the same job so the verdict
can never be yesterday's, the app POSTs a small JSON payload to whatever URL
the admin has put in Settings. **The signal is the ABSENCE of a ping**, not
its contents — the receiver alerts when one fails to arrive, which is the only
mechanism in this whole feature that covers "the machine is off", "Docker did
not start", "the app crashed at boot". None of those can report themselves.

### 31.1 Decisions worth knowing

- **The startup self-check pings too**, and that matters more than it looks. A
  clinic that switches its machine on at 8am and off at 6pm is asleep when the
  02:20 job is due, so the startup ping is the **only** ping it will ever
  send. Without it every such clinic would look permanently dead. This is not
  in the plan; it was found by asking what a real clinic's day looks like.
- **Disabled is the default and is not a finding.** No URL → nothing is sent,
  `(True, "disabled")`. An app that phones home by default is not acceptable
  for clinic software.
- **A failed heartbeat is never escalated to the clinic.** They cannot act on
  it, and a red banner about monitoring would train them to ignore the banners
  that matter.
- **The URL is a credential**, and is treated as one: `https://` enforced on
  save, never written to a log, and never included in a returned message —
  `requests` embeds the full URL in its exception text, which is exactly how a
  credential reaches a log file, so only the exception *type* is reported.
  Anyone holding a healthchecks.io ping URL can send a fake ping and thereby
  **suppress a real alert**.
- **The receiver is not assumed to be healthchecks.io.** It is a plain text
  setting, one per install, so a clinic can move to a self-hosted receiver
  with no code change.

### 31.2 The payload, and what is deliberately not in it

Counts and statuses only: install id, app, version, timestamp, status,
findings (worst 10), a backup section (timestamps, sizes, consecutive
failures, last verification), a db section (table count and row counts for
`owners`/`patients`/`visits`/`sales` only), free disk, uptime. **Real
measured size: 821 bytes** against a 4 KB cap.

Never included: owner/patient/staff names, phone numbers, addresses, notes,
**any money figure**, free text from user-entered fields, or full file paths —
a backup path routinely contains a person's account name, so only sizes and
timestamps travel, never `filepath`.

> **One disclosure the payload cannot prevent, recorded so it is not a
> surprise.** The receiver necessarily sees the clinic's **public IP address**
> and the timing of every ping — healthchecks.io displays it (`HTTPS POST from
> …`). So a receiver learns each clinic's public IP and its daily
> online/offline rhythm even though the body carries nothing personal. That is
> true of any HTTP receiver, self-hosted included. It is small, but it is a
> real disclosure and an admin should know before pasting a URL in.

### 31.3 Verified against a real receiver

Not mocked. A real healthchecks.io check (the user's TESTURL project):

- **IQ pinged: HTTP 200**, and the receiver displayed the payload byte for
  byte — confirmed by the user from the healthchecks.io side.
- **JO pinged: HTTP 200**, with a **different `install_id`** (`E91CE662` vs
  IQ's `D6D481CC`), which is the property that lets one monitoring account say
  *which* clinic went quiet.
- `self_check_log.reported_at` set on success, and left NULL on failure.
- Settings round-trip live: the section renders, `http://` is refused with
  "must start with https://" and the stored value is left untouched, `https://`
  is accepted, blank disables — and the URL never appeared in the app log.

Mutation-checked, both apps: sending when the URL is empty, adding an owner
name to the payload, and letting the URL leak into the failure message all
fail the suite.

Suites green with a database: **IQ 424 passed / 1 skipped, JO 405 / 1.**

### 31.4 A plan contradiction, and the settings that resolve it

Plan §2.3 says one check per install, **period 1 day, grace 36 hours**. Plan
§6.1 says the soak is *"stop the app for 48 hours and confirm the receiver
alerts."* **Those disagree**: 1 day + 36 hours means the alert fires at ~60
hours, so at 48 hours nothing would have happened and the soak would look
like a failure when it was working correctly.

Resolved in favour of §2.3's numbers: the grace is a considered decision about
false alarms (the app pings once daily just after the backup, so a machine off
for one night pings ~48h apart, and a tighter grace would page for a clinic
that simply closed on a Sunday — the same "one missed night is noise, two is a
pattern" logic as the 2-day backup staleness threshold). **§6.1's "48 hours"
should be read as "leave it stopped until the alert arrives" — budget ~60
hours.**

For the throwaway test check, period and grace of 5 minutes each make the
absence path observable in ten minutes rather than two and a half days.

---

## Index — every section, and when to read it

Added 2026-08-26. This file is append-only, so the sections below are in
chronological order, not order of importance. **The ones marked ⚠ describe
a real bug that shipped** — read those before touching the area they name.

| § | Subject | Read it when |
|---|---|---|
| 1 | the money models, roles, frontend, updater, security | **always, before anything money- or permission-adjacent** |
| 2 | module-by-module differences | porting a feature between the apps |
| 3 | feature inventory — what exists in one app only | asked 'does JO have X?' |
| 4 | known-open items (superseded by §18) | rarely — §18 replaces it |
| 5 | planned parity work | historical |
| 6 | Clean Up feature + audit rollout | touching bills, discounts or write-offs |
| 7 | desktop shortcut | the launcher or autostart |
| 8 | off-palette colour literals | any CSS change |
| 9 | ChamPet accent, folder-browser row | IQ palettes |
| 10 | ⚠ backups prompting for a password in Terminal | anything in `backup.py` |
| 11 | sticky table headers | tables |
| 12 | dark mode for JO, IQ contrast fix | colours or themes |
| 13 | light-palette contrast to AA | colours |
| 14 | amber via a `--warn-ink` split | colours |
| 15 | inventory refresh | inventory |
| 16 | mobile / tablet pass | responsive CSS |
| 17 | shutdown-triggered backup ported to JO | backup triggers |
| 18 | **still open, deliberate divergences** | **before assuming something is a bug** |
| 19 | boarding discount, over-narrow modals | boarding or modals |
| 20 | full line-by-line divergence audit, 7.1–7.5 closed | looking for known divergences |
| 21 | ⚠ `parse_date` validated a prefix, not the value | dates, filters, or `logic.parse_date` |
| 22 | JO date-filter warnings made consistent | list-page filters |
| 23 | **test coverage + the restore drill** | **writing any test** |
| 24 | real-data damage audit on the ~/Downloads install | checking for damage from a bug |
| 25 | ⚠ updater verified end to end | anything in `updater.py` |
| 26 | IQ backup + both drills passing | backups or `restore_drill.sh` |
| 27 | ⚠ **POS Complete Sale did nothing, and every test passed** | **before trusting a green suite** |
| 28 | divergence audit 7.6 closed; the date-field guard, strengthened | writing a static/grep-style guard test |
| 29 | **monitoring Layer 1 built (unreleased)**; two plan claims corrected | working on monitoring, or `scheduler.py` |
| 30 | ⚠ monitoring Layer 4, the self-verifying backup; a JO-only money bug | backups, restores, or anything money-type-adjacent |
| 31 | monitoring Layers 2 & 3, the heartbeat and payload; receiver settings | the heartbeat, payload privacy, or configuring a receiver |

### The four sections a new session should read first

1. **§1.1** — the money models. IQ is `float` with 250-IQD note rounding and
   an anti-"looks free" floor; JO is exact 3-decimal `Decimal` with neither.
   Every money bug in this project traces back to someone assuming these are
   the same.
2. **§18** — what is divergent *on purpose*. Saves you "fixing" something
   deliberate.
3. **§23** — how the test suites are built and what they assert. Also
   `CLAUDE.md` §7.
4. **§20 and §25–26** — the audits and what they missed. §21 exists because a
   twelve-section line-by-line audit missed a reproducible 500 that a
   five-minute test run caught.

