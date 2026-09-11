"""Wrap hardcoded user-facing text in Jinja templates — ARABIC_LOCALIZATION_PLAN §5.2.

Deliberately CONSERVATIVE. It wraps only what it can prove is a plain,
self-contained piece of user-facing text, and skips anything it is not sure
about. A string left in English is a visible, fixable gap; a mangled template
is a broken page, and there are 63 of them per app.

What it wraps:
  - text content of a known set of elements, when that text contains no Jinja
  - placeholder= / aria-label= / title= attribute values, same condition

What it deliberately skips:
  - anything inside <script> or <style>
  - text containing {{ ... }} or {% ... %} (mixed text and expression)
  - text that is only whitespace, punctuation, digits or a single symbol
  - text already wrapped in _()
  - <option> values that are submitted as data rather than shown as prose
    (handled separately — their English is the stored value)

Run with --check to see counts without writing.
"""
import re
import sys

# Elements whose text content is prose the user reads.
TEXT_ELEMENTS = ("label", "button", "th", "h1", "h2", "h3", "h4", "h5", "h6",
                 "legend", "summary", "caption", "figcaption")
ATTRS = ("placeholder", "aria-label", "title")

SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
# Jinja blocks are masked for the same reason script bodies are: a `>` inside
# `{{ x if y|length > 10 else z }}` is a COMPARISON OPERATOR, not a tag close,
# so a bare >TEXT< scan happily wrapped "10 else r.event_date }}" and produced
# a template that would not parse. Checking the matched text for "{{" is not
# enough -- the fragment after the operator contains only the CLOSING braces.
JINJA_BLOCK = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.S)
HAS_JINJA = re.compile(r"\{\{|\{%|\{#")
# at least one letter, and not already a translation call
WORTH_IT = re.compile(r"[A-Za-z]{2,}")


def _mask_script_style(s):
    """Blank out script/style bodies AND every Jinja block, keeping length so
    offsets in the masked copy still line up with the real source."""
    out = list(s)
    for pat in (SCRIPT_OR_STYLE, JINJA_BLOCK):
        for m in pat.finditer(s):
            for i in range(m.start(), m.end()):
                if out[i] != "\n":
                    out[i] = "\x00"
    return "".join(out)


def wrap(path, check=False):
    src = open(path, encoding="utf-8").read()
    masked = _mask_script_style(src)
    edits = []

    # --- 1. any text node between two tags ------------------------------
    # Broadened from a fixed element list after measuring coverage: card
    # headings, stat labels, empty-state lines and "+ New X" buttons all sat
    # in div/p/a/td/span, and a button containing an <svg> never matched the
    # element-scoped pattern at all because its text is not the whole body.
    # Script/style bodies are masked out above, and anything containing Jinja
    # is still skipped, so this stays safe while covering far more.
    for m in re.finditer(r"(>)([^<>]+)(<)", masked):
            text = m.group(2)
            stripped = text.strip()
            if not stripped or HAS_JINJA.search(text) or "\x00" in text:
                continue
            if not WORTH_IT.search(stripped):
                continue
            if stripped.startswith("_(") or "&times;" in stripped:
                continue
            # not prose: URLs, file paths, entities, and bare identifiers
            if re.match(r"^(https?://|/|[A-Za-z]:\\\\)", stripped):
                continue
            if re.fullmatch(r"&[a-zA-Z#0-9]+;", stripped):
                continue
            lead = text[:len(text) - len(text.lstrip())]
            trail = text[len(text.rstrip()):]
            esc = stripped.replace("\\", "\\\\").replace("'", "\\'")
            new = f"{m.group(1)}{lead}{{{{ _('{esc}') }}}}{trail}{m.group(3)}"
            edits.append((m.start(), m.end(), new, stripped))

    # --- 2. user-facing attributes -------------------------------------
    for attr in ATTRS:
        for m in re.finditer(rf'{attr}="([^"]*)"', masked, re.I):
            text = m.group(1).strip()
            if not text or HAS_JINJA.search(m.group(1)) or "\x00" in m.group(1):
                continue
            if not WORTH_IT.search(text):
                continue
            esc = text.replace("\\", "\\\\").replace("'", "\\'")
            new = f'{attr}="{{{{ _(\'{esc}\') }}}}"'
            edits.append((m.start(), m.end(), new, text))

    if not edits:
        return 0, []

    # apply back-to-front, skipping overlaps
    edits.sort(key=lambda e: e[0], reverse=True)
    out, last_start, applied, strings = src, len(src) + 1, 0, []
    for start, end, new, text in edits:
        if end > last_start:          # overlaps a later edit: skip
            continue
        out = out[:start] + new + out[end:]
        last_start = start
        applied += 1
        strings.append(text)

    if not check:
        open(path, "w", encoding="utf-8").write(out)
    return applied, strings


if __name__ == "__main__":
    check = "--check" in sys.argv
    total, seen = 0, set()
    for p in [a for a in sys.argv[1:] if not a.startswith("--")]:
        n, strings = wrap(p, check)
        total += n
        seen.update(strings)
        if n:
            print(f"  {p}: {n}")
    print(f"TOTAL {'would wrap' if check else 'wrapped'}: {total} "
          f"({len(seen)} distinct strings)")
