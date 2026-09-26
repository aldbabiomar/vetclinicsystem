"""
Numbers and money as a person reads them: 12, not 12.000; Arabic-Indic
digits under Arabic; the money setting's format.
"""
from decimal import Decimal

from vcs import money


def format_quantity(v):
    """A count, measurement or percentage on its way into display text:
    Decimal("12.000") -> "12", Decimal("2.500") -> "2.5", 10 -> "10".

    Every such column is NUMERIC, so a whole number arrives with the column's
    decimal tail ("× 1.000" on a receipt, "4.500 kg"). f"{x:g}" does NOT fix
    that for a Decimal — it keeps the zeros. Never scientific notation.

    Digits only; Arabic-Indic conversion stays with core.display_number() and
    the |qty filter, the boundaries that decide that. Not for a value that
    will be put back into an <input> in Arabic — that one stays Western.
    """
    if v is None or v == "":
        return ""
    d = v if isinstance(v, Decimal) else Decimal(str(v))
    if not d.is_finite():
        return str(d)
    d = d.normalize()
    return "0" if d == 0 else format(d, "f")


_ARABIC_INDIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def to_arabic_indic_digits(s):
    """Substitute Eastern Arabic-Indic digits into an ALREADY-FORMATTED string.

    Display only, and the boundary is not decoration -- see
    ARABIC_LOCALIZATION_PLAN.md §7.1:

      - never on a value that will be parsed back (parse_money, a submitted
        form value). Every calculation happens in Western digits and this runs
        at the very last step, on its way into a template.
      - never on an editable <input>'s value. A number input's underlying
        value is a Western-digit string in every browser regardless of locale,
        so converting what is displayed risks a mismatch with what the
        keyboard types and what gets submitted.
      - never on an ID or reference code (V0001, INV301). Those are
        identifiers, matched elsewhere as literal strings, not quantities.
      - never inside pdf_export.py. PDFs stay English with Western digits,
        permanently (§0). If this helper is ever tempting to call from that
        module, something has been wired wrong.
    """
    if s is None:
        return s
    return str(s).translate(_ARABIC_INDIC_DIGITS)


def display_qty(v):
    """format_quantity() for a message: Arabic-Indic digits under Arabic."""
    text = format_quantity(v)
    try:
        from flask_babel import get_locale
        if str(get_locale()) == "ar":
            return to_arabic_indic_digits(text)
    except RuntimeError:
        pass
    return text


def format_percent(v):
    """A percentage on its way into display text: 10.00 -> "10", 12.5 -> "12.5"
    (a clinic may legitimately set 12.5%)."""
    return format_quantity(v)


def fmt_money(amount):
    """Display form of an amount under the clinic's money setting — whole
    dinars under IQ, three decimals under JO. See money.fmt()."""
    return money.fmt(amount)
