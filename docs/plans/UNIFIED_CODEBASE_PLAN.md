# Plan — one VetClinicSystem codebase with an IQ/JO money setting

**Written 2026-09-25. Status: IN PROGRESS — execution started 2026-09-25.**
The owner's decisions are in §10 and override anything earlier in this file
that disagrees with them (the biggest: the money setting is a **Settings
dropdown that locks itself**, not an install-time choice — §3.2 and §3.4 are
rewritten to match). What has been built so far is in the **progress log, §13**.

**Premise, as instructed:** treat this as a project that has never been
deployed. There are no installs to migrate, no databases to convert, no update
channels or environment-variable names to keep working. The two trees under
`webapps/` are **source material**, not systems to keep compatible with. That
removes most of what would make a merge risky, and it lets the merged app fix
the design problems in `CODE_AUDIT_2026-09-25.md` §5 instead of carrying them.

**Inputs:** `CODE_AUDIT_2026-09-25.md` (every finding ID below — B, S, F, P, D —
refers to it), `COMPARISON.md` §1.1 (the money model), `SEAM_RULES.md`, and a
function-by-function diff of the two trees.

---

## 0. The idea in one paragraph

83% of IQ's code, templates, JS and CSS already exist line for line in JO. The
real differences between Iraq and Jordan are small and are **data**: a
currency (IQD, whole dinars, paid in 250-dinar notes / JOD, 3 decimals, paid
to the fils), a phone format, a name, colours and logos. So there is **one**
app with a **country profile** chosen when a clinic is installed. The key
point, and what makes this simpler than it looks, is that **IQ's money rules
are not separate logic**: every one of them (round the bill to the nearest
note, never round a real bill down to free, give change down to a note, pay a
refund down to a note, warn when an amount can't be paid in notes) is one
general rule applied with a smallest cash unit of 250. With JO's smallest unit
of 0.001, the same rule does nothing, which is exactly JO's behaviour today.
There is **one money implementation, not two**.

## 1. Goals, and what is out of scope

**Goals**

1. One implementation of every rule. The parity problem (audit §4) **goes
   away** rather than being managed; `COMPARISON.md` stops being needed as a
   diff between two apps.
2. Country differences live in one place (`country/`) and nowhere else, and a
   test enforces that.
3. Every finding in the 2026-09-25 audit is fixed **by construction** where
   the design allows, and by an explicit, tested rule where it doesn't (§7).
4. Keep what works: Flask, psycopg 3, Waitress, Flask-Babel, the in-process
   job runner, the CSP nonce model, the no-inline-handler convention, the
   updater mechanism, the seam-rule tests.

**Out of scope**

- **More than one country per install.** One install is one clinic in one
  country, fixed at install time and never changed (§3.4).
- Multi-tenancy, a public API, or a new frontend framework.
- New features. This is a merge. A feature that exists in only one app today
  is adopted if it is plainly better (§6), and not otherwise extended.

---

## 2. What actually differs — measured

From the two trees at IQ v1.17.2 / JO v1.15.2. Anything **not** in this table
is the same by intent, and ends up as one implementation.

| Area | IQ | JO | In the unified app |
|---|---|---|---|
| Currency code / Arabic label | IQD / د.ع | JOD / د.أ | `profile.currency.code`, `.label_ar` |
| Decimal places (quantum) | 0 | 3 | `.minor_units` |
| Smallest cash unit | 250 | 0.001 | `.cash_unit` — **drives every IQ rounding rule** |
| Clean Up cap per bill | 1000 | 1.000 | `.cleanup_cap` |
| Largest accepted amount | 999,999,999,999 | 999,999,999.999 | `.max_amount` |
| Python money type | `float` | `Decimal` | **`Decimal` everywhere** |
| DB money type | `DOUBLE PRECISION` (68 columns incl. non-money) | `NUMERIC(12,3)`, `NUMERIC(10,3)`, `NUMERIC(5,2)` | **`NUMERIC` everywhere** (§4.1) |
| "Bill is settled" | `balance <= 0.5` | `balance <= 0` | one rule: `balance <= 0` after rounding |
| Cash-audit "Perfect" | `|diff| < 1` | `|diff| < 1` (**bug B7**) | one rule: `diff == 0` at the quantum |
| Money rule call sites | 17 calls into `money.py` + 4 warnings | none | the same 21 sites, one policy |
| Phone | `+964`, 10 local digits | `+962`, 9 | `profile.phone` |
| Branding | 2 palettes (vetzone, champet), PNG logos/favicons | 1 palette, SVG icon | `profile.branding` + an assets folder |
| Default clinic name/location | "VetClinicSystem IQ", Baghdad | "VetClinicSystem JO", Amman | `profile.branding` |
| Weekend default | Fri/Sat | Fri/Sat | `profile.weekend_days` (same today) |
| Time zone | clinic PC local time | same | `profile.timezone` (Asia/Baghdad, Asia/Amman) |
| Hard-coded currency in strings | 83 × "IQD" | 70 × "JOD" | none — `%(currency)s` |
| Arabic catalogue | 1304 msgids | 1304 msgids | 1262 shared; the 42/42 that differ are almost all currency wording |
| Arabic badge wrapping | `overflow-wrap:anywhere` scoped to RTL | `nowrap` | pick one badge style (§6, decision D-7) |

**Everything else** — the app-name, data-dir, port and Docker identifiers
spread across 17 files per app, the 7 differently-named indexes, `vet_users` inlined three times, two
row-navigation scripts, two conflict-handling styles — is drift, not a
country difference.

---

## 3. Architecture

### 3.1 Repository layout

```
vetclinicsystem/
├── vcs/                          the application package
│   ├── __init__.py               create_app(profile) — no module-level app
│   ├── country/
│   │   ├── __init__.py           Profile dataclasses, load_profile(), the registry
│   │   ├── iq.py                 PROFILE = Profile(...)
│   │   └── jo.py
│   ├── money.py                  THE money policy — the only place that rounds (§3.3)
│   ├── db/
│   │   ├── pool.py               psycopg pool; native %s placeholders (D7)
│   │   ├── migrate.py            versioned migration runner (§4.3)
│   │   └── migrations/0001_baseline.sql, 0002_seed_permissions.sql, ...
│   ├── domain/                   everything that decides; no Flask imports
│   │   ├── billing.py            bill totals + bill_changed() (§4.2)
│   │   ├── payments.py           record_payment(), record_refund()
│   │   ├── pos.py, inventory.py, consignment.py, cash_register.py,
│   │   ├── members.py, appointments.py, reports.py, clinical.py
│   ├── web/
│   │   ├── forms.py              every request validator (§5.1)
│   │   ├── permissions.py        permission registry + nav registry (§5.3)
│   │   ├── errors.py             error handlers (rollback first — B12)
│   │   └── blueprints/           settings, admin, clinical, sales, inventory,
│   │                             consignment, reports — thin
│   ├── templates/, static/, translations/
├── profiles/iq/, profiles/jo/    branding assets only (logos, favicons, palette CSS)
├── tests/                        one suite, run once per profile (§8)
├── scripts/                      test env, restore drill, simulation — profile-aware
├── setup.py                      one installer: `setup.py --country iq|jo`
└── docs/decisions/               the "why" that is 29% of today's line count (D12)
```

`app.py`'s current mixture (config, hardening, error handlers, dashboard,
reports, launcher) splits into `create_app()`, `web/errors.py`,
`blueprints/reports.py` and a small `run.py`. Blueprints keep the rule the
split established: they never import the app; shared pieces come from `vcs.*`.

