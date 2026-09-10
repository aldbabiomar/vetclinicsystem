# Clinic-PC Hosting via Cloudflare Tunnel

Status: **draft for review** — written 2026-08-24, not yet executed.
Re-checked 2026-09-10: still accurate, and still not executed. It cites no
`app.py` line numbers, so the 2026-09-10 blueprint split (`COMPARISON.md`
§49) leaves it untouched. Read `HOSTING_MIGRATION_PLAN.md` first — this is
the alternative to that plan, not a successor to it.
Scope: VetClinicSystem_IQ and VetClinicSystem_JO, each made reachable at a
real public domain **from the clinic's own existing computer** — no VPS, no
port forwarding, no monthly server bill. This is the alternative explored
after `HOSTING_MIGRATION_PLAN.md` (the VPS plan) and after ruling out raw
port-forwarding + dynamic DNS.

Read `HOSTING_MIGRATION_PLAN.md` first if you haven't — this plan reuses
several of its pieces directly (the security fix in §3 below, the off-site
backup reasoning) rather than re-deriving them, and assumes the same
per-app framing: one clinic PC, one tunnel, one domain, run twice (once per
app), not a shared setup.

## What this actually changes vs. raw port-forwarding (the idea from two
questions ago)

Both get the clinic PC acting as the origin server — that part doesn't
change, and neither does the underlying risk profile tied to *that*: the
site is only as available as the clinic's own power and internet, and
public traffic now shares that machine's resources with the front desk's
own LAN use. What the tunnel *does* fix, concretely:

- **No port forwarding, no public IP needed at all** — `cloudflared` makes
  an *outbound* connection from the clinic PC to Cloudflare's edge; nothing
  needs to be opened on the router. Works fine even if the ISP puts the
  clinic behind CGNAT (no real public IP at all), which silently breaks
  raw port-forwarding.
- **The clinic's real IP is never exposed.** Only Cloudflare's edge is
  publicly reachable; the tunnel is the only path in.
- **TLS is Cloudflare's problem, not yours** — no Let's Encrypt renewal to
  babysit on a machine that might be asleep or rebooting at the wrong
  moment.
- **Free**, at the traffic level a single clinic generates.

---

## 1. Prerequisite: the domain's DNS must be on Cloudflare

Cloudflare Tunnel's DNS routing only works for a zone Cloudflare is
authoritative for. This does **not** mean transferring domain
*registration* — just changing the domain's **nameservers** to Cloudflare's
(a standard, free, reversible operation at whatever registrar you bought
the domain from). If the domain is already registered elsewhere, that's
the only change needed at the registrar; everything else below happens in
Cloudflare's dashboard.

If starting from scratch, registering the domain directly through
Cloudflare skips this step entirely.

---

## 2. Per-app variable table

| Placeholder | IQ value | JO value |
|---|---|---|
| `{ENV_PREFIX}` | `VETCLINICSYSTEMIQ` | `VETCLINICSYSTEMJO` |
| `{app_dir_name}` | `vetclinicsystem_iq-main` | `vetclinicsystem_jo-main` |
| `{tunnel_name}` | `vetclinicsystemiq` | `vetclinicsystemjo` |
| `{domain}` | e.g. `vetzone.example.com` | e.g. `dogtopia.example.com` |

---

## 3. Required first — the same code fix as the VPS plan

Both apps have the identical `api_browse_folder` gap documented in
`HOSTING_MIGRATION_PLAN.md` §6: any `manage_settings` user can list *any*
directory on the machine, with no confinement. That gap is unrelated to
*how* the machine becomes reachable — it matters the moment either app is
reachable from the public internet at all, tunnel or VPS. Apply that same
fix, in the same two functions, in each app's repo, before setting up the
tunnel. Not repeating the diff here — see that document's §6 for the exact
code.

---

## 4. Install `cloudflared` on the clinic PC

**macOS:**
```bash
brew install cloudflared
```
(No Homebrew? Download the `.pkg` directly from Cloudflare's
`cloudflared` GitHub releases page instead.)

**Windows:**
```powershell
winget install --id Cloudflare.cloudflared
```
(Or download the MSI installer from the same releases page.)

---

## 5. Create the tunnel — dashboard flow (recommended over the CLI-config
   approach)

