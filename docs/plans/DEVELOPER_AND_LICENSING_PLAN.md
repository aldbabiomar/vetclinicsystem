# Plan — Developer area, licensing, and native PostgreSQL

**Written 2026-09-25. Status: NOT STARTED — waits for the merge.**
Owner decisions are in §1.1 and were taken with the owner on 2026-09-25; they
override the original request wherever the two disagree (§1.4 lists every
place they do). Progress goes in the log, §18.

This plan is written to be handed to a different Claude session. Read, in this
order, before touching anything:

1. `CLAUDE.md` — the ground rules. Especially: the money setting (§3), the
   isolated test environment and the two predecessor installs you must never
   touch (§4), tests under **both** money settings and mutation-proving every
   guard (§5), localization rules (§6).
2. `docs/plans/UNIFIED_CODEBASE_PLAN.md` — the merge this plan builds on,
   especially §3.2 (money setting), §5.3 (permission, settings-field and
   navigation registries), §5.4 (maintenance mode, error handler) and its
   progress log §13.
3. `docs/CODE_AUDIT_2026-09-25.md` — S1 and S2 (§3) are the two security
   findings this plan must not reintroduce in a new shape.
4. `docs/SEAM_RULES.md` — read-only mode is a rule that must hold on every
   write path at once, which is exactly what that document is about.

---

## 0. Preconditions — do not start until these hold

1. **The merge is done**: `UNIFIED_CODEBASE_PLAN.md` §12 "Done means" is met
   and its progress log says so. If it is not, **stop and tell the owner**.
   This plan edits settings, auth, the updater, setup and the schema, which
   merge phases 3–7 restructure; running both at once means rework and
   conflicts. (Owner decision L-4.)
2. **1.0.0 has not been published.** This plan is meant to ship in the first
   release. While 1.0.0 is unpublished, schema changes go into
   `migrations/0001_baseline.sql` in place (then
   `scripts/schema_snapshot.py --write` and read the diff), per `CLAUDE.md`.
   If 1.0.0 *has* shipped, every schema change below becomes a new numbered
   migration instead; say so in the progress log.
3. `git status` is clean, or you know whose work is uncommitted. Another
   session may still be finishing the merge.

---

## 1. Decisions

### 1.1 Taken by the owner, 2026-09-25 — do not re-ask

| # | Decision |
|---|---|
| **L-1** | **The repository becomes private.** Each clinic gets its **own** read-only GitHub token (fine-grained, *Contents: read*, this one repository), entered in Developer → Updates. Revoking one clinic's token stops only that clinic's updates. **Overrides merge decision D-1** ("public, so the updater needs no credentials"). |
| **L-2** | **The 15 palettes stay (D-12), but the developer chooses the palette**, in Developer → Configuration. Clinics cannot change it. There is no custom colour picker and no logo upload. **Overrides D-12's placement in Settings.** |
| **L-3** | **The money setting moves to the developer** (Developer → Configuration). Its lock is unchanged: changeable until the first money is recorded, then locked. The phone format still follows it. **Language, time zone and weekend days stay clinic settings** in Settings. New countries are added as built-in money profiles in code, with their own tests, never typed into a form. **Overrides D-9's placement** (the rule itself is unchanged) and changes D-10's wording (§9.3). |
| **L-4** | **Timing:** after the merge, before 1.0.0 (§0). |
| **L-5** | **Clinic admins can enter a license key and run the full data export.** Both work outside the Developer area. A key cannot be forged, so letting the clinic paste one is safe, and an expired clinic can still take its own data. Every other Developer section is developer-only. |
| **L-6** | **Developer access is a signed, time-limited Developer Pass**, never a password. The owner's brother (the vendor) signs a pass for **one** install with his vendor tool; it is valid for a few hours. Nothing secret is stored at the clinic. |
| **L-7** | **Setup requires a valid license key.** `setup.py` refuses to finish without one. There is no trial state. |
| **L-8** | **Clinics can still check, apply and roll back updates** themselves (`manage_maintenance`, as today). Only the update *configuration* — the GitHub token — is developer-only. |
| **L-9** | **Expiry never locks the records away.** Warnings before expiry, then a grace period, then **read-only mode**: view, search, print and export stay available, backups keep running, and the switch to read-only happens at a sign-in, never mid-task. (From the original request, §9.) |
| **L-10** | **Rejected — do not build** (§1.2). |

### 1.2 Rejected — do not build, and do not infer

1. A feature-switch / checkbox system for turning modules on or off.
2. Basic / Pro / Full plan presets. (The license carries an `entitlements`
   object reserved for the future; v1 ignores it and shows no plans.)
3. A clinic-facing branding chooser: no custom colours, no logo upload. The 15
   built-in palettes remain, chosen by the developer (L-2).
4. An in-app Docker-to-native migration workflow.
5. Hosted/VPS deployment.
6. Any IQ/JO split: separate apps, forks, or `if` statements on a money code.
7. A remote kill switch or an online license check. Licensing is offline.
8. A hard lockout that hides records (L-9).

### 1.3 Defaults chosen by the plan's author — override before starting if wrong

