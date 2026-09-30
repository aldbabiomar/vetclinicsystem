"""
The colour palettes (owner decisions D-12, D-17): fifteen, each light and
dark, every text/background pair the stylesheet draws WCAG AA, distinct
from one another, and the CSS generated from the one registry.

vcs/web/palettes.py is the definition. These tests hold it to its promises,
and hold the stylesheet to using only what it defines.
"""
import itertools
import math
import re
import sys

import pytest

import source_files
from vcs.web import palettes as P

sys.path.insert(0, str(source_files.ROOT / "scripts"))
import palette_design  # noqa: E402  (the colour maths the palettes were designed with)

THEMES = [(key, theme) for key in P.PALETTES for theme in ("light", "dark")]
STYLE_CSS = source_files.STATIC_DIR / "style.css"
PALETTES_CSS = source_files.STATIC_DIR / "palettes.css"
# Tokens that are not colours and so are not the palettes' business.
LAYOUT_TOKENS = {"radius", "radius-sm", "topbar-h", "shadow-sm", "shadow", "shadow-lg"}


def _tokens(key, theme):
    p = P.PALETTES[key]
    return p.light if theme == "light" else p.dark


def test_there_are_fifteen_palettes_and_slate_is_the_default():
    assert len(P.PALETTES) == 15
    assert P.DEFAULT == "slate"
    assert {"vetzone", "champet", "crimson"} <= set(P.PALETTES), "the predecessor apps' palettes are kept"


@pytest.mark.parametrize("key,theme", THEMES)
def test_every_theme_defines_exactly_the_tokens(key, theme):
    """GUARD. A missing token falls back to the default palette's value --
    a crimson button on a sage page, and nothing reports it."""
    assert set(_tokens(key, theme)) == set(P.TOKENS)


@pytest.mark.parametrize("key,theme", THEMES)
def test_every_pair_the_stylesheet_draws_is_aa(key, theme):
    """GUARD (D-12): text 4.5:1, icons and chart series 3:1."""
    t = _tokens(key, theme)
    failures = [f"{fg} on {bg}: {P.contrast(t[fg], t[bg], base=t['sidebar-bg']):.2f} < {need}"
                for fg, bg, need in P.TEXT_PAIRS
                if P.contrast(t[fg], t[bg], base=t["sidebar-bg"]) < need]
    assert not failures, f"{key} ({theme}):\n  " + "\n  ".join(failures)


def _mix(a, b, share):
    """color-mix(in srgb, a share, b)."""
    ra, rb = P.rgba(a), P.rgba(b)
    return "#" + "".join(f"{round(ra[i] * share + rb[i] * (1 - share)):02X}" for i in range(3))


@pytest.mark.parametrize("key,theme", THEMES)
def test_text_on_the_darkest_heatmap_cell_is_aa(key, theme):
    """GUARD. The Retention heatmap keeps the page's text on its cells."""
    t = _tokens(key, theme)
    cell = _mix(t["primary"], t["paper"], P.HEATMAP_MAX_MIX)
    assert P.contrast(t["ink"], cell) >= P.AA_TEXT


def test_control_contrast_is_measured_right():
    """CONTROL on the measure every guard above relies on."""
    assert round(P.contrast("#000000", "#FFFFFF"), 1) == 21.0
    assert round(P.contrast("#777777", "#FFFFFF"), 2) == 4.48          # the classic just-fails grey
    assert P.contrast("#FFFFFF", "rgba(255,255,255,0.05)", base="#051335") > 15
    with pytest.raises(ValueError):
        P.contrast("#FFFFFF", "rgba(255,255,255,0.05)")                 # translucent needs a base


def _oklab(hex_):
    L, C, h = palette_design.hex_to_oklch(hex_)
    return L, C * math.cos(math.radians(h)), C * math.sin(math.radians(h))


def test_the_palettes_are_distinct():
    """GUARD (D-12 "distinct"): no two palettes' accent and sidebar together
    within 0.09 in OKLab -- a just-noticeable difference is about 0.02."""
    close = []
    for (k1, p1), (k2, p2) in itertools.combinations(P.PALETTES.items(), 2):
        d = (math.dist(_oklab(p1.light["primary"]), _oklab(p2.light["primary"]))
             + math.dist(_oklab(p1.light["sidebar-bg"]), _oklab(p2.light["sidebar-bg"])))
        if d < 0.09:
            close.append(f"{k1} / {k2}: {d:.3f}")
    assert not close, close


