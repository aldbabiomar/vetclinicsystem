"""
Where the application's source lives, for the tests that read it.

Many tests scan source text -- for a rule that must hold everywhere, or for
a string that must not be there. Each used to build its own paths
("app.py", ROOT / "routes"), so moving the code meant finding every one of
them; a scan left pointing at a file that no longer exists passes, having
read nothing. They all read from here now, so a move is one edit.

Not a test module (no test_ prefix): import what you need.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "vcs"

APP = ROOT / "app.py"                                   # the app and its top-level routes
ROUTES = sorted((ROOT / "routes").glob("*.py"))         # the blueprints
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
TRANSLATIONS_DIR = ROOT / "translations"
MIGRATIONS_DIR = PKG / "db" / "migrations"
CATALOGUE = TRANSLATIONS_DIR / "ar" / "LC_MESSAGES" / "messages.po"

# A module by its short name, wherever it lives in the package.
_MODULES = {p.stem: p for p in PKG.rglob("*.py") if p.stem != "__init__"}


def module(name):
    """The source file of a module: module("logic"), module("pool")."""
    path = _MODULES.get(name)
    assert path is not None, f"no module named {name!r} under vcs/"
    return path


def web_modules():
    """The request layer: the app and every blueprint."""
    return [APP, *ROUTES]


def all_python():
    """Every application Python file: the app, the blueprints and the
    package (setup.py and the tests excluded)."""
    return [APP, *ROUTES, *sorted(p for p in PKG.rglob("*.py"))]


def templates():
    return sorted(TEMPLATES_DIR.glob("*.html"))