| # | Default | Why |
|---|---|---|
| A1 | Grace and warning windows are carried **in the signed license** (`grace_days`, `warn_days`), defaulting to **14** and **14** in the vendor tool. | The vendor can give one clinic a longer grace without a code change; the clinic cannot edit it. |
| A2 | A Developer Pass is valid for at most **12 hours**, whatever the pass says. | Limits the damage of a pass pasted into the wrong chat. |
| A3 | **One vendor signing key** signs both licenses and passes; the payload's `kind` field keeps them apart. The app holds a **list** of trusted public keys, each with a key ID. | One key to protect; the list allows rotation (§4.4). |
| A4 | The license is stored **in the data directory**, not the database. | A restore of an older backup must not roll the license back, and the license must not travel in backups, exports or support bundles. |
| A5 | The GitHub token is stored in the data directory, in a file readable only by the app's user, not in the database or `.env`. | Same reason as A4: it must not travel in backups or exports, and changing it must not need a text editor. |
| A6 | The heartbeat URL **stays** in the `settings` table, as today. Only its UI moves. | The code works and has tests; moving storage is churn. Its secrecy is already enforced (`SECRET_SETTING_KEYS`). |
| A7 | Read-only mode allows, besides every page view: sign-in and sign-out, changing your own password, license key entry, the full data export, Backup Now, restore, update check/apply/rollback, **user administration** (so a departing employee can still be disabled), and **clinical notes and contact-log entries on inpatient cases that are already admitted** (animal welfare). Everything else that writes is refused. **Recording payments on existing bills is refused**; that is the commercial lever. | The owner asked for "view, search, print, export and whatever is needed to look after existing patients safely". Payments and inpatient notes are the two calls most worth confirming (§1.5). |
| A8 | Full data export needs `manage_maintenance`, the same permission as backups. | A backup already contains everything the export does. |
| A9 | License key entry needs `manage_settings`. | Ordinary clinic administration. |
| A10 | Developer actions go to a **new `developer_audit` table** that the clinic's log pruning never touches and the app offers no way to delete. Clinic users holding `view_logins_changes` can **read** it. | `audit_log` is pruned by the clinic-controlled `log_retention_days` (`logic.prune_old_logs`); a vendor's actions must not be erasable by the clinic, and the clinic should be able to see what its vendor did. |
| A11 | The database mode is an explicit `.env` value, `VETCLINICSYSTEM_DB_MODE=docker|native`, default **`docker`** (unchanged behaviour). No auto-detection. | On a machine with two PostgreSQL servers, "whatever answers on the port" could set the app up against the wrong, empty database. |
| A12 | The Developer area has its own minimal layout, and works **with or without** a clinic sign-in. | Admin recovery (§11.3) exists precisely for when nobody can sign in. |
| A13 | The vendor message is one plain-text field (escaped, never HTML), a level (information / warning) and an optional expiry. | The vendor writes it in the clinic's language; HTML would be an injection surface. |

### 1.4 Where this plan changes the original request

| Request said | This plan | Why |
|---|---|---|
| The clinic enters the license key in Developer → License | Clinic admins enter it on **Settings → License**; developers can also use Developer → License | L-5; Developer is developer-only |
| Full data export is Developer-accessible | Also available to clinic admins | L-5 |
| Move update management into Developer | Clinics keep apply/rollback; Developer gets the token and the same controls | L-8 |
| Configurable country, currency, money logic, phone, time zone, weekend, language in Developer | Money setting and palette in Developer; language, time zone and weekend stay in Settings; countries are code profiles | L-2, L-3 |
| Do not implement a palette chooser | The 15 palettes stay, chosen by the developer | L-2 |
| Preserve stored configuration / backward compatibility for moved settings | **Nothing to preserve**: the project has never been deployed (`CLAUDE.md`). Move the UI and the gate; keep the storage keys. | No install exists to migrate |
| A private production repository | Private, one token per clinic; no separate releases repo | L-1 |

### 1.5 Worth a second look by the owner (not blocking)

- **A7, payments while read-only.** Refusing them is the lever; the cost is
  a clinic taking cash it cannot record. Moving the payment routes onto the
  allowlist is a one-line change in one registry (§6.4).
- **A7, inpatient notes while read-only.** Allowed for animal welfare.

---

## 2. The honest limit — put this in the docs, once, plainly

The app is installed on the clinic's own computer, with its database, its
Python source and its clock. **Whoever controls that machine can edit the
code, the database or the clock.** Nothing in this plan changes that, and
nothing should pretend to. What the plan does guarantee:

- There is **no supported way** to bypass the license or reach the Developer
  area: no password in the source, no setting, no environment variable, no
  role or permission. Getting around it takes deliberate editing of code or
  files.
- The license cannot be **forged**: the app can only verify, never sign.
- Tampering is **detectable**: an edited license fails its signature, and a
  clock wound back is caught (§5.3).
- Stopping a clinic's **updates** is real: revoke its GitHub token (L-1).

---

## 3. Phase 0 — re-map against the merged tree

The merge moves code (`UNIFIED_CODEBASE_PLAN.md` §3.1). Before writing
anything, find where each of these lives **now** and record the map in the
progress log (§18). The middle column is where it was on 2026-09-25; do not
trust it.

