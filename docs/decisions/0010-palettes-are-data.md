# 0010 — Palettes are data, generated to CSS, and held to AA by a test

## Context

The owner chose fifteen palettes, each light and dark, with every
text/background pair WCAG AA (D-12), and Slate as the default (D-17). The
predecessor apps wrote palettes by hand into the stylesheet. IQ had two, JO
one, and every one of them failed AA somewhere: secondary and muted text on
the light themes (2.2–4.2:1), and Vetzone's white sidebar text on light blue
(2.1:1). Fifteen hand-written blocks of thirty tokens would be 900 values
that nothing checks.

## Decision

- **One registry**, `vcs/web/palettes.py`: every palette's light and dark
  tokens as data, the token contract (`TOKENS`), and the text/background
  pairs the stylesheet actually draws (`TEXT_PAIRS`: text 4.5:1, icons and
  chart series 3:1).
- **The CSS is generated** (`scripts/build_palettes.py` →
  `vcs/static/palettes.css`). The default palette is the bare `:root`, so a
  page with no palette still has every token. Each other palette overrides it
  by `html[data-palette]`.
- **`style.css` holds no colour.** White-on-accent is `--on-primary`, the
  sidebar's overlays are `--sidebar-*` tokens, and the chart series and the
  Retention heatmap read the palette. A light sidebar (Vetzone, Mint, Ocean,
  Lavender, Terracotta, Olive, Graphite) works as well as a dark one.
- **The twelve new palettes** are derived from a few seeds in OKLCH
  (`scripts/palette_design.py`), each text colour's lightness moved until its
  pairs pass. The three predecessor palettes keep their colours wherever they
  passed and moved lightness only where they failed.
- **The logo mark** (D-18) is one drawing in `currentColor`
  (`vcs/web/brand.py`). The sidebar, the login page and the favicon use it.
  The favicon is served in the palette's accent.

## Consequences

A palette is changed in the registry and the CSS regenerated, never edited by
hand. A new colour use in the stylesheet is a new pair in `TEXT_PAIRS`, or
the test cannot see it.

## Held by

`tests/test_palettes.py`:
- the token contract, AA on every pair in both themes, and the heatmap cell;
- distinctness (OKLab), the CSS generated from the registry, and no colour
  token outside the palettes;
- the Settings field, and the favicon.

`tests/test_browser.py::test_every_palette_paints_the_page_in_both_themes`
proves the wiring in a real browser. Every guard was mutation-checked.
