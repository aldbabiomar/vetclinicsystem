# Release draft — IQ 1.11.0 / JO 1.9.0

**Status: DRAFT for review. Not committed to either app.**

Per `RELEASE_WORKFLOW.md` §3–§4 the `CHANGELOG.md` entry and the `VERSION`
bump go in **one commit**, at release time — which is why this sits here and
not in the app repos yet.

- IQ: `1.10.9` → **`1.11.0`**, tag `v1.11.0`
- JO: `1.8.10` → **`1.9.0`**, tag `v1.9.0`

**MINOR** is correct: the only schema change is a new `self_check_log` table,
created by `CREATE TABLE IF NOT EXISTS` through the updater's existing schema
sync. Additive, automatic, no manual admin step.

**Change the date if the release slips.** Dated for 2026-09-02, gated on Test
C's day 3.

## What was deliberately left OUT of `### Fixed`

The monitoring feature and the Settings redesign are **new in this release** —
they have never shipped. Bugs found in them during the soak (the health banner
dismissing itself, the Settings page not shrinking on a phone, the duplicated
backup warning) were never visible to any admin, so listing them would
describe problems nobody had. `RELEASE_WORKFLOW.md` §4: user-facing, not a
commit log dump.

What *is* listed under Fixed is limited to behaviour that shipped in 1.10.9 /
1.8.10 and was genuinely wrong there — chiefly the scheduled-backup misses and
the backup-destination handling.

---

## The entry — identical for both apps except the version number and date

```markdown
## [1.11.0] - 2026-09-02

### Added
- **The app now checks its own health once a day** — that backups are
  actually running and landing where they should, that there is disk space
  left, and that the database is reachable. If something is wrong, a warning
  appears at the top of the Dashboard for anyone who can change Settings. If
  it is still wrong three days running, a pop-up appears at sign-in until it
  is dealt with. Nothing is sent anywhere; this is entirely local.
- **Optional daily status ping, for a clinic you are not sitting in.** Under
  Settings → Remote Monitoring, paste the URL a monitoring service gives you
  (healthchecks.io or similar) and the app pings it once a day with a short
  status. If the machine is switched off, asleep, or the app is not running,
  the ping does not arrive and the service emails you. That is the point:
  it notices the failure the app itself cannot report. Off unless you set a
  URL, and the ping carries no patient, staff or financial data.
- **A monthly proof that a backup can actually be restored.** Once a month
  the app restores its own most recent backup into a temporary database and
  checks what came back — the tables, the records, and that the money column
  survived with the right type. A backup file that looks perfectly fine on
  disk can restore to nothing, and this is the only way to find that out
  before you need it.
- **Start at boot on Windows.** Under Settings → Startup & Shutdown, the app
  can now start when the PC powers on rather than waiting for someone to sign
  in — so an unattended machine still takes its nightly backup.

### Changed
- **The Settings page has been reorganised.** It is now four cards — Clinic
  Settings, Backups & Restore, Updates, and Startup & Shutdown — with related
  fields side by side instead of one per row, so the page is far shorter and
  things are easier to find. Each card's Save button now says what it covers.
- **Phones and tablets are properly supported.** Buttons and form fields are
  now sized for a fingertip on any touch device rather than only below a
  fixed screen width — an iPad in portrait previously got the desktop layout,
  with fields small enough that iOS zoomed in on every tap and did not zoom
  back out.
- **Consistent spacing** between cards on the Dashboard, Insights, Settings
  and every other page that shows them.

### Fixed
- **Nightly backups are no longer skipped when the computer was asleep or
  switched off at the scheduled time.** Previously that backup was silently
  abandoned and nothing ran until the next night — so a machine shut down
  each evening could go a long time between backups without any sign. Missed
  backups now run at the next opportunity.
- **A backup folder that disappears is now reported instead of quietly
  recreated.** If the folder your backups are written to goes away — an
  unplugged external drive, a synced folder that unlinked, a folder someone
  moved — the app used to create a new empty one in its place and carry on
  reporting success, while the copy you were relying on had stopped being
  updated. It now refuses to write and tells you on the Dashboard. It also
  now notices when the most recent backup file is missing from disk.
- **The Settings page and several list pages no longer run off the side of
  the screen** on smaller displays.
```

---

## Release-day checklist (from `RELEASE_WORKFLOW.md` §6)

1. Confirm Test C passed — the day-3 modal was actually seen.
2. Confirm `git remote -v` per app before the first push.
3. `VERSION` + `CHANGELOG.md` in **one** commit, per app.
4. Tag `v1.11.0` (IQ) / `v1.9.0` (JO) — exact format, no exceptions.
5. Release notes = that version's CHANGELOG section, not the commit list.
6. Then, first thing after: `TRANSITION_NOTES.md` §4 item 2 (bound the backup
   retry) and item 3 (port `consecutive_fail_days`).
