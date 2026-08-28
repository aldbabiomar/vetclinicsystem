# Code review — operational monitoring + Windows autostart

**Date:** 2026-08-27
**Effort:** high
**Scope:** the unreleased work on `main` in both apps

| App | Range | Files | Lines |
|---|---|---|---|
| VetClinicSystem_IQ | `v1.10.9..HEAD` (7 commits) | 15 | +3,328 / −20 |
| VetClinicSystem_JO | `v1.8.10..HEAD` (7 commits) | 15 | +3,350 / −46 |

New modules `selfcheck.py`, `selfverify.py`, `heartbeat.py`; substantial changes to
`scheduler.py`, `autostart.py`, `app.py`, `schema_postgres.sql`, and the dashboard /
settings templates.

> The workspace repo (`VetClinicSystem/`) tracks only docs, so its own `HEAD~1` diff is
> a `SOAK_LOG.md` edit. The reviewable code is in the two nested clones, which have no
> upstream configured — the release tags are the only sensible base.

---

## Findings

Nine findings, most severe first. All were traced to the code that produces the failure,
not inferred from the diff alone.

### 1. `heartbeat_url` credential is written to the audit log — HIGH

`webapps/vetclinicsystem_iq-main/app.py:6543` (JO: `app.py:6418`)

`heartbeat.py:26-29` states the ping URL is a credential that is "never written to a log,
never included in an error message, and never returned to a caller." Adding `heartbeat_url`
to the generic settings loop routes it straight through `auth.log_change()`.

**Failure scenario.** An admin pastes `https://hc-ping.com/<uuid>`. `auth.py:403` inserts the
full URL into `audit_log.old_value`/`new_value`. `templates/admin_logs.html:26` renders
`{{ c.old_value }} → {{ c.new_value }}` to anyone holding **`view_logins_changes`** — a
different and broader permission than `manage_settings`. So a user who cannot open Settings
can read the credential off the audit page, and out of any audit export. Holding it lets them
POST fake pings and suppress the alert that fires when the clinic machine goes dark.

`tests/test_heartbeat.py` asserts the URL never escapes `heartbeat.send()`'s return message.
The invariant is tested at one boundary and violated at another.

**Suggested fix.** Skip `heartbeat_url` in the `log_change` loop, or log a redacted marker
(`"set"` / `"cleared"`) — the fact that it changed is the auditable part, not the value.

---

### 2. Windows boot task + Startup folder collide in a 2-second respawn loop — HIGH

`webapps/vetclinicsystem_iq-main/autostart.py:278` (same in JO)

`_windows_enable()` now writes **both** the `ONSTART` Scheduled Task and the Startup-folder
`.bat`. The docstring justifies it: *"the launcher is a supervisor loop, and a second copy
exits immediately because the port is taken."* The second half is true of the **app**; the
supervisor restarts it regardless.

**Failure scenario.** Windows boots → the SYSTEM boot task runs `Start VetClinicSystem.bat`,
which binds port 5050. A user signs in at 08:00 → the Startup-folder `.bat` runs the *same*
supervisor script → its `python.exe app.py` cannot bind 5050 and exits → the launcher's
`:loop` (`setup.py:509-526`) prints `"exited — restarting in 2 seconds"`, waits 2s, retries.
There is no port-in-use check and no exit condition. The result is a console window
respawning the app every 2 seconds for the whole logon session, plus a browser tab, on every
clinic PC where the boot task succeeded.

Before this diff only the Startup folder existed, so the two could never collide. This is new.

**Suggested fix.** Write the Startup-folder entry only when the task could *not* be created
(`if not task_ok:`), and delete it when a later enable does succeed. The stated benefit —
not stranding a boot task nobody remembers — is already covered by `_windows_disable()`,
which queries and removes the task independently.

---

### 3. `startup_catchup` is the one job left on the 1-second misfire default — MEDIUM

`webapps/vetclinicsystem_iq-main/scheduler.py:294` (JO: `scheduler.py:295`)

Every recurring job is added with `misfire_grace_time=MISFIRE_GRACE_SECONDS` (`None`). The
`startup_catchup` `DateTrigger` job is added without it, so it keeps APScheduler's 1-second
default — the exact default the module docstring says *"silently broke the nightly backup on
a real install (2026-08-27)."*

