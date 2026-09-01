# Hosting Migration Plan — Clinic PC → Public Server

Status: **draft for review** — written 2026-08-24, not yet executed.
Scope: VetClinicSystem_IQ and VetClinicSystem_JO, each moved from running on a
clinic's own PC to running on its own hosted VPS, reachable over the public
internet at a real domain. Single-tenant per deployment throughout — this is
*not* a multi-tenant SaaS rework (see the prior conversation on that fork;
this plan is the "same app, hosted remotely" branch).

This plan follows the same discipline as `CLAUDE.md` §2: every claim below is
checked against each app's **actual current code**, cited by file:line, not
assumed from the other app or from generic hosting advice. The good news,
confirmed directly rather than assumed: the hosting-relevant code is
genuinely identical between IQ and JO (verified in §1), so this is one
recipe, followed twice — once per app, each on its own server.

## Decisions (resolved 2026-08-24, before implementation)

Four questions were talked through with the user before writing this plan.
All four went with the recommended option:

| Question | Decision | Where it shows up below |
|---|---|---|
| Scope | **Both apps**, as two identical, independent deployments — one VPS per app, not one VPS shared between them. | Whole document; §3 has the per-app variable table. |
| Hosting model | **Self-managed VPS** (DigitalOcean/Hetzner/Linode-class), not a managed PaaS. Smallest change from what's already built — the app's Docker Postgres + Waitress-behind-a-proxy shape was already designed for exactly this. | §2, §4–§7 |
| Deploy mechanism | **Conventional** — SSH in (or a small CI step), `git pull`, `systemctl restart`. **Not** the in-app updater — confirmed its self-restart supervisor script (`setup.py`'s `enable_updates()`) only generates a macOS `.command` and a Windows `.bat`; nothing Linux-shaped exists today, so keeping it would mean writing a new Linux supervisor loop for a feature a server doesn't need (SSH access already exists). | §9 |
| Off-site backups | **Backblaze B2**, S3-compatible, via `rclone`. | §8 |

---

## 1. What was actually investigated, and what it found

Read both apps' `app.py` (network/session hardening block, error handlers,
the Waitress startup block), `db.py`, `backup.py`, `attachments.py`,
`autostart.py`, `updater.py`, `setup.py`, `docker-compose.yml`,
`requirements.txt`, and `.env.example`, in both repos, before writing
anything below.

**Better starting position than expected.** Both apps already have, verified
identical in both:
- `ProxyFix` applied when `BEHIND_TLS_PROXY=1`
  ([app.py:89](webapps/vetclinicsystem_iq-main/app.py:89) IQ,
  [app.py:107](webapps/vetclinicsystem_jo-main/app.py:107) JO) — correctly
  trusts exactly one proxy hop for `X-Forwarded-For`/`Proto`/`Host`, not a
  blind header trust.
- Hardened session cookies — `HttpOnly`, `SameSite=Lax`, `Secure` tied to
  `BEHIND_TLS_PROXY`, configurable lifetime
  ([app.py:96-105](webapps/vetclinicsystem_iq-main/app.py:96) IQ).
- An optional CIDR allowlist (`VETCLINICSYSTEM{IQ,JO}_ALLOWED_NETWORKS`),
  unset by default — fine to leave unset for a real public site; useful if
  the clinic later wants to restrict to a known office/VPN range.
- A `/health` endpoint ([app.py:1524](webapps/vetclinicsystem_iq-main/app.py:1524)
  IQ, [app.py:6331](webapps/vetclinicsystem_jo-main/app.py:6331) JO) that
  checks real DB connectivity, not just process liveness — built for the
  in-app updater, but exactly what an uptime monitor wants too (§10).
- Graceful `SIGTERM`/`SIGINT` handling that takes a final backup before exit
  ([app.py:6870-6890](webapps/vetclinicsystem_iq-main/app.py:6870)) — this
  is precisely what `systemctl stop` sends, so the existing shutdown code
  needs no change to work correctly under systemd.
- Waitress already binds host/port from env vars and explicitly documents
  that it never terminates TLS itself — "TLS here always means there's a
  reverse proxy in front" ([app.py:6911](webapps/vetclinicsystem_iq-main/app.py:6911)).
