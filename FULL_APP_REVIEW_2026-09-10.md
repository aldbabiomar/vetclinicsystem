# Full application review — IQ and JO — 2026-09-10

A whole-codebase review of both apps against industry practice: security,
coding logic, bugs, user QoL, dead code and dead files.

**Status: IN PROGRESS — 33 of 37 implemented, tested and mutation-proved, plus the two user-raised refund findings (R1, R2). Branch `review-fixes-2026-09-10` in both repos, local, not pushed. Suites: IQ 697 passed / JO 678 passed, zero failures, zero skips.**
Every finding below is agreed work; each carries a ready-to-paste prompt in its
*Fix prompt* block. No change has been made to either app as part of this
review — the two throwaway environments used for verification were torn down,
and the real install was not touched.

Work through them in the **Suggested order of work** at the end of this file,
not top to bottom: M2 must precede M3, and B1/B2 belong in one change.

---

## How this was produced, and what it is worth

Static read of both trees plus targeted live checks against throwaway
environments (`scripts/isolated_test_env.sh`, IQ on 5091 / JO on 5092), per
`CLAUDE.md` §5. Every finding below is marked **CONFIRMED** (reproduced or
directly observed) or **INFERRED** (read from code and configuration, not
executed). `CLAUDE.md` §0 is right that reading code is not running it, so the
distinction is kept honest rather than flattened.

**Baseline measured during this review, both environments, all three tiers
alive:**

| | IQ | JO |
|---|---|---|
| `VERSION` | 1.12.1 (test env reported 1.12.2) | 1.10.1 (test env reported 1.10.2) |
| Tests passed | **528** | **509** |
| Skipped | **0** | **0** |
| `test_*.py` files | 24 | 24 |
| Browser tier `--collect-only` | 13 collected | 13 collected |
| Route decorators | 148 | 147 |
| `app.py` | 7,066 lines | 6,921 lines |

Run at ~02:50, i.e. past the `test_scheduler_catchup.py` clock gates in
`CLAUDE.md` §7. Coverage was **not** re-measured — see M7 for why.

**Deliberate divergences were not reported as bugs.** The money models
(`COMPARISON.md` §1.1), phone formats, the ChamPet palette axis and
`--accent-alt` are all left alone per `COMPARISON.md` §18.

---

## Index

All 37 accepted 2026-09-10. **33 implemented and verified**; the remaining 4 are ✅ accepted, not yet started: S6, M3, M4, M8.

| ID | Severity | Apps | Finding | Status |
|---|---|---|---|---|
| **S1** | **High** | IQ (JO variant) | Settings admin gate is template-only; restore/update/rollback routes accept a non-admin role | **DONE** |
| **S2** | **High** | both | `/api/browse-folder` enumerates the entire host filesystem, unconfined | **DONE** |
| **S3** | Medium | both | `X-Forwarded-For` trusted unconditionally — audit-log IP is attacker-controlled | **DONE** |
| **S4** | Medium | JO | Login lockout never escalates against a sustained attack | **DONE** |
| **S5** | Low | both | Unauthenticated `/health` returns raw exception text | **DONE** |
| **S6** | Low | both | CSP is stuck on `'unsafe-inline'` because of inline handlers | ✅ |
| **S7** | Low | both | Password policy is length-only | **DONE** |
| **S8** | Low | JO | `.gitignore` does not exclude `uploads/` (patient attachments) | **DONE** |
| **B1** | **High** | both | Rollback picks the wrong release — string sort over `app_vX.Y.Z` | **DONE** |
| **B2** | Medium | both | `is_update_available()` compares tags with `!=`, not ordering | **DONE** |
| **B3** | Medium | both | `scheduler.py` swallows nine exception classes and logs nothing | **DONE** |
| **B4** | Medium | JO | Unpinned dependencies on a self-updating app | **DONE** |
| **B5** | Low | both | Search does not escape `%` / `_` in ILIKE patterns | **DONE** |
| **B6** | Low | both | Four audit/log tables are never pruned | **DONE** |
| **B7** | Low | both | Connection pool is not closed at interpreter exit (Python 3.14) | **DONE** |
| **B8** | Info | both | `?`→`%s` translation and `run_script()` splitting are not quote-aware | **DONE** |
| **U1** | Medium | both | 1-hour CSRF token vs 12-hour session: long-open forms fail and log you out | **DONE** |
| **U2** | Medium | both | An expired session on a POST silently discards everything typed | **DONE** |
| **U3** | Medium | both | ~233 of 236 `<label>`s are not associated with their input | **DONE** |
| **U4** | Low | both | 349 `<th>` elements, zero `scope=` | **DONE** |
| **U5** | Low | both | Login form has no `autocomplete` hints | **DONE** |
| **U6** | Low | JO | No `/favicon.ico` route | **DONE** |
| **D1** | **Medium** | both | An unfinished Desktop-shortcut feature: 6 of 15 functions dead (47 lines), and the dead half is also wrong | **DONE** |
| **D2** | Low | both | `heartbeat.py` imports `os` and never uses it | **DONE** |
| **D3** | Low | IQ | Two unreferenced favicon SVGs in `static/` | **DONE** |
| **D4** | Low | IQ | `.settings-strike` CSS rule is dead | **DONE** |
| **D5** | Low | IQ | `auth.discount_cap_for(db)` takes an unused parameter | **DONE** |
| **D6** | Low | IQ | `logic.followups_page()` carries an always-empty `params` list | **DONE** |
| **M1** | Medium | both | 84/89 code comments cite documents that do not ship in the repo | **DONE** |
| **M2** | Medium | both | 22/21 hardcoded URLs in templates instead of `url_for()` | **DONE** |
| **M3** | Medium | both | `app.py` is one 7,000-line module | ✅ |
| **M4** | Low | both | 11/10 functions over 100 lines | ✅ |
| **M5** | Low | JO | Clean Up validation duplicated inline in four routes | **DONE** |
| **M6** | Low | JO | `auth.py` comment claims features JO actually has | **DONE** |
| **M7** | Low | tooling | Documented coverage command cannot run in the sanctioned environment | **DONE** |
| **M8** | Low | both | ~490 inline `style=` attributes | ✅ |
| **M9** | Trivial | IQ | Zero-width space inside a `backup.py` comment | **DONE** |

**What was checked and found clean** — worth recording so it is not re-audited:
no SQL injection (every dynamic fragment is literal; `sort` is whitelisted);
no `|safe`, `Markup()` or disabled autoescaping anywhere; no `shell=True`, no
`eval`/`exec`/`pickle`; no bare `except:`; no mutable default arguments; no
`csrf.exempt`; attachment upload/serve is traversal-safe (DB lookup plus
`send_from_directory`); the restore path *is* confined to app-created backups
(`resolve_restorable_backup`); every one of the 148/147 routes is reachable
from the UI; every template is rendered; CSS has exactly one dead rule.

---

# SECURITY

## S1 — Settings' admin-only gate exists only in the template — **CONFIRMED**

**Severity: High · IQ (JO has a related, different problem)**

`templates/settings.html` line 110 opens `{% if is_system_admin %}` and closes
it at line 376. Everything inside — **Backups & Restore**, **Restore Now**,
**Updates**, **Startup & Shutdown** — is hidden from anyone who is not in the
locked system Admin role.

Every route behind that UI is guarded only by
`@auth.permission_required("manage_settings")`.

So a custom role holding `manage_settings` sees a Settings page with those
sections removed, and can still drive all of them by request.

**Evidence.** Against the live IQ environment I created a custom role holding
`manage_settings` and nothing else, put a user in it, and logged in as them:

```
[IQ] GET /settings -> 200
[IQ]   UI contains Backups & Restore heading   : False
[IQ]   UI contains backup-now form             : False
[IQ]   UI contains restore-now form action     : False
[IQ]   UI contains updates polling JS          : False
[IQ]   UI contains autostart form              : False

[IQ] POST /settings/restore-now      -> HTTP 302   (not 403)
[IQ] GET  /settings/updates/status   -> HTTP 200   (not 403)
[IQ] GET  /settings/updates/check    -> HTTP 200   (not 403)
[IQ] POST /settings/updates/rollback -> HTTP 400   (not 403)
[IQ] GET  /api/browse-folder         -> HTTP 200   (not 403)
```

`POST /settings/backup-now` with a valid CSRF token returned **400 with the
route's own business error** — `{"error":"No backup folder configured yet — set
one above, then Save Settings, before backing up."}` — which is the decisive
part: the request was fully authorized and the route executed. It declined
only because the throwaway environment has no backup folder set.

**JO's variant.** JO has no `auth.is_system_admin()` at all and no template
gate, so those controls are simply visible to any `manage_settings` holder. JO
is at least self-consistent; IQ presents a restriction it does not enforce.

**Why it matters.** `manage_settings` currently means both "rename the clinic"
and "restore the database over the top of the live one, apply or roll back an
app version, and browse the server's disk." An admin creating a "Practice
Manager" role and ticking Settings has no reason to expect the second half —
IQ's own UI actively tells them it is not included.

**Fix prompt**

