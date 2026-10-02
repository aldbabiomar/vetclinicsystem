"""
A filled button is the palette's main colour (the owner's decision,
2026-10-02). There used to be a red one (`.btn.danger`: Restore Now, Delete,
Disable, the x on a bill line, a dialog's Confirm) and a green one (`.btn.ok`:
the WhatsApp links), which stood out of every palette but the one they were
drawn for. What marks a destructive action now is its confirmation, not its
colour.

Static: the rule is about what the source may say.
"""
import re

import source_files

CSS = source_files.STATIC_DIR / "style.css"
# What a button's background may be: the palette's main colour and its hover,
# the outlined button's paper and its hover, or nothing.
ALLOWED = {"var(--primary)", "var(--primary-dark)", "var(--paper)", "var(--muted-tint)", "none", "transparent"}
COLOURED = re.compile(r"(?<![\w-])(danger|ok|warn|warning|success|error)(?![\w-])")
BTN_CLASSES = re.compile(r"""class=\\?["']([^"']*(?<![\w-])btn(?![\w-])[^"']*)["']""")


def _button_rules():
    """(selector, declarations) of every rule in style.css that styles a .btn."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
            if re.search(r"\.btn(?![\w-])", sel)]


def test_no_button_rule_paints_outside_the_main_colour():
    """GUARD."""
    rules = _button_rules()
    assert len(rules) >= 8, f"only {len(rules)} .btn rules read -- did the stylesheet move?"
    wrong = []
    for selector, body in rules:
        for value in re.findall(r"background(?:-color)?\s*:\s*([^;]+)", body):
            if value.strip() not in ALLOWED:
                wrong.append(f"{selector} {{ background: {value.strip()} }}")
    assert not wrong, "a button painted outside the palette's main colour:\n  " + "\n  ".join(wrong)


def test_control_the_filled_button_is_the_main_colour():
    """CONTROL: the scan reads the real rules, and the main colour is there."""
    rules = dict(_button_rules())
    assert "background: var(--primary)" in rules[".btn"]
    assert "background: var(--primary-dark)" in rules[".btn:hover"]


def test_no_button_is_given_a_colour_class():
    """GUARD. In a template or in a script that builds one: `btn danger` and
    `btn ok` no longer mean anything, and must not come back meaning red."""
    files = sorted(source_files.TEMPLATES_DIR.glob("*.html")) + sorted(source_files.STATIC_DIR.glob("*.js"))
    seen, wrong = 0, []
    for path in files:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for classes in BTN_CLASSES.findall(line):
                seen += 1
                plain = re.sub(r"\{\{.*?\}\}", lambda m: " ".join(re.findall(r"'([\w -]*)'", m.group(0))), classes)
                if COLOURED.search(plain):
                    wrong.append(f"{path.name}:{i}: class=\"{classes}\"")
    assert seen >= 250, f"only {seen} buttons read -- did the templates move?"
    assert not wrong, "button(s) with a colour class:\n  " + "\n  ".join(wrong)
