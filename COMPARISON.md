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

**2026-09-01 — this section was right, and `CLAUDE.md` §1 was not.** Every
correction above was recorded here on 2026-08-23. `CLAUDE.md` §1 nevertheless
went on listing custom role creation, backup restore, the folder browser and
the JS framework as IQ-only until it was rewritten on 2026-09-01, and
`CLAUDE.md` §2 step 5 still claimed JO had 3 fixed roles. Nobody re-checked;
the claims simply aged. Noted here because `CLAUDE.md` loads automatically
every session and this file does not, so the stale copy was the one being
read first. `CLAUDE.md` §1 now says that when the two disagree, this file
wins.

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

## 32. The soak found a real bug: missed jobs were silently skipped — 2026-08-27

The monitoring soak paid for itself on its first night, on a real install,
by finding something worse than the feature it was testing.

### 32.1 What happened, and the theory that was wrong

The nightly backup did not run on 2026-08-27, and no heartbeat was sent. The
first hypothesis — reasonable, and acted on — was that backups require a
logged-in account, since the web session had expired overnight.

**The data disproved it**, and the disproof is worth keeping because it is
exactly the kind of plausible theory that sends a fix in the wrong direction:

| Evidence | Meaning |
|---|---|
| `2026-08-26T02:00:00 nightly success` | ran at 2am with nobody using the app — no session required |
| `2026-08-27T02:00` — nothing | that night it did not run |
| `pmset -g log`: Sleep 01:01 → Wake 03:10 ("lid … UserActivity") | the Mac was asleep across 02:00, 02:20 and 02:45 |
| `2026-08-27T03:14:00 nightly success` | worked immediately once awake |

The scheduler is a background thread with its own database connection and no
Flask session, so a login could never have been involved.

### 32.2 The real cause

**APScheduler discards a job whose scheduled time has passed by more than
`misfire_grace_time`, and that defaults to ONE SECOND.** A machine that sleeps
across its backup window does not run the backup late — it does not run it at
all, and says nothing.

For a clinic this is worse than the monitoring feature it was found by: no
backups, silently, on any machine that sleeps overnight.

### 32.3 Two failures, two fixes — they are not interchangeable

This is the third time this shape has appeared in this project, so the
scheduler's docstring now states it directly:

| Unavailability | What happens | Fix |
|---|---|---|
| **ASLEEP** | process suspended, resumes later | `misfire_grace_time=None` + `coalesce=True` — run however late, once |
| **OFF** | process gone, restarts with no memory of what it missed | the startup catch-up; no grace time can help |

The earlier two instances were the startup self-check (§29) and the
verification becoming a daily due-check rather than a monthly cron (§31).

Mutation-checked four ways, both apps. Restoring APScheduler's one-second
default fails two tests. Suites green: **IQ 451 / 1 skipped, JO 432 / 1.**

### 32.4 A trap that cost real time: stale bytecode outliving a reverted mutation

A test passed alone, then failed in the full suite, then failed alone too. The
failure was a **ghost of a mutation that had already been reverted in source**:
an earlier `py_compile` had failed to write `__pycache__` (macOS had revoked
folder access mid-session), leaving a `.pyc` compiled from the *mutated*
scheduler. Python kept loading it.

The symptom is nasty because it inverts the usual trap: `TRANSITION_NOTES.md`
trap #6 warns that a mutation which does not apply looks like a test that
cannot catch it. This is the mirror image — **a mutation that was undone in
the source but not in the loaded bytecode**, so a correct fix looks broken.

`rm -rf __pycache__` resolved it instantly. Worth reaching for the moment
source and behaviour disagree, especially after any interrupted or
permission-denied run.

### 32.5 Windows: starting at boot rather than at sign-in

Prompted by the same investigation, since the deployment target is Windows.
The Startup folder runs at **user logon**, so a PC that Windows Update
restarts at 3am sits at the lock screen doing nothing until someone arrives.

`autostart.py` in both apps now creates a Scheduled Task (`ONSTART`,
`RU SYSTEM`) via `schtasks`, falling back to the Startup folder when not
elevated — and **saying what was lost** rather than reporting plain success.
`disable()` removes both. 10 tests per app, 3 mutations caught.

**Not verified on Windows and cannot be from here.** The tests check the
decisions and the command arguments, not that Windows accepts them.

> **Deployment note that outranks the code:** if PostgreSQL runs under Docker
> Desktop, Docker Desktop itself starts at user logon — so the database will
> not be there either and starting the app earlier achieves nothing. Install
> PostgreSQL as a Windows service. (The user has since decided the clinic PC
> will have no password at all, which sidesteps this: Windows boots straight
> to a desktop, so the Startup entry works and the task is redundant
> insurance.)

---

## 33. The same bug again, one layer down: a frozen clock — 2026-08-28

§32's fix was necessary and **not sufficient**. The second night of the soak
failed the same way: no nightly backup, no heartbeat, a yellow check — and
this time the app had been alive throughout and `misfire_grace_time=None` was
already in place.

### 33.1 The measurement that explains it

```
wall clock since boot :   93.64 h
time.monotonic()      :   48.08 h
difference            :   45.56 h
```

**macOS does not advance `time.monotonic()` while the machine sleeps.**
APScheduler waits on an event with a *monotonic* timeout, so when it computed
"next backup in 22h03m" at 05:11 and the Mac then slept most of the night,
that countdown froze. Wall-clock elapsed was 29 hours; monotonic elapsed was
far less.

**The job was not missed and not late — it never became due.** That is why
misfire grace could not help: misfire handling acts on a run that was
skipped, and nothing had been skipped.

This is the difference between "the alarm went off while you were out" and
"the alarm clock stopped."

### 33.2 The fix: stop trusting timers

A **tick every 5 minutes** that runs whatever the *wall clock* says is overdue
and the database says has not happened — today's backup, today's self-check
and heartbeat, the restore verification. A short interval bounds the damage:
however long the machine sleeps, the tick fires within five minutes of waking
and then decides by wall clock rather than by any countdown.

Every action is gated on "has today's X already happened?", so the tick and
the cron jobs cannot double-run, and on a machine that never sleeps the tick
is a permanent no-op.

The rule now stated in the module docstring: **decide what to run by comparing
the wall clock against what the database says already happened.**

> **Platform note.** Windows' `time.monotonic()` is `GetTickCount64()`, which
> *does* include suspend time — so on the actual deployment target the cron
> jobs probably do fire, and §32's fix alone might have sufficed. "Probably"
> is not a good enough basis for a clinic's backups, and the tick costs two
> cheap queries every five minutes.

### 33.3 Three failures, three mechanisms — none of them redundant

| Unavailability | Symptom | Mechanism |
|---|---|---|
| **OFF** | process gone, no memory of what it missed | `_do_startup_catchup` |
| **ASLEEP, noticed late** | run discarded (misfire default: 1 second) | `MISFIRE_GRACE_SECONDS = None` |
| **ASLEEP, never noticed** | countdown frozen; job never becomes due | `TICK_MINUTES` + wall-clock due checks |

Each was found in production *after* the previous one was declared fixed.
That is the honest record, and it is the argument for the soak existing.

### 33.4 Verified live, not just in tests

On the real install, with the tick deployed: `backup_time` was temporarily set
so the self-check was overdue but the backup was not.

- self-check rows 5 → **6** — the tick ran the overdue check and sent the
  heartbeat at 10:36:50
- backup rows 23 → **23** — it correctly left the not-overdue backup alone

Both halves matter: a tick that acted on everything would take a backup every
five minutes forever. Mutation-checked four ways (long interval, cron trigger
instead of interval, never acting, always acting). Suites: **IQ 458 / 1
skipped, JO 439 / 1.**

---

## 34. Code review of the unreleased monitoring work — nine findings, all real — 2026-08-28

`CODE_REVIEW_MONITORING_2026-08-27.md` (workspace root) reviewed the whole
unreleased range in both apps. **All nine findings were verified against the
code before being fixed, and all nine were genuine.** Two were serious enough
that shipping without them would have been a mistake.

### 34.1 The two that mattered

**The ping URL was written to the audit log (HIGH).** Adding `heartbeat_url`
to the generic settings loop routed it through `auth.log_change()`, which
writes values into `audit_log` — a page readable by **`view_logins_changes`**,
a *broader* permission than `manage_settings`, and included in audit exports.
So a user who cannot open Settings could read the credential and use it to
send fake pings, suppressing the alert that fires when a clinic machine goes
dark.

The instructive part: `heartbeat.py` documents that the URL is "never written
to a log", and `test_heartbeat.py` asserts it at `send()`. **The invariant was
tested at one boundary and violated at another.** A guard proves only the
boundary it stands on. Now logs `"set"` / `"not set"`, with a regression test
at the save path.

**The Windows boot task and the Startup entry collided in a respawn loop
(HIGH).** `_windows_enable()` wrote both, reasoning that a second app copy
exits harmlessly when the port is taken. That much is true — but the launcher
is a **supervisor loop** (`:loop … timeout /t 2 … goto loop`, no port check,
no exit condition), so it relaunches the app every two seconds for the entire
logon session, console window and browser tab included, on every clinic PC
where the boot task succeeded. Exactly one mechanism is now active.

Both were introduced by this work: before it, only the Startup folder existed
and the two could never collide.

### 34.2 The rest

| # | Severity | Finding |
|---|---|---|
| 3 | MEDIUM | `startup_catchup` was the only job left on APScheduler's 1-second misfire default — **and the test filtered it out of the assertion guarding exactly that** |
| 4 | MEDIUM | a psycopg error in `_backup_section` escaped an `except (TypeError, ValueError)` and killed the whole heartbeat: a DB blip became indistinguishable from a dead machine |
| 5 | MEDIUM | `install_id` returned an id it had failed to persist, so a failing write meant a new id every night and a permanent false "went quiet" |
| 6 | LOW | a missing `patients` table rendered a *failing* check as `"None orphaned"` |
| 7 | LOW | `is_due`'s comment disclaimed the daily retry its own code and test implement |
| 8 | LOW | IQ's not-found error named `Start VetClinicSystem IQ.bat`; `setup.py` writes `Start VetClinicSystem.bat` — introduced by the sed-based port from JO |
| 9 | LOW | the `/DELAY` comment said `HHHH:MM`; `schtasks` parses `mmmm:ss` |

Finding 3 is worth dwelling on for the same reason as finding 1: the test
existed, named the right property, and had a filter that excluded the one job
that violated it.

### 34.3 What this says about the work

Three of the nine (1, 3, and arguably 5) are **invariants that were documented
and tested, and still violated** — at a different boundary, or behind a filter
in the test itself. That is a more useful lesson than any individual bug: a
guard is evidence about the exact path it runs on, and nothing else.

Suites after the fixes: **IQ 461 / 1 skipped, JO 442 / 1.** The credential fix
and the respawn-loop fix are both mutation-checked.

The review's own "not reviewed" note stands: the ~2,000 lines of new test code
have not had a dedicated §7.3 pass of their own.

---

## 35. Settings page regrouped, and the 760px breakpoint retired — 2026-08-28

Applied to **both apps**, unreleased (ships after monitoring, per the user's
call). The two pages remain structurally identical apart from IQ's Colour
Palette selector, which JO has no setting for.

**Why.** The whole page was one card holding eleven sections, so the single
Save Settings button appeared to own everything — including Updates, Restore
and the autostart toggle, which are separate forms that act immediately. The
backup story was spread across 250 lines with Updates and Startup wedged
between the folder setting, the history table, and the restore that reads them.

Now four cards: the saved settings in one enclosure ending in a bar reading
"Saves the six sections above", then Backups & Restore, Updates, and Startup &
Shutdown, each tagged *Runs when you click*.

### 35.1 The layout change, and the measurement behind it

`.form-grid` was `1fr 1fr` collapsing at `max-width: 760px` — and **a standard
tablet is 768px**, so an iPad portrait sat 8px on the wrong side and kept both
the expanded sidebar and two columns. This is `TRANSITION_NOTES.md` trap #4
("760px is not a tablet"), which had already shipped twice; the settings page
was a third instance nobody had measured.

Measured on the running app, the cliff:

| Viewport | Columns | Backup-folder field |
|---|---|---|
| 1024px | 324 + 324 | 218px |
| **768px** | **196 + 196** | **182px** |
| **760px** | **682 (one)** | **576px** |

Eight pixels of viewport tripled the usable field width.

Replaced with `repeat(auto-fit, minmax(260px, 1fr))`, so the browser picks the
count from available space. Measured after, identical in both apps: **1280px →
3 × 295px** (three-field sections stop orphaning one onto a second row, which
is what prompted the work), **768px → 1 × 410px** with the path field at
**304px**, **375px → 1 × 297px**, no horizontal overflow anywhere. The
8px-wrong breakpoint stops mattering rather than being re-tuned to another
guess. Long values (the backup path, the ping URL) opt out with `.full`.

### 35.2 Two things worth carrying

- **The app compiles templates once at boot with no auto-reload.** A first
  verification pass showed the CSS change applied and the template change
  absent, which looked exactly like a failed edit. It was a stale template.
  **Restart the app after any template edit**, or you will debug a change that
  was never loaded.
- **Jinja parsing proves nothing about an `{% if %}` you cut inside of.** The
  restructure lifted a block out of IQ's `{% if is_system_admin %}` gate. The
  file parsed either way; a misplaced `endif` parses fine while guarding the
  wrong content. Confirmed against the original that it opens and closes
  around the same content as before.

Suites unchanged by the redesign: **IQ 461 / 1 skipped, JO 442 / 1.**

---

## 36. The 760px breakpoint, swept out of both apps — 2026-08-28

The Settings redesign (§35) turned out to be the **third** instance of
`TRANSITION_NOTES.md` trap #4. That prompted a sweep of every media query in
both apps, and the underlying problem was much larger than any of the three.

### 36.1 It was not a rule, it was the entire mobile switch

`@media (max-width: 760px)` contained the sidebar-to-drawer change, the mobile
topbar, the sticky-header offset, the grid collapse, **and every touch
accommodation in the app**. A standard tablet is 768px, so an iPad in portrait
received none of it. Measured on the running app:

| | 768px | 760px |
|---|---|---|
| Form field font | **14px** (all 15) | 16px |
| Form field height | 37–41px | 44px |
| Buttons | 34–37px | 44px |
| Nav links | 32–34px (**36 of them**) | 44px |
| Appointment "+" button | **21px** | 44px |

Three consequences, worst first:

1. **iOS Safari zoomed on every field and never zoomed back.** `style.css`
   carries the comment explaining exactly this — *"iOS Safari zooms the page
   whenever a focused field is under 16px, and does not zoom back out"* — and
   the rule implementing it was inside the 760px query. The bug the comment
   describes was live on the device the comment describes.
2. **A bug already fixed was still shipping.** `.appt-add-btn { min-height:
   44px }` was IQ 1.10.8 / JO 1.8.9, found by a browser test at 390px. It sat
   inside the same query, so at 768px that button was still 21px tall.
3. **No 44px targets on a touch device**, against a floor the code itself
   cites Apple HIG / WCAG 2.5.5 for.

Not affected: `.stat-grid`/`.panel-grid` (a 900px rule covers them),
`.pos-grid` (900px), tables (1120px). No horizontal overflow at any width.

### 36.2 The fix: ask the browser, don't guess a number

Touch rules now sit behind **`@media (pointer: coarse), (max-width: 900px)`**.
The real condition was never the viewport — it is whether a finger is doing
the pointing. This covers a touch screen at any width and leaves a
mouse-driven desktop untouched at any size; the width half is a fallback for
narrow mouse windows. The shell switch moved to **900px** so a tablet gets the
drawer and its full width; the grid collapse stays at **760**, since with the
sidebar gone there is room for two columns.

Same shape as §35's `auto-fit` change, and the general lesson from both:
**when a fixed number keeps being wrong, the number was the wrong tool.**

Measured after, both apps: 768px gives 16px fields, 44px controls, a 44px
appointment button, a drawer sidebar and 361px stat cards (was 221px).
**1440px, 1024px and 375px are unchanged.**

### 36.3 Why three fixes missed it — the test looked in the wrong place

`test_touch_targets_are_big_enough_on_a_phone` ran on the **phone viewport
alone**, while `VIEWPORTS` already defined a 768px tablet that was checked
only for sideways scrolling. The guard named the right property, cited the
right standard, and never looked where it was violated.

This is the same failure as `COMPARISON.md` §34.3's three findings: an
invariant that was documented and tested and still violated, because the guard
stood on one boundary while another was broken.

Now parametrized over phone **and** tablet, plus a new test asserting no field
is under 16px. **Mutation-checked:** putting the touch rules back behind 760px
fails both tablet cases while **both phone cases still pass** — demonstrating
directly that the old test could not have caught this.

