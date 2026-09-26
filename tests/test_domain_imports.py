"""
A domain module's name is never rebound in a file that imports it
(restructure R3).

logic.py became modules named for their areas -- billing, search, settings,
consignment, refunds -- and those are also the natural names for a local
variable in a route. A function that assigns `billing = ...` and calls
`billing.visit_billing_summary(...)` raises UnboundLocalError, and only when
that one path runs; one that assigns it after the call quietly works until
someone reorders two lines. The split renamed the eight locals it met; this
keeps the next one from arriving.
"""
import ast

import source_files


def _domain_imports(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == "vcs.domain":
            for a in n.names:
                yield a.asname or a.name


def _rebindings(tree, name):
    """Lines where `name` is bound other than by its `from vcs.domain import`."""
    lines = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)) and n.id == name:
            lines.append(n.lineno)
        elif isinstance(n, ast.arg) and n.arg == name:
            lines.append(n.lineno)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name:
            lines.append(n.lineno)
        elif isinstance(n, (ast.Import, ast.ImportFrom)) and not (
                isinstance(n, ast.ImportFrom) and n.module == "vcs.domain"):
            lines += [n.lineno for a in n.names if (a.asname or a.name.split(".")[0]) == name]
    return lines


def _offenders(tree, label):
    return [f"{label}:{line}: `{name}`"
            for name in sorted(set(_domain_imports(tree))) for line in _rebindings(tree, name)]


def test_no_file_rebinds_a_domain_module_it_imports():
    """GUARD."""
    files = [*source_files.all_python(), *sorted((source_files.ROOT / "tests").glob("*.py"))]
    offenders, imports = [], 0
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports += len(set(_domain_imports(tree)))
        offenders += _offenders(tree, path.relative_to(source_files.ROOT))
    assert imports >= 60, f"only {imports} domain imports found — the scan has lost its subject"
    assert not offenders, (
        "a name that is also an imported domain module is rebound — rename the "
        "local (the split used term, bill, refund_rows, …):\n  " + "\n  ".join(offenders))


def test_control_a_rebinding_is_found():
    """CONTROL: the detector sees each way a name gets bound."""
    src = '''
from vcs.domain import billing, search, settings, refunds, alerts
def view(search):
    billing = billing.visit_billing_summary(None, 1)
    for settings in []:
        pass
    def refunds():
        pass
import json as alerts
'''
    found = _offenders(ast.parse(src), "x")
    assert {f.split("`")[1] for f in found} == {"billing", "search", "settings", "refunds", "alerts"}, found
    assert _offenders(ast.parse("from vcs.domain import billing\nbilling.x()\n"), "x") == []


def _flask_imports(tree):
    """Modules imported from Flask or the request layer, flask_babel aside."""
    found = []
    for n in ast.walk(tree):
        names = ([a.name for a in n.names] if isinstance(n, ast.Import)
                 else [n.module or ""] if isinstance(n, ast.ImportFrom) else [])
        found += [m for m in names if m.split(".")[0] in ("flask", "flask_wtf", "werkzeug")
                  or m.startswith("vcs.web")]
    return found


def test_the_domain_does_not_import_flask_or_the_request_layer():
    """GUARD. vcs/domain runs in request threads, background jobs and the
    scheduler alike (vcs/domain/__init__.py); flask_babel is the one
    allowance."""
    offenders = []
    for path in source_files.domain_modules():
        offenders += [f"{path.name}: {m}" for m in _flask_imports(ast.parse(path.read_text(encoding="utf-8")))]
    assert not offenders, "\n  ".join(["the domain imports the request layer:", *offenders])


def test_control_a_flask_import_is_found():
    src = "from flask import request\nimport werkzeug.exceptions\nfrom vcs.web import core\nfrom flask_babel import gettext\n"
    assert _flask_imports(ast.parse(src)) == ["flask", "werkzeug.exceptions", "vcs.web"]
