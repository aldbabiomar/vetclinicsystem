#!/usr/bin/env python3
"""
Regenerates the desktop-shortcut icons committed into each app
(`installer_assets/appicon.icns` / `appicon.ico`) from the shared source
SVG glyph.

Run from this workspace folder:

    python3 scripts/make_app_icons.py path/to/favicon.svg

Why this exists as a script rather than a one-off: the icons are committed
binaries, so without the recipe next to them nobody can tell later how they
were produced or reproduce them after a tweak to the glyph. Nothing at
install time depends on this file — a clinic machine only ever sees the
already-generated .icns/.ico.

Rasterizing is done with macOS's own QuickLook (`qlmanage`), the only SVG
renderer guaranteed present on this project's dev machines — no cairosvg /
rsvg / Inkscape dependency. QuickLook always composites onto opaque white,
so the glyph's alpha is recovered analytically below (see _glyph_alpha).
"""
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

# The source glyph is a single flat colour on white; this is that colour,
# and the value the un-blending below solves against.
SOURCE_RGB = (178, 28, 67)  # #B21C43

# Each app tints the same glyph to its own --primary token (static/style.css),
# so the two desktop shortcuts are telling apart at a glance rather than being
# two identical icons sitting side by side.
APPS = {
    "iq": {
        "tint": (185, 122, 125),  # #B97A7D — IQ --primary
        "dest": "webapps/vetclinicsystem_iq-main/installer_assets",
    },
    "jo": {
        "tint": (178, 28, 67),  # #B21C43 — JO --primary (the source colour)
        "dest": "webapps/vetclinicsystem_jo-main/installer_assets",
    },
}

MASTER = 1024
ICNS_SIZES = [16, 32, 128, 256, 512]  # each also emitted at @2x
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _render_svg(svg_path, workdir):
    """SVG -> 1024px RGBA PNG, via QuickLook. Comes back on opaque white."""
    local = os.path.join(workdir, "source.svg")
    shutil.copy(svg_path, local)
    subprocess.run(
        ["qlmanage", "-t", "-s", str(MASTER), "-o", workdir, local],
        check=True, capture_output=True, text=True,
    )
    out = os.path.join(workdir, "source.svg.png")
    if not os.path.isfile(out):
        raise RuntimeError("qlmanage did not produce a thumbnail for " + svg_path)
    return Image.open(out).convert("RGBA")


def _glyph_alpha(img):
    """
    Recovers the glyph's real alpha from a flat-colour-on-white render.

    Every pixel QuickLook produced is `a*C + (1-a)*W` for glyph colour C and
    white W — including the anti-aliased edges, which is the whole reason a
    naive "make white transparent" threshold leaves ugly fringing. Solving
    that for `a` on the green channel (C's green is 28 vs white's 255, the
    widest separation of the three, so the least noise-sensitive) recovers
    smooth edges exactly.
    """
    green = img.split()[1]
    span = 255 - SOURCE_RGB[1]
    return green.point(lambda g: max(0, min(255, round((255 - g) * 255 / span))))


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
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    svg_path = sys.argv[1]
    if not os.path.isfile(svg_path):
        print(f"No such SVG: {svg_path}")
        return 1

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with tempfile.TemporaryDirectory() as workdir:
        alpha = _glyph_alpha(_render_svg(svg_path, workdir))
        for name, cfg in APPS.items():
            dest_dir = os.path.join(root, cfg["dest"])
            os.makedirs(dest_dir, exist_ok=True)
            master = build_icon(alpha, cfg["tint"])
            master.save(os.path.join(dest_dir, "appicon.png"))
            write_icns(master, os.path.join(dest_dir, "appicon.icns"), workdir)
            write_ico(master, os.path.join(dest_dir, "appicon.ico"))
            print(f"  {name}: wrote appicon.icns / appicon.ico / appicon.png -> {cfg['dest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