| Concept | Where it was (2026-09-25) | What the merge plan says it becomes |
|---|---|---|
| App factory, auth gate, `before_request` hooks | `app.py` | `create_app()`, `web/` (§3.1) |
| Shared seam for blueprints | `core.py` (`DATA_DIR`, parsing) | `vcs.*` |
| Permission list, system role, `log_change()` | `auth.py` (`PERMISSIONS`, `ADMIN_ONLY_TODAY`, `log_change`) | `web/permissions.py` registry (§5.3) |
| **Settings field → permission registry** | not built (S1 open) | §5.3 — this plan adds a `developer` gate to it |
| **Navigation registry** | not built (P1 open) | §5.3 — this plan adds the Developer entry |
| Settings page, its POST, `SECRET_SETTING_KEYS` | `routes/settings.py` `settings_page()`, `templates/settings.html` | `web/blueprints/settings.py` |
| Money setting and its lock | `money.py` (`SETTING_KEY`, `MONEY_TABLES`, `set_current`) | `vcs/money.py`, `vcs/country/` |
| Palette choice | IQ-only `theme_palette`; D-12 not built yet | built by the merge in Settings (D-12) |
| Clinic clock | `clock.py` (`set_current`) | unchanged in intent |
| Heartbeat | `heartbeat.py` (`URL_SETTING`, `INSTALL_ID_SETTING`), settings section "Remote Monitoring" | unchanged in intent |
| Updater | `updater.py`; token read once at import (`GITHUB_TOKEN = os.environ.get(...)`) | "updater with one repo" (§9 phase 7) |
| Update routes | `routes/settings.py` `settings_updates_*` (`manage_maintenance`) | settings blueprint |
| Backup / restore / tool discovery | `backup.py` (`shutil.which("pg_dump")`, Docker fallback) | unchanged in intent |
| Self-verify | `selfverify.py` (`CREATE DATABASE` for the throwaway) | unchanged in intent |
| Self-check findings, disk check | `selfcheck.py` (`run_self_check`, `_check_disk_low`) | unchanged in intent |
| Setup | `setup.py` `main()` → `check_docker()`, `start_postgres()` | "one installer", `install_slug` (§3.2, phase 7) |
| Scheduler jobs | `scheduler.py` (`nightly_backup`, `daily_self_check`, `verify_restore`, `tick`) | unchanged in intent |
| Admin password reset | `routes/admin.py` `admin_user_reset_password()`; password policy in `auth.py` | S2 fixed in merge phase 4 |
| Login rate limit, lockout | `app.py` `_login_rate_limit_check()`, `auth.login_lock_status()` | B20 fixed in the merge |
| Log pruning | `logic.prune_old_logs()` over `audit_log`, `login_log` | unchanged in intent |
| Background jobs + progress UI | `jobs.py`, `static/progress.js` | unchanged |
| Maintenance mode (503 during restore) | not built (S3 open) | §5.4 |
| Env var prefix | `VETCLINICSYSTEM_` | check |

**Also confirm:** S1 and S2 are fixed (merge phase 4), the settings-field
registry exists, and `install_slug` exists. This plan builds on all three.

---

## 4. Signed tokens — licenses and Developer Passes

