"""
Where the Developer area's buttons sit (the owner's request, 2026-10-01): a
section's buttons are together in one row in its far bottom corner; a single
button is in that corner alone. The two buttons of Support -> Checks keep
their place, and a button that belongs to a table row stays in its row.

The rule is `.dev-area .form-actions` in style.css, so what is held here is
that every button on every Developer page is in such a row. A new page whose
button is left loose fails this.
"""
import re
from html.parser import HTMLParser

import source_files
from conftest import needs_db

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Buttons(HTMLParser):
    """Every button (and link drawn as one) inside .dev-area, with its
    ancestors; and each button row with the box it belongs to."""

    def __init__(self):
        super().__init__()
        self.stack, self.buttons, self.rows = [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        node = {"tag": tag, "classes": (a.get("class") or "").split(), "attrs": a, "text": "", "direct": 0}
        inside = any("dev-area" in n["classes"] for n in self.stack)
        if inside and (tag == "button" or (tag == "a" and "btn" in node["classes"])):
            node["ancestors"] = list(self.stack)
            self.buttons.append(node)
            if self.stack and "form-actions" in self.stack[-1]["classes"]:
                self.stack[-1]["direct"] += 1
        if inside and "form-actions" in node["classes"]:
            # The box a row belongs to: a card, or a panel inside one (an update that was found).
            node["box"] = next((id(n) for n in reversed(self.stack)
                                if "card" in n["classes"] or n["attrs"].get("id") == "updAvailablePanel"), None)
            self.rows.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()["tag"] == tag:
                break

    def handle_data(self, data):
        for n in self.buttons[-1:]:
            if self.stack and self.stack[-1] is n:
                n["text"] += data


def _pages(flask_app):
    return sorted(r.rule for r in flask_app.url_map.iter_rules()
                  if r.endpoint.startswith("developer.") and "GET" in r.methods
                  and r.endpoint != "developer.login" and "<" not in r.rule)


def _where(button):
    names = [n["tag"] + "".join("." + c for c in n["classes"]) for n in button["ancestors"][-3:]]
    return f"{button['text'].strip()!r} in {' > '.join(names)}"


@needs_db
def test_every_developer_button_is_in_its_sections_corner_row(developer, flask_app):
    """GUARD. A button is in a .form-actions row, as its direct child; or in a
    table row's own cell; or in the Checks section, which keeps its place."""
    loose, crowded, seen, pages = [], [], 0, 0
    for path in _pages(flask_app):
        r = developer.get(path)
        if r.status_code != 200 or "text/html" not in r.content_type:
            continue                                   # a JSON route, or a download
        pages += 1
        page = _Buttons()
        page.feed(r.get_data(as_text=True))
        for b in page.buttons:
            seen += 1
            parents = b["ancestors"]
            in_row = bool(parents) and "form-actions" in parents[-1]["classes"]
            in_table = any(n["tag"] == "td" and "cell-actions" in n["classes"] for n in parents)
            keeps = any("data-keeps-its-place" in n["attrs"] for n in parents)
            if not (in_row or in_table or keeps):
                loose.append(f"{path}: {_where(b)}")
        boxes = [row["box"] for row in page.rows]
        crowded += [f"{path}: {boxes.count(box)} button rows in one section" for box in set(boxes)
                    if boxes.count(box) > 1]
    assert pages >= 9 and seen >= 9, f"only {pages} pages and {seen} buttons read -- did the area move?"
    assert not loose, "button(s) outside their section's corner row:\n  " + "\n  ".join(loose)
    assert not crowded, "a section's buttons are in more than one row:\n  " + "\n  ".join(crowded)


@needs_db
def test_the_updates_sections_buttons_share_one_row(developer):
    """Save token and Test connection are two forms' buttons: one row holds
    both, the second naming its form."""
    page = _Buttons()
    page.feed(developer.get("/developer/updates").get_data(as_text=True))
    labels = [b["text"].strip() for b in page.buttons if "form-actions" in b["ancestors"][-1]["classes"]
              and b["ancestors"][-1] is page.rows[0]]
    assert labels[0] == "Save token" and labels[-1] == "Test connection", labels
    test = next(b for b in page.buttons if b["text"].strip() == "Test connection")
    assert test["attrs"].get("form") == "devupd-2-test"
    assert '<form method="post" action="/developer/updates/test" id="devupd-2-test">' in \
        developer.get("/developer/updates").get_data(as_text=True)


@needs_db
def test_control_the_checks_section_keeps_its_buttons_where_they_were(developer):
    """CONTROL for the exception: it is still there, with both its buttons,
    and it is the only one."""
    html = developer.get("/developer/support").get_data(as_text=True)
    page = _Buttons()
    page.feed(html)
    kept = [b["text"].strip() for b in page.buttons
            if any("data-keeps-its-place" in n["attrs"] for n in b["ancestors"])]
    assert kept == ["Run the self-check now", "Test connection"]
    assert html.count("data-keeps-its-place") == 1


def _rule(css, selector):
    found = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert found, f"style.css has no rule for {selector}"
    return found.group(1)


def test_the_corner_row_is_the_far_end():
    """GUARD: the row is pushed to the end (the right in English, the left in
    Arabic). CONTROL: a button row elsewhere in the app is not -- 19 templates
    share .form-actions, and nobody asked for those to move."""
    css = (source_files.STATIC_DIR / "style.css").read_text()
    assert "justify-content: flex-end" in _rule(css, ".dev-area .form-actions")
    assert "justify-content: flex-end" in _rule(css, ".form-actions.form-actions-end")
    assert "text-align: end" in _rule(css, "td.cell-actions")
    assert "justify-content" not in _rule(css, ".form-actions")
    layout = (source_files.TEMPLATES_DIR / "developer_layout.html").read_text()
    assert '<div class="dev-area">{% block dev_main %}{% endblock %}</div>' in layout


def test_the_panels_the_clinic_shares_keep_their_button_in_the_corner_there_too():
    """GUARD. The License and Data Export panels are also the clinic's own
    pages (Settings -> License, Data Export), outside .dev-area: their rows
    carry the corner themselves. The owner found Save license key on the left
    there, 2026-10-02."""
    for name, button in (("_license_panel.html", "Save license key"), ("_data_export_panel.html", "Make an export")):
        html = (source_files.TEMPLATES_DIR / name).read_text()
        row = html[:html.index(button)].rsplit("<div", 1)[1]
        assert 'class="form-actions form-actions-end"' in row, f"{name}: {button} is not in a corner row"
