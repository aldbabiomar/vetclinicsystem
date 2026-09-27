# -*- coding: utf-8 -*-
"""A modal that is shown must actually be painted, and a warning modal must
wait for a button.

`.modal-overlay { opacity: 0 }` hands opacity to `static/motion.js`, so a
modal opened with a bare `element.style.display = 'flex'` lays out at full
size and is never painted. The self-check modal did exactly that: it was
visible only for the frame before `style.css` applied, which reads as a dialog
that dismisses itself before anyone can finish reading it. It took a
frame-by-frame screen recording to find out what it said.

**This guard is conditional on the stylesheet**, deliberately. The hazard only
exists where CSS drives the opacity. IQ's stylesheet did; this system's (JO's)
does not, and its modals open with a raw display assignment perfectly
correctly. The scan runs either way — it used to skip, which read as a check
that was not there — and the rule starts biting the moment the stylesheet
hands the overlay's opacity to motion.js.
"""
import source_files
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = source_files.STATIC_DIR / "style.css"
TEMPLATES = source_files.TEMPLATES_DIR

RAW_SHOW = re.compile(r"""(\w[\w.()'"\[\]#-]*)\s*\.style\.display\s*=\s*['"]flex['"]""")
# `var el = document.getElementById('selfCheckModal')` — without resolving
# this, a guard that matches on the variable NAME misses `el.style.display`,
# which is precisely the line that shipped the bug.
VAR_BINDING = re.compile(r"""(?:var|let|const)\s+(\w+)\s*=\s*document\.getElementById\(\s*['"]([^'"]+)['"]""")


def _css_drives_overlay_opacity(css=None):
    css = CSS.read_text(encoding="utf-8") if css is None else css
    src = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in re.finditer(r"\.modal-overlay\s*\{([^}]*)\}", src):
        body = m.group(1)
        if re.search(r"opacity:\s*0\b", body):
            return True
    return False


def _modal_ids_in(template_src):
    return set(re.findall(r'id="([^"]+)"[^>]*class="[^"]*modal-overlay', template_src)) | \
           set(re.findall(r'class="[^"]*modal-overlay[^"]*"[^>]*id="([^"]+)"', template_src))


def _raw_shows(name, src):
    """Each place `src` shows one of its modal overlays by setting display alone."""
    modal_ids = _modal_ids_in(src)
    bindings = {v: eid for v, eid in VAR_BINDING.findall(src)}
    out = []
    for m in RAW_SHOW.finditer(src):
        target = m.group(1)
        resolved = bindings.get(target, target)
        if (any(mid in resolved for mid in modal_ids)
                or any(mid in target for mid in modal_ids)
                or "modal" in resolved.lower()):
            out.append(f"{name}:{src[:m.start()].count(chr(10)) + 1}: {m.group(0)}")
    return out


def test_no_modal_is_shown_by_a_bare_display_assignment():
    modals, offenders = 0, []
    for f in sorted(TEMPLATES.rglob("*.html")):
        src = f.read_text(encoding="utf-8")
        if _modal_ids_in(src):
            modals += len(_modal_ids_in(src))
            offenders += _raw_shows(f.name, src)
    assert modals >= 5, f"only {modals} modal overlays found — did the templates move?"
    if _css_drives_overlay_opacity():
        assert not offenders, (
            "These show a modal overlay by setting display alone. The stylesheet "
            "keeps .modal-overlay at opacity 0 and motion.js animates it, so the "
            "modal lays out invisible:\n  " + "\n  ".join(offenders)
            + "\nUse window.VZSpring.present(el, true, {}).")


def test_control_the_rule_bites_when_the_stylesheet_drives_opacity():
    assert _css_drives_overlay_opacity(".modal-overlay { display: none; opacity: 0; }")
    assert not _css_drives_overlay_opacity(".modal-overlay { display: none; }")
    assert not _css_drives_overlay_opacity("/* .modal-overlay { opacity: 0 } */ .modal-overlay { }")
    sample = ('<div id="warnModal" class="modal-overlay"></div><script>'
              "var el = document.getElementById('warnModal'); el.style.display = 'flex';</script>")
    assert _raw_shows("x.html", sample) == ["x.html:1: el.style.display = 'flex'"]


def test_the_health_warning_modal_requires_a_button():
    """It reports that the install has failed its health check three days
    running. A stray backdrop click must not dismiss something unread."""
    src = (TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
    m = re.search(r'<div id="selfCheckModal"[^>]*>', src, re.S)
    assert m, "the self-check modal is gone — if it moved, point this test at it"
    assert "data-no-backdrop-close" in m.group(0), (
        "the health-warning modal can be dismissed by clicking the backdrop")


def test_the_backdrop_handler_honours_the_opt_out():
    """The attribute means nothing unless ui.js checks it."""
    ui = (source_files.STATIC_DIR / "ui.js").read_text(encoding="utf-8")
    assert "data-no-backdrop-close" in ui, (
        "ui.js does not check data-no-backdrop-close, so the attribute on the "
        "modal is decoration")


def test_control_the_scanner_reads_templates_and_css():
    assert _modal_ids_in((TEMPLATES / "dashboard.html").read_text(encoding="utf-8")), \
        "no modal overlay found in dashboard.html — the scanner is not matching"
    assert ".modal-overlay" in CSS.read_text(encoding="utf-8"), "no overlay CSS found"
