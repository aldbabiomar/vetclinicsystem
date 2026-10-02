# VetClinicSystem — clinic management system

> One system, for any clinic, with one **money setting** — IQ (Iraqi dinar:
> whole dinars, cash rounded to the 250-dinar note) or JO (Jordanian dinar:
> three decimals, exact to the fils) — chosen by the vendor when the clinic is
> installed. It replaced the two predecessor apps, VetClinicSystem IQ and
> VetClinicSystem JO.


A full clinic management system for veterinary clinics: patient records,
visits, inpatient care, boarding, wellness & grooming tracking,
appointments, a point of sale, inventory & ordering, distributor and
consignment tracking, billing & refunds, a rewards card, a cash register,
financial reporting, and business-intelligence dashboards — running entirely
on one computer in the clinic, reachable from any device on the clinic's WiFi,
in **English or Arabic** (a clinic setting). It updates itself in-app from the
vendor's releases, with an automatic pre-update backup and one-click rollback,
and watches its own health: a daily self-check, nightly backups that are
test-restored every month, and an optional daily status ping to the vendor.

Each clinic has its own install, its own database and its own license.

## Status

| | |
|---|---|
| **The app** | Built: the IQ and JO predecessor apps merged into this one system (2026-09-27), then licensing, the vendor's Developer area and native PostgreSQL (2026-09-30). The full test suite passes under both money settings. |
| **Licensing** | Signed license keys, checked offline; read-only after the license and its grace period run out. The vendor issues licenses from the **Vendor Console** (below), and a new clinic is set up with one setup code. |
| **First release** | `1.0.0` is **not published yet**. Before it: make the repository private, put the vendor's real signing key into the code, create a GitHub token per clinic, and run one real update through such a token (`docs/plans/DEVELOPER_AND_LICENSING_PLAN.md` §18). |
| **Arabic** | Complete, but written without a native speaker's review: `docs/ARABIC_REVIEW.md` lists every string for the clinic to confirm. |

Everything lives in a **PostgreSQL** database — in Docker on the same
computer, or a PostgreSQL server installed on it (native mode) — so multiple
staff can safely use the app at the same time. No internet connection or cloud
account is needed day to day; internet is used only for updates and, if the
vendor turns it on, a daily status ping.

## Installing (the vendor does this)

A clinic is installed by its vendor. For a new clinic the vendor brings **one
setup code** from the Vendor Console: it carries the clinic's license, money
setting, color palette and name, and its update token. Setup asks for it and
needs nothing else. Setup does not finish without a valid license (there is no
trial); without a setup code it prints this installation's ID for the vendor to
sign a license key for, and asks for that key.

**One-time only:**
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (free) and open it once so it finishes starting up — or, to run without Docker, a PostgreSQL 16+ server on this computer (`docs/NATIVE_POSTGRESQL.md`).
2. **macOS:** double-click `Start VetClinicSystem.command` (first time, macOS will refuse to open it — right-click → **Open** → **Open** again; you only need to do this once).
   **Windows:** double-click `Start VetClinicSystem.bat`.

That single script creates the Python environment, installs dependencies,
starts PostgreSQL, sets up the database, and asks for the setup code. Every run
after that just starts the app and opens it in your browser.

**Manual setup**, if you'd rather run it yourself:
```bash
cd vetclinicsystem
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 setup.py --setup-code '<the setup code>'    # Docker: starts PostgreSQL, builds the schema
python3 run.py
```

Native PostgreSQL instead of Docker (the role and the commands for each
platform are in `docs/NATIVE_POSTGRESQL.md`):
```bash
python3 setup.py --db-mode native \
    --database-url postgresql://vetclinicsystem:PASSWORD@127.0.0.1:5432/vetclinicsystem \
    --setup-code '<the setup code>'
```

A clinic set up without a setup code takes `--money-setting IQ|JO` and
`--license-key '<the key>'` instead. Without a money setting, the vendor
chooses it later in the Developer area; until then billing, payments, the point
of sale and the price list stay locked. It locks itself once the first price or
amount is recorded.

Open **http://127.0.0.1:5050** on the server machine — or the address setup
printed, if 5050 was already taken on this computer: setup then gives the app
the next free port (and, in Docker mode, the database likewise, from 5432) and
writes both into `.env`, which the launchers and the Desktop shortcut read.

## Using it from other devices on the clinic network

