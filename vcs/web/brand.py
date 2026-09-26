"""
The logo mark (owner decision D-18): a shield with a paw, drawn in
`currentColor` so the palette tints it. One drawing, used three ways: the
sidebar and the login page (`logo_mark()`, a template global) and the
favicon (`favicon_svg()`, served by main.favicon_svg in the palette's accent,
since a favicon cannot read the page's CSS).
"""
from markupsafe import Markup

_DRAWING = (
    '<path d="M12 21.25c-4.55-2.2-7.75-5.6-7.75-10.1V5.6L12 2.75l7.75 2.85v5.55c0 4.5-3.2 7.9-7.75 10.1z"/>'
    '<g fill="currentColor" stroke="none">'
    '<path d="M12 11.4c1.7 0 3.1 1.45 3.1 2.95 0 1.25-.95 1.85-1.9 1.85-.55 0-.8-.25-1.2-.25s-.65.25-1.2.25'
    'c-.95 0-1.9-.6-1.9-1.85 0-1.5 1.4-2.95 3.1-2.95z"/>'
    '<ellipse cx="8.55" cy="10.35" rx="1.05" ry="1.35" transform="rotate(-18 8.55 10.35)"/>'
    '<ellipse cx="10.85" cy="8.35" rx="1" ry="1.35" transform="rotate(-6 10.85 8.35)"/>'
    '<ellipse cx="13.15" cy="8.35" rx="1" ry="1.35" transform="rotate(6 13.15 8.35)"/>'
    '<ellipse cx="15.45" cy="10.35" rx="1.05" ry="1.35" transform="rotate(18 15.45 10.35)"/>'
    '</g>'
)
_OPEN = ('viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" '
         'stroke-linecap="round" stroke-linejoin="round"')


def logo_mark():
    """The mark for a page, in the colour of whatever contains it."""
    return Markup(f'<svg class="logo-mark" {_OPEN} aria-hidden="true" focusable="false">{_DRAWING}</svg>')


def favicon_svg(colour):
    """The mark as a standalone SVG file, in `colour` (a "#RRGGBB")."""
    return f'<svg xmlns="http://www.w3.org/2000/svg" {_OPEN} color="{colour}">{_DRAWING}</svg>'