Browser tier actually run for this work (Playwright installed into the
throwaway venv only, never `requirements.txt`): **13 passed per app.**
Non-browser suites: IQ 461, JO 442.

---

## 37. The fix that caused the next bug: two paths, one second — 2026-08-29

Third night of the soak, third real bug — and this one was **introduced by
§33's fix**. Worth recording as its own section precisely because it is the
cost of the belt-and-braces design, and the cost was real.

### 37.1 What the install logged

```
04:02:08  success  nightly
04:02:08  failed   nightly   "Another backup ... is already running"
04:02:08  ok       (pinged)
04:02:08  ok       (not pinged)
```

The machine woke; the cron trigger and the tick both fired in the **same
second**. Two backups, two self-checks, two pings for one night. The
wall-clock due-checks could not prevent it, because **both paths read "not
done yet" before either committed**.

### 37.2 Why it mattered more than it looked

`logic.backup_alert_message()` reads the **newest** `backup_log` row. The
success happened to land with the higher id — had the failed row landed
there instead, the Dashboard would have announced *"The last database backup
failed"* in the same second a backup succeeded. A red banner on a healthy
clinic is exactly the cry-wolf failure the plan's §6.0 says gets a monitoring
feature switched off and never switched back on.

### 37.3 The fix

The redundancy stays — it is the point, and the tick is what actually took the
backup on the two previous nights. What was missing is that the two paths knew
nothing about each other.

Every scheduled write now goes through **`_run_backup_if_due` /
`_run_self_check_if_due`**, which hold a module-level lock across
check-and-run. The cron triggers, the tick and the startup catch-up all call
the same two functions, so the second arrival sees the first's committed row
and does nothing.

Also changed: an install that has **never** self-checked is due whatever the
hour — deliberately unlike the backup catch-up, which waits for its scheduled
time. A self-check is read-only and carries the first heartbeat, so a fresh
install started at 01:00 with a 23:59 slot would otherwise send nothing for 22
hours and look dead to the receiver while showing the admin none of the
problems it can already see.

Mutation-checked: removing the lock reproduces *"2 self-checks ran
concurrently"*; removing the due-check reproduces *"2 backups started
concurrently"* — the same failure the install logged.

Verified on the real install: after the redeploy the startup catch-up
correctly did **nothing**, because today's backup and self-check had already
run. Before the fix it would have produced another duplicate pair.

### 37.4 The pattern across three nights

| Night | Bug | Introduced by |
|---|---|---|
| 26→27 | missed jobs silently discarded (misfire grace = 1s) | original design |
| 27→28 | frozen monotonic clock; job never became due | §32's fix was insufficient |
| 28→29 | two paths raced and duplicated | §33's fix |

Each fix was correct and each exposed the next layer. That is not an argument
against the fixes; it is the argument for the soak. **None of the three was
visible to a green test suite**, and all three were found by one real install
running for three nights.

---

## 38. One card-spacing unit — 2026-08-30

Cosmetic, both apps, unreleased. Recorded because the audit found the drift was
app-wide rather than a Settings problem.

§35's redesign left the four Settings cards butting together: `.card` carries
no margin, and unlike the Dashboard that page had no grid to supply a gap.
Fixed with a `.settings-stack` wrapper — the same mechanism and the same 16px
`.panel-grid` already used, rather than a margin on `.card`, which would double
up with the gap wherever cards *do* sit in a grid.

Auditing the rest of the app then found four different values in use:

| Value | Occurrences |
|---|---|
| 16px | 13 inline + `.panel-grid` |
| 20px | 11 inline |
| 10px | 2 inline |
| 14px | 1 inline + `.stat-grid` |

**Both apps had drifted identically** — the same 13/11/2/1 split — which is
what a fork does: the drift predates the split. None of the outliers carried a
comment or a pattern; they were accumulated one-offs.

Everything is now **16px**, the plurality and what the Dashboard already used.
The unit is documented beside the grid definitions so the next card added does
not restart the drift. Verified live: `.panel-grid`, `.stat-grid` and
`.settings-stack` all 16/16, with measured card-to-card gaps of 16 on both
Dashboard and Settings.

---

## 39. A backup destination that vanished reported as healthy — 2026-08-30

Found while staging soak Test C, which is the second time setting up a test
has found a bug the test was not looking for.

**The symptom:** renaming the backup folder away produced status `ok`.
`os.makedirs(backup_dir, exist_ok=True)` recreated it a minute later, empty,
and the write probe then passed.

### 39.1 Why that is dangerous rather than untidy

`os.makedirs` cannot tell *"first run, the folder is not made yet"* from
*"the destination went away"*. The second is the one that matters, and the
`README` points straight at it: it recommends a **synced folder** (Google
Drive, OneDrive) as the way to get off-site copies. If that folder unlinks or
moves, the app recreates a plain local directory at the same path, backups
keep reporting success into it, and the off-site copy the clinic believes in
has silently stopped — with a green health check on the Dashboard.

An unplugged **external drive** was already caught, because `/Volumes` refuses
the create. The exposure was folders under the user's own home — exactly where
the synced-folder advice points.

**The fix** distinguishes the two cases by asking whether `backup_log` records
a successful backup written *into that folder*. A folder with history that
disappears is reported; a folder with no history is still created, because
that is the helpful first-run behaviour.

### 39.2 The second, worse finding

Every other check trusts `backup_log` — which lives in the **database**, not
the folder. So **every `.dump` file could be deleted and the feature would
report `ok`.** Layer 4 would have caught it, but its cadence is monthly, which
is a long time to believe in backups that are not there.

New `backup_file_missing` check: one `os.path.isfile` against the newest
successful backup. Cheap, and it also covers the vanished-folder case from a
second direction.

### 39.4 The fix was incomplete, and the soak caught that too

Night 2 (2026-08-31): the staged Test C fault **healed itself**. `selfcheck.py`
had been taught not to recreate a vanished destination, but `backup.py` has its
own `os.makedirs` — and the backup runs **first** (02:00 backup, 02:20 check).
So the nightly backup recreated the folder, wrote into it, and the check then
saw a fresh successful backup in a writable folder and reported `ok`.

**The selfcheck fix was effectively dead code in the nightly path**, because
the folder always existed again by the time the check looked. Fixing the
reporting path while leaving the acting path untouched fixed nothing.

`run_backup` now applies the same distinction and **refuses**, recording a
failed backup so the Dashboard surfaces it. Nothing is written: a backup saved
somewhere nobody can find is worse than one that failed loudly.

### 39.3 Tests

Four, each with its control — a first-run folder **must still be created**, and
a file that is present must not be reported, because otherwise "reports a
missing destination" and "always fires" are the same result. Mutation-checked:
restoring the silent recreate fails the first, dropping the new check from
`_CHECKS` fails the third.

Suites: **IQ 468, JO 449.**

---

## 40. A banner that was never a banner, and a Settings page that never shrank — 2026-08-31

Two bugs, both found the same way: by finally **looking at a running app**
instead of at the HTML it emits.

### 40.1 ⚠ The health banner was a toast, and the worse it was the faster it vanished

`toast.js` (both apps, identical) does this on load:

```js
document.querySelectorAll("main .flash, .auth-flash-wrap .flash").forEach(function (el) {
  const kind = el.classList.contains("error") ? "error" : ...;
  show(el.textContent.trim(), kind);
  el.remove();                       // <- the banner is gone from the DOM
});
```

The self-check banner added in §29 used `class="flash error"`. So it was
never a banner: it became a corner toast and was **removed from the page**.
And because `error` maps to an auto-dismissing toast while anything else maps
to a persistent "status" one, the `fail` banner disappeared on a timer while
the milder `warn` banner stayed — *the more serious the problem, the sooner
it left the screen.*

That defeats the premise of the whole escalation design. The three-day modal
exists because "a banner is what is currently being ignored" (§29); a banner
that deletes itself after four seconds cannot be ignored, it can only be
missed.

**Fix, both apps:** a dedicated `.selfcheck-banner` / `.selfcheck-banner.fail`
class that is deliberately outside the sweep, with a CSS comment saying why it
must never be reintroduced as a `.flash`.

**Why it survived a check.** On 2026-08-26 the banner was verified by
asserting against the **server-rendered HTML**, which the JS then undid. This
is the fourth instance in this work of the same shape — an invariant tested at
one boundary and violated at another (§34 the heartbeat URL, §32 the misfire
assertion the test's own filter excluded, §36 the touch-target test that ran
phone-only). It is worth stating as a rule: **when JS post-processes a thing,
asserting on the markup that produced it is not a test of the thing.**

**And the first replacement guard was itself vacuous.** A browser test
asserting "the banner survives page load" *passed* against a deliberately
reintroduced bug, because the isolated test install is healthy, so no banner
renders at all and there is nothing to survive. It compared post-load HTML
against the post-load DOM: both go false together and the assertion is
trivially true. Replaced with a static guard on `dashboard.html`, plus a
control pinning `toast.js`'s sweep selector so the guard's own premise
cannot rot silently. Four mutations were run; each fails on its own message.

### 40.2 ⚠ The redesigned Settings page scrolled sideways at every phone and tablet width

`/settings` rendered **1118px (IQ) / 1136px (JO) of content in a 390px
window** — and identically in a 768px one, i.e. it never responded at all.

Cause: `.settings-stack` is a grid, and a grid item defaults to
`min-width: auto`, meaning it will not shrink below its own max-content
width. Each `.card` therefore resolved to max-content, which gave the
`repeat(auto-fit, minmax(260px, 1fr))` `.form-grid` inside unlimited room —
so auto-fit laid out **all four columns** (4 x 260 + gaps) rather than
collapsing to one. The auto-fit from §35 was correct; it was being handed a
container that never got narrow.

**Fix, both apps:** `grid-template-columns: minmax(0, 1fr)` on
`.settings-stack`. Verified by mutation in both apps — reverting the line
reproduces the exact overflow.