Do not invent cryptography. Use **Ed25519** from the `cryptography` package
(pin it in `requirements.txt`; wheels exist for Windows and macOS; confirm
`setup.py`'s dependency step installs it).

### 4.1 Format

```
VCS1.<base64url(payload_bytes)>.<base64url(signature)>
```

- `payload_bytes` is UTF-8 JSON. The signature covers **those exact bytes**;
  the verifier decodes and checks the signature **before** parsing JSON, and
  never re-serialises. No canonicalisation problems.
- base64url without padding. Whitespace and line breaks are stripped before
  parsing, because keys arrive through WhatsApp.
- Reject: unknown version prefix, unknown `kid`, bad signature, wrong `kind`,
  wrong `install_id`, missing fields, times that do not parse. Every refusal
  has its own translated message; none reveals anything secret.

### 4.2 Payloads

**License** (`kind: "license"`):

| Field | Meaning |
|---|---|
| `v` | `1` |
| `kind` | `"license"` |
| `kid` | which trusted key signed it |
| `install_id` | the install it is for (§5.1) |
| `license_id` | unique ID, shown in the UI and the audit |
| `clinic_name` | shown on the License page |
| `issued_at`, `expires_at` | UTC ISO-8601 with offset |
| `grace_days`, `warn_days` | A1 |
| `entitlements` | `{}`; reserved, ignored by v1, must be an object |

**Developer Pass** (`kind: "dev_pass"`): `v`, `kind`, `kid`, `install_id`,
`pass_id`, `developer` (the name that appears in the audit), `issued_at`,
`expires_at`. The verifier refuses a pass whose lifetime exceeds 12 hours
(A2), or whose `issued_at` is more than 10 minutes in the clinic clock's
future.

### 4.3 Trusted keys — the rule that makes forging impossible

The trusted public keys are **constants in the source** (e.g.
`licensing/trusted_keys.py`: `{kid: public_key_bytes}`). **No environment
variable, setting, file or request can add a trusted key** in production. A
configurable trust list is a documented free-license switch.

For tests only, a function `licensing.trust_for_tests(kid, public_key)` adds
an in-memory key. It is called **only** from `tests/conftest.py` and from the
test launcher (§14.4). A test asserts that no production entry point
(`run.py`/`app.py`, `setup.py`, the generated launcher) references it, and
that nothing reads a trusted key from `os.environ` or the database.

### 4.4 The vendor tool — lives in the repo, never holds a key

`scripts/vendor/vcs_vendor.py` (the owner's brother runs it on his own
machine):

| Command | Does |
|---|---|
| `keygen --out PATH` | creates an Ed25519 key, **passphrase-encrypted**, and prints the public key and a new `kid` to paste into `trusted_keys.py` |
| `license --key PATH --install-id ID --clinic-name NAME (--days N \| --expires DATE) [--grace-days 14] [--warn-days 14]` | prints a license string |
| `pass --key PATH --install-id ID --developer NAME [--hours 8]` | prints a Developer Pass |
| `inspect TOKEN` | decodes and verifies against the trusted keys, and prints the payload |

- It refuses to write a key file anywhere inside the repository.
  `.gitignore` covers `*.pem` and `vendor-keys/`. A test scans every tracked
  file for `PRIVATE KEY` and fails on a match.
- **Key custody goes in `docs/DEVELOPER_GUIDE.md`**: keep two encrypted
  offline copies. If the key is lost, no renewal can be issued until a
  release ships a new trusted key. If it leaks, anyone can mint licenses
  until a release removes it.
- **Rotation:** add the new `kid` to `trusted_keys.py` in a release *before*
  retiring the old one, so every install trusts both during the changeover.

---

## 5. Install identity and license storage

### 5.1 `install_id`

A random UUID generated by `setup.py` on first install and written to `.env`
as `VETCLINICSYSTEM_INSTALL_ID`. It never changes, is shown on the License
pages and printed by setup, and is what licenses and passes bind to. It is
**not** the merge's `install_slug` (which names folders and containers) and
**not** `heartbeat_install_id`; leave both alone.

### 5.2 Storage (A4)

- `<data dir>/license/license.key` holds the license string exactly as
  entered, written atomically (temp file + rename).
- `<data dir>/license/state.json` holds `{"max_seen_at": …}` for §5.3. The
  same value is mirrored in `settings.license_max_seen_at`; use the **later**
  of the two.
- Resolve the data directory through the same helper the app already uses
  (`core.DATA_DIR` or its successor), falling back the same way it does for a
  development checkout.
- The app verifies the license at start-up, after every key entry, at every
  sign-in and on the daily scheduler tick, and caches the result in memory.
  **An invalid license never stops the app from starting**; it only sets the
  state.

### 5.3 Tamper awareness

- An edited license fails its signature: state **invalid**.
- **Clock rollback:** every verification records `max_seen_at = max(now,
  max_seen_at)`. If `now < max_seen_at − 24 hours`, the state is
  **clock_wrong**; the message tells the clinic to correct the computer's
  clock. The 24 hours absorbs time-zone and NTP corrections. "Now" comes from
  `clock.py`, never `datetime.now()`.
- A license for another install: state **invalid**, with a message naming
  the install ID it expected.

---

## 6. License states, banners and read-only mode

### 6.1 States

| State | When | Effect |
|---|---|---|
| `active` | valid, more than `warn_days` left | none |
| `expiring` | valid, `warn_days` or fewer left | banner to `manage_settings` holders: "License expires on …" |
| `grace` | expired, within `grace_days` | banner to **everyone**: "Expired on …; the system becomes read-only on …" |
| `read_only` | past grace | read-only at the next sign-in (§6.3) |
| `invalid`, `missing`, `clock_wrong` | §5 | treated as `read_only`, with their own message |

Dates are displayed in the clinic's time zone. Every banner string is
translated (§13). Banners reuse the existing persistent-notice style (audit
M5 moved dashboard warnings off auto-dismissing toasts; do the same here).

### 6.2 Renewal

Entering a newer valid key recomputes the state **immediately for every
session**. Unlocking is instant; locking waits for a sign-in.

### 6.3 Read-only happens at a sign-in, never mid-task

- At sign-in, the auth code stores the state in the session.
- A `before_request` hook refuses a write **only when** the session was
  signed in under a non-writable state **and** the cached current state is
  still non-writable.
- A session signed in while the license was writable keeps working until it
  ends. `SESSION_LIFETIME_HOURS` bounds that (12 hours by default), and the
  grace period is the real buffer.
- Scheduler jobs (nightly backup, self-check, restore verification,
  heartbeat) run outside requests and are **not** affected. A test proves the
  nightly backup runs in `read_only`.

### 6.4 One allowlist, enforced at one place

- A single registry names every endpoint allowed to write while read-only
  (A7). Everything not on it that uses POST/PUT/PATCH/DELETE is refused with
  a translated page explaining why and linking to the License page. GET
  requests are never refused.
- Enforcement is the one `before_request` hook, **not** a check inside each
  route. That is the `SEAM_RULES.md` lesson applied up front: a rule that
  lives in one place cannot be missing from a sibling.
- The UI hides or disables write buttons from a context flag. That is a
  convenience only; the hook is the rule.
- **Test (§14.2):** walk Flask's live `url_map` (the `test_permissions.py`
  approach). Every writing endpoint is either on the allowlist or refused in
  read-only, with a floor on how many endpoints were checked, plus a control
  showing the same request succeeds when the license is active.

---

## 7. Developer access

### 7.1 Sign-in with a Developer Pass

- `GET/POST /developer/login`: paste a pass. Verified per §4, rate-limited
  with the same limiter as clinic sign-in (lock-protected after the merge's
  B20 fix), CSRF-protected like every form.
- On success the session gets `developer = {name, pass_id, expires_at}`,
  **separate** from any clinic user in the same session. It ends at the
  pass's expiry, on `/developer/logout`, or when the session ends.
- The Developer area works **with or without** a clinic sign-in (A12). The
  clinic auth gate exempts `/developer/login`, `/developer/*` (which check
  the developer session themselves) and static files.
- The Developer blueprint (`developer.`) never imports the app module, and
  its endpoint names carry the prefix (`CLAUDE.md` §2).

### 7.2 Why no role or permission can reach it

- There is **no** `developer` permission. It is not in the permission
  registry, so the role editor cannot grant it, and the system Admin role
  (which re-grants itself every permission at seed time) does not get it.
- Tests: a user in the system Admin role with every permission gets the
  refusal on every `/developer/*` route except login (guard). A valid pass
  gets in (control). A role-editor POST naming `developer` as a permission
  has no effect.

### 7.3 Developer audit (A10)

New table `developer_audit`:

