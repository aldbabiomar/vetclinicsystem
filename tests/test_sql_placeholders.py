"""
The SQL the app sends, and the one file it splits by hand.

1. Placeholders are psycopg's own '%s' (audit D7). They used to be SQLite's
   '?', rewritten to '%s' by a regex in db.py that was not quote-aware: a '?'
   inside a string literal would have become a parameter and desynced the
   list. The translator is gone, so a '?' written out of habit now reaches
   Postgres as its jsonb operator and fails on the one path that runs it.
   And since psycopg reads every '%' in a query that has parameters, a bare
   '%' there must be written '%%' (a LIKE pattern goes in a parameter).

2. pool.run_script() splits a .sql file on ';' after stripping '--'
   comments. A semicolon inside a string literal, or a $$-quoted function
   body, would be split mid-statement. This runs at install and on every
   in-app update, so a break here is a database that half-exists.
"""
import ast
import re

import source_files

# Every migration file — the schema has no other .sql source.
SQL_FILES = sorted(source_files.MIGRATIONS_DIR.glob("*.sql"))
PY_FILES = [*source_files.all_python(), source_files.ROOT / "setup.py",
            *(p for p in sorted((source_files.ROOT / "tests").glob("*.py")) if p.name != "test_sql_placeholders.py")]

SQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|WHERE|VALUES|RETURNING)\b")
# a '?' where a bound value would go: not glued to a word, a quote, ')' or
# a regex quantifier on the left, nor to a word or '(' on the right
QMARK_PLACEHOLDER = re.compile(r"(?<![A-Za-z0-9_'\"\\)\-*+}\]])\?(?![A-Za-z0-9_(=]|:(?!:))")
REGEX_FUNCS = {"compile", "search", "sub", "subn", "match", "fullmatch", "findall", "finditer", "split"}
# what psycopg reads as a placeholder or an escaped percent; any other % is stray
PSYCOPG_PERCENT = re.compile(r"%%|%\(\w+\)s|%s")


def _sql_literals(path):
    """(line, text) of every string constant in `path` that reads as SQL —
    docstrings and regex patterns aside."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in REGEX_FUNCS \
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "re" and n.args:
            docstrings.update(id(c) for c in ast.walk(n.args[0]))      # a pattern, not SQL
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            first = n.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
            and SQL.search(n.value)]


def _offenders(literals):
    out = []
    for label, line, text in literals:
        if QMARK_PLACEHOLDER.search(text):
            out.append(f"{label}:{line}: a '?' placeholder: {text[:70]!r}")
        if "%s" in text and "%" in PSYCOPG_PERCENT.sub("", text):
            out.append(f"{label}:{line}: a bare '%' in a query with parameters: {text[:70]!r}")
    return out


def _all_literals():
    return [(p.relative_to(source_files.ROOT), line, text) for p in PY_FILES for line, text in _sql_literals(p)]


def test_every_query_uses_native_placeholders():
    """GUARD."""
    literals = _all_literals()
    assert len(literals) >= 1000, f"only {len(literals)} SQL literals found — the scan has lost its subject"
    assert sum("%s" in t for _, _, t in literals) >= 700, "the scan no longer sees the parameterised queries"
    offenders = _offenders(literals)
    assert not offenders, "\n  ".join(["SQL psycopg will not run as written:", *offenders])


def test_control_a_question_mark_and_a_bare_percent_are_found():
    found = _offenders([
        ("x", 1, "SELECT * FROM t WHERE a=?"),
        ("x", 2, "UPDATE t SET a=%s WHERE b LIKE 'x%'"),
        ("x", 3, "INSERT INTO t (a) VALUES (?, %s)"),
    ])
    assert [f.split(":")[1] for f in found] == ["1", "2", "3"], found
    # not SQL placeholders, and not a problem: a regex, a parameterless LIKE,
    # %% and %(name)s, a cast
    assert _offenders([
        ("x", 1, "SELECT (?:x) WHERE"),
        ("x", 2, "SELECT 1 WHERE a LIKE 'x%'"),
        ("x", 3, "SELECT %s WHERE a LIKE 'x%%' AND b=%(b)s AND c=%s::date"),
    ]) == []


def _sql_string_literals(text):
    """Single-quoted SQL literals, with '' escapes handled."""
    return re.findall(r"'((?:[^']|'')*)'", text)


def test_the_schema_has_no_dollar_quoted_bodies():
    """GUARD on run_script()'s split. A $$...$$ function or DO block contains
    semicolons that are not statement terminators."""
    offenders = [p.name for p in SQL_FILES if "$$" in p.read_text(encoding="utf-8")]
    assert not offenders, (
        f"dollar-quoted block(s) in {offenders} — pool.run_script() splits on ';' "
        f"and would cut the body in half")


def test_the_schema_has_no_semicolon_inside_a_string_literal():
    """GUARD on the same split, for the more likely case: a default value or a
    CHECK message containing a semicolon."""
    offenders = []
    for path in SQL_FILES:
        text = "\n".join(line.split("--")[0] for line in path.read_text(encoding="utf-8").splitlines())
        for lit in _sql_string_literals(text):
            if ";" in lit:
                offenders.append(f"{path.name}: '{lit[:50]}'")
    assert not offenders, (
        "a ';' inside a SQL string literal would be treated as a statement "
        "terminator by pool.run_script():\n  " + "\n  ".join(offenders))


def test_the_guards_are_looking_at_real_files():
    """CONTROL. Every assertion above passes vacuously against an empty file
    list — which is exactly how a path typo would present."""
    assert SQL_FILES, "no .sql files found; the glob above is wrong"
    assert any("CREATE TABLE" in p.read_text(encoding="utf-8") for p in SQL_FILES)


def test_the_literal_parser_actually_finds_literals():
    """CONTROL for _sql_string_literals(). If it silently returned nothing,
    the literal-scanning guard above would pass against anything."""
    assert _sql_string_literals("SELECT 'abc', 'd''e' FROM t") == ["abc", "d''e"]
    assert _sql_string_literals("a ';' b") == [";"]
    assert _sql_string_literals("no literals here") == []


# ",".join("?" * n) built "?,?,?" because "?" is one character, so the join
# walked a string of placeholders. With "%s" it walks "%s%s%s" character by
# character into "%,s,%,s" — D7's rewrite made exactly that, at seven sites.
JOINED_STRING_OF_PLACEHOLDERS = re.compile(r"""join\(\s*(["'])%s,?\1\s*\*""")


def test_no_placeholder_list_is_joined_from_a_multiplied_string():
    """GUARD. A list of placeholders is ["%s"] * n."""
    offenders = [f"{p.relative_to(source_files.ROOT)}:{n}"
                 for p in PY_FILES for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if JOINED_STRING_OF_PLACEHOLDERS.search(line)]
    assert not offenders, "\n  ".join(['",".join("%s" * n) joins characters, not placeholders:', *offenders])


def test_control_the_multiplied_string_is_found():
    assert JOINED_STRING_OF_PLACEHOLDERS.search('",".join("%s" * len(ids))')
    assert not JOINED_STRING_OF_PLACEHOLDERS.search('",".join(["%s"] * len(ids))')
