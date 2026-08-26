# Operational Monitoring — Implementation Plan

Status: **APPROVED, NOT YET BUILT** — written 2026-08-26; every open question
resolved with the user the same day (§0.4, §7). This is ready to implement as
written. Nothing needs checking back before starting.
Scope: VetClinicSystem_IQ and VetClinicSystem_JO. Four layers (§1–§4), built
and shipped together in one release per app — see §6.

This plan follows the ground rules in `CLAUDE.md`: it is written from each
app's **actual current code**, cited by `file:line`, and treats IQ and JO as
siblings needing separately tailored changes.

> **Money surface: none.** Unusually for this codebase, nothing here touches
> currency, rounding, or `compute_bill_totals()`. The IQ/JO money divergence
> (`CLAUDE.md` §1, `COMPARISON.md` §1.1) does **not** apply to any code in
> this plan. The divergences that *do* apply are listed in §0.2 — read those
> before assuming a change can be copied between the apps.

---

## 0. Context the implementer needs

### 0.1 The problem, stated precisely

Everything the app can currently report requires the app to be **running** to
report it. `backup_alert_message()` needs the machine on, Postgres up, and a
request being served.

The failures that actually cost a clinic its data are the ones where none of
that holds: the machine never came back after a power cut, Docker did not
start, someone closed the terminal window, the disk filled. **Those produce
no error at all — they produce silence.**

So the primary signal is not an error report. It is the *absence* of an
expected signal. That inversion is what §2 exists for, and it is the reason
§1 alone is not sufficient.

Second constraint, equally load-bearing: **the audience is the maintainer,
not the clinic.** Clinic staff scroll past banners. The maintainer is remote,
and the clinic machine is behind NAT — so it cannot be polled. It has to
push.

### 0.2 Divergences that apply to this work

Verified by reading both trees on 2026-08-26, not assumed:

| Item | IQ | JO |
|---|---|---|
| `scheduler.py` | 77 lines | 78 lines — **files differ**; diff before editing |
| `logic.backup_alert_message()` | — | **differs from IQ**; do not copy one over the other |
| `/health` route | identical in both | identical in both |
| Data-dir env var | `VETCLINICSYSTEMIQ_DATA_DIR` | `VETCLINICSYSTEMJO_DATA_DIR` |
| Backup filename prefix | `vetclinicsystemiq_backup_` | `vetclinicsystemjo_backup_` |
| `apply_incremental_migrations()` | takes no args; updater calls it explicitly | takes `con`; called from inside `apply_schema()` |

### 0.3 What already exists and must be reused, not rebuilt

Line numbers below are **IQ's**, correct as of v1.10.8. JO's differ — locate
by symbol name, not by line.

| Existing | Where | Use it for |
|---|---|---|
| `backup_log` / `restore_log` tables | `backup.py` | backup age, last outcome |
| `backup.last_backup(db)`, `recent_backups(db, limit)` | `backup.py:593,597` | the same |
| `backup.reap_stale_running(db)` | `backup.py:573` | detecting stranded `running` rows |
| `logic.backup_alert_message(row)` | `logic.py:72` (IQ; JO differs) | the existing Dashboard banner — **extend, do not replace** |
| Dashboard wiring | `app.py:1568`, gated on `manage_settings` | where the verdict surfaces |
| Banner render | `templates/dashboard.html:20` | ditto |
| `settings.migration_failures` | set by `setup.py` | a self-check finding |
| `scheduler.start(get_db, close_db)` | `scheduler.py` | where the daily job hangs |
| `requests` | already in `requirements.txt` (used by `updater.py:110`) | the heartbeat POST — **no new dependency** |
| `/health` | `app.py` | already returns `{status, version}` |

### 0.4 Decisions already made

Do not re-derive or re-ask these.