> In **both** apps, split the destructive half of Settings away from
> `manage_settings` and enforce it server-side.
>
> 1. Add a new permission key to `auth.PERMISSIONS` — `manage_backup_restore`,
>    category `Admin` — and add it to `ADMIN_ONLY_TODAY` so Vet/Reception do
>    not seed with it.
>
>    **⚠ Do not stop there — on an existing install this step alone locks
>    everyone out, permanently.** `seed_default_roles_and_permissions()`
>    upserts the new key into the `permissions` table, but its role loop does
>    `existing = SELECT id FROM roles WHERE name=?` → `if existing: continue`,
>    so an already-created Admin role is **skipped** and granted nothing. And
>    `admin_role_edit()` opens with
>    `if role["is_system"]: flash("The Admin role can't be edited.")`, so the
>    grant cannot be made from the UI either. Net effect on every existing
>    clinic: nobody — including the system Admin — can back up, restore,
>    update, roll back or browse folders, with no in-app way to recover.
>
>    Fix it generally rather than for this one key, since the next permission
>    added will hit the same wall. In `seed_default_roles_and_permissions()`,
>    immediately **after** the `permissions` upsert loop and **before** the
>    defaults loop, re-assert the system role's full grant on every launch:
>
>    ```python
>    # The Admin role is is_system and cannot be edited from the UI, so a
>    # permission added to PERMISSIONS after an install already exists would
>    # otherwise be held by nobody, with no way to grant it. Re-assert it.
>    db.execute(
>        "INSERT INTO role_permissions (role_id, permission_id) "
>        "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p "
>        "WHERE r.is_system = true ON CONFLICT DO NOTHING"
>    )
>    ```
>
>    It must run after the upsert because `role_permissions.permission_id`
>    references `permissions(id)`. Do **not** put it in
>    `INCREMENTAL_SCHEMA_STATEMENTS` — those run before `auth` seeding (see
>    `scripts/isolated_test_env.sh up`), so the row it needs does not exist yet
>    and the foreign key would fail.
>
>    Test it as an upgrade, not a fresh install: seed a database at the current
>    schema, *then* add the key and re-run seeding, and assert the Admin role
>    holds it and a restore route answers for an Admin. A fresh-install test
>    passes either way and proves nothing.
> 2. Re-gate these routes on it (in addition to, not instead of,
>    `manage_settings` where the route also reads ordinary settings):
>    `settings_backup_now`, `settings_restore_now`, `settings_job_status`,
>    `settings_autostart`, `settings_updates_status`, `settings_updates_check`,
>    `settings_updates_apply`, `settings_updates_rollback`,
>    `api_browse_folder`, `api_browse_folder_new`.
> 3. In IQ, change `templates/settings.html`'s `{% if is_system_admin %}` at
>    line 110 to `{% if has_permission('manage_backup_restore') %}` so the UI
>    gate and the server gate are the same condition. Add the same gate to
>    JO's `settings.html` around its equivalent block.
> 4. Port `auth.is_system_admin()` into JO, or drop IQ's now-unused copy —
>    do not leave one app with a helper the other lacks.
>
> Per `CLAUDE.md` §7.3, pair each new guard test with a control: for every
> route above, assert a role **with** `manage_backup_restore` still succeeds
> and a role with only `manage_settings` gets 403. Prove the tests bite by
> removing one decorator and watching exactly those tests fail. Verify live in
> both isolated environments with a real custom role, the same way this
> finding was verified.

---

## S2 — `/api/browse-folder` enumerates the whole host filesystem — **CONFIRMED**

**Severity: High · both apps**

`api_browse_folder()` takes the caller's `?path=` and does:

```python
path = os.path.abspath(requested)
```

There is no confinement to the backup directory, the data directory, the home
directory, or anything else. Any absolute path that exists is listed.

**Evidence.** As the non-admin custom role from S1, against live IQ:

```
  /etc            -> HTTP 200  19 folders: ['apache2', 'asl', 'cups', 'manpaths.d', ...]
  /               -> HTTP 200  12 folders: ['Applications', 'bin', 'cores', 'dev', ...]
  /Users          -> HTTP 200   2 folders: ['omaraldbabi', 'Shared']
  /var/log        -> HTTP 200  15 folders: ['apache2', 'asl', ...]
  /Applications   -> HTTP 200  20 folders: ['Affinity.app', 'Claude.app', 'Docker.app', ...]
  /etc?ext=.conf  -> files: ['asl.conf', 'autofs.conf', 'nfs.conf', 'ntp.conf', 'pf.conf', ...]
```

**Scope, stated fairly.** This lists *names*, not contents — it cannot read a
file. Dotfiles are skipped and symlinked directories are not followed. It still
discloses the operating-system account name, installed applications, and
arbitrary directory structure to any logged-in user with `manage_settings`, and
it compounds S1 because the UI presents that role as not-an-admin.

The picker legitimately has to browse the *server's* disk (the docstring
explains why, and it is correct). The fix is a root, not removal.

**Fix prompt**

> In **both** apps, confine `api_browse_folder()` and
> `api_browse_folder_new()` to an allowlist of roots instead of accepting any
> absolute path.
>
> Define the permitted roots as: the user's home directory, the configured
> `backup_dir`, and the data directory (`VETCLINICSYSTEM{IQ,JO}_DATA_DIR`) when
> set. Resolve the request with `os.path.realpath()` and reject anything whose
> resolved path is not the root itself or beneath it — compare with
> `os.path.commonpath()`, not `str.startswith()`, so `/Users/omar-evil` cannot
> pass a `/Users/omar` check. Return the existing 400 shape with a clear
> message naming which folders can be browsed. Apply the identical check to
> the new-folder endpoint so a folder cannot be created outside a root either.
>
> Test both directions per `CLAUDE.md` §7.3: a control asserting the backup
> folder and home still list correctly, and guards asserting `/etc`, `/`, and a
> `..`-escaping path under an allowed root are all refused. Confirm the guard
> fails before the fix and passes after — the bug is present right now, so run
> the test first and watch it fail, the way `COMPARISON.md` §47 did.

---

## S3 — `X-Forwarded-For` is trusted unconditionally in the login audit log — **CONFIRMED (by inspection)**

**Severity: Medium · both apps**

`auth.py` (IQ line 272, JO line 266):

```python
ip = request.headers.get("X-Forwarded-For", request.remote_addr)
```

This runs whether or not a proxy is in front. The default deployment is plain
HTTP on the clinic LAN with `BEHIND_TLS_PROXY` unset, so there is no proxy and
no header — which means any client that *sends* one controls the value written
to `login_log.ip`, the column Admin → Logins and Changes displays.

`app.py` already does this correctly: when `BEHIND_TLS_PROXY=1` it installs
`ProxyFix`, which is what makes `request.remote_addr` trustworthy behind a
proxy. Reading the raw header is therefore both unnecessary when a proxy exists
and unsafe when one does not.

The login rate limiter is unaffected — it uses `request.remote_addr` directly.

**Fix prompt**

> In **both** apps, change `auth.log_login()` to record `request.remote_addr`
> only, and delete the `X-Forwarded-For` lookup. `ProxyFix` already rewrites
> `remote_addr` from the header when `BEHIND_TLS_PROXY=1`, so the proxied case
> keeps working and the unproxied case stops being forgeable. Add a comment
> saying exactly that, so nobody re-adds the header read.
>
> Add a test that posts a failed login with a spoofed
> `X-Forwarded-For: 10.9.9.9` header and asserts the stored `login_log.ip` is
> the test client's address, not the header value. Pair it with a control
> asserting the IP is still recorded correctly with no header present.

---

## S4 — JO's login lockout never escalates against a sustained attack — **CONFIRMED**

**Severity: Medium · JO (IQ has a milder, opposite weakness)**

`login_lock_status()` has two materially different implementations. This is not
in `COMPARISON.md` §18's list of deliberate divergences, and it is the same
class of problem as §40.6 (`selfcheck.py` claiming a parity it never had).

- **IQ** counts every failure since the last success and escalates on each
  full block of 5: `episode = n // 5`.
- **JO** groups failures into bursts, starting a new burst only when the gap
  since the previous failure exceeds 15 minutes, and escalates per *burst*.

**Evidence.** Both real modules, identical synthetic inputs, via a stub DB:

```
A. 5 rapid failures            IQ 15 min   JO 15 min    AGREE
B. 10 rapid failures           IQ 30 min   JO 14 min    *** DISAGREE ***
C. 15 rapid failures           IQ 60 min   JO 13 min    *** DISAGREE ***
D. 3 bursts of 5, 30 min apart IQ 59 min   JO 59 min    AGREE
E. 4 stray over 12h, then 5    IQ 14 min   JO 15 min    *** DISAGREE ***
```

**Why it matters.** JO's escalation only triggers on a *pause* longer than
15 minutes. An attacker who simply never pauses stays in one burst forever and
never escalates past the base 15 minutes — the exact behaviour JO's own comment
says the escalation was introduced to prevent. Case C is the point: fifteen
straight wrong guesses buy IQ an hour and JO thirteen minutes.

Scenario E shows IQ's own smaller weakness in the other direction: stale
failures shift its anchor backwards, so a few paced guesses can shorten the
lock slightly.

**Fix prompt**

> Reconcile `login_lock_status()` across both apps onto one implementation, and
> record the decision in `COMPARISON.md` as a dated note.
>
> Recommended shape, which fixes both weaknesses: keep JO's burst grouping (it
> correctly ignores stray failures that never crossed the threshold), but count
> an additional escalation step for **every further block of
> `LOCKOUT_THRESHOLD` failures inside the current burst**, not only for
> separate bursts. So 5 failures → 15 min, 10 → 30, 15 → 60, whether or not the
> attacker paused. Anchor `unlock_at` on the failure that crossed the current
> threshold, as JO already does, so continuing to guess after a lock is armed
> cannot extend it further within the same block.
>
> Port the result to both apps, re-derived against each app's own code rather
> than copy-pasted. Add the five scenarios above as table-driven tests in
> **both** suites — A and D as controls (behaviour must not change), B, C and E
> as the guards. Confirm the guards fail against each app's current
> implementation before the fix lands; note that a naively written test will
> pass against both versions, which is precisely the trap `TRANSITION_NOTES`
> §4.3 called out for `consecutive_fail_days()`.

