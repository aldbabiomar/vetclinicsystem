# 0004 — SQL uses psycopg's own `%s`

## Context

The code was written against SQLite and kept its `?` placeholders on
Postgres: a subclass of psycopg's connection rewrote every `?` to `%s` with a
regex before running a query (audit D7). The regex could not tell a
placeholder from a `?` inside a string literal, and every `%` in a query was
already psycopg's business anyway.

## Decision

Every query is written with `%s`, as psycopg expects, and the translator is
gone (restructure R4). Two rules follow from psycopg's own parsing:

- In a query that takes parameters, a literal `%` is written `%%`. A LIKE
  pattern goes in a parameter (`search.like_pattern()`), never in the SQL.
- A list of placeholders is `", ".join(["%s"] * n)`. `",".join("%s" * n)`
  joins the characters of `"%s%s%s"` — it worked for `"?"`, which is one
  character, and the rewrite broke it at seven sites before a test did.

## Consequences

A `?` written out of habit now reaches Postgres as its `jsonb` operator and
fails on the one path that runs it; the test below finds it first.

## Held by

`tests/test_sql_placeholders.py`: no SQL literal uses `?`, none with
parameters carries a bare `%`, and no placeholder list is joined from a
multiplied string — each with a control, and a floor on how much SQL it read.
