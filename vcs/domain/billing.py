"""
Bill totals for visits, inpatient cases and boarding stays: the lines,
the discount (never on a non-discountable line), Clean Up, and what is
paid.
"""
from vcs import clock
from vcs import money
from vcs.domain import dates


# ---------------------------------------------------------------------------
# Billing (Automatic line-items OR Manual lump sum) + discount + payment status
# ---------------------------------------------------------------------------
def retail_consistency_flags(db):
    """
    Cross-checks the Retail category between Inventory Catalog and Price
    List. Returns (flagged_price_ids, flagged_inventory_ids):
      - a Price List Retail row is flagged if its linked item doesn't exist
        or isn't an active Retail inventory item
      - an active Retail inventory item is flagged if no active Price List
        Retail row links to it
    """
    price_rows = db.execute(
        "SELECT id, linked_item_id FROM price_list WHERE active=true AND category='Retail'"
    ).fetchall()
    inv_ids = {r["id"] for r in db.execute(
        "SELECT id FROM inventory_list WHERE active=true AND category='Retail'"
    ).fetchall()}

    flagged_price = {r["id"] for r in price_rows if not r["linked_item_id"] or r["linked_item_id"] not in inv_ids}
    linked_ids = {r["linked_item_id"] for r in price_rows if r["linked_item_id"]}
    flagged_inventory = inv_ids - linked_ids

    return flagged_price, flagged_inventory


def non_discountable_line_names(db, price_ids):
    """Given a set/list of price_list IDs on a bill, returns the display
    names of any that are marked as not discountable (can_discount=false)."""
    if not price_ids:
        return []
    ids = [i for i in price_ids if i]
    if not ids:
        return []
    placeholders = ",".join(["%s"] * len(ids))
    rows = db.execute(
        f"SELECT name FROM price_list WHERE id IN ({placeholders}) AND can_discount=false",
        tuple(ids),
    ).fetchall()
    return [r["name"] for r in rows]


def non_discountable_line_names_for_items(db, inventory_item_ids):
    """Same as non_discountable_line_names(), but for POS carts, which
    reference inventory_list IDs rather than price_list IDs directly —
    looks up each item's linked Retail price_list entry."""
    ids = [i for i in inventory_item_ids if i]
    if not ids:
        return []
    placeholders = ",".join(["%s"] * len(ids))
    rows = db.execute(
        f"SELECT name FROM price_list WHERE linked_item_id IN ({placeholders}) AND can_discount=false",
        tuple(ids),
    ).fetchall()
    return [r["name"] for r in rows]


def discountable_by_item_ids(db, inventory_item_ids):
    """Discount eligibility per POS cart item, as {inventory_item_id: bool}.

    Same linked_item_id join as non_discountable_line_names_for_items(), but
    it returns the flag for every id rather than the names of the ineligible
    ones -- POS needs the value itself, both to price the cart per line and
    to snapshot it onto each sale_items row.

    Filters active=true to match item_sale_price(), deliberately: eligibility
    must come from the same price_list row the PRICE came from, or a stale
    inactive row could discount a line priced from a different one.
    non_discountable_line_names_for_items() does not filter active; it feeds
    the staff-discount guard and is left as-is rather than changed underneath
    that guard. An id with no active linked row is simply absent -- callers
    treat missing as not discountable.
    """
    ids = [i for i in inventory_item_ids if i]
    if not ids:
        return {}
    placeholders = ",".join(["%s"] * len(ids))
    rows = db.execute(
        f"SELECT linked_item_id, can_discount FROM price_list "
        f"WHERE linked_item_id IN ({placeholders}) AND active=true",
        tuple(ids),
    ).fetchall()
    return {r["linked_item_id"]: bool(r["can_discount"]) for r in rows}


def save_visit_billing_lines(db, visit_id, lines):
    """
    Replaces every visit_billing_lines row for this visit with a fresh snapshot
    of what's in the cart at Save time \u2014 price_id/name/category/
    quantity/unit_price/unit_cost per line, from the search-and-add billing UI
    (visit_billing_save() in the clinical blueprint builds this list). Does not
    commit (caller's job, same convention as every other write in this module).
    """
    db.execute("DELETE FROM visit_billing_lines WHERE visit_id=%s", (visit_id,))
    now_str = clock.now().isoformat(timespec="seconds")
    for l in lines:
        db.execute(
            "INSERT INTO visit_billing_lines (visit_id, price_id, name, category, quantity, unit_price, unit_cost, discountable, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (visit_id, l["price_id"], l["name"], l["category"], l["quantity"],
             l["unit_price"], l["unit_cost"], l["discountable"], now_str),
        )