---

## S5 — Unauthenticated `/health` returns raw exception text — **PARTIALLY CONFIRMED**

**Severity: Low · both apps**

`/health` is in `OPEN_ENDPOINTS` — no login required, by design, because
`updater.py` probes it before promoting a release. On failure it returns:

```python
return {"status": "error", "detail": str(e)}, 503
```

`str(e)` is whatever the exception says, unbounded.

**What was reproduced, and what was not.** I stopped the throwaway JO Postgres
container and called `/health`; the response was benign:

```
{"detail":"terminating connection due to administrator command","status":"error"}
```

The pool returned that same cached message on every subsequent attempt, so I
could not drive the *fresh-connect* failure path through `/health` in this
environment. I confirmed separately what that path produces, using the same
psycopg build the app runs:

```
[port closed]   'connection failed: connection to server at "127.0.0.1", port 55999 failed: could not receive data from server: Connection refused'
[bad password]  'connection failed: connection to server at "127.0.0.1", port 55492 failed: FATAL:  password authentication failed for user "postgres"'
```

So: the unauthenticated disclosure of database host, port and username is
reachable in principle — the app starting before Postgres is the obvious way —
but I did not observe the two halves in one response. Treat it as a real gap in
output discipline rather than a demonstrated leak.

Worth noting the pool recovered cleanly once the database came back; that part
behaved correctly.

**Fix prompt**

> In **both** apps, stop returning raw exception text from `/health`. Keep the
> 503 and the `{"status": "error"}` shape, and replace `detail` with a fixed
> string plus the crash-reference id the app already generates for the error
> log (see `error_logger` in `app.py`), so an operator can still correlate it.
> Log the full `str(e)` and traceback to `logs/errors.log`, where it is already
> access-controlled.
>
> Check `updater.py`'s `_probe_health()` first: if it reads `detail` to decide
> whether a release is healthy, keep whatever it needs and redact only the
> connection string. Add a test asserting a failing `/health` response contains
> no `port`, no `user`, and no `password` substring.

---

## S6 — CSP cannot be tightened while inline handlers remain — **CONFIRMED (measured)**

**Severity: Low · both apps**

`add_security_headers()` ships
`script-src 'self' 'unsafe-inline'` and the comment is candid that a stricter
nonce policy was skipped because "every template here is inline-script-heavy."
Measured: **88 (IQ) / 96 (JO)** `onclick=` attributes across the templates,
plus inline `<script>` blocks in most pages (9 in `base.html`, 4 in
`settings.html`).

`'unsafe-inline'` is what makes the script-src directive close to decorative.
The rest of the policy (`default-src 'self'`, `connect-src 'self'`,
`frame-ancestors 'none'`) is doing real work and should stay.

**Fix prompt**

> In **both** apps, remove `'unsafe-inline'` from `script-src` by moving inline
> handlers off the markup. Do it incrementally, one template per change, so a
> regression is easy to bisect:
>
> 1. Replace each `onclick="fn(...)"` with a `data-*` attribute plus a
>    delegated listener in the page's existing `<script>` block.
> 2. Once a page has no inline attributes left, move its `<script>` body into a
>    file under `static/` and load it with `url_for('static', ...)`.
> 3. Only when every template is converted, drop `'unsafe-inline'` from the
>    header.
>
> Add a static guard test that fails if any template gains an `on*=` attribute
> or an inline `<script>` with a body — modelled on the `static/` guard from
> `COMPARISON.md` §47, and run against the current tree first so its false
> positives are visible before it is trusted. Do not start step 3 until the
> browser tier passes on both apps.

---

## S7 — Password policy is length-only — **CONFIRMED (by inspection)**

**Severity: Low · both apps**

`len(new) < 8` is the entire rule, at all three sites (`change_password`,
`admin_user_new`, `admin_user_reset_password`). `password123` and the user's
own username are both accepted.

The surrounding controls are genuinely good — per-username escalating lockout,
per-IP rate limiting, a timing-equalised login, session invalidation on
password change — so this is the weakest link rather than a crisis.

**Fix prompt**

> In **both** apps, add two proportionate checks alongside the existing
> 8-character minimum, in one shared helper used by all three password-setting
> sites: reject a password equal to (or containing) the username
> case-insensitively, and reject a small embedded list of the most common
> passwords. No new dependency, no complexity-class rules, no expiry — those
> cost usability at a front desk and buy little. Surface the reason in the
> existing flash message. Add tests for both rejections plus a control that an
> ordinary 8-character password still succeeds.

---

## S8 — JO's `.gitignore` does not exclude `uploads/` — **CONFIRMED**

**Severity: Low (unrealised) · JO**

IQ's `.gitignore` covers `logs/`, `uploads/`, `*.log`, `.DS_Store`,
`Thumbs.db`, the releases/data directories, `dev_seed/`, `.coverage`,
`last_restore.json` and `.pytest_cache/`.

JO's is nine lines and covers `__pycache__/`, `*.pyc`, `.env`,
`.pytest_cache/`, `logs/`, `.coverage`, `last_restore.json`, `venv/`, `.venv/`.

`uploads/` is missing — and JO's `attachments.py` puts `UPLOAD_ROOT` inside the
repo directory whenever `VETCLINICSYSTEMJO_DATA_DIR` is unset, which is the
case for a dev clone. Those files are patient X-rays, bloodwork and test
results.

**Nothing has leaked.** `git ls-files uploads` in JO returns exactly one entry,
`uploads/.gitkeep`, and the working tree is clean. This is a missing guard, not
an incident. But it is the guard that would stop `git add -A` in a dev clone
from committing clinical attachments to a GitHub repo, and IQ has it.

This is the same shape as `COMPARISON.md` §47: an unreferenced file under a
served or tracked directory has no symptom at all until it does.

**Fix prompt**

> Bring JO's `.gitignore` up to IQ's coverage. Add at minimum `uploads/`,
> `*.log`, `.DS_Store`, `Thumbs.db`, and the `/vetclinicsystemjo-data/` and
> `/vetclinicsystemjo-releases/` guards, keeping IQ's explanatory comments
> adapted to JO's paths. Keep `uploads/.gitkeep` tracked with a
> `!uploads/.gitkeep` negation so the directory still exists on clone.
>
> Then add a test to **both** suites that fails if `git ls-files` reports any
> tracked file under `uploads/` other than `.gitkeep`. Verify it by staging a
> throwaway file under `uploads/`, watching the test fail, and unstaging.

---

# BUGS AND CODING LOGIC

## B1 — Rollback picks the wrong release — **CONFIRMED**

**Severity: High · both apps**

`updater.list_releases()`:

```python
return sorted(names, reverse=True)
```

with the docstring "`app_vX.Y.Z` sorts correctly for this app's strict-semver
tags." That is false as soon as a version component reaches two digits, because
this is a string sort: `"app_v1.9.0" > "app_v1.12.1"`.

Both apps are past that point. IQ is on 1.12.1; JO is on 1.10.1.

`_rollback_to_previous_locked()` and `settings_updates_rollback()` both take
`candidates[0]` from that order.

**Evidence.** Running the real `list_releases()` against temporary release
directories:

```
[IQ]  on disk (chronological): ['app_v1.9.0', 'app_v1.11.0', 'app_v1.12.1']
      active release          : app_v1.12.1
      list_releases() order   : ['app_v1.9.0', 'app_v1.12.1', 'app_v1.11.0']
      rollback candidates[0]  : app_v1.9.0
      CORRECT rollback target : app_v1.11.0        *** WRONG ROLLBACK TARGET ***

[JO]  on disk (chronological): ['app_v1.9.0', 'app_v1.10.0', 'app_v1.10.1']
      active release          : app_v1.10.1
      list_releases() order   : ['app_v1.9.0', 'app_v1.10.1', 'app_v1.10.0']
      rollback candidates[0]  : app_v1.9.0
      CORRECT rollback target : app_v1.10.0        *** WRONG ROLLBACK TARGET ***
```

**When it bites, stated fairly.** `_prune_old_releases(keep={new, old})` keeps
two folders, and with exactly two there is one candidate and the answer is right
regardless of order. The bug needs three or more release folders present. That
happens when a prune partially fails — `shutil.rmtree(..., ignore_errors=True)`
swallows it silently — when an operator copies a folder in, or after a
`--enable-updates` migration leaves an extra behind.

The consequence is not cosmetic: Rollback is the control an admin reaches for
when a new version misbehaves, and it would move the clinic back three minor
versions, across schema migrations, while telling them it is doing something
else. `updater.py` is the module `TRANSITION_NOTES` §4.6 records as having no
unit coverage.

I checked `_prune_old_releases()` separately and it is **not** affected — it is
driven by the `keep` set rather than by position, and reaches the right outcome
on 3- and 4-release inputs.

**Checked against the real install**, read-only:
`~/Downloads/vetclinicsystemiq-releases/` currently holds exactly two folders,
`app_v1.11.1` and `app_v1.12.2`, with the pointer on `app_v1.12.2`. With two,
there is one candidate and Rollback picks correctly today. So this is a latent
bug on that machine, not an active one — which is the honest severity: High
because of what it does when it fires and because Rollback is a recovery
control, not because it is firing now.

