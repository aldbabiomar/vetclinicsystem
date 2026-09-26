# Release workflow — VetClinicSystem

## Why this file exists

VetClinicSystem has an in-app updater (`updater.py`) that pulls a **specific,
named GitHub Release** and applies it to a live clinic install. It only works
if every release follows the exact same naming, tagging and structure — the
updater does not guess, it trusts the format. This document is that format.
Follow it exactly whenever asked to "ship", "release" or "push an update".

If something the owner asks for in the moment conflicts with this process,
flag the conflict and ask before deviating: a malformed release can silently
break a clinic's ability to update.

**Nothing is released until the IQ/JO merge is complete and verified under
both money settings** (`docs/plans/UNIFIED_CODEBASE_PLAN.md` §12). The first
release is `1.0.0`.

---

## 1. Repo identity

| | |
|---|---|
| Repo | `aldbabiomar/vetclinicsystem` (public) |
| `.env` / `.env.example` `GITHUB_REPO` | `aldbabiomar/vetclinicsystem` |

One repository, one `VERSION`, one `CHANGELOG.md`, one release stream — for
every clinic, whichever money setting (IQ or JO) it runs. A release must work
under **both** money settings; there is no such thing as an IQ-only or JO-only
release.

Before the first push of a session, confirm `git remote -v` points at
`aldbabiomar/vetclinicsystem`. Never push to a fork or a scratch repo "just for
now" — installs are hard-wired (through `.env`) to this one.

---

## 2. Branching

- **`main` is always deployable.** A tagged release is just "main at this
  commit, named and published".
- Work directly on `main` for normal changes. A short-lived branch only for
  something genuinely risky; merge and delete it promptly.
- **Never force-push `main`**, never rewrite pushed history. Fix forward.

---

## 3. Versioning