def discounted_raw_total(subtotal, discountable_subtotal, discount_percent):
    """The bill before rounding: the discount comes off the eligible part of
    the subtotal only, and the rest is charged in full.

    Lives in one function that BOTH compute_bill_totals() and pos_checkout()
    call, rather than being written out at each — one rule spelled out in two
    places is exactly the shape every entry in SEAM_RULES.md came from. The
    arithmetic itself is money.discounted().

    On a staff discount `discountable_subtotal == subtotal` always (the
    guards refuse a staff discount on a bill holding a non-discountable
    line), so this returns exactly `subtotal * (1 - d)`.
    """
    return money.discounted(subtotal or 0, discountable_subtotal or 0, discount_percent or 0)


def compute_bill_totals(subtotal, discount_percent, paid, cleanup_amount=0, *,
                        discountable_subtotal):
    """
    Shared by visit_billing_summary() and inpatient_billing_summary() so the
    money math (total/balance/status) is defined in exactly one place instead
    of being duplicated per billing type.

    `discountable_subtotal` is the part of `subtotal` the discount may
    actually come off; the remainder is charged in full. It is KEYWORD-ONLY,
    REQUIRED and has NO DEFAULT, deliberately: a default of `subtotal` would
    let any caller that forgot it silently treat a non-discountable item as
    discountable, and a silently wrong total is the one failure this feature
    cannot afford. Forgetting it is a TypeError instead. See
    features/REWARDS_CARD_PLAN.md §2.2 and seam rule 6.

    The payable total is the discounted figure rounded to the money
    setting's cash unit by money.payable() — to the nearest 250-dinar note
    under IQ, never rounding a real bill down to free; unchanged under JO.
    Applied ONCE, to the whole total, never per line: rounding each line
    separately would drift the bill away from its own subtotal.

    cleanup_amount is a capped, explicit staff write-off (see
    CLEANUP_FEATURE_PLAN.md) applied AFTER that rounding, on top of whatever
    it produced — not a replacement for it.

    Returns (total, paid, balance, status, pre_cleanup_total). That last one
    is the payable total BEFORE Clean Up comes off: receipts print it instead
    of re-deriving `subtotal * (1 - d)`, which does not match on a bill
    holding non-discountable lines — returning it from here is what keeps
    `subtotal - discount - Clean Up = total` true on every export.
    """
    discount_percent = discount_percent or 0
    pre_cleanup_total = money.payable(
        discounted_raw_total(subtotal, discountable_subtotal, discount_percent), discount_percent)
    total = money.to_store(max(pre_cleanup_total - (cleanup_amount or 0), 0))
    paid = money.to_store(paid or 0)
    # What is still owed, at the cash unit: a remainder smaller than half a
    # 250-dinar note is not collectable under IQ and reads as settled. There
    # is deliberately no tolerance constant in the status test below — the
    # predecessor apps carried `<= 0.5` (noise in IQD, real money in JOD).
    balance = money.balance_due(total, paid)
    if total <= 0:
        status = "N/A"
    elif paid <= 0:
        status = "Unpaid"
    elif money.is_settled(balance):
        status = "Fully Paid"
    else:
        status = "Partially Paid"
    return total, paid, balance, status, pre_cleanup_total


