#!/usr/bin/env python3
"""Reintroduce each bug the rewards-card guards protect against; require RED.

A guard that has never been watched to refuse is not yet known to be a guard
(CLAUDE.md §7.3). Each mutation is applied to a real file, the named tests are
run, the file is restored, and the result must be a FAILURE.

    python3 scripts/simulation/prove_rewards_guards.py iq
    python3 scripts/simulation/prove_rewards_guards.py jo

Requires the matching isolated environment to be up (scripts/isolated_test_env.sh).
The mutations differ between the apps ONLY where the code genuinely differs —
JO's inpatient guard skips a blocked line where IQ refuses the whole
submission, and JO's money is Decimal. Everything else is the same rule.
"""
import io, os, subprocess, sys

ROOT = "/Users/omaraldbabi/Desktop/VetClinicSystem/webapps"
CFG = {
    "iq": dict(app=f"{ROOT}/vetclinicsystem_iq-main", venv="/tmp/vz_iq_test_venv/bin/python",
               db="postgresql://postgres:test@localhost:55491/vetclinicsystemiq",
               guard_old='''        if (existing_discount and (existing_discount["discount_percent"] or 0) > 0
                and existing_discount["discount_source"] == "staff"):''',
               guard_new='''        if (existing_discount and (existing_discount["discount_percent"] or 0) > 0):''',
               hundred="100",
               # IQ APPORTIONS a stored total, so making every line uniformly
               # discountable cancels in the ratio and changes nothing. The
               # mutation has to be asymmetric to be a mutation at all.
               cat_old="""                            * (1 - CASE WHEN vbl.discountable THEN COALESCE(b.discount_percent,0) ELSE 0 END / 100.0))""",
               cat_new="""                            * (1 - CASE WHEN NOT vbl.discountable THEN COALESCE(b.discount_percent,0) ELSE 0 END / 100.0))""",
               pl_old='        d = case_discount.get(r["case_id"], 0) if r["discountable"] else 0',
               pl_new='        d = case_discount.get(r["case_id"], 0)'),
    "jo": dict(app=f"{ROOT}/vetclinicsystem_jo-main", venv="/tmp/vz_jo_test_venv/bin/python",
               db="postgresql://postgres:test@localhost:55492/vetclinicsystemjo",
               guard_old='''        if (existing_discount and (existing_discount["discount_percent"] or 0) > 0
                and existing_discount["discount_source"] == "staff"):''',
               guard_new='''        if (existing_discount and (existing_discount["discount_percent"] or 0) > 0):''',
               hundred="Decimal(100)",
               # JO RE-DERIVES, so discounting every line changes the total.
               cat_old="""                   * (1 - CASE WHEN vbl.discountable THEN COALESCE(b.discount_percent,0) ELSE 0 END/100.0) AS amount""",
               cat_new="""                   * (1 - COALESCE(b.discount_percent,0)/100.0) AS amount""",
               pl_old='        discount = case_discounts.get(r["case_id"], 0) if r["discountable"] else 0',
               pl_new='        discount = case_discounts.get(r["case_id"], 0)'),
}

REFUSAL = ('''flash(_("This bill carries a rewards-card discount. A staff discount can't be '''
           '''added on top of it, and can't replace it."), "error")''')