The app binds to the network, not just the one computer, so any phone,
tablet, or laptop on the same WiFi can reach it. Once running, the exact
address to use is shown on the **Dashboard** and **Settings** pages to admins
(something like `http://192.168.1.X:5050`) — type that into a browser on any
other device. The computer running `python3 run.py` is acting as the server,
so it needs to stay on and running during clinic hours for other devices to
reach it. macOS may prompt to allow incoming connections the first time —
click **Allow**.

## First login

- Username: `admin`. The password is the one-time password `setup.py` printed
  at the end of setup. Lost it before signing in? Run `python3 setup.py` again
  and it prints a new one — until the first sign-in, never after.
- You'll be forced to set a new password immediately — do this first, before
  creating other staff accounts.
- Create accounts for your team under **Admin → Users**, assigning each
  person a role.

## Roles & permissions

Three roles come pre-configured — **Admin**, **Vet**, **Reception** — but
roles aren't fixed: **Admin → Roles & Permissions** can create any number of
custom roles (e.g. "Practice Manager", "Groomer"), each with its own name,
its own discount cap (0–100%), and its own checkbox-by-checkbox set of ~28
individual permissions spanning Patients & Visits, Inpatient, Inventory,
Sales & Billing, Consignment, and Admin. A role can also be flagged "can be
assigned as a vet," which is what makes it selectable in every vet picker
across Appointments, New Visit, Grooming, and Inpatient.

The three built-in roles seed with sensible defaults:

| | Admin | Vet | Reception |
|---|---|---|---|
| Everyday clinical/front-desk work | ✔ | ✔ | ✔ |
| Discount cap on any bill | 25% | 15% | 10% |
| Price List, Refunds, Cash Register (view/edit) | ✔ | — | — |
| Financial Reports, Insights & Retention | ✔ | — | — |
| Settings, backups, data export, updates | ✔ | — | — |
| User & Role management | ✔ | — | — |
| Logins and Changes (audit trail) | ✔ | — | — |
| Consignment settlements | ✔ | — | — |
| Mark a vet/groomer unavailable | ✔ | — | ✔ |

Vets and Reception can still see prices while billing (a read-only picker
appears right on the Visit/Inpatient billing panel) even without Price List
access — only the Price List *editing* page itself is gated.

## What's in each part of the app

**Dashboard** — patients, active cases, follow-ups due, reminder calls,
wellness reminders due, grooming queue, low stock, audit/expiry alerts.
Admins (or any role with the right permissions) additionally see a
**missed-items panel** (any follow-up, wellness reminder, or
Lost-to-Follow-Up case that's gone 2+ weeks past its deadline without
action, with the responsible staff member named) and a reminder to enter
this month's operating costs before the month closes.

**Owners & Patients** — one owner can have multiple patients. Patients are
sortable by ID, animal name, species, or owner. Each patient has a full
**History** page (every visit, inpatient stay, and boarding stint, merged
and dated) and two PDF exports: the clinical file, and the billing history.

