"""
The money reports: the Monthly and Yearly P&L (computed live from the stored
bill totals), the operating costs behind them, Insights and Retention.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Blueprint, redirect, render_template, request, url_for
from flask_babel import gettext as _

from vcs import auth
from vcs.db import pool as dbmod
from vcs.domain import analytics, cash_register, dates, reports
from vcs.web.core import (PER_PAGE, BadNumber, _render_with_progress, flash, get_db, get_page, has_negative,
                          page_count, page_offset, parse_money, requires_money_setting, strict_month)

bp = Blueprint("reports", __name__)


# ---------------------------------------------------------------------------
# Reports: Monthly & Yearly P&L (Admin only)
# ---------------------------------------------------------------------------
def _reports_context(db):
    pl = reports.monthly_pl(db)
    opex_rows = db.execute("SELECT month, rent, salaries, utilities, marketing, other FROM monthly_opex").fetchall()
    opex_by_month = {r["month"]: dict(r) for r in opex_rows}
    return dict(pl=pl, opex_by_month=opex_by_month)


@bp.route("/reports")
@auth.permission_required("view_financial_reports")
@requires_money_setting
def monthly():
    db = get_db()
    return render_template("reports.html", **_reports_context(db))


@bp.route("/reports/yearly")
@auth.permission_required("view_financial_reports")
@requires_money_setting
def yearly():
    db = get_db()
    all_pl = reports.yearly_pl(db)
    page = get_page()
    total = len(all_pl)
    offset = page_offset(page)
    pl = all_pl[offset:offset + PER_PAGE]
    return render_template("reports_yearly.html", pl=pl,
                            page=page, total_pages=page_count(total), total_count=total)


# ---------------------------------------------------------------------------
# Insights (BI dashboard) & Retention (cohort analysis) — Admin only
# ---------------------------------------------------------------------------
@bp.route("/insights")
@auth.permission_required("view_insights_retention")
@requires_money_setting
def insights():
    months_back = 12
    cutoff = dates.month_list(months_back)[0] + "-01"

    def compute(update):
        # Runs in a background thread — no Flask request/g context exists
        # here, so each query borrows its own connection from the shared
        # pool rather than reusing anything tied to the request that
        # kicked this off.
        def _run(fn):
            con = dbmod.getconn()
            try:
                return fn(con)
            finally:
                con.rollback()  # read-only; explicit rollback before returning to the pool
                dbmod.putconn(con)

        job_defs = [
            ("revenue", lambda c: analytics.revenue_by_category(c, months_back=months_back)),
            ("vets", lambda c: analytics.vet_performance(c, months_back=months_back)),
            # Same window as every other panel on this page — the client
            # list used to be lifetime while the tiles beside it were not.
            ("clients", lambda c: analytics.client_value(c, limit=20, months_back=months_back)),
            ("weekday_load", lambda c: analytics.appointment_weekday_load(c, months_back=months_back)),
            ("occupancy", lambda c: analytics.inpatient_boarding_occupancy(c, months_back=months_back)),
            ("payment_mix", lambda c: [dict(r) for r in c.execute(
                "SELECT method, COUNT(*) c, COALESCE(SUM(amount),0) total FROM payments "
                "WHERE date >= ? GROUP BY method ORDER BY total DESC",
                (cutoff,),
            ).fetchall()]),
            ("cash_register_health", lambda c: cash_register.cash_register_last_30_days(c)),
        ]
        results = {}
        # Capped rather than len(job_defs) — this report alone shouldn't be
        # able to claim most of the DB connection pool at once and starve
        # every other request. See ERROR_500_AUDIT.md E-03.
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {ex.submit(_run, fn): name for name, fn in job_defs}
            done = 0
            # as_completed gives real progress: update() fires exactly when
            # each section's own query actually finishes, not on a timer
            # standing in for it.
            for fut in as_completed(futures):
                name = futures[fut]
                results[name] = fut.result()
                done += 1
                update(done)

        top_clients, avg_spend, active_client_count = results["clients"]
        return {
            "revenue": results["revenue"], "vets": results["vets"],
            "top_clients": top_clients, "avg_spend": avg_spend,
            "active_client_count": active_client_count,
            "weekday_load": results["weekday_load"], "occupancy": results["occupancy"],
            "payment_mix": results["payment_mix"], "months_back": months_back,
            "cash_register_health": results["cash_register_health"],
        }

    return _render_with_progress(
        "insights.html",
        [_("Revenue by category"), _("Vet performance"), _("Client value"),
         _("Weekday appointment load"), _("Inpatient/boarding occupancy"),
         _("Payment mix"), _("Cash Register health")],
        compute,
        page_title="Loading Insights",
        page_note="Running six report queries in parallel.",
    )


@bp.route("/retention")
@auth.permission_required("view_insights_retention")
def retention():
    page = get_page()

    def compute(update):
        # Runs in a background thread, so its own connection (not g.db).
        con = dbmod.connect()
        try:
            full = analytics.cohort_retention_grid(con, max_offset=11)
        finally:
            con.close()
        total = len(full["grid"])
        total_pages = page_count(total)
        eff_page = min(page, total_pages)
        offset = page_offset(eff_page)
        page_grid = full["grid"][offset:offset + PER_PAGE]
        cohort = {"cohort_months": full["cohort_months"][offset:offset + PER_PAGE],
                  "offsets": full["offsets"], "grid": page_grid}
        return {"cohort": cohort, "page": eff_page, "total_pages": total_pages, "total_count": total}

    return _render_with_progress(
        "retention.html",
        [_("Computing cohort retention grid")],
        compute,
        page_title="Loading Retention",
        page_note="Computing cohort retention across every month with visit history.",
    )


@bp.route("/reports/opex", methods=["POST"])
@auth.permission_required("view_financial_reports")
@requires_money_setting
def opex_save():
    db = get_db()
    f = request.form

    def redisplay():
        return render_template("reports.html", **_reports_context(db), form=f)

    month = f.get("month", "").strip()
    if not month:
        flash(_("Pick a month first."), "error")
        return redisplay()
    # strict_month(), not a \d{4}-\d{2} pattern: that accepted 2026-13,
    # stored under a month no report ever shows (audit B1).
    try:
        strict_month(month)
    except ValueError:
        flash(_("That's not a valid month."), "error")
        return redisplay()
    try:
        rent = parse_money(f.get("rent")) or 0
        salaries = parse_money(f.get("salaries")) or 0
        utilities = parse_money(f.get("utilities")) or 0
        marketing = parse_money(f.get("marketing")) or 0
        other = parse_money(f.get("other")) or 0
    except BadNumber:
        flash(_("Operating costs must be valid numbers."), "error")
        return redisplay()
    # A negative operating cost does not reduce spending, it reads as income:
    # yearly_pl() computes net_profit = gross_profit - total_opex, so a
    # negative column makes total_opex smaller and the reported profit LARGER.
    # A single mistyped "-100,000" rent moved the annual net profit figure by
    # +200,000 in testing.
    if has_negative(rent, salaries, utilities, marketing, other):
        flash(_("Operating costs can't be negative."), "error")
        return redisplay()
    db.execute(
        """INSERT INTO monthly_opex (month, rent, salaries, utilities, marketing, other) VALUES (?,?,?,?,?,?)
           ON CONFLICT(month) DO UPDATE SET rent=excluded.rent, salaries=excluded.salaries,
           utilities=excluded.utilities, marketing=excluded.marketing, other=excluded.other""",
        (month, rent, salaries, utilities, marketing, other),
    )
    auth.log_change(db, "monthly_opex", month, "update")
    db.commit()
    flash(_("Operating costs saved for %(month)s.", month=month), "success")
    return redirect(url_for("reports.monthly"))
