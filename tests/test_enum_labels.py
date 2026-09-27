# -*- coding: utf-8 -*-
"""`enum_labels.py` duplicates constants on purpose — these tests keep the copies honest.

pybabel extracts by reading source text, so `_(CASE_STATUSES)` on a variable
yields nothing and the stored values have to be spelled out a second time.
Duplication nothing checks is how the first version of that file came to
declare a grooming status of "In Progress" that no code has ever stored,
while the real "Waiting" went untranslated and nothing failed.

Two sources of truth are checked here: the Python constants, and the literal
lists that exist only inside a template's `{% for x in [...] %}`.
"""
import source_files
import ast
import re
from pathlib import Path

import pytest

from vcs import enum_labels
from vcs.web import core
from vcs.domain import analytics, clinical
from vcs.web.blueprints import clinical as clinical_bp, inventory as inventory_bp

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = source_files.TEMPLATES_DIR


def labels(name):
    """enum_labels list as plain strings (they are lazy proxies)."""
    return [str(s) for s in getattr(enum_labels, name)]


@pytest.mark.parametrize("label_name,source", [
    ("CASE_STATUSES", clinical_bp.CASE_STATUSES),
    ("FOLLOWUP_REASONS", clinical_bp.FOLLOWUP_REASONS),
    ("WELLNESS_TYPES", clinical_bp.WELLNESS_TYPES),
    ("GROOMING_SERVICES", clinical.GROOMING_SERVICES),
    ("PAYMENT_METHODS", core.PAYMENT_METHODS),
    ("PRICE_CATEGORIES", inventory_bp.PRICE_CATEGORIES),
    ("INVENTORY_CATEGORIES", inventory_bp.INVENTORY_CATEGORIES),
    ("REVENUE_CATEGORIES", analytics.REVENUE_CATEGORIES),
])
def test_mirrors_the_python_constant(label_name, source):
    assert labels(label_name) == list(source), (
        f"enum_labels.{label_name} has drifted from the constant it mirrors. "
        f"The stored values are what routes validate against — fix the copy in "
        f"enum_labels.py, never the constant."
    )


def template_literal_lists():
    """{loop var: [literals]} for every `{% for x in ['A','B'] %}` in templates."""
    found = {}
    for f in sorted(TEMPLATES.rglob("*.html")):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r"\{%\s*for\s+(\w+)\s+in\s+(\[[^\]]*\])\s*%\}", src):
            try:
                values = ast.literal_eval(m.group(2))
            except (ValueError, SyntaxError):
                continue
            if all(isinstance(v, str) for v in values):
                found.setdefault((f.name, m.group(1)), values)
    return found


@pytest.mark.parametrize("label_name,template,var", [
    ("VISIT_TYPES", "visit_form_edit.html", "t"),
    ("FOLLOWUP_STATUSES", "followups_list.html", "s"),
    ("GROOMING_STATUSES", "grooming_list.html", "s"),
    ("SPECIES", "patient_form_edit.html", "sp"),
    ("REPRO_STATUSES", "patient_form_edit.html", "rs"),
    ("HOUSING", "patient_form_edit.html", "h"),
    ("SEXES", "patient_form_edit.html", "sx"),
])
def test_mirrors_the_template_literal(label_name, template, var):
    lists = template_literal_lists()
    assert (template, var) in lists, (
        f"{template} no longer has a `{{% for {var} in [...] %}}` literal list — "
        f"if the vocabulary moved to Python, point this test at the new constant."
    )
    assert labels(label_name) == lists[(template, var)]


def test_every_translatable_option_has_an_explicit_value():
    """An <option> with no value= submits its TEXT. Translate the text and the
    form posts Arabic into a column the app compares against English.

    Proven end to end once: a visit payment submitted in Arabic stored
    method='نقدًا', which the cash register buckets as "other" rather than
    Cash, so the drawer count reported a surplus that was not real.
    scripts/archive/predecessor-simulation/repro_option_value.py.
    """
    offenders = []
    for f in sorted(TEMPLATES.rglob("*.html")):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r"<option\b([^>]*)>(.*?)</option>", src, re.S):
            attrs, body = m.group(1), m.group(2)
            if re.search(r"\bvalue\s*=", attrs):
                continue
            if "_(" in body or "|tr" in body:
                line = src[:m.start()].count("\n") + 1
                offenders.append(f"{f.name}:{line} {body.strip()[:50]}")
    assert not offenders, (
        "These <option> elements submit their translated text as the form value:\n  "
        + "\n  ".join(offenders)
        + "\nGive each one value=\"<the English constant>\"."
    )


def test_control_an_option_with_an_explicit_value_is_accepted():
    """Pairs with the guard above: it must pass the shape we actually ship,
    not refuse every <option> it sees."""
    sample = '<option value="Cash" selected>{{ _(\'Cash\') }}</option>'
    m = re.fullmatch(r"<option\b([^>]*)>(.*?)</option>", sample, re.S)
    assert re.search(r"\bvalue\s*=", m.group(1)), "the control itself is malformed"


def test_permission_labels_mirror_auth():
    """The roles matrix renders auth.PERMISSIONS through |tr, so every label
    has to be declared — a new permission added to auth.py without a line here
    shows as English on an otherwise Arabic page."""
    from vcs import auth
    assert labels("PERMISSION_LABELS") == [lab for _, lab, _ in auth.PERMISSIONS]
    assert labels("PERMISSION_CATEGORIES") == list(auth.PERMISSION_CATEGORIES)