| Question | Decision | Rationale |
|---|---|---|
| New permission key? | **No.** Reuse `manage_settings`, which already gates the Dashboard backup alert and the Settings page. | Consistent with the Clean Up plan's precedent; a monitoring-only permission would gate one banner. |
| Heartbeat on by default? | **No.** Off unless `heartbeat_url` is set. | An app that phones home by default is not acceptable for clinic software. Opt-in, per install. |
| Build a receiver? | **No — recommend healthchecks.io.** | It *is* this primitive: ping on a schedule, alert on absence, free tier. A self-hosted receiver is one more thing that can fail silently. §2.4 covers self-hosting if preferred later. |
| Patient data in the payload? | **Never.** Counts and statuses only. | See §3.2. Anything else turns this into a data-protection conversation with every clinic. |
| Alert on individual errors? | **No.** Only sustained conditions. | A 500 on a hand-crafted URL is not an incident; alerting on it trains everyone to ignore alerts. |
| Hosted receiver or self-host? | **healthchecks.io**, at least initially. | Purpose-built for exactly this (ping on a schedule, alert on absence), free tier, nothing to keep alive. §2.4 covers moving off it later, and is explicitly *not* the starting point. |
| One receiver for all clinics, or one per clinic? | **One check per install**, distinguished by `heartbeat_install_id`. | A shared check cannot tell you *which* clinic went quiet, which is the only thing the alert needs to say. |
| Modal dismissal window? | **Session only.** | A day-long dismissal means a machine rebooted each morning never shows it again. A reboot should re-surface it. |
| Backup staleness threshold? | **2 days.** | Backups are nightly: one missed night is noise, two is a pattern. Configurable via `selfcheck_backup_max_age_days` (§1.6) if a clinic proves otherwise. |
| Blocking modal? | **Yes, but only for `manage_settings` holders, and only after 3 consecutive failing days.** | A dismissible banner is what is already being ignored. §1.5. |

---

## 1. Layer 1 — the local self-check

**Works with no internet. Must stand alone**, because a clinic that never
gets online still needs this.

### 1.1 New module: `selfcheck.py`

One new file per app, at the repo root beside `backup.py`.

```python
def run_self_check(db) -> dict:
    """Returns:
       {
         "status": "ok" | "warn" | "fail",
         "ran_at": "2026-08-26T02:05:00",
         "findings": [
             {"code": "backup_stale", "severity": "fail",
              "message": "No successful backup for 6 days."},
             ...
         ],
       }
    Never raises. A check that cannot run records itself as a finding with
    severity "warn" — silence is the thing this whole feature exists to
    prevent, so a check that quietly skips is treated as a problem, not a
    pass. (Same rule as scripts/restore_drill.sh.)
    """
```

### 1.2 The checks

Implement exactly these. Each returns at most one finding.

| code | severity | condition |
|---|---|---|
| `backup_never` | fail | `backup.last_backup(db)` is None |
| `backup_stale` | fail | newest successful backup older than `selfcheck_backup_max_age_days` (default 2) |
| `backup_failing` | fail | the 3 most recent `backup_log` rows are all `failed` |
| `backup_stranded` | warn | a `backup_log` row is `running` and older than 6 hours |
| `backup_dir_missing` | fail | `settings.backup_dir` unset, or the path does not exist and cannot be created |
| `backup_dir_unwritable` | fail | the folder exists but a probe write fails |
| `disk_low` | warn / fail | free space on the backup volume < 2 GB (warn) or < 500 MB (fail), via `shutil.disk_usage()` |
| `migration_failed` | fail | `settings.migration_failures` non-empty |
| `update_rolled_back` | warn | most recent `updater` log entry records a rollback |
| `restore_unverified` | warn | no passing verified-restore result in the last 45 days (§4) |
| `db_unreachable` | fail | the check's own `SELECT 1` raises |

`status` is the worst severity present; `ok` when `findings` is empty.

> **Do not add a "row counts look wrong" check.** There is no baseline to
> compare against, and it would fire on a quiet clinic.

### 1.3 Storage

New table in **both** apps' `schema_postgres.sql`:

```sql
CREATE TABLE IF NOT EXISTS self_check_log (
    id          INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    ran_at      TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('ok','warn','fail')),
    findings    TEXT,          -- JSON array, may be empty
    reported_at TEXT           -- set by §2 once this result was sent; NULL if not
);
CREATE INDEX IF NOT EXISTS idx_selfcheck_ran ON self_check_log(ran_at DESC);
```