**Visits** — the single record for an encounter. New Visit branches into
"existing patient" (live search by name/ID/owner/phone) or "new patient"
(owner + patient intake in one form — automatically linked to an existing
owner instead of duplicated if the phone number's already on file). A visit
can carry, all at once: the clinical exam/treatment notes, a follow-up, a
wellness reminder, and a grooming request — since a pet's single visit is
often "checkup + vaccine + a bath" together, these all live on the same
visit rather than being split into separate records. Case status is one of:
Needs Filling, Ongoing, Admitted to Inpatient, Deceased/Euthanized, Lost to
Follow Up, Resolved, Referred. Visits are sortable by date (default), type,
status, or payment, and filterable to a specific date.

**Follow-ups / Wellness / Grooming** — three tabs, each reading straight off
the Visits table:
- *Follow-ups*: method (Physical Visit / Phone Call), reason, status.
- *Wellness*: reminders start 5 days before the next-dose date; flagged
  missed at 2+ weeks overdue if not marked contacted.
- *Grooming*: a working queue (Waiting → Ongoing → Finished) with admitted
  items and contacted status.

**Inpatient** — its own case record (separate from, but linked back to, the
originating visit): presenting complaint, exam findings, a daily update log
(with a "last 3 days" quick view), a contact log (same), a billing tab
(check off procedures used, enter quantity), attending/supervising vet,
admission/dismissal, its own discount + payments, file attachments
(X-rays, bloodwork), and a PDF export.

**Boarding** — a separate kennel/pet-boarding module: entry/exit dates,
an incident log for anything worth noting during the stay, its own billing
and payments, a dismiss workflow, and a PDF export. Boarding stays show up
on the patient's merged History alongside their visits and inpatient cases.

**Appointments** — a week of day-tabs; pick a day to see the booking grid
(one column per active Vet plus one Grooming column, rows generated from the
start time/end time/slot length you set in Settings, auto-lettered A, B, C…).
Double-booking the same vet (or Grooming) into the same slot is blocked
automatically. Admin or Reception can mark a specific vet or Grooming
unavailable for a specific day, which greys out just that column. Booking
doesn't require an existing patient record — it's a scheduling aid; the real
Visit gets created normally when the patient actually arrives.

**Point of Sale** — scan a barcode or search by name to ring up **Retail**
items only; stock deducts in real time, with a fixed per-cart-load token
that stops a double-click on "Complete Sale" from ever ringing up the same
cart twice. **Medicine** billed on a Visit is priced but does *not* touch
inventory (since it's billed by range, not exact dispensed amount) — only
Retail/POS sales move stock.

**Inventory** — several linked pieces:
- *Price List* (Service / Medicine / Retail) and *Inventory Catalog*
  (Medical / Retail) are separate: what you charge vs. what you stock.
- *Audit History* is a whole-catalog counting session: walk the shelf, fill
  in every item's count in one table, **Save** as a draft to finish later,
  or **Confirm** to lock it in permanently (irreversible, with a warning).
  Only Confirmed audits count toward *Inventory Status* and the *Ordering
  Sheet* — a Draft is just a mid-shift checkpoint. Leaving a column blank on
  a new audit means "keep whatever was set last time" for that item
  (threshold, critical flag, target coverage).
- Barcodes: either scan/type in a real one from the item's own packaging,
  or generate one for an item that doesn't have a manufacturer barcode —
  never both at once. Print a single label, or bulk-print labels for every
  item this app generated a barcode for.

**Distributors & Consignment** — track suppliers, log bills owed to them and
payments made, and export a distributor statement to PDF. Retail items can
be flagged **Consignment** (owned by the distributor until sold, not the
clinic) instead of clinic-owned stock — the Consignment area tracks
receiving, shrinkage, and returns for those items separately, shows a live
shelf-stock-and-amount-owed overview per distributor, and records
settlements when a distributor is paid out.

**Billing** — Automatic (priced line items, computed from what's actually
checked off) or Manual (one lump amount, exported on PDF as a single
"Veterinary Services" line) — your choice per visit or inpatient case.
Payment status (Unpaid / Partially Paid / Fully Paid) is computed from
actual payments recorded, not typed in by hand. Cash totals follow the money
setting: exact to the fils under JO; under IQ, rounded to the 250-dinar note
and never down to free. **Clean Up** lets staff write off a small leftover
at payment time, capped per bill, and every bill's total is stored so the
reports read the same figure the bill shows.

**Rewards card** — a member percentage off the eligible lines of a bill, for
owners holding a card, with its rate and term set in Settings.

**Refunds** — separate retail (against a specific POS sale, restocking
optional) and service (against a visit or inpatient case's payments) refund
flows, each capped against what was actually paid so a refund can never
exceed real money taken in.

**Cash Register** — a daily ledger of everything that moved cash in or out
(sales, payments, payouts, refunds), a payout tool for cash leaving the
drawer for a reason, and an end-of-day audit that compares the ledger's
expected total against a physical note count.

**Monthly & Yearly P&L / Operating Costs** — revenue from both visit billing
and POS sales, COGS from measured stock usage, editable monthly operating
costs, month-over-month and year-over-year % change (green = up, red =
down).

**Insights** — a business-intelligence dashboard computed across up to 12
months of history in parallel: revenue by category, vet performance, top
client value, weekday appointment load, inpatient/boarding occupancy,
payment-method mix, and Cash Register health.

**Retention** — a cohort retention grid showing how many clients from each
month's first visit came back in each following month.

**Logins and Changes** (audit trail) — pick a date on the calendar to see
every login attempt (who, when, IP, device/browser) and every data change
(who, what record, old value → new value) on that day.

**Settings** — clinic name and location; language (English or Arabic) and
time zone; numeric thresholds (audit-overdue days, expiry-soon days,
appointment slot length); the rewards card's rate and term; nightly backup
folder, time, and retention (with an in-app folder browser to pick or create
the backup destination), Back Up Now and restore; the daily self-check;
starting the app automatically when this computer starts; **in-app updates**
— check for a new version, apply it (automatic pre-update backup, progress
shown step by step), or roll back to the previous release with one click;
**License**, to enter a new key; and **Data Export**. The money setting and
the color palette are shown but set by the vendor.

## Security & hardening

Runs safely as a normal LAN app out of the box, with several things opt-in
for a deployment that needs them: CSRF protection on every form, a
Content-Security-Policy header, per-IP and per-account login rate limiting
with an escalating lockout, session invalidation on password change,
configurable session lifetime, an optional network allowlist (restrict which
client IPs can reach the app at all), and optional reverse-proxy/TLS
awareness for a deployment that puts one in front. All of this is
environment-variable driven — see `.env.example` for the full list — and
none of it changes default behavior for a normal single-router clinic LAN
unless explicitly configured.

## A few judgment calls made during the build

- **Grooming lives on the Visit record itself**, not a separate table,
  since a single visit is often several things at once for the same
  patient.
- **File uploads (X-rays, bloodwork, etc.)** are keyed by patient ID +
  visit/case ID on disk (`uploads/<patient_id>/<record_id>/…`), not by
  date, since two records can share a calendar date for the same patient.
  Only the file path is stored in the database — the files themselves stay
  on disk, so the database doesn't balloon in size.
- A web app can't pop open your Mac's actual Finder — the folder-picker
  fields (e.g. choosing a backup destination) use an in-app file browser
  instead, with the same practical result.

## Nightly Backups

Set a backup folder on the **Settings** page (any path on this computer —
an internal folder, an external drive, a mapped network share, or a synced
folder like Google Drive/OneDrive all work). Every night at the time you
choose, the app runs a full database backup into that folder, deletes
backups older than the number you choose to keep, and shows the result on
Settings (and warns on the Dashboard if a backup fails or goes stale). You
can also click **Back Up Now** any time, or restore from a backup file
straight from the Settings page.

To restore a backup manually (only needed if you're recovering from a
serious problem outside the app):
```bash
pg_restore --clean --if-exists -d "$DATABASE_URL" path/to/vetclinicsystem_backup_XXXXXXXX_XXXXXX.dump
```

## Staying up to date

Updating is the vendor's job, not the clinic's. **Developer → Updates** (which
opens with a Developer Pass) checks for, applies and rolls back updates
without a terminal (setup puts every new install on the versioned-release
layout this needs). Applying an update backs up the database first, downloads
and validates the new release, applies its database changes, and switches
over — with the previous release kept so a one-click rollback is always there.
The clinic's own Settings page has no update controls.

The releases are in a private repository: each clinic's install reads them
with its own read-only access token, which the vendor sets on the same page.
With no token, Updates says so; a revoked one stops that clinic's updates and
nothing else.

## The license

The vendor's license key says how long this install is licensed for. Before
it runs out, whoever can change Settings sees a warning (14 days ahead, unless
the key says otherwise); after it runs out there is a grace period (14 days),
with a banner for everyone. Then the system becomes **read-only** — from the
next sign-in, never in the middle of someone's work:

- every record can still be viewed, searched, printed and exported; backups,
  restores and updates still run; users can still be managed and passwords
  changed; notes can still be added on animals already admitted;
- nothing else can be saved, payments included.

A new key, entered on **Settings → License**, ends read-only at once for
everyone. The key is kept in the data folder (`license/license.key`), not in
the database, so restoring an older backup never brings back an older license,
and backups and exports never carry it.

**The Developer area** (`/developer/`) is the vendor's: it opens with a
Developer Pass signed for this install for a few hours, never with a password
or a role — the clinic's administrator cannot reach it. Everything the vendor
does there is listed under **Logins and Changes → Developer Audit**, which
nothing deletes.

## For the vendor

- **The Vendor Console** (`python scripts/vendor/console.py`) runs on the
  vendor's own computer only, at `http://127.0.0.1:5099`. It makes the signing
  key the first time, then keeps the list of clinics and where each license
  stands, makes a new clinic's setup code, signs renewals (prefilled a year on)
  and Developer Passes. The key is unlocked with its passphrase and held only
  in memory.
- **The Developer area** of each clinic's app (`/developer/`, opened with a
  Developer Pass): the license, system health, updates and the clinic's token,
  a support bundle, restoring the administrator's access, the money setting and
  palette, monitoring, a message to the clinic, and the data export.
- `docs/DEVELOPER_GUIDE.md` covers both, the signing key's custody, and the
  command-line tool (`scripts/vendor/vcs_vendor.py`) that does the same work.

## Running on multiple computers / higher traffic

This runs comfortably for a single clinic's simultaneous staff on one
server machine. If you ever need to move the database to its own server,
just point `DATABASE_URL` in `.env` at that server instead of the local
Docker container — nothing else in the app needs to change.

## How the code is organised

Everything is in the `vcs/` package; `run.py` starts it.

```
vcs/config.py       .env and the settings read from the environment
vcs/money.py, clock.py, auth.py, ...   the rules every part shares
vcs/db/             the connection pool and the numbered schema migrations
vcs/domain/         the queries and calculations (no Flask)
vcs/web/            the request layer: factory.py (create_app), hooks.py,
                    errors.py, templating.py, core.py (the blueprints' shared
                    seam: get_db(), the parsers and validators, the MAX_*
                    bounds, the shared exception types), nav.py
vcs/web/blueprints/ one per area: main, reports, settings, admin, clinical,
                    sales, inventory, consignment, developer
vcs/licensing/      checking a signed license or Developer Pass; the license's state
vcs/ops/            backups, the updater, the scheduler, self-checks, the one
                    finder of the PostgreSQL tools, the support bundle, the export
vcs/templates/, vcs/static/, vcs/translations/
scripts/vendor/     the vendor's tools: vcs_vendor.py and the Vendor Console
```

Three rules follow from that:

- **A new route goes in the blueprint that owns its area.**
- **Anything two blueprints both need goes in `vcs/web/core.py`** (or the rest
  of `vcs`). A helper imported from a sibling blueprint is a circular import
  waiting to happen, and a blueprint never imports the factory.
- **Importing the package loads `.env` first** (`vcs/config.py`), so a module
  may read the environment at import time.

Endpoint names are blueprint-prefixed — `settings.settings_page`, not
`settings_page` — so a stale `url_for()` fails loudly when the page renders
rather than producing a broken link.

### Styling conventions

Colours live in the palettes: `vcs/web/palettes.py` defines the 15 (each light
and dark, every text pair WCAG AA), and `scripts/build_palettes.py` generates
`vcs/static/palettes.css` from it — never edit that file by hand. Styles live
in `vcs/static/style.css`, not in `style=` attributes. The foot of that
file holds a small set of utilities (spacing, flex rows, a few component
classes) built on the palette variables — use those rather than typing a pixel
value into a template.

The rule is opportunistic, not a sweep: **when you edit a template for any
reason, move its inline `style=` declarations up into the stylesheet.**
`settings.html` and `inventory_catalog.html` were done first;
`tests/test_inline_styles.py` holds the line for the rest, and fails if the
count goes up.

Two things stay inline and are not a lapse:

- **A value the server computes** — `style="display:{{ 'none' if ... }}"`.
- **Anything a script reveals with `el.style.display = ''`.** That clears the
  *inline* style and nothing else, so it unhides the element only while the
  inline style is the only thing hiding it. Move that `display:none` into a
  class and the element never appears again — no error, no clue. There is a
  test for exactly this, because it is the obvious-looking edit that breaks the
  Updates panel.

One quirk worth knowing: a few utilities are written with their class name
twice (`.u-strong.u-strong`). `.field label` is more specific than a single
class, so the inline style being replaced was the only thing winning; doubling
the class raises specificity without tying the utility to where it is used.

## Running the tests

The money math — totals, discounts, write-offs, cash rounding, and the
Decimal discipline that keeps every amount exact under both money settings —
is the part of this app most worth checking on every change, and the part where a mistake is
least visible: a wrong colour is obvious, a wrong total is a bill someone
already paid. `tests/test_money.py` covers it.

`tests/test_frontend.py` is the other one worth knowing by name — the rest
of the suite is described by tier below. It reads `style.css` and
the templates and fails on the kinds of breakage that used to be found only
by someone noticing them — a colour hardcoded instead of taken from the
palette (so it stays wrong in dark mode), a `var(--token)` that no longer
resolves (which renders as *nothing*, not as an obviously wrong colour), a
theme missing a colour the other theme has, a layout guard being deleted,
or an asset reference pointing at a file that isn't there.

Be clear about its limits: it is static analysis, not a browser. It cannot
tell you a page *looks* right — only that the specific things that have
broken before have not broken again. Looking at the app on a phone is still
the only way to know it works on a phone.

### The three tiers

The tests are not all the same kind. Each tier **skips cleanly** when what it
needs is absent, so the plain command below always works:

```
venv/bin/python -m pip install pytest
venv/bin/python -m pytest tests/ -q
```

| Tier | Needs | Runtime |
|---|---|---|
| **Pure** — money, static template/CSS guards, updater ordering | nothing | a few seconds |
| **Database** — routes, permissions, backups, migrations, concurrency | a throwaway Postgres in `TEST_DATABASE_URL` | ~15 seconds |
| **Browser** — `test_browser.py` | Playwright and a running app in `APP_URL` | ~2 minutes |

(They import the `vcs` package, so they need the app's own dependencies —
which is why they run from that venv rather than a bare Python.)

**A clean skip is not a pass, and the skip count will not tell you which.** A
tier whose import is missing collects *zero* tests and prints as a single
skip, not as the number of tests it holds. Confirm a tier is alive by
collecting it — `pytest tests/test_browser.py --collect-only` — rather than by
reading totals.

The database tier needs a throwaway Postgres, never a real one:

```
TEST_DATABASE_URL=postgresql://postgres:test@localhost:55491/vetclinicsystem \
  venv/bin/python -m pytest tests/ -q
```

`TEST_DATABASE_URL` is deliberately a different variable from `DATABASE_URL`
so that an exported shell variable can never point these tests, which write
and delete rows, at a live install. `scripts/isolated_test_env.sh up iq` (and
`up jo`) builds that database, a venv with pytest and Playwright in it, and a
running app licensed with a throwaway key.

**Run it under both money settings** — the `iq` and `jo` environments — before
calling a change done. An unmarked test follows the run's setting;
`@pytest.mark.money("IQ")` pins one (`CLAUDE.md` §5).

The scheduler's catch-up tests are gated on the clock and skip between 00:00
and about 01:05 — they need today's 00:30 backup slot to have passed. Skips in
`test_scheduler_catchup.py` in a run started then are that, not a broken tier.

If something fails,
**read what it says before changing it**: several of these tests exist
because the bug they describe already happened once. The tests around a
leftover balance are the clearest example — a threshold carried over
unchanged from the IQD original once marked bills with up to 500 fils
still owing as "Fully Paid", quietly hiding real uncollected money.

The two money settings make deliberately *different* assertions about the
same bill: IQ rounds cash to the 250-dinar note and never lets a real bill
round down to free; JO is exact to the fils. They are one set of functions
with different values (`docs/decisions/0001-money-is-one-policy.md`), and the
tests say which setting they expect.

## Running the browser checks (optional)

`tests/test_browser.py` opens every page in a real browser and checks it
isn't *broken* — no sideways scrolling, no JavaScript errors, no failed
assets, no control rendered at zero size, touch targets big enough on a
phone, and every page still rendering in dark mode. It does **not** compare
screenshots, so there is nothing to review or regenerate when you change
the design on purpose.

It needs two things the rest of the suite doesn't, and skips cleanly
without either — Playwright, and a running app:

```
venv/bin/python -m pip install playwright
venv/bin/python -m playwright install chromium
```

Then, with the app running:

```
APP_URL=http://127.0.0.1:5092 venv/bin/python -m pytest tests/test_browser.py -q
```

(5092 for JO. Set `APP_USER`/`APP_PASS` if your login isn't the default.)

Playwright is deliberately **not** in `requirements.txt`. The app itself has
no build step and no browser dependency, which is what lets it run anywhere
and keep running for years — that property is worth more than making these
tests run by default. Takes about two minutes.

## Your data

Everything lives in PostgreSQL (in Docker mode, inside the
`vetclinicsystem_pgdata` Docker volume) — see **Nightly Backups** above for how
it's backed up automatically. Uploaded X-rays and bloodwork live on disk in the
data folder (`attachments/uploads/`), which the database backup does not
include, so back that folder up too (e.g. with whatever backs up the rest of
this computer).

**Settings → Data Export** makes the clinic's own copy of everything it has
recorded — every table as a spreadsheet file (CSV), every attachment, the
database structure and a list of what is inside — at any time, read-only
included. It is for reading the records and taking them elsewhere; a backup
remains the exact copy to restore from.