def test_the_stylesheet_is_generated_from_the_registry():
    """GUARD. palettes.css is written by scripts/build_palettes.py; an edit
    by hand, or a registry change without a rebuild, fails here."""
    assert PALETTES_CSS.read_text(encoding="utf-8") == P.css()


def test_every_palette_has_its_blocks_in_the_stylesheet():
    css = PALETTES_CSS.read_text(encoding="utf-8")
    for key in P.PALETTES:
        if key == P.DEFAULT:
            assert css.count(":root {") == 1 and css.count('html[data-theme="dark"] {') == 1
        else:
            assert f'html[data-palette="{key}"] {{' in css
            assert f'html[data-palette="{key}"][data-theme="dark"] {{' in css


def test_the_stylesheet_uses_only_palette_colours():
    """GUARD. A colour token the palettes do not define renders as nothing
    in every palette; one defined in style.css would ignore the palette."""
    used = set()
    for path in [STYLE_CSS, *source_files.templates()]:
        used |= set(re.findall(r"var\(--([\w-]+)", path.read_text(encoding="utf-8")))
    spacing = {u for u in used if u.startswith("space-")}
    stray = used - set(P.TOKENS) - LAYOUT_TOKENS - spacing
    assert not stray, f"colour tokens no palette defines: {sorted(stray)}"
    defined_here = set(re.findall(r"--([\w-]+)\s*:", STYLE_CSS.read_text(encoding="utf-8")))
    assert not (defined_here & set(P.TOKENS)), "style.css redefines palette tokens"


def test_every_label_is_marked_for_translation():
    src = source_files.module("palettes").read_text(encoding="utf-8")
    for p in P.PALETTES.values():
        assert f'N_("{p.label}")' in src


def test_an_unknown_key_shows_the_default():
    assert P.current("no-such") == P.DEFAULT and P.current(None) == P.DEFAULT
    assert P.current("sage") == "sage"


# ---------------------------------------------------------------------------
# The setting, the page and the favicon
# ---------------------------------------------------------------------------
from conftest import needs_db  # noqa: E402


@pytest.fixture
def palette_left_as_found(db):
    row = db.execute("SELECT value FROM settings WHERE key='theme_palette'").fetchone()
    yield
    if row is None:
        db.execute("DELETE FROM settings WHERE key='theme_palette'")
    else:
        db.execute("UPDATE settings SET value=%s WHERE key='theme_palette'", (row["value"],))
    db.commit()


def _save(developer, **fields):
    """The vendor chooses the palette, in the Developer area (L-2)."""
    return developer.post("/developer/configuration", data=fields, follow_redirects=True)


@needs_db
def test_a_chosen_palette_is_saved_and_drawn(client, developer, db, palette_left_as_found):
    """CONTROL: a registry key saves, and every page carries it."""
    _save(developer, theme_palette="sage")
    assert db.execute("SELECT value FROM settings WHERE key='theme_palette'").fetchone()["value"] == "sage"
    html = client.get("/").get_data(as_text=True)
    assert 'data-palette="sage"' in html
    assert "palettes.css" in html and 'class="logo-mark"' in html


@needs_db
def test_a_palette_that_is_not_in_the_registry_is_refused(developer, db, palette_left_as_found):
    """GUARD. The value goes into an HTML attribute and only registry keys
    have CSS behind them."""
    _save(developer, theme_palette="sage")
    resp = _save(developer, theme_palette='x" onload="alert(1)')
    assert "Not a valid color palette." in resp.get_data(as_text=True)
    assert db.execute("SELECT value FROM settings WHERE key='theme_palette'").fetchone()["value"] == "sage"


@needs_db
def test_the_configuration_page_offers_every_palette(developer):
    html = developer.get("/developer/configuration").get_data(as_text=True)
    for key in P.PALETTES:
        assert f'<option value="{key}"' in html


@needs_db
def test_the_favicon_is_the_mark_in_the_palettes_accent(client, developer, db, palette_left_as_found):
    _save(developer, theme_palette="orchid")
    resp = client.get("/favicon.svg")
    assert resp.status_code == 200 and resp.mimetype == "image/svg+xml"
    assert f'color="{P.PALETTES["orchid"].light["primary"]}"' in resp.get_data(as_text=True)
    assert client.get("/favicon.ico").get_data() == resp.get_data()


@needs_db
def test_the_favicon_needs_no_sign_in(flask_app):
    anon = flask_app.test_client()
    assert anon.get("/favicon.svg").status_code == 200
