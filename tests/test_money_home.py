"""
The money setting has one home (plan §12, "Done means" items 3 and 4).

- Nothing outside vcs/money.py rounds money, and nothing compares the money
  setting's code or carries a country's literals (its currency code, phone
  prefix, time zone, Arabic currency label). Everything that differs between
  IQ and JO is a value of money.SETTINGS, so code written once cannot drift
  into "for IQ" or "for JO" (CLAUDE.md §0).
- The one writer of stored totals is billing.bill_changed(): seam rule 12,
  held by tests/test_seam_rules.py.

Pure tier: an AST scan of every application module, so a docstring or a
comment that NAMES a country is not a finding; code that uses one is.
"""
import ast

import source_files

# Code the rule allows, by (file, function), each with its reason.
ALLOWED = {
    # A discount PERCENT, rounded to its two places -- not money.
    ("core.py", "parse_percent"): "percent",
    # The translated display names of the two settings: pybabel extracts a
    # msgid only from a literal, so the two names are spelled out.
    ("core.py", "money_setting_label"): "label",
}
LITERALS = ("IQD", "JOD", "+964", "+962", "00964", "00962", "Asia/Baghdad", "Asia/Amman", "د.ع", "د.أ")
ROUNDING = ("quantize", "ROUND_HALF_UP", "ROUND_HALF_EVEN", "ROUND_DOWN", "ROUND_UP", "ROUND_FLOOR", "ROUND_CEILING")


def _docstrings(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


def findings(name, source):
    """(line, what) for each use of the money setting outside its home."""
    tree = ast.parse(source)
    docs = _docstrings(tree)
    owner = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                owner.setdefault(id(node), fn.name)
    out = []
    for node in ast.walk(tree):
        if (name, owner.get(id(node))) in ALLOWED:
            continue
        if isinstance(node, ast.Compare):
            for side in [node.left, *node.comparators]:
                if isinstance(side, ast.Constant) and side.value in ("IQ", "JO"):
                    out.append((node.lineno, f"compares with {side.value!r}"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            hit = [lit for lit in LITERALS if lit in node.value]
            if hit:
                out.append((node.lineno, f"literal {hit[0]!r}"))
        elif isinstance(node, (ast.Attribute, ast.Name)):
            ident = node.attr if isinstance(node, ast.Attribute) else node.id
            if ident in ROUNDING:
                out.append((node.lineno, f"rounds with {ident}"))
    return sorted(set(out))


def test_control_the_scan_sees_code_and_not_prose():
    source = '''
"""IQ rounds to the 250-IQD note (a docstring may say so)."""
from decimal import ROUND_HALF_UP
def f(code, x):
    # a comment may name +964 too
    if code == "IQ":
        return x.quantize(1, rounding=ROUND_HALF_UP)
    return "+962" + x
'''
    assert findings("x.py", source) == [
        (6, "compares with 'IQ'"), (7, "rounds with ROUND_HALF_UP"), (7, "rounds with quantize"),
        (8, "literal '+962'")]


def test_control_an_allowed_function_is_allowed_and_nothing_else():
    source = 'def money_setting_label(code):\n    if code == "IQ":\n        return "IQD"\n' \
             'def other(code):\n    return code == "JO"\n'
    assert findings("core.py", source) == [(5, "compares with 'JO'")]


def test_the_money_setting_has_one_home():
    """GUARD. money.py is the home; clock.py resolves a zone FROM a setting."""
    home = {source_files.module("money")}
    files = [p for p in source_files.all_python() if p not in home]
    assert len(files) >= 60, f"only {len(files)} modules scanned — did the package move?"
    found = [f"{p.relative_to(source_files.ROOT)}:{line}: {what}"
             for p in files for line, what in findings(p.name, p.read_text(encoding="utf-8"))]
    assert not found, (
        "the money setting's values belong in money.SETTINGS, and money is rounded "
        "only in money.py:\n  " + "\n  ".join(found))


def test_every_allowance_names_a_function_that_exists():
    """An allowance for a function that was renamed allows nothing — and so
    hides nothing either; but it reads as if the rule had an exception."""
    for (name, function), _ in ALLOWED.items():
        path = next(p for p in source_files.all_python() if p.name == name)
        assert f"def {function}(" in path.read_text(encoding="utf-8"), f"{name} has no {function}()"