**Fix prompt**

> In **both** apps, make `updater.list_releases()` order by parsed version, not
> by string. Add a small key function that turns `app_vX.Y.Z` into a
> `(major, minor, patch)` int tuple and sorts on that, `reverse=True`. Make it
> tolerant of a folder whose name does not parse — sort those last rather than
> raising, so one stray directory cannot break Rollback entirely. Fix the
> docstring, which currently asserts the opposite of the truth.
>
> While in there, review `_prune_old_releases()` against the new ordering to
> confirm it still keeps the right two (it is driven by `keep`, so it should be
> unaffected — verify rather than assume).
>
> `updater.py` has no unit tests at all. Add a `test_updater_releases.py` to
> both suites covering: the three-release case above asserting the correct
> rollback target; a two-release control asserting today's behaviour is
> unchanged; a mixed-width set like `1.9.0 / 1.10.0 / 1.12.1` asserting full
> ordering; and an unparseable folder name asserting no exception. Confirm the
> new tests fail against the current implementation before the fix.

---

## B2 — `is_update_available()` compares tags with `!=` — **CONFIRMED (by inspection)**

**Severity: Medium · both apps**

```python
return latest["tag_name"].lstrip("v") != current_version(), latest
```

Any difference counts as "an update is available," including a lower version.
If a release is deleted and GitHub's `/releases/latest` then resolves to an
older tag, or a tag is republished, the clinic is offered a downgrade described
as an update — and `apply_update()` will install it.

Same root cause as B1: the module treats versions as strings.

**Fix prompt**

> In **both** apps, change `is_update_available()` to report an update only
> when the remote tag is strictly *newer* than `current_version()`, reusing the
> version-tuple parser added for B1 so there is one comparison function in the
> module rather than two. Handle an unparseable remote tag by reporting "no
> update" and logging it, rather than by installing something unknown.
>
> Tests in both suites: newer → available; identical → not available; older →
> not available (this is the guard); unparseable → not available and logged.

---

## B3 — `scheduler.py` swallows everything and logs nothing — **CONFIRMED (measured)**

**Severity: Medium · both apps**

Nine `except Exception: pass` handlers, at lines 144, 167, 197, 199, 205, 233,
239, 354 and 366 — identical in both apps. `grep` for `logging`, `logger` or
`error_logger` in `scheduler.py` returns **nothing** in either app. `app.py`
builds a rotating `error_logger` writing to `logs/errors.log`; no other module
uses it.

This is the component whose entire recorded bug history is silent failure:
§32 (missed jobs silently skipped), §33 (frozen monotonic clock), §37 (tick and
cron racing), §39 (a vanished backup destination reported healthy), §41 (a
failing backup erasing the evidence its folder was real). The module's own
docstring opens with "THE THEME, learned the hard way four times now."

Concretely: if `_parse_hour_minute()` raises on a malformed `backup_time`
setting, or `import backup` fails, or `run_backup()` raises before it can write
its `backup_log` row, `_run_backup_if_due()` returns `False` and **no record of
the reason exists anywhere**. Detection then falls back to staleness, which is
slower and less specific than the error already in hand.

Swallowing is correct here — a scheduled job must not take the process down.
Swallowing *silently* is the defect.

**Fix prompt**

> In **both** apps, make `scheduler.py` observable without changing its
> swallow-everything behaviour.
>
> Import the existing error logger rather than creating a second one — expose
> `app.error_logger` through a small accessor if a direct import would be
> circular, or move the logger construction into its own module both can
> import. Then give every one of the nine handlers a
> `logger.error("<job name> failed\n" + traceback.format_exc())` before its
> `pass`/`return False`. Keep the control flow exactly as it is.
>
> The three inner `close_db()` handlers can log at warning level; the six that
> wrap actual job bodies should log at error.
>
> Test it: monkeypatch `logic.get_setting` to raise inside
> `_run_backup_if_due()`, assert the function still returns `False` (control —
> the swallow must survive) **and** that a line naming the job reached the log
> (guard). Confirm the guard fails before the logging is added.

---

## B4 — JO's dependencies are unpinned on a self-updating app — **CONFIRMED**

**Severity: Medium · JO**

| IQ `requirements.txt` | JO `requirements.txt` |
|---|---|
| `Flask==3.1.3` | `Flask>=3.0` |
| `reportlab==5.0.1` | `reportlab>=4.0` |
| `Pillow==12.3.0` | `Pillow>=10.0` |
| `psycopg[binary]==3.3.4` | `psycopg[binary]>=3.1` |
| `psycopg-pool==3.3.1` | `psycopg-pool>=3.2` |
| `waitress==3.0.2` | `waitress>=3.0` |
| `APScheduler==3.11.3` | `APScheduler>=3.10` |
| `python-dotenv==1.2.3` | `python-dotenv>=1.0` |
| `Flask-WTF==1.3.0` | `Flask-WTF>=1.2` |
| `requests==2.34.2` | `requests>=2.31` |

`updater.py` builds a **fresh venv per release** and runs
`pip install -q -r requirements.txt` into it, then gates promotion on
`python -c "import app"` and a `/health` probe. Under floors, that resolves to
whatever is newest on PyPI *at update time*. A JO clinic applying an in-app
update can silently move several major versions of Flask, psycopg or reportlab,
unattended, with no relationship to what was tested.

The health probe catches an import error or a dead app. It does not catch a
behavioural change — a `reportlab` major that renders PDFs differently, or a
`psycopg` change in type adaptation, which for JO is `Decimal`-sensitive.

IQ has already made this choice correctly. This is a straightforward parity
gap, not a design difference.

**Fix prompt**

> Pin JO's `requirements.txt` to exact `==` versions, matching IQ's convention.
> Pin to the versions JO is actually running and tested against today — read
> them from a fresh `isolated_test_env.sh up jo` venv with
> `/tmp/vz_jo_test_venv/bin/pip freeze`, do not copy IQ's numbers across, since
> the two apps are not required to be on the same releases.
>
> After pinning, tear the environment down, bring it back up so the venv is
> rebuilt from the pinned file, and run the full JO suite — all three tiers,
> zero skips — to prove the pins resolve and nothing regressed. Record the
> before/after in `COMPARISON.md` as a dated note, since this changes how the
> two apps compare.

---

## B5 — Search does not escape `%` and `_` in ILIKE patterns — **CONFIRMED (by inspection)**

**Severity: Low · both apps**

Ten sites per app build `f"%{search}%"` and pass it to `ILIKE ?`. No `ESCAPE`
clause appears anywhere in either app (`grep -c ESCAPE` → 0/0).

The queries are parameterised, so this is not injection. It is a correctness
bug: a user typing `%` matches every row, and `_` matches any single character.
Searching for a name or item containing either returns the wrong set with no
indication anything went wrong.

**Fix prompt**

> In **both** apps, add one shared helper — `logic.like_pattern(term)` — that
> escapes `\`, `%` and `_` in the user's term and returns `f"%{escaped}%"`, and
> append `ESCAPE '\'` to every `ILIKE ?` clause that consumes it. Route all ten
> call sites in each app through it (`app.py` and `logic.py`; the microchip
> search in `logic.py` needs it on both its patterns).
>
> Tests, per app: seed an owner named `A_B` and one named `AXB`, search `A_B`,
> assert only the first comes back (guard); search `A` and assert both come
> back (control, so the escaping has not broken ordinary substring search).

---

## B6 — Four audit and log tables are never pruned — **CONFIRMED (measured)**

**Severity: Low · both apps**

`grep "DELETE FROM <table>"` across both trees:

| Table | Pruned? |
|---|---|
| `audit_log` | never |
| `login_log` | never |
| `backup_log` | never |
| `restore_log` | never |
| `self_check_log` | yes (`selfcheck.py`) |

`audit_log` grows fastest — `log_change()` writes **one row per changed field**
on every update, plus one per create and delete. Over a clinic's years of real
use it becomes the largest table in the database, and it is inside every
`pg_dump`. That inflates backup duration, backup size and restore time
indefinitely, which interacts with two things already recorded as known: the
shutdown backup that "may not finish" on a large database (§18) and the restore
drill's runtime.

There is no operational reason to keep every field-level change forever, and
`backup_retention` already establishes the pattern of a Settings-configurable
retention window.

**Fix prompt**

> In **both** apps, add retention for the four unbounded log tables.
>
> Add a Settings field `log_retention_days`, defaulting to 730 (two years) and
> clamped 90–3650 the same way `backup_retention` is clamped 1–3650. Add a
> scheduled prune that deletes rows older than that from `audit_log`,
> `login_log`, `backup_log` and `restore_log`, run from the existing daily job
> in `scheduler.py` — and, given B3, make sure it logs its own failures.
>
> Two things to get right. First, `auth.login_lock_status()` reads `login_log`
> over `LOCKOUT_LOOKBACK_HOURS`; the retention floor of 90 days is far above
> that, but assert it in a test so a future change to either constant cannot
> quietly disarm the lockout. Second, prune in bounded batches rather than one
> statement, so a first run against years of history does not hold a long
> transaction.
>
> Tests: rows older than the window are removed; rows inside it survive
> (control); the lockout still works with the prune enabled; retention of 0 or
> negative is rejected by the clamp — this is the `backup_retention` = 0
> failure mode from `TRANSITION_NOTES` §2.1, and it must not be reintroduced.

---

## B7 — The connection pool is not closed at interpreter exit — **CONFIRMED**