- `docker-compose.yml`'s Postgres already binds `127.0.0.1:5432` only, in
  both apps — already correct for a VPS, no change needed.
- `attachments.py`'s `UPLOAD_ROOT` already resolves relative to
  `VETCLINICSYSTEM{IQ,JO}_DATA_DIR` when set
  ([attachments.py:24](webapps/vetclinicsystem_iq-main/attachments.py:24)) —
  pointing that env var at a real persistent path is enough; no code
  change needed to relocate uploads onto a proper disk.
- `RotatingFileHandler` already caps `logs/errors.log`
  ([app.py:262](webapps/vetclinicsystem_iq-main/app.py:262)) — log rotation
  needs no extra tooling at this scale.

**One real gap, confirmed by reading the function, not assumed:**
`api_browse_folder` ([app.py:1706](webapps/vetclinicsystem_iq-main/app.py:1706)
IQ, [app.py:1711](webapps/vetclinicsystem_jo-main/app.py:1711) JO) lets any
`manage_settings` user list **any directory the process can read** —
`requested = request.args.get("path")` → `os.path.abspath(requested)` →
`os.listdir(path)`, with no base-directory confinement at all. On a clinic
PC, "the server" *is* the admin's own computer, so this is harmless. Once
"the server" is a remote box, this becomes a real directory-enumeration
capability reachable by anyone who compromises a Settings-permitted
account. Required fix — §6.

**Confirmed non-issues, so they're not in this plan:**
- `sslmode` for a remote Postgres connection: not a code change —
  `db.py`'s `connect()` builds entirely from `DATABASE_URL`
  ([db.py:56](webapps/vetclinicsystem_iq-main/db.py:56)), and psycopg reads
  `?sslmode=require` straight out of that URL. Only matters if the DB is
  ever moved off the same VPS as the app (not in this plan — see §5).
- `autostart.py` already self-disables outside macOS/Windows
  (`is_supported()` returns `False` on Linux) — nothing to change or
  disable on the server.
- The earlier Docker-terminal-vs-Docker-Desktop question from this same
  conversation doesn't apply here at all: a headless Linux VPS uses native
  Docker Engine, which is what `setup.py`'s `docker`/`docker compose` CLI
  calls already expect — "Docker Desktop" is a macOS/Windows-only concept
  that was never in this VPS's path to begin with.

---

## 2. Target architecture (per app, per VPS)

```
Internet
   │  HTTPS :443
   ▼
┌─────────────────────────────────────────────┐
│  VPS (Ubuntu 22.04/24.04 LTS)                │
│                                               │
│  Caddy  ──reverse proxy──▶  Waitress          │
│  (auto TLS,                 (systemd service, │
│   :80/:443)                  127.0.0.1:5050)  │
│                                     │          │
│                                     ▼          │
│                              Postgres 16       │
│                              (Docker,          │
│                               127.0.0.1:5432,  │
│                               unchanged from    │
│                               docker-compose)   │
│                                               │
│  uploads/, backup_dir  ──▶  local disk        │
│                              (persistent)      │
└──────────────────┬────────────────────────────┘
                    │  nightly, via rclone
                    ▼
              Backblaze B2 (off-site)
```

One VPS per app (IQ and JO each get their own, per the Decisions box) — same
recipe, run twice, with the per-app substitutions in §3.

---

## 3. Per-app variable table

Substitute these consistently through every command/config below.

| Placeholder | IQ value | JO value |
|---|---|---|
| `{ENV_PREFIX}` | `VETCLINICSYSTEMIQ` | `VETCLINICSYSTEMJO` |
| `{app_dir_name}` | `vetclinicsystem_iq-main` | `vetclinicsystem_jo-main` |
| `{service_name}` | `vetclinicsystemiq` | `vetclinicsystemjo` |
| `{repo}` | `aldbabiomar/vetclinicsystem_iq` | `aldbabiomar/vetclinicsystem_jo` |
| `{db_user}` / `{db_name}` | `vetclinicsystemiq` | `vetclinicsystemjo` |
| `{domain}` | e.g. `vetzone.example.com` | e.g. `dogtopia.example.com` |
| `{currency}` | IQD | JOD |

