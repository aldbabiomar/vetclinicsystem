# VetClinicSystem IQ & JO — Orphaned Records Audit

**Scope:** every action or edge case that can leave a record in the database with no
reachable parent, no required children, or a reference that no longer resolves. Originally
audited against JO only (2026-08-24); extended to cover IQ the same day. Every finding was
re-verified against IQ's actual current code per `CLAUDE.md` §1-2 rather than assumed from
JO — several turned out to already be fixed in one app and not the other, one turned out to
be intentional, documented product design in IQ that doesn't exist in JO, and one new
IQ-only finding surfaced from a feature JO doesn't have (custom roles).

**Codebase reviewed (both apps):** `app.py` (~5400 lines each), `logic.py` (~2270 lines
each), `auth.py`, `attachments.py`, `db.py`, `schema_postgres.sql`, `backup.py`,
`reconcile_attachments.py`, all templates.

**Neither app is in production yet** (confirmed with the user 2026-08-24) — every
constraint below is written as a direct edit to `schema_postgres.sql` rather than an
`ALTER TABLE` migration, there is no existing data to clean up first, and nothing needs to
be phased around a live database. Severity language describes impact *once deployed*, not
damage already happening — the good news about finding all of this now.

---

## Executive summary

The schema is in good shape in both apps. Every parent→child link that matters has a real
FK, and Postgres's default `NO ACTION` means a classic dangling-FK orphan is impossible for
those columns. The delete surface is tiny and mostly guarded. The orphans in this codebase
come from five places instead:

1. **Crash-time partial commits.** `close_db()` commits when Flask hands it `exc=None`, and
   the global `@app.errorhandler(Exception)` guarantees `exc` is *always* `None`. Every
   route that has already written rows before a later failure has those rows committed
   anyway. Open, identical, in both apps — the single highest-value fix in this document.
2. **Parents saved without their required children**, because validation runs after the
   parent insert, or because a form field the code depends on isn't actually required. Two
   instances of this exact shape (F-02, F-03) were **already fixed in both apps** by
   unrelated work earlier today — direct evidence the rest of this document needed fresh
   verification, not a blind port.
3. **Rows made unreachable by an edit rather than a delete** — an inventory item's
   distributor cleared, a visit's case status changed, an item deactivated mid-audit, a
   custom role's vet-eligibility flipped (IQ-only, new finding F-25).
4. **Rows that never reach the reports they're supposed to feed** — a bill with a null
   `date_billed` is skipped outright by the P&L.
5. **Recovery tooling that fails open** — the restore/backup layer records its own state
   inside the database that a restore wipes, and the one existing orphan-repair script
   treats "no record of a restore" as "safe to proceed." Identical in both apps, except
   IQ's manual-backup route already sidesteps one of the two sub-bugs here (F-24).

25 findings below (F-01–F-24 from the original JO pass, plus new IQ-only F-25), each with
**JO status** and **IQ status** verified fresh against current code. F-02 and F-03 are
recorded as **resolved** rather than open — kept in the numbering, not deleted, so the fix
is documented. §Invariant checks at the end are queries to run against your QA database
after exercising the app — pre-deployment they're regression tests, not cleanup tools.
§Decisions records what was resolved with the user before this document was finalized.

**Severity key:** 🔴 data loss or money silently wrong · 🟠 record becomes unreachable ·
🟡 junk rows / degraded UX.

---

## 🔴 F-01 — Every unhandled exception commits the half-finished transaction

**Files:** `app.py` (`close_db`, `handle_unexpected_error`, `handle_bad_number`,
`handle_bad_phone`)

`close_db` is correct in isolation (`if exc is None: db.commit() else: db.rollback()`), but
Flask only passes an exception to teardown if it **escaped** `full_dispatch_request`.
`@app.errorhandler(Exception)` catches it and returns a rendered 500 page, so the exception
never escapes, so teardown receives `None`, so **`db.commit()` runs on a transaction that
failed halfway through.** Verified against the actual Flask version in both apps'
`requirements.txt` (`Flask>=3.0`, resolved 3.1.3) with a minimal repro: an errorhandler that
swallows an exception and returns a response still gets teardown called with `exc=None`.
`handle_bad_number`/`handle_bad_phone` have exactly the same effect — a `BadNumber` raised
*after* rows were already written also commits those rows, in both apps.

**JO status: open, unchanged.** `close_db()` (`app.py:277-297`) still does the naive
`if exc is None: commit() else: rollback()`. No `mark_transaction_failed()`/`g.db_failed`
flag exists anywhere (grepped `errorhandler`, `db_failed`, `mark_transaction_failed` — zero
hits beyond the handler registrations). `handle_unexpected_error()` still passes
`HTTPException` straight through before reaching any failure-marking. No
`@app.errorhandler(HTTPException)` exists to catch non-GET aborts.

**IQ status: open, identical.** Same `close_db()` shape, same missing flag mechanism, same
`HTTPException` passthrough. IQ additionally registers
`@app.errorhandler(dbmod.NumericValueOutOfRange)` (see `ERROR_500_AUDIT.md` E-06) but that
handler has the same "flash and redirect after possible partial writes" shape — doesn't
change this finding.

**Fix (both apps, identical):**

```python
# app.py — near get_db()
def mark_transaction_failed():
    g.db_failed = True

# in handle_unexpected_error(), handle_bad_number(), handle_bad_phone(),
# as the first statement of each:
    mark_transaction_failed()

# close_db()
def close_db(exc):
    db = g.pop("db", None)
    failed = g.pop("db_failed", False)
    if db is not None:
        try:
            try:
                if exc is None and not failed:
                    db.commit()
                else:
                    db.rollback()
            except Exception:
                error_logger.error("close_db(): commit/rollback failed\n" + traceback.format_exc())
        finally:
            dbmod.putconn(db)
```

`handle_unexpected_error` passes `HTTPException` straight through (`return e`) before
reaching that point — 404s, 403s, and `BadRequestKeyError` take that path. Add a handler so
aborts also roll back:

```python
@app.errorhandler(HTTPException)
def handle_http_exception(e):
    if request.method != "GET":
        mark_transaction_failed()
    return e
```

**Verification:** add a `/health/rollback-test` route (dev only) that inserts an owner then
raises; confirm no row lands. Do this in both apps' isolated test environments.

---

## 🔴 F-02 — `_create_visit()` returns a redirect object where the caller expects a visit ID

**RESOLVED — fixed in both apps today**, by unrelated work (the form-data-loss fix earlier
this session). Recorded here rather than deleted, per the standing rule not to rewrite
history in these documents.

**Original bug:** `_create_visit()` caught `BadDate` internally and did
`return redirect(request.referrer or url_for("dashboard"))` — a `Response` object. Callers
did `vid = _create_visit(...); return redirect(url_for("visit_detail", visit_id=vid))`,
so `url_for` stringified the `Response` into the URL. Three consequences: an orphaned
patient in `visit_new_patient` (owner+patient committed before `_create_visit` was called —
see F-03), a broken redirect to a 404, and a burned `V`-number on every failed attempt.

**Confirmed fixed, both apps, by direct read of current code:** `_create_visit()` no longer
catches `BadDate`/`BadNumber` — a new `_parse_visit_fields()` helper does the parsing and
*raises*, and both callers (`visit_new_existing()`, `visit_new_patient()`) now catch the
exceptions themselves. JO: `app.py:1882-1909` (`_create_visit`), `1855-1879`
(`_parse_visit_fields`), `1771-1779`/`1799-1806` (callers). IQ: `app.py:1918-...`
(`_create_visit`), `1883-1898` (`_parse_visit_fields`), `1799-1834` (callers) — confirms IQ
never had this bug shape to begin with; it already raised rather than swallowed, in a
similarly-structured but independently-written version of the same function.

**One residual sub-issue neither app's fix addresses, worth a small follow-up:** inside
`_create_visit()`, `vid = dbmod.next_id(db, "V")` (JO `app.py:1883`, IQ `app.py:1918`) still
runs *before* `_parse_visit_fields(f)` on the next line. For `visit_new_existing()` (which
doesn't pre-validate before calling `_create_visit`), a `BadDate`/`BadNumber` there still
burns a V-number, even though the orphan/broken-redirect bug itself is fixed. Not data loss,
just an ID gap — low priority, not separately numbered.

**Divergence worth knowing if porting either function further:** IQ's
`_parse_visit_fields()` has an extra `if has_negative(weight_kg): raise BadNumber(...)`
check JO's does not.

---

## 🔴 F-03 — `visit_new_patient` commits owner+patient before the visit is attempted

**RESOLVED — fixed in both apps today**, alongside F-02, by the same unrelated work.

**Original bug:** the sequence was insert/lookup owner → insert patient → `db.commit()` →
create the visit. Anything failing at the last step left a committed owner+patient with no
visit — and since there's no `/patients/new` route in either app (a patient only exists
because a visit was being created), a patient with zero visits is an orphan by definition.