> **Critical, per `COMPARISON.md` §25 and the v1.10.6 bug:** a new table goes
> in `schema_postgres.sql` only, using `CREATE TABLE IF NOT EXISTS`. Do **not**
> add a `CREATE INDEX` to `schema_postgres.sql` that references a column added
> by `INCREMENTAL_SCHEMA_STATEMENTS` — `apply_schema()` runs first and it will
> raise on every upgrade. The index above is safe because its column is in the
> `CREATE TABLE`. `tests/test_migrations.py` has a static guard for this;
> it must stay green.

Retention: keep 180 rows, pruned in the same job that writes them.

### 1.4 When it runs

Two triggers, both in `scheduler.py` (**which differs between the apps — diff
first**):

1. **Daily**, 20 minutes after `backup_time`, so it judges that night's backup.
   Add a second `add_job` with `id="daily_self_check"` alongside the existing
   `nightly_backup`. `reschedule()` must move both.
2. **At startup**, once, after the schema is applied — catches a machine that
   has been off for a week.

### 1.5 How it surfaces

Extend the existing path at `app.py:1568`; do not add a parallel one.

- `status == "ok"` → nothing shown.
- `warn` → the existing Dashboard banner, listing findings.
- `fail` → the banner, styled with `--danger`.
- `fail` **on 3 consecutive days** → a modal on the Dashboard for
  `manage_settings` holders, dismissible for that session only, reappearing
  next login until the condition clears.

The modal is the point. A banner is what is currently being ignored.

### 1.6 Settings

Add to the key list at `app.py:~6490` and to `NUMERIC_RANGES` at `app.py:~6389`:

| key | default | range |
|---|---|---|
| `selfcheck_backup_max_age_days` | `2` | 1–30 |
| `selfcheck_enabled` | `1` | — (checkbox) |

---

## 2. Layer 2 — the heartbeat

### 2.1 New module: `heartbeat.py`

```python
def send(db, payload: dict) -> tuple[bool, str]:
    """POSTs the payload to settings.heartbeat_url. Returns (ok, message).

    NEVER raises and never blocks longer than the timeout. A failed
    heartbeat is logged and recorded, and is explicitly NOT escalated to
    the user: the clinic cannot act on it, and a red banner about
    monitoring would train them to ignore banners that matter.
    """
```

- `timeout=10`, no retries beyond one immediate retry after 5 seconds.
- Runs **after** the daily self-check, in the same job, so it carries a fresh
  verdict.
- If `heartbeat_url` is empty: return `(True, "disabled")` and do nothing.
  Disabled is the default and is not a finding.
- On success, set `self_check_log.reported_at`.

### 2.2 Why absence is the signal

The receiver's job is to alert when a ping **does not arrive**. This is the
only mechanism in the plan that covers "the machine is off", "Docker did not
start", "the app crashed at boot" — none of which can report themselves.

Implementers sometimes invert this and alert only on `status == "fail"`
payloads. **That is the wrong design and defeats the purpose of the layer.**

### 2.3 The receiver: healthchecks.io (decided, §0.4)

- One check per clinic install, period 1 day, grace 36 hours.
- The ping URL goes in `settings.heartbeat_url`.
- The payload (§3) is POSTed as the body; healthchecks.io stores and displays
  it, and emails when a ping is late.
- Free tier covers a handful of installs.

### 2.4 If self-hosting later

A Cloudflare Worker + KV is roughly 30 lines: store `last_seen` per install
id, and a scheduled trigger that emails when `now - last_seen > 36h`. Only
worth building once the hosted version has proved the idea. **Do not build
this first** — a monitoring system that fails silently is worse than none.

### 2.5 Settings

| key | default | notes |
|---|---|---|
| `heartbeat_url` | `""` | empty disables the whole layer |
| `heartbeat_install_id` | generated once | random 8-char id, so one receiver can host several clinics |

