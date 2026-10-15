"""Split a ``pg_dump --column-inserts`` dump into per-table INSERT batches.

Only ``INSERT INTO <table> (...) VALUES (...);`` statements are migration
payload. Everything else in the dump (SET, CREATE, COPY, SELECT pg_catalog
calls, comments) is ignored by the splitter and reported as skipped -- DDL
comes from the D1 schema ports (tickets 2/3), never from the dump, so a dump
can never create, alter, or drop anything through this path.

Batching: consecutive INSERTs for the same table are grouped so one
transaction carries at most ``batch_size`` statements. Tables never mix
inside a batch, which keeps per-table row counts exact and makes a failed
batch attributable to exactly one table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: ``INSERT INTO public.positions (a, b) VALUES (...);`` -- schema prefix is
#: optional, quoted identifiers allowed. Matched case-insensitively because
#: pg_dump emits uppercase keywords.
_INSERT_RE = re.compile(
    r"""^INSERT\s+INTO\s+
        (?P<table>(?:"[^"]+"|[A-Za-z_][\w$]*)(?:\.(?:"[^"]+"|[A-Za-z_][\w$]*))?)
        \s*\(.*\)\s*VALUES\s*\(.*\)\s*;\s*$""",
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

_URL_LIKE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


@dataclass(frozen=True)
class SplitResult:
    """Outcome of splitting one dump file."""

    #: table name -> ordered INSERT statements for that table.
    tables: dict[str, list[str]]
    #: non-INSERT, non-blank lines seen (DDL, SET, comments, ...). Counted so
    #: the operator can confirm the dump contained what was expected.
    skipped_lines: int


def _strip_schema(qualified: str) -> str:
    """``public.positions`` -> ``positions``; strips double quotes."""
    name = qualified.split(".")[-1]
    return name.strip('"').strip()


#: The ``INSERT INTO [schema.]table`` prefix, for retargeting dump
#: statements at unqualified local/D1 table names.
_INTO_RE = re.compile(
    r"""^(\s*INSERT\s+INTO\s+)
        (?P<target>(?:"[^"]+"|[A-Za-z_][\w$]*)(?:\.(?:"[^"]+"|[A-Za-z_][\w$]*))?)""",
    re.IGNORECASE | re.VERBOSE,
)


def local_insert(statement: str) -> str:
    """Rewrite a dump INSERT at its unqualified table name.

    Dumps qualify tables (``public.positions``); the local/D1 DDL defines
    bare names (``positions``). Rewriting keeps the statement verbatim
    otherwise -- values, quoting, and escaping are untouched.
    """
    match = _INTO_RE.match(statement)
    if match is None:
        raise ValueError(f"not an INSERT statement: {statement[:80]!r}")
    table = _strip_schema(match.group("target"))
    return f'{match.group(1)}"{table}"' + statement[match.end("target") :]


def assert_local_dump_file(dump: str | Path) -> Path:
    """Refuse anything that is not a plain local dump file.

    Raises ``ValueError`` for URLs / remote-looking inputs and
    ``FileNotFoundError`` for missing files. This is the gate that keeps
    ticket-0 discipline: migration input is always Chris's snapshot file.
    """
    text = str(dump)
    if _URL_LIKE.match(text) or text.startswith(("\\\\", "//")):
        raise ValueError(f"refusing non-local dump input: {text!r}")
    path = Path(text)
    if not path.is_file():
        raise FileNotFoundError(f"dump file not found: {path}")
    return path


def split_dump_file(dump: str | Path) -> SplitResult:
    """Split a pg_dump ``--column-inserts`` file per table."""
    path = assert_local_dump_file(dump)
    return split_dump_text(path.read_text(encoding="utf-8"))


def split_dump_text(dump_text: str) -> SplitResult:
    """Split dump text per table (same rules as :func:`split_dump_file`)."""
    tables: dict[str, list[str]] = {}
    skipped = 0
    buffer: list[str] = []

    def flush_buffer() -> None:
        nonlocal skipped
        if buffer:
            # A multi-line statement that never completed as an INSERT is
            # not payload -- count it as skipped, never guess.
            skipped += len(buffer)
            buffer.clear()

    for line in dump_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(stripped)
        joined = " ".join(buffer)
        if not joined.rstrip().endswith(";"):
            continue  # statement continues on the next line
        match = _INSERT_RE.match(joined)
        if match is None:
            skipped += len(buffer)
        else:
            tables.setdefault(_strip_schema(match.group("table")), []).append(joined)
        buffer.clear()
    flush_buffer()
    return SplitResult(tables=tables, skipped_lines=skipped)


@dataclass(frozen=True)
class TableBatch:
    """One transaction's worth of INSERTs for a single table."""

    table: str
    statements: list[str]


def batch_inserts(
    tables: dict[str, list[str]],
    batch_size: int = 500,
) -> list[TableBatch]:
    """Group per-table INSERTs into batches of at most ``batch_size``."""
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    batches: list[TableBatch] = []
    for table in sorted(tables):
        statements = tables[table]
        for start in range(0, len(statements), batch_size):
            batches.append(
                TableBatch(table=table, statements=statements[start : start + batch_size])
            )
    return batches