**Severity: Low · both apps**

Every test run in both apps ends with:

```
Exception ignored while calling deallocator <function ConnectionPool.__del__ ...>:
  ...
PythonFinalizationError: cannot join thread at interpreter shutdown
```

`dbmod.close_pool()` exists and is called from `app.py`'s shutdown paths, but
nothing registers it with `atexit`, and the test harness never calls it. On
Python 3.14 the pool's `__del__` then tries to join its worker threads during
finalisation, which is no longer permitted.

Harmless today — it happens after the exit code is decided, and the app's own
signal handlers do call `close_pool()`. It is still noise on every run, and it
is the kind of noise that hides a real message later.

**Fix prompt**

> In **both** apps, register `close_pool()` with `atexit` inside `db.py`'s
> `init_pool()`, so any process that creates a pool tears it down before
> finalisation regardless of how it exits. Make `close_pool()` idempotent (it
> nearly is — confirm the `_pool = None` reset covers a double call) so the
> existing explicit calls in `app.py` stay correct.
>
> Also add a `conftest.py` session-scoped teardown that calls it, so the test
> process is clean too. Verify by running the full suite in both apps and
> confirming the traceback no longer appears.

---

## B8 — Placeholder translation and script splitting are not quote-aware — **INFERRED, latent**

**Severity: Informational · both apps**

Two known-fragile helpers in `db.py`, both already documented in their own
comments, both safe today, both silent when they break:

1. `_PLACEHOLDER_RE = re.compile(r"\?")` replaces **every** `?` with `%s`,
   including one inside a SQL string literal. The comment says this is "safe
   today only because the app never puts a literal `?` inside any SQL string
   literal (verified)." I re-verified: still true. The only `?` in either
   schema is inside a `--` comment (IQ line 733 / JO line 815), and
   `run_script()` strips comments before translation, so it never reaches the
   regex.
2. `run_script()` splits on `;` after stripping `--` comments. A semicolon
   inside a string literal, or a `$$`-quoted function body, would be split
   mid-statement. Neither schema currently contains either (`grep '\$\$'` → 0
   in both).

Neither is a bug now. Both are trip-wires with no guard, in the code path that
creates the database.

**Fix prompt**

> In **both** apps, convert these two comments into tests rather than rewriting
> the helpers — the helpers are fine for the SQL this app actually writes, and
> making them fully quote-aware is more risk than the problem warrants.
>
> Add to the pure tier: a test that fails if any `.py` or `.sql` file in the
> repo contains a `?` inside a single-quoted SQL string literal, and a test
> that fails if `schema_postgres.sql` contains `$$` or a semicolon inside a
> string literal. Run both against the current tree first and confirm they pass
> for the right reason — then deliberately add a violating line, watch each
> fail, and remove it. Reference `db.py`'s existing comments from the test so
> the two stay connected.

---

# USER QUALITY OF LIFE

## U1 — A form open longer than an hour fails and logs you out — **CONFIRMED (by configuration)**

**Severity: Medium · both apps**

`WTF_CSRF_TIME_LIMIT` is never set in either app. Confirmed against the
installed Flask-WTF 1.3.0: `app.config.setdefault("WTF_CSRF_TIME_LIMIT", 3600)`
— **one hour**.

`PERMANENT_SESSION_LIFETIME` is set deliberately to **twelve hours**, with a
comment explaining that a front-desk browser is left open for a whole shift.

So the session outlives the CSRF token by eleven hours. A visit form, an
inpatient billing form or a POS cart left open for over an hour fails on submit
with a `CSRFError`, and the handler does this:

```python
flash("Your session expired while this page was open. Please log in again — "
      "you may need to re-enter what you were working on.", "error")
return redirect(url_for("login"))
```

Three problems in one: the work is gone, the user is forced through a full
re-login they did not need, and **the message is wrong** — the session had not
expired, only the token had. Someone debugging this from the message alone
would go looking at `SESSION_LIFETIME_HOURS`, which is not involved.

This is a front desk. An hour is an ordinary length of time for a form to sit
open while a consultation happens.

**Fix prompt**

> In **both** apps, tie the CSRF token lifetime to the session lifetime instead
> of leaving it at Flask-WTF's one-hour default. Set
> `app.config["WTF_CSRF_TIME_LIMIT"]` from the same
> `SESSION_LIFETIME_HOURS` value that already feeds
> `PERMANENT_SESSION_LIFETIME`, so the two can never drift apart again, and
> comment it saying why they are linked.
>
> Separately, fix the `CSRFError` message so it stops asserting something it
> does not know. If `session.get("user_id")` is still set, the session is
> alive: say the page had been open too long, redirect back to the referring
> page rather than to `/login`, and keep the user logged in. Only fall through
> to the log-in-again path when the session really is gone.
>
> Test both branches: a `CSRFError` with a live session redirects back and does
> not clear the session (guard); a `CSRFError` with no session still redirects
> to login (control).

---

## U2 — An expired session on a POST silently discards everything typed — **CONFIRMED (by inspection)**

**Severity: Medium · both apps**

`require_login()`:

```python
return redirect(url_for("login", next=request.path))
```

For a `POST`, the browser is redirected to the login page, and after a
successful login `login()` does `redirect(nxt)` — a **GET** of that path. The
entire submitted body is gone. The user sees a blank form and no explanation
that anything was lost.

The app already has the machinery to do better: `form_value()` / the `fv()`
Jinja global exist precisely to redisplay a rejected submission, and
`unsaved-changes.js` already warns on navigation away.

**Fix prompt**

> In **both** apps, stop losing a POST body across a re-login.
>
> The minimal honest fix: in `require_login()`, when the request is not a GET
> and the session is gone, flash a specific message before redirecting —
> something like "You were signed out before that could be saved. Please sign
> in and re-enter it." — so the loss is stated rather than silent. That alone
> removes the worst part, which is the user not knowing.
>
> The better fix, if you want it: stash the submitted `request.form` in the
> session under a single-use key before redirecting, and have the target route
> pass it to `render_template` as `form=` on the next GET, which the existing
> `fv()` helper already knows how to consume. Cap the stash size, drop it after
> one read, and never stash a route that carries a password field — enumerate
> those explicitly rather than pattern-matching field names.
>
> Test: POST to a protected route with no session, assert the flash is present
> after following the redirect; with the stash implemented, assert the field
> values come back on the redisplayed form, and assert a password field does
> not.

---

## U3 — Labels are not associated with their inputs — **CONFIRMED (measured)**

**Severity: Medium · both apps**

| | IQ | JO |
|---|---|---|
| `<label>` elements | 236 | 235 |
| ...with `for=` | 3 | 3 |
| `<input>` elements | 330 | — |
| ...with `id=` | 57 | — |

And the labels do not wrap their inputs either — the pattern throughout is
siblings:

```html
<div class="field"><label>Name</label><input required name="name" value="..."></div>
```

So there is no `for`/`id` pairing **and** no implicit nesting. A screen reader
announces "edit text, blank" with no name, and clicking the label does not
focus the field. That is roughly 230 form controls per app.

This is not an exotic requirement — it is the single most basic form
accessibility rule, and the fix is mechanical.

**Fix prompt**

> In **both** apps, associate every form label with its control. The
> established markup is `<div class="field"><label>X</label><input name="y">`,
> so the mechanical transform is: give the input `id="f-<name>"` and the label
> `for="f-<name>"`.
>
> Do it file by file rather than in one sweep, and watch for the cases the
> transform does not cover: fields that already carry an `id` used by JavaScript
> (keep the existing id and point `for` at it), radio and checkbox groups (the
> group needs a `<fieldset><legend>`, not a `for`), and any template rendering
> inputs in a loop where the id must include the loop index to stay unique.
>
> Add a static guard test to the pure tier that fails if a template contains a
> `<label>` with neither a `for=` attribute nor a nested form control. Run it
> against the current tree first — it should report ~230 hits per app, which is
> how you know it works — then fix until it is clean. Finish with a browser-tier
> check on two or three real forms asserting the accessible name is present.

---

## U4 — Table headers carry no `scope` — **CONFIRMED (measured)**

**Severity: Low · both apps**

349 `<th>` elements in each app; **zero** with `scope=`. In a table with both
row and column headers, assistive technology cannot tell which cells a header
governs. These are clinical and financial tables — visit history, billing
lines, inventory, consignment ledgers.

**Fix prompt**

> In **both** apps, add `scope="col"` to every `<th>` inside a `<thead>` row,
> and `scope="row"` to any `<th>` used as the first cell of a body row. This is
> almost entirely mechanical; do it as one change per template so review stays
> readable. Add a static guard test that fails on a `<th>` with no `scope`, run
> it against the current tree first to see all 349 hits, then fix to clean.

---

## U5 — The login form gives password managers nothing to work with — **CONFIRMED (by inspection)**

**Severity: Low · both apps**

`templates/login.html`:

```html
<label>Username</label>
<input name="username" required autofocus>
<label>Password</label>
<input type="password" name="password" required>
```

No `autocomplete` attributes. Password managers fall back to heuristics, and on
a shared front-desk machine with several staff accounts that is exactly where
they misfire. Nine `autocomplete` attributes exist elsewhere in the templates,
so the convention is established — it just was not applied here.

**Fix prompt**

> In **both** apps, add `autocomplete="username"` to the login username input
> and `autocomplete="current-password"` to the password input. In
> `change_password.html`, add `autocomplete="current-password"` to the current
> field and `autocomplete="new-password"` to the new and confirm fields. Do the
> same for the admin new-user and reset-password forms, which should use
> `new-password`. This also stops a browser offering the *current* password as
> a suggestion in a *new* password box.

