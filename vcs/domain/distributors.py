"""
The distributor ledger: bills and payments, kept by hand, and what is
still owed.
"""



# ---------------------------------------------------------------------------
# Distributor Ledger — manual bookkeeping for what you've been billed by a
# distributor and what you've paid them: a lump-sum charge per bill,
# payments recorded against it, balance always computed (never stored).
# Not linked to inventory, POS, or any report; every bill is a manual
# entry, same as the paper/memory tracking this replaces.
# ---------------------------------------------------------------------------
def distributor_bill_balance(bill, payments):
    """payments: list of payment rows for this bill."""
    paid = sum(p["amount"] for p in payments)
    balance = bill["total_amount"] - paid
    if balance <= 0:
        status = "Paid"
    elif paid > 0:
        status = "Partial"
    else:
        status = "Unpaid"
    return {"paid": paid, "balance": balance, "status": status}


def distributor_ledger(db, distributor_id):
    """Bills for a distributor, each annotated with paid/balance/status,
    plus distributor-level totals. Used by the distributor detail page."""
    bills = [dict(r) for r in db.execute(
        "SELECT * FROM distributor_bills WHERE distributor_id=%s ORDER BY bill_date DESC, id DESC",
        (distributor_id,)
    ).fetchall()]
    all_payments = db.execute(
        "SELECT * FROM distributor_bill_payments WHERE bill_id IN "
        "(SELECT id FROM distributor_bills WHERE distributor_id=%s) ORDER BY payment_date, id",
        (distributor_id,)
    ).fetchall()
    by_bill = {}
    for p in all_payments:
        by_bill.setdefault(p["bill_id"], []).append(dict(p))

    total_billed = total_paid = 0
    for b in bills:
        pmts = by_bill.get(b["id"], [])
        calc = distributor_bill_balance(b, pmts)
        b.update(calc)
        b["payments"] = pmts
        total_billed += b["total_amount"]
        total_paid += calc["paid"]

    return {
        "bills": bills,
        "total_billed": total_billed,
        "total_paid": total_paid,
        "total_outstanding": total_billed - total_paid,
    }


def distributor_outstanding_totals(db):
    """distributor_id -> outstanding balance, for the Distributors list column."""
    rows = db.execute(
        "SELECT b.distributor_id, b.id AS bill_id, b.total_amount, "
        "COALESCE(SUM(p.amount),0) AS paid "
        "FROM distributor_bills b "
        "LEFT JOIN distributor_bill_payments p ON p.bill_id = b.id "
        "GROUP BY b.distributor_id, b.id, b.total_amount"
    ).fetchall()
    totals = {}
    for r in rows:
        totals[r["distributor_id"]] = totals.get(r["distributor_id"], 0) + (r["total_amount"] - r["paid"])
    return totals


def distributor_payables_summary(db):
    """Rolled up across every distributor, for the Distributors list
    page's payables block — total owed, how many distributors have a
    balance, how many bills haven't seen a single payment yet, and a
    small ranked "who you owe most" table."""
    totals = distributor_outstanding_totals(db)  # {distributor_id: balance}
    names = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM distributors").fetchall()}

    with_balance = {did: bal for did, bal in totals.items() if bal > 0}
    ranked = sorted(
        ({"id": did, "name": names.get(did, did), "balance": bal} for did, bal in with_balance.items()),
        key=lambda r: r["balance"], reverse=True,
    )[:5]

    unpaid_bill_count = db.execute(
        "SELECT COUNT(*) AS n FROM distributor_bills b WHERE NOT EXISTS "
        "(SELECT 1 FROM distributor_bill_payments p WHERE p.bill_id = b.id)"
    ).fetchone()["n"]

    return {
        "total_outstanding": sum(with_balance.values()),
        "distributors_with_balance": len(with_balance),
        "unpaid_bill_count": unpaid_bill_count,
        "top_outstanding": ranked,
    }