---

## 4. VPS provisioning and OS hardening

1. **Provider/size.** A DigitalOcean/Hetzner/Linode-class box, smallest tier
   with 1GB+ RAM (this app is explicitly sized for "a single-clinic
   deployment" throughout its own code comments — `DB_POOL_MAX_SIZE`
   defaults to 15, Waitress runs 8 threads; a $6–12/mo droplet-class VPS is
   genuinely enough). Region: any is fine functionally for a CRUD web app
   used by a handful of front-desk staff; if minimizing latency to
   Iraq/Jordan specifically matters, AWS `me-south-1` (Bahrain) or Oracle
   Cloud's regional presence are options, at more setup complexity than a
   plain DigitalOcean/Hetzner droplet.
2. Ubuntu 22.04 or 24.04 LTS.
3. Create a non-root sudo user; disable SSH password auth (key-only);
   optionally move SSH off port 22 and/or install `fail2ban` — standard
   practice, not app-specific.
4. Firewall (`ufw`):
   ```bash
   ufw default deny incoming
   ufw allow OpenSSH        # or your custom SSH port
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw enable
   ```
   Deliberately **not** opening 5050 (the app) or 5432 (Postgres) —
   both stay bound to `127.0.0.1` and are reached only via Caddy or from
   the app itself on the same box, matching what `docker-compose.yml`
   already does today.

---

## 5. Postgres

No change from what's already built — this is the one piece that
transfers as-is:

```bash
# on the VPS, inside {app_dir_name}/
docker compose up -d
```

Uses the existing `docker-compose.yml`
([docker-compose.yml](webapps/vetclinicsystem_iq-main/docker-compose.yml)),
already binding `127.0.0.1:5432` only. `DATABASE_URL` in `.env` points at
that same local address, same as a clinic-PC install — no `sslmode` needed
since the connection never leaves the box.