Strict [Semantic Versioning](https://semver.org), `MAJOR.MINOR.PATCH`:

- **PATCH** — bug fixes, no schema change, nothing a user would call "new".
- **MINOR** — new features and **additive** schema changes (new tables,
  columns with defaults, new indexes), backward-compatible.
- **MAJOR** — anything that needs the admin to do something by hand, or a
  destructive/type-narrowing schema change. Should be very rare.

*Precedent (from the predecessor apps):* a backfill plus a new constraint,
with no data loss and no manual step, counts as additive → MINOR, with the
tightening spelled out in the CHANGELOG so the admin sees it before updating.
Still flag it, and still verify the migration on a database built by the
previous release first.

The version lives in **one place**: `VERSION` at the repo root, containing
only the number (`1.0.0`, no `v`). The app reads it at boot; it must match the
release tag exactly (tag `v1.0.0` ↔ `VERSION` `1.0.0`) or the updater's
validation refuses the release.

---

## 4. CHANGELOG.md

[Keep a Changelog](https://keepachangelog.com) style, newest at the top, a new
entry **in the same commit** as the `VERSION` bump:

```markdown
## [1.0.1] - 2026-10-02

### Fixed
- Refunds on a cash sale now round down to the smallest cash unit under the IQ
  money setting.
```

`### Added` / `### Changed` / `### Fixed` / `### Removed` as needed. Entries
are user-facing: this text is shown to the clinic admin before they click
Update Now. Say which money setting a change affects when it affects only one.

---

## 5. Commit messages

Lightweight [Conventional Commits](https://www.conventionalcommits.org)
prefixes: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`. One logical
change per commit.

---

## 6. The release checklist — every time, in order

1. **The full suite passes under BOTH money settings**, database and browser
   tiers included (`CLAUDE.md` §5):

   ```bash
   scripts/isolated_test_env.sh up iq && scripts/isolated_test_env.sh up jo
   APP_URL=http://127.0.0.1:5091 TEST_DATABASE_URL=postgresql://postgres:test@localhost:55491/vetclinicsystem \
     /tmp/vcs_test_venv_iq/bin/python -m pytest tests/ -q
   APP_URL=http://127.0.0.1:5092 TEST_DATABASE_URL=postgresql://postgres:test@localhost:55492/vetclinicsystem \
     /tmp/vcs_test_venv_jo/bin/python -m pytest tests/ -q
   ```

   A bare `pytest tests/ -q` **skips** every database test and passes in
   seconds — which looks identical to a real run. Read the skip count. For a
   behavioural fix, verify live in the throwaway environment first.

2. **Schema changes are new migrations, never edits to old ones.** After
   `1.0.0` ships, every schema change is a new numbered file under
   `migrations/`; a published migration is never edited, because installs
   have already recorded it as applied. Each migration runs once, in its own
   transaction — if it fails, the update fails and rolls back, so it must be
   proven against a database built by the previous release
   (`tests/test_migrations.py`). Destructive or type-narrowing changes are
   MAJOR and need a manual note in the CHANGELOG.

   *(Until `1.0.0` is published, `migrations/0001_baseline.sql` may be edited
   in place — there is no install that has applied it.)*

3. **Bump `VERSION`** per §3.
4. **Add the `CHANGELOG.md` entry** per §4, dated today.
5. **Commit both together**: `chore: release v1.0.1` — never split, so the
   updater never sees the two disagree.
6. **Push `main`**: `git push origin main`.
7. **Tag**, annotated, exactly `v` + `VERSION`:
   ```bash
   git tag -a v1.0.1 -m "v1.0.1"
   git push origin v1.0.1
   ```
8. **Publish a GitHub Release from that tag**, body = that version's CHANGELOG
   entry (not GitHub's generated notes — the admin reads this):
   ```bash
   gh release create v1.0.1 --repo aldbabiomar/vetclinicsystem --title "v1.0.1" \
     --notes-file <(sed -n '/## \[1.0.1\]/,/## \[/p' CHANGELOG.md | sed '$d')
   ```
9. **Verify it is what the updater expects**: `GET
   /repos/aldbabiomar/vetclinicsystem/releases/latest` returns `tag_name`
   exactly `v1.0.1`, not a draft or prerelease, with a source tarball.

---

## 7. Hard rules

- Never publish without bumping `VERSION` in the same commit.
- Never tag a commit not yet pushed to `main`.
- Never reuse or move a published tag (`git tag -f`) — publish a new PATCH.
- Never mark an unready build as the latest release — use a draft or
  prerelease; the updater only ever asks for `/releases/latest`.
- Never include a destructive schema change in a MINOR or PATCH.
- Never skip the CHANGELOG entry.
- Never ship a test-only or docs-only change as a release — commit it to
  `main`; a clinic should not be prompted to update for something it cannot
  see.
- The updater offers a release only if its tag is **strictly newer** than the
  running version (`updater.is_update_available()` compares version tuples).
  Never republish an older number as "latest".

---

## 8. Hotfix flow

Same checklist, smaller: fix on `main`, PATCH bump, one-line `### Fixed`
entry, then steps 5–9 unchanged. Do not bypass the tag/release path under
time pressure — the updater's rollback safety net only protects a version it
installed itself.

---

## 9. How the consumer side works (reference)

On a clinic machine, after `python3 setup.py --enable-updates`:

```
vetclinicsystem-data/          never touched by updates
  .env                         DATABASE_URL, SECRET_KEY, GITHUB_REPO, …
  logs/, uploads/, backups/
  active_release.txt           e.g. "app_v1.0.0"
vetclinicsystem-releases/
  app_v1.0.0/                  current
  app_v1.0.1/                  after an update; the previous one is kept for rollback
```

Environment: `VETCLINICSYSTEM_DATA_DIR`, `VETCLINICSYSTEM_RELEASES_DIR`, set by
the launcher that `setup.py` writes into the data directory.

`updater.py`: asks `GET /repos/{GITHUB_REPO}/releases/latest`; backs up the
database (`backup.py`); downloads the tarball into a new release folder
(extracted with `filter="data"`); validates it (`VERSION` matches the tag,
`run.py` and the schema files are there); builds that release's own venv and
builds its app (`create_app()`) there; applies its schema
(migrations); flips `active_release.txt`; restarts; health-checks `/health`.
If the health check fails it flips back and restarts the previous release —
the pre-update backup means nothing is lost either way. Only the last two
releases are kept on disk.

Settings → Updates is admin-triggered only, never automatic, and shows the
release body (the CHANGELOG entry) before the admin confirms.

---

## 10. Quick reference

| Thing | Format | Example |
|---|---|---|
| `VERSION` | `MAJOR.MINOR.PATCH` | `1.0.1` |
| Tag / release title | `v` + VERSION | `v1.0.1` |
| Release notes | that version's CHANGELOG section | §4 |
| Release commit | `chore: release vX.Y.Z` | `chore: release v1.0.1` |
| Branch | `main` only | — |
| Repo | `aldbabiomar/vetclinicsystem` | — |