def mutations(c):
    T = ["tests/test_rewards.py"]
    S = ["tests/test_seam_rules.py", "tests/test_rewards.py"]
    return [
     ("guard scoping: a member's bill refuses its own non-discountable items",
      "routes/clinical.py", c["guard_old"], c["guard_new"], T),
     ("card-only: visit_discount_save accepts a member bill",
      "routes/clinical.py",
      '''    if member_bill and member_bill["discount_source"] == "member":''',
      '''    if False and member_bill and member_bill["discount_source"] == "member":''', T),
     ("compute_bill_totals gains a default for discountable_subtotal",
      "logic.py",
      "def compute_bill_totals(subtotal, discount_percent, paid, cleanup_amount=0, *,\n"
      "                        discountable_subtotal):",
      "def compute_bill_totals(subtotal, discount_percent, paid, cleanup_amount=0, *,\n"
      "                        discountable_subtotal=None):\n"
      "    discountable_subtotal = subtotal if discountable_subtotal is None else discountable_subtotal", S),
     ("refunds price every line at the discounted rate again",
      "logic.py",
      '        line_discount = discount_percent if r["discountable"] else 0',
      '        line_discount = discount_percent', T),
     ("the visit UPSERT re-stamps the membership snapshot on every save",
      "routes/clinical.py",
      '"manual_amount=excluded.manual_amount, date_billed=excluded.date_billed, notes=excluded.notes",',
      '"manual_amount=excluded.manual_amount, date_billed=excluded.date_billed, notes=excluded.notes, "\n'
      '        "discount_percent=excluded.discount_percent, discount_source=excluded.discount_source",', T),
     ("a new report re-derives revenue from lines x (1 - d)  [rule 8]",
      "logic.py",
      "def discounted_raw_total(subtotal, discountable_subtotal, discount_percent):",
      "def a_new_report(rows, discount_percent):\n"
      "    return sum(r * (1 - discount_percent / %s) for r in rows)\n\n\n"
      "def discounted_raw_total(subtotal, discountable_subtotal, discount_percent):" % c["hundred"], S),
     ("the card dies a day early: >= becomes >",
      "logic.py", "    return expires >= date.today()", "    return expires > date.today()", T),
     ("the removal action reads a percentage from the request",
      "routes/clinical.py",
      '''    db.execute(f"UPDATE {table} SET discount_percent=0, discount_source='staff', "
               f"discount_applied_by=NULL WHERE {key}=?", (bill_id,))''',
      '''    _p = float(request.form.get("discount_percent") or 0)
    db.execute(f"UPDATE {table} SET discount_percent=?, discount_source='staff', "
               f"discount_applied_by=NULL WHERE {key}=?", (_p, bill_id,))''', T),
     ("revenue_by_category stops reading each line's own eligibility",
      "logic.py", c["cat_old"], c["cat_new"], T),
     ("the inpatient P&L stops reading each line's own eligibility",
      "logic.py", c["pl_old"], c["pl_new"], T),
     ("the member rate is pushed through the staff role cap",
      "logic.py",
      '''    rate = member_discount_rate(db)
    if rate <= 0:''',
      '''    import auth as _a
    if member_discount_rate(db) > _a.discount_cap_for():
        return 0, "staff"
    rate = member_discount_rate(db)
    if rate <= 0:''', T),
    ]


def main():
    app = (sys.argv[1] if len(sys.argv) > 1 else "iq").lower()
    if app not in CFG:
        sys.exit("usage: prove_rewards_guards.py {iq|jo}")
    c = CFG[app]
    env = dict(os.environ, TEST_DATABASE_URL=c["db"])
    results = []
    for name, rel, old, new, tests in mutations(c):
        path = os.path.join(c["app"], rel)
        original = io.open(path, encoding="utf-8").read()
        if original.count(old) != 1:
            results.append((name, "SKIPPED-ANCHOR", "matched %d" % original.count(old)))
            continue
        io.open(path, "w", encoding="utf-8").write(original.replace(old, new))
        try:
            p = subprocess.run([c["venv"], "-m", "pytest", *tests, "-q", "--no-header", "-x"],
                               cwd=c["app"], env=env, capture_output=True, text=True, timeout=900)
            last = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
            results.append((name, "RED (good)" if p.returncode else "GREEN (BAD)", last))
        finally:
            io.open(path, "w", encoding="utf-8").write(original)

    print(f"\n=== MUTATION RESULTS ({app.upper()}) ===")
    bad = 0
    for name, verdict, detail in results:
        print(f"{verdict:16} {name}")
        if detail:
            print(f"                 {detail}")
        if verdict != "RED (good)":
            bad += 1
    print(f"\n{len(results)-bad}/{len(results)} mutations correctly caught")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