---

## U6 — JO has no `/favicon.ico` route — **CONFIRMED**

**Severity: Low · JO**

IQ added a root `/favicon.ico` route with a comment explaining that Safari
probes that exact path and, without it, falls back to something wrong. It is
also in IQ's `OPEN_ENDPOINTS` so it works on the login page.

JO has no such route, and `OPEN_ENDPOINTS` is
`{"login", "static", "health", "logout"}` — no `favicon_ico`. JO ships only
`static/favicon.svg`.

Small, but it is a divergence with a recorded reason on one side and no
decision on the other.

**Fix prompt**

> Port IQ's `/favicon.ico` route into JO, adapted to JO's single-palette asset
> naming (JO has no `static_asset()` helper and only `favicon.svg`, so either
> serve that with the right mimetype or add a small `.ico`). Add `favicon_ico`
> to JO's `OPEN_ENDPOINTS` so it resolves before login, matching IQ. Record it
> in `COMPARISON.md` as a closed gap.

---

# DEAD CODE AND DEAD FILES

Detection was mechanical — reference-counting every symbol, template, static
asset, CSS selector and route across `.py`, `.html`, `.js`, `.sql` and the test
suites — then each candidate hand-checked. Several candidates turned out to be
false positives and are recorded below as such, because "we checked and it is
alive" is worth as much as the removals.

## D1 — An unfinished Desktop-shortcut feature, whose dead half is also wrong — **CONFIRMED**

**Severity: Medium (revised up from Low on re-examination) · both apps,
identical**

This was first written up as one stray helper. That was wrong — it is
**6 of the module's 15 functions, 47 lines, byte-identical in both apps**, and
the dead code contains a defect the module's own comments already warn about.

**What is actually unreachable.** Computing the call graph from the only
entry points anything outside the module uses:

```
UNREACHABLE (6 of 15 functions):
  is_present                   L85     7 lines   called by: — nothing —
  remove                       L103    7 lines   called by: — nothing —
  _macos_remove                L211    9 lines   called by: ['remove']
  _windows_remove              L279   10 lines   called by: ['remove']
  _windows_shortcut_paths      L81     2 lines   called by: ['_windows_remove', 'is_present']
  _windows_desktop_candidates  L67    12 lines   called by: ['_windows_shortcut_paths']
```

Every qualified call into the module from anywhere in either app —
`grep -oE 'desktop_shortcut\.[a-z_]+'` across `*.py`, `tests/` and
`templates/`:

```
  5  desktop_shortcut._macos_create   (tests only)
  1  desktop_shortcut.is_supported    (setup.py)
  1  desktop_shortcut.create          (setup.py)
```

**Why the shape matters.** The module exposes
`is_supported / is_present / create / remove`. That is precisely the shape of
`autostart.py`'s `is_supported / is_enabled / enable / disable` — and all four
of *those* are wired, to the Settings "Startup & Shutdown" toggle via
`settings_autostart()`. `desktop_shortcut` has only `is_supported` and
`create` wired, both from `setup.py` at install time.

So `is_present()` and `remove()` are the query-and-undo half of a Settings
control that was designed for and never built. No template mentions a
shortcut (0 of 63 files in IQ), and the README does not either.

**The dead half is not merely unused — it is incorrect.** `_windows_create()`
locates the Desktop through PowerShell, with this comment:

> `[Environment]::GetFolderPath('Desktop')` is the only reliable way to get
> the real Desktop — it follows OneDrive/Known Folder redirection, which
> `%USERPROFILE%\Desktop` does not.

The dead `is_present()` and `_windows_remove()` locate it through
`_windows_desktop_candidates()`, which does exactly what that comment says is
unreliable: it guesses `USERPROFILE\OneDrive\Desktop`, then
`USERPROFILE\Desktop`.

The two halves therefore disagree about where the shortcut lives, and the dead
half uses the method the code itself documents as wrong. Wire it into a
Settings toggle as-is, on any machine whose Desktop is redirected somewhere
those two guesses miss — folder redirection to a network share, or OneDrive
under a localized folder name — and:

- `is_present()` reports "no shortcut" while the icon is visibly on the Desktop;
- `remove()` returns `(True, "There's no Desktop shortcut to remove.")` — a
  **success** message for having done nothing.

**And none of it is tested.** `test_desktop_shortcut_target.py` calls
`_macos_create` five times and touches nothing else; there is no test anywhere
in either app for `is_present`, `remove`, `_macos_remove`, `_windows_remove`
or the Windows path derivation.

**Note on how this was found.** The first pass counted bare-word references,
so `remove` looked used because the token appears throughout the templates and
in `os.remove`. Re-running with an alias-aware, qualified-reference detector
confirms `is_present` is the **only** top-level function in either entire app
with no reference of any kind — so D2–D6 stand and the rest of the codebase is
clean on this axis. `remove()` needed the call-graph check to catch.

## D2 — `heartbeat.py` imports `os` and never uses it — **CONFIRMED**

Both apps. `grep '\bos\.'` in `heartbeat.py` returns nothing.

## D3 — Two unreferenced favicon SVGs in IQ's `static/` — **CONFIRMED**

`static/favicon.svg` and `static/favicon-champet.svg`. `base.html` references
only `favicon-v2.ico`, `favicon-v2-32.png` and `favicon-v2-180.png` through
`static_asset()`, and the `/favicon.ico` route serves `favicon-v2.ico`. Nothing
names either SVG. JO's `favicon.svg` **is** referenced and must stay.

Note this is the same directory that §47 found ten saved web pages in. Flask
serves everything under `static/`.

## D4 — `.settings-strike` is a dead CSS rule — **CONFIRMED**

`static/style.css:911` in IQ. Not used by any template, script or Python file,
and the class does not exist in JO at all. It is the only genuinely dead
selector in either stylesheet — the `vz-toast-*` rules that a naive scan flags
are built dynamically by `toast.js` (`"vz-toast-" + kind`) and are alive.

## D5 — `auth.discount_cap_for(db)` takes an unused parameter — **CONFIRMED**

IQ only. The body reads `session.get("discount_cap", 0)` and never touches
`db`. Nine call sites pass a connection for nothing. JO already has the
no-argument signature.

## D6 — `logic.followups_page()` carries an always-empty `params` — **CONFIRMED**

IQ only. `params = []` is built, never appended to, passed to the `COUNT(*)`
query and then concatenated as `params + [limit, offset]`. JO's equivalent has
no such variable.

## Verified NOT dead

- **All 148 (IQ) / 147 (JO) routes are reachable.** Nine per app initially
  looked orphaned; every one is invoked from JavaScript by string-built URL
  (see M2). No route should be removed.
- **Every template is rendered, extended or included.** No orphans.
- **No other unreferenced static assets** in either app.
- **No unused imports** beyond D2.

**Fix prompt (D1–D6 together)**

> Remove the dead code found by this review, as one small commit per app so it
> is trivially reviewable:
>
> - **Decide D1 first — it is a choice, not a cleanup.** Either (a) delete all
>   six unreachable functions from `desktop_shortcut.py` in **both** apps
>   (`is_present`, `remove`, `_macos_remove`, `_windows_remove`,
>   `_windows_shortcut_paths`, `_windows_desktop_candidates`), or (b) finish
>   the feature: add a Settings control beside the autostart toggle showing
>   whether the shortcut exists, with Create and Remove. If you pick (b), you
>   **must** first replace `_windows_desktop_candidates()` with the same
>   `[Environment]::GetFolderPath('Desktop')` call `_windows_create()` uses, or
>   you ship the redirected-Desktop bug described in D1 — and add the Windows
>   and `is_present`/`remove` tests that have never existed. Option (b) has real
>   user value: today a trashed shortcut can only be restored by re-running
>   `setup.py`.
> - Remove the unused `import os` from `heartbeat.py` in **both** apps.
> - Delete `static/favicon.svg` and `static/favicon-champet.svg` from **IQ
>   only** — JO's `favicon.svg` is referenced and must stay.
> - Delete the `.settings-strike` rule from IQ's `static/style.css`.
> - Change IQ's `auth.discount_cap_for(db)` to `discount_cap_for()`, matching
>   JO, and update all nine call sites.
> - Remove the always-empty `params` list from IQ's `logic.followups_page()`,
>   passing `[limit, offset]` directly.
>
> Because these are deletions, use the §47 ordering: run the full suite before
> and after each deletion, and for the two static files confirm with a live
> request that nothing 404s that did not 404 before. Do **not** remove any
> route — all of them are reachable from JavaScript.

---

# MAINTAINABILITY AND CODING STANDARDS

## M1 — 84/89 code comments cite documents the repo does not contain — **CONFIRMED (measured)**

**Severity: Medium · both apps**

Counting citations of `*.md` filenames in `.py` and `.sql`: **84 in IQ across
12 files, 89 in JO across 11.** Not one of the cited documents is inside either
repository.

Where they actually live:

