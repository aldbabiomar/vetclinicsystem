# -*- coding: utf-8 -*-
"""Translate user-facing prose inside inline <script> blocks.

These are the messages a user only sees after doing something: the empty state
under a search box, a confirm dialog's buttons, "Could not reach the server."
Every one of them stayed English on a fully Arabic page, and the template pass
could not see them because they live inside a string literal, not a text node.

`{{ _('...') }}` works here — Jinja renders before the browser parses — but the
result has to be a JS *literal*, so it goes through `|tojson`, which adds the
quotes and escapes the Arabic correctly. Wrapping in bare quotes instead would
break on any apostrophe in a translation.

Only whole prose literals are rewritten. Two kinds are deliberately skipped and
handled per site: CSS class/style strings, and FRAGMENTS that JS concatenates
into a sentence ('1 staff member' + ' currently assigned to ') — those have the
same problem as English plural suffixes in a template and need to become whole
sentences, not translated word order.
"""
import json
import re
import sys

# strings that are markup, style or code rather than prose
SKIP_EXACT = {
    "small muted", "btn small danger",
    "display:flex; align-items:center; gap:10px; padding:8px 4px; "
    "border-bottom:1px solid var(--line);",
}
# fragments concatenated at runtime — per-site work, see the module docstring
SKIP_FRAGMENT = {
    "1 staff member", " staff members", " currently assigned to ",
    " has no sale price set in the Price List.", " failed to start.",
    "Account locked — try again in ", "Manage Barcode — ", "VetClinicSystem IQ v",
    "VetClinicSystem JO v",
    # apostrophe-split fragments of comments, not strings at all
    "d stay Vetzone", "s pos_checkout()), so what", "are you sure",
}


def should_wrap(t):
    if t in SKIP_EXACT or t in SKIP_FRAGMENT:
        return False
    if re.match(r"^[.#\[]", t.strip()) or re.search(r"\[[\w-]+[=\]]", t):
        return False
    if ":" in t and ";" in t:            # inline style
        return False
    return bool(re.search(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}", t))


SCRIPT = re.compile(r"(<script\b[^>]*>)(.*?)(</script>)", re.S)
LITERAL = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"")


def rewrite_body(body, seen):
    def repl(m):
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        if raw is None:
            return m.group(0)
        text = raw.replace("\\'", "'").replace('\\"', '"')
        if not should_wrap(text):
            return m.group(0)
        seen.append(text)
        esc = text.replace("\\", "\\\\").replace("'", "\\'")
        return "{{ _('%s')|tojson }}" % esc
    return LITERAL.sub(repl, body)


def main(app_dir):
    import glob
    total = 0
    for f in sorted(glob.glob(f"{app_dir}/templates/**/*.html", recursive=True)):
        src = open(f, encoding="utf-8").read()
        seen = []

        def repl(m):
            return m.group(1) + rewrite_body(m.group(2), seen) + m.group(3)

        new = SCRIPT.sub(repl, src)
        if seen:
            open(f, "w", encoding="utf-8").write(new)
            print(f"  {f.split('/')[-1]:28s} {len(seen)}")
            total += len(seen)
    print(f"{app_dir.split('/')[-1]}: {total} JS strings wrapped")


if __name__ == "__main__":
    for a in sys.argv[1:]:
        main(a)
