"""
Finding records from what staff type: LIKE patterns, microchip numbers
without their separators, and the patient search.
"""
import re

from vcs.domain import codes


# ---------------------------------------------------------------------------
# Owners / Patients
# ---------------------------------------------------------------------------
# The one definition of what counts as noise inside a microchip number: spaces,
# hyphens (including the en/em dashes a paste can carry) and dots. The clinical
# blueprint's normalize_microchip() strips exactly this before storing, and
# search_patients() strips exactly this before matching -- the two must agree
# or a chip typed the way it is printed would not find the record it is on.
_MICROCHIP_SEPARATORS = re.compile(r"[\s\-\u2013\u2014.]")


def like_pattern(term):
    """A substring pattern for LIKE/ILIKE, with the wildcards in `term`
    escaped so they match themselves.

    Every search box in this app built f"%{term}%" and passed it straight in.
    The query is parameterised, so this was never an injection route -- but %
    and _ are wildcards inside the pattern regardless of how it got there, so
    someone searching for "50%" matched every row and an item called "A_B"
    also matched "AxB". Wrong results, quietly.

    Postgres treats backslash as LIKE's escape character by default (verified
    against the live database: 'axb' ILIKE '%a\\_b%' is false), so no ESCAPE
    clause is needed at the call sites -- escaping the pattern is enough.
    Backslash is escaped first, or it would double-escape the two below it.
    """
    escaped = (term or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def strip_microchip_separators(raw):
    if raw is None:
        return ""
    return _MICROCHIP_SEPARATORS.sub("", str(raw)).upper()


def search_patients(db, term):
    # Microchip numbers are stored normalized, so the term has to be
    # normalized too before it can match one: staff type a chip the way it is
    # grouped on the scanner ("985 141 000 123456") and that string appears
    # nowhere in the database. Every other field is matched on the term as
    # typed, which is why this is a second parameter rather than a change to
    # the first.
    chip_term = like_pattern(strip_microchip_separators(term))
    id_term = codes.parse_id(term, "PT")
    term = like_pattern(term)
    return db.execute(
        "SELECT p.*, o.name as owner_name, o.phone as owner_phone FROM patients p "
        "JOIN owners o ON o.id = p.owner_id "
        "WHERE p.animal_name ILIKE %s OR p.id = %s OR p.microchip ILIKE %s "
        "OR o.name ILIKE %s OR o.phone ILIKE %s "
        "ORDER BY p.animal_name LIMIT 25",
        # A typed code ("PT-00012") or number finds that patient exactly.
        (term, id_term, chip_term, term, term),
    ).fetchall()