**Confirmed fixed, both apps:** `_parse_visit_fields(f)` is now called and any
`BadDate`/`BadNumber` handled *before* the owner/patient `INSERT` + `db.commit()`. JO
`app.py:1800` (validate) / `1826-1844` (write+commit). IQ `app.py:1828` (validate) /
`1854-1872` (write+commit). Comments in both files document the ordering explicitly as the
fix.

**Still open, both apps — the `IntegrityError` fallback inside the same function.** F-03's
original write-up also discussed the duplicate-phone-race recovery path:

```python
except dbmod.IntegrityError:
    db.rollback()
    oid = db.execute("SELECT id FROM owners WHERE phone=?", (owner_phone,)).fetchone()["id"]
```

This is **the same bug as `ERROR_500_AUDIT.md`'s E-12** — unguarded, assumes the `SELECT`
always finds a row, breaks if the violation was a different constraint or if `owner_phone`
is `None`. Confirmed still present, unguarded, in both apps: JO `app.py:1829-1836`, IQ
`app.py:1853-1864`. **Fix once, in that document (E-12) — not duplicated here.** Flagging
the cross-document overlap explicitly so it isn't tracked (or fixed) twice.

---

## 🔴 F-04 — No `BadDate` error handler, and one `clean_date()` call is uncaught

**First half — missing handler: open, both apps.** `BadNumber` and `BadPhone` both have a
registered `@app.errorhandler`. `BadDate` does not, in either app.

**Second half — the specific uncaught inline call: now fixed in both apps, as a side effect
of the F-02/F-03 restructuring.** The call the original finding pointed at (an inline
`clean_date()` for `wellness_next_dose_date`, buried in `_create_visit`'s INSERT argument
list) now lives inside `_parse_visit_fields()`, which both callers wrap in
`try/except BadDate`. Checked every `clean_date(` call site in both files (25 each) against
its enclosing `try/except BadDate` — all 25 covered, in both apps. The specific bug no
longer reproduces; the missing safety-net handler is still worth having (defense-in-depth
against a future call site that forgets to wrap it, same rationale as the existing
`BadNumber`/`BadPhone` handlers) but is not currently an active bug in either app.

**Fix (both apps, identical, for the handler):**

```python
@app.errorhandler(BadDate)
def handle_bad_date(e):
    mark_transaction_failed()
    flash(str(e), "error")
    return _fallback_redirect()
```

---

## 🔴 F-05 — A service refund can be recorded against nothing, with no cap

**File:** `app.py` (`refund_service_save`), `templates/refunds.html`

Both the Visit ID and Inpatient Case ID fields on the service-refund form are optional, and
every cap check sits inside `if visit_id:` / `if case_id_raw:`. Submit with both blank and
you get a `refunds` row with `refund_type='service'`, both anchors `NULL`, **any amount**,
which immediately reduces that month's revenue. Second problem: both fields can be filled at
once, double-counting against both the visit's and the case's caps.

**JO status: open, exactly as originally described.** `refund_service_save()`
(`app.py:5408-5483`): independent `if visit_id:` (5442) / `if case_id_raw:` (5456) gating,
INSERT at 5473-5477 proceeds with both anchors `NULL` if both are blank.