Cloudflare offers two ways to set this up: hand-editing a local
`config.yml` + credentials file, or a token-based flow driven entirely from
the dashboard. **Use the token flow** — it sidesteps a real, commonly-hit
Windows gotcha (a `cloudflared` service runs as the SYSTEM account, which
looks for `config.yml` in a *different* folder than the interactive user's
— the token approach has no config file to misplace at all).

1. Cloudflare dashboard → **Zero Trust** → **Networks** → **Tunnels** →
   **Create a tunnel** → connector type **Cloudflared**.
2. Name it `{tunnel_name}`.
3. It gives you an install command with an embedded token, shaped like:
   ```
   cloudflared service install <long token>
   ```
   Copy it — you'll run it in the next step, per OS.
4. Still in the dashboard, add a **Public Hostname**:
   - Domain: `{domain}`
   - Service type: `HTTP`
   - URL: `localhost:5050`
   Saving this **also creates the DNS record automatically** — no manual
   DNS step needed, since the zone is on Cloudflare (§1).

---

## 6. Install the tunnel as a service on the clinic PC

**macOS** (Terminal, needs `sudo`):
```bash
sudo cloudflared service install <token from step 5>
```
Installs a `launchd` daemon — system-level, starts at boot, no user login
required.

**Windows** (PowerShell as Administrator):
```powershell
cloudflared service install <token from step 5>
```
Installs a Windows Service, same system-level behavior.

Verify it's actually running:
```bash
# macOS
sudo launchctl list | grep cloudflared
# Windows
sc query Cloudflared
```

---

## 7. App configuration — `.env` changes, both apps

```bash
BEHIND_TLS_PROXY=1
```

Reasoning is identical to the VPS plan: `cloudflared` terminates TLS at
Cloudflare's edge and forwards plain HTTP to the app locally, setting
standard `X-Forwarded-For`/`Proto` headers along the way — `ProxyFix`
(already in both apps, confirmed in the earlier investigation) trusts
exactly one such hop, and `cloudflared` running on the same machine *is*
that one hop.

**Leave `{ENV_PREFIX}_HOST` as its default (`0.0.0.0`).** Unlike the VPS
plan, this isn't optional here — the app needs to stay reachable two ways
at once: directly over the LAN (front-desk devices, as today, no change)
*and* via `cloudflared` connecting to `localhost:5050` for the public
tunnel. Binding to `127.0.0.1` only would break the existing LAN access
that the front desk still relies on.

Restart the app after this change (however it's normally started/stopped
on that machine — the existing launcher, unchanged).

---

## 8. The autostart / boot-order gotcha — read this before relying on it

`cloudflared service install` runs at the **system** level — it comes up
before anyone logs in. The app's own autostart (`autostart.py`, already
built into both apps) is **user**-level — a `launchd` *Agent* on macOS, a
Startup-folder shortcut on Windows — which only fires once someone actually
logs into that account.

Left unaddressed, a reboot (power blip, Windows update, anything) leaves
the tunnel up but pointing at nothing — visitors get a connection error
from Cloudflare until a person physically logs into the clinic PC.

**Fix: set that account to log in automatically at boot.** Standard OS
setting on both platforms, not app-specific:
- macOS: System Settings → Users & Groups → Login Options → Automatic login.
- Windows: `netplwiz` → uncheck "Users must enter a password" for that
  account (or configure via Settings → Accounts → Sign-in options).

This is a real security tradeoff worth naming plainly: automatic login
means anyone with physical access to that machine is already at the
desktop, no password prompt. On a machine that's meant to be a dedicated,
physically-secured front-desk terminal, that's usually an acceptable
trade for "the site actually comes back up unattended." If that machine
is also used for other things by other people, it isn't — worth deciding
deliberately rather than defaulting into it.

(A more invasive alternative — converting the app itself from its current
"visible terminal window, close it to stop" design into a true background
service — would remove this dependency entirely, but that's a bigger
change than this plan takes on; the app's own launcher comments are
explicit that it's designed to run in a visible window a person can see
and close, not headless. Worth a separate look if this login-dependency
trade turns out to be the wrong one.)

---

## 9. Off-site backups — same reasoning as the VPS plan, still needed