def test_cash_ledger_events_mirror_the_query():
    """These are built inside the SQL of cash_register.cash_register_ledger(), so the
    source of truth is the query text itself."""
    import re
    src = source_files.module("cash_register").read_text(encoding="utf-8")
    start = src.index("def cash_register_ledger")
    segment = src[start:start + 8000]
    found = set(re.findall(r"'([A-Z][A-Za-z ]+)' AS event_type", segment))
    found |= set(re.findall(r"THEN '([A-Z][A-Za-z ]+)'", segment))
    found |= set(re.findall(r"ELSE '([A-Z][A-Za-z ]+)' END", segment))
    declared = set(labels("CASH_LEDGER_EVENTS"))
    missing = found - declared
    assert not missing, (
        f"cash_register_ledger() produces event types that enum_labels does not "
        f"declare, so they render in English: {sorted(missing)}")
    assert found, "no event types found in the query — this test reads nothing"


def test_weekday_labels_mirror_logic():
    from vcs.domain import analytics
    assert labels("WEEKDAY_LABELS") == list(analytics.WEEKDAY_LABELS)


def test_seeded_roles_mirror_auth():
    """auth.py seeds three roles with a name and a description; both render
    through |tr, so both have to be declared or they stay English."""
    import re
    src = source_files.module("auth").read_text(encoding="utf-8")
    block = src[src.index("    defaults = ["):]
    block = block[:block.index("\n    ]")]
    pairs = re.findall(r'\(\s*"([^"]+)",\s*"((?:[^"\\]|\\.)*)"', block, re.S)
    assert len(pairs) == 3, f"expected 3 seeded roles, found {len(pairs)}"
    names = [n for n, _ in pairs]
    descs = [re.sub(r"\s+", " ", d) for _, d in pairs]
    assert labels("SEEDED_ROLE_NAMES") == names
    assert [re.sub(r"\s+", " ", d) for d in labels("SEEDED_ROLE_DESCRIPTIONS")] == descs


# ---------------------------------------------------------------------------
# A stored constant is shown through |tr
# ---------------------------------------------------------------------------
# Fields that only ever hold one of the app's own English constants. Printed
# raw, they stay English on an Arabic page: scripts/simulation/ar_coverage.py
# found a boarding bill's "Fully Paid", a follow-up's reason and a shrinkage
# reason that way. (`reason` elsewhere is free text a person typed, so it is
# checked only where it is a constant.)
CONSTANT_FIELDS = {
    "status", "payment_status", "case_status", "followup_status", "grooming_status", "visit_type", "sex",
    "method", "payment_method", "refund_method", "category", "ownership_type", "liable_party", "billing_type",
    "event_type", "audit_status", "stock_status", "expiry_status", "followup_method", "wellness_type",
    "followup_reason", "appointment_type", "resource_type",
}
CONSTANT_FIELDS_IN = {"consignment_shrinkage.html": {"reason"}}
# `{{ x.field }}`, and the same with a fallback — `{{ x.field or "—" }}`,
# `{{ x.field if x.field else "—" }}` — which prints the raw value just the same.
OUTPUT = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*(?:\}\}|or\b|if\b)")


def _raw_constants(name, src):
    """`{{ x.field }}` printed as text (not inside a tag's attributes) with no
    filter, where `field` holds a constant."""
    fields = CONSTANT_FIELDS | CONSTANT_FIELDS_IN.get(name, set())
    out = []
    for m in OUTPUT.finditer(src):
        before = src[:m.start()]
        if before.rfind("<") > before.rfind(">"):
            continue                      # inside a tag: an attribute, not text
        if m.group(1).split(".")[-1] in fields:
            out.append(f"{name}:{before.count(chr(10)) + 1} {{{{ {m.group(1)} }}}}")
    return out


def test_a_stored_constant_is_shown_through_tr():
    """A stored constant (a status, a payment method, a reason) printed raw is
    English under the Arabic setting. Found printed raw: a boarding bill's
    status, a follow-up reason, a shrinkage reason, and a distributor
    payment's method behind an `or "—"` fallback."""
    offenders, outputs = [], 0
    for f in sorted(TEMPLATES.glob("*.html")):
        src = f.read_text(encoding="utf-8")
        outputs += len(OUTPUT.findall(src))
        offenders += _raw_constants(f.name, src)
    assert outputs >= 500, f"only {outputs} {{{{ }}}} outputs scanned — did the templates move?"
    assert not offenders, ("these print a stored English constant raw — add |tr:\n  " + "\n  ".join(offenders))


def test_control_the_constant_scan_reads_text_not_attributes():
    sample = ('<span class="badge {{ s.status }}">{{ s.status }}</span> {{ s.status|tr }} '
              '<div class="flash {{ category }}">{{ note.reason }}</div>')
    assert _raw_constants("x.html", sample) == ["x.html:1 {{ s.status }}"]
    assert _raw_constants("consignment_shrinkage.html", "<td>{{ l.reason }}</td>") == [
        "consignment_shrinkage.html:1 {{ l.reason }}"]
    fallback = ('<td>{{ p.method or "—" }}</td><td>{{ p.method if p.method else "—" }}</td>'
                '<td>{{ p.method|tr if p.method else "—" }}</td>')
    assert _raw_constants("x.html", fallback) == ["x.html:1 {{ p.method }}"] * 2