| Cited document | Where it is |
|---|---|
| `CLAUDE.md`, `COMPARISON.md`, `RELEASE_WORKFLOW.md` | workspace root — not in the repos |
| `ERROR_500_AUDIT.md`, `ORPHANED_RECORDS_AUDIT.md` | `audits/` — not in the repos |
| `CLEANUP_FEATURE_PLAN.md`, `MONITORING_FEATURE_PLAN.md` | `features/` — not in the repos |
| `BUGFIXES.md` | **nowhere on this machine** |
| `CLAUDE_CODE_RELEASE_WORKFLOW.md` | **nowhere** (superseded, source deleted) |
| `UPDATE_MECHANISM_PLAN.md` | **nowhere** (superseded, source deleted) |
| `Consignment_Feature_Framework.md` | **nowhere** |
| `data_integrity_framework.md` | **nowhere** |
| `QA_RESULTS.md` | **nowhere** |
| `IQD CURRENCY ROUNDING PLAN.md` | **nowhere** (cited by `money.py`'s module docstring) |

Both repos are published to GitHub. Someone cloning `vetclinicsystem_iq` finds
dozens of comments of the form "see `ORPHANED_RECORDS_AUDIT.md` F-12" pointing
at a file that is not there — and seven of the titles cannot be found by
anyone, including you, because the documents no longer exist.

This directly undercuts `CLAUDE.md` §0, which instructs a reader to search the
audits before removing anything that looks redundant. The guards are annotated;
the annotations resolve to nothing.

**Fix prompt**

> Make the citations resolvable, in this order.
>
> 1. **The seven that exist nowhere** — `BUGFIXES.md`,
>    `CLAUDE_CODE_RELEASE_WORKFLOW.md`, `UPDATE_MECHANISM_PLAN.md`,
>    `Consignment_Feature_Framework.md`, `data_integrity_framework.md`,
>    `QA_RESULTS.md`, `IQD CURRENCY ROUNDING PLAN.md`. For each citation,
>    either inline the reasoning the comment was deferring to (preferred, since
>    the source is gone and the reasoning is the valuable part), or repoint it
>    at the surviving document that superseded it —
>    `CLAUDE_CODE_RELEASE_WORKFLOW.md` and `UPDATE_MECHANISM_PLAN.md` are
>    superseded by `RELEASE_WORKFLOW.md`, and `IQD CURRENCY ROUNDING PLAN.md`'s
>    content is effectively `COMPARISON.md` §1.1. Do not delete a citation
>    without capturing what it was pointing at.
> 2. **The seven that exist in the workspace but not the repos** — add a short
>    `docs/README.md` to each repo listing them, saying they live in the shared
>    `VetClinicSystem/` workspace and are deliberately not vendored. That makes
>    the reference honest for an outside reader without duplicating 3,700 lines
>    into two repos.
> 3. Add a static guard test to the pure tier that fails if a `.py` or `.sql`
>    file cites a `*.md` filename that is neither present in the repo nor
>    listed in `docs/README.md`. Run it against the current tree first and
>    confirm it reports the full set — that is how you know it works before you
>    trust it.

---

## M2 — 22/21 hardcoded URLs in templates instead of `url_for()` — **CONFIRMED (measured)**

**Severity: Medium · both apps**

Every route this review initially flagged as unreachable was in fact reached by
a string-built URL in JavaScript — `fetch(\`/api/sales/${id}/refundable-items\`)`,
`form.action = '/admin/roles/' + roleId + '/delete'`, and so on. 22 in IQ, 21
in JO, covering the POS lookup, patient search, price-list lookup, barcode
management, refunds, boarding incident and payment, appointment cancel, role
delete, the updater endpoints and the folder browser.

Two consequences. Renaming or re-prefixing a route breaks the UI silently, with
no import error, no template error and no test failure — which is exactly the
shape of the POS "Complete Sale" bug in `COMPARISON.md` §27, where route tests
POSTed directly and never clicked. And it defeats static analysis: nothing can
tell you which routes the UI actually uses.

**Fix prompt**

> In **both** apps, stop hardcoding application URLs in templates.
>
> For a URL with no dynamic segment, replace the literal with
> `{{ url_for('endpoint') }}` directly. For one with a dynamic segment, emit a
> template from Jinja using a placeholder id and substitute in JS —
> `const url = "{{ url_for('api_sale_refundable_items', sale_id=0) }}".replace(/0$/, encodeURIComponent(saleId))`
> is brittle; prefer putting the built URL on the element as a `data-url`
> attribute rendered by `url_for()` in the loop that already has the id, and
> reading it in the handler. That is the pattern the appointment and boarding
> buttons are closest to already, since they carry `data-appt-id` /
> `data-pet-name`.
>
> Add a static guard test that fails if a template contains a `fetch(`,
> `.action =` or `window.location =` whose target is a string literal starting
> with `/`. Run it against the current tree first — it must report 22 hits in
> IQ and 21 in JO — then fix to clean. Finish with the browser tier, which is
> the only tier that can catch a URL you rewrote wrong.

---

## M3 — `app.py` is one 7,000-line module — **CONFIRMED (measured)**

**Severity: Medium · both apps**

IQ 7,066 lines / 148 routes; JO 6,921 / 147. Already recorded as open work in
`TRANSITION_NOTES` §4.7, which correctly says splitting it is worth doing *now
that tests exist to catch what a split breaks* — that condition is met: 528 and
509 passing, zero skips, all three tiers alive.

Listed here for completeness rather than as news. It is also the reason M4, M2
and D6 are as easy to accumulate as they are.

**Fix prompt**

> Split `app.py` into Flask blueprints, one module per domain, in **both** apps
> — but do it as a series of separate, individually-verified moves, not one
> commit.
>
> Suggested order, easiest and most isolated first: `settings` (and the updater
> endpoints), `admin` (users, roles, logs), `consignment`, `inventory` (catalog,
> price list, audits, barcodes), `sales` (POS, refunds, cash register),
> `clinical` (owners, patients, visits, inpatient, boarding, appointments).
> Leave app construction, config, error handlers, `before_request` hooks and the
> shared parsing helpers in `app.py` — those are genuinely cross-cutting.
>
> Rules for each move: pure relocation, no behaviour changes in the same commit;
> run the full suite including the browser tier after each one; and check
> `url_for()` endpoint names, which gain a blueprint prefix and will break every
> template and every hardcoded URL that names them. **Do M2 first** — the
> hardcoded URLs are the part a blueprint rename breaks silently.

---

## M4 — Eleven/ten functions over 100 lines — **CONFIRMED (measured)**

**Severity: Low · both apps**

Longest, excluding the standalone scripts:

| | IQ | JO |
|---|---|---|
| `pos_checkout` | 199 | 202 |
| `settings_page` | 158 | 149 |
| `visit_billing_save` | 154 | 147 |
| `refund_retail_save` | 137 | 134 |
| `logic._revenue_and_cogs_by_month` | 156 | 112 |
| `logic.consignment_balance` | 135 | 132 |

`pos_checkout` is the one that matters most: it is the highest-traffic
transactional path, it holds row locks, and it is the route that silently did
nothing for 25 releases (§27).

**Fix prompt**

> Extract cohesive blocks from `pos_checkout` in **both** apps, tailored per
> app rather than ported — this is money code and the two apps' types differ
> (`COMPARISON.md` §1.1). Natural seams, in order: cart parsing and quantity
> merging; the lock-and-snapshot step; per-line pricing and stock validation;
> discount and Clean Up validation; the insert-and-audit step. Each becomes a
> helper taking `db` and returning either a value or an error string, matching
> the existing `discount_percent_error()` / `cleanup_amount_error()` convention.
>
> Pure refactor, no behaviour change. Run the full suite plus the browser tier
> before and after — the browser tier is the only thing that proves the button
> still works, which is the specific lesson of §27. Do the other five
> long functions only after this one has landed and shipped cleanly.

---

## M5 — JO duplicates Clean Up validation in four routes — **CONFIRMED**

**Severity: Low · JO**

IQ has `cleanup_amount_error(new_amount, existing_amount, balance)` at
`app.py:431`, used from four payment routes. JO inlines the same three checks
at four sites — `app.py` lines ~2800, ~5081, ~5297 and ~5795 — and they are not
identical: the POS copy compares against `total` rather than an accumulated
prior amount (correct, and commented), and another compares against
`balance_after_discount`.

I checked whether any copy had drifted into a missing check. **None had** — all
four include the negative check, the cap check and the balance check. So this
is duplication, not a bug. It is still four places to change and four chances to
miss one.

IQ's `discount_percent_error()` is in the same position — a shared helper in IQ,
inline in JO.

**Fix prompt**

> In JO, extract `cleanup_amount_error()` and `discount_percent_error()` as
> shared helpers matching IQ's signatures and convention, and route all four
> Clean Up sites and all discount sites through them. Preserve the two
> legitimate per-site differences by passing them as arguments — the POS site's
> "no prior accumulated amount" case and the boarding site's
> `balance_after_discount` — rather than by keeping a special-cased copy.
>
> This is money code: re-derive against JO's `Decimal` types rather than
> copying IQ's `float` helper. Run JO's money tests before and after; they
> should be unchanged, which is the point. Confirm the helper actually bites by
> temporarily removing one check from it and watching the corresponding tests
> at all four sites fail.

---

## M6 — JO's `auth.py` describes features JO has — **CONFIRMED**

**Severity: Low · JO**

`auth.py` lines 20–25:

> Includes a few keys (`manage_cash_register`, `view_consignment`,
> `manage_consignment_items`, `manage_consignment_stock`,
> `manage_consignment_settlements`) for features **this app doesn't have yet** —
> kept in the vocabulary now so adding those features later is a permission
> grant, not a second permissions-list migration.

JO has all of them. `grep '@app.route'` finds 14 consignment routes and 3
cash-register routes, and the permission keys are used 13 and 3 times
respectively as live decorators.

Exactly the failure mode `CLAUDE.md`'s own header warns about: a stale claim in
a file that loads on every read.

**Fix prompt**

> Delete the stale paragraph from JO's `auth.py` and replace it with a one-line
> note that every permission key in the list is live and enforced, dated. While
> there, check the rest of `auth.py`'s comments against JO's actual routes —
> that block was written before the consignment and cash-register work landed
> and nothing re-checked it.

---

## M7 — The documented coverage command cannot run in the sanctioned environment — **CONFIRMED**

**Severity: Low · tooling**

`CLAUDE.md` §7 says to re-measure coverage with:

```bash
TEST_DATABASE_URL=... venv/bin/python -m pytest tests/ -q --cov=. --cov-report=
venv/bin/python -m coverage report --omit="tests/*,venv/*" --sort=cover
```

`scripts/isolated_test_env.sh up` installs `pytest` and `playwright` and
nothing else. Running the documented command in the environment the same
document tells you to build:

```
python -m pytest: error: unrecognized arguments: --cov=. --cov-report=
/private/tmp/vz_iq_test_venv/bin/python: No module named coverage
```

This is why the coverage table in `CLAUDE.md` §7 was **not** re-measured during
this review. Same shape as the `venv/bin/python` correction already recorded in
§7.1 on 2026-09-09: an instruction that cannot be followed as written.

**Fix prompt**

> Add `pytest-cov` to the test-only install in `scripts/isolated_test_env.sh`,
> alongside `pytest` and `playwright`, with a comment saying it exists so
> `CLAUDE.md` §7's coverage command actually runs. Keep it out of both apps'
> `requirements.txt`, per `TRANSITION_NOTES` §5.
>
> Then bring both environments up, run the §7 command end to end, and correct
> §7's coverage table with the measured figures and today's date — the current
> numbers are dated 2026-09-01 and predate the microchip feature, the GitHub
> quota fix and the §47 guard.

---

## M8 — Roughly 490 inline `style=` attributes per app — **CONFIRMED (measured)**

**Severity: Low · both apps**

497 in IQ, 488 in JO. Sizing, spacing, colour and `display:none` toggles are
scattered across the templates rather than living in `style.css` — which is
otherwise in good shape (994 / 782 lines, one dead rule between them).

This is what made the card-spacing drift of §38 app-wide and identical in both
apps, and what makes a theming or responsive change require touching 60
templates instead of one stylesheet.

**Fix prompt**

> This is not worth a big-bang sweep. Adopt a rule and apply it opportunistically:
> whenever a template is edited for any other reason, move its inline `style=`
> declarations into `style.css` as classes, reusing the existing token
> variables (`--line-soft`, `--muted-tint`, `--danger`, the 16px card-spacing
> unit from §38) rather than inventing literals.
>
> Two exceptions to leave alone: server-computed values that genuinely have to
> be inline (`style="display:{{ 'none' if ... }}"`), and one-off print styles.
>
> Do the two worst offenders deliberately as a first pass —
> `settings.html` (644 lines) and `inventory_catalog.html` (435) — and note the
> convention in each app's README so it does not drift back.

---

## M9 — Zero-width space inside a `backup.py` comment — **CONFIRMED**

**Severity: Trivial · IQ**

A U+200B sits between `run_backup()/` and `_log()` in a comment in IQ's
`backup.py`, inside `resolve_restorable_backup()`. Invisible, harmless, and it
makes a diff against JO's identical comment show a phantom change — which is
exactly how it was found.

**Fix prompt**

> Remove the U+200B from the comment in IQ's `backup.py`
> (`resolve_restorable_backup()`, the `run_backup()/_log()` line) so the two
> apps' copies of that comment are byte-identical. While there, run a quick
> sweep for other zero-width or non-breaking characters across both trees —
> `grep -P '[\x{200B}\x{200C}\x{200D}\x{FEFF}\x{00A0}]'` — and clean any others
> found.

---

---

# ADDED AFTER THE REVIEW — user-reported, 2026-09-10

Two findings raised by the user after the sweep, both confirmed and both fixed
in the same session. They are numbered separately because they were not part of
the original 37.

| ID | Severity | Apps | Finding | Status |
|---|---|---|---|---|
| **R1** | **High** | both | A boarding stay could be paid for and never refunded | **DONE** |
| **R2** | Medium | both | The service-refund form called its anchor optional when it is required | **DONE** |

## R1 — Boarding stays were not refundable — **CONFIRMED**

**Severity: High · both apps**

The schema states the gap plainly. `payments` anchors on exactly one of three:

```sql
CONSTRAINT payments_one_anchor_ck CHECK (
    (visit_id IS NOT NULL)::int
  + (inpatient_case_id IS NOT NULL)::int
  + (boarding_id IS NOT NULL)::int = 1
)
```

`refunds` had only two, and its CHECK actively required one of them:

```sql
OR (refund_type = 'service' AND sale_id IS NULL
    AND (visit_id IS NOT NULL) <> (inpatient_case_id IS NOT NULL))
```

So money could be taken for a boarding stay and there was no way to give it
back through the Refunds page — not merely a missing form field, but a
constraint that would have refused the row.

**Is anything else uncovered?** No. There are four billable client surfaces:
visits, inpatient cases, boarding stays, and POS sales. Refunds covered three.
Grooming and wellness are billed through a visit (`billing` /
`visit_billing_lines` key on `visit_id`), so they are covered by the visit
anchor. `distributor_bills` and `consignment_settlements` are supplier-side,
not client refunds. Boarding was the only gap.

**A second defect found while fixing it.** `logic.revenue_by_category()` mapped
every non-retail refund to the `Service` column:

```sql
CASE WHEN r.refund_type='retail' THEN 'Retail' ELSE 'Service' END
```

Boarding revenue has its own column, so a boarding refund would have reduced
Service while Boarding stayed untouched — pushing two P&L columns apart and
making neither right. Fixed in the same change.

**What was done**, per app rather than ported (this is money code —
`COMPARISON.md` §1.1):

- `refunds.boarding_id`, the anchor CHECK widened from "exactly one of two" to
  "exactly one of three", and a foreign key to `boarding_sessions`.
- A migration in `INCREMENTAL_SCHEMA_STATEMENTS` — extending the existing
  `refunds_anchor_ck` pair rather than adding a second one. Additive: every
  existing row already satisfies the widened rule.
- `refund_service_save()` in each app's own idiom: IQ sums the `payments`
  table and compares with its `1e-9` float epsilon; JO reads
  `logic.boarding_billing_summary()["paid"]` and compares exact `Decimal`.
- The Clean Up snapshot extended to `boarding_sessions.cleanup_amount`.
- `FOR UPDATE` on the boarding row before the cap is computed, matching the
  visit and inpatient branches.

**Verified**: 16 tests per app, mutation-proved. Reverting the anchor check to
two-way fails 8; removing the boarding cap fails exactly the 2 cap tests;
reverting the category CASE fails exactly the 1 P&L test. The visit and
inpatient controls pass under all three, which is what shows they are controls
and not noise.

## R2 — The service-refund form contradicted itself — **CONFIRMED**

**Severity: Medium · both apps**

The description read:

> Removes a revenue amount only — no stock is touched. Link it to a Visit or
> Inpatient case ID for your own records, if relevant **(optional)**.

Directly beneath it, the two fields were labelled *"Visit ID (required — or
Inpatient Case ID below)"* and *"Inpatient Case ID (required — or Visit ID
above)"*, and `refund_service_save()` rejects a submission with neither. So the
paragraph told staff the link was optional, the labels told them it was
required, and the server agreed with the labels.