`heartbeat_url` must be validated as `https://` on save, and stored as-is.
Do **not** log the full URL anywhere — for healthchecks.io the URL *is* the
credential.

---

## 3. Layer 3 — the payload

### 3.1 Exact shape

```json
{
  "install_id":   "A1B2C3D4",
  "app":          "iq",
  "version":      "1.10.8",
  "sent_at":      "2026-08-26T02:20:00",
  "status":       "warn",
  "findings":     [{"code": "disk_low", "severity": "warn",
                    "message": "3.1 GB free on the backup volume."}],
  "backup": {
    "last_success_at":  "2026-08-26T02:00:11",
    "age_hours":        0.3,
    "last_size_bytes":  131847,
    "consecutive_failures": 0,
    "verified_at":      "2026-08-01T02:40:00",
    "verified_result":  "pass"
  },
  "db": {
    "reachable":  true,
    "table_count": 44,
    "row_counts": {"owners": 12, "patients": 14, "visits": 14, "sales": 88}
  },
  "disk_free_bytes": 3221225472,
  "uptime_hours": 41.2
}
```

### 3.2 What must never be in it

Hard rule, no exceptions:

- no owner, patient, or staff **names**
- no phone numbers, addresses, or notes
- no money figures — no totals, balances, revenue or prices
- no free-text from any user-entered field
- no full file paths (a basename is fine; a path can carry a person's name)

**Counts and statuses only.** `row_counts` is deliberately limited to the
tables listed above; it exists to show a database is not empty, not to
describe a clinic's business.

### 3.3 Size

Keep under 4 KB. Truncate `findings` to the 10 worst.

---

## 4. Layer 4 — the self-verifying backup

Without this the whole feature reports on a file's *existence*, which is
worth very little: a truncated dump, a correctly-sized file of random bytes,
and a structurally perfect archive containing zero rows all look identical
on disk — and the third restores cleanly. This was demonstrated against
`scripts/restore_drill.sh`; see `COMPARISON.md` §23.3.

### 4.1 What to build

A Python port of the essential checks in `scripts/restore_drill.sh`, run
**monthly** from the same scheduler, against the newest backup:

1. restore into a throwaway database on the same Postgres server
   (`CREATE DATABASE selfverify_<random>`) — **not a container**, so this
   works on a clinic machine with no Docker permissions
2. assert: table count > 0, foreign keys present, core tables populated,
   at least one user row, no orphaned patients
3. assert the money column type — `numeric` for JO, `double precision` for
   IQ. **This is the one place the apps' divergence shows up in this plan**
4. `DROP DATABASE` in a `finally`, always

Build this BEFORE Layers 2 and 3 (see §6.3): the `restore_unverified`
finding and the `backup.verified_*` payload fields both read its output.

Record the result as `settings.last_verified_restore` (`{at, result, detail}`)
and feed it into the `restore_unverified` finding (§1.2) and the payload
(§3.1).

### 4.2 Guard rails

- Never touch the live database. Restore only into the throwaway one.
- Never delete a backup file.
- Hard timeout (10 minutes); on timeout, record `warn`, drop the database,
  move on.
- Skip if `pg_restore` is unavailable, recording a `warn` finding — not a
  silent pass.

---

## 5. Tests required

Follow the existing conventions: `tests/`, `conftest.py`'s `needs_db`, and
skip cleanly when a database is absent.

### 5.1 `tests/test_selfcheck.py` (both apps)

For each check in §1.2, arrange the condition and assert the finding appears
with the right severity — plus the inverse, asserting a healthy database
produces `status == "ok"` and no findings. **The healthy-case test is not
optional**: without it, a self-check that always reports `fail` would pass
every other test in the file.

Specifically cover: no backup ever; a stale backup; three consecutive
failures; a stranded `running` row; an unset backup folder; a populated
`migration_failures`; and the escalation to `fail` on the third consecutive
day.

### 5.2 `tests/test_heartbeat.py` (both apps)

- an empty `heartbeat_url` sends nothing and reports `disabled`
- a payload contains **none** of the forbidden fields in §3.2 — assert by
  seeding an owner named `ZZTESTOWNERNAME` and a phone, then asserting
  neither string appears anywhere in `json.dumps(payload)`
- a receiver returning 500, and a connection error, both return `(False, ...)`
  and **do not raise**
- the URL is never written to any log
- payload stays under 4 KB with 200 findings

### 5.3 Mutation checks before declaring done

Per the discipline used throughout this codebase — a test that passes on
first run has not yet been shown to catch anything. Reintroduce each of
these and confirm a test fails:

- self-check always returns `ok`
- `backup_stale` threshold ignored
- heartbeat sends the payload even when the URL is empty
- a patient name added to the payload
- the verified-restore step reports `pass` when the restore actually failed

### 5.4 Regression guard that must stay green

`tests/test_migrations.py::test_no_index_in_the_schema_file_depends_on_a_migration_added_column`
— the new table in §1.3 must not break it.

---

## 6. Rollout

Per `RELEASE_WORKFLOW.md`. Both apps are versioned independently.

**Build and ship all four layers in a single release per app.** An earlier
draft staged them across three; that was overturned deliberately, and the
reasoning below matters because the risk staging was managing is still real
and now has to be handled a different way.

1. **MINOR** bump in each app (new feature, additive schema).
2. Schema change is additive-only: one new table, no alterations to existing
   ones. This satisfies §6.2 of the release workflow — but re-read that
   section's ordering warning before adding anything to
   `schema_postgres.sql`.
3. Build in dependency order — **1 → 4 → 2 → 3** — even though they ship
   together:
   - **Layer 1** first: it is the only one that stands alone, and everything
     else consumes its verdict.
   - **Layer 4** next, not last. The `restore_unverified` finding (§1.2) and
     the `backup.verified_*` payload fields (§3.1) both depend on it, so
     building it after Layer 3 means going back to wire it in.
   - **Layers 2 and 3** last: the heartbeat is the thin part, and it should
     be sending a payload that is already complete and already correct.
4. One release per app, `CHANGELOG.md` describing it as a single feature.

### 6.0 What staging was protecting, and how to protect it now

The staged plan existed so a noisy self-check could be caught on a healthy
install before anything started phoning home. Shipping together removes that
natural gap, so it has to be replaced by two things that are **not optional**:

- **The heartbeat ships disabled.** `heartbeat_url` defaults to empty (§0.4),
  so a fresh install runs Layer 1 only until someone deliberately sets a URL.
  That preserves the staging benefit without a second release: enable it on
  one clinic, watch it for a week, then roll out.
- **§6.1's soak must actually be run before the release**, not after. A
  monitoring feature that cries wolf in its first week gets turned off and
  never turned back on, and with everything in one release there is no second
  chance to discover that.

### 6.1 Verify before shipping

All of these, before the single release goes out — there is no second
release to catch what they miss.

- run `scripts/isolated_test_env.sh up {iq,jo}` and confirm the self-check
  reports `ok` on a healthy seeded install, **on several consecutive daily
  runs, not one** — a check that is quiet once but noisy on day three is the
  failure staging used to catch
- break one thing deliberately (rename the backup folder) and confirm the
  banner appears, then that the modal appears on the third consecutive day
- confirm a fresh install with no `heartbeat_url` sends nothing at all and
  records no finding about it
- point `heartbeat_url` at a real healthchecks.io check and confirm a ping
  arrives with the payload of §3.1
- confirm the payload contains none of §3.2's forbidden fields, against a
  database holding real-looking names and phone numbers
- run Layer 4 end to end and confirm it drops its throwaway database even
  when the restore fails
- **stop the app for 48 hours and confirm the receiver alerts.** This is the
  only test of the property the whole feature exists for. It cannot be
  rushed, and it cannot be inferred from the other checks passing.

---## 7. Nothing is open

Every question this plan originally raised has been answered and folded into
§0.4. There is nothing to check back on before starting — build it as
written.

If something in here turns out to be wrong once you are in the code, that is
a finding worth recording (append to `COMPARISON.md`, per `CLAUDE.md` §4),
not a reason to stop and ask.