This is the direct answer to the question asked when the redesign was
commissioned ("check if that affects the use of the web app on smaller
screens like phones"). The answer at the time was drawn from the mockup and
the CSS. It was wrong, and only running the page caught it.

### 40.3 The reason 40.2 went unseen: a whole test tier that reported "1 skipped"

**IQ's browser tier had never once run.** Playwright was not installed in its
venv, and `test_browser.py` gates on `pytest.importorskip(...)` at module
scope — which collects **zero** tests and reports as **`1 skipped`**, not 13.

So the skip count, which is the documented way to notice a dormant tier
(`CLAUDE.md` §7.1: every tier "skips cleanly"), showed a single innocuous
skip while thirteen tests silently did not exist. JO reported 13 skips for
the same condition only because Playwright *was* installed there, so the
tests were collected and then skipped by `pytestmark`. **The two apps
reported the same dormant tier with different numbers, and the smaller
number was the more dangerous one.**

With Playwright installed in both venvs the suites now run **485 (IQ) / 466
(JO), zero skips**.

Practical rule: `-q` totals do not distinguish "skipped" from "never
collected". Confirm a tier is alive by collecting it
(`pytest tests/test_browser.py --collect-only`), not by reading the skip
count.

### 40.4 The same backup failure, told twice, in two shapes — 2026-08-31

Once the banner in §40.1 actually stayed on screen, it exposed a second
problem the toast had been hiding: `logic.backup_alert_message()` predates
Layer 1 and reports the same four situations the `backup_*` findings do
(never run / failed / stranded / stale), in less detail. Both fired at once,
so the admin got the news in the banner *and* as a corner toast, in different
wordings.

Fixed by suppressing the older alert when the banner already carries a
`backup_*` finding. **Deliberately narrow**, with two controls:

- a banner about something else (low disk, rolled-back update) must **not**
  silence it — otherwise the suppression is just deletion with extra steps;
- with the self-check switched off (`selfcheck_enabled=0`) it must still
  appear, because then it is the only backup warning the app has left.

The two also disagree by design: the self-check's staleness threshold is
configurable (`selfcheck_backup_max_age_days`), this one is fixed at 2 days,
so they are not interchangeable in the general case.

Mutation-verified in both apps — reverting the fix, and widening it to an
unconditional suppression, each fail on their own message.

**Still open, not fixed:** within the banner, `backup_failing` quotes the
backup error verbatim, and when the cause is a vanished folder that error
*is* the `backup_dir_missing` message — so bullets 2 and 3 say the same thing
twice. Three checks correctly firing for one root cause reads as repetition.
Left alone deliberately: changing which findings surface is a behaviour
change to the feature under soak.

### 40.5 One fault printed twice inside the banner — 2026-08-31

`_check_backup_failing` quotes the last attempt's error so that, standing
alone, it says *why* backups are failing. When the cause is the backup folder
itself, that quote is `backup.py`'s dir-gone paragraph and
`backup_dir_missing` is the same fact in its own words — so the banner listed
one fault twice, in two wordings, directly above each other.

Fixed with `_drop_duplicated_cause()`, applied after the checks run: when
`backup_failing` appears alongside `backup_dir_missing` or
`backup_dir_unwritable`, its message drops the quote and becomes "The last 3
backup attempts all failed."

**The finding is kept, only the quote goes.** The repeat count is information
the folder check does not carry — it is what says this is ongoing rather than
a one-off, and it is what the 3-day modal escalates on. And when
`backup_failing` stands alone the quote survives untouched, because then it is
the only explanation the admin gets; dropping it would trade a repetition for
a mystery. Same reasoning `_check_backup_dir` already used for reporting
`backup_dir_missing` *or* `backup_dir_unwritable` but never both.

Three mutations verified in both apps: removing the dedupe, making it
unconditional, and dropping the finding rather than its quote each fail on
their own message.

**A note on how this was verified.** The first version of the guard failed for
the wrong reason — it asserted `backup_dir_missing` contained the *quoted*
error string, when that finding states the same fact in its own wording. The
test was wrong, not the fix. Worth recording because it is the friendly case
of §27's lesson: a test that fails for the wrong reason is visible, while one
that *passes* for the wrong reason is not.

### 40.6 selfcheck.py was never actually identical across the apps — 2026-08-31

Found incidentally while diffing the two files after the §40.5 patch. JO's
module docstring claimed "This file is currently identical to IQ's, and that
is a verified result rather than a copy-paste". **It was not true**, and only
two commits have ever touched either file — so the divergence has been there
since the feature landed.

`consecutive_fail_days()` differs: IQ keys each day's verdict by `ran_at`
timestamp and documents why it ends at the most recent *recorded* day rather
than today (a machine switched off for two days has no rows for those days).
JO keys by insert order, relying on `ORDER BY id DESC` agreeing with `ran_at`
order, and its docstring still says "ending today", which its own code does
not do.

The two agree whenever id order and ran_at order agree, which is always in
normal operation — **a robustness gap, not a live bug.** IQ's version is the
better one.

**Not ported, deliberately:** this function decides when the Dashboard modal
escalates, which is exactly what Test C is soaking, and it is day 1. JO's
docstring has been corrected to state the divergence and point here. Port it
once the soak is done.

The wider lesson: a comment asserting parity is not evidence of parity, and
this one went stale without a single commit touching the function it
described. `diff` the files.

**Closed 2026-09-09 — ported, with the test that can tell the two versions
apart. See §43.**

## 41. ⚠ A failing backup erased the evidence that its folder was real — 2026-09-02

The soak's Test C reported a vanished backup destination correctly for about
100 minutes, then **repaired itself**: the app recreated the missing folder,
the next backup "succeeded" into the fabricated local copy, and the Dashboard
went green while the real destination stayed gone. Precisely the failure §39's
guard exists to prevent, reintroduced through a different door.

### Two independent causes

**1. Two implementations of `_backups_written_here`, one of them fragile.**

| | Query | Survives a failure storm? |
|---|---|---|
| `backup.py` | `WHERE status='success' … ORDER BY id DESC LIMIT 50` | **yes** |
| `selfcheck.py` | scanned `recent_backups(db, limit=20)` — last 20 rows of **any** status | **no** |

A broken destination produces failures, which pushed the last success out of
the 20-row window. `selfcheck` then concluded the folder had never been an
established destination and took its `os.makedirs` branch. The staged install
had **70 failure rows behind its last success**; the folder was recreated at
03:07:22, in the same second as that day's self-check.

`selfcheck`'s copy is deleted. Both modules now share `backup.py`'s.

**2. An unbounded retry supplied the failures.** `_backup_catchup_due` asks
whether a backup *succeeded* since the scheduled time, so a permanently broken
destination never satisfied it and the 5-minute tick retried forever — ~288
rows a day, enough to exhaust a 20-row window in about 100 minutes. Bounded to
one attempt per hour, which still recovers a transient fault quickly.

Either fix alone closes the hole. Both are in, because they are separate
defects and the first is not obviously the last of its kind.

### What this cost, and why it is recorded at length

On 2026-09-01 the retry was found and **deferred as cosmetic log noise**, on
the reasoning that it "only bites an install whose backup destination is
already broken and loudly reported." That was wrong in the way that matters:
**it silences the report.** The release decision rested on that sentence.

The lesson is not "retry storms are bad". It is that *"this only affects an
already-degraded install"* is not a severity argument — the monitoring
feature's entire job is to be correct on a degraded install. A defect in the
degraded path is a defect in the product, not in an edge case.

### An existing test was asserting the removed behaviour

`test_a_failed_backup_does_not_count_as_todays_run` failed against fix 2. Its
docstring said "a failed attempt **an hour ago**" while its code used **one
minute** — drifted apart at some point, and the code half was pinning exactly
the retry cadence being removed. Rewritten to test the property it names (a
failure is not mistaken for a success), with the throttle covered separately.
A test whose docstring and arrangement disagree is worth re-reading whenever
it blocks a deliberate change.

### Verified live, not only in tests

Re-staged on the real Test C install with **71 failure rows** behind the last
success — more than the run that broke it — the check now reports
`backup_dir_missing` and leaves the folder absent. `_backup_catchup_due`
returns `False` 17 minutes after a failed attempt where it previously returned
`True` within five.

*(Unrelated but worth knowing: Test C would not restart during this work
because a Homebrew upgrade from Python 3.14.6 to 3.14.7 left every venv's
`bin/python3.14` symlink dangling. Repointing the symlink fixed it — the 3.14
ABI is stable across patch releases, so installed packages survive.)*

## 42. A Python upgrade could stop either app starting, silently — 2026-09-02

Found while cleaning up after the release. `brew upgrade` deletes the
versioned Cellar directory a venv was built against, so
`venv/bin/python3` dangles. The consequence is not a 500 and not a crash
report: **the app never starts at all.**

The supervisor launcher makes it worse. It respawns the app whenever it
exits — right for a crash, wrong for a missing interpreter — so it loops
`exited (code 127) — restarting in 2 seconds` **forever**, with nothing on
screen naming the cause. Nightly backups stop with it. The only thing that
notices is the heartbeat going quiet, which alerts at ~60 hours.

Both of the JO install's releases were already in this state and could not
have restarted.

### `--copies` does not fix it, which is the counterintuitive part

The obvious fix is `python3 -m venv --copies`, so the interpreter is a real
file rather than a symlink. It does not work. `otool -L` on both variants:

```
/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python
```

An absolute, versioned dylib path with no `@rpath` indirection. Copying the
executable does not copy the framework it loads, so a `--copies` venv breaks
too — and looks perfectly intact on disk while doing it.

### What was actually done

1. **The launcher probes its interpreter before starting, and rebuilds the
   venv if it will not run** (both macOS and Windows templates). Rebuilding is
   safe — a venv holds only dependencies — and covers every variant: patch
   upgrade, minor upgrade, uninstall, moved install. A rebuild that fails
   exits with an explanation instead of falling back into the loop.
2. **`setup.py` builds release venvs from `sys._base_executable`, not
   `sys.executable`.** Inside a venv the latter is that venv's own python, so
   each release inherited whatever path its parent resolved to — which is how
   a versioned Cellar path propagated through all nine soak builds. The base
   interpreter resolves through Homebrew's stable `opt` symlink, which `brew`
   repoints on upgrade.

(2) narrows the window; (1) closes it. Only (1) survives an uninstall.

`tests/test_launcher_preflight.py` covers both, including a real rebuild of a
deliberately dangled venv against an empty requirements file so it stays
offline, plus a control asserting a healthy venv is left alone — without that,
a preflight that rebuilt unconditionally would pass while adding a minute to
every startup. Three mutations verified.

**Worth knowing:** `/opt/homebrew/bin/python3` symlinks straight into the
Cellar, not through `opt`, so landing on the fragile path is easy. Check a
venv with `readlink venv/bin/python3.14`: an `/opt/homebrew/opt/...` target
survives a patch upgrade, a `/opt/homebrew/Cellar/...` one does not.

## 43. `consecutive_fail_days()` ported into JO, and the test that can tell the two versions apart — 2026-09-09

Closes the last open item from §40.6 and `TRANSITION_NOTES.md` §4 item 3. JO's
copy of `selfcheck.consecutive_fail_days()` now keys each day's verdict by the
`ran_at` timestamp, as IQ's always did, instead of by insert order. The two
`selfcheck.py` files are now byte-identical apart from JO's module docstring,
verified by `diff` rather than asserted — which is the whole point of §40.6.

### Why insert order was wrong, in terms of what a clinic sees

The function reads `ORDER BY id DESC LIMIT 400` and decides, per calendar day,
whether that day "failed". JO took the first row it saw for each day, which is
the highest id, and called that the day's verdict. That is only the day's
latest result while id order and `ran_at` order agree.

They stop agreeing after any clock movement — NTP correcting a drifted
machine, a DST step, or a front-desk PC whose date was simply wrong until
someone fixed it. Both directions are bad, and both now have a test:

| rows, in insert order | insert-order verdict | timestamp verdict |
|---|---|---|
| today 03:30 `ok`, then today 03:05 `fail` | today failed → a streak that never happened | today passed → 0 |
| 2 days `fail`, then today 03:30 `fail`, then today 03:05 `ok` | today passed → streak 0, **modal never fires** | streak 3 → modal fires |

The second row is the one that matters. `app.py` gates the Dashboard modal on
`consecutive_fail_days(db) >= 3`, so insert order could keep the modal silent
through three genuinely failing days — the exact silence Layer 1 exists to
break (§29).

### The test discipline this needed, which is the reusable part

`TRANSITION_NOTES.md` warned that the obvious test passes against **both**
implementations, and that was exactly right. Before this change neither app's
suite could distinguish them: all 36 existing `test_selfcheck.py` tests write
their rows in ascending time order, where the two agree by construction.

Two tests were added **to both apps** (the function is identical in both and
touches no money, so the §1.1 reason to diverge does not apply):

- `test_a_days_verdict_follows_the_timestamp_not_the_insert_order` — the later
  row written first, asserting `0`.
- `test_an_out_of_order_row_cannot_hide_a_real_failing_streak` — the same
  ordering trick against three failing days, asserting `3`. This is the
  **control** the other one needs: it asserts a NON-zero streak, so the pair
  separates "counted for the right reason" from "returned 0 for any reason"
  (`CLAUDE.md` §7.3).

**Mutation-verified in both apps.** Reverting each `selfcheck.py` to
`by_day.setdefault(...)` — with a `diff` printed to prove the mutation landed
in the code and not in a comment, the failure mode §7.3 records — fails
**exactly these two tests and no others**, in IQ and in JO. That both apps
lost the same two, and only those two, is the evidence that every other test
in the file was blind to this bug.

### A code review looked straight at this and passed it

`CODE_REVIEW_MONITORING_2026-08-27.md`, under "What was checked and found
sound", records `selfcheck.py` as differing "only in `consecutive_fail_days`'
implementation, which is functionally equivalent" — and then justifies that
by comparing the two **loop-termination** styles, `by_day.get(day)` versus
`day in by_day and ...`, which genuinely are equivalent. The `setdefault`
versus timestamp-max line four lines above it, the one that actually
diverges, is not mentioned.

So the review compared the halves of the function that matched and concluded
the function matched. §40.6 then found the real difference four days later by
running `diff`. This is the §21 lesson in a second setting: **a careful read
of the right file can still miss what a mechanical comparison catches
immediately.** `diff` first, then read.

### Verified live

Both apps, full suite, all three tiers, in their own isolated environments
(`scripts/isolated_test_env.sh`): **IQ 504 passed / 0 skipped, JO 485 / 0**.

## 44. ⚠ `isolated_test_env.sh` records the wrong PID, so `down` does not guard anything — 2026-09-09

Found while tearing down after §43, in both apps independently.

`up` prints an "App PID" and writes it to `/tmp/vz_{app}_test.pid`. **It is
not the app's PID.** Measured on two separate runs, minutes apart:

| app | PID file | actual listener (`lsof -ti :PORT`) |
|---|---|---|
| IQ | 41035 | **41037** |
| JO | 40011 | **40013** |

Off by two in both cases: the recorded PID is the short-lived wrapper around
the launch, not the `python3 app.py` that ends up holding the port. The line
is

```sh
( cd "$REPO_DIR" && nohup env ... "$VENV_DIR/bin/python3" app.py > ... 2>&1 &
  echo $! > "$PID_FILE" )
```

and `$!` there names the backgrounded `cd && nohup env …` compound, not the
interpreter that survives it. On the JO run the recorded PID happened to be
the setup script itself, which is why `up jo` appeared to hang for fifty
minutes and then "finished" the moment that PID was killed.

**Why this matters more than a cosmetic wrong number.** `CLAUDE.md` §5 sells
two guarantees that both rest on this PID:

1. *"`up` prints the PID to kill when you're done testing"* — killing it
   leaves the real app running, still serving on 5091/5092 and still writing
   to the throwaway database. Nothing says so; the port keeps answering 200.
2. *"`down` won't proceed while that process is still running"* — the guard
   checks `kill -0` on the **recorded** PID. Once that wrapper is gone the
   guard passes, and `down` removes the container, the venv and the data dir
   **out from under a live app**. The protection reads as present and is not.

This is the §7.3 pattern in tooling rather than in a test: a check that
cannot fail is indistinguishable from a check that passes. Both apps were
torn down correctly here only because the mismatch was noticed first —
`lsof -ti :5091` / `:5092` is the reliable way to find what to kill until
this is fixed.

### Fixed the same day

**The launch.** `$!` now names the interpreter, because the subshell is
backgrounded and `exec`ed into rather than the AND-list being backgrounded
inside it:

```sh
( cd "$REPO_DIR" && exec nohup env ... python3 app.py > log 2>&1 ) &
echo $! > "$PID_FILE"
```

`exec` replaces the subshell with `nohup`, which execs `env`, which execs
`python3` — all in place, one PID throughout. As a side effect `up` now exits
instead of hanging: the JO run that appeared to hang for fifty minutes was the
script itself sitting in the pipeline it had recorded as the app.

**The launch is then checked, not trusted.** `up` cross-checks the recorded
PID against `lsof -ti tcp:$APP_PORT`, and refuses with the port-holder's real
PID if they disagree — "the PID looks plausible" is how this read for weeks.

**`down` grew a second, independent guard.** It now refuses while *either*
the recorded PID is alive *or* anything still holds the app port. The port
guard is the one that survives the PID bookkeeping being wrong again, which
is the whole lesson here. If `lsof` is missing it refuses rather than
assuming the port is free — `CLAUDE.md` §6's rule that a check which cannot
run is a failure, not a pass.

**Verified by a real cycle in both apps**, four cases each:

| case | expected | result |
|---|---|---|
| recorded PID vs actual listener | equal | IQ 42327 = 42327, JO 42499 = 42499 |
| `down` with the app running | refuse (PID guard) | exit 1, both |
| `down` with a **dead PID written into the file**, app still up | refuse (port guard) | exit 1, both |
| `down` after killing the printed PID | succeed, remove everything | exit 0, both |

The third row is the case that used to slip through, and it is the reason for
the fourth: disabling one layer must still refuse, and the control proves
`down` can still succeed rather than having become unconditionally stuck
(`CLAUDE.md` §7.4 on defence in depth — disable one layer, then both).

Killing the printed PID now actually stops the app, which it did not before.

**Follow-up, 2026-09-10.** The new port cross-check sampled once, three seconds
after launch, and JO's app took slightly longer than that to bind — so a
perfectly healthy `up jo` printed "Nothing is listening on 5092 yet". A warning
that fires on a normal startup is worth less than no warning, because it trains
you to read past the one time it is real (the §6.0 cry-wolf rule, applied to
tooling). It now waits up to 20 seconds for the port, gives up early if the
process dies while waiting, and **exits non-zero** if the port never appears
instead of printing a caveat and carrying on.

## 45. Microchip number on patients — the same feature, twice — 2026-09-10

An optional microchip number on `patients`, and — the reason it exists — a way
to find a patient by it: a scanner reads a chip on a stray or a transferred
animal and staff need the record it belongs to.

`patients` was byte-identical in both apps before this and still is. Nothing
about a chip is country-specific and nothing here touches money, so **no new
divergence was introduced**; the only per-app differences are in the templates
that had already diverged (IQ's `_back_link.html`, sticky header and
`data-row-href` versus JO's inline `onclick`), which were edited in place
rather than copied across.

### The decisions, and who made them

| | |
|---|---|
| Optional | Always. Most patients have no chip and nothing may become harder to save. |
| Unique when present | Partial index, `WHERE microchip IS NOT NULL`. The column arrives empty on every install, so no existing row can violate it — the safest possible moment to add a constraint, and the reason no backfill was needed. |
| 9–15 alphanumerics | 15-digit ISO 11784/11785 is what a clinic implants today, but animals carrying an older 9-digit AVID Euro or 10-digit AVID/trovan chip still walk in. A strict 15 would make those unrecordable. |
| Where it shows | Patient record, both patient forms, the search picker, and the patient-file / visit / inpatient / boarding PDFs. **Not** a column in `/patients` — a 15-digit number in an already 6-column table, and the search finds the patient either way. |

### Normalization is the whole feature, and it has one definition

Staff type a chip the way it is grouped on the scanner: `985 141 000 123456`,
`985-141-000123456`. Stored verbatim, those are three different strings — the
search misses two of them and the unique index cannot see them as one chip.

So the number is normalized on the way in. The subtlety is that **the search
term has to be normalized by the same rule**, or a chip typed the way it is
printed finds nothing. Those are two call sites in two modules, which is
exactly how a rule drifts, so there is only one definition of it:
`logic.strip_microchip_separators()`. `app.py`'s `normalize_microchip()` calls
it before storing; `logic.search_patients()` calls it before matching. Every
other field in that search is still matched on the term as typed, which is why
the chip gets its own parameter rather than a change to the shared one.

`search_patients()` is the single search path behind both `/patients` and
`/api/patients/search`, so one clause gave both the list page and the picker.

### The index lives in setup.py, not the schema file

`ALTER TABLE patients ADD COLUMN IF NOT EXISTS microchip TEXT` plus the unique
index both go in `INCREMENTAL_SCHEMA_STATEMENTS`. The index cannot go in
`schema_postgres.sql`: `apply_schema()` runs first, so an index over a
migration-added column works on a fresh install and raises on every upgrade —
the §42-adjacent trap that `test_migrations.py`'s static guard exists to catch,
and the same reason `idx_sales_idempotency_key` lives there.

### Two layers on the duplicate, and the mutation matrix that proves both

A pre-check names the animal already holding the chip ("already on file for
Luna (PT042)"); the unique index is what actually enforces it. In
`visit_new_patient()` the pre-check runs **with the other field validations,
before the owner INSERT** — that route writes an owner, then a patient, then a
visit in one transaction, so a chip rejected at the patient INSERT has to roll
the owner back too or every rejected attempt leaves the ownerless-pet shape
`ORPHANED_RECORDS_AUDIT.md` F-03 describes. The `IntegrityError` fallback does
exactly that, and returns the id counter with it.

Per `CLAUDE.md` §7.4, defence in depth has to be disabled a layer at a time or
the test proves nothing. Identical results in **both** apps:

| mutation | expected | result |
|---|---|---|
| storage normalization removed | the "stored normalized" test fails | ✅ that test alone |
| search-term normalization removed | "found however it is typed" fails | ✅ that test alone |
| `p.microchip ILIKE ?` clause removed | "found however it is typed" fails | ✅ that test alone |
| pre-check disabled, index intact | **still passes** — the index holds | ✅ 24/24 |
| index dropped, pre-check intact | **still passes** — the check holds | ✅ 24/24 |
| **both** disabled | the duplicate test fails | ✅ that test alone |
| field silently made required | the *optional* control fails | ✅ that test alone |
| blank stored as `''` instead of NULL | both NULL-asserting tests fail | ✅ those two alone |

The last two rows are the ones worth keeping. Every other microchip test is a
rejection test, and a field that had quietly become mandatory would pass all
of them.

The `''`-instead-of-NULL row is not hypothetical bookkeeping: the partial
index ignores NULLs but treats two empty strings as the same value, so storing
a blank would mean the **second** patient anyone cleared a chip from could not
be saved — a bug that only appears on the second use, in a clinic, weeks
later. Clearing a chip that was recorded against the wrong animal is a thing
staff will actually do, so it has its own test rather than riding on the
never-had-one case.

### Verified live, not only under the test client

Both apps: the chip renders on the patient page; a chip typed with spaces and
a dash finds the patient through the real picker and shows `· Chip: …` on the
result line; the patient-file and visit PDFs carry it in the identity header;
and clearing the chip removes the whole `· Chip: …` fragment rather than
leaving an empty label or a stray separator.

Full suites, all three tiers, in their own isolated environments: **IQ 511,
JO 492, zero skips** (504 + 7 and 485 + 7).

**SHIPPED 2026-09-10 as IQ v1.12.0 / JO v1.10.0.** MINOR in both, per
`RELEASE_WORKFLOW.md` §3 — a new feature plus an additive column. The full §6
checklist was run per app: suites green first, schema confirmed additive-only
with the unique index in `INCREMENTAL_SCHEMA_STATEMENTS` rather than the
schema file (§6.2), `VERSION` and `CHANGELOG.md` bumped in one commit, tag
equal to `v` + `VERSION`, and `releases/latest` verified non-draft,
non-prerelease with a tarball attached. JO's `1.9.1 → 1.10.0` is a
double-digit minor; that is safe because `updater.py` compares with `!=`
rather than ordering (§ the standing note on `is_update_available()`).

**One thing found on the way, unrelated to this feature but worth knowing.**
The first JO run reported `9 skipped`, which in this project is the shape of a
dormant tier (§40.3). It was not: `test_scheduler_catchup.py` carries two
wall-clock gates, and the run started at 00:32. Nine tests skip before 01:00
because today's 00:30 backup slot has not passed, and a tenth skips until
about 01:05 because it needs `now - (BACKUP_RETRY_MIN_MINUTES + 5)` to still
land on today's date. Both gates are correct — the state under test cannot
exist at that hour — but between midnight and ~01:05 the suite cannot reach
the zero-skip figure `CLAUDE.md` §7 quotes, and someone reading the total
would think a tier had gone dark. Re-running the same file at 01:05: 22
passed, no skips. Recorded in §7 so the next midnight run does not start a
hunt for a bug that is not there.

## 46. ⚠ The Settings page spent the clinic's GitHub quota, then blamed the internet — 2026-09-10

Reported from a real install a few hours after shipping §45: the app said
**"Couldn't check for updates — offline, or GitHub is unreachable."** The
machine was online and GitHub was up.

What GitHub actually returned:

```
HTTP 403
{"message":"API rate limit exceeded for <ip>..."}
```

**Unauthenticated GitHub API calls are capped at 60 per hour PER IP ADDRESS**,
shared by every install behind that address — and both apps run on the same
machine here.

### Two separate bugs, and the second is what spent the quota

**1. One sentence for every cause.** `settings_updates_check()` wrapped the
call in a bare `except Exception` and returned a fixed string. A rate limit, a
404 from a wrong `GITHUB_REPO`, a rejected token, a 500 at GitHub and a real
outage were all reported identically — as being offline. The one failure that
reached a clinic was the one where that sentence was actively wrong: it sent
the admin to check a connection that was fine, and gave them no way to learn
that waiting eleven minutes would fix it.

**2. The page-load call.** `loadUpdatesStatus()` ran on every Settings page
load and called `/settings/updates/check`, which asks GitHub for the latest
release. Look at what it did with the answer: read `configured` and
`current_version` to choose a panel and print "VetClinicSystem IQ v1.12.0".
**Both are local** — `is_configured()` checks two env vars and two
directories, `current_version()` reads a file. It spent a rate-limited network
request to render two facts already on disk, and the cost landed on the
*button*, the one place the call is genuinely wanted.

Sixty Settings visits an hour is not a large number for a clinic.

### The fix

- `/settings/updates/status` — local only, and its docstring says to keep it
  that way. The page load uses it.
- `updater.describe_check_failure(exc)` classifies: rate limit (403/429 with
  `x-ratelimit-remaining: 0`) names the cap **and the time it lifts**, taken
  from `x-ratelimit-reset`; 401 points at the token; 404 at the repository;
  other statuses report the code; connection errors and timeouts still say
  offline, because for a real outage that answer is correct.

### Measured against real GitHub, not a stub

The unit tests build the exception themselves, so they prove classification
but not consumption. So the routes were driven against live GitHub with a
configured install and the quota read either side:

| | quota |
|---|---|
| before | 58 |
| after **5×** `/settings/updates/status` | **58** — unchanged |
| after **1×** `/settings/updates/check` | **57** — dropped by exactly one |

Before this change those five page loads cost five requests.

### Test discipline

Four mutations, identical results in both apps. Pointing the page load back at
`/check` — the original bug, reintroduced — fails only the static template
guard; making `/status` call GitHub fails only the route guard; removing the
rate-limit branch fails the four rate-limit tests; collapsing every message
into one sentence fails eleven, including the control that asserts five
different causes produce five different sentences.

That template guard exists because of a hole worth naming: the route tests
prove `/status` avoids the network, and say nothing about **which route the
page asks for**. On their own they would still pass with the bug fully
reintroduced.

**SHIPPED 2026-09-10 as IQ v1.12.1 / JO v1.10.1**, PATCH in both — a bug fix
with no schema change. Same `RELEASE_WORKFLOW.md` §6 run as §45: suites green
first, tags equal to `v` + `VERSION`, `releases/latest` verified non-draft and
non-prerelease with a tarball.

## 47. Ten saved web pages were committed into `static/` and served publicly — 2026-09-10

Found while cleaning up after §46. `static/` had accumulated **"Save Page As"
copies of rendered pages** — one in IQ (`_v_settings.html`, 2026-08-28), nine
in JO (`_c_*.html`, 2026-08-29), both during the card-spacing and responsive
work of §36/§38. Flask serves everything under `static/`, so each was live at
its own URL for two weeks.

Nothing referenced them. Nothing failed. That is the whole problem: an
unreferenced file in `static/` has no symptom at all, and neither app's tests
looked at `static/` as a directory — only at assets that templates name.

### What was actually in them

Checked before deleting rather than assumed. No patient IDs, owner IDs or
phone numbers — they were captured against an empty database. The two Settings
snapshots did carry the install's **LAN address and port**, the configured
**backup folder path**, and a CSRF token from whoever saved them. Low severity
on a LAN-only clinic app, and worth exactly nothing to keep.

### The guard, and the false positive that nearly shipped with it

A test now fails if a rendered page appears in `static/` again. Its first
version keyed off the `csrf-token` meta tag those pages carry — and flagged
`static/rebuild.js`, a real, referenced script whose job includes **reading**
that tag.

Caught only because the guard was run against the current tree before the
files were deleted, so its output could be read: two offenders in IQ, one of
them legitimate. It now keys off a complete HTML document living in `static/`,
which no asset is.

**This is the §7.3 pattern with the polarity reversed.** Usually you write a
guard, watch it pass, and have to reintroduce the bug to learn whether it
catches anything. Here the bug was still present, so the honest sequence was
free: run the guard first and watch it fail, delete the files, watch it pass.
When a fix is a deletion, that ordering costs nothing and is strictly better
evidence — and it is the only reason the false positive was seen at all.

**SHIPPED 2026-09-10 as IQ v1.12.2 / JO v1.10.2**, PATCH in both.

Released on its own after all, and the reasoning is worth correcting rather
than quietly dropping. The first call was "no clinic-visible behaviour
changes, so let it ride along with the next release." That was wrong, for a
reason specific to how this updater works: **deleting the files from the
repository does not remove them from a clinic's install.** Each install serves
whatever is in its own active release directory, so every clinic went on
serving those pages until an update replaced that directory. Shipping is not
cosmetic here — it is the only thing that makes the deletion take effect
anywhere but this machine.

Verified on the published tags rather than assumed: the released tree for both
`v1.12.2` and `v1.10.2` contains zero `static/*.html`.

## 48. The full-application review, and the 34 findings it shipped — 2026-09-10

A whole-codebase review of both apps against industry practice — security,
coding logic, bugs, user QoL, dead code, dead files — recorded in
`FULL_APP_REVIEW_2026-09-10.md` in this folder. 37 findings, all accepted;
**34 implemented, tested and mutation-proved on branch
`review-fixes-2026-09-10` in both repos** (33 in this pass, plus M3 as §49).
Three remain open and are listed at the end of this section. Two more findings
(R1/R2) were raised by the user during the work and are included.

**Suites after the work: IQ 698 / JO 679, zero skips** (from 528/509).
**Coverage re-measured the same day: 65% of application code in both**, up from
the 61% recorded on 2026-09-01 — `updater.py` moved 19% → 36% on the back of
its first unit tests, `money.py` is at 100%, `auth.py` 89%. Per-module figures
were re-measured again after the blueprint split; see §50 for the current
ones.

### What differed between the apps, and is now recorded

Per §4, the items below change how the two apps compare:

- **`login_lock_status()` was two different algorithms** and had never been
  listed as a deliberate divergence. They disagreed on three of five ordinary
  scenarios: 10 rapid failures locked IQ for 30 minutes and JO for 14; 15
  locked IQ for 60 and JO for 13. JO escalated per *burst*, so an attacker who
  never paused never escalated — pausing was cheaper than not. IQ escalated on
  volume but had no bursts, so stray old failures dragged its anchor back and
  *shortened* real locks. **Both now run one implementation** with both
  properties. See §S4 of the review.
- **JO's `.gitignore` did not exclude `uploads/`**, where `attachments.py`
  anchors patient X-rays and bloodwork in a dev clone. Nothing had leaked —
  only `.gitkeep` was ever tracked — but IQ had the guard and JO did not. Both
  now have it, plus a test.
- **JO's dependencies were unpinned** (`Flask>=3.0`) while IQ pinned exact
  versions. The updater builds a fresh venv per release and installs from that
  file, so a JO clinic could move several major versions unattended. JO's venv
  had already resolved `psycopg 3.3.5` against IQ's pinned 3.3.4 — the drift
  was real, not hypothetical. JO is now pinned to what it actually runs.
- **JO had no `/favicon.ico` route**; IQ has had one since Safari's probe was
  noticed. JO now serves its SVG there with the right mimetype.
- **JO's `auth.py` claimed the consignment and cash-register permission keys
  were placeholders** "for features this app doesn't have yet". Both shipped
  long ago — 14 consignment routes and 3 cash-register routes carry those
  decorators. Corrected.
- **JO duplicated the discount and Clean Up validation** inline in four routes
  where IQ had shared helpers. JO now has helpers too, re-derived against its
  `Decimal` money model rather than copied from IQ's float one.
- **IQ carried `auth.is_system_admin()`**, which JO never had. It existed only
  to drive a Settings gate that turned out not to be enforced (below); removed.

### The two that mattered most

**The Settings page hid controls it did not gate.** IQ's `settings.html` hid
Backups & Restore, Updates and Startup behind `{% if is_system_admin %}` while
every route behind them required only `manage_settings` — so a custom role the
UI presented as not-an-admin could restore the database, apply or roll back an
update, and browse the server's filesystem by request. JO had no gate at all.
Both now have a `manage_maintenance` permission and the UI condition and the
server condition are the same one.

The migration for that nearly shipped as an outage, and the shape is worth
carrying: `seed_default_roles_and_permissions()` only *creates* roles that are
missing, and `admin_role_edit()` refuses to edit a system role — so adding a
permission key to `auth.PERMISSIONS` on an existing install grants it to
**nobody**, with no way to fix it from the UI. Seeding now re-asserts the system
role's full grant on every run, which closes it for this key and every future
one. `auth.py`'s comment claiming the vocabulary re-syncs "on every launch" was
wrong and is corrected: it syncs from `setup.apply_schema()`, i.e. on a
`setup.py` run and on every in-app update.

**`/api/browse-folder` had no root at all.** It resolved any absolute path with
`os.path.abspath()` and listed it — `/`, `/etc`, `/Users`, `/var/log`,
`/Applications`, confirmed live. Now confined to the home directory, the
configured backup folder and the data dir, compared with `commonpath()` after
`realpath()` so a prefix-sharing sibling and a `..` escape are both refused.

### Boarding was never refundable (R1)

`payments` has anchored on exactly one of `visit_id` / `inpatient_case_id` /
`boarding_id` since it existed. `refunds` had only the first two, and its CHECK
constraint *required* one of them — so a clinic could take money for a boarding
stay and the database would have refused the row that gave it back. Boarding
was the only such gap: of the four billable client surfaces (visits, inpatient
cases, boarding stays, POS sales) the other three were covered, and grooming
and wellness bill through a visit.

Fixing it surfaced a second defect: `revenue_by_category()` mapped every
non-retail refund to the `Service` column, but Boarding has its own — so a
boarding refund would have pulled Service down while Boarding stayed untouched,
leaving both wrong.

### Two lessons about guards, both learned the hard way here

**A mutation that does not apply looks exactly like a test that cannot catch
the bug.** It happened twice: once from shell escaping of `\n` inside a
`python -c`, once from an anchor that did not exist in the file. Both times the
suite passed and the only reason it was noticed is that the harness printed
"DID NOT APPLY". Diff against a pre-mutation copy, not against `git HEAD` —
HEAD shows every uncommitted change and drowns the one you care about.

**A guard can pass for the wrong reason in the arrangement, not the
assertion.** Four instances: a percent-escaping test whose search term pinned
the row either way; two lockout tests whose scenarios put the two candidate
anchors seconds apart; a Clean Up route test that used the seeded admin and, on
failure, rewrote the password every later test logs in with. Each was rewritten
until reverting the fix actually failed it.

### Still open — three

M3 was the fourth and is done; see §49.

- **S6** — the CSP still carries `'unsafe-inline'`, because 88 (IQ) / 96 (JO)
  inline `onclick=` handlers require it.
- **M4** — `pos_checkout` is ~200 lines. Money code in two type systems; a
  pure refactor, but not one to do casually.
- **M8** — ~490 inline `style=` attributes per app. The review's own advice is
  to fix these opportunistically when a template is edited for another reason,
  not to sweep them.

## 49. `app.py` split into blueprints — 2026-09-10

The last structural item from the full review (§48's M3). `app.py` was ~7,200
lines in both apps, two thirds of it route handlers, and had been on the
"worth doing once tests exist to catch what a split breaks" list since
2026-08-26. There are now ~700 tests per app, so it was done.

| | IQ | JO |
|---|---|---|
| `app.py` | 7,211 → **1,333** | 7,109 → **1,277** |
| `core.py` (new) | 394 | 456 |
| `routes/` (new) | 5,764 in 6 blueprints | 5,658 in 6 blueprints |

`routes/` holds `settings`, `admin`, `consignment`, `inventory`, `sales` and
`clinical`. What stays in `app.py` is genuinely cross-cutting: the Flask app
and its configuration, the security headers and network allowlist, the auth
gate, the error handlers, the context processor, the dashboard, the reports
and insights pages, `/health` and the launcher — thirteen routes.

### Why blueprints, and what they cost

Blueprints are the documented Flask mechanism and what any Flask developer
opening these repos expects. The alternative considered — modules registering
routes onto a shared `app` object — needs circular imports, cannot be imported
or tested independently, and gives up per-area `url_prefix`, `before_request`
and error handlers. It was rejected as an anti-pattern, not preferred for being
lower-risk.

The cost is that Flask prefixes every blueprint endpoint:
`url_for("settings_page")` became `url_for("settings.settings_page")`, across
~480 call sites per app. Two things made that tractable rather than dangerous:

- **M2 landed first.** Before it, 43 URLs per app were built by string
  concatenation — invisible to a rename and silent when broken. Doing M3 before
  M2 would have broken the UI in exactly the way §27 describes.
- **`url_for()` raises `BuildError` while the page renders.** A missed rename
  fails at the first page load, not the first click.

### `core.py` — the seam

A blueprint cannot import from `app.py`, because `app.py` registers it. The
pieces both sides need moved to `core.py`: `get_db`, `VERSION`, `BASE_DIR`,
`DB_REQUEST_TIMEOUT_SECONDS`, `lan_address`, the form parsing and validation
helpers (`parse_money`, `parse_int`, `clean_date`, `normalize_phone`,
`required_field`, `has_negative`, the `Bad*` exceptions and the `MAX_*`
bounds), pagination, `_render_with_progress`, and the money-validation helpers
`cleanup_amount_error` / `discount_percent_error`.

**Ordering is load-bearing there.** `core.py` reads
`DB_REQUEST_TIMEOUT_SECONDS` from the environment at import time, so it must be
imported *after* `app.py`'s `load_dotenv()`. `app.py` keeps its own early
`_data_dir` read because that one has to happen before `.env` is loaded at all.

`parse_money`, `MAX_MONEY`, `CLEANUP_CAP` and the `PHONE_*` constants differ
between the apps on purpose (§1.1). Each app's own version moved; they must not
be merged. IQ additionally has `flash_cash_denomination_warning`, which belongs
to the 250-note model JO has no equivalent of.

### ⚠ What broke, and what did NOT catch it

Four things broke during the move. Every one was caught, but by which check
matters:

- **JO would not import at all** — its `MAX_MONEY` is a `Decimal` where IQ's is
  an `int`, and `core.py` had not imported `Decimal`.
- **JO's `parse_money` catches `InvalidOperation`**, not imported either. Every
  non-numeric money input 500'd; twelve tests across five files named it.
- **`CLEANUP_CAP` and `MAX_QUANTITY` stayed a step behind the functions that
  read them.** Neither is referenced at import time, so **both apps started
  cleanly and all 22 sampled pages rendered without error.** What was actually
  broken was every Clean Up on every payment surface, and every POS checkout in
  JO. The `/health` check and the page-render sweep both reported healthy. Only
  the test suite found it — worth remembering the next time a green `/health`
  and a clean render pass feel like enough.

### ⚠ Static guards that read `app.py` alone

Six tests per app parse source text. After the split, `app.py` holds a
fraction of the routes, so any of them still reading only `app.py` would pass
while checking almost nothing — the §7.3 failure mode at its purest.

Two were widened *before* the first route moved (`test_permissions.py`,
`test_maintenance_permission.py`), and a new test pins discovery against
Flask's live `url_map`, so it needs no magic number and cannot drift. That
guard was then proved against the real condition rather than a simulation:
with routes actually moved, reverting discovery to `app.py` alone fails it with
all eleven route names printed.

**`test_no_raw_form_dates.py` caught itself.** It carries a floor — *"the
scanner found only 0 date form reads across 21 modules. Either the app changed
how it reads form data, or this detector stopped matching — fix the detector
rather than lowering this floor."* That floor is what reported the omission
after `clinical` moved. Without it the guard would have passed silently. All
six source-scanning tests were audited afterwards and are package-aware.

### The hardcoded-URL guard had the bug it was written to catch

M2's guard looked for `fetch(`, `.action =` and `window.location =`. It missed
four more per app — `const url = '/api/browse-folder'` and two
`runUpdateJob('/settings/updates/...')` calls — **two of which were routes the
settings blueprint was about to move**, so they would have broken silently. It
now matches any path literal in an assignment or call argument.

### Suites

IQ 698, JO 679, zero skips, 37 `test_*.py` files each. `url_map` still holds
148 rules in both, unchanged through all six moves.

---

---

## 50. Coverage re-measured after the split, and the doc sweep — 2026-09-10

The blueprint split (§49) invalidated every per-module coverage figure in
`CLAUDE.md`, because the module the figures described no longer existed. Both
suites were re-run with coverage against the throwaway environments rather
than adjusting the old numbers.

| | IQ | JO |
|---|---|---|
| Tests passed | **698** | **679** |
| Skipped | 0 | 0 |
| Application-code coverage | **65%** | **65%** |
| `app.py` | 72% (573 stmts) | 74% (556) |
| `core.py` | 88% (144) | 85% (172) |
| `routes/sales.py` | 86% | 87% |
| `routes/clinical.py` | 70% | 70% |
| `routes/consignment.py` | 70% | 70% |
| `routes/settings.py` | 64% | 64% |
| `routes/inventory.py` | 55% | 56% |
| `routes/admin.py` | 54% | 55% |

The headline did not move — 65% before and after — which is the expected
result when code is relocated rather than changed, and is worth stating
because it is also what a broken measurement would look like. The evidence
that it is real is the per-module spread: `routes/sales.py` at 86-87% and
`routes/admin.py` at 54-55% were both inside the old 66% `app.py` average, and
that average was hiding both of them.

**A divergence surfaced by the measurement rather than by reading:** IQ has a
`money.py` (100% covered); **JO has no `money.py` at all**. That is correct and
deliberate — exact 3-decimal `Decimal` JOD has nothing to round to a
denomination, so the module IQ needs for its 250-note floor has no JO
counterpart. It is now stated in `CLAUDE.md` §1's divergence table, where
previously the row said only "`Decimal`, 3-decimal JOD" and left a reader to
assume a parallel module existed. This is the third time a "missing" file in
one app has turned out to be a deliberate divergence rather than a gap
(`COMPARISON.md` §3, §18), and the second time the fix was to say so in the
table rather than in prose someone has to find.

### The documentation sweep

Everything below was stale in a way that would have misled the next session,
and was corrected the same day:

- **`TRANSITION_NOTES.md` §1, §2 and §4 rewritten.** §1's state table claimed
  IQ 1.10.9 / JO 1.8.10 and 379/361 tests — three weeks and ~300 tests out of
  date. §2 was framed as "what changed recently" for sessions that are now
  history, and is now a one-table map into this file. §4's open-work list had
  an item reading "`app.py` is ~4,000 statements in one file". The file's own
  §7 says to rewrite a misleading section rather than patch it, on the grounds
  that a half-true handoff doc is worse than an obviously old one — that
  advice was followed rather than quoted.
- **§3's trap list gained six entries** (12-16 plus a renumbering; two items
  had both been numbered 4 since 2026-08-28). The new ones are the moved
  module-level constants that a green `/health` could not see, the static
  guard that goes vacuous rather than red when code moves, `\b` matching
  inside `data-role-id="`, a new `auth.PERMISSIONS` key being granted to
  nobody on an existing install, and tests that rewrite shared state.
- **Both apps' `README.md`.** The "Running the tests" section still said the
  tests "need no database, no Docker and no running app" and "should pass in
  well under a second" — true when there were five of them, and now describing
  only the pure tier. Replaced with the three tiers, the `TEST_DATABASE_URL`
  rule, the `--collect-only` warning about dormant tiers, and the midnight
  clock gates. Both READMEs also gained a **"How the code is organised"**
  section, because a reader following the old one would look for a route in
  `app.py` and not find it.
- **`HOSTING_MIGRATION_PLAN.md`** cited nine `app.py:NNNN` line numbers into a
  file that is now 1,333 lines; every one pointed at unrelated code or past the
  end of the file. Replaced with symbol names and the file that now owns them,
  which is the citation style that survives a refactor. Its "one real gap",
  `api_browse_folder`, is also **fixed** now (finding S2) and says so.
- **`CLINIC_PC_TUNNEL_PLAN.md`** needed no correction — it cites no line
  numbers — and now carries a dated line saying it was checked and is still
  unexecuted, so the next reader does not have to re-derive that.
- **`FULL_APP_REVIEW_2026-09-10.md`** still said "IN PROGRESS — 33 of 37" and
  "No change has been made to either app". It now states 34 of 37, names the
  three that remain (S6, M4, M8), marks M3 DONE with the reasoning for
  blueprints, and — the part that matters for anyone reading a finding cold —
  says explicitly that the findings are written in the present tense of the
  review, so "this is broken" means *before* the fix unless it is one of the
  three still open. Its baseline table is labelled as the BEFORE state and
  deliberately left as measured.

**The pattern across all six:** none of these documents was wrong when
written. Each became wrong because something shipped, and nothing re-checks a
document on its own. `CLAUDE.md`'s header has now gone stale by omission
three times (2026-09-01, 2026-09-09, and again here), always in the same
way — a file added or a number moved, and the doc not touched in the same
commit. The countermeasure that has actually worked is not discipline but
shape: figures that carry the date they were measured, and citations by symbol
rather than by line.

---

---

---

## 51. The last three review findings — S6, M4, M8 — 2026-09-10

`FULL_APP_REVIEW_2026-09-10.md` is now closed: **37 of 37 shipped**, plus R1
and R2. Suites **IQ 728 / JO 709**, zero skips, all three tiers, 39 test files
each, coverage unchanged at 65%.

### S6 — script-src no longer carries `'unsafe-inline'`

Replaced with a per-request nonce (`core.csp_nonce()`, cached on `g` so the
value in the header and the value in the markup are necessarily the same one —
deriving them separately is the classic way to ship a policy that blocks every
script on the page). Every `on*=` attribute became a listener in a new
`static/behaviors.js`.

Two mechanisms, because one does not fit both cases. `VZ.bind(key, type, fn)`
for markup Jinja renders, keyed by `data-vzh`; `VZ.action(name, fn)` for markup
a page script **builds at runtime**, dispatched by one delegated listener on
`document`. The second is not a stylistic preference: the POS cart, the two
bill carts and the search dropdowns are replaced wholesale on every re-render,
so nothing bound at load time would survive. Delegation means re-rendering the
cart now needs no rebinding at all, which it did not have before either.

**The review's own count was low, and the missing half was the dangerous half.**
It reported 88 (IQ) / 96 (JO) `onclick=`. The real figures were 125 and 142
once `onchange`/`oninput`/`onkeydown`/`onblur` were counted — and a further
**22 and 16 generated by JS at runtime**, invisible to a template grep because
they live inside template literals in `<script>` bodies. Every POS quantity
and remove button is in that set.

Four things this nearly shipped broken, each caught by a different check and
none by "the page still renders":

1. **Handlers hoisted out of a `{% for %}` loop took `{{ s.id }}` with them**
   and raised `UndefinedError`. The suite caught it on the first file.
2. **Handlers hoisted out of a template literal took `${c.id}` with them**,
   where it is no longer interpolation but four literal characters. Every cart
   quantity button would have targeted a line id that does not exist. Caught by
   reading the diff, not by any test.
3. **`test_browser.py` located the POS search result with
   `div[onclick*=addToCart]`.** That stopped matching, and because a missing
   result was a `skip`, the two tests written after the 25-release Complete
   Sale bug (§27) went dormant and reported green. This is §40.3's shape a
   third time: *a guard that goes vacuous rather than red.* The helper now
   asserts when the search returns rows but none is clickable.
4. **`pageerror` does not fire for a CSP violation.** The browser refuses the
   script and writes a console error; the page looks completely normal. The
   existing browser tier could not have seen a policy that blocked every
   script on every page.

Verified live as well as by test: added to the cart, changed quantity through
two re-renders, removed the line, confirmed an empty cart refuses to submit and
a full one POSTs with its items — the server rejected that one *by name* for an
unaudited item, which is what proves the hidden fields built by the converted
handler actually arrived.

**JO's CSP gains explicit `connect-src` and `frame-ancestors`.** The effective
policy did not change — `connect-src` falls back to `default-src 'self'`, and
`X-Frame-Options: DENY` already blocked framing — so this closes a textual
divergence from IQ, not a security gap. Worth stating plainly because the first
reading of it here was "JO is missing two directives", which was wrong.

`style-src` still allows `'unsafe-inline'` and cannot stop doing so: a nonce
does not authorise `style=` attributes either, and the ones that remain are
server-computed. That is M8's territory, and M8 deliberately does not go there.

### M4 — `pos_checkout` extracted

199/202 lines to ~110, with five helpers on the seams the review named. Each
returns `(value…, error)` with `error` a string or None, matching
`discount_percent_error()`. None of them flashes or renders — the route owns
the response, so a helper cannot return a page from three frames down. A local
`refuse()` collapses fourteen flash-then-redisplay pairs to one line each.

Derived separately per app, same shape and deliberately different bodies: IQ
parses quantities with `parse_money` and floors change to a 250-IQD note; JO
uses `parse_quantity`, `Decimal(100)` in the discount, and gives change exact
to the fils. Two behaviours that were easy to lose in the move and were not:
the "no sale price — skipped" notices still flash *before* any later error, in
submitted order, because the helper returns them rather than flashing them; and
`_record_sale` deliberately does not commit, so the checkout stays one
transaction with its row locks still held.

Mutation-proved on eight seams. The one worth recording: mutating JO's change
calculation to IQ's 250-rounding is caught by JO's
`test_checkout_change_is_floored_so_the_clinic_never_overpays` — the **same
test name as IQ's, asserting the opposite thing** (§7.2 working exactly as
intended).

One mutation initially read as a blind test and was not: removing `round(x, 3)`
from JO's change is a **no-op**, because subtracting two exact 3-decimal
`Decimal`s is already exact. "The test did not fail" and "the test cannot fail"
are different claims, and the difference is whether the mutation changed
behaviour at all.

### M8 — the two worst files, and why it is not a sweep

M8 says this is not worth a big-bang sweep. The first attempt here proved why:
a mechanical `style=` → class conversion of the two named files changed **69
computed properties** across the four pages. Reverted and redone.

What broke, none of it visible to any existing test:

- **`el.style.display = ''` clears the inline style and nothing else.** It
  unhides an element only while the inline style is the only thing hiding it.
  Moved to a class, the Settings **Updates panel would never have appeared
  again** — no error, no failed request, nothing to see.
- **`.field label` is 0,0,1,1 and outranks a single utility class.** The inline
  style was the only thing winning, so labels went from font-weight 500 to 620.
- **`margin:0 0 8px` is not `margin-bottom:8px`** — it also zeroes the top
  margin, and a `<p>`'s default came back at 12.5px.
- A class carrying only `border:none; background:transparent` **must not also
  set padding or width**, or the `<select>` it lands on collapses 95×37 → 71×19.

So `display:` toggles stay inline on purpose and are the entire residue in both
files (8/8 in IQ, 8/6 in JO). Everything else moved into a documented utility
and component layer at the foot of `style.css`.

**The method matters more than the result here.** Every element under `<main>`
on both pages in both apps was captured in a real browser before and after —
position, size and eleven computed properties each — and the runs are identical
across all **643 elements**. That harness found all four regressions above;
three of them look like nothing in a screenshot, and the fourth (a panel that
never opens) needs a specific click to notice.

A divergence it also caught: **JO's catalog column widths are 5%/24% where IQ's
are 7%/22%.** The first version of this change put IQ's numbers in both
stylesheets — CLAUDE.md §2, in the smallest possible form.

### What the guards cost, and the two that were born blind

Three new test files, all mutation-proved: `test_no_inline_handlers.py` (17
static checks), `test_inline_styles.py` (10, a ratchet rather than a demand),
plus CSP checks in `test_browser.py`.

Two of them passed against the mutation they existed to catch, and both are
worth remembering:

- **The CSP violation guard needed a control.** With `'unsafe-inline'` put
  back, it passes perfectly — *no violations is exactly what a permissive
  policy produces*. The control injects a script the policy must refuse and
  fails if it runs.
- **The reveal guard's own CSS parser swallowed comments.** The doc comment
  above each rule was captured as part of the selector, so it found
  `.u-hidden` (no comment above it) and not `.reveal-panel` (comment above it)
  — and therefore passed against the exact mutation it was written for. Found
  only because the mutation was run.

That is the third and fourth instance this cycle of *a check that reports green
because it is looking at nothing* (§40.3, §49, and both of these). The pattern
is now specific enough to name: **whenever a guard's subject is discovered
rather than fixed — by scanning a file, parsing a stylesheet, or matching a
selector — write a floor that asserts how much it found.** Every guard added
today has one.

---

---

## 52. Restore drill, 2026-09-11 — IQ passes, JO has nothing to restore

Monthly drill, run because the review branch touches backup-adjacent code and
should not be released without one. `scripts/restore_drill.sh`.

### IQ — PASSED, all eight checks

Against `vetclinicsystemiq_backup_20260910_022801.dump` (132K), the backup the
updater took automatically before the 2026-09-10 in-app update:

| Check | Result |
|---|---|
| Valid `pg_dump` archive | 45 table-data entries |
| `pg_restore` | completed cleanly |
| Schema | 45 tables (current schema defines 45) |
| Referential integrity | 78 foreign keys restored |
| Core data | 135 rows across 8 core tables |
| Login possible after restore | 15 user accounts |
| Orphans | none |
| Money model | `double precision`; 15 bills, 420,000 IQD total, every non-zero bill a whole multiple of 250 |
| App boots against it | connects and queries |

**The backup that passed is a pre-update one, and that is the good news rather
than a caveat.** It is the safety net that matters most — taken automatically
at the moment immediately before an update, which is exactly when a rollback
gets needed. `logs/updates.log` records it: `backup ok`.

**There are no nightly backups on this install**, and that is explained rather
than alarming: nightly runs at 00:30 and only while the app is running. This
install was last started 2026-09-10 02:28 and has not been up across a 00:30
boundary since. `errors.log` is 0 bytes, dated 2026-09-02. Nothing failed; the
scheduler simply never had an opportunity. Worth re-checking after the app has
been left running overnight, because "the nightly has never produced a file"
and "the nightly is broken" look identical from here.

### JO — the drill cannot run, and the reason is not about backups

`No backup found for jo` — because **there is no JO install on this machine
any more.** Checked 2026-09-11: no `~/Downloads/vetclinicsystemjo-data`, no
releases directory, no `.app`, and no `vetclinicsystemjo_postgres` container
(running or stopped). Only the dev clone under `webapps/vetclinicsystem_jo-main`
remains, which is source, not an install.

So the drill's exit 1 is a true statement — JO has no reachable backup here —
but it says nothing about whether JO's backup *code* works. Two different
findings that the same red line would report identically, which is worth
naming: **"the check failed" and "there was nothing to check" are not the same
result**, and this drill deliberately prints the second in its own words
("That is itself the finding: this app has no reachable backup") rather than
letting it read as the first.

Whether JO's removal was deliberate is not recorded anywhere in this workspace.
If it was not, the data is unrecoverable — JO has no backup on this machine
either. Raised with the user rather than assumed either way.

### Two environment facts corrected the same day

- **Port 5432 is now IQ's container**, not JO's. `TRANSITION_NOTES.md` §6 had
  said JO's since 2026-08-26; that container no longer exists.
- **The standing "do not touch `~/Downloads/vetclinicsystemjo-data`" rule has
  no subject.** Replaced with what is actually there now, plus the same rule
  for IQ's install, which very much does exist and holds the only backup.

Both were stale in the direction that matters: a session reading them would
have gone looking for a JO install, found nothing, and had no way to tell
whether that was the note being old or the install being missing.

---

---

## 53. Released — IQ v1.13.0 / JO v1.11.0 — 2026-09-11

The review branch is merged, released and gone. `main` is level with
`origin/main` in both repos, `review-fixes-2026-09-10` is deleted, and the two
GitHub releases are live and verified.

**MINOR, not PATCH**, per `RELEASE_WORKFLOW.md` §3: the release carries an
additive schema change (`refunds.boarding_id`) and a new user-facing capability
(boarding stays can be refunded). Nothing destructive, no manual admin step, so
not MAJOR.

| | IQ | JO |
|---|---|---|
| Version | 1.12.2 → **1.13.0** | 1.10.2 → **1.11.0** |
| Commits released | 33 | 34 |
| Tests at release | 728 | 709 |
| Tag | `v1.13.0` | `v1.11.0` |

### What the checklist caught that a straight merge would not have

**The CHECK constraint was the risk, not the column.** `refunds_anchor_ck` now
names `boarding_id`. Inside `CREATE TABLE` that is fine on a fresh install and
says nothing at all about an upgrade — this is the §6.2 trap that once made 16
of 38 tagged releases unable to update. It is handled: `setup.py` drops and
recreates the constraint in `INCREMENTAL_SCHEMA_STATEMENTS`, beside the
`ALTER TABLE` that adds the column.

Verified empirically rather than by reading, on a database built from
`v1.12.2`'s own schema and then upgraded through the real path: `boarding_id`
absent before, present after, and the constraint afterwards reads
`(visit_id IS NOT NULL)::int + (inpatient_case_id IS NOT NULL)::int +
(boarding_id IS NOT NULL)::int = 1`. Without that, boarding refunds would have
worked on every fresh install and failed on every upgraded one — the exact
split that is hardest to notice, because the developer's own machine is
usually the fresh install.

**And the verification itself had a side effect worth recording.** The command
used was `setup.py --sync-schema`, a flag that does not exist. `setup.py` does
not reject unknown arguments; it fell through to its default full-install path
and created `webapps/vetclinicsystemiq-data/` and
`webapps/vetclinicsystemiq-releases/app_v1.12.2/` in the workspace. Harmless
here — both were removed, both git trees stayed clean, and the real install at
`~/Downloads/vetclinicsystemiq-data` was untouched (its single backup still
present) — but **`setup.py` treats an unrecognised flag as "do the default
thing", and the default thing is to install an app.** Anyone reaching for a
one-off setup.py invocation should pass a flag it actually parses
(`--desktop-shortcut`, `--enable-updates`, `--no-enable-updates`) or expect an
install.

### End-to-end, not just the API

Both releases were checked twice: `GET /releases/latest` returns exactly
`v1.13.0` / `v1.11.0`, non-draft, non-prerelease, with a tarball; and each
app's **own `updater.check_latest_release()`** was run against the live repo
and returned the same. That second check is the one that matters, since it is
the code path a clinic actually uses, and it is where B1 lived.

`GITHUB_REPO` comes from the install's `.env`, not from the repo — running the
updater from a bare shell gets `repos/None/releases/latest` and a 404. Not a
bug; worth knowing before diagnosing one.

---

---

## 54. JO reinstalled on this machine — 2026-09-11

`COMPARISON.md` §52 recorded that JO's install had disappeared. It is back:
**v1.11.0, on the versioned-release layout, serving on 5051 with its own
Postgres on 5433.** IQ is untouched and still on 5050/5432. Both run at once,
which they could not do before today.

**The old data is gone and this is a fresh clinic, not a restoration.** A
full-disk search (Spotlight, including the Trash) found no JO dump anywhere —
the only surviving artefact was an orphaned LaunchAgent. `seed_data.json`
ships empty by design, so the new database has one admin account, 3 roles and
29 permissions, and no owners, patients or price list.

### Two collisions, not one

Both apps default to the same two ports, and nothing in either repo said so:

| | IQ | JO (before) | JO (now) |
|---|---|---|---|
| App | 5050 | 5050 | **5051** |
| Postgres, host | 5432 | 5432 | **5433** |

The app port was already overridable (`VETCLINICSYSTEMJO_PORT`), so that one
is a default changed in the launcher, which lives in the data directory and
survives updates. The database port was not overridable at all, and that is
what made "reinstall JO" a code change rather than a copy: `docker compose up
-d` fails with *port is already allocated*, `setup.py` aborts on `check=True`,
and the install never completes. Whichever app was installed second simply
could not be installed while the first one's container was up.

### Three install-layer bugs, all found by doing it rather than reading it

`setup.py` sits at 14% coverage and `updater.py` at 36%; this is what lives
down there.

1. **The Postgres host port was hardcoded** in `docker-compose.yml` in both
   apps. Now `${POSTGRES_HOST_PORT:-5432}` — the default is exactly today's
   behaviour, so no existing install changes — and `setup.py` derives it from
   `DATABASE_URL` so the two cannot drift. They disagreeing presents as
   "PostgreSQL didn't become ready in time" while `docker compose logs` shows
   a perfectly healthy database.

2. **`--enable-updates` excluded `.env.example` from the release it built.**
   The ignore predicate was `n.startswith(".env")`, meant to keep a real `.env`
   out of a versioned release; `.env.example` is part of the app and
   `ensure_env_file()` reads it. Running `setup.py` inside a release built this
   way dies with `FileNotFoundError`. Releases unpacked by `updater.py` were
   fine, because that path copies the tarball wholesale — **which is why this
   survived: the only way to reach it is a fresh `--enable-updates` install,
   the one path no test covers and nobody repeats.**

3. **`setup.py` looked for `.env` in the release folder, not the data
   directory.** On a managed install `load_dotenv_now()` therefore loaded
   nothing, and `ensure_env_file()` — finding no `.env` — helpfully *created*
   one, inventing a fresh `SECRET_KEY` and a `DATABASE_URL` on port 5432. On
   this machine that port is IQ's. The file sat in the release folder
   shadowing nothing during normal operation, because the launcher exports the
   data directory, but it was one `python3 app.py` in the wrong directory away
   from connecting to the wrong database with a secret key that signs everyone
   out. Both now resolve through `_env_dir()`.

All three are fixed on JO's branch `install-port-override`, **not released**.
**IQ has all three, identically.** Not changed there today: IQ's install is
already on the managed layout and working, so nothing re-runs those paths —
but a fresh IQ install hits all three, and the compose fix is what lets a
future third app coexist at all.

### Autostart is off, and was already broken

JO's LaunchAgent survived the install's removal, pointing at
`app_v1.4.4`, and `launchctl list` showed it exiting **126** at every login.
Repointing it at the new install produced the same 126: `Operation not
permitted`. The launcher runs fine from a shell, so this is macOS TCC —
launchd cannot read `~/Downloads` without a Full Disk Access grant.

**The agent has been removed** rather than left logging a failure every login
(kept at `/tmp/com.vetclinicsystemjo.autostart.plist.disabled`). **IQ has never
had one**, so both apps now start the same way: the Desktop shortcut, or
`Start VetClinicSystem JO.command` in the data directory. Enabling autostart
needs either a Full Disk Access grant for launchd in System Settings — a
manual step — or moving the install out of `~/Downloads`, which would diverge
from IQ's layout.

That 126 is worth keeping in mind: **it is what an autostart failure looks
like, and it looks identical whether the target is missing or merely
unreadable.** The first reading here was "the agent points at a deleted
install", which was true and was not the whole story.

### Verified, and what was deliberately not verified

Auth gate (`/`, `/pos`, `/settings` all 302 to `/login?next=…`), login page
200 and rendering correctly branded and styled with no console errors, schema
applied, `billing.total` restored as `numeric` (JO's money model, not IQ's),
Admin holding all 29 permissions, `/health` green on both apps at once.

**Not verified: a logged-in session.** That needs a password typed into a
form, which is not something to do on the user's behalf. The documented first
login is `admin` / `admin123`, and the account is flagged
`must_change_password`.

One thing the fresh install proves incidentally: **JO v1.11.0 serves
`script-src 'self' 'nonce-…'` while IQ's running v1.12.2 still serves
`'unsafe-inline'`.** IQ is one release behind — S6 shipped in v1.13.0 — so
IQ's in-app updater has something to do.

---

## 55. The live-use simulation audit — six findings, all shipped — 2026-09-11

Released as **IQ v1.14.0 / JO v1.12.0**, with **v1.14.1 / v1.12.1** immediately
after for the upgrade-path half of one fix (below). The audit itself is
`SIMULATION_AUDIT_2026-09-11.md`; the harness that found the findings is
checked in at `scripts/simulation/`, one `repro_*.py` per finding.

**What this pass did differently.** Both apps were driven as real users — a
full clinic day end to end, then rare and hostile cases — rather than read.
That matters, because five of the six findings were invisible to a suite of
728/709 tests, and §21's lesson repeated itself: reading code is not running
it.

### The shape of every finding

**Five of six live at a seam between two code paths that should share a rule
and did not.** Not carelessness — each surface was written correctly in
isolation, and the rule simply did not propagate:

| | the rule | where it was | where it was missing |
|---|---|---|---|
| F1 | the anti-"looks free" floor | `compute_bill_totals` | `pos_checkout` |
| F2/F5 | `parse_money`'s non-finite rejection | every other numeric entry point | `_save_audit_lines` |
| F3 | refunds round down | retail *and* service | neither handled reaching **zero** |
| F6 | a stay cannot end before it begins | `boarding_edit` | `inpatient_edit` |

This predicts the next bug better than a count does: every new surface is a
chance to miss a rule the others have, and **two apps doubles it**. F1's fix
is therefore `money.payable_total()` — one function both paths call — not a
patched line 299.

### F1 and F3 were IQ-only, and that is §1.1 doing its job

Both are consequences of 250-IQD note rounding. JO, with exact `Decimal` and
no rounding, was correct at every boundary tested — a 0.100 sale stays 0.100,
a 0.240 refund pays 0.240. The two apps' new `test_simulation_findings.py`
files assert **opposite** things for these paths, and JO's carries an import
guard that fails if a `money.py` ever appears there.

**F1 was the expensive one.** A cart whose discounted total fell under half a
note recorded `total = 0`: the goods left the shop, and because change is
`cash_received - total`, the till was told to hand back every dinar tendered.
Reachable two ways at realistic prices — a per-tablet line under 167 IQD with
the default 25% cap, or (confirmed live) a **2,000 IQD item at 94% discount**
from a manager role, which returned all 250,000 IQD tendered.

### F2 is the clearest "same root, different symptom" case yet

`_save_audit_lines` parsed counts with `float()`, which accepts `"nan"`. The
count was confirmable and locked. Then:

- **IQ**: `qty > nan` is `False`, so the POS oversell guard passed — 500 units
  sold off an empty shelf, recorded at 500,000 IQD.
- **JO**: `qty` is a `Decimal`, so the same comparison raises
  `decimal.InvalidOperation` — **every checkout of that item 500s**, and the
  till stops working until someone corrects the count.

One line, opposite failures, each needing its own fix: IQ uses `parse_money`
(what its cart uses), JO uses `parse_quantity` (what *its* cart uses), so both
sides of the comparison share one ceiling. JO's version also removed the last
raw Python `float` being written to a column against its own Decimal rule.

**A Postgres detail worth keeping:** a plain `CHECK (stock_counted >= 0)`
would **not** catch NaN — NaN sorts above every value, so `'NaN' >= 0` is
true. `>= 0 AND < 'Infinity'` rejects negatives, NaN and both infinities in
one expression. Verified against both databases before being written.

### The patch release, and why it was needed the same day

v1.14.0/v1.12.0 put those CHECKs in `CREATE TABLE` only — correct on a fresh
install, **absent on every upgraded one**. That is precisely §53's trap, and
§53 is in this file because the project has been bitten by it before. The
user's steer that morning ("not deployed yet, no migration needed to preserve
old data") was about *data*; the asymmetry is about *convergence*, and the two
real installs on this machine (§4a) upgrade rather than reinstall. Added to
`INCREMENTAL_SCHEMA_STATEMENTS` in v1.14.1/v1.12.1, with the repair ordered
**before** the `ADD CONSTRAINT` — a constraint that trips on an existing row
aborts the update, and `_run_schema_sync()` uses `check=True`, so a clinic on
that version could never update again. Strictly worse than the bug.

### What the audit could NOT break — worth as much as the findings

Re-run after the fixes, the hostile sweep now reports **zero** findings where
it previously found the one 500. Also held, under deliberate attack:

- **1,028 hostile GET probes per app** — 22 id-routes × 14 malformed ids, 27
  list/search routes × 22 nasty values (SQL wildcards, injection shapes, RTL
  overrides, 500-char strings, `1e999`), 14 paginated views × 9 page values.
  One 500 in the whole matrix, and it is F4.
- **Four concurrency races, all correctly serialised**: two tills on the last
  unit (1 sale, not 2), two staff paying one bill, two receptionists on one
  slot, two registrations of one phone number. The `FOR UPDATE` ordering and
  the idempotency key do what §49 claims.
- **Permissions**: a real custom role holding one permission reached 1 of 45
  pages, leaked no write route, and could not promote itself to Admin.
- **CSRF** (missing *and* forged), logged-out access, and login lockout.
- **The browser walk**: 33 pages per app, **zero CSP violations, zero inline
  `on*=` handlers, zero console errors**, no mobile overflow, no native
  dialogs — §51's two conventions holding in the rendered DOM, not just in the
  source-scanning tests.

`SIMULATION_AUDIT_2026-09-11.md` §8 is the full list, and doubles as a
"do not re-audit this" note.

### Two guards that were born blind, caught during this work

§7.3 keeps earning its place:

1. The first verification script checked NaN rejection against a **confirmed**
   audit session — which refuses every save regardless of value. Five
   assertions passed while proving nothing. Rewritten against a Draft, with a
   control before *and* after the rejections.
2. The first F4 mutation reverted only half the fix. The other half still
   caught the bug, so the mutation reported NOT PROVEN — correctly. Both
   halves now come out together.

`scripts/simulation/prove_guards.py` reverts each fix, restarts the app, and
asserts the bug returns: **10/10 proven.** A mutation that changes nothing is
a failure there, which is what caught the second case above.

### Two smaller things fixed in passing

- A cash-drawer count that came out over or short was flashed as an **error**
  though the audit had saved, so staff re-ran counts already recorded. Both
  apps gained a `.flash.warning` state, built from the `--warn` tokens both
  already carried (dark mode included).
- JO's `inventory_catalog_create_barcode` is renamed to IQ's
  `inventory_catalog_barcode_generate`. Same URL, same behaviour; the apps
  simply had two names for one identical route.

### And one the work surfaced in a test, not in the app

`test_frontend.py`'s citation guard had two latent flaws: its filename pattern
excluded `-`, so a dated document matched as `11.md` and reported a citation
no index entry could ever satisfy; and it globbed only the repo root, so after
§49's split it was checking a fraction of the surface. Both fixed. Counts
after all of this: **IQ 761, JO 736, zero skips.**

---

## 56. Seam rules, and the Arabic toggle — 2026-09-11

Two pieces of work, **both on `main` in each app and deliberately NOT
released**: the localization catalogue is partial by design (below), and a
clinic should not get an "update available" prompt for a half-translated UI.

### 56.1 The seam audit — three more of the same bug

`SEAM_RULES.md` is the durable artefact; this is the summary. Five of six
§55 findings shared one shape — a rule present in one code path and missing
from its sibling — so the next step was to audit for the shape itself. Three
more:

- **S1 (IQ only).** `visit_billing_save` has always taken the visit row
  `FOR UPDATE`, and its comment says the lock is there *"so a concurrent
  discount save on the same visit serialises behind this one"*. **A lock only
  serialises if both sides take it**, and `visit_discount_save` never did —
  nor did `inpatient_discount_save` or `inpatient_billing_add`. The two guards
  that stop a discount landing on a non-discountable line were each validating
  against a snapshot the other had already invalidated, and because the paths
  took locks in different orders they **deadlocked outright**. Reproduced at
  2/25 trials plus 46 `DeadlockDetected` 500s; 0/25 and zero deadlocks after.
  **JO had locked all four routes from the start and was clean throughout**,
  which is the only reason the asymmetry was visible at all.
- **S2/S3 (both apps).** `/admin/logs` and `/consignment/sales` took `?date=`
  straight into the query while four sibling list pages validated theirs.
  Neither 500s — the value reaches a text-prefix comparison, matches nothing,
  and renders an empty page with no warning. On the audit log that is
  indistinguishable from *"nobody did anything that day"*, on the one screen
  whose entire job is showing what happened.

`tests/test_seam_rules.py` (both apps) now enforces four rules, each derived
from a defect rather than invented. **Rule 3's first draft was a regex that
stayed green through a reintroduced F2**, because F2 assigns the form value to
a local before calling `float()` on it — it now walks the AST and tracks
request-derived locals. A guard proven blind on its own first mutation run is
the entire argument for §7.3.

The exploratory half, `scripts/simulation/seam_audit.py`, is a **candidate
generator and cannot be an oracle**: matching a guard by name under-reports
when a guard is delegated to a helper, and inlining helpers over-reports the
other way. Its useful output is the both-apps vs one-app split — S1 surfaced
as one real finding among thirteen IQ-only holes.

### 56.2 Arabic toggle — mechanism complete, translation partial

`ARABIC_LOCALIZATION_PLAN.md` §4, §6, §7 executed; §5 (wrapping every string)
is deliberately incomplete.

**Why it is not shaped like the dark/light toggle it was modelled on:** theme
is a client-side attribute flip because both palettes already sit in the CSS.
Language cannot be, because the *text* is written into the HTML by Jinja on
the server. So the toggle sets a cookie and the page reloads, and
`<html lang>`/`<dir>` are rendered server-side — a direction flip applied
after the page has painted LTR is both jarring and wrong for accessibility
tooling.

- **RTL cost almost nothing.** All 16 physical LTR-only CSS declarations
  became logical properties (`inline-start`/`inline-end`/`start`/`end`), so
  English renders identically and Arabic follows direction. Only two cases
  needed an explicit `html[dir="rtl"]` override.
- **Arabic-Indic digits hook into the existing `|money` filter**, the choke
  point every displayed amount already passes through — no per-template edit
  for money. §7.1's boundary is asserted rather than assumed: never on a value
  that will be parsed back, never on an `<input>`, never on an ID, never in
  `pdf_export.py` (§0, permanent).
- **22 of 46 strings translated.** The rest are clinical, money and
  report-heading vocabulary that §3 reserves for the translator — left blank
  so gettext falls back to English. Both apps work in Arabic today with those
  items in English. `ARABIC_TRANSLATION_QUESTIONS.md` is the batch.

**An existing guard caught a real regression in this work:** the language
toggle button shipped at 40x24 and `test_browser.py`'s touch-target floor
failed it on phone and tablet. A control too small to hit with a thumb is a
defect, not a style preference.

**And the input-boundary guard needed two attempts to prove.** The obvious
mutation — pushing `|money` into an input's value — left the input *empty* on
a fresh page, so the test passed while testing nothing. It is only known to
work because the second attempt used an input carrying a real value. Same
failure mode as §55's confirmed-session blind test, one day later.

Counts after both pieces: **IQ 789, JO 764, zero skips**, 42 test files each.

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
| 32 | ⚠ **the soak found missed jobs were silently skipped**; stale-bytecode trap | scheduling, sleep/off behaviour, or a fix that looks broken |
| 33 | ⚠ **the same bug one layer down: macOS freezes the monotonic clock during sleep** | anything scheduled; read with §32 |
| 34 | ⚠ code review of the monitoring work: 9 real findings, incl. a leaked credential | before shipping monitoring; on writing guards that actually hold |
| 35 | Settings page regrouped; the 760px breakpoint retired for auto-fit | touching Settings, or any `.form-grid` layout |
| 36 | ⚠ **the 760px breakpoint swept from both apps**; iOS zoom + 44px targets on tablets | any responsive/CSS work; on guards that look in the wrong place |
| 37 | ⚠ the tick and the cron raced and duplicated; one guarded entry point | scheduler work; on redundancy needing coordination |
| 38 | one 16px card-spacing unit; the drift was app-wide and identical in both | adding a card, or any spacing question |
| 39 | ⚠ **a vanished backup destination reported as healthy**; files never checked | backups, or trusting a log over the filesystem |
| 40 | ⚠ **the health banner was a self-deleting toast**; Settings never shrank on a phone; IQ's browser tier had never run | monitoring UI, responsive CSS, or before trusting a skip count |
| 40.4 | the pre-Layer-1 backup alert duplicated the banner; suppressed narrowly | adding a Dashboard warning, or touching `backup_alert_message()` |
| 40.5 | `backup_failing`'s quoted error duplicated the folder finding | adding a self-check finding, or wording one |
| 40.6 | ⚠ **`selfcheck.py` was never identical across the apps, despite saying so** | before trusting any in-file parity claim |
| 41 | ⚠ **a failing backup erased the evidence its folder was real, and the app fabricated a new one** | backups, the self-check, or judging the severity of a degraded-path bug |
| 42 | ⚠ **a Python upgrade could stop either app starting, forever and silently** | venvs, the launcher, or deploying to a machine someone else updates |
| 43 | `consecutive_fail_days()` ported into JO; the test pair that can tell insert order from timestamp order | the self-check, the Dashboard modal, or writing a test meant to catch a *robustness* gap |
| 44 | ⚠ **`isolated_test_env.sh` recorded the wrong PID; `down`'s "still running" guard could not fire** — fixed 2026-09-09 | before trusting a guard you have not watched refuse, in tooling as much as in tests |
| 45 | microchip number on patients: optional, unique when present, searchable however it is typed | adding a field that must be searchable, or a constraint to a brand-new column |
| 46 | ⚠ **the Settings page spent the clinic's 60/hour GitHub quota on page loads, then reported a rate limit as being offline** | anything that calls an external API, or any `except Exception` that renders a fixed message |
| 47 | ten saved web pages committed into `static/` and served publicly; the guard against it, and its false positive | before trusting a new guard, and when a fix is a deletion |
| 48 | ⚠ **the full-application review: 33 of 37 findings shipped in this pass (M3 is §49, the last three are §51), incl. a Settings gate that was never enforced, an unrooted folder browser, and boarding being unrefundable** | **before re-auditing anything; and before adding a permission key, which grants it to nobody on an existing install** |
| 49 | ⚠ **`app.py` split into six blueprints per app (7,200 → 1,300 lines), and the four things that broke while a green /health and a clean render sweep said otherwise** | **any work in `routes/` or `core.py`; before writing a test that parses source text** |
| 50 | Coverage re-measured per module after the split (65%, and which blueprint the old 66% average was hiding); IQ has a `money.py`, JO deliberately has none; the doc sweep that followed | before quoting any coverage figure; before citing a file:line in a plan doc |
| 51 | ⚠ **the last three findings: CSP nonce (and the runtime-generated handlers the review missed), pos_checkout extracted, inline styles — plus two guards that were born blind** | **before touching a template's on*= or style=; before trusting a new static guard** |
| 52 | ⚠ **restore drill 2026-09-11: IQ passes on a pre-update backup; JO has no install on this machine at all** | **before a release; and before assuming a red drill means the backup code is broken** |
| 53 | released as IQ v1.13.0 / JO v1.11.0; the CHECK constraint that would have worked on fresh installs and failed on upgrades; setup.py installs an app if given an unknown flag | before any release; before running setup.py by hand |
| 54 | ⚠ **JO reinstalled: both apps default to the same two ports, and three install-layer bugs that only a fresh install can reach** | **before installing either app anywhere; before touching setup.py or docker-compose.yml** |
| 55 | ⚠ **the live-use simulation audit: six findings, five of them at a seam where one path had a rule and its sibling did not; one NaN with opposite symptoms per app; and what 1,028 hostile probes could NOT break** | **before adding a rule to one money/validation path; before trusting that a green suite means a behaviour is covered** |
| 56 | ⚠ **three more seam bugs (a lock only one side took, two unvalidated date filters), and the Arabic toggle: mechanism done, translation partial** | **before adding a cross-cutting rule — read SEAM_RULES.md; before touching localization or a .po file** |
| 57 | ⚠ **Arabic finished (IQ v1.15.0 / JO v1.13.0), and three bugs it flushed out: a translated `<option>` posting Arabic into the cash register's totals, a `%(name)s` Jinja insists on filling that 500'd six pages per app in BOTH languages, and `~` escaping markup before `|safe` sees it** | **before translating anything, before adding an `<option>`, and before writing a checker you have not watched fail — this one reported CLEAN against a broken page three times** |
| 58 | ⚠ **released IQ v1.16.0 / JO v1.14.0 — the language is a clinic SETTING now, not a per-browser cookie (two staff can no longer be on two languages), and Inpatient/Boarding/Refunds were renamed in Arabic** | **before touching `_select_locale`, the settings form, or any of the three renamed terms — and read 58.2 before any find-and-replace on an Arabic word** |
| 59 | ⚠ **five UI bugs a clinic found by USING the app — every one HTTP 200 with valid JS and invisible to 823 tests; plus the loading-shell blind spot that meant the JavaScript-error test never covered /insights or /retention** | **before trusting a green browser suite; before reading any page straight after goto; before porting chart or palette code between the apps** |
| 60 | ⚠ **the health banner (self-check + backup alert) translated — and why a message that is STORED cannot be translated where it is written; one of them was untranslatable by construction, not merely untranslated** | **before touching selfcheck.py, backup_alert_message, or any message written to a table and read back later** |
| 61 | ⚠ **JO's update had no progress bar: the component shipped, was styled, and was already used by two of the four long jobs on the same screen — SEAM_RULES S6; plus every job step label was English in both apps** | **before adding a long-running job, and before assuming a missing feature means missing code** |

## 57. Arabic finished, and the bugs it flushed out — released IQ v1.15.0 / JO v1.13.0 — 2026-09-11

§56 left the Arabic toggle working but the wrapping deliberately partial. This
closes it. **IQ 1341 msgids, JO 1329, both fully translated**, and the measured
English left on the rendered pages is seven word instances per app: a shell
command (`python3 setup.py --enable-updates`), a cash-audit note somebody
typed, and two test-data usernames in the login log.

Three bugs came out of finishing it. None of them is a translation problem, and
all three produce a page that looks correct.

### 57.1 The money one: `<option>` without `value=`

An `<option>` with no `value=` attribute submits its **text content**. Wrapping
that text in `_()` therefore makes the form post Arabic into a column the rest
of the app compares against English constants.

Proven end to end, not reasoned about: `/visits/V001/payment` submitted the way
a browser would in Arabic stored `payments.method = 'نقدًا'`.
`logic.cash_register_totals()` buckets any method outside Cash/Card/Transfer
into `other`, so the page showed `Cash 1,688,710 · … · Other 500 IQD` — the
250 just paid was not in the cash total. **A clinic counting the drawer would
find more cash than the system claimed and record a surplus that never
existed.** `scripts/simulation/repro_option_value.py`.

Eighteen options per app were already in that state; twenty-one more were one
`|tr` away from it. The count differed between the apps — **IQ 39, JO 53** —
because the two had drifted in opposite directions on the same seam: JO's
refunds, settlements and distributor-payment forms lacked the explicit value
IQ's had, and IQ's had gaps JO's did not. That asymmetry is the tell for a rule
applied by hand each time instead of once. `SEAM_RULES.md` S5.

Every translatable `<option>` now carries the English constant in `value=`.
`tests/test_enum_labels.py` fails on any that does not.

### 57.2 The 500 one: a placeholder Jinja insists on filling

`{{ _('Only %(stock)s in stock.')|tojson }}.replace('%(stock)s', item.stock)`
reads as though the placeholder survives to JavaScript. It does not: **Jinja's
gettext always runs `rv % variables`**, even when the call passed no keyword
arguments, so the msgid raises `KeyError: 'stock'` while rendering.

Six pages per app returned 500 — `/pos`, `/refunds`, `/appointments`,
`/settings`, `/reports`, `/admin/users` — **in English as well as Arabic**.
Placeholders JavaScript fills are now `{name}`, which carries no `%` and passes
through untouched; `%(name)s` means "Jinja fills this, here, now".
`tests/test_placeholder_args.py` reads every gettext call in every template and
fails on any placeholder the call does not supply.

### 57.3 The invisible one: `~` escapes before `|safe` sees it

Mid-sentence emphasis is passed as a placeholder so Arabic can put it where
Arabic puts it. The obvious idiom is wrong:

| idiom | renders |
|---|---|
| `('<b>' ~ _('all') ~ '</b>')\|safe` | `X &lt;b&gt;all&lt;/b&gt; Y` |
| `('<b>%s</b>'\|safe) % _('all')` | `X <b>all</b> Y` |
| `'<b>'\|safe ~ _('all') ~ '</b>'\|safe` | `X <b>all</b> Y` |

Jinja's `~` escapes its plain-string operands *before* `|safe` marks the
result, so the tags arrive as visible angle brackets. All four candidates were
rendered through the app's own Jinja environment rather than argued about.

### 57.4 A seam gap found on the way

JO had `BIND_PORT` as a module-level constant exposed to templates and used it
on the dashboard. **IQ read the port only as a local inside `main()`** and
hard-coded `:5050` on both the dashboard and Settings — so IQ told staff the
wrong address on any other port. Not hypothetical: both apps ship the same two
default ports and JO had to move to 5051 (§54). IQ now has the same constant,
`main()` uses it so the two cannot disagree, and `tests/test_bind_port.py`
refuses any port literal in a template. `SEAM_RULES.md` S4.

### 57.5 What is translated that a template pass cannot reach

- **Values stored in English.** `enum_labels.py` declares them so pybabel can
  see them, and a `|tr` filter looks them up at render time — case statuses,
  payment methods, species, the roles-and-permissions matrix, the
  cash-register ledger's event types, the inventory badges and the ordering
  sheet's usage trend. Only the display changes; the stored constant is what
  routes validate and CHECK constraints enforce.
  `tests/test_enum_labels.py` compares every declared list against its source
  of truth — and caught a fallback event type ("Payment") and an invented
  grooming status ("In Progress", where the schema says "Waiting") on its
  first run.
- **104 strings (IQ) / 86 (JO) inside inline `<script>`** — empty states,
  confirm dialogs, "Could not reach the server." Through `|tojson`, never bare
  quotes: bare quotes do not break the script, they render `isn&#39;t` on
  screen, which nothing reports. `tests/test_js_localization.py`.
- **52 `{% block title %}` per app**, so the browser tab is Arabic too.
- **Weekday names.** `strftime`'s `%a`/`%b` are C-locale and stay English
  whatever Babel is set to. A `weekdate` filter uses `flask_babel.format_date`
  instead — which takes no `locale=` keyword, unlike `babel.dates.format_date`.

### 57.6 Where the JS strings diverge

Adapted per app, not copied. JO's cash-received note formats to three decimals
and has **no rounding line at all**, because there is no note denomination to
round to (§1.1). JO's update panel reports through `panel.textContent` with an
`actionLabel`; IQ's uses a toast with a `startingMessage`.

### 57.7 Three rounds of a checker that could not fail

`scripts/simulation/check_rendered_js.py` parses every inline script of every
page in both languages with node, and checks no markup arrived escaped. It
reported CLEAN against a deliberately broken page **three times** before it
worked, and each failure was a different lesson:

1. **The app never restarted.** `pkill -f "vz_iq_test_venv/bin/python3 app.py"`
   matched nothing, because `exec env … python3 app.py` rewrites the command
   line to the resolved `Python.app` path. Hours of "verified" output came from
   a process started before the code under test existed.
   `scripts/simulation/restart_test_apps.sh` kills by **port** and asserts the
   listening pid actually changed.
2. **The page list was hand-written** and did not contain `/retention`. It is
   now derived from the app's own `url_map` — 50 pages, not the 28 someone
   typed — the way `tests/test_permissions.py` does it.
3. **`/retention` is a loading shell.** Several heavy reports return a
   placeholder and navigate to the real URL once a background job finishes;
   the checker was reading the placeholder. It now follows the job through.

`CLAUDE.md` §5 already says a guard you have never watched refuse is not yet
known to be a guard. This is that lesson three times in one afternoon, in
tooling rather than in tests.

### 57.8 Measuring it honestly

`scripts/simulation/ar_coverage.py` counts English words on each rendered page,
excluding anything that appears in a data column. The exclusion list matters
more than the count: with three of its queries silently failing on wrong table
and column names, it reported **316 untranslated words per app**; with them
fixed, **7**. The difference was entirely change-log rows and ids. A broken
data query is now fatal rather than swallowed, because a quiet miscount is the
exact failure this script exists to avoid.

---

## 58. The language became a clinic setting, and three features were renamed — released IQ v1.16.0 / JO v1.14.0 — 2026-09-11

Both from the clinic, after using §57 for an afternoon. **Released** — MINOR in
both, because the language setting is a new capability. Verified through each
app's own `updater.check_latest_release()` against the live repo, not just
against the GitHub API: tag matches `VERSION`, tarball attached, release body
is the CHANGELOG entry, and `is_update_available()` correctly returns False for
a build that IS the latest.

**The upgrade case needed its own check, and it is the interesting part.** No
schema ships with this release, so nothing creates the `language` row — every
upgrading clinic starts with it absent. Simulated by deleting the row: both
apps render English, `/settings` renders, and the dropdown is there to set it.
One nuance worth knowing if these options are ever reordered: with the row
absent, *neither* option carries `selected`, so the browser shows the first one.
That is English today and matches what the app actually renders, but it is true
by position rather than by intent — the same idiom `theme_palette` has used all
along.

**A clinic that was using Arabic reverts to English on upgrade**, and there is
no way around it: the old preference lived in a browser cookie, so the server
has nothing to migrate from. The CHANGELOG says so in the first entry an admin
reads, because the CHANGELOG is the only thing they see before clicking Update
Now.

### 58.1 The language is a saved setting, not a header toggle

The "العربية" button is gone. The language is a dropdown in **Clinic
Settings**, saved with the same button as Clinic Name and the backup folder,
and it behaves like `theme_palette` in every way that matters: clinic-wide,
DB-backed, read server-side before first paint.

That is a real behaviour change, not a relocation. The cookie was **per
browser** — two receptionists could be looking at two different languages, and
a new phone started in English. The setting is **per clinic**: a second session
that has never touched it now agrees, which is the property the cookie could
not provide and the reason for the move.

`_select_locale()` reads `logic.get_setting(db, "language", "en")`, wrapped in
`try/except` and cached in `g`. The wrapping is not defensive habit: the
selector runs on **every** render including the 500 page, and the likeliest
reason a page is failing is the database — a locale selector that raised there
would replace the error page with a second error, which is the page you least
want to break and the one least likely to be looked at before release.
`inject_globals()` already carries that comment for the same reason; this is
the same hazard one layer lower.

The submitted value is **whitelisted in the route**, exactly as `theme_palette`
is, because it reaches Flask-Babel directly. An unknown locale does not error —
it falls back to English, which to the person who just pressed Save is
indistinguishable from "the setting did not save".

`/set-language/<lang>` and `is_safe_local_path_url()` are removed with the
button they existed for. The open-redirect guard that helper carried is gone
because the redirect is gone; `is_safe_local_path()` (the login `next`
parameter) is untouched and still in `auth.py`.

**JO's dropdown sits in a different place.** IQ's goes beside Color Palette; JO
has no palette field at all (§1, one palette by design), so its Language field
follows Clinic Opening Date. Same field, adapted to each app's own form.

### 58.2 Three features renamed

| | was | now |
|---|---|---|
| Inpatient | التنويم | الإقامة المرضية |
| Boarding | الإيواء | الإقامة الفندقية |
| Refunds | المرتجعات | المرتجعات النقدية |

64 entries in IQ, 62 in JO, **each written out rather than substituted.** A
find-and-replace would have been wrong three ways, and all three are the same
lesson: the term is not a token, it is a word in a sentence.

1. **"تنويم" is a noun AND a verb.** As a noun it is the ward — that is what
   was renamed. As a masdar it is the *act* of admitting: "تنويم المريض" is
   "admit the patient", and substituting a noun phrase gives "الإقامة المرضية
   المريض", which is not Arabic. Every verbal use became **إدخال**, a word the
   catalogue already used ("الحيوانات المُدخلة حاليًا"). So "Admit Patient" is
   إدخال المريض and "Admission Date" is تاريخ الإدخال, while "Inpatient Cases"
   is حالات الإقامة المرضية.
2. **"المرتجعات" means two different things in this app.** A refund returns
   MONEY to a client; a consignment return sends STOCK back to a distributor.
   Only the first is المرتجعات النقدية. The consignment side had already been
   disambiguated in §57 (`Returns` → المرتجعات إلى المورد, `Consignment
   Returns` → مرتجعات الأمانة) and is deliberately untouched — calling a
   distributor's stock return "cash returns" would be worse than the ambiguity
   it replaced.
3. **`Housing` is بيئة الإيواء and does not change.** It is the patient's
   living environment — Indoor / Outdoor / Stray — and merely shares a word
   with the boarding service.

After the pass, zero entries in either catalogue still carry the old terms,
and the three exceptions above still read as they should. That check is worth
more than the count: "no survivors" and "nothing was skipped" are different
claims, and only the first is cheap to verify.

### 58.3 What the tests had to become

`test_localization.py` set a cookie in almost every test, and its autouse
fixture deleted one. Both are now writes to the `language` row — and the
fixture's docstring got *stronger*, not weaker: a cookie only followed the
session-scoped `client`, but this row is read by every request any test in the
suite makes. It is global state, so leaving it on "ar" would break every test
that asserts on English flash text. That failure has already happened once in
this file's history, under the cookie, as nine failures in an unrelated file.

The §3 block changed from testing a route to testing a saved field: the form
switches the language, an unknown value is refused, **a second session
agrees**, and the old route really is gone. Each was mutation-tested —
reverting the selector to a cookie fails eight of them, and a stub route
brought back for ten seconds fails the fourth.

---

## 59. Five UI bugs a clinic found by using the app — released IQ v1.16.1 / JO v1.14.1 — 2026-09-12

Reported from real use of the v1.16.0 / v1.14.0 build. **Released** as a PATCH,
together with §60. What they have in common is worth more than any one of them:
every single one rendered a page that is HTTP 200, has valid JavaScript, and
looks plausible in a screenshot. Nothing in a 823-test suite, a 1,028-probe
hostile sweep or a 50-page render checker saw any of them.

| # | Symptom | Cause |
|---|---|---|
| 1 | the Grooming badge printed over the next column in Arabic | `white-space: nowrap` on a badge whose text got four times longer |
| 2 | Create Barcode drew nothing, in both languages | the render function was bound to a load event that had already fired |
| 3 | the bar chart could not fill its card; the doughnut was enormous | Chart.js sized the WIDTH from an aspect ratio derived from a height attribute |
| 4 | Add Role barely fitted a laptop, and could not be submitted on a phone | six category blocks stacked, and no height cap or scroll on any modal |
| 5 | the payment chart was a blank white card | it was empty, and an empty chart said nothing |

### 59.1 Measured, not eyeballed

Each was quantified before it was touched, because three of the five look like
taste and are not:

- **The badge.** `nowrap` keeps the text on one line but does **not** stop the
  box shrinking. At a 900px table the text needed 99px inside a 71px box — 28px
  of it rendered outside the badge and over the neighbouring cell; at 700px,
  50px. `normal` gives zero spill at every width and costs two extra lines of
  height. JO never had the `nowrap`: an IQ-only divergence.
- **The modal.** 894px tall in a 900px viewport — six pixels of headroom. On a
  390x844 phone: 1374px, top clipped at -281, **submit button unreachable**,
  `overflow-y: visible`, `max-height: none`. A role could not be created on a
  phone at all. Flowed into three columns it is 682px on a laptop; capped and
  scrollable it fits every size with the button reachable.
- **The charts.** Both canvases were 510px wide because their height times an
  inferred 1.36 (revenue) or 1.00 (payment) ratio said so — the doughnut is a
  square as tall as the card is wide, by construction.

### 59.2 The pie chart was not broken, and that matters

It had empty labels and empty data because `payments` had no rows in the
window — corroborated by the clinic's own screenshot, which reads *العملاء ذوو
زيارات مدفوعة: 0* two inches above the blank card. Inserting three payments
drew it immediately.

So the defect was never the chart. It was that **an empty chart renders as a
blank white card with a title**, which is indistinguishable from a broken one.
The tables on the same page have had empty notes all along; the charts did not.

### 59.3 What the fix broke, and what caught it

Porting IQ's chart code into JO carried `_cssVar('--primary')` across. **JO has
no `_cssVar`**: it ships one palette and writes hex literals, where IQ reads
CSS custom properties because it has several to follow (§1). The result is a
`ReferenceError`, the doughnut is never constructed, and its canvas sits at
Chart.js's 300x150 default inside a 510x320 box.

The new chart guard caught it within minutes. `CLAUDE.md` §2 exists for exactly
this and was not followed; the guard is what made the cost minutes instead of a
release.

### 59.4 The blind spot worth more than the five bugs

`/insights` and `/retention` answer with a **loading shell** that polls a
background job and then navigates itself to the real page. `_visit()` in
`tests/test_browser.py` did `goto(..., networkidle)` and read its error list
immediately — so it has always been reading the placeholder, and
`test_no_page_raises_a_javascript_error_or_fails_an_asset` **has never covered
the two heaviest pages in the app**. That is how the `_cssVar` ReferenceError
above sat on /insights while the JS-error test passed.

`_visit` now waits for the shell to resolve, and with that it catches the error
it previously missed — verified by reintroducing it.

**This is the third time this shell has hidden something** (§57.7 has the other
two: a checker whose page list omitted /retention, and one reading the shell
instead of the page). Anything that reads a page straight after `goto` is
looking at a placeholder on these routes.

### 59.5 Guards added

Five, each mutation-tested against the bug it names:

| Guard | Refuses |
|---|---|
| `test_the_barcode_label_actually_draws_a_barcode` | an empty `<svg>` — asserts on the drawing, since the PAGE rendered fine throughout |
| `test_a_modal_never_grows_taller_than_the_screen` | a modal taller than a phone, or a submit button it cannot reach |
| `test_a_chart_fills_its_card_rather_than_its_aspect_ratio` | a canvas leaving its card unused |
| `test_an_empty_chart_explains_itself` | a chart card with neither a chart nor a note — with a floor, because the selector going stale would otherwise make it pass while checking nothing |
| `test_nowrap_translations.py` | translated text pinned to one line in an INLINE box |

The last one is deliberately narrow. It flags `<span>`/`<button>`/`<a>` and
**not** `<td style="white-space:nowrap">` — measured, not assumed: a table cell
is sized by the table layout to fit its content, and four such cells across
/price-list, /pos/history and /distributors overflow by zero in Arabic at
900px. Keeping a row of action buttons on one line is legitimate; pinning a
word you are going to translate is not.

---

## 60. The health banner, and a message you cannot translate where it is written — released IQ v1.16.1 / JO v1.14.1 — 2026-09-12

The self-check findings and the backup alert were the last English in either
app. They are also the ones that matter most at the moment they appear: they
are what tells a clinic its backups are failing, its backup folder has
vanished, or no backup has ever been verified as restorable.

**With these done, the only English left anywhere is `python3 setup.py
--enable-updates`, which is a command.**

### 60.1 Why a stored message cannot be translated where it is written

A self-check finding is **written** to `self_check_log` when the scheduler
runs and **read back** whenever someone opens the dashboard — possibly in
another language, certainly at another time. Translating at check time freezes
whichever language happened to be active when a background job ran, which is
not a property anyone chose.

So `selfcheck.py` stores three things and the split is the whole design:

| field | what it is | who reads it |
|---|---|---|
| `message` | the RENDERED English | the heartbeat, `self_check_log`, several tests |
| `msgid` | the same sentence with `%(name)s` | the `finding` template filter |
| `args` | the values | the same filter, at render |

**`message` deliberately stays the rendered English**, and that is not
conservatism. `test_selfcheck.py` asserts that a particular error string is
**absent** from `backup_failing`'s message — a check that means something only
while the value is actually there to be absent. Moving the value into `args`
would have left that test passing against a template that could never contain
the string under any circumstances. A guard made vacuous by a refactor is
worse than no guard, because it still reports green.

Rows written by older builds have no `msgid` and fall back to `message`, which
is English — exactly what they already displayed.

### 60.2 The one that could never have been translated at all

`logic.backup_alert_message()` predates the self-check and reported four of the
same conditions through its own mechanism: a bare f-string. Not "untranslated"
— **untranslatable**. The interpolated error made every message a different
string, so no catalogue entry could ever have matched one, and no amount of
translating would have changed the page.

It now returns the same shape a finding does, and both render through one
`finding` filter. JO's dashboard markup for that banner differs from IQ's, so
that edit is its own rather than IQ's copied across.

### 60.3 Which numbers get Arabic-Indic digits, and which must not

Numeric arguments go through `core.display_number` like every other number in
a message — `٩ يومًا`, `٠.٤٢ غيغابايت`. `%(error)s`, `%(detail)s` and
`%(failures)s` do **not**: they carry file paths, OS error text and schema
statements, and rewriting the digits inside `Errno 13 /Volumes/Backup2` would
corrupt the one detail that says what went wrong. The filter converts a value
only when it is a number.

### 60.4 Guards

Four, each mutation-tested: every `_finding` message marked with `N_()` so
pybabel can see it (an f-string cannot be), a floor so the scanner cannot pass
by matching nothing, `message` still carrying its values, and a mismatched
argument set falling back rather than raising — because the thing that would
disappear is the banner reporting the problem.

---

## 61. Why JO's update had no progress bar — 2026-09-12

Asked after watching an IQ update draw one. **Unreleased on `main`.**

### 61.1 The answer

JO's Update and Rollback reported progress as a single line of plain text —
`Validating release (2/6)` and nothing else. No bar, no elapsed time, while
the app restarted underneath the person watching.

**Nothing was missing.** `progress.js` ships in both apps. JO already called
`VZProgress.poll`/`render` for its Backup and Restore jobs — in the same
template, about a hundred lines from the code that did not. Only the
Update/Rollback path hand-rolled a `setInterval` over `job-status` and wrote
into `panel.textContent`. `waitForRestart()` had the same split, so even when
IQ's bar was drawn JO dropped back to plain text for the restart phase.

Two of four sibling paths had the rule. Nothing failed, because each path was
individually correct. `SEAM_RULES.md` S6 — and the cheapest entry in that
register to have avoided, since the component was already imported, already
styled and already used on the same screen.

Fixed by matching **JO's own Backup/Restore handlers**, not IQ's update
handler. Same component, this app's idiom.

### 61.2 Three things that were English in both apps

Fixing the bar made them visible, because a bar with English labels is more
obviously wrong than a line of English text:

- **The job step labels.** `"Backing up database"`, `"Validating release"`,
  `"Restoring database"`, and the loading-shell steps on the heavy reports —
  twenty-odd literals across `routes/settings.py`, `app.py` and
  `routes/consignment.py`. They are sent to the browser as JSON and drawn in
  the panel, so they are display text, and they were the last English a clinic
  would see at the moment it is watching most closely. Wrapped in `_()` rather
  than `N_()`, because `jobs.start()` runs inside the request the admin
  clicked in — the locale is the one on their screen.
- **The action labels**, concatenated as `successMessagePrefix + ' complete.'`,
  so "Update complete." and "Rollback failed." could never translate.
- **`waitForRestart` wrote its argument straight into the panel**, so a job
  finishing without a message printed `undefined` on the one screen an admin
  stares at during a restart.

### 61.3 The guard that earned its keep the same afternoon

Rewriting JO's handler, I wrote `_('%(job)s failed to start.')` where the
placeholder is filled by JavaScript — the exact bug §57.2 documents, which
raises `KeyError: 'job'` while rendering and turned `/settings` into a 500.

`tests/test_placeholder_args.py` catches it, and I found it by loading the
page rather than by running the tests first. The guard was right, the order of
operations was not. Verified afterwards by reintroducing it: the test fails.

### 61.4 Also

Ordering Sheet is **كشف النواقص**, the clinic's term, replacing كشف الطلبات
everywhere — including inside the help sentences, since leaving those would
have one page calling it two different things. Changed in the catalogues and
in the `ar_batch*.py` sources, so a rebuild from source keeps it.

---

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
