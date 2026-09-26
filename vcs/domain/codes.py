"""
Record codes: the numeric id staff see as V-00123, and reading one back
from what they type.
"""
import re


_MAX_ID = 2_147_483_647  # an INTEGER column's ceiling


_ID_RE = re.compile(r"^\s*(?:([A-Za-z]{1,4})\s*-?\s*)?0*(\d{1,10})\s*$")


def parse_id(raw, prefix=None):
    """A record ID from a form field or query string -> int, or None.

    Accepts the number itself ("123", "00123") and, when `prefix` is given,
    the display code staff read and type ("V-00123", "v123"; codes.code()).
    Anything else is None — never an exception and never a value that
    reaches an INTEGER column as text, where Postgres would refuse it with a
    500. A code with the WRONG prefix (a patient code typed into a visit
    field) is None too, so it cannot silently name a different record."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw if 0 < raw <= _MAX_ID else None
    m = _ID_RE.match(str(raw))
    if not m:
        return None
    if m.group(1) and (prefix is None or m.group(1).upper() != prefix.upper()):
        return None
    val = int(m.group(2))
    return val if 0 < val <= _MAX_ID else None


# The code staff read and type for a record: its numeric id with a prefix
# (V-00123). One definition, used by the |code filter, messages and PDFs;
# core.parse_id() reads it back. Western digits always — a code is an
# identifier, not a quantity (ARABIC_LOCALIZATION_PLAN.md §7.1).
CODE_PREFIX = {"owners": "OW", "patients": "PT", "visits": "V", "inventory_list": "INV",
               "price_list": "PL", "distributors": "D", "distributor_bills": "DB"}


def code(prefix, record_id):
    """code("V", 123) -> "V-00123"; blank for no id."""
    if record_id is None or record_id == "":
        return ""
    return f"{prefix}-{int(record_id):05d}"