*(Not choosing a managed Postgres here, per the Decisions box's "self-managed
VPS" call — that would be a reasonable later upgrade if this ever needs to
survive a single VPS's disk failure without relying on the B2 backup alone,
but it's out of scope for this pass.)*

---

## 6. Required code fix — confine `api_browse_folder` (§1)

Both apps, same shape. Reuses the exact path-confinement pattern
`resolve_restorable_backup()` already established for restore-file selection
([backup.py](webapps/vetclinicsystem_iq-main/backup.py) — "the file must
resolve, symlinks included, to somewhere inside the currently-configured
backup_dir") rather than inventing a new one:

```python
# app.py, near api_browse_folder()
def _allowed_browse_roots(db):
    """Directories api_browse_folder() may list. A public-facing server
    has no business exposing a full-filesystem directory listing to a
    manage_settings account — confine it to the places this feature
    actually needs to reach: home, the data dir if this install uses the
    versioned-release layout, and whatever backup_dir is already
    configured to."""
    roots = [os.path.expanduser("~")]
    data_dir = os.environ.get(f"{ENV_PREFIX}_DATA_DIR")
    if data_dir:
        roots.append(data_dir)
    configured = logic.get_setting(db, "backup_dir")
    if configured:
        roots.append(configured)
    return [os.path.realpath(r) for r in roots]

def _is_within_allowed(path, roots):
    real = os.path.realpath(path)
    return any(real == r or real.startswith(r + os.sep) for r in roots)
```

In `api_browse_folder()`, after resolving `path`:
```python
if not _is_within_allowed(path, _allowed_browse_roots(db)):
    return jsonify({"error": "That folder is outside the locations this app can browse."}), 403
```

Same guard in `api_browse_folder_new()` (folder creation) — same file,
same confinement check before `os.makedirs`.

Ship this **before** the server goes live, not after — it's a small,
self-contained change with no schema/migration involved.

---

## 7. The app itself — venv, systemd, Caddy

### 7.1 Deploy the code

```bash
git clone https://github.com/{repo}.git ~/{app_dir_name}
cd ~/{app_dir_name}
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
```bash
DATABASE_URL=postgresql://{db_user}:<generated password>@127.0.0.1:5432/{db_name}
POSTGRES_PASSWORD=<same password>
SECRET_KEY=<real random value — setup.py normally generates this>
BEHIND_TLS_PROXY=1
{ENV_PREFIX}_HOST=127.0.0.1
{ENV_PREFIX}_PORT=5050
SESSION_LIFETIME_HOURS=12          # or lower for a public-facing install
```

Deliberately **not** setting `{ENV_PREFIX}_DATA_DIR`/`RELEASES_DIR` or
running `setup.py --enable-updates` — per the Decisions box, this install
stays on the plain-checkout layout and is deployed conventionally (§9), so
the versioned-release machinery (and its macOS/Windows-only supervisor
scripts) simply isn't invoked.

Run first-time setup (schema, seed check, Docker Postgres — same script as
a clinic PC):
```bash
venv/bin/python setup.py --no-enable-updates
```

### 7.2 systemd service

`/etc/systemd/system/{service_name}.service`:
```ini
[Unit]
Description=VetClinicSystem — {service_name}
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=<the non-root deploy user>
WorkingDirectory=/home/<user>/{app_dir_name}
ExecStart=/home/<user>/{app_dir_name}/venv/bin/python app.py
Restart=on-failure
RestartSec=5
# systemctl stop sends SIGTERM — app.py's own graceful-shutdown handler
# (final backup, clean pool close) already does the right thing with it,
# confirmed in §1. No extra ExecStop needed.

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now {service_name}
```

### 7.3 Caddy (reverse proxy + automatic TLS)

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:
```
{domain} {
    reverse_proxy 127.0.0.1:5050
}
```

```bash
sudo systemctl reload caddy
```

Caddy handles the Let's Encrypt certificate issuance/renewal automatically
— no certbot, no manual cert management.

---

## 8. DNS

Point `{domain}`'s `A` record at the VPS's public IPv4 (and `AAAA` if the
VPS has IPv6). Standard TTL. Caddy will start serving HTTPS as soon as DNS
resolves and it can complete the ACME challenge — no other app-side change
needed; `BEHIND_TLS_PROXY=1` already makes the app itself proxy-aware (§1).

---

## 9. Deploy workflow (conventional, per the Decisions box)

Manual, for the first deploy and any time after:
```bash
ssh <user>@{domain}
cd ~/{app_dir_name}
git pull
venv/bin/pip install -r requirements.txt    # only does anything if requirements.txt changed
sudo systemctl restart {service_name}
curl -s http://127.0.0.1:5050/health        # confirm it came back up
```

Optional upgrade, not required for going live: a small GitHub Actions
workflow that SSHes in and runs the same four commands on push to `main` or
on a tag, matching the cadence `RELEASE_WORKFLOW.md` already documents for
tagging a release — worth doing once the manual flow above has been
exercised a few times, not before.

---

## 10. Monitoring

- **Uptime check** against the app's own `/health` endpoint — it already
  checks real DB connectivity, not just "the process is up"
  ([app.py:1524](webapps/vetclinicsystem_iq-main/app.py:1524)). A free tier
  of UptimeRobot (or similar) hitting `https://{domain}/health` every few
  minutes, alerting by email/SMS on a non-200, closes the gap that used to
  be "a receptionist notices the window is closed."
- **systemd's own `Restart=on-failure`** (§7.2) handles a crash without
  anyone needing to notice at all, most of the time.
- **`logs/errors.log`** (`RotatingFileHandler`, already capped) is where to
  look first if the uptime check fires.

---

## 11. Off-site backups → Backblaze B2 (per the Decisions box)

The app already runs its own nightly `pg_dump`-based backup into whatever
local `backup_dir` is configured in Settings (`backup.py`, unchanged by this
plan) — but a backup sitting on the same VPS disk as the database it backs
up isn't a real backup once there's no separate physical clinic PC's worth
of redundancy behind it. And `uploads/` is explicitly **not** covered by
that DB backup at all (same gap this codebase's own README already states
for the clinic-PC install).

1. Create a Backblaze B2 bucket + application key, one per app (or one
   bucket with `{service_name}/` prefixes for both).
2. Install `rclone` on the VPS, configure a B2 remote (`rclone config`).
3. A small sync script, `~/bin/offsite-sync-{service_name}.sh`:
   ```bash
   #!/bin/bash
   set -euo pipefail
   rclone sync "$(cat /path/to/current-backup-dir)" "b2:{service_name}-backups/db/"
   rclone sync ~/{app_dir_name}/uploads "b2:{service_name}-backups/uploads/"
   ```
4. A systemd timer running this ~30 minutes after the app's own configured
   `backup_time` setting (default 02:00, so e.g. 02:30) — timer unit
   mirrors the standard systemd `.timer`/`.service` pair pattern, not
   reproduced in full here since it's boilerplate, not app-specific.
5. **Extend the monthly restore drill** (`CLAUDE.md` §6,
   `scripts/restore_drill.sh`) to periodically pull the *B2 copy* down and
   drill against that, not only the local file — the existing drill only
   proves the local backup restores; it says nothing about whether the
   `rclone sync` itself has been silently failing.

---

## 12. Verification checklist before calling this live

- [ ] `https://{domain}` loads, shows a valid cert (not self-signed/Caddy's
      internal one — confirms ACME actually completed).
- [ ] Log in, confirm session cookie has `Secure` + `HttpOnly` set (browser
      devtools) — confirms `BEHIND_TLS_PROXY=1` actually took effect.
- [ ] `curl -I http://{domain}` (plain HTTP) redirects to HTTPS — Caddy's
      default behavior, worth confirming rather than assuming.
- [ ] `systemctl stop {service_name}` — confirm a backup log entry appears
      (`backup_log` table, `triggered_by='shutdown'`) before the process
      exits, proving the graceful-shutdown path (§1) works under systemd,
      not just under a `Ctrl-C`'d desktop session.
- [ ] `systemctl restart {service_name}` after killing the process
      (`kill -9`) — confirm `Restart=on-failure` actually brings it back.
- [ ] Attempt `api_browse_folder` against a path outside the allowlist
      (e.g. `/etc`) as a `manage_settings` user — confirm the §6 fix
      rejects it with a 403, not a directory listing.
- [ ] Confirm the nightly backup lands locally, then confirm the offsite
      sync timer actually pushed it to B2 (check the bucket, not just that
      the timer "ran").
- [ ] Run `scripts/restore_drill.sh` against a backup pulled *from B2*
      specifically, per §11's last point.
- [ ] Uptime monitor is actually configured and its first check has fired
      green.

---

## 13. Rough monthly cost

| Item | Estimate |
|---|---|
| VPS (per app) | $6–12/mo |
| Domain (per app, if not already owned) | ~$10–15/yr |
| Backblaze B2 storage | Typically single-digit $/mo at this data volume (a single clinic's DB dumps + uploads) |
| Caddy, systemd, ufw, rclone | Free |

Two apps, two VPS's: roughly $15–25/mo total, plus whatever domains cost.

---

## 14. Order of work

1. §6 — ship the `api_browse_folder` confinement fix to each app's repo
   first; it's small, self-contained, and should land before either app is
   reachable from the public internet.
2. §4 — provision the VPS, OS hardening, firewall.
3. §5 — Postgres via existing `docker-compose.yml`, unchanged.
4. §7 — venv, `.env`, systemd, Caddy.
5. §8 — DNS, confirm HTTPS.
6. §11 — off-site backup sync, then run the extended restore drill once
   before considering backups "real."
7. §10 — uptime monitor.
8. §12 — full verification checklist.
9. Repeat 2–8 for the second app, on its own VPS.

---

## 15. Explicitly not in this plan

- Multi-tenancy — out of scope per the earlier conversation; this is two
  single-tenant deployments, not a shared platform.
- Porting the in-app updater to Linux — per the Decisions box, deliberately
  skipped in favor of conventional deploys.
- Managed Postgres — possible later upgrade, not needed for this pass
  (§5).
- CI-triggered auto-deploy — mentioned as an optional follow-up in §9, not
  required to go live.