**Failure scenario.** The job is scheduled for `now + 30s`. On a clinic PC at boot — antivirus
scan, Postgres starting, disk contention — the `BackgroundScheduler` thread wakes more than
one second late and APScheduler discards the run. The catch-up backup for the week the machine
was off never happens, and no heartbeat is sent. `scheduler.py:284-287` notes that for a clinic
powering on at 8am and off at 6pm this startup ping is the **only** ping it ever sends, so the
receiver reports the site dead.

`tests/test_scheduler_catchup.py:75` explicitly filters this job out of the misfire assertion:

```python
recurring = [k for k in captured if k.get("id") != "startup_catchup"]
```

so nothing guards the gap.

**Suggested fix.** Add `misfire_grace_time=MISFIRE_GRACE_SECONDS` to the `startup_catchup`
job and drop the filter from the test.

---

### 4. Narrow `except` in `_backup_section` aborts the whole heartbeat — MEDIUM

`webapps/vetclinicsystem_iq-main/heartbeat.py:137`

The first `try` block in `_backup_section` catches `Exception`; the second catches only
`(TypeError, ValueError)`.

**Failure scenario.** The nightly job runs `_do_self_check` → `heartbeat.send_for()`. The
connection has gone stale, or the transaction was aborted by an earlier statement, so
`logic.get_setting(db, "last_verified_restore")` at line 132 raises
`psycopg.InterfaceError`/`OperationalError`. Neither is a `TypeError` or `ValueError`, so it
propagates out of `build_payload` before `send()` is reached; `scheduler.py`'s
`except Exception: pass` swallows it. The install goes silent for the night.

Per the module docstring, the receiver alerts on silence — so a transient DB blip is
indistinguishable from a machine that never came back after a power cut. That is a false page
on the one signal the design says must stay trustworthy.

`install_id()` at line 70 has the same unguarded `get_setting` call.

**Suggested fix.** Widen both to `except Exception`, matching the block above them.

---

### 5. `install_id` returns an id it failed to persist — MEDIUM

`webapps/vetclinicsystem_iq-main/heartbeat.py:87`

The docstring promises *"Generated once, then stable."* On a failing write the rollback at
line 84 discards the value and line 87 returns it anyway, so it is regenerated on every call.

**Failure scenario.** The settings write fails (read-only transaction, disk-full Postgres, an
aborted transaction earlier in the same job). Tonight's payload carries `ABCD1234`; tomorrow's
carries `EF567890`. The receiver keys "which clinic went quiet" on `install_id`
(lines 68-69), so it sees the previous id stop reporting — a dead-machine alert for a machine
that is fine — while an unrecognised new install appears each day and never accumulates enough
history to alert on at all.

**Suggested fix.** Return `None` on a failed write so `build_payload` can omit the field,
rather than reporting an identity that will not be there tomorrow.

---

### 6. Missing `patients` table fails with the detail `"None orphaned"` — LOW

`webapps/vetclinicsystem_iq-main/selfverify.py:169` (JO: `selfverify.py:174`)

When `public.patients` is absent, `orphans` stays `None`. The check correctly fails
(`None == 0` is `False`) but its detail renders as `"None orphaned"` — which reads as a clean
result on a failing check.

**Failure scenario.** A partial or `--table`-filtered dump restores without `patients`. The
`to_regclass` guard at line 165 is false, so line 169 appends `ok=False` with
`f"{orphans} orphaned"`. `verify_latest_backup` records `result="fail"`, detail
`"no orphaned patients: None orphaned"`, and `selfcheck`'s `restore_unverified` finding
surfaces that verbatim on the Dashboard. The admin reads a failure whose stated reason is that
there were no orphans, with no way to reach the real cause.

**Suggested fix.** Branch on `orphans is None` and say the table was missing.

---

### 7. `is_due` comment contradicts its own code and test — LOW

`webapps/vetclinicsystem_iq-main/selfverify.py:351` (JO: `selfverify.py:366`)

The comment says a previous failure is *"worth re-testing on the normal cadence rather than
being retried every single day"*; the next line returns `True` once one day has elapsed —
exactly the daily retry it disclaims. `tests/test_selfverify.py:387`
(`test_a_failure_is_retried_tomorrow_not_today`) asserts the daily behaviour, so **the comment
is the wrong half**, not the code.

**Failure scenario.** A maintainer reads the comment, sees `days >= 1` apparently contradicting
it, and "fixes" it to `>= max_age_days`. A failed verification then retries only after 30 days
instead of the next night — past the useful window before
`selfcheck.RESTORE_VERIFY_MAX_AGE_DAYS` (45) starts warning. The test catches it, but the
comment reads as authority for overriding the test.

