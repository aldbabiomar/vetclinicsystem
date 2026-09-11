"""Seam audit — find rules that exist in one code path and not its sibling.

Five of the six findings in SIMULATION_AUDIT_2026-09-11.md had this shape:
a guard written into one surface and not the equivalent one next to it. Each
surface was individually correct, so nothing failed; the rule simply did not
propagate. This script makes that class visible by building a matrix of
"parallel surfaces" x "shared guards" and printing the holes.

It reports CANDIDATES, not defects. A blank cell can be correct — a route
with no money field has no business calling a money guard. The point is to
make every hole a decision someone looked at, rather than an omission nobody
saw. Read the output, then check each hole against the route.
"""
import os, re, sys, ast, json

WEB = "/Users/omaraldbabi/Desktop/VetClinicSystem/webapps"

# Parallel surfaces: groups of functions that do the same job on different
# records. A guard used by some members of a group and not others is the
# shape worth looking at.
GROUPS = {
    "take a payment": [
        ("clinical", "visit_payment_add"),
        ("clinical", "inpatient_payment_add"),
        ("clinical", "boarding_payment"),
        ("sales", "pos_checkout"),
    ],
    "apply a discount": [
        ("clinical", "visit_discount_save"),
        ("clinical", "inpatient_discount_save"),
        ("clinical", "boarding_payment"),
        ("sales", "pos_checkout"),
    ],
    "add billing lines": [
        ("clinical", "visit_billing_save"),
        ("clinical", "inpatient_billing_add"),
    ],
    "record a refund": [
        ("sales", "refund_retail_save"),
        ("sales", "refund_service_save"),
    ],
    "edit a dated record": [
        ("clinical", "visit_edit"),
        ("clinical", "boarding_edit"),
        ("clinical", "inpatient_edit"),
    ],
    "create a person/party": [
        ("clinical", "owner_new"),
        ("clinical", "owner_edit"),
        ("consignment", "distributor_new"),
        ("consignment", "distributor_edit"),
    ],
    "create a priced item": [
        ("inventory", "price_list_new"),
        ("inventory", "price_list_edit"),
        ("inventory", "inventory_catalog_new"),
        ("inventory", "inventory_catalog_edit"),
    ],
    "move consignment stock": [
        ("consignment", "consignment_receiving_new"),
        ("consignment", "consignment_returns_new"),
        ("consignment", "consignment_shrinkage_new"),
    ],
    "cash drawer": [
        ("sales", "cash_register_payout_new"),
        ("sales", "cash_register_audit_new"),
    ],
}

# The shared rules worth tracking. Keyed by a readable name; the value is a
# regex matched against the function's own source text.
GUARDS = {
    "parse_money/qty": r"\bparse_money\s*\(|\bparse_quantity\s*\(",
    "has_negative": r"\bhas_negative\s*\(",
    "clean_date": r"\bclean_date\s*\(",
    "discount cap": r"\bdiscount_percent_error\s*\(",
    "cleanup cap": r"\bcleanup_amount_error\s*\(",
    "stale-write": r"\bstale_edit_error\s*\(",
    "note warning": r"\bflash_cash_denomination_warning\s*\(",
    "FOR UPDATE": r"FOR UPDATE",
    "payable floor": r"\bpayable_total\s*\(",
    "date ordering": r"can't end before it starts|before it was admitted|< str\(",
    "raw float()": r"(?<![\w.])float\s*\(\s*(?:f\.get|request\.form)",
}


def functions_in(path):
    """{name: source text} for every top-level function in a module."""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", None) or node.lineno
            out[node.name] = "".join(lines[node.lineno - 1:end])
    return out


def expand(src, module_fns, depth=2):
    """Inline the bodies of same-module helpers this function calls.

    Without this the scan reports false holes: pos_checkout's row lock lives
    in _lock_and_snapshot_cart_items() after the M4 extraction, so a
    function-body-only grep says "pos_checkout lacks FOR UPDATE" when it does
    not. A guard delegated to a helper is still applied.
    """
    seen = set()
    for _ in range(depth):
        for name, body in module_fns.items():
            if name in seen or not re.search(rf"\b{re.escape(name)}\s*\(", src):
                continue
            seen.add(name)
            src += "\n" + body
    return src


def audit(app):
    root = f"{WEB}/vetclinicsystem_{app}-main"
    mods = {}
    for mod in ("settings", "admin", "consignment", "inventory", "sales", "clinical"):
        p = f"{root}/routes/{mod}.py"
        if os.path.exists(p):
            mods[mod] = functions_in(p)
    mods["app"] = functions_in(f"{root}/app.py")

    print(f"\n{'='*100}\n{app.upper()}  — guard coverage across parallel surfaces\n{'='*100}")
    holes = []
    for group, members in GROUPS.items():
        present = {}
        for mod, fn in members:
            src = mods.get(mod, {}).get(fn)
            if src is not None:
                src = expand(src, mods.get(mod, {}))
            present[(mod, fn)] = None if src is None else {
                g: bool(re.search(pat, src)) for g, pat in GUARDS.items()}
        # only report guards used by at least one member (others are N/A)
        used = {g for v in present.values() if v for g, hit in v.items() if hit}
        used.discard("raw float()")
        if not used:
            continue
        print(f"\n{group}")
        width = max(len(f"{m}.{f}") for m, f in members)
        header = "  " + " " * width + "  " + "  ".join(f"{g[:13]:^13}" for g in sorted(used))
        print(header)
        for (mod, fn), v in present.items():
            label = f"{mod}.{fn}".ljust(width)
            if v is None:
                print(f"  {label}   (not found)")
                continue
            cells = []
            for g in sorted(used):
                if v[g]:
                    cells.append(f"{'yes':^13}")
                else:
                    cells.append(f"{'— ':^13}")
                    holes.append((group, f"{mod}.{fn}", g))
            print(f"  {label}  " + "  ".join(cells))
        # raw float() on form input is always worth naming
        for (mod, fn), v in present.items():
            if v and v.get("raw float()"):
                print(f"    !! {mod}.{fn} calls float() directly on form input")
                holes.append((group, f"{mod}.{fn}", "raw float() on form input"))
    return holes


if __name__ == "__main__":
    allholes = {}
    for app in ("iq", "jo"):
        allholes[app] = audit(app)
    print(f"\n{'='*100}\nHOLES TO REVIEW (a blank is not automatically a bug — check each)\n{'='*100}")
    # a hole present in BOTH apps is a shared design choice; one app only is
    # more likely a genuine divergence
    iq = {(g, f, r) for g, f, r in allholes["iq"]}
    jo = {(g, f, r) for g, f, r in allholes["jo"]}
    both = sorted(iq & jo)
    only_iq = sorted(iq - jo)
    only_jo = sorted(jo - iq)
    print(f"\nIn BOTH apps ({len(both)}) — consistent between the two, so likely deliberate:")
    for g, f, r in both:
        print(f"  [{g}] {f}  lacks  {r}")
    for label, rows in (("IQ only", only_iq), ("JO only", only_jo)):
        print(f"\n{label} ({len(rows)}) — ASYMMETRIC BETWEEN THE APPS, look at these first:")
        for g, f, r in rows:
            print(f"  [{g}] {f}  lacks  {r}")