### 3.2 The country profile

Frozen dataclasses. Values only — no functions, no behaviour. A third country
later is a new file.

```python
@dataclass(frozen=True)
class Currency:
    code: str              # "IQD" / "JOD" — Latin, used in PDFs and exports
    label_ar: str          # "د.ع" / "د.أ"
    minor_units: int       # 0 / 3 — the quantum is 10**-minor_units
    cash_unit: Decimal     # 250 / 0.001 — smallest amount physically handed over
    cleanup_cap: Decimal   # 1000 / 1.000
    max_amount: Decimal

@dataclass(frozen=True)
class Phone:
    country_code: str      # "964" / "962"
    local_length: int      # 10 / 9
    example: str

@dataclass(frozen=True)
class Branding:
    product_name: str      # shown in titles and PDFs
    default_clinic_name: str
    default_location: str
    palettes: tuple        # ("vetzone", "champet") / ("default",)
    assets_dir: str        # "profiles/iq"

@dataclass(frozen=True)
class Profile:
    code: str              # "IQ" / "JO"
    currency: Currency
    phone: Phone
    branding: Branding
    weekend_days: frozenset
    timezone: str
```

**Selection — decided by the owner 2026-09-25: a Settings dropdown that locks
itself.** The profile is stored as `settings.money_setting` (`IQ` or `JO`;
absent until chosen). An admin with `manage_settings` picks it in Settings.
It can be changed **only while no money has been recorded** — any row in a
money-bearing table (price list or catalogue prices, bills, payments, sales,
refunds, boarding charges, inpatient lines, distributor bills, consignment
records, cash register payouts or audits, operating costs). From the first
such row it is locked, server-side, and the dropdown shows why.

**Before it is chosen**, every money screen (billing, POS, payments, refunds,
price list and catalogue prices, cash register, P&L, consignment, distributor
bills) is gated: it redirects to Settings with a prompt, and an admin logging
in is taken there first. Phone fields accept only a full international number
(`+964…`, `+962…`) until the setting provides a country default.

The phone format, the default time zone and the weekend default follow the
money setting. Branding does **not**: the palette is its own clinic setting
(§6), open to either money setting.

**Install identity** (data-dir name, Docker container/volume, DB name, backup
file prefix, default port) comes from one `install_slug` in `.env`, set by
`setup.py`. It is not part of the country profile, because two clinics in the
same country on one machine must not share it — which is also why the two
installs collided on port 5050 (`COMPARISON.md` §54).

**Enforced by a test:** outside `vcs/country/` and the branding assets, no code
compares a profile code (`== "IQ"`, `profile.code in ...`), and no file
contains the literals `IQD`, `JOD`, `964`, `962`, `250`. Every difference goes
through a profile field. This is the rule that keeps the app one app.

### 3.3 Money: one policy, parameterised

`vcs/money.py` is the only module that rounds, quantizes, or compares against
a tolerance. Everything is `Decimal`; the database is `NUMERIC`. With
`q = 10**-minor_units` and `u = cash_unit`:

