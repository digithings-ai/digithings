#!/usr/bin/env python3
"""Derive D1 (SQLite) RAISE(ABORT) append-only triggers from the Postgres migrations.

DIG-2894 (supabase exit 6). Every ``reject_*_mutation`` guard defined in
``digiquant/supabase/migrations/*.sql`` becomes a SQLite ``BEFORE UPDATE`` /
``BEFORE DELETE`` trigger whose body is ``SELECT RAISE(ABORT, <message>)``.

Coverage is 1:1 by construction: the mapping is read off the migrations, so a
table guarded in Postgres is guarded in the D1 output and one that is not, is not.

Semantics carried across from Postgres
-------------------------------------
* Postgres guards read ``BEFORE UPDATE OR DELETE ON <table> FOR EACH ROW``.
  That is **append-only**: INSERT stays legal, corrections must INSERT a
  superseding row. The D1 triggers mirror UPDATE/DELETE only.
* The abort message is the one from the guard's own ``RAISE EXCEPTION``, so the
  D1 runtime reports the same operator-facing text as Postgres.
* Postgres also installs ``BEFORE TRUNCATE ... FOR EACH STATEMENT`` triggers.
  SQLite has no TRUNCATE and no statement-level trigger, so those are emitted as
  an explicit worker-side obligation list instead of being silently dropped.

Usage::

    python3 scripts/gen_d1_reject_guards.py            # rewrite the artefact
    python3 scripts/gen_d1_reject_guards.py --check    # non-zero if stale
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
OUTPUT_PATH = REPO_ROOT / "digiquant" / "src" / "digiquant" / "d1_reject_guards.sql"

GUARD_FN_DEF_RE = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+(?:public\.)?"
    r"(?P<name>reject_[a-z0-9_]*_mutation)\s*\(\s*\)\s*RETURNS\s+trigger",
    re.IGNORECASE,
)
GUARD_MSG_RE = re.compile(r"RAISE\s+EXCEPTION\s+'(?P<msg>[^']*)'", re.IGNORECASE)

# Postgres combines operations: "BEFORE UPDATE OR DELETE ON t".
OP = r"(?:INSERT|UPDATE|DELETE|TRUNCATE)"
CREATE_TRIGGER_RE = re.compile(
    r"CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<trig>\"?[a-z0-9_]+\"?)"
    r"\s+(?P<timing>BEFORE|AFTER)\s+(?P<ops>" + OP + r"(?:\s+OR\s+" + OP + r")*)"
    r"\s+ON\s+(?:public\.)?(?P<table>\"?[a-z0-9_]+\"?)"
    # [^;] is load-bearing: a bare .*? lets a match run past a statement
    # terminator and swallow the NEXT trigger, silently attributing this
    # trigger's function to the wrong table.
    r"(?P<mid>[^;]*?)"
    r"(?:EXECUTE\s+(?:PROCEDURE|FUNCTION)\s+(?:public\.)?"
    r"(?P<fn>reject_[a-z0-9_]*_mutation)\s*\(\s*\)\s*;)",
    re.IGNORECASE | re.DOTALL,
)

# SQLite expresses the D1-safety subset of the Postgres operation set.
SQLITE_PORTABLE_OPS = ("UPDATE", "DELETE")
SQLITE_UNSUPPORTED_OPS = ("INSERT", "TRUNCATE")


def _unquote(name: str) -> str:
    return name.strip().strip('"')


def _sqlite_quote(text: str) -> str:
    return text.replace("'", "''")


# A guard function body ends at the first `$$` terminator (or, defensively, at the
# next function definition).
_FN_BODY_END_RE = re.compile(r"\$\$;?|\bLANGUAGE\b", re.IGNORECASE)
_NEXT_FN_RE = re.compile(r"CREATE\s+OR\s+REPLACE\s+FUNCTION\b", re.IGNORECASE)
# `IF TG_OP = 'TRUNCATE' THEN ... END IF;` -- the statement-level branch.
_TRUNCATE_BRANCH_RE = re.compile(
    r"IF\s+TG_OP\s*=\s*'TRUNCATE'.*?END\s+IF\s*;", re.IGNORECASE | re.DOTALL
)


def _function_body(sql: str, start: int) -> str:
    """Return the SQL of the function whose header ends at ``start``."""
    end = _FN_BODY_END_RE.search(sql, start)
    nxt = _NEXT_FN_RE.search(sql, start)
    if nxt is not None and (end is None or nxt.start() < end.start()):
        end = nxt
    if end is None:
        return sql[start:]
    return sql[start : end.start()]


def _row_path_message(body: str) -> str:
    """The abort message the function raises for a row-level UPDATE/DELETE.

    The TRUNCATE branch is stripped first: its message is statement-specific and
    would be reported verbatim on row triggers, which is wrong.
    """
    truncate_spans = [m.span() for m in _TRUNCATE_BRANCH_RE.finditer(body)]
    for m in GUARD_MSG_RE.finditer(body):
        inside_truncate = any(
            start <= m.start() < end for start, end in truncate_spans
        )
        if not inside_truncate:
            return m.group("msg").strip()
    return ""


def parse_migrations(migrations_dir: pathlib.Path = MIGRATIONS_DIR):
    """Return ``(guard_functions, triggers, unsupported)`` read off the migrations."""
    guard_functions: dict[str, dict] = {}
    triggers: list[dict] = []
    unsupported: list[tuple[str, str, str, str]] = []

    layered = sorted((migrations_dir / "engine").glob("*.sql")) + sorted(
        (migrations_dir / "prod").glob("*.sql")
    )
    # No stray top-level files: the chain lives in engine/ and prod/ (D-Q6′).
    strays = sorted(migrations_dir.glob("*.sql"))
    assert not strays, f"top-level migration(s) outside engine/ and prod/: {strays}"
    for path in layered:
        # Strip line comments so a commented-out definition cannot inflate a count.
        sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))

        for m in GUARD_FN_DEF_RE.finditer(sql):
            name = m.group("name").lower()
            # Bound the search to THIS function's own body. Searching the rest of
            # the file returns a later function's message, or this function's
            # TRUNCATE-branch message on a row trigger.
            body = _function_body(sql, m.end())
            guard_functions[name] = {
                "message": _row_path_message(body),
                "migration": path.name,
            }

        for m in CREATE_TRIGGER_RE.finditer(sql):
            fn = m.group("fn").lower()
            table = _unquote(m.group("table")).lower()
            ops = [o.upper() for o in re.split(r"\s+OR\s+", m.group("ops"), flags=re.I)]
            level = "statement" if re.search(r"FOR\s+EACH\s+STATEMENT", m.group("mid"), re.I) else "row"
            triggers.append({
                "trigger": _unquote(m.group("trig")),
                "table": table,
                "ops": ops,
                "level": level,
                "fn": fn,
                "migration": path.name,
            })
            if level == "statement" or any(o in SQLITE_UNSUPPORTED_OPS for o in ops):
                for op in ops:
                    if op in SQLITE_UNSUPPORTED_OPS or level == "statement":
                        unsupported.append((op, table, fn, path.name))

    return guard_functions, triggers, sorted(set(unsupported))


def render_sql(guard_functions, triggers, unsupported) -> str:
    portable = [t for t in triggers if t["level"] == "row" and set(t["ops"]) & set(SQLITE_PORTABLE_OPS)]
    tables: dict[str, set[str]] = {}
    for t in portable:
        tables.setdefault(t["table"], set()).update(o for o in t["ops"] if o in SQLITE_PORTABLE_OPS)

    out: list[str] = []
    out.append("-- Append-only guards for D1 (SQLite).")
    out.append("--")
    out.append("-- GENERATED FILE - DO NOT EDIT BY HAND.")
    out.append("-- Source of truth: scripts/gen_d1_reject_guards.py, which reads")
    out.append("-- digiquant/supabase/migrations/*.sql. Run it after touching a migration.")
    out.append("--")
    out.append("-- Ticket: DIG-2894 (supabase exit 6). Reviewer: DIG-2892 (exit 4).")
    out.append("--")
    out.append("-- The Postgres guards are BEFORE UPDATE OR DELETE ... FOR EACH ROW, i.e.")
    out.append("-- append-only: INSERT stays legal and corrections must INSERT a superseding")
    out.append("-- row. Each guard function's own RAISE EXCEPTION text is reused verbatim so")
    out.append("-- the D1 runtime reports the same operator-facing message.")
    out.append("")
    out.append(f"-- Guard functions ported: {len(guard_functions)}")
    out.append(f"-- Guarded tables:         {len(tables)}")
    out.append(f"-- D1 row triggers:       {sum(len(v) for v in tables.values())}")
    out.append(f"-- Worker-side obligations (no SQLite equivalent): {len(unsupported)}")
    out.append("")
    out.append("BEGIN TRANSACTION;")
    out.append("")

    for table in sorted(tables):
        guard_fns = sorted({t["fn"] for t in portable if t["table"] == table})
        msg = guard_functions.get(guard_fns[0], {}).get("message") or (
            f"{table} is append-only; corrections must INSERT a superseding row"
        )
        out.append(f"-- {table}: append-only via {', '.join(guard_fns)} in Postgres.")
        for op in sorted(tables[table]):
            quoted = _sqlite_quote(msg)
            out.append(
                f'CREATE TRIGGER IF NOT EXISTS "{table}_append_only_{op.lower()}"\n'
                f"BEFORE {op} ON \"{table}\"\n"
                f"BEGIN\n"
                f"  SELECT RAISE(ABORT, '{quoted}');\n"
                f"END;"
            )
        out.append("")

    out.append("COMMIT;")
    out.append("")

    if unsupported:
        out.append("-- ----------------------------------------------------------------------")
        out.append("-- Worker-side obligations. NOT enforced by this file: SQLite has no")
        out.append("-- TRUNCATE and no statement-level trigger. The Worker data API must")
        out.append("-- refuse these operations in application code. See DIG-2894 / DIG-2892.")
        out.append("-- ----------------------------------------------------------------------")
        for op, table, fn, migration in unsupported:
            out.append(f"--   {op:<9} ON {table:<42} (Postgres {fn}, {migration})")
        out.append("")

    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate D1 append-only guards.")
    ap.add_argument("--check", action="store_true", help="fail if the artefact is stale")
    args = ap.parse_args(argv)

    guard_functions, triggers, unsupported = parse_migrations()

    # Guard against a silently-empty artefact: a parser regression must fail loudly.
    if len(guard_functions) != 19:
        print(f"ERROR: parsed {len(guard_functions)} guard functions, expected 19; migrations moved?")
        return 2
    if not triggers:
        print("ERROR: no guard triggers parsed; refusing to emit an empty artefact")
        return 2

    sql = render_sql(guard_functions, triggers, unsupported)

    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if current != sql:
            print(f"STALE: {OUTPUT_PATH.relative_to(REPO_ROOT)} differs from the migrations")
            return 1
        print(f"OK: artefact is in sync ({len(guard_functions)} guards)")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(sql, encoding="utf-8")
    n_tables = len({t["table"] for t in triggers if t["level"] == "row"})
    print(
        f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}: {len(guard_functions)} guard functions, "
        f"{n_tables} tables, {len(triggers)} PG triggers parsed, {len(unsupported)} worker-side obligations"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
