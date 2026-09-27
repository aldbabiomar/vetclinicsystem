#!/usr/bin/env python3
"""
Regenerates the desktop-shortcut icons (`installer_assets/appicon.icns`,
`appicon.ico`, `appicon.png`) from the logo mark (owner decision D-18,
vcs/web/brand.py), in the default palette's accent (D-17).

    /tmp/vcs_test_venv_jo/bin/python scripts/make_app_icons.py

A desktop shortcut cannot follow the clinic's palette the way the favicon
does, so it carries the default one. The icons are committed binaries: this
recipe is how to reproduce them after a change to the mark.

The mark is rendered by headless Chromium (Playwright, which the browser
tests already need) on a transparent background, so its alpha is exact.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MASTER = 1024
ICNS_SIZES = [16, 32, 128, 256, 512]  # each also emitted at @2x
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _mark_alpha():
    """The mark's coverage as an 8-bit alpha channel at MASTER size."""
    from playwright.sync_api import sync_playwright
    from vcs.web import brand
    svg = brand.favicon_svg("#000000").replace("<svg ", f'<svg width="{MASTER}" height="{MASTER}" ', 1)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": MASTER, "height": MASTER})
        page.set_content(f'<html><body style="margin:0;background:transparent">{svg}</body></html>')
        with tempfile.TemporaryDirectory() as tmp:
            shot = os.path.join(tmp, "mark.png")
            page.screenshot(path=shot, omit_background=True, clip={"x": 0, "y": 0, "width": MASTER, "height": MASTER})
            browser.close()
            return Image.open(shot).convert("RGBA").split()[3]


def _rounded_card(size, radius, fill, border):
    """The white squircle-ish plate the glyph sits on, so the icon reads as an
    app icon on any wallpaper instead of floating hairlines."""
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=fill,
                        outline=border, width=max(1, size // 340))
    return card


def build_icon(alpha, tint):
    """Composites the tinted glyph onto the card at the master size."""
    canvas = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))

    margin = round(MASTER * 0.035)
    card_size = MASTER - margin * 2
    card = _rounded_card(card_size, round(card_size * 0.2237),
                         (255, 255, 255, 255), (17, 24, 39, 26))
    canvas.alpha_composite(card, (margin, margin))

    glyph = Image.new("RGBA", (MASTER, MASTER), tint + (0,))
    glyph.putalpha(alpha)
    target = round(MASTER * 0.58)
    glyph = glyph.resize((target, target), Image.LANCZOS)
    offset = (MASTER - target) // 2
    canvas.alpha_composite(glyph, (offset, offset))
    return canvas


def write_icns(master, dest, workdir):
    iconset = os.path.join(workdir, "appicon.iconset")
    os.makedirs(iconset, exist_ok=True)
    for size in ICNS_SIZES:
        master.resize((size, size), Image.LANCZOS).save(
            os.path.join(iconset, f"icon_{size}x{size}.png"))
        retina = size * 2
        master.resize((retina, retina), Image.LANCZOS).save(
            os.path.join(iconset, f"icon_{size}x{size}@2x.png"))
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", dest],
                   check=True, capture_output=True, text=True)


def write_ico(master, dest):
    master.save(dest, format="ICO", sizes=[(s, s) for s in ICO_SIZES])


def main():
    from vcs.web import palettes
    accent = palettes.PALETTES[palettes.DEFAULT].light["primary"]
    tint = tuple(int(accent[i:i + 2], 16) for i in (1, 3, 5))
    dest_dir = ROOT / "installer_assets"
    dest_dir.mkdir(exist_ok=True)
    master = build_icon(_mark_alpha(), tint)
    master.save(dest_dir / "appicon.png")
    with tempfile.TemporaryDirectory() as workdir:
        write_icns(master, str(dest_dir / "appicon.icns"), workdir)
    write_ico(master, str(dest_dir / "appicon.ico"))
    print(f"wrote installer_assets/appicon.icns, .ico and .png in {palettes.DEFAULT} ({accent})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