| Function | Rule | IQ (`u = 250`) | JO (`u = 0.001`) |
|---|---|---|---|
| `parse(raw)` | reject NaN/Inf/over `max_amount`; **quantize to `q`, half-up** | 1,234.6 → 1,235 | 0.0004 → 0.000 (then `> 0` checks see 0 — **fixes B6**) |
| `payable(raw, discount_pct)` | round to `u`, half-up; if `0 < raw ≤ u/2` and discount < 100 → `u` | 100 → 250 (the anti-"looks free" floor) | 0.100 → 0.100 |
| `change(received, total)` | floor `received − total` to `u` | 1,100 → 1,000 | exact |
| `refund(amount, headroom)` | floor to `u`; if that is 0 but `amount > 0`, pay `u` when `headroom ≥ u` | F3's rule | exact |
| `is_settled(balance)` | `balance <= 0` | replaces `<= 0.5` | same |
| `audit_status(diff)` | `Perfect` iff `diff == 0` | same as today in practice | **fixes B7** |
| `payable_in_cash(amount)` | `amount % u == 0` | the denomination warning | always true — never warns |
| `format(x)` | `minor_units` places, grouped | `12,500` | `12.500` |
| `input_step(kind)` | `q` for typed amounts, `u` for cash received | `1` / `250` | `0.001` |
| `pct(x)` | `Decimal` percentage, 0–100 | | |
| `discounted(subtotal, discountable, pct)` | the one discount formula (today's `discounted_raw_total`) | | |

The two apps' opposite money tests (IQ 40 + 76, JO 35 + 76) become **one
table-driven specification** with a column per profile. Every IQ edge case
(125 → 250, 100% discount exempt from the floor, change floored, the F3 refund
floor bounded by headroom) and every JO one (0.240 refunded as 0.240, 0.100
stays 0.100) is a row. JO's guard that "fails 20 tests if IQ's rounding is
ported across" becomes this table's JO column.

**JavaScript gets the same policy, once.** `base.html` emits
`window.VZ_MONEY = {minorUnits, cashUnit, code, label}` and a single
`static/money.js` (`VZMoney.payable`, `.change`, `.format`) serves the POS
preview, visit billing and every other live total. Today IQ's POS preview
hard-codes `Math.round(x / 250) * 250` and JO's hard-codes three decimals.

### 3.4 One currency per database, forever after the first money

Because the setting locks at the first money-bearing row, a database can never
hold amounts recorded under two currencies, and every stored number keeps the
meaning it was entered with. The lock is enforced in the settings route (not
just by disabling the dropdown), and a test posts a change after money exists
and asserts it is refused. A clinic that genuinely changes currency gets a new
install.

---

## 4. Database

### 4.1 One schema

Start from **JO's** schema (already exact, already NUMERIC) with these changes:

- **Money:** `NUMERIC(15,3)` for every amount (holds IQ's 12 integer digits and
  JO's 3 decimals); `NUMERIC(10,3)` for quantities that are multiplied by a
  price; `NUMERIC(5,2)` for percentages. IQ amounts are stored as `.000`. The
  app quantizes on entry, so a stored JO value can never carry a fourth
  decimal (B6).
- **CHECK constraints on every amount** (D10): `>= 0` or `> 0` as appropriate,
  percentages `BETWEEN 0 AND 100`, quantities `> 0`. Today only
  `distributor_bill_payments.amount` has one.
- **Counts** (`stock_counted`, `received_since_prior`, thresholds, `change_qty`,
  `weight_kg`): `NUMERIC(12,3)` with the existing non-negative checks (plus
  `<> 'NaN'`, since numeric NaN sorts above everything). No floats anywhere.
- **Time** (D6): `date` for business dates; `timestamptz` for every event time
  (`sales.sale_date` becomes `sold_at`, `audit_log.timestamp`,
  `inventory_transactions.timestamp`, consignment `period_start/end`,
  `created_at`s). Filtering by day becomes a range on an indexed column, not
  `LIKE 'YYYY-MM-DD%'`, which removes the silent-empty half of B1 and the
  sub-second boundary of B13.
- **Keys** (decision D-2): integer identity primary keys throughout, with the
  human codes staff read (`V-00123`, `PT-00045`) produced by one template
  filter. Today's text IDs share one counters table, sort wrongly past 999
  (`V999` after `V1000`), and exist only because of the SQLite origin.
- **Indexes** for what the app filters and joins on (D9): `sales(sold_at)`,
  `payments(recorded_at)`, `payments(date)`, `refunds(refund_date)`,
  `refund_items(sale_item_id)`, `sale_items(item_id)`,
  `login_log(username, at)`, `audit_log(at)`, `visits(followup_date)`,
  `visits(wellness_next_dose_date)`, `inpatient_cases(visit_id)`,
  `inventory_transactions(item_id, at)`. One naming scheme.
- **`refund_items.sale_item_id` NOT NULL** — every cost reversal uses the sale
  line's snapshot (B9).
- **`payments.recorded_at` and `refunds.recorded_at`** (server time, set by the
  database) alongside the business date. The Cash Register counts what was
  recorded on the day; P&L uses the business date (B16).
- **`settings.country`** written by the first migration (§3.2).

### 4.2 Derived money: one entry point, and the P&L computed on read

Today four stored totals and a monthly summary table are kept in step by hand
from about 30 call sites; the audit found three that forgot (B2), a report
that read the uncached column (B3), and a rebuild race (B14).

- **Bill totals stay stored** (`billing.total`, `inpatient_cases.total`,
  `boarding_sessions.billed_total`, `sales.total`) because every report sums
  them. They are written by **exactly one function**,
  `domain.billing.bill_changed(db, kind, id)`, which recomputes the total from
  lines, discount and Clean Up. Every function that changes a bill ends by
  calling it, and a test enforces that no module other than
  `domain/billing.py` writes those columns.
- **`monthly_financial_summary` is dropped.** Monthly and yearly P&L,
  Insights revenue by category, vet performance and client value read the
  **same stored totals** through one query module (`domain/reports.py`),
  grouped by month over indexed dates. At a clinic's scale — thousands of rows
  a year — that is milliseconds. No rebuild button, no staleness, no race.
  If a real clinic ever makes it slow, add a materialised view refreshed by
  `bill_changed()`; do not go back to hand-maintained rows.
- **Insights and the P&L cannot disagree** because they call the same
  function for revenue (B3); a test asserts they agree for the same month.
- **Refund cost reversals and consignment credits** use the refunded sale
  line's `unit_cost` and `distributor_id` snapshots (B9), at timestamp
  precision.

### 4.3 Migrations run once each

A `schema_migrations(version, applied_at)` table and numbered SQL files, each
applied once in its own transaction (D5). `0001_baseline.sql` is the whole
schema; seed data (roles, permissions, default settings) is a separate
idempotent step that also re-asserts "the system role holds every permission"
(the fix `FULL_APP_REVIEW` S1 had to add by hand). This removes, as a category:
the 100-statement list re-run on every start, the ~30 constraint DROP/ADD pairs
that re-validate whole tables at every launch, the unconditional
`permissions_version` increment, and the "index over a migration-added column
aborts every upgrade" trap that once blocked 16 of 38 releases.

`test_migrations.py` becomes: apply 0001…N to an empty database for each
profile, and assert the result equals a schema dump checked into the repo.

### 4.4 Locking conventions

Written down once (`docs/decisions/locking.md`) and enforced by the existing
seam-rule test 1, extended: every money write locks its parent row, **and**
every cap check runs under the lock of the row that owns the cap — the sale
for a refund aggregate, a per-day `cash_register_days` row for payouts (B15),
the distributor for settlements. Helpers never commit; only the request (or a
job) does (D11).

---

## 5. Application layer

### 5.1 One validator per kind of input — `web/forms.py`

| Validator | Rule | Fixes |
|---|---|---|
| `strict_date(v)` | `YYYY-MM-DD` only: `strptime` **and** `v == parsed.isoformat()` | B1 — no `fromisoformat` on request input anywhere |
| `date_filter(name)` | the one read-side filter helper (JO's `date_filter_arg`) with its warning | B1, P11 |
| `money(v)` / `quantity(v)` / `percent(v)` | via `money.parse`, bounds from the profile | B6 |
| `payment_method(v)` | one of the constants, on **every** surface | B10 |
| `business_date(v, not_before, not_after)` | e.g. a refund between the sale date and today | B16 |
| `phone(v)` | profile country code and length | — |
| `choice(v, allowed)` | with a translated message | F1 |

A validator raises one exception type carrying a msgid and arguments; the
blueprint catches it and redisplays. No route parses request input by hand.

### 5.2 Services, not routes, own the rules

The four payment surfaces (visit, inpatient, boarding, POS) call one
`payments.record_payment()` that does, in order: lock the parent, validate the
method and amount, apply discount and Clean Up through `money`, insert, call
`bill_changed()`. Refunds likewise. Today each route carries its own copy of
that sequence, which is how every entry in `SEAM_RULES.md` happened. A rule
that lives in one function cannot drift.

Also in the service layer:

- `get_or_404(table, id, lock=False)` before every child insert (B11).
- `inventory.status_for(db, item_ids)` scoped to the items asked about (D4);
  POS refuses a line whose item is inactive or has no usable count (B5).
- `vet_users()` exists once (P19).
- `consignment.balance()` with microsecond period bounds and an upper bound on
  every query (B13).
- Audit usage adds `consignment_receipt` movements to "received since prior"
  automatically (B18).

### 5.3 Permissions and navigation come from registries

- **One permission registry** (key, label, category, "admin-equivalent" flag).
  `manage_users_roles` is flagged admin-equivalent in the UI, and three rules
  are enforced in the service: only a system-role user may assign the system
  role, reset a system-role user's password, or grant a permission they do
  not hold themselves (S2).
- **Settings fields declare their permission.** A registry maps every
  settings key to the permission that may change it (`backup_dir`,
  `backup_retention`, `log_retention_days`, `backup_time` →
  `manage_maintenance`). The template renders from that map and the POST
  accepts only keys the user may change, so the UI gate and the server gate
  are one definition (S1).
- **One navigation registry** (endpoint, label, permission, group). The
  sidebar renders from it, so a link is shown exactly when its page would not
  403 (P1); the permission tests walk the same registry.

### 5.4 Cross-cutting behaviour, decided once

- **Error handler** rolls back before rendering, so the 500 page keeps the
  clinic's name and language (B12).
- **Edit conflicts**: redisplay the user's values **with the original token**
  and show the other person's current values beside them; a second Save is
  refused again until the user reloads or merges (B4, P10).
- **Restore** puts the app in maintenance mode: every request except the job
  poll answers 503 until it finishes; `pg_restore` runs with
  `--single-transaction` (S3).
- **Redirects** only through `safe_redirect()` (S5); the dev server binds
  127.0.0.1 on the configured port (S4).
- **Background jobs** return results tagged with the endpoint that started
  them; a page only accepts its own job's result.
- **Login rate limiter** guarded by a lock (B20).
- **Dashboard badge** from `COUNT(*)` queries, cached per minute (D3). Wellness
  "due" is bounded to the missed window and superseded by a newer reminder for
  the same patient and type (B19).

---

## 6. Frontend and localization

- **Templates from IQ** (the more complete set), parameterised by profile:
  currency via `currency_label()` and `%(currency)s`, input `step` from
  `money.input_step()`, branding from `profile.branding`.
- **One of each mechanism**: `ui.js` row navigation (drag threshold,
  aria-label) — `data-vz-href` in `behaviors.js` is deleted (P6); every modal
  through `VZSpring`; `_back_link.html` on every detail page (P5); tab state
  kept in the URL hash with ARIA roles (P3).
- **All UI text translatable** (F1, F2):
  - `flash()` only ever receives `_()` — enforced by an AST test over
    `vcs/` (the scan in the audit found ~30 violations per app);
  - service and validator errors carry `(msgid, args)`, translated at the
    route;
  - `base.html` emits `window.VZ_I18N` for the static scripts (unsaved-changes
    dialogs, upload progress, job progress, phone validation, toast);
  - loading-shell titles and job step labels go through `_()`.
- **Catalogue merge**: the 1,262 shared msgids carry over as-is. The 42/42
  that differ are re-worded once with `%(currency)s` instead of a literal code,
  translated once, and reviewed by the clinic like the earlier question files
  (never `pybabel update` fuzzy matches — see
  `ARABIC_TRANSLATION_QUESTIONS_REWARDS.md`).
- **Numbers in JS** format through `VZMoney.format` with the app's locale, not
  `toLocaleString()` with the browser's.
- **PDFs** stay English with the Latin currency code
  (`ARABIC_LOCALIZATION_PLAN.md` §0), from `profile.currency.code`, and print
  quantity and line total (B8).
- **Branding**: palettes listed by the profile; each palette is CSS custom
  properties plus an image set under `profiles/<code>/`. IQ's
  `static_asset()` palette-suffix helper generalises to
  `asset(name)`.

### Behaviour chosen where the two apps disagree (audit §4)

| # | Adopt | Why |
|---|---|---|
| P1 | permission-gated sidebar (from the registry) | a link that 403s is a bug |
| P2 | search-based inpatient billing, **Service + Medicine** | JO cannot bill medicines to an inpatient case |
| P3 | tab kept across submits, ARIA tabs | IQ |
| P4 | drop the admitting visit from patient history | IQ |
| P5, P6 | back link; `ui.js` row navigation | IQ |
| P7 | consignment shortfall warning on audit confirm | IQ |
| P8 | refuse the whole inpatient submission when a staff discount meets a non-discountable item | matches visit billing and POS (decision D-5) |
| P9 | audit-log admission fields | IQ |
| P12 | nothing — the summary table and its rebuild are gone (§4.2) | |
| P13 | batched stock lookup | JO |
| P14 | explain *and* keep `next` after a password-change sign-out | both halves |
| P15 | wellness: overdue first, then soonest | neither app's order is useful once the list is bounded |
| P16, P17 | keep the booked day; 404 for a missing parent | IQ |
| P20 | delete as "×" with aria-label **and** per-item barcode print link | take both |

---

## 7. The audit, mapped to this plan

**By construction** means the design makes the bug impossible rather than
checking for it.

| Finding | Where it goes | How |
|---|---|---|
| B1 date filters → 500 / empty | §5.1, §4.1 | `strict_date` everywhere; `timestamptz`/`date` range filters — **by construction** |
| B2 stale P&L | §4.2 | no summary table — **by construction** |
| B3 JO boarding revenue | §4.2 | one revenue function over stored totals — **by construction** |
| S1 settings fields | §5.3 | field → permission registry — **by construction** |
| S2 users/roles → Admin | §5.3 | three service rules + test |
| B4 edit conflicts | §5.4 | keep the original token on redisplay |
| B5 POS inactive item | §5.2 | fail closed on missing status + active check |
| B6 sub-fils | §3.3 | `money.parse` quantizes — **by construction** |
| B7 JO cash audit | §3.3 | `audit_status` exact — **by construction** |
| B8 IQ PDF quantities | §6 | one PDF renderer (JO's line rendering) — **by construction** |
| B9 reversal cost basis | §4.1, §4.2 | `sale_item_id` NOT NULL, snapshot joins |
| S3 restore while serving | §5.4 | maintenance mode + single transaction |
| F1 untranslated flashes | §6 | AST-enforced `_()`; `(msgid, args)` errors |
| F2 static JS English | §6 | `VZ_I18N` |
| B10 payment method | §5.1, §5.2 | one validator inside `record_payment()` — **by construction** |
| B11 missing parents | §5.2 | `get_or_404(..., lock=True)` |
| B12 error page on aborted txn | §5.4 | rollback first |
| B13 settlement boundary | §4.1, §5.2 | `timestamptz` + bounded queries |
| B14 rebuild race | §4.2 | no rebuild — **by construction** |
| B15 unlocked caps | §4.4 | cap-owning row lock, seam rule 1 extended |
| B16 free-form dates | §4.1, §5.1 | `recorded_at` for the drawer; bounded business dates |
| B17 JO appointment day | §5.4 / P16 | explicit context builders (IQ style) — **by construction** |
| B18 audit usage vs receiving | §5.2 | receipts feed "received since prior" |
| B19 wellness forever due | §5.4 | bounded + superseded |
| B20 small items | §4.4, §5.4 | helpers never commit; locked rate limiter |
| S4, S5 | §5.4 | loopback dev server; `safe_redirect()` |
| P1–P20 parity | §6 table | one implementation — **by construction** |
| D1 two forks | §0, §3 | this plan |
| D2 hand-synced totals | §4.2 | `bill_changed()` + reports on read |
| D3 dashboard per page | §5.4 | counts, cached |
| D4 catalogue recompute | §5.2 | `status_for(ids)` |
| D5 migrations every launch | §4.3 | versioned, run once |
| D6 TEXT timestamps / 3 parsers | §4.1, §5.1 | typed columns, one strict parser |
| D7 `?` translator | §3.1 | native `%s` |
| D8 duplicate mechanisms | §6 | one of each |
| D9 indexes | §4.1 | added in the baseline |
| D10 constraints | §4.1 | CHECK on every amount |
| D11 committing helpers | §4.4 | rule + test |
| D12 comment volume | §3.1 | `docs/decisions/`; code comments state invariants only |

---

## 8. Tests — one suite, two profiles

- **The whole suite runs once per profile**: `pytest --profile=iq` and
  `--profile=jo`, each against its own throwaway database built by the
  migrations for that profile. `scripts/isolated_test_env.sh up iq|jo` stays,
  now building the same code with a different `VCS_COUNTRY`. A run that tests
  only one profile is not a pass.
- **Carry over** the existing 52/51 test files, merged: 26 are byte-identical
  between the apps today and most of the other 25 differ only in money or
  names; the money pair becomes the table in §3.3; IQ-only
  `test_arabic_wrapping.py` follows decision D-7.
- **Keep** the seam-rule tests (`test_seam_rules.py`) and the conventions
  tests (no inline handlers, inline-style ratchet, `|tojson` in scripts).
- **Add**, from the audit's §6:
  1. a POST sweep of every parameterised route with a missing parent (B11);
  2. after every money-writing route, the P&L, Insights and the stored total
     agree (B2, B3);
  3. hostile dates on every filter, including `2026-W39-4` and `20260925` (B1);
  4. the AST scan: no untranslated `flash()` (F1); no profile-code comparison
     or currency/phone literal outside `vcs/country/` (§3.2);
  5. permissions: a role with only `manage_settings` cannot change a
     maintenance field; a role with only `manage_users_roles` cannot assign the
     system role (S1, S2);
  6. only `domain/billing.py` writes stored totals; nothing in `domain/`
     commits (D2, D11).
- **Mutation-prove every new guard** before believing it (`CLAUDE.md` §7.3):
  reintroduce the bug, watch the right test fail in **both** profiles.
- **Seed a barcode** in the test environment, so the browser barcode test
  stops skipping (audit §6).
- **Browser tier**: every page, both profiles × both languages, no console
  errors, no CSP violations, no horizontal overflow at 375 px, loading shells
  waited out (`CLAUDE.md` §5).

---

## 9. Build order

Each phase ends with its tests green in both profiles. "Port" means: take the
function from the tree named, apply the decision in §6/§7, and record the
source in the commit message.

| Phase | Work | Size | Source |
|---|---|---|---|
| **0. Decisions** | Settle §10's open questions | S | — |
| **1. Skeleton** | Repo, package layout, `create_app()`, profiles, `money.py` + the table-driven spec | M | JO for Decimal, IQ's `money.py` for the rules |
| **2. Database** | Baseline schema, migration runner, seed, schema snapshot test | M | JO schema + §4.1 |
| **3. Domain** | Port `logic.py` into `domain/*`; `bill_changed()`; reports on read; `record_payment()`/`record_refund()` | L | IQ behaviour, JO typing |
| **4. Web** | Validators, registries, blueprints, error handlers, maintenance mode | L | IQ routes (explicit context style) |
| **5. Frontend** | Templates, `money.js`, `VZ_I18N`, nav, branding assets | M | IQ templates |
| **6. Localization** | Catalogue merge, currency-parameterised msgids, clinic review | M | both `.po` files |
| **7. Tooling** | `setup.py --country`, test env, restore drill, simulation harness, updater with one repo | M | both |
| **8. Verification** | Full suite ×2, simulation day ×2, hostile sweeps ×2, restore drill ×2, audit repros all refused | M | `scripts/simulation/` |

Roughly: phases 1–2 are the foundation and should be reviewed before phase 3
starts, because every later phase assumes the money policy and the schema.
Phase 3 is the biggest and the riskiest: ~2,800–3,000 lines of `logic.py`,
where most bugs in the audit live.

---

## 10. Decisions — taken by the owner, 2026-09-25

| # | Decision | Taken |
|---|---|---|
| D-1 | Product, repo, first version | **VetClinicSystem**, `aldbabiomar/vetclinicsystem` (made **public** so the updater needs no credentials), first release `1.0.0` |
| D-2 | Record IDs | **Numeric keys**; staff see generated codes (`V-00123`) |
| D-3 | Monthly summary table | **Dropped**; P&L and Insights computed live from stored bill totals |
| D-4 | Profiles as modules or data | Python modules (implementation choice) |
| D-5 | Inpatient billing with a blocked item | Refuse the whole submission |
| D-6 | IQ's ChamPet palette | Kept |
| D-7 | Badge style | `nowrap` — an Arabic word is never broken |
| D-8 | Time zone | stored `timestamptz`; a **Time Zone setting** in Settings, changeable at any time, whose "Automatic" default follows the money setting's zone (the computer's zone until one is chosen). Asked again during phase 2c and answered by the owner, 2026-09-25, over "follow the computer's clock" and "follow the money setting only" |
| D-9 | How the money setting is chosen | **Settings dropdown**, changeable until the first money is recorded, then locked; it also sets the phone format |
| D-10 | Before it is chosen | Money screens locked until an admin chooses; phone fields international-only |
| D-11 | Logo | **A new neutral SVG mark**, tinted by the active palette; the dog illustrations stay on error pages, also tinted |
| D-12 | Palettes | **15**: Vetzone and ChamPet (from IQ), JO's crimson/navy, plus **12 new distinct calm palettes**, each light + dark, every text/background pair WCAG AA |
| D-13 | Documents | All in this repo; IQ/JO-era documents archived under `docs/archive/`; the predecessor clones kept read-only in `webapps/` (untracked) until the merge is done, then removed |
| D-14 | Execution order | Start from **JO's tree** (already exact-decimal throughout), port IQ's features and money rules into it, and transform it step by step with the suite green at every commit — rather than writing a fresh skeleton. Same end state as §3, less risk |
| D-15 | Code layout | **Full restructure** into the `vcs/` package of §3.1 (owner, 2026-09-25, asked with the option of keeping the flat layout). The country profile of §3.2 is realised as the money setting (D-9), so `vcs/country/` becomes the money setting's home and there is no `setup.py --country`: §12 items 3 and 5 are read that way |
| D-16 | Wellness reminders | Most urgent first on the Dashboard and the Wellness page (owner, 2026-09-25). "Due" ends when "missed" begins; a newer wellness entry for the same pet and type replaces the old one (audit B19, P15) |

> **Superseded in part, after the merge** — `DEVELOPER_AND_LICENSING_PLAN.md` (owner decisions, 2026-09-25) makes the repository **private** with a GitHub token per clinic (L-1, over D-1), and moves the choice of **palette** (L-2, over D-12's placement) and of the **money setting** (L-3, over D-9's placement; the lock rule is unchanged) to a vendor-only Developer area. It runs **after** this merge and reuses the storage keys this merge creates, so build D-9 and D-12 in Settings as written here.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| IQ's arithmetic moves from `float` to `Decimal` and behaves slightly differently | the IQ column of the money spec is IQ's current tests, verbatim; mixing float and Decimal raises `TypeError` immediately, so mistakes are loud |
| A rule quietly changes in the port | every function in the function diff (≈120) gets a recorded decision; the simulation day and hostile sweeps rerun in both profiles |
| Computing the P&L on read is slow | measure on a synthetic 10-year database in phase 8; materialised view fallback (§4.2) |
| Translation drift | msgids only change where a currency literal becomes `%(currency)s`; no fuzzy matching; clinic review |
| "Country" leaks back into code as `if` statements | the §3.2 enforcement test |
| Scope creep into new features | §1: adopt, don't extend |

---

## 12. Done means

1. Both profiles: full suite green, zero skips (with `APP_URL` set), browser
   tier alive in both languages.
2. Every reproduction in `CODE_AUDIT_2026-09-25.md` §9 is refused or correct in
   both profiles.
3. No profile-code comparison or country literal outside `vcs/country/`.
4. Exactly one module rounds money (`money.py`) and exactly one writes stored
   totals (`domain/billing.py`).
5. A fresh `setup.py --country iq` and `--country jo` install side by side on
   one machine without colliding.
6. `COMPARISON.md` is replaced by `docs/decisions/` — there is nothing left to
   compare.

---

## 13. Progress log

Newest last. Each entry says what landed, how it was verified, and the suite
result under each money setting.

- **2026-09-25 — Bootstrap.** Workspace became the repo
  `aldbabiomar/vetclinicsystem`. JO v1.15.2's tree imported as the base
  (commit `7b3cb5d` of the JO repo); every `VetClinicSystem JO` /
  `vetclinicsystemjo` / `VETCLINICSYSTEMJO_` identifier renamed to the single
  product (37 files, catalogue msgids and msgstrs together, recompiled). Docs
  restructured: current ones under `docs/`, IQ/JO-era ones under
  `docs/archive/`, new `docs/README.md` index, new `CLAUDE.md`, fresh
  `CHANGELOG.md`, `VERSION` 1.0.0. `scripts/isolated_test_env.sh` now builds one
  app per money setting (`vcs_test_iq` 5091 / `vcs_test_jo` 5092). The
  predecessor apps' upgrade-from-old-tags migration tests replaced with
  fresh-install idempotency checks (there are no old tags here). Suite (jo
  setting, the only behaviour the tree has yet): **844 passed, 4 skipped** —
  the skips are data/feature-dependent and tracked.
  **Known not yet converted:** `scripts/simulation/prove_guards.py`,
  `prove_rewards_guards.py`, `check_rendered_js.py`, `repro_pos_floor.py`,
  `scripts/restore_drill.sh` and `scripts/make_app_icons.py` still target the
  predecessor trees under `webapps/` — rewritten in the tooling phase. The
  one-off translation scripts (`ar_batch*.py`, `wrap_*.py`, `fix_*.py`) are
  spent and will be archived then.
- **2026-09-25 — Phase 1: one money model, two money settings.** `money.py`
  is the only place money is rounded, compared or parsed: `Decimal`
  throughout, every money column `NUMERIC(15,3)`, and the two settings as data
  (`money.IQ`: whole dinars, 250-dinar cash unit, 1,000 Clean Up cap, +964/10
  digits; `money.JO`: three decimals, the fils, 1.000 cap, +962/9). IQ's rules
  are the general rules with IQ's numbers — payable totals half-up to the cash
  unit with the anti-"looks free" floor, change and refunds rounded down, a
  refund never zero while a unit is refundable, the drawer audit exact. The
  setting is chosen in Settings (D-9), locks itself once `money.MONEY_TABLES`
  hold a row, and is enforced on the server, not just by disabling the
  dropdown. Until it is chosen, every money screen redirects with a message
  (D-10) and phone fields accept international numbers only. It drives the
  phone format, the currency label (IQD/JOD in English, د.ع/د.أ in Arabic,
  the Latin code on PDFs), every `step=` on a money input, and the browser
  previews (`static/money.js`, fed from `window.VZ_MONEY`). Active per request
  through a `ContextVar`, copied into background job threads.
  **IQ's tests came across verbatim in intent:** `test_money_iq.py` (110, from
  IQ's `test_money.py`) and `test_money_routes_iq.py` (from IQ's
  `test_money_routes.py`), marked `@pytest.mark.money("IQ")`; the suite's
  default stays JO. Two IQ-marked browser tests put non-note amounts in front
  of the real till — until now no browser test had ever run the IQ rules.
  **Also fixed:** audit B6 and B7 (JO precision and the 1-JOD "Perfect"
  tolerance, now pinned at the route); B13's same-second double count (the
  restock term waits for `timestamptz`); and eight bugs the audit had missed,
  recorded as `CODE_AUDIT_2026-09-25.md` §10 M1–M8 — among them JO's rewards
  card that could never be switched on (M1), IQ service refunds of 0 or of
  more than was paid (M2, now `SEAM_RULES.md` S8), and distributors owed
  money that could never be settled (M8). Every new guard was
  mutation-checked: the bug put back, the test watched failing, the fix
  restored.
  **Arabic:** 57 msgids changed or added (the currency became `%(currency)s`
  in ~20 messages, and POS/refund refusals that had always shown English are
  wrapped for the first time). 21 reuse the predecessors' reviewed Arabic;
  36 were written from the catalogue's glossary and are listed in
  `docs/ARABIC_REVIEW.md` for the clinic. Six translations that were one
  sentence repeated are fixed. `tests/test_catalogue.py` now extracts every
  msgid the code uses and fails on a missing, fuzzy, doubled or
  placeholder-dropping translation.
  **Tooling:** `scripts/isolated_test_env.sh restart iq|jo` reloads the app,
  killing by port and asserting the pid changed.
  **Suite, both money settings, browser tier alive:** IQ environment
  **1057 passed, 4 skipped**; JO environment **1058 passed, 3 skipped** — the
  skips are data-dependent (no barcode seeded, no visit to export, …) and
  tracked. With no database: 446 passed, 615 skipped, 0 errors.
- **2026-09-25 — Phase 2a: migrations run once each.** `schema.py` applies
  numbered files in `migrations/` — each once, in its own transaction, under an
  advisory lock, recorded in `schema_migrations` — then seeds roles and
  permissions (which also re-grants the system role every permission). A
  failing file rolls back whole and stops the run: `setup.py` exits non-zero,
  which fails an update before its pointer flips. `schema_postgres.sql` plus the
  99-statement `INCREMENTAL_SCHEMA_STATEMENTS` list became
  `migrations/0001_baseline.sql`; built both ways, the two schemas compared
  **equal** (tables, columns, constraints and indexes, as Postgres reports them),
  and IQ's predecessor schema matched too apart from index names.
  `tests/schema_snapshot.json` now pins the schema; `scripts/schema_snapshot.py`
  regenerates it on purpose. The `migration_failures` setting and its banner are
  gone; a database behind the code is reported instead (`schema_behind`, a
  self-check failure and a dashboard banner). A restore brings an older backup
  forward through the same runner. Found on the way: two source-parsing tests
  (`test_sql_placeholders.py`, and `test_frontend.py`'s citation check) globbed
  `*.sql` at the root and would have gone silently empty — the first one's
  control caught it; the second had no control and now has one. The updater's
  release validation had no test at all; it has four.
  Mutation-checked: skip-and-continue, per-statement commits, a dropped index,
  and a stale required-file name each turn a test red.
  **Suite:** IQ **1071 passed, 4 skipped**; JO **1071 passed, 4 skipped**; no
  database 457 passed, 0 errors.
- **2026-09-25 — Phase 2b: no floats, and every amount checked by the
  database.** The last seven float columns — the four audit-count columns,
  `inventory_transactions.change_qty` and both `weight_kg` — are
  `NUMERIC(10,3)`: the width `parse_quantity()` already bounds every count to
  (§4.1 said `(12,3)`; a column wider than its parser's bound buys nothing,
  and one bound for every count is the point). Every NUMERIC
  column now has a CHECK: its sign as the routes enforce it, percentages 0–100,
  `amount_paid <= amount_owed` on settlements, and **never NaN** — Postgres sorts
  NaN above every number, so `>= 0` alone admits it. A structural test fails
  for any future numeric column without one. The D9 indexes are in, including
  the first index `login_log` has ever had (it is read on every login).
  Decimal counts changed the meaning of two lines in the Ordering Sheet, both
  fixed before they could ship and pinned by tests: `-(-x // 1)` rounds a
  positive Decimal DOWN (`//` truncates toward zero), and `rate * 1.15`
  raises TypeError. One formatter now prints every count and weight (M9), the
  POS stock goes to the browser as a JSON number (a string would have turned
  a capped quantity plus one into "131"), and four consignment refusals that
  were English-only are translated (F1). `isolated_test_env.sh reset iq|jo`
  rebuilds just the database after an in-place baseline edit.
  **Suite:** IQ **1094 passed, 4 skipped**; JO **1094 passed, 4 skipped**; no
  database 473 passed.
- **2026-09-25 — Phase 2c-i: the clinic's clock.** `clock.py` decides what
  "now" and "today" mean: the new **Time Zone** setting (D-8, the owner's
  choice), else the money setting's zone, else the computer's. All 118 clock
  reads in the application and 181 in the tests go through it, and a scan fails
  on any new `datetime.now()` / `date.today()`. A request applies the zone to
  its pooled connection (committed at once, so a later rollback cannot undo
  it), `db.connect()` does the same for jobs, and every scheduled job runs
  inside the clinic context — APScheduler's cron triggers now get the zone
  explicitly, because they take the computer's otherwise. Stored timestamps
  parsed back from text are made aware in one helper (`clock.parse`), fixing
  the naive/aware comparisons in the login lockout, heartbeat, scheduler,
  self-check, self-verify and the attachment reconciler. `tzdata` joins the
  requirements (Windows Python has no zone database). Columns are still text:
  phase 2c-ii changes their type.
  **Suite:** IQ **1111 passed, 4 skipped**; JO **1111 passed, 4 skipped**.
- **2026-09-25 — Phase 2c-ii: event times are `timestamptz`.** 39 text
  columns holding ISO strings are `TIMESTAMPTZ` (`sales.sale_date` renamed
  `sold_at`, as §4.1 said; `users.password_changed_at` is NULL for "never",
  not `''`). What that took, beyond the type: every `LIKE 'YYYY-MM%'` and
  `substr(timestamp, …)` filter became an indexed range from
  `logic.day_bounds()` / `month_bounds()` / `month_dates()` in the clinic's
  zone (the rest of D9); `to_char` for month labels; a
  `COALESCE(timestamp, text)` and a `GREATEST(…, '')` that no longer type-check
  rewritten, the latter keeping its "no lower bound" meaning with
  `-infinity`; the Cash Register ledger's UNION made text on both sides; the
  edit-conflict token and the session's password-change token compared as
  instants (`clock.token` / `same_instant`) — as strings, a timestamp read back
  differs in form from the one written, and every save would have been a
  conflict and every user signed out; the heartbeat's JSON given a string; and
  ~20 template slices (`[:16]`, `[11:19]`, `.replace('T', ' ')`) replaced by
  `|localtime` / `|localdate`, which show the clinic's zone. A new test seeds
  one row of every kind whose time a page prints, renders each page and PDF,
  and fails if a raw ISO timestamp reaches a reader — the route smoke test
  renders them only on a near-empty database.
  **Suite:** IQ **1115 passed, 4 skipped**; JO **1115 passed, 4 skipped**; no
  database 481 passed.
- **Correction to the 2b entry above.** It says the POS stock "goes to the
  browser as a JSON number (a string would have turned a capped quantity plus
  one into "131")". Wrong: `app._DecimalJSONProvider` already turned every
  Decimal into a number, so stock was `13.0`, never `"13.000"`. Found in 2d
  when a mutation that should have produced the string did not; the helper
  that 2b added for it (`core.quantity_json`) was removed as dead code.
- **2026-09-25 — Phase 2d: numeric keys, shown as codes (D-2).** Every table
  that had a text id (`"V0042"`, `"U1A2B…"`, `"INV301"`) has an identity
  integer — users, roles, owners, patients, visits, inventory, price list,
  distributors, distributor bills — and the 68 columns that point at them are
  INTEGER; `permissions.id` stays text (it is the permission's name). Staff
  see codes: `logic.code("V", 123)` → `V-00123`, the `|code` filter, a `code`
  field in the patient search API; `parse_id(raw, prefix)` reads a typed code
  or number back and returns None for anything else, including a code for the
  wrong kind of record. `id_counters`, `db.next_id` and `import_seed.py` (a
  spreadsheet importer for an always-empty `seed_data.json`) are gone; setup
  creates the first admin with a printed one-time password instead of the
  public `admin/admin123`, reissued by setup until first sign-in.
  Integer ids broke things silently wherever text met a number, each fixed and
  pinned by a mutation-checked test: the inpatient non-discountable block
  (`text in set_of_ints` is never true — every blocked line would have gone
  through), the appointment vet check, the POS and visit-bill cart buttons
  (`dataset.lineId` is a string), `<select>` re-selection on an error page,
  a distributor edit that `!=`-compared text with an int and refused every
  consignment save, URL placeholders built with `'__ID__'` for `<int:>` routes,
  and JSON error keys. Found on the way and fixed: M10 (a visit's saved bill
  shown empty) — see the audit.
  **Suite:** IQ **1142 passed, 4 skipped**; JO **1142 passed, 4 skipped**; no
  database 498 passed.
- **2026-09-25 — Phase 3 (first part): the P&L is computed on read (D-3).**
  `reports.py` holds one query that yields every revenue and cost line with
  its month and category, apportioned from the STORED totals — a visit's
  `billing.total`, a sale's `sales.total`, an inpatient case's `total` (spread
  over its procedures' months), a stay's `billed_total` — minus refunds; costs
  from the lines' own snapshots, and a restock reverses the SALE LINE's cost.
  The Monthly and Yearly P&L and Insights' revenue by category all sum those
  lines, so they agree to the fils. `monthly_financial_summary`, its 16
  recompute calls, the Rebuild button and its route are gone — closing B2,
  B3, B14 and S5 (the unvalidated `return_to` lived on that route) and the
  P&L half of B9. Seam rule 8 had a blind spot since phase 1 (it knew `/ 100`
  but not money.py's `/ HUNDRED`, so it had never seen the shared formula);
  its floor reported it the moment the old report functions went.
  **Suite:** IQ **1151 passed, 4 skipped**; JO **1151 passed, 4 skipped**; no
  database 498 passed.

- **2026-09-25 — Audit S1 and S2: nobody reaches beyond their own access.**
  S2: `routes/admin.py` has one rule, `_beyond_actor()`: someone outside the
  system role may create, assign, edit, delete, disable or reset only within
  the permissions they hold themselves. It covers seven routes, including
  the long ways round (deleting your own role so its staff land in Admin;
  demoting an Admin). S1: `SETTING_FIELD_PERMISSION` in `routes/settings.py`
  is the one table of which permission each Settings field needs. The POST
  refuses the whole submission if it carries a field the user can't change,
  and the template draws fields from that same table. `tests/test_privileges.py`
  has 21 tests (guards with controls). Mutation-checked nine ways, and each
  mutation fails exactly its own route's tests. Two harness traps came to
  light on the way, and the fixture now guards against both. First, the
  app's 20-sign-ins-per-address limit silently refused the fixture's later
  sign-ins, so every POST bounced off the login gate and the guard tests
  "passed". Second, a broken guard let the escalation succeed, which left
  the Admin disabled or moved and failed every later test. Two new Arabic
  strings are flagged in `docs/ARABIC_REVIEW.md` §7.
  **Suite:** IQ **1172 passed, 4 skipped**; JO **1172 passed, 4 skipped**; no
  database 498 passed.
- **2026-09-25 — Audit B1, B4, B5, B8, and M11.**
  - **B1 (dates).** `core.strict_date()` is the one parser for a date in a
    request (exactly `YYYY-MM-DD`). The lenient parser is renamed
    `logic.as_date()` and reads stored values only. Seam rule 2 no longer
    counts it as validation, and a new rule 9 keeps it out of the request
    layer. Two write paths that took a date unchecked were fixed too: the
    audit sheet's expiry and the opex month.
  - **B4 (edit conflicts).** A conflict is refused again on the next Save. A
    panel lists what the other person saved (time, who, field, old → new,
    from the audit log), and "save mine over theirs" works only against the
    version the panel showed. The fix also closed three more ways to the same
    lost update:
    - a record's first edit was unguarded (`updated_at` was NULL);
    - four status buttons wrote columns the edit forms write without
      bumping `updated_at`, and a scan now holds every UPDATE of the three
      tables to that rule;
    - tokens were stored to the second.
  - **B5.** POS fails closed on a deactivated item.
  - **B8.** Already fixed in the JO-based tree; now pinned by a test.
  - **M11.** Found on the way: the sidebar highlighted only the pages left in
    `app.py`, because it compared blueprint endpoints by bare name.
    `nav_active()` takes full names and raises on an unknown one.

  New tests: `test_dates_strict.py`, `test_edit_conflicts.py`,
  `test_pos_deactivated.py`, `test_nav_active.py`, plus one in
  `test_exports.py`. Each guard was mutation-checked, and each blind mutation
  found on the way was redone. 13 new Arabic strings are flagged in
  `ARABIC_REVIEW.md` §8–10.
  **Suite:** IQ **1281 passed, 4 skipped**; JO **1281 passed, 4 skipped** (the
  B8 test was added after that run; it passes on its own).
- **2026-09-25 — Audit B10: every payment names how it was paid.**
  - `core.clean_payment_method()` is required on the clinic's own payments
    and optional on supplier payments. It is called on all eight reads.
  - There is a CHECK on the five method columns.
  - Seam rule 10 holds every future read to the check.
  - Found on the way: B12 reproduced. The database refusing a bad method
    produced a 500 page that then failed to render its globals on the
    aborted transaction. Still open, next in line.

  **Suite:** IQ **1322 passed, 4 skipped**; JO **1322 passed, 4 skipped**.
- **2026-09-25 — Audit B11 and B12.**
  - **B11.** Existence checks on the three POST routes that 500'd on a
    missing parent, and the two distributor redisplays handle a deleted
    distributor. The audit's own sweep (every parameterised POST route with
    an id that cannot exist) is now a test, so a fourth such route cannot be
    added. The daily-update and contact routes audit the new row's own id.
  - **B12.** `mark_transaction_failed()` rolls back at once, so an error page
    after a database error is in the clinic's language, under its name.

  **Suite:** IQ **1328 passed, 4 skipped**; JO **1328 passed, 4 skipped**.
- **2026-09-25 — Audit B15–B19, and owner decisions D-15 and D-16.**
  - **B15.** The cash payout takes a per-day advisory lock, and the retail
    refund locks the sale row. Both races are played deterministically by
    `test_locked_caps.py`.
  - **B16.** Refunds are dated between the day of what they pay back and
    today; payments record today.
  - **B17.** A refused booking re-opens on its own day.
  - **B18.** The audit sheet pre-fills Consignment Receiving.
  - **B19.** Wellness "due" ends where "missed" begins, a newer entry
    replaces the old one, and both screens show the most urgent first
    (D-16).
  - **Decisions.** The owner chose the full `vcs/` package restructure
    (D-15), next in line after the remaining audit items.
  - **Arabic.** Four new strings, flagged in `ARABIC_REVIEW.md` §12–13.

  **Suite:** IQ **1353 passed, 4 skipped**; JO **1353 passed, 4 skipped**.