Rewritten to say what is actually true — exactly one of the three is required,
the refund is capped at what is still refundable against that record, and a
goodwill refund with no record behind it belongs in Cash Register. The
per-field labels now read "(one of these three)" rather than each claiming to
be "required".


## Suggested order of work

Grouped by what unblocks what, not strictly by severity.

1. **S1, S2** — the access-control pair. They compound, and S2's fix is small.
2. **B1, B2** — the updater's version ordering. Both are the same root cause and
   should land together, with the unit tests `updater.py` has never had.
3. **B4** — pin JO's dependencies before the next JO release, since the updater
   builds a venv per release.
4. **U1** — a one-line config fix plus an honest error message, high
   user-visible value.
5. **S3, B3** — audit-log integrity and scheduler observability.
6. **D1–D6** — the deletions. Cheap, and best done before M3 moves code around.
7. **M2** — hardcoded URLs. **Must precede M3.**
8. **S4** — reconcile the lockout implementations.
9. **U3, U4, U5** — accessibility, mechanical, guard-test-driven.
10. **M1, M6, M7** — documentation integrity.
11. **B5, B6, B7, S7, S8, U2, U6, M5, M9** — the remainder.
12. **M3, M4, M8, S6** — the structural work, once tests and URLs are ready.

## Standing rules that apply to every item

- **`COMPARISON.md` §2 before any cross-app port.** Several findings here are
  one-app only, and several of the two-app ones need re-deriving rather than
  copying — S4 and M5 especially.
- **`CLAUDE.md` §7.3 on every guard**: reintroduce the bug and watch the test
  fail, and always pair a guard with a control. Where the bug is still present
  (S2, M1, M2, U3, U4) run the guard first and watch it fail — that ordering is
  free and strictly better evidence, per §47.
- **Append a dated note to `COMPARISON.md`** for anything that changes how the
  two apps compare — S4, S8, B4, U6 and M6 all do.
- **Follow `RELEASE_WORKFLOW.md`** for anything that ships.