| Column | |
|---|---|
| `id` | identity |
| `at` | `timestamptz` |
| `actor` | `dev:<developer name>` or `user:<username>` (clinic admins entering a key or exporting) |
| `pass_id` | for developer actions |
| `action` | e.g. `license.entered`, `license.state_changed`, `admin.recovered`, `update.started`, `update.token_changed`, `heartbeat.changed`, `vendor_message.changed`, `config.money_setting`, `config.palette`, `export.generated`, `support_bundle.generated`, `developer.login`, `developer.login_failed` |
| `target` | what it acted on (user ID, license ID, file name) |
| `outcome` | `ok` / `refused` / `failed` |
| `detail` | JSONB; **never** a secret (§12) |
| `remote_addr` | |

- It is **not** in `logic.prune_old_logs()`'s table list, and no route
  deletes from it. A test asserts both.
- Actions that change clinic data (an admin password reset, a money setting
  or palette change) **also** go through `log_change()` with the actor name,
  so the clinic's own change log shows them.
- Developer → Developer Audit lists it; clinic users with
  `view_logins_changes` can read it from the audit-log page (A10).

---

## 8. The Developer area

Separate pages, not one long page. Every control is wired to real behaviour;
no placeholders.

| Section | Contents |
|---|---|
| **License** | install ID, clinic name, license ID, state, issued, expires, days left, grace and warning windows, and a key entry box. The clinic's **Settings → License** page shows the same thing to `manage_settings` holders (L-5, A9). |
| **System** | §11.1 |
| **Updates** | installed version, latest available (the existing check), apply and rollback (the existing jobs), recent history (the updates log in the data directory), the configured repository (read-only, from `.env`), the **GitHub token** (§10) and a *Test connection* button. There is no version hold: none exists, and this plan adds no features beyond its scope. |
| **Support** | Generate support bundle (§11.2), restore administrator access (§11.3), run the self-check now (existing), test the update connection |
| **Configuration** | money setting and palette, **editable** (L-2, L-3, §9); language, time zone and weekend days shown **read-only** with "clinic setting — change in Settings"; install ID, database mode, PostgreSQL version and tool paths (read-only) |
| **Monitoring** | the heartbeat URL and install ID, moved from Settings (§9.2) |
| **Vendor message** | §11.5 |
| **Data export** | §11.4 (also on Settings for clinic admins) |
| **Developer Audit** | §7.3 |

Navigation: add a Developer group to the navigation registry, shown only
when a developer session is active. It is not tied to any permission.

---

## 9. Settings — what moves and how it is gated

### 9.1 A `developer` gate in the settings-field registry

The merge's settings-field → permission registry (§5.3) exists so that the
template and the POST share one definition (audit S1). Give it one more gate
value, `developer`, and mark `money_setting`, the palette key and
`heartbeat_url` with it. Then:

- `POST /settings` **refuses** a developer-gated key from anyone, including
  the system Admin. Removing it from the template is not enough; that is S1
  exactly.
- Developer routes write those keys through the same save helper, so the
  money-lock rule and `SECRET_SETTING_KEYS` behaviour apply unchanged.
- Test: the system Admin posting `money_setting` / palette / `heartbeat_url`
  to `/settings` changes nothing (guard); the Developer route changes it
  (control). Mutation: remove the refusal and watch the guard fail.

### 9.2 What moves

| Item | From | To | Storage |
|---|---|---|---|
| Money setting (the lock is unchanged) | Settings | Developer → Configuration; Settings shows it read-only, "set by your vendor" | unchanged key |
| Palette | Settings (D-12) | Developer → Configuration | unchanged key |
| Heartbeat URL + install ID | Settings "Remote Monitoring" | Developer → Monitoring | unchanged (A6) |
| GitHub token | `.env` (`GITHUB_TOKEN`) | Developer → Updates | data directory file (A5); **drop the env var** (never deployed) |
| Update apply/rollback | Settings | **stays** in Settings, **also** in Developer → Updates | — |
| Language, time zone, weekend | Settings | stay | — |

### 9.3 Before the money setting is chosen (D-10, reworded)

The money screens stay gated. A clinic user sees: "Setup isn't finished — your
vendor needs to choose the money setting." They are **not** sent to Settings.
`setup.py` accepts `--money-setting IQ|JO` so the vendor can finish in one
step; Developer → Configuration can still change it until the first money is
recorded.

---

## 10. Updates and the private repository (L-1, L-8)

- The updater reads the token **at each call** from the token file (a
  function, not a module-level constant), sends it as `Authorization: Bearer`,
  and never puts it in a log line, error message, job result, redirect or
  audit row.
- The error for a private repository answering 404 must say "not found or no
  access", because GitHub answers 404 rather than 403 for a private repository
  the token cannot see. Keep the existing "GitHub rejected the access token"
  message for 401.
- **Test connection** calls the latest-release endpoint and reports OK, bad
  token, no access, rate limited, or offline. It uses the existing
  error-classification code rather than a second copy.
- Token UI: masked (last four characters), with Replace and Remove actions.
  Removing it disables updates with a clear message. Every change is audited
  **without** the value (`{"token": "set"/"not set"}`, the
  `SECRET_SETTING_KEYS` pattern).
- **Manual step for the owner (list it in the end-of-work report):** make the
  repository private, create one fine-grained token per clinic (*Contents:
  read-only*, this repository only), and run one real update through a
  private-repo token end to end on a throwaway install. Mocked tests cannot
  prove the real download path.
- `docs/RELEASE_WORKFLOW.md`: the repository is private; issuing a token per
  clinic; revoking a non-paying clinic's token; what a clinic sees when its
  token stops working.
- Update `CLAUDE.md`'s decision table: D-1 → private (L-1), D-9 → developer
  (L-3), D-12 → developer (L-2).

