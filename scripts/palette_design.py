#!/usr/bin/env python3
"""
How the palettes in vcs/web/palettes.py were made -- a design tool, not part
of the app.

Each new palette is a few seeds (an accent hue, a sidebar hue and style, a
neutral tint). Every token is derived from them in OKLCH, where a hue stays
the same hue while its lightness moves, and each text colour's lightness is
then pushed until every pair it is used in passes WCAG AA (4.5:1) with a
small margin -- the same pairs tests/test_palettes.py checks.

    /tmp/vcs_test_venv_jo/bin/python scripts/palette_design.py > proposal.py

prints the palettes as Python literals, to review and paste into
vcs/web/palettes.py. Re-running it is how a palette is re-derived.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vcs.web.palettes import TEXT_PAIRS, contrast  # noqa: E402

MARGIN = 4.6          # AA is 4.5; a little headroom for rounding to hex


# --- OKLCH <-> sRGB (Björn Ottosson's OKLab) --------------------------------
def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def oklch_to_hex(L, C, h):
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    bl = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_
    rgb = [min(max(_gam(max(x, 0.0)), 0.0), 1.0) for x in (r, g, bl)]
    return "#" + "".join(f"{round(x * 255):02X}" for x in rgb)


def hex_to_oklch(hex_):
    r, g, b = (_lin(int(hex_[i:i + 2], 16) / 255) for i in (1, 3, 5))
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def fix(hex_, against, darker):
    """The same hue and chroma, lightness moved until `hex_` passes against
    every colour in `against` -- how a predecessor palette is brought to AA
    without changing its character."""
    if all(contrast(hex_, o) >= MARGIN for o in against):
        return hex_
    L, C, h = hex_to_oklch(hex_)
    return solve(L, C, h, against, darker)


def solve(L, C, h, against, darker, step=0.005):
    """Move L (darker or lighter) until the colour meets MARGIN against every
    colour in `against`."""
    for _ in range(400):
        c = oklch_to_hex(L, C, h)
        if all(contrast(c, other) >= MARGIN for other in against):
            return c
        L += -step if darker else step
    raise SystemExit(f"cannot solve L for hue {h} against {against}")


def derive(seed):
    """seed: key, label, accent (hue, chroma), neutral (hue, chroma),
    sidebar (hue, chroma, 'dark'|'light')."""
    hp, cp = seed["accent"]
    hn, cn = seed["neutral"]
    hs, cs, style = seed["sidebar"]
    out = {}

    # ---- light ----
    t = {}
    t["bg"] = oklch_to_hex(0.975, cn * 0.6, hn)
    t["paper"] = "#FFFFFF"
    t["line"] = oklch_to_hex(0.905, cn, hn)
    t["line-soft"] = oklch_to_hex(0.950, cn * 0.8, hn)
    t["muted-tint"] = oklch_to_hex(0.955, cn * 0.8, hn)
    t["ink"] = oklch_to_hex(0.24, cn * 1.6, hn)
    t["primary-tint"] = oklch_to_hex(0.950, cp * 0.22, hp)
    t["ink-soft"] = solve(0.56, cn * 1.4, hn, [t["bg"], t["paper"], t["muted-tint"]], darker=True)
    t["muted"] = solve(0.60, cn * 1.2, hn, [t["bg"], t["paper"], t["muted-tint"]], darker=True)
    t["on-primary"] = "#FFFFFF"
    t["primary"] = solve(0.62, cp, hp, [t["paper"], t["bg"], t["primary-tint"], t["on-primary"]], darker=True)
    t["primary-dark"] = solve(0.50, cp, hp, [t["paper"], t["primary-tint"], t["on-primary"]], darker=True)
    for name, h, c in (("ok", 150, 0.09), ("danger", 32, 0.12)):
        t[f"{name}-tint"] = oklch_to_hex(0.955, 0.03, h)
        t[name] = solve(0.62, c, h, [t[f"{name}-tint"], t["paper"], t["on-primary"]], darker=True)
    t["danger-dark"] = solve(0.47, 0.12, 32, [t["on-primary"]], darker=True)
    t["warn-tint"] = oklch_to_hex(0.965, 0.03, 85)
    t["warn"] = oklch_to_hex(0.72, 0.12, 75)
    t["warn-ink"] = solve(0.60, 0.11, 70, [t["warn-tint"], t["paper"]], darker=True)
    _sidebar(t, hs, cs, style, dark_theme=False)
    out["light"] = t

    # ---- dark ----
    d = {}
    d["bg"] = oklch_to_hex(0.165, cn * 0.9, hn)
    d["paper"] = oklch_to_hex(0.205, cn * 0.9, hn)
    d["line"] = oklch_to_hex(0.310, cn, hn)
    d["line-soft"] = oklch_to_hex(0.255, cn, hn)
    d["muted-tint"] = oklch_to_hex(0.245, cn, hn)
    d["ink"] = oklch_to_hex(0.945, cn * 0.6, hn)
    d["primary-tint"] = oklch_to_hex(0.285, cp * 0.35, hp)
    d["ink-soft"] = solve(0.70, cn * 1.2, hn, [d["bg"], d["paper"], d["muted-tint"]], darker=False)
    d["muted"] = solve(0.66, cn * 1.2, hn, [d["bg"], d["paper"], d["muted-tint"]], darker=False)
    d["on-primary"] = d["bg"]
    d["primary"] = solve(0.66, cp * 0.9, hp, [d["paper"], d["bg"], d["primary-tint"], d["on-primary"]], darker=False)
    d["primary-dark"] = solve(0.76, cp * 0.8, hp, [d["paper"], d["primary-tint"], d["on-primary"]], darker=False)
    for name, h, c in (("ok", 150, 0.10), ("danger", 32, 0.11)):
        d[f"{name}-tint"] = oklch_to_hex(0.255, 0.035, h)
        d[name] = solve(0.70, c, h, [d[f"{name}-tint"], d["paper"], d["on-primary"]], darker=False)
    d["danger-dark"] = solve(0.78, 0.10, 32, [d["on-primary"]], darker=False)
    d["warn-tint"] = oklch_to_hex(0.265, 0.035, 80)
    d["warn"] = oklch_to_hex(0.76, 0.11, 75)
    d["warn-ink"] = solve(0.76, 0.11, 75, [d["warn-tint"], d["paper"]], darker=False)
    _sidebar(d, hs, cs, "dark", dark_theme=True)
    out["dark"] = d
    for theme, tokens in out.items():
        tokens["chart-2"] = chart2(tokens, dark=theme == "dark")
    return out


def chart2(t, dark):
    """The second Insights series: a mid-tone of the sidebar's hue, visible
    on a card in both themes (3:1 -- the sidebar colour itself is not: a dark
    sidebar vanishes on a dark card, a light one on a white card)."""
    L, C, h = hex_to_oklch(t["sidebar-bg"])
    C = max(C * 1.6, 0.06)
    for step in range(400):
        c = oklch_to_hex((0.72 + step * 0.005) if dark else (0.46 - step * 0.005), C, h)
        if contrast(c, t["paper"]) >= 3.1:
            return c
    raise SystemExit("cannot solve chart-2")


def _sidebar(t, hs, cs, style, dark_theme):
    if style == "dark":
        t["sidebar-bg"] = oklch_to_hex(0.15 if dark_theme else 0.27, cs, hs)
        t["sidebar-ink"] = oklch_to_hex(0.94, min(cs, 0.02), hs)
        t["sidebar-active"] = oklch_to_hex(0.25 if dark_theme else 0.36, cs * 1.1, hs)
        t["sidebar-active-ink"] = t["sidebar-ink"]
        t["sidebar-muted"] = solve(0.66, cs * 0.8, hs, [t["sidebar-bg"]], darker=False)
        white = "255,255,255"
        t["sidebar-line"] = f"rgba({white},0.08)"
        t["sidebar-hover"] = f"rgba({white},0.05)"
        t["sidebar-control"] = f"rgba({white},0.12)"
        t["sidebar-control-hover"] = f"rgba({white},0.22)"
        t["sidebar-control-border"] = f"rgba({white},0.28)"
    else:
        t["sidebar-bg"] = oklch_to_hex(0.93, cs, hs)
        t["sidebar-ink"] = oklch_to_hex(0.26, cs * 1.4, hs)
        t["sidebar-active"] = "#FFFFFF"
        t["sidebar-active-ink"] = t["primary-dark"]
        t["sidebar-muted"] = solve(0.50, cs * 1.2, hs, [t["sidebar-bg"]], darker=True)
        ink = t["sidebar-ink"]
        rgb = ",".join(str(int(ink[i:i + 2], 16)) for i in (1, 3, 5))
        t["sidebar-line"] = f"rgba({rgb},0.10)"
        t["sidebar-hover"] = f"rgba({rgb},0.06)"
        t["sidebar-control"] = "rgba(255,255,255,0.55)"
        t["sidebar-control-hover"] = "rgba(255,255,255,0.85)"
        t["sidebar-control-border"] = f"rgba({rgb},0.18)"


# The twelve new palettes (owner decision D-12): calm, and far enough apart
# on the wheel, in lightness or in sidebar style to tell apart at a glance.
SEEDS = [
    {"key": "sage", "label": "Sage", "accent": (148, 0.075), "neutral": (135, 0.010), "sidebar": (160, 0.040, "dark")},
    {"key": "mint", "label": "Mint", "accent": (180, 0.070), "neutral": (175, 0.010), "sidebar": (178, 0.030, "light")},
    {"key": "harbor", "label": "Harbor", "accent": (205, 0.080), "neutral": (215, 0.010), "sidebar": (215, 0.045, "dark")},
    {"key": "ocean", "label": "Ocean", "accent": (240, 0.110), "neutral": (240, 0.010), "sidebar": (238, 0.035, "light")},
    {"key": "slate", "label": "Slate", "accent": (258, 0.070), "neutral": (255, 0.008), "sidebar": (255, 0.025, "dark")},
    {"key": "indigo", "label": "Indigo", "accent": (278, 0.115), "neutral": (275, 0.010), "sidebar": (278, 0.065, "dark")},
    {"key": "lavender", "label": "Lavender", "accent": (302, 0.090), "neutral": (300, 0.010), "sidebar": (302, 0.035, "light")},
    {"key": "orchid", "label": "Orchid", "accent": (342, 0.100), "neutral": (345, 0.010), "sidebar": (348, 0.045, "dark")},
    {"key": "terracotta", "label": "Terracotta", "accent": (40, 0.110), "neutral": (50, 0.012), "sidebar": (48, 0.028, "light")},
    {"key": "sand", "label": "Sand", "accent": (72, 0.095), "neutral": (78, 0.012), "sidebar": (62, 0.030, "dark")},
    {"key": "olive", "label": "Olive", "accent": (112, 0.085), "neutral": (105, 0.012), "sidebar": (108, 0.035, "light")},
    {"key": "graphite", "label": "Graphite", "accent": (250, 0.020), "neutral": (250, 0.004), "sidebar": (250, 0.006, "light")},
]


def main():
    print("NEW = {")
    for seed in SEEDS:
        themes = derive(seed)
        print(f'    "{seed["key"]}": ("{seed["label"]}", {{')
        for theme in ("light", "dark"):
            print(f'        "{theme}": {{')
            for k, v in themes[theme].items():
                print(f'            "{k}": "{v}",')
            print("        },")
        print("    }),")
    print("}")
    # the same check the test makes
    for seed in SEEDS:
        for theme, t in derive(seed).items():
            for fg, bg, need in TEXT_PAIRS:
                c = contrast(t[fg], t[bg], base=t.get("sidebar-bg"))
                if c < need:
                    print(f"# FAIL {seed['key']} {theme}: {fg} on {bg} = {c:.2f}", file=sys.stderr)


if __name__ == "__main__":
    main()