Nothing about running from the clinic PC instead of a VPS changes this:
the DB backup and the `uploads/` folder both still live on one machine's
disk, and a fire/theft/hardware failure at the clinic takes out the live
app and every local backup at once. §11 of `HOSTING_MIGRATION_PLAN.md`
already covers the reasoning and the Backblaze B2 + `rclone` approach —
identical here, just scheduled differently since there's no systemd timer
on a clinic PC:

- **macOS:** a `launchd` user or system agent (plist with a
  `StartCalendarInterval`), or simply a cron entry via `crontab -e`.
- **Windows:** Task Scheduler, a daily trigger ~30 minutes after the
  app's configured `backup_time` setting (default 02:00).

Same script shape as before:
```bash
rclone sync "<current backup_dir>" "b2:{tunnel_name}-backups/db/"
rclone sync "{app_dir_name}/uploads" "b2:{tunnel_name}-backups/uploads/"
```

---

## 10. Monitoring

Same as the VPS plan — the app's own `/health` endpoint already checks
real DB connectivity, not just process liveness. Point a free UptimeRobot
(or similar) check at `https://{domain}/health`. This matters *more* here
than on a VPS: there's no provider-level infrastructure monitoring
underneath a clinic PC, so this external check is the only thing that
would actually notice "the tunnel's up but the app crashed" or "the power
went out" before a customer does.

---

## 11. Verification checklist

- [ ] `https://{domain}` loads with a valid Cloudflare-issued certificate.
- [ ] Front-desk devices on the clinic LAN can still reach the app the
      normal way (`http://<clinic-PC-LAN-IP>:5050`) — confirms §7's
      "leave HOST as 0.0.0.0" didn't regress the existing setup.
- [ ] Log in via the public URL, confirm the session cookie shows
      `Secure` + `HttpOnly` in devtools — confirms `BEHIND_TLS_PROXY=1`
      actually took effect over the tunnel.
- [ ] Reboot the clinic PC. After it comes back: confirm automatic login
      happened, confirm the app's own autostart brought it up, confirm
      `https://{domain}` is reachable again without anyone touching the
      machine. This is the single most important check in this plan —
      it's the failure mode §8 exists to prevent.
- [ ] Attempt `api_browse_folder` outside the allowlist as a
      `manage_settings` user — confirms §3's fix is actually deployed.
- [ ] Confirm the off-site backup task actually ran and landed in B2, not
      just that it's scheduled.
- [ ] Uptime monitor configured and its first check has fired green.

---

## 12. Cost

| Item | Estimate |
|---|---|
| Cloudflare Tunnel | Free at this traffic level |
| Domain (if not already owned) | ~$10–15/yr |
| Backblaze B2 storage | Single-digit $/mo |
| Everything else | Free (uses hardware already owned) |

Meaningfully cheaper than the VPS plan's $15–25/mo across both apps — the
cost being traded away is reliability and isolation, not money.

---

## 13. What this plan deliberately does not fix

Restating this plainly rather than letting the checklist above imply
otherwise:

- **Uptime is still tied to the clinic's own power and internet.** A VPS
  in a datacenter has redundancy this setup never will.
- **Public and LAN traffic still share one machine's resources.** A slow
  moment for a remote request can still be felt at the front desk.
- **This is not a substitute for deciding auto-login's tradeoff in §8**
  — that's a real, deliberate security/convenience call, not a default to
  accept passively.

If any of these turn out to matter more than the cost savings once this
is running, `HOSTING_MIGRATION_PLAN.md`'s VPS approach is the upgrade path
— nothing here is wasted moving to it, since the `.env`/`BEHIND_TLS_PROXY`
/ security-fix work is identical either way.

---

## 14. Order of work

1. §3 — ship the `api_browse_folder` fix to each app's repo.
2. §1 — point the domain's nameservers at Cloudflare (if not already).
3. §4–§6 — install `cloudflared`, create the tunnel, install it as a
   service.
4. §7 — `.env` change, restart the app.
5. §8 — decide and configure auto-login; this is the step most likely to
   be skipped and regretted, so treat it as required, not optional.
6. §9 — off-site backup task.
7. §10 — uptime monitor.
8. §11 — full verification checklist, **including the actual reboot
   test** — don't consider this done until that one has passed.
9. Repeat 2–8 for the second app, on its own clinic PC.