**Suggested fix.** Rewrite the comment to describe the daily retry and why it is bounded.

---

### 8. Error names a launcher file IQ never creates — LOW (IQ only)

`webapps/vetclinicsystem_iq-main/autostart.py:276`

The not-found message names `"Start VetClinicSystem IQ.bat"`, but
`_windows_launcher_path()` (line 157) builds `"Start VetClinicSystem.bat"` and `setup.py:611`
writes that name. JO's names match; only IQ diverges.

**Failure scenario.** An admin on an IQ install without the versioned-release layout turns on
autostart, is told to look for a filename `setup.py` never produces, and searches for it in
vain — while the interpolated `{launcher}` path in the same sentence shows the correct name.
The message contradicts itself.

---

### 9. `TASK_BOOT_DELAY` comment states the wrong `schtasks` format — LOW

`webapps/vetclinicsystem_iq-main/autostart.py:102` (same in JO)

The comment documents `/DELAY` as `HHHH:MM`; `schtasks` parses it as `mmmm:ss`. `"0001:00"`
gives the intended one minute only because the two readings coincide at this value.

**Failure scenario.** Postgres proves slow to come up and someone widens the delay to five
minutes. Reading the comment as `HHHH:MM` they write `"0000:05"`, which `schtasks` accepts as
**5 seconds** — shorter than the original and the opposite of the intent.

---

## What was checked and found sound

Recorded so a later session does not re-derive it.

- **IQ/JO money divergence (CLAUDE.md §1, §2.3).** `selfverify.py` correctly asserts opposite
  invariants per app: IQ `double precision` + every non-zero bill a whole multiple of 250 IQD;
  JO `numeric` + `scale(total::numeric) <= 3`. The `::numeric` cast in JO's `scale()` call is
  load-bearing and correctly placed — without it the check raises on the one input it exists to
  catch, turning a `fail` into a `warn`. Nothing else in the new modules touches money.
- **Cross-app port fidelity.** `heartbeat.py` differs only in `APP = "iq"/"jo"`; `scheduler.py`
  only in one comment; `selfcheck.py` only in `consecutive_fail_days`' implementation, which is
  functionally equivalent (JO's `by_day.get(day)` terminates the streak loop identically to IQ's
  `day in by_day and ...`). `autostart.py` differs only in names and paths. `app.py` and the two
  templates are structurally identical changes.
- **Template CSS dependencies.** `.modal-overlay`, `.modal-box`, `--danger-tint`, `--warn-tint`,
  `--warn-ink`, `--muted-tint` all exist in **both** apps' `static/style.css`, so the new
  dashboard modal renders correctly in JO despite the frontend divergence CLAUDE.md §1 warns
  about. The dismissal script is vanilla JS and needs no framework.
- **`reschedule_job` and misfire settings.** APScheduler's `reschedule_job` modifies only
  `trigger` and `next_run_time`, so `misfire_grace_time=None` and `coalesce=True` survive a
  backup-time change in Settings.
- **Timestamp handling.** `backup_log.started_at` is `TEXT` written as naive
  `datetime.isoformat(timespec="seconds")` (`backup.py:555`), so the
  `datetime.fromisoformat` comparisons in `_backup_catchup_due` and `_check_backup_stale`
  cannot hit the naive/aware `TypeError` that a `timestamptz` column would cause.
- **`recent_backups` ordering.** `ORDER BY id DESC` (`backup.py:598`), so
  `_check_backup_failing`'s `recent[:3]` really is the newest three, not the oldest.
- **Schema addition.** `self_check_log` is a new `CREATE TABLE` with its index over a column
  defined in the same statement — correctly avoiding the `apply_schema()` ordering trap called
  out in `RELEASE_WORKFLOW.md` §6.2.
- **`selfverify` guard rails.** The throwaway database is hex-named (no injection surface),
  dropped in a `finally` on every path including timeout, and every check query runs on a
  separate connection that the `with` block closes before the `DROP`. No backup file is ever
  written to or deleted.

## Not reviewed

The ~2,000 lines of new test code were read only where a finding depended on them (findings 3
and 7). A dedicated pass against CLAUDE.md §7.3 — reintroduce each bug, confirm the suite fails,
and check every guard has a control — has not been done here.