---

## 11. Developer tools

### 11.1 System health — reuse, don't rebuild

Show what the app already knows: database reachable (`SELECT 1`), server
version, database mode, PostgreSQL tool paths and versions (§12.2), the
latest self-check result and its findings (`selfcheck.latest`), last
successful backup and last restore verification (from their logs), disk free
(the self-check's own disk check, not a second one), schema behind (the
existing finding), app version and uptime, and the tail of `errors.log`
passed through the redactor (§11.2). **No new health infrastructure.**

### 11.2 Support bundle (developer only)

A ZIP the developer downloads. **Settings go in by an allowlist of
non-sensitive keys, never by excluding a blocklist**, so a new secret setting
is left out by default.

| Included | Excluded, always |
|---|---|
| version, VERSION, Python / OS / PostgreSQL versions, database mode, tool paths | any row of clinic data: owners, patients, visits, bills, payments, sales, refunds, inventory, users, `audit_log`, `login_log` |
| allowlisted settings | the license string, the Developer Pass, the GitHub token, the heartbeat URL, `DATABASE_URL`'s password, `SECRET_KEY`, `.env` itself, the data directory's `license/` and secrets |
| license **state** (state, license ID, expiry, install ID) | |
| latest self-check result, backup/restore/verify log summaries (file names only) | |
| applied schema migrations | |
| last 500 lines of `errors.log` and the updates log, **redacted** | |
| a `README.txt` saying what is in the bundle and what was redacted | |

