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
WEB = PKG / "web"

BLUEPRINTS = sorted(p for p in (WEB / "blueprints").glob("*.py") if p.name != "__init__.py")
# The request layer beside the blueprints: what runs around every request,
# the error handlers, and what every template can use.
WEB_APP = [WEB / "hooks.py", WEB / "errors.py", WEB / "templating.py", WEB / "factory.py"]
TEMPLATES_DIR = PKG / "templates"
STATIC_DIR = PKG / "static"
TRANSLATIONS_DIR = PKG / "translations"
MIGRATIONS_DIR = PKG / "db" / "migrations"
CATALOGUE = TRANSLATIONS_DIR / "ar" / "LC_MESSAGES" / "messages.po"
RUN = ROOT / "run.py"

# A module by its short name, wherever it lives in the package. The
# blueprints are not in it -- `reports` is the domain module, and the
# blueprint of the same name is in BLUEPRINTS.
_MODULES = {}
for _p in sorted(PKG.rglob("*.py")):
    if _p.stem == "__init__" or _p.parent.name == "blueprints":
        continue
    assert _p.stem not in _MODULES, f"two modules named {_p.stem!r}: {_MODULES[_p.stem]} and {_p}"
    _MODULES[_p.stem] = _p


def module(name):
    """The source file of a module: module("billing"), module("pool")."""
    path = _MODULES.get(name)
    assert path is not None, f"no module named {name!r} under vcs/"
    return path


def blueprint(name):
    path = WEB / "blueprints" / f"{name}.py"
    assert path.exists(), f"no blueprint module {name!r}"
    return path


def domain_modules():
    """The queries and calculations: every module under vcs/domain/."""
    mods = sorted(p for p in (PKG / "domain").glob("*.py") if p.name != "__init__.py")
    assert len(mods) >= 18, f"expected the domain modules, found {[p.name for p in mods]}"
    return mods


def web_modules():
    """The request layer: every blueprint, and the hooks, error handlers,
    templating and factory that used to be app.py."""
    for p in [*BLUEPRINTS, *WEB_APP]:
        assert p.exists(), f"{p} is gone: tests/source_files.py needs updating"
    assert len(BLUEPRINTS) >= 8, f"expected the eight blueprints, found {[p.name for p in BLUEPRINTS]}"
    return [*BLUEPRINTS, *WEB_APP]


def all_python():
    """Every application Python file: the package and the launcher (setup.py
    and the tests excluded)."""
    return [RUN, *sorted(PKG.rglob("*.py"))]


def templates():
    return sorted(TEMPLATES_DIR.glob("*.html"))