**IQ status: was structurally different — an explicit, documented, intentional design
choice, not an oversight.** IQ's `refund_service_save()` (`app.py:5496-5584`) has the same
independent gating, but at `app.py:5547-5552` carries a comment stating an unanchored
service refund is deliberately supported ("a general refund for a reason unrelated to a
specific record"), with the cap check gated on `if visit_id or case_id:` so an unanchored
refund is deliberately uncapped.

**Decision (resolved 2026-08-24, after discussion — see §Decisions):** align IQ to the same
rule as JO. The clinic already has a Cash Register page that can document a goodwill
payout/refund outside the visit/case-billing system if that scenario ever comes up, so the
app doesn't need a first-class "refund anchored to nothing" path to support it. IQ's
"intentional" comment is being treated as a design choice that shouldn't have shipped, not a
capability worth preserving as-is — **remove the unanchored path in IQ, apply the same
anchor requirement as JO.**

**Still shared in both apps regardless of the above:** neither guards against `visit_id`
*and* `case_id_raw` both being set at once (double-counted against both caps) — that half is
a plain bug in both, independent of the anchor-optionality question.

**Fix (both apps, now identical):**

```python
if bool(visit_id) == bool(case_id_raw):
    flash("A service refund must be linked to exactly one visit OR one inpatient case.", "error")
    return redirect(url_for("refunds_page"))
```

In `schema_postgres.sql`, as a table-level constraint at the end of the `refunds`
`CREATE TABLE`, both apps:

```sql
    -- A refund always reverses exactly one thing: a POS sale (retail), or
    -- one visit or one inpatient case (service). A goodwill/no-specific-record
    -- refund is handled through Cash Register instead, not this table.
    CONSTRAINT refunds_anchor_ck CHECK (
        (refund_type = 'retail'  AND sale_id IS NOT NULL
            AND visit_id IS NULL AND inpatient_case_id IS NULL)
     OR (refund_type = 'service' AND sale_id IS NULL
            AND (visit_id IS NOT NULL) <> (inpatient_case_id IS NOT NULL))
    )
```

Also mark the two form inputs as a required either/or in `refunds.html`, both apps, so the
UI stops advertising them as optional. **For IQ specifically**, also remove the
`app.py:5547-5552` comment and the `if visit_id or case_id:` cap-skip — the code path it
justified no longer exists once the constraint above lands.

---

## 🔴 F-06 — A bill with no `date_billed` never reaches the P&L

**Files:** `logic.py` (`_revenue_and_cogs_by_month`), `app.py` (`visit_billing_save`),
`templates/visit_detail.html`

```python
for r in db.execute("SELECT visit_id, billing_type, date_billed, total FROM billing" ...):
    if not r["date_billed"]:
        continue                      # ← silently dropped from revenue AND cogs
```

`visit_billing_save` accepts a blank Date Billed, and the template's default is `visit.date`
— itself nullable. Save a bill, take payments, collect the money — the revenue never appears
in Monthly or Yearly P&L, forever, with nothing flagging it.

**JO status: open, unchanged.** `logic.py:906` — the `continue`. `visit_billing_save`
(`app.py:2160-2163`) has no fallback when `date_billed` parses to `None`.
`templates/visit_detail.html:113` — no `required` attribute.

**IQ status: open, identical.** `logic.py:915` — same `continue`. `visit_billing_save`
(`app.py:2201-2204`) — same missing fallback. Same template gap (shared file, confirmed
identical in both apps' copies). No dashboard warning for
`billing WHERE date_billed IS NULL AND total > 0` exists in either app.

**Fix (both apps, identical):**

```python
# app.py, visit_billing_save() — after date_billed is parsed
if not date_billed:
    date_billed = (visit_row["date"] or date.today().isoformat())
```

```html
<!-- templates/visit_detail.html -->
<input type="date" name="date_billed" required
       value="{{ billing.date_billed if billing else (visit.date or today) }}">
```

Plus a Dashboard warning (same panel as the missed-items list) counting
`billing WHERE date_billed IS NULL AND total > 0`, both apps.

---

## 🔴 F-07 — Editing an item's distributor silently re-assigns its consignment history

**Files:** `app.py` (`inventory_catalog_edit`, `inventory_catalog_bulk_edit`), `logic.py`
(`consignment_balance`, `consignment_item_locked`)

The Consignment Items screen calls `consignment_item_locked()` before touching
`distributor_id` on a locked item. The **Inventory Catalog** screen writes the same column
with no lock check at all. That matters because `consignment_balance()` is asymmetric about
where it reads the distributor from — sales via the item's *current* `distributor_id`,
shrinkage via the *snapshot* on the shrinkage row — so re-pointing one item from Distributor
A to B moves every past sale's cost to B while leaving A's shrinkage/receipts/returns
behind, wrong in opposite directions. Clearing it to blank is worse: the distributor can
disappear from the Consignment Overview entirely if that was its only consignment item,
along with its receipts, shrinkage, returns, settlements, and any unpaid residual. And
`_consignment_item_choices()` inner-joins `distributors`, so an item left `Consignment` with
a NULL `distributor_id` vanishes from the Receiving/Shrinkage/Returns pickers while still
selling as consignment stock.

**JO status: open, unchanged.** No lock check in `inventory_catalog_edit`/
`inventory_catalog_bulk_edit` (`app.py:2759-2795` / `2798-2869`). Asymmetry present in
`logic.py:1485-1520`.

**IQ status: open, identical shape.** Same missing lock check
(`app.py:2874-2910` / `2821-2869`). Same asymmetry, worded almost identically, in
`logic.py:2109-2145`.

**Decision (resolved 2026-08-24):** add the `distributor_id` guard (both apps) **and**
snapshot `distributor_id` on `sale_items` at checkout, the same way `unit_cost` already is
— this makes both `consignment_balance()` terms historically stable, closing the underlying
asymmetry rather than just working around it. No migration cost since neither app is
deployed. See §Decisions.

**Fix — the guard (both apps, identical):**

```python
# in both inventory_catalog_edit() and inventory_catalog_bulk_edit(),
# before building new_vals:
requested_dist = f.get("distributor_id") or None
if requested_dist != old["distributor_id"] and logic.consignment_item_locked(db, item_id):
    flash("This item has consignment activity against it — its distributor can't be "
          "changed here. Create a new inventory item for the new supply source.", "error")
    return redirect(url_for("inventory_catalog"))      # or errors[item_id] = ... in bulk
```

**Fix — the schema, both apps:**

```sql
    -- A Consignment item is by definition somebody's stock — the whole
    -- consignment layer (balance, overview, the receiving/shrinkage/
    -- returns pickers) inner-joins distributors, so an item in this state
    -- with no distributor silently disappears from all of it while still
    -- selling as consignment stock.
    CONSTRAINT inventory_consignment_needs_distributor_ck
        CHECK (ownership_type <> 'Consignment' OR distributor_id IS NOT NULL)
```

**Fix — the snapshot (both apps, both `sale_items` DDL and checkout write path):**

```sql
-- sale_items, alongside unit_cost
distributor_id TEXT REFERENCES distributors(id)
```

```python
# pos_checkout(), wherever unit_cost is snapshotted per line — snapshot
# distributor_id the same way, from the item's distributor_id at sale time
```

```python
# logic.py — consignment_balance(): read sale attribution from
# sale_items.distributor_id (the historical snapshot) instead of joining
# to inventory_list.distributor_id (the item's current value)
```

---

## 🟠 F-08 — `distributor_delete` doesn't check the four consignment tables

**File:** `app.py` (`distributor_delete`)

`consignment_receipts`, `consignment_shrinkage`, `consignment_returns` and
`consignment_settlements` all `REFERENCES distributors(id)` and none was originally checked
— normally an item still points at the distributor and the `inventory_list` check catches
it, but F-07 makes "distributor with consignment history and zero inventory rows" reachable,
and then this route raises a raw `ForeignKeyViolation`.

**JO status: open, exactly as described.** `app.py:3107-3127` — `still_linked` loop only
checks `inventory_list` and `distributor_bills`.

**IQ status: already fixed.** `app.py:3206-3226` — the loop already checks all six tables
(`inventory_list`, `distributor_bills`, `consignment_receipts`, `consignment_shrinkage`,
`consignment_returns`, `consignment_settlements`), with a comment citing the same rationale
this finding describes ("same failure mode `admin_role_delete()` already guards against for
roles"). **Confirmed divergence — IQ independently fixed this, JO did not.** Port IQ's
version into JO directly; no adaptation needed, the check shape doesn't depend on
money type.

**Fix (JO — copy IQ's list verbatim):**

```python
for label, table in [("inventory item(s)",       "inventory_list"),
                     ("distributor bill(s)",     "distributor_bills"),
                     ("consignment receipt(s)",  "consignment_receipts"),
                     ("consignment shrinkage log(s)", "consignment_shrinkage"),
                     ("consignment return(s)",   "consignment_returns"),
                     ("consignment settlement(s)", "consignment_settlements")]:
```

---

## 🟠 F-09 — Changing an item's category strands it outside every consignment screen

**File:** `app.py` (`inventory_catalog_edit`/`inventory_catalog_bulk_edit`)

Flip a Consignment item from Retail to Medical and: `/consignment/items` filters
`WHERE i.category='Retail'`, so the item is no longer listed — meaning you can't flip it
back to Owned from the only screen that offers that control; POS only sells Retail, so shelf
stock is stranded; the distributor overview has no category filter, so it keeps showing an
owed balance for stock nobody can sell or return.

**JO status: open, unchanged.** Same routes referenced in F-07 — no block on `category`
change while `ownership_type == 'Consignment'`.

**IQ status: open, identical.** Same gap, same routes.

**Fix (both apps, identical):**

```python
if new_vals["category"] != old["category"] and old["ownership_type"] == "Consignment":
    flash("Set this item back to Owned on the Consignment Items page before changing "
          "its category.", "error")
    return redirect(url_for("inventory_catalog"))
```

---

## 🟠 F-10 — A visit's case status and its inpatient case drift apart

**File:** `app.py` (`visit_edit`, `_create_inpatient_case`)

An `inpatient_cases` row is only ever created at visit-creation time (when `admit_inpatient`
is ticked). `visit_edit` then lets `case_status`/`visit_type` be set to anything the form
offers, with no corresponding action — set `case_status = 'Admitted to Inpatient'` on an
existing visit and there's no inpatient case to open (the animal is invisible to
`/inpatient`); move an admitted visit's status away from that and the `inpatient_cases` row
stays `dismissed=false` forever, denying the admission ever happened while sitting on the
active list.

**JO status: open, unchanged.** `app.py:1994-2071` — code is essentially identical to IQ
here.

**IQ status: open, identical.** `app.py:2034-2110`+ — same gap. Only cosmetic difference:
on a stale-edit conflict, JO calls `redisplay()`, IQ redirects — irrelevant to this finding.

**Fix (both apps, identical shape):**

```python
was_admitted = visit["case_status"] == "Admitted to Inpatient"
now_admitted = new_case_status == "Admitted to Inpatient"
existing_case = db.execute(
    "SELECT id, dismissed FROM inpatient_cases WHERE visit_id=? ORDER BY id DESC LIMIT 1",
    (visit_id,)).fetchone()

if now_admitted and not existing_case:
    _create_inpatient_case(db, visit["patient_id"], visit_id,
                           f.get("complaint"), edited_date or visit["date"],
                           edited_weight_kg, edited_bcs)
    flash("An inpatient case was opened for this visit.", "success")
elif was_admitted and not now_admitted and existing_case and not existing_case["dismissed"]:
    flash(f"Inpatient case #{existing_case['id']} is still open for this visit — "
          f"dismiss it there first, or leave the status as Admitted to Inpatient.", "error")
    return redirect(url_for("visit_edit", visit_id=visit_id))
```

Also validate `case_status in CASE_STATUSES` and `visit_type in ("Outpatient","Inpatient")`
before the UPDATE — see `ERROR_500_AUDIT.md` E-07, same finding from the crash side.

---

## 🟠 F-11 — Audit lines for an item deactivated mid-draft become invisible and unfixable

**File:** `app.py` (`audit_session_view`, `_save_audit_lines`)

Both the render and the save iterate `WHERE active=true`. Deactivate an item after a draft
line was saved for it and that line is no longer rendered, editable, or re-saved — but it's
still there, and confirming the session locks it in while it stays invisible on the session
view. Reverse case: deactivating *between* page render and Save drops the counts a
technician just typed, silently, with a success flash.

**JO status: open, unchanged.** `app.py:3945` (render), `3974` (`_save_audit_lines`) —
both `WHERE active=true`.

**IQ status: open, identical.** `app.py:3901`, `3930` — same shape.

**Fix (both apps, identical):**

```python
ITEMS_FOR_SESSION = """
    SELECT i.* FROM inventory_list i
    WHERE i.active = true
       OR EXISTS (SELECT 1 FROM audit_session_lines l
                   WHERE l.session_id = ? AND l.item_id = i.id)
    ORDER BY i.category, i.name
"""
```

Use it in both places, and mark inactive ones in `audit_session_view.html` with a
"(deactivated)" badge, both apps.

---

## 🟠 F-12 — Attachment rows with no file, and no tooling to find them

**Files:** `attachments.py`, `reconcile_attachments.py`, `app.py` (`serve_attachment`)

`reconcile_attachments.py` only solves one direction (files on disk with no DB row); the
reverse — a row whose file is gone — has no detection at all, and `uploads/` is not part of
the database backup. `serve_attachment` checks the row exists, then hands off to
`send_from_directory`, which raises a bare 404 with no indication the *record* is fine and
only the file is missing.

**JO status: open, unchanged.** No `--check-missing` mode in `reconcile_attachments.py`.
`serve_attachment()` (`app.py:2324-2330`) — no existence pre-check.

**IQ status: open, identical gap.** Same missing reverse-mode. `serve_attachment()`
(`app.py:2359-2371`) — same missing pre-check (IQ's version has an unrelated added
permission-gate comment, doesn't touch this finding).

**Fix (both apps, identical):**

```python
# reconcile_attachments.py — new --check-missing mode
rows = db.execute("SELECT id, patient_id, visit_id, inpatient_case_id, "
                  "relative_path, original_name, uploaded_at FROM attachments").fetchall()
missing = [r for r in rows
           if not os.path.isfile(os.path.join(attach_mod.UPLOAD_ROOT, r["relative_path"]))]
```

Report only by default; never auto-delete a row.

```python
# serve_attachment()
disk_path = os.path.join(attach_mod.UPLOAD_ROOT, relpath)
if not os.path.isfile(disk_path):
    flash("This file's record exists but the file itself is missing from the uploads "
          "folder — it may not have been included in a backup/restore. "
          "Check with whoever manages backups before re-uploading.", "error")
    return redirect(request.referrer or url_for("dashboard"))
```

---

## 🟠 F-13 — Attachments with neither a visit nor an inpatient case are unreachable

**Files:** `schema_postgres.sql` (`attachments`)

`visit_id`/`inpatient_case_id` are both nullable, no CHECK. `list_attachments()` only ever
queries by one or the other, so a row with both NULL is invisible everywhere, and so is its
file. `attachment_delete` already has a fallback branch for exactly this state — anticipated
but never prevented. `save_attachment` can't produce it today, but a manual import or a
future bulk-upload feature could.

**JO status: open, unchanged.** No CHECK in `schema_postgres.sql`.

**IQ status: open, identical.** Same nullable columns, no CHECK.

**Fix (both apps, identical):**

```sql
    -- list_attachments() only ever queries by visit_id OR
    -- inpatient_case_id, so a row with neither is invisible everywhere —
    -- and so is the clinical file it points at.
    CONSTRAINT attachments_one_anchor_ck
        CHECK ((visit_id IS NOT NULL) <> (inpatient_case_id IS NOT NULL))
```

---

## 🟠 F-14 — Payments with no anchor, or against a bill whose lines were all removed

**Files:** `schema_postgres.sql` (`payments`), `app.py` (`inpatient_billing_delete`,
`visit_billing_save`)

**No anchor.** `payments` has `visit_id`/`inpatient_case_id`/`boarding_id`, all nullable,
nothing requiring exactly one. `cash_register_totals` would count a row with all three NULL
against no record at all.

**Stranded above a zeroed bill.** `inpatient_billing_delete` removes lines one at a time and
recomputes the total; delete every line from a case with existing payments and `total`
becomes 0 while the payments stay. Same for `visit_billing_save` re-saved with a shorter
cart. No delete/edit route exists for a payment (deliberately), and nothing surfaces
`paid > total`.

**JO status: open, both sub-issues.** No CHECK in schema (`schema_postgres.sql:574-591`).
`inpatient_billing_delete` (`app.py:4875-4888`) — no `paid > remaining_total` guard.

**IQ status: open, identical, both sub-issues.** No CHECK (`schema_postgres.sql:484-509` —
IQ has an added comment block there about `ON DELETE` FK semantics, unrelated to an
anchor-count constraint; confirmed no CHECK exists anywhere in the DDL). `app.py:4879-4892`
— same missing guard.

**Fix — schema (both apps):**

```sql
    -- Every payment belongs to exactly one of the three billable record
    -- types. All three columns are nullable so any one of them can be
    -- used; nothing previously stopped a row from using none of them,
    -- which cash_register_totals() would still have counted.
    CONSTRAINT payments_one_anchor_ck CHECK (
        (visit_id IS NOT NULL)::int
      + (inpatient_case_id IS NOT NULL)::int
      + (boarding_id IS NOT NULL)::int = 1
    )
```

**Fix — the overpay guard (both apps):**

```python
# inpatient_billing_delete(), before the DELETE
paid = logic.inpatient_billing_summary(db, case_id)["paid"]
remaining_total = ...  # recompute excluding this line
if paid > remaining_total:
    flash(f"Removing this line would leave {logic.fmt_money(paid)} paid against a "
          f"{logic.fmt_money(remaining_total)} bill. Process a service refund for the "
          f"difference first.", "error")
    return redirect(url_for("inpatient_detail", case_id=case_id))
```

Mirror in `visit_billing_save`, both apps. (IQ: `fmt_money` already handles IQD formatting;
JO: JOD — no change needed to the fix shape itself, `logic.fmt_money` already knows its own
app's currency.)

---

## 🟡 F-15 — Abandoned draft audit sessions accumulate with no way to remove them

**Files:** `logic.py` (`get_or_create_draft_session`), `app.py` (`audit_session_start`)

Clicking **Start** commits an empty session immediately. The reuse query is scoped to
`audit_date = today`, so an abandoned draft from any previous day is never picked up again —
and there is no delete route for audit sessions anywhere. Related: confirming an all-blank
session is also allowed, producing an immutable Confirmed session with zero lines.

**JO status: open, unchanged.** `logic.py:70-84` — commits immediately. No delete route.

**IQ status: open, identical.** `logic.py:67-...` — same shape. No delete route.

**Decision (resolved 2026-08-24):** manual delete only for now, no automatic nightly purge
— a technician's in-progress count shouldn't vanish because of a long weekend. See
§Decisions.

**Fix (both apps, identical):**

```python
# audit_session_confirm() — refuse an empty confirm
filled = db.execute("SELECT COUNT(*) c FROM audit_session_lines "
                    "WHERE session_id=? AND stock_counted IS NOT NULL",
                    (session_id,)).fetchone()["c"]
if not filled:
    flash("Nothing has been counted in this audit yet — fill in at least one item "
          "before confirming.", "error")
    return redirect(url_for("audit_session_view", session_id=session_id))
```

```python
# new route: delete an empty draft
@app.route("/audit-history/session/<int:session_id>/delete", methods=["POST"])
@auth.permission_required("manage_audit_history")
def audit_session_delete(session_id):
    db = get_db()
    sess = db.execute("SELECT status FROM audit_sessions WHERE id=?", (session_id,)).fetchone()
    if not sess or sess["status"] != "Draft":
        flash("Only a draft audit can be discarded.", "error")
        return redirect(url_for("audit_history_list"))
    db.execute("DELETE FROM audit_session_lines WHERE session_id=?", (session_id,))
    db.execute("DELETE FROM audit_sessions WHERE id=?", (session_id,))
    auth.log_change(db, "audit_sessions", str(session_id), "delete")
    db.commit()
    flash("Draft audit discarded.", "success")
    return redirect(url_for("audit_history_list"))
```

No scheduler-based automatic cleanup, per the decision above.

---

## 🟡 F-16 — A discount on an unbilled visit creates an empty `billing` row

**File:** `app.py` (`visit_discount_save`)

The UPSERT inserts if there's no existing row — applying a discount to a never-billed visit
creates a childless `billing` row (`total = 0`, no lines, no `date_billed`). Harmless to the
P&L (F-06's `continue` skips it), but a childless artifact row that makes the audit-log
"create"/"update" distinction wrong and displays a discount against a bill that doesn't
exist.

**JO status: open, unchanged.** `app.py:2111` — UPSERT with no existing-bill guard.

**IQ status: open, identical.** Same route, same gap.

**Fix (both apps, identical):**

```python
existing = db.execute("SELECT * FROM billing WHERE visit_id=?", (visit_id,)).fetchone()
if not existing:
    flash("Save the bill first — a discount needs something to apply to.", "error")
    return redirect(url_for("visit_detail", visit_id=visit_id))
```

Then the statement can be a plain `UPDATE`, and the `ON CONFLICT` complexity goes away.

---

## 🟡 F-17 — Moving a vet to a non-vet role orphans their appointments with no warning

**Files:** `app.py` (`admin_user_role`, `admin_user_toggle`)

`admin_user_toggle` gets this right — it counts future appointments and flashes a heads-up.
`admin_user_role` produces the identical outcome (`day_grid` only builds columns for users
whose role has `is_vet_role=true`) and says nothing.

**JO status: open, unchanged.** `app.py:1089-1097` has the warning; `1103-1125` doesn't.

**IQ status: open, identical.** `app.py:1118-1126` / `1132-1154` — same shape.

**Note:** this gap is reachable more often in IQ, since IQ supports arbitrary custom roles
(JO has only 3 fixed roles) — see the related but distinct new finding **F-25** below, which
covers the role-*definition*-level version of this same problem (unique to IQ).

**Fix (both apps, identical):**

```python
def _warn_orphaned_appointments(db, user_id):
    n = db.execute("SELECT COUNT(*) c FROM appointments "
                   "WHERE resource_type='vet' AND resource_id=? AND appt_date >= ?",
                   (user_id, date.today().isoformat())).fetchone()["c"]
    if n:
        flash(f"Heads up: {n} upcoming appointment(s) were booked against this person — "
              f"they won't show on the Appointments grid anymore. Check Appointments for "
              f'the "need attention" list to reschedule them.', "error")
```

---

## 🟡 F-18 — `orphaned_appointments()` only looks forward from today

**File:** `logic.py`

`WHERE a.appt_date >= ?` (today). Correct as the guaranteed-to-exist fallback, but a booking
that became unreachable *and* whose date has since passed is invisible permanently, and
there's no other page listing appointments by id.

**JO status: open, unchanged.** `logic.py:1899-1924`.

**IQ status: open, identical.** `logic.py:1854-1880` (cosmetic-only difference: IQ's
docstring references `vet_users(db)` directly, JO's computes `active_vet_ids` inline).

**Fix:** low priority; a "show past unreachable bookings" toggle on the Appointments page,
both apps, worth doing alongside F-17/F-25 since it's the same screen.

---

## 🟠 F-19 — Fourteen user-referencing columns have no foreign key

**File:** `schema_postgres.sql`

`visits.created_by`, `billing.discount_applied_by`, `boarding_sessions.created_by`,
`boarding_incidents.user_id`, `inpatient_cases.created_by`/`discount_applied_by`,
`inpatient_updates.user_id`, `inpatient_contact_log.staff_user_id`,
`inpatient_billing.logged_by`, `inventory_transactions.user_id`,
`sales.discount_applied_by`, `refunds.processed_by`, `appointments.resource_id`/`created_by`
all hold a `users.id` with no constraint behind it. (`login_log.user_id` and
`audit_log.user_id` are correctly excluded — a log entry should outlive its subject.)
Nothing dangles today, because neither app has a delete-user route (deactivate only), but
the protection is accidental and evaporates the moment anyone adds a delete-user feature or
runs a manual `DELETE FROM users`. `appointments.resource_id` already demonstrates the
shape of the problem — `orphaned_appointments()` exists precisely because that reference can
stop resolving.

**JO status: open — all 14 confirmed missing.**

**IQ status: open, identical — all 14 independently re-confirmed missing** by direct read of
each column (not assumed from JO):
`visits.created_by`, `billing.discount_applied_by`, `boarding_sessions.created_by`,
`boarding_incidents.user_id`, `inpatient_cases.created_by`/`discount_applied_by`,
`inpatient_updates.user_id`, `inpatient_contact_log.staff_user_id`,
`inpatient_billing.logged_by`, `inventory_transactions.user_id`,
`sales.discount_applied_by`, `refunds.processed_by`, `appointments.resource_id`/`created_by`
— none has a FK in IQ's schema either. (IQ does already have FKs on a few *different*
columns not in this list — `distributor_bills.created_by`, `distributor_bill_payments
.created_by`, `consignment_shrinkage.logged_by`, `cash_register_payouts.logged_by`,
`payments.user_id` — pre-existing, unrelated to F-19's specific 14, not partial progress on
this finding.)

**Decision (resolved 2026-08-24): `RESTRICT`, not `SET NULL`.** Matches how both apps
already behave today (deactivate, never delete) — more honest about current design than
leaving room for a future erasure feature that doesn't exist yet. See §Decisions.

**Fix (both apps, identical shape, `RESTRICT` per the decision above):**

```sql
-- visits
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT

-- appointments  (resource_id is the one that already demonstrably orphans —
-- logic.orphaned_appointments() exists because this reference can stop resolving)
    FOREIGN KEY (resource_id) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by)  REFERENCES users(id) ON DELETE RESTRICT

-- ...and the same shape for the remaining eleven, both apps
```

Since there's no real seed data in either app yet (per §Decisions on F-23), no need to
special-case a seed-run's `created_by` handling here.

---

## 🔴 F-20 — The restore safety cutoff lives inside the table the restore wipes

**Files:** `backup.py` (`_run_restore_locked`, `_try_log_restore`),
`reconcile_attachments.py` (`restored_backup_snapshot_time`)

`reconcile_attachments.py`'s entire safety argument rests on knowing *when* the restored
backup was taken, read from `restore_log` — but `pg_restore --clean` drops and recreates
**every table, including `restore_log`**. The row recording the restore is written *after*
the wipe by `_try_log_restore`, which is explicitly best-effort. If the process dies in that
window (power cut, a force-quit on a hung-looking restore), the restore happened but left no
record — `restored_backup_snapshot_time()` returns `None`, and the script's fail-open
message ("No successful restore on record — every orphaned file ... is safe to readopt") is
exactly backwards: IDs were rewound, and the script will cheerfully attach a previous
patient's file to an unrelated animal's record — the precise outcome it exists to prevent.

**JO status: open, unchanged.** No marker-file mechanism in `backup.py`.
`restored_backup_snapshot_time()` and the fail-open message unchanged.

**IQ status: open, identical.** Same absence, same fail-open message, word-for-word.

**Decision (resolved 2026-08-24):** write the marker on every app boot (not an
`--assume-no-restore` escape hatch) — makes "no restore has happened" provable rather than
assumed, at the cost of one small write added to the startup path. See §Decisions.

**Fix (both apps, identical except the env var name, which already differs per app
everywhere else in each `backup.py`):**

```python
# backup.py — new, called immediately before _run_pg_restore()
# IQ: os.environ.get("VETCLINICSYSTEMIQ_DATA_DIR")
# JO: os.environ.get("VETCLINICSYSTEMJO_DATA_DIR")
def _write_restore_marker(dump_path, started):
    data_dir = os.environ.get("VETCLINICSYSTEM{APP}_DATA_DIR") or BASE_DIR
    path = os.path.join(data_dir, "last_restore.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"source_file": dump_path,
                   "started_at": started.isoformat(timespec="seconds"),
                   "status": "in_progress"}, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)          # atomic
```

Update to `"status": "success"` alongside `_try_log_restore`. Additionally, per the
decision, write (or touch) the same marker file at app startup with
`{"status": "no_restore_since_boot", "checked_at": <now>}` whenever no `in_progress`/
`success` marker already exists — this is what makes "no restore has happened" a provable
fact rather than an absence of evidence.

```python
def restored_backup_snapshot_time(db):
    from_log    = _cutoff_from_restore_log(db)
    from_marker = _cutoff_from_marker_file()
    candidates = [c for c in (from_log, from_marker) if c]
    return max(candidates) if candidates else None
```

And make the genuinely-no-record branch fail closed rather than open:

```python
if not cutoff:
    print("No restore cutoff could be determined. Every orphaned file will be flagged for\n"
          "manual review rather than readopted.")
    cutoff = datetime.min          # treat everything as post-cutoff
```

An in-progress marker that was never marked `success` should also surface on the Settings
page as "a restore may not have completed — check the database before continuing," both
apps.

---

## 🟠 F-21 — A killed backup leaves a `backup_log` row stuck at `running` forever

**File:** `backup.py` (`run_backup`, `_log`)

`_log` commits a `status='running'`, `finished_at=NULL` row before `pg_dump` starts. Both
completion paths are Python `except` clauses — neither survives the process being killed. A
machine shut down mid-backup is not exotic on a single clinic desktop running a nightly
02:00 job. The stranded row then actively misleads: `backup_alert_message` only alarms on
`status == "failed"` or a 2+-day-old `started_at` — a `running` row is neither, so the
Dashboard reports healthy backups for roughly 48 hours when the last one never finished.

**JO status: open, unchanged.** No `reap_stale_running()`. `backup_alert_message`
(`logic.py:45-54`) has no `"running"` branch.

**IQ status: open, identical.** Same absence, same `backup_alert_message` shape
(`logic.py:45-54`).

**Fix (both apps, identical):**

```python
# backup.py — called from app startup
def reap_stale_running(db, stale_after_hours=6):
    """A 'running' row can only be genuine if this process created it, and this
    process was just started — so anything still 'running' at boot is from a run
    that was killed."""
    n = db.execute(
        "UPDATE backup_log SET status='failed', finished_at=?, "
        "error='Backup did not finish — the app was stopped or the machine shut down "
        "while it was running.' "
        "WHERE status='running' RETURNING id",
        (datetime.now().isoformat(timespec="seconds"),),
    ).rowcount
    db.commit()
    return n
```

```python
if last_backup_row["status"] == "running":
    started = parse_date(last_backup_row["started_at"])
    if started and (datetime.now() - ...).total_seconds() > 6 * 3600:
        return "The last backup started but never finished — check the Settings page."
```

---

## 🟡 F-22 — One failing migration statement will permanently block every later one, silently

**File:** `setup.py` (`apply_incremental_migrations`)

```python
def apply_incremental_migrations(con):
    for stmt in INCREMENTAL_SCHEMA_STATEMENTS:
        con.execute(stmt)
    con.commit()
```

One connection, one transaction, no per-statement isolation. The first statement that raises
aborts the transaction, so every statement after it is skipped and nothing at all commits.
This isn't hypothetical — the code comments on itself, at the duplicate-owner-phone unique
index statement: if a database already has two owners sharing a phone, this statement fails
outright and the whole run stops there, silently, on every launch, forever, since
`apply_schema()` runs on every app start.

**JO status: open, as originally described**, and the original doc's framing is basically
right for JO: 6 statements in `INCREMENTAL_SCHEMA_STATEMENTS`, all already redundant on a
clean install.

**IQ status: open, same underlying bug, but the original doc's "no consequence yet"
framing does not hold for IQ.** IQ's list is meaningfully larger and, unlike JO's, includes
statements beyond schema tweaks: data-normalization UPDATEs (payment-method backfills across
`sales`/`payments`/`distributor_bill_payments`/`consignment_settlements`) and a retroactive
permission grant (`INSERT INTO role_permissions ... SELECT ... FROM roles WHERE
is_system=true`). Since neither app is deployed yet (confirmed with the user), "already
causing damage" isn't accurate — but **this mechanism will start mattering the moment the
first real IQ install happens**, in a way JO's shorter, purely-schema list doesn't. If any
statement in IQ's list fails on a real clinic's data, everything after it — including the
permission grant — silently never lands, every single launch, with nothing printed anywhere
an operator would see. Treat IQ as the higher-priority side of this fix.

**Decision (resolved 2026-08-24):** Dashboard banner for admins, not a startup block — this
is the front desk's only system during opening hours; failing loud-but-non-fatal beats
taking the clinic down over a schema issue. See §Decisions.

**Fix (both apps, identical):**

```python
def apply_incremental_migrations(con):
    failures = []
    for stmt in INCREMENTAL_SCHEMA_STATEMENTS:
        try:
            with con.transaction():          # psycopg savepoint per statement
                con.execute(stmt)
        except Exception as e:
            failures.append((stmt, str(e)))
    con.commit()
    if failures:
        print("\n  !! Some schema migrations could not be applied:")
        for stmt, err in failures:
            print(f"     - {stmt.split(chr(10))[0][:90]}\n       {err}")
        print("     The app will still start, but the features these support may not work.")
        print("     Resolve the underlying data issue and restart.\n")
    return failures
```

Persist the failure list to a `settings` key and surface it on the Dashboard for admins, per
the decision, in both apps. Also consider emptying `INCREMENTAL_SCHEMA_STATEMENTS` before
first real deployment in both — every statement in it describes a migration from a version
no freshly-deployed database will ever have had.

---

## 🟡 F-23 — `import_seed.py` writes to a column that no longer exists

**File:** `import_seed.py`

```python
cur.execute(
    "INSERT INTO billing (visit_id,billing_type,codes,date_billed,discount_percent,notes) "
    ...
```

`codes` was removed from `billing` in both schemas (the column comment says so in its
place). Latent today since both apps' shipped `seed_data.json` have an empty `billing`
array — confirmed 0 rows in both.

**JO status: latent, unchanged.** `import_seed.py:208`.

**IQ status: latent, unchanged.** `import_seed.py:210`.

**Decision (resolved 2026-08-24):** no real historical-data seed import is planned for
either clinic right now (confirmed with the user) — this stays a low-priority, latent fix
rather than something blocking deployment. Still worth landing, since it would abort the
entire seed the moment anyone *does* put a real `billing` row in `seed_data.json`, and it's
a one-line correction. See §Decisions.

**Fix (both apps, when picked up):**

```python
cur.execute(
    "INSERT INTO billing (visit_id,billing_type,manual_amount,date_billed,discount_percent,total,notes) "
    "VALUES (?,'Manual',?,?,0,?,?) ON CONFLICT (visit_id) DO NOTHING",
    (vid, amount, date_billed or visit_date_fallback, amount, s(row[5])),
)
```

(Seeding as `Manual` with a lump sum, rather than `Automatic` with line items, since there's
no real per-line source data to seed either app with — matches the "no seed import planned"
decision; revisit the shape only if that changes.) Run `logic.recompute_full_summary(con)`
once at the end of any future seed run so the P&L reflects imported history.

---

## 🟡 F-24 — `run_backup()` commits the caller's request transaction

**Files:** `backup.py` (`_log`, `_finish_log`), `app.py` (`settings_backup_now`)

`_log`/`_finish_log` call `db.commit()` on whatever connection is passed in. If that's the
request's own connection (`get_db()`), any other pending write on that request is committed
as a side effect of taking a backup.

**JO status: open, exactly as described.** `settings_backup_now()` (`app.py:5614-5627`)
passes the request's own `get_db()` connection straight into `run_backup(db)`
(`app.py:5623`).

**IQ status: already redesigned for the manual-backup path.** `settings_backup_now()`
(`app.py:5866-5886`) runs the backup as a background job whose closure opens its **own**
fresh connection (`conn = dbmod.connect()`, `app.py:5875`), passes that into
`run_backup(conn, ...)`, and closes it in a `finally` — with a comment explaining why
(`g.db` belongs to the request and would be closed before the background thread finishes).
`_log`/`_finish_log`'s commits land on a connection nothing else is using.
**Caveat, not yet checked:** IQ's *other* `run_backup(...)` call site
(`app.py:6092`, `run_backup(db, triggered_by="shutdown")` inside the shutdown handler) was
not verified for the same connection-ownership question — worth a quick look before
declaring F-24 fully closed in IQ.

**Fix (JO):**

```python
# Give the logging helpers their own connection, the way _try_log_restore already does
run_backup(get_fresh_db, ...)   # instead of run_backup(db, ...)
```

Note this is a bigger lift for JO than a one-line swap — IQ's fix required restructuring
the manual-backup route into a background job with progress polling (JO's route is
currently synchronous/blocking). Porting F-24's fix into JO means porting that structural
change too, not just swapping the connection argument.

**Fix (IQ):** verify `app.py:6092`'s shutdown-triggered call; if it shares the shutdown
handler's own connection rather than opening a fresh one, apply the same fresh-connection
pattern there.

---

## 🟠 F-25 — Toggling or reassigning a role's `is_vet_role` flag orphans appointments with no warning (IQ-only — new finding)

**Files:** `app.py` (`admin_role_edit`, `admin_role_delete`), `logic.py` (`vet_users`)

**IQ-only** — JO has no custom-role feature (only 3 fixed roles), so this surface doesn't
exist there. Distinct from F-17 (which covers moving a *user* to a different role) — this
covers changing a *role's own* `is_vet_role` flag, or reassigning every user on a deleted
role to a target role, in one action affecting potentially many users at once.

`vet_users()` — the function every vet picker (Appointments, New Visit, Grooming, Inpatient)
reads from — filters `WHERE r.is_vet_role=true AND u.active=true`. `admin_role_edit()` lets
an admin flip an *existing* role's `is_vet_role` flag directly; `admin_role_delete()` lets an
admin reassign every user on a deleted role to a different target role. Neither checks
whether that role-level change strips vet status from users who have future appointments
booked against them. The only post-save check in `admin_role_edit()` is
`auth.no_vet_role_configured(db)`, which only fires if **zero** roles remain vet-eligible
clinic-wide — flipping one non-Admin role from vet to non-vet while other vet roles exist
triggers nothing, even though every active user under that role just had every future
appointment become unreachable from the grid. Same gap in `admin_role_delete()`'s
reassignment path: only a generic "N staff moved" flash, no appointment-count warning.

```python
# admin_role_edit() — app.py:1249-1266
is_vet_role = bool(f.get("is_vet_role"))
...
db.execute("UPDATE roles SET name=?, description=?, discount_cap=?, is_vet_role=? WHERE id=?", ...)
...
if auth.no_vet_role_configured(db):
    flash("No role is currently marked \"Can be assigned as a vet\" — ...", "error")
```

**Fix.** Reuse the `_warn_orphaned_appointments(db, user_id)` helper proposed for F-17,
called for every affected user (not just one) after both role-level mutations:

```python
# admin_role_edit() — after db.commit(), when is_vet_role flipped true->false
if role["is_vet_role"] and not is_vet_role:
    affected = db.execute("SELECT id FROM users WHERE role_id=? AND active=true", (role_id,)).fetchall()
    total = sum(_future_appt_count(db, u["id"]) for u in affected)
    if total:
        flash(f"Heads up: {total} upcoming appointment(s) across {len(affected)} staff member(s) "
              f"on this role won't show on the Appointments grid anymore. Check Appointments for "
              f'the "need attention" list to reschedule them.', "error")
```

Same pattern in `admin_role_delete()`'s `if assigned:` branch, before the success flash, when
the deleted role was vet-eligible and the target role isn't. Extract the per-user
appointment-count query (already inline in `admin_user_toggle()`) into a shared
`_future_appt_count(db, user_id)` helper so F-17 and F-25 share one implementation.

---

## Invariant checks — QA regression queries

No production data to clean up, so these aren't repair tools — they're the invariants the
fixes above are supposed to guarantee, written as queries. **Every one should return zero
rows.** Run against **both** apps' QA databases after a realistic exercise — create visits,
bill them, take payments, run a POS sale, refund it, run an audit, admit and discharge an
inpatient. Worth wiring into `tests/` as a single test asserting each returns empty (both
apps already have `tests/test_no_raw_form_dates.py` establishing that pattern in JO — port
the same test-file convention to IQ, which currently has no `tests/` directory at all).

```sql
-- D-02/03: patients with no visit at all (only creatable via the visit form)
SELECT p.id, p.animal_name, p.owner_id
FROM patients p
WHERE NOT EXISTS (SELECT 1 FROM visits v WHERE v.patient_id = p.id);

-- D-03b: owners with no patients
SELECT o.id, o.name, o.phone
FROM owners o
WHERE NOT EXISTS (SELECT 1 FROM patients p WHERE p.owner_id = o.id);

-- D-01a: sales whose stored total doesn't match their line items (partial commit)
SELECT s.id, s.sale_date, s.subtotal,
       COALESCE(SUM(si.line_total), 0) AS line_sum
FROM sales s LEFT JOIN sale_items si ON si.sale_id = s.id
GROUP BY s.id, s.sale_date, s.subtotal
HAVING COALESCE(SUM(si.line_total), 0) <> s.subtotal;

-- D-01b: sales with no line items at all
SELECT s.id, s.sale_date, s.total FROM sales s
WHERE NOT EXISTS (SELECT 1 FROM sale_items si WHERE si.sale_id = s.id);

-- D-01c: retail refunds with no refund_items
SELECT r.id, r.refund_date, r.amount FROM refunds r
WHERE r.refund_type = 'retail'
  AND NOT EXISTS (SELECT 1 FROM refund_items ri WHERE ri.refund_id = r.id);

-- D-01d: sale_items with no matching inventory_transactions 'sale' row
SELECT si.sale_id, si.item_id, si.quantity
FROM sale_items si
WHERE NOT EXISTS (
    SELECT 1 FROM inventory_transactions t
    WHERE t.reason = 'sale' AND t.ref_id = si.sale_id::text AND t.item_id = si.item_id);

-- D-05: service refunds anchored to nothing, or to two things at once
-- (now applies to BOTH apps, per the F-05 decision — IQ's prior "intentional
-- unanchored" design is gone once F-05's constraint lands)
SELECT id, refund_date, amount, visit_id, inpatient_case_id
FROM refunds
WHERE refund_type = 'service'
  AND (visit_id IS NOT NULL) = (inpatient_case_id IS NOT NULL);

-- D-06: bills that will never appear in the P&L
SELECT visit_id, billing_type, total FROM billing
WHERE date_billed IS NULL AND total > 0;

-- D-07a: Consignment items with no distributor
SELECT id, name, category, ownership_type FROM inventory_list
WHERE ownership_type = 'Consignment' AND distributor_id IS NULL;

-- D-07b: consignment child rows whose distributor no longer matches the item's
SELECT 'receipt' AS kind, cr.id, cr.item_id, cr.distributor_id AS row_dist,
       i.distributor_id AS item_dist
FROM consignment_receipts cr JOIN inventory_list i ON i.id = cr.item_id
WHERE cr.distributor_id IS DISTINCT FROM i.distributor_id
UNION ALL
SELECT 'shrinkage', cs.id, cs.item_id, cs.distributor_id, i.distributor_id
FROM consignment_shrinkage cs JOIN inventory_list i ON i.id = cs.item_id
WHERE cs.distributor_id IS DISTINCT FROM i.distributor_id
UNION ALL
SELECT 'return', crt.id, crt.item_id, crt.distributor_id, i.distributor_id
FROM consignment_returns crt JOIN inventory_list i ON i.id = crt.item_id
WHERE crt.distributor_id IS DISTINCT FROM i.distributor_id;

-- D-07c: distributors with consignment history but no current consignment item
--        (invisible on the Consignment Overview)
SELECT d.id, d.name FROM distributors d
WHERE (EXISTS (SELECT 1 FROM consignment_receipts   x WHERE x.distributor_id = d.id)
    OR EXISTS (SELECT 1 FROM consignment_shrinkage  x WHERE x.distributor_id = d.id)
    OR EXISTS (SELECT 1 FROM consignment_returns    x WHERE x.distributor_id = d.id)
    OR EXISTS (SELECT 1 FROM consignment_settlements x WHERE x.distributor_id = d.id))
  AND NOT EXISTS (SELECT 1 FROM inventory_list i
                  WHERE i.distributor_id = d.id AND i.ownership_type = 'Consignment');

-- D-09: Consignment items no longer on the Consignment Items page
SELECT id, name, category FROM inventory_list
WHERE ownership_type = 'Consignment' AND (category <> 'Retail' OR active = false);

-- D-10a: visits claiming an admission with no inpatient case
SELECT v.id, v.date, v.patient_id FROM visits v
WHERE v.case_status = 'Admitted to Inpatient'
  AND NOT EXISTS (SELECT 1 FROM inpatient_cases c WHERE c.visit_id = v.id);

-- D-10b: open inpatient cases whose visit no longer says admitted
SELECT c.id, c.visit_id, v.case_status FROM inpatient_cases c
JOIN visits v ON v.id = c.visit_id
WHERE c.dismissed = false AND v.case_status <> 'Admitted to Inpatient';

-- D-11: audit lines for items that are now inactive
SELECT l.session_id, l.item_id, i.name, s.status
FROM audit_session_lines l
JOIN inventory_list i ON i.id = l.item_id
JOIN audit_sessions s ON s.id = l.session_id
WHERE i.active = false;

-- D-13: attachments anchored to neither a visit nor a case
SELECT id, patient_id, relative_path FROM attachments
WHERE visit_id IS NULL AND inpatient_case_id IS NULL;

-- D-14a: payments with no anchor, or more than one
SELECT id, amount, date, visit_id, inpatient_case_id, boarding_id FROM payments
WHERE (visit_id IS NOT NULL)::int
    + (inpatient_case_id IS NOT NULL)::int
    + (boarding_id IS NOT NULL)::int <> 1;

-- D-14b: inpatient cases paid above their bill
SELECT c.id, c.total, SUM(p.amount) AS paid
FROM inpatient_cases c JOIN payments p ON p.inpatient_case_id = c.id
GROUP BY c.id, c.total HAVING SUM(p.amount) > c.total;

-- D-14c: visits paid above their bill
SELECT b.visit_id, b.total, SUM(p.amount) AS paid
FROM billing b JOIN payments p ON p.visit_id = b.visit_id
GROUP BY b.visit_id, b.total HAVING SUM(p.amount) > b.total;

-- D-15: empty draft audit sessions
SELECT s.id, s.audit_date, s.created_at FROM audit_sessions s
WHERE s.status = 'Draft'
  AND NOT EXISTS (SELECT 1 FROM audit_session_lines l
                  WHERE l.session_id = s.id AND l.stock_counted IS NOT NULL);

-- D-16: billing rows with a discount but nothing billed
SELECT visit_id, discount_percent FROM billing
WHERE billing_type = 'Automatic' AND manual_amount IS NULL AND date_billed IS NULL
  AND NOT EXISTS (SELECT 1 FROM visit_billing_lines l WHERE l.visit_id = billing.visit_id);

-- D-20: restores on record, to compare against the on-disk marker (F-20).
--       If the marker file is newer than the newest row here, a restore
--       went unrecorded and reconcile_attachments would run unsafely.
SELECT id, started_at, finished_at, status, source_file, triggered_by
FROM restore_log ORDER BY id DESC LIMIT 10;

-- D-21: backups stuck at 'running'
SELECT id, started_at, filepath FROM backup_log
WHERE status = 'running'
ORDER BY started_at DESC;

-- D-22: every constraint this document adds is actually present, in this app.
--       Expect one row per constraint named below; anything missing means an
--       edit to schema_postgres.sql didn't land. Run against BOTH apps.
SELECT conname FROM pg_constraint WHERE conname IN (
    'refunds_anchor_ck',
    'inventory_consignment_needs_distributor_ck',
    'attachments_one_anchor_ck',
    'payments_one_anchor_ck'
);

-- D-19: any user reference that doesn't resolve.
--       With the F-19 foreign keys in place this is structurally impossible —
--       keep it as the check that proves they were actually added. Run against BOTH apps.
SELECT 'visits.created_by' AS col, v.id::text AS rec, v.created_by AS bad
FROM visits v LEFT JOIN users u ON u.id = v.created_by
WHERE v.created_by IS NOT NULL AND u.id IS NULL
UNION ALL
SELECT 'appointments.resource_id', a.id::text, a.resource_id
FROM appointments a LEFT JOIN users u ON u.id = a.resource_id
WHERE a.resource_id IS NOT NULL AND u.id IS NULL;
-- ...repeat per column in F-19

-- D-25: IQ only — appointments for users whose current role isn't vet-eligible (F-25)
SELECT a.id, a.appt_date, a.resource_id, u.role_id, r.is_vet_role
FROM appointments a
JOIN users u ON u.id = a.resource_id
JOIN roles r ON r.id = u.role_id
WHERE a.resource_type = 'vet' AND a.appt_date >= CURRENT_DATE AND r.is_vet_role = false;
```

---

## Decisions — resolved 2026-08-24, before implementation

Talked through with the user directly; recorded here so implementation doesn't need to
re-derive or re-ask them.

| Question | Decision | Where it shows up |
|---|---|---|
| F-05, unanchored service refunds | **IQ aligns to JO's rule** — every service refund requires exactly one anchor (visit or case), in both apps. IQ's prior "intentional" unanchored path is removed; a goodwill/no-record refund is handled through the Cash Register page instead, not the refunds table. | F-05 |
| F-07, `consignment_balance` asymmetry | Add a `distributor_id` snapshot column on `sale_items`, written at checkout the same way `unit_cost` already is — in addition to blocking the distributor-change edit. Both apps, no migration cost pre-deployment. | F-07 |
| F-15, automatic cleanup | Manual delete only via the new route — no automatic nightly purge of abandoned drafts. Safer default; an in-progress audit shouldn't vanish over a long weekend. | F-15 |
| F-19, FK behavior on user delete | `RESTRICT`, not `SET NULL` — matches how both apps already behave (deactivate, never delete); more honest about current design than reserving room for a future erasure feature. | F-19 |
| F-20, fail-closed reconcile | Write the restore marker on every app boot (not an `--assume-no-restore` flag) — makes "no restore has happened" provable rather than assumed. Both apps. | F-20 |
| F-22, migration failures | Dashboard banner for admins, not a startup block — this is the front desk's only system during opening hours. Both apps; IQ treated as the higher-priority side since its migration list already carries real data-normalization/permission-grant logic. | F-22 |
| F-23, real seed data | No real historical-data seed import is planned for either clinic right now. Fix stays low-priority/latent — worth the one-line correction regardless, since it will crash the moment `seed_data.json`'s `billing` array is ever non-empty, but not blocking anything today. | F-23 |
| Verification access | `scripts/isolated_test_env.sh` gives real isolated-Postgres access for both apps — fixes will be verified live, not just described. | throughout |
| Deployment status | Neither app is in production yet — confirmed 2026-08-24. All schema changes above are written as direct `schema_postgres.sql` edits, no `ALTER TABLE` migration path needed; severity language throughout describes impact *once* deployed. | throughout |

---

## Suggested order of work

Nothing here needs phasing around a live database (neither app is deployed), so this is
grouped by what's coherent to work on together, across both apps, rather than by risk to a
production system that doesn't exist yet.

**Group A — the transaction layer.** F-01 (teardown fail-closed) · F-04 (`BadDate` handler —
the specific uncaught call site is already fixed in both apps, just the safety-net handler
remains) · the shared E-12/F-03 `IntegrityError` fallback (fix once, closes both documents'
mention of it). Both apps, identical fix. Do these first: several other findings are only
*reachable* because of F-01.

**Already done, no action needed:** F-02, F-03's core commit-ordering fix (both apps,
verified fixed by unrelated work today).

**Group B — billing and money.** F-05 (refund anchoring, now identical in both apps per the
decision) · F-06 (`date_billed` required) · F-14 (payment anchoring + overpay guard) · F-16
(no discount without a bill). Both apps, mostly identical fix shape.

**Group C — consignment and distributors.** F-07 (including the new `sale_items
.distributor_id` snapshot) + F-08 + F-09. One coherent change per app: Inventory Catalog
routes must respect `consignment_item_locked()`, `distributor_delete` must check all six
tables (JO needs this port; IQ already has it), the category flip must be blocked. Fixing
one alone leaves the others reachable, both apps.

**Group D — backup, restore, and recovery tooling.** F-20 (restore marker + boot-time write)
· F-21 (reap stuck `running` backups) · F-12 (reverse attachment reconcile) · F-24 (backup
connection ownership — JO needs the full fix including the background-job restructuring;
IQ needs only the shutdown-path check). Independent of everything above, can run in
parallel, both apps.

**Group E — schema constraints.** The `CHECK` constraints from F-05, F-07, F-13, F-14 and
the `RESTRICT` foreign keys from F-19, written directly into both apps'
`schema_postgres.sql`. Do these *after* Groups A-C rather than before: the route-level
guards are what produce good error messages, and a constraint that fires first turns a
friendly flash into a 500.

**Group F — everything else.** F-10 (visit ↔ inpatient case) · F-11 (audit lines for
deactivated items) · F-15 (draft audit cleanup) · F-17 + F-25 (share the
`_future_appt_count()`/`_warn_orphaned_appointments()` helper — F-25 is IQ-only) · F-18 ·
F-22 (per-statement migrations + Dashboard banner — higher priority for IQ) · F-23 (the seed
script, low priority per the decision above).

**One sequencing note that isn't optional, if F-23's premise ever changes:** if a real
historical-data seed import does get planned for either clinic later, settle F-23 before
running it, not after — `import_seed.py` writes to a column that no longer exists, so the
seed would fail outright; and once that's fixed, the way it currently writes `billing` rows
would produce F-16/F-06 orphans in bulk on day one.