def visit_billing_summary(db, visit_id):
    b = db.execute("SELECT * FROM billing WHERE visit_id=%s", (visit_id,)).fetchone()
    if not b:
        return {"billing_type": "Automatic", "lines": [], "subtotal": 0, "discount_percent": 0,
                "discount_source": "staff", "discountable_subtotal": 0, "pre_cleanup_total": 0,
                "cleanup_amount": 0, "total": 0, "paid": 0, "balance": 0, "status": "N/A"}

    if b["billing_type"] == "Manual":
        lines = [{"id": None, "name": "Veterinary Services", "category": "Service",
                  "price": b["manual_amount"] or 0, "discountable": True}] if b["manual_amount"] else []
        subtotal = b["manual_amount"] or 0
        # A Manual bill is one typed figure with no item lines to check, and
        # staff discounts already applied to the whole of it — so the card
        # does too. features/REWARDS_CARD_PLAN.md A4.
        discountable_subtotal = subtotal
    else:
        snapshot_rows = db.execute(
            "SELECT price_id, name, category, quantity, unit_price, discountable FROM visit_billing_lines WHERE visit_id=%s ORDER BY id",
            (visit_id,),
        ).fetchall()
        # Priced from the snapshot taken when this bill was saved (via the
        # search-and-add billing UI) — doesn't change if someone edits the
        # Price List afterward. Mirrors inpatient_billing_summary()'s shape
        # exactly (quantity + line_total per line).
        lines = [{"id": r["price_id"], "name": r["name"], "category": r["category"],
                  "price": r["unit_price"], "quantity": r["quantity"],
                  "line_total": money.to_store(r["unit_price"] * r["quantity"]),
                  "discountable": bool(r["discountable"])}
                 for r in snapshot_rows]
        subtotal = sum(l["line_total"] for l in lines)
        discountable_subtotal = sum(l["line_total"] for l in lines if l["discountable"])

    discount_percent = b["discount_percent"] or 0
    cleanup_amount = b["cleanup_amount"] or 0
    paid_row = db.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE visit_id=%s", (visit_id,)).fetchone()
    total, paid, balance, status, pre_cleanup_total = compute_bill_totals(
        subtotal, discount_percent, paid_row["s"], cleanup_amount,
        discountable_subtotal=discountable_subtotal)
    return {"billing_type": b["billing_type"], "lines": lines, "subtotal": money.to_store(subtotal),
            "discount_percent": discount_percent, "cleanup_amount": cleanup_amount,
            "discount_source": b["discount_source"], "pre_cleanup_total": pre_cleanup_total,
            "discountable_subtotal": money.to_store(discountable_subtotal),
            "total": total, "paid": paid, "balance": balance, "status": status}


def _refresh_visit_billing_total(db, visit_id):
    """billing.total, from the bill's lines, manual amount, discount and
    Clean Up (see bill_changed())."""
    total = visit_billing_summary(db, visit_id)["total"]
    db.execute("UPDATE billing SET total=%s WHERE visit_id=%s", (total, visit_id))


# ---------------------------------------------------------------------------
# Inpatient billing (procedures only — never touches stock)
# ---------------------------------------------------------------------------
def inpatient_billing_summary(db, case_id):
    rows = db.execute(
        "SELECT ib.*, p.name, p.category FROM inpatient_billing ib "
        "JOIN price_list p ON p.id = ib.price_id WHERE ib.case_id=%s ORDER BY ib.timestamp",
        (case_id,),
    ).fetchall()
    lines, subtotal, discountable_subtotal = [], 0, 0
    for r in rows:
        # The price snapshotted when the line was added: a later Price List
        # edit never reprices a bill already charged.
        unit_price = r["unit_price"]
        line_total = unit_price * r["quantity"]
        subtotal += line_total
        if r["discountable"]:
            discountable_subtotal += line_total
        lines.append({"id": r["id"], "name": r["name"], "quantity": r["quantity"],
                       "unit_price": unit_price, "line_total": money.to_store(line_total),
                       "discountable": bool(r["discountable"])})
    case = db.execute("SELECT discount_percent, discount_source, cleanup_amount FROM inpatient_cases WHERE id=%s", (case_id,)).fetchone()
    discount_percent = case["discount_percent"] if case else 0
    cleanup_amount = (case["cleanup_amount"] if case else 0) or 0
    paid_row = db.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE inpatient_case_id=%s", (case_id,)).fetchone()
    total, paid, balance, status, pre_cleanup_total = compute_bill_totals(
        subtotal, discount_percent, paid_row["s"], cleanup_amount,
        discountable_subtotal=discountable_subtotal)
    return {"lines": lines, "subtotal": money.to_store(subtotal), "discount_percent": discount_percent,
            "discount_source": case["discount_source"] if case else "staff",
            "discountable_subtotal": money.to_store(discountable_subtotal),
            "pre_cleanup_total": pre_cleanup_total,
            "cleanup_amount": cleanup_amount, "total": total, "paid": paid, "balance": balance, "status": status}


def _refresh_inpatient_total(db, case_id):
    """inpatient_cases.total, from the case's procedures, discount and Clean
    Up (see bill_changed())."""
    total = inpatient_billing_summary(db, case_id)["total"]
    db.execute("UPDATE inpatient_cases SET total=%s WHERE id=%s", (total, case_id))