**Redaction pass**, applied to every text file in the bundle: token shapes
(`ghp_…`, `github_pat_…`, `VCS1.…`), URLs with credentials, the configured
heartbeat URL value, the database password, e-mail addresses, phone-number
digit runs, and quoted literals in error messages (a database error can quote
a patient's name). The README says the clinic may read the ZIP before sending
it.

Test (§14.2): plant a patient name, phone number, GitHub token, heartbeat URL
and license string in the database **and** in `errors.log`, generate a bundle,
and assert none of them appears anywhere in the ZIP. Control: the version and
self-check result do appear.

### 11.3 Restore administrator access (developer only)

- Developer → Support lists system-role users. Choosing one:
  1. generates a strong temporary password, **shown once** and never stored
     or logged;
  2. sets `must_change_password = true`;
  3. bumps `password_changed_at`, which ends that user's other sessions;
  4. clears that username's login lockout.
- It goes through the existing reset code path and password policy, not
  around them.
- It is audited in `developer_audit` **and** `log_change()` (the clinic sees
  that its admin was reset by its vendor, and when).
- This is not a backdoor: it needs a valid pass for this install, it is
  time-limited, and every use is recorded where the clinic can read it.

### 11.4 Full data export (clinic admins with `manage_maintenance`, and developers)

A ZIP built by a background job (the existing job runner and progress UI),
written to `<data dir>/exports/` and downloaded from the page. It runs in
read-only mode (A7).

| Part | Content |
|---|---|
| `data/<table>.csv` | **every table**, discovered from the live schema, as UTF-8 CSV with a BOM (so Excel opens Arabic correctly), header row, ISO dates, numbers at full precision (not money-formatted) |
| `attachments/` | every uploaded file, at its stored relative path |
| `schema.sql` | the migrations, in order |
| `manifest.json` | app version, export time, install ID, money setting, and per table the row count and SHA-256 of its file, plus the exclusions list |
| `README.md` | the format, how the tables relate, what is excluded and why, and that a backup (`.dump`) is the exact restorable copy |

**Excluded:** the `users.password_hash` column, `settings` rows in
`SECRET_SETTING_KEYS`, and nothing else unless recorded in the exclusions
registry with a reason. Secrets that live outside the database (license,
token) are never in it.

Test (§14.2): every table in the live schema is either exported or named in
the exclusions registry, so **adding a table without deciding fails the
test**. Row counts match. No password hash. No heartbeat URL. The attachment
is present. It works in a read-only session.

### 11.5 Vendor message (A13)

Settings keys: `vendor_message_text`, `vendor_message_level`,
`vendor_message_expires_at`. Rendered in `base.html` in a style distinct from
clinic content, labelled "Message from your vendor", escaped (never `|safe`),
hidden after expiry. Set, edit, enable, disable and clear from Developer;
every change audited.

---

## 12. Native PostgreSQL

### 12.1 Setup

- `VETCLINICSYSTEM_DB_MODE=native` (A11). `setup.py` then **never** calls
  `check_docker()`, `start_postgres()` or any `docker` command. It waits for
  `DATABASE_URL` to accept connections, with a timeout and a message that
  names the host and port.
- Under **both** modes, setup refuses a server older than 16
  (`server_version_num < 160000`) with a clear message.
- **Native mode also checks privileges:** the role must be able to create
  databases (`rolcreatedb` or superuser), because the self-verification
  restores into a throwaway database. Without it, setup warns and explains;
  the self-check reports it as its own finding rather than a generic
  verification failure.
- `DATABASE_URL` stays the only way the running app finds its database; the
  app does not know or care which mode it is in.

### 12.2 One PostgreSQL tool finder

A single function (e.g. `pgtools.find("pg_dump")`) used by backup, restore,
self-verify, the export and the health panel. No module calls
`shutil.which("pg_dump"/"pg_restore")` itself; a test enforces that, which
makes it a new seam rule.

- If `VETCLINICSYSTEM_PG_BIN_DIR` is set, look **only** there; a missing
  tool is an error, never a silent fallback.
- Otherwise look on `PATH`, then in the usual install locations:
  - **Windows:** `C:\Program Files\PostgreSQL\<n>\bin`, highest version
    first. The standard installer does not add this to PATH.
  - **macOS:** Homebrew `postgresql@<n>`, Postgres.app.
  - **Linux:** `/usr/lib/postgresql/<n>/bin`.
- Check each tool's major version (`--version`); it must be **at least** the
  server's major version, or refuse with a message saying so.
- **Native mode never falls back to Docker.** Docker mode keeps today's
  behaviour: local tools if compatible, otherwise `docker exec`.
- Error messages name the mode and the missing tool: never "install Docker
  Desktop" in native mode.

### 12.3 Privileges (documented, and the minimum)

A login role that **owns** the application database, plus **CREATEDB**.
Nothing else: no superuser, and no extensions are used (checked 2026-09-25).
Give the exact commands for macOS, Windows and Linux in the setup docs.

### 12.4 Starting at boot

The app does not install PostgreSQL or its service. Document each platform's
normal service: Homebrew services or Postgres.app on macOS, the service the
Windows installer registers (starts at boot, which also makes the
`autostart.py` boot task useful), and systemd on Linux. The health panel and
self-check report "database unreachable" clearly.

### 12.5 Backups and self-verification in native mode

Both run through `pgtools`, in either license state (§6.3), and with only the
§12.3 privileges.

---

## 13. Secrets — where each lives, and where it must never appear

| Secret | Lives in | Never in |
|---|---|---|
| Vendor signing key | the brother's machine, passphrase-encrypted | the repository, any install, any log |
| License string | `<data dir>/license/license.key` | database, backups, exports, support bundle, logs, audit detail |
| Developer Pass | pasted, verified, discarded (only `pass_id` is kept) | anywhere stored, logs, audit detail |
| GitHub token | `<data dir>` token file, owner-only permissions | database, `.env`, backups, exports, bundle, logs, errors, job results, audit detail |
| Heartbeat URL | `settings` (A6) | exports, bundle, logs, audit detail (already enforced) |
| Temporary admin password (§11.3) | shown once | stored anywhere, logs, audit |
| `SECRET_KEY`, DB password | `.env` | bundle, exports, logs |

**Test (§14.2):** one test sets a known value for every row above, drives the
actions that touch it, and scans the logs, `developer_audit`, `audit_log`,
job results, the support bundle and the data export for each value.

**Localization:** every new user-facing string goes through `_()`, including
banners, refusal pages, Developer pages and validator messages. Arabic you
write yourself goes into `docs/ARABIC_REVIEW.md` for the clinic to confirm;
never accept `pybabel update` fuzzy matches; recompile the catalogue
(`CLAUDE.md` §6). "License", "grace period", "read-only", "vendor" and
"Developer Pass" need a real translator's eye; flag them rather than guess.
Install IDs, license IDs and version numbers are identifiers and are never
digit-converted.

---

## 14. Tests

Run the whole suite in the isolated environment under **both** money
settings (`CLAUDE.md` §4–§5). Prove every guard: put the bug back, watch the
named test fail, restore the fix. Pair every guard with a control.

### 14.1 By area

| Area | Guard tests | Controls |
|---|---|---|
| Tokens | tampered payload, tampered signature, unknown `kid`, wrong `kind`, wrong install, pass longer than 12 hours, pass from the future, garbage input | valid license; valid pass; whitespace or line breaks inside a pasted key |
| Trust | no production entry point calls `trust_for_tests`; no trusted key read from env or DB; no `PRIVATE KEY` in tracked files | test keys work in tests |
| Developer access | system Admin with every permission refused on every `/developer/*`; a role naming `developer` has no effect; an expired pass is refused; a pass for another install is refused; rate limit | valid pass gets in; works with no clinic sign-in |
| License states | each state from §6.1 with a controlled clock; clock wound back; edited license file; missing file | renewal unlocks immediately |
| Read-only | `url_map` walk (§6.4) with a floor on endpoints checked; a session signed in *before* expiry keeps writing until it ends; the nightly backup runs in `read_only` | every allowlisted action works in read-only |
| Setup | refuses to finish without a valid key; refuses a server older than 16 | finishes with a valid key |
| Settings gate | `POST /settings` of a developer-gated key by the system Admin changes nothing | the Developer route changes it |
| Moved features | heartbeat pings with the URL set from Developer; updates still apply and roll back from Settings | — |
| Updater | 401, 404 and network failure each give the right message and never contain the token; the token is read per call (change it, next call uses it) | successful check with a mocked release |
| Audit | every action in §7.3 writes a row; `developer_audit` is not pruned and has no delete route | — |
| Admin recovery | refused without a pass; the temporary password is not logged | the recovered admin signs in and is forced to change it |
| Export | every live table exported or excluded; row counts; no hash; no secret | attachment present; works in read-only |
| Support bundle | planted secrets and PII absent (§11.2) | version and self-check result present |
| Secrets | the §13 scan | — |
| Native PostgreSQL | §14.3 | — |
| Browser tier | Developer login page, License page, the expiring/grace/read-only banners and the read-only refusal page: both languages, no console errors, no CSP violations, no inline handlers | — |

### 14.2 New seam rules

Add them to `docs/SEAM_RULES.md` §3 and to `tests/test_seam_rules.py`, each
discovering its subject live and asserting a floor on what it inspected:

1. Every writing endpoint is on the read-only allowlist or refused in
   read-only.
2. Every developer-gated settings key is refused by `POST /settings`.
3. Only `pgtools` locates `pg_dump` / `pg_restore`.
4. No secret from §13 appears in any output that §13 lists.

### 14.3 Native PostgreSQL without touching this machine's other servers

`CLAUDE.md` §4: this machine runs the two predecessor installs and an
unrelated Homebrew PostgreSQL. **Never** touch ports 5050/5051/5432/5433,
never quit or restart Docker Desktop, never run a Docker-wide command.

"Native mode" means the app does not manage the server. So test it against
the throwaway `vcs_test_*` container's port **as if it were native**:

- Run setup, backup, restore and self-verify with `DB_MODE=native` and a
  `PATH` from which `docker` has been removed (a shim directory holding only
  the PostgreSQL client tools). That proves no Docker call is made.
- An empty `PG_BIN_DIR`: the error names the missing tool and does not say
  "Docker".
- A fake `pg_dump` that reports version 15 against a 16 server: refused.
- A test role **without** CREATEDB, created in the throwaway container: the
  self-check reports the specific finding.
- These need PostgreSQL client tools on the machine. When they are absent the
  tests **skip loudly**, and the progress log must say whether they actually
  ran (`CLAUDE.md` §5.1: a skip can hide a dormant tier).

### 14.4 The test environment needs a license

Otherwise every test environment is read-only.
`scripts/isolated_test_env.sh up` must:

1. generate an **ephemeral** vendor key pair in the environment's temp
   directory; nothing is committed;
2. write a one-year license for the throwaway install into its data
   directory;
3. start the app through a **test launcher** that calls
   `trust_for_tests()` with that public key, then runs the normal app;
4. write a Developer Pass for the browser tests to read.

`tests/conftest.py` does the same in-process. The production launcher never
calls `trust_for_tests()` (§14.1, Trust).

---

## 15. Documentation

| File | What |
|---|---|
| `README.md` | install: the install ID, the license key and `--money-setting` at setup; native PostgreSQL (version, privileges, tool folder, service); where the license lives |
| `docs/DEVELOPER_GUIDE.md` (new, for the vendor) | the vendor tool; key custody and rotation; issuing a license; renewing; issuing a pass; installing a clinic step by step; the per-clinic GitHub token and revoking it; admin recovery; data export; support bundle contents; the vendor message |
| `docs/decisions/licensing.md` (or wherever the merge put decision records) | the token design, the trust rule (§4.3), the states, read-only at sign-in, and §2's honest limit |
| `docs/RELEASE_WORKFLOW.md` | private repository, tokens, key rotation in a release |
| `docs/SEAM_RULES.md` | §14.2's four rules |
| `CLAUDE.md` | decision table (D-1, D-9, D-12 overridden by L-1, L-3, L-2), the Developer area in the layout, the test-environment license (§14.4) |
| `docs/README.md` | move this plan from "Plans — not executed" to done when it is |
| `docs/ARABIC_REVIEW.md` | every new Arabic string |

Do not document the IQ/JO two-app architecture as current.

---

## 16. Build order

Each phase ends with the suite green under **both** money settings, every new
guard mutation-proven, and an entry in the progress log (§18).

| Phase | Work |
|---|---|
| **0. Re-map** | §3; confirm §0's preconditions |
| **1. Tokens** | `cryptography`; token format and verifier; trusted keys; the vendor tool; `install_id`; tests; test-environment license (§14.4) — do this early, or every later phase's tests run read-only |
| **2. Developer access** | Developer Pass sign-in; developer session; `developer_audit`; blueprint skeleton and layout; navigation entry |
| **3. License** | storage, states, banners, Settings → License and Developer → License, setup requires a key, read-only hook and allowlist |
| **4. Moves** | the `developer` settings gate; money setting, palette, heartbeat into Developer; the GitHub token file; the updater reads it per call; Updates section |
| **5. Tools** | health panel, support bundle, admin recovery, full data export, vendor message |
| **6. Native PostgreSQL** | the `DB_MODE` branch in setup, the version and privilege checks, `pgtools`, backup/restore/self-verify through it, the self-check findings |
| **7. Docs** | §15 |
| **8. Verification** | the full suite under both settings with the browser tier alive; a simulated clinic day that runs into expiry (warn, then grace, then read-only at the next sign-in, then renew); the §13 secret scan; a fresh `setup.py` install in native mode against a throwaway server; the owner's manual private-repository update test (§10) |

## 17. Done means

1. The suite is green under both money settings, with zero unexplained
   skips and the browser tier alive in both languages.
2. No supported path reaches the Developer area or bypasses the license:
   §7.2's tests are green and mutation-proven.
3. Every writing endpoint is covered by the read-only rule (seam rule 1).
4. No secret appears in any output (seam rule 4).
5. A fresh native-mode install works with `docker` absent from `PATH`.
6. The docs in §15 are updated, and `CLAUDE.md` records L-1, L-2 and L-3.

## 17a. End-of-work report

Give the owner:

1. a summary of what changed;
2. files and modules changed;
3. schema changes;
4. new environment variables (`VETCLINICSYSTEM_INSTALL_ID`,
   `VETCLINICSYSTEM_DB_MODE`, `VETCLINICSYSTEM_PG_BIN_DIR`) and the one
   removed (`GITHUB_TOKEN`);
5. PostgreSQL requirements;
6. the license design and where verification happens;
7. storage decisions for secrets;
8. tests run and their results under each money setting;
9. what needs manual setup, at least:
   - make the repository private;
   - generate the real vendor key and put its public key in
     `trusted_keys.py`;
   - create a GitHub token per clinic;
   - run the real private-repository update test.

---

## 18. Progress log

Newest last. Each entry: what landed, how it was verified, and the suite
result under each money setting.

*(empty)*