# ---------------------------------------------------------------------------
# Boarding
# ---------------------------------------------------------------------------
def boarding_nights(entry_date, dismissal_date):
    """Nights stayed so far (or planned), at least 1."""
    start = dates.as_date(entry_date)
    end = dates.as_date(dismissal_date) if dismissal_date else clock.today()
    if not start:
        return 1
    return max(1, (end - start).days)


def boarding_suggested_total(price_per_day, entry_date, dismissal_date):
    if not price_per_day:
        return None
    return money.to_store(price_per_day * boarding_nights(entry_date, dismissal_date))


def boarding_billing_summary_from_fields(b, paid):
    """Same computation as boarding_billing_summary(), factored out so a
    caller that already has the boarding_sessions row in hand (e.g. a list page
    rendering many rows at once) can skip re-fetching it and the per-row
    payments query — see boarding_page() in the clinical blueprint, which
    batches `paid` across the whole page in one query instead of one per row.
    `b` needs total, total_is_auto, price_per_day, entry_date, dismissal_date,
    dismissed, cleanup_amount, discount_percent,
    discount_source."""
    if not b:
        subtotal = 0
    elif b["total_is_auto"] and not b["dismissed"] and b["price_per_day"]:
        # Still an active stay, and `total` has never been overridden with
        # a deliberately-typed figure — the stored value is only ever the
        # suggestion computed once, back when the stay was created/last
        # edited (usually 1 night, since dismissal_date is normally still
        # unknown then). Recompute live from price_per_day x nights-so-far
        # so the bill never sits frozen at a stale night count while the
        # animal is still boarding. Once dismissed, boarding_dismiss()
        # locks in the final figure and this branch no longer applies.
        subtotal = boarding_suggested_total(b["price_per_day"], b["entry_date"], b["dismissal_date"]) or 0
    else:
        subtotal = b["total"] or 0
    cleanup_amount = (b["cleanup_amount"] if b else 0) or 0
    discount_percent = (b["discount_percent"] if b else 0) or 0
    # A stay is one amount with no item lines to check, and staff discounts
    # already applied to the whole of it — so the card does too. A4.
    total, paid, balance, status, pre_cleanup_total = compute_bill_totals(
        subtotal, discount_percent, paid, cleanup_amount,
        discountable_subtotal=subtotal)
    return {"total": total, "paid": paid, "balance": balance, "status": status,
            "cleanup_amount": cleanup_amount, "discount_percent": discount_percent,
            "discount_source": (b["discount_source"] if b else "staff") or "staff",
            "discountable_subtotal": subtotal, "pre_cleanup_total": pre_cleanup_total,
            "subtotal": subtotal}


def boarding_billing_summary(db, boarding_id):
    b = db.execute(
        "SELECT total, total_is_auto, price_per_day, entry_date, dismissal_date, dismissed, cleanup_amount, "
        "discount_percent, discount_source "
        "FROM boarding_sessions WHERE id=%s", (boarding_id,)
    ).fetchone()
    paid_row = db.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE boarding_id=%s", (boarding_id,)).fetchone()
    return boarding_billing_summary_from_fields(b, paid_row["s"])


def _refresh_boarding_total(db, boarding_id):
    """boarding_sessions.billed_total — the figure boarding_page()'s batched
    list view and the reports read instead of recomputing per row (see
    bill_changed())."""
    total = boarding_billing_summary(db, boarding_id)["total"]
    db.execute("UPDATE boarding_sessions SET billed_total=%s WHERE id=%s", (total, boarding_id))


# ---------------------------------------------------------------------------
# The one way a stored bill total is kept right (audit D2)
# ---------------------------------------------------------------------------
_REFRESH = {"visit": _refresh_visit_billing_total, "inpatient": _refresh_inpatient_total,
            "boarding": _refresh_boarding_total}
BILL_KINDS = tuple(_REFRESH)


def bill_changed(db, kind, record_id):
    """A bill's lines, manual amount, discount or Clean Up changed: store its
    new total. `kind` is "visit" (record_id = the visit), "inpatient" (the
    case) or "boarding" (the stay).

    Call it in the same transaction as the change, before commit. The stored
    totals are what the P&L, Insights and every list read (reports.py), so a
    write that skips this leaves them reporting the old amount -- audit B2 was
    three such writes. It is the only entry point, and seam rule 12 checks
    every function that writes a bill's inputs calls it. Payments do not
    change a total, only what is still owed."""
    if kind not in _REFRESH:
        raise ValueError(f"bill_changed(): not a kind of bill: {kind!r}")
    _REFRESH[kind](db, record_id)
