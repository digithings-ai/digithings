"""Contract tests for migration 070, explicit fee and slippage on the fill row.

Companion to ``test_migration_069.py`` and deliberately in its style: the migration
is read as text, because these are claims about the DDL the repo will apply, and the
only place to check them before it runs is the file itself.

The invariant this file exists for is **re-runnability**. 070 adds its columns with
``ADD COLUMN IF NOT EXISTS`` but ``ADD CONSTRAINT`` has no such form, so a bare
``ALTER TABLE ... ADD CONSTRAINT`` makes the file idempotent in its first statement
and fatal (SQLSTATE 42710, ``duplicate_object``) in its third. That is worse than a
plainly non-idempotent file: it reads as safe to re-apply right up to where it isn't.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "070_olympus_paper_execution_costs.sql"

TABLE = "public.portfolio_ledger_paper_executions"
COLUMNS = ("fee", "slippage")
SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


def _check_body(sql: str, column: str) -> str:
    """The CHECK expression guarding ``column``, with whitespace collapsed."""
    match = re.search(
        rf"ADD\s+CONSTRAINT\s+chk_portfolio_ledger_paper_executions_{column}\s+"
        rf"CHECK\s*\((?P<body>.*?)\)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing CHECK constraint for {column}"
    return " ".join(match.group("body").split())


def test_migration_is_the_only_070() -> None:
    assert sorted(MIGRATIONS_DIR.glob("070_*.sql")) == [MIGRATION_PATH]


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    """No self-wrapping: the runner supplies the transaction, as in every migration here.

    A ``DO $$ ... END $$`` block is not a transaction and does not violate this — it opens
    a subtransaction inside whatever the runner opened, which is exactly why its exception
    handler can swallow one failed statement without poisoning the rest of the file.
    """
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


@pytest.mark.parametrize("column", COLUMNS)
def test_columns_are_added_idempotently(sql: str, column: str) -> None:
    assert re.search(rf"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+{column}\s+numeric", sql, re.I)


def test_every_add_constraint_is_rerunnable(sql: str) -> None:
    """Each ``ADD CONSTRAINT`` sits inside a ``duplicate_object``-swallowing block.

    ``ADD CONSTRAINT`` has no ``IF NOT EXISTS``, so an unwrapped one aborts the second
    application of this file with 42710 — after ``ADD COLUMN IF NOT EXISTS`` has already
    signalled that re-applying is fine. The blocks are counted rather than merely detected
    so that adding a third constraint later without a wrapper fails here instead of in
    production.
    """
    blocks = re.findall(
        r"DO\s*\$\$\s*BEGIN(?P<body>.*?)EXCEPTION\s+WHEN\s+duplicate_object\s+THEN\s+NULL\s*;"
        r"\s*END\s*\$\$\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    guarded = sum(len(re.findall(r"ADD\s+CONSTRAINT", body, re.I)) for body in blocks)
    total = len(re.findall(r"ADD\s+CONSTRAINT", sql, re.I))
    assert total == len(COLUMNS), f"expected one CHECK per cost column, found {total}"
    assert guarded == total, (
        f"{total - guarded} of {total} ADD CONSTRAINT statement(s) are not wrapped in a "
        "duplicate_object handler — re-applying 070 would fail with 42710"
    )


@pytest.mark.parametrize("column", COLUMNS)
def test_cost_columns_stay_nullable_with_no_default(sql: str, column: str) -> None:
    """NULL is load-bearing: it means "this fill predates cost tracking".

    A ``DEFAULT 0`` or a ``NOT NULL`` would assert a measurement nobody took, and because
    069's trigger rejects UPDATE on this table, a pre-070 row can never be corrected — so
    the fabrication would be permanent. Zero-is-measured is the writer's job, not the
    schema's.
    """
    add = re.search(rf"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+{column}\s+numeric[^,;]*", sql, re.I)
    assert add is not None
    clause = add.group(0)
    assert "DEFAULT" not in clause.upper()
    assert "NOT NULL" not in clause.upper()


@pytest.mark.parametrize("column", COLUMNS)
def test_cost_checks_admit_null(sql: str, column: str) -> None:
    assert f"{column} IS NULL OR" in _check_body(sql, column)


@pytest.mark.parametrize("column", COLUMNS)
def test_cost_checks_reject_nan_and_infinity(sql: str, column: str) -> None:
    """NaN and Infinity both pass a bare ``>= 0`` in Postgres ``numeric``.

    NaN in particular poisons every SUM that reaches it, so a single bad fill would make
    every cost total downstream of it NaN rather than merely wrong by one row.
    """
    body = _check_body(sql, column)
    assert f"NOT ({column} = 'NaN'::numeric)" in body
    assert f"NOT ({column} = 'Infinity'::numeric)" in body


def test_fee_is_non_negative_but_slippage_is_signed(sql: str) -> None:
    """The asymmetry is the point, so it is pinned rather than left to the header prose.

    A negative fee is a rebate no paper venue here pays, and admitting one would let a
    fabricated credit flatter realised performance. Negative *slippage* is ordinary — it
    is a fill better than the declared mark — so clamping it would discard favourable
    execution silently, which is the same class of quiet wrongness in the other direction.
    """
    fee = _check_body(sql, "fee")
    slippage = _check_body(sql, "slippage")
    assert "fee >= 0" in fee
    assert ">= 0" not in slippage
    assert "NOT (slippage = '-Infinity'::numeric)" in slippage
    # -Infinity needs its own clause only where negatives are admitted: `fee >= 0`
    # already excludes it, so demanding the symmetric clause there would be noise.
    assert "-Infinity" not in fee


def test_migration_does_not_backfill_existing_fills(sql: str) -> None:
    """No DML at all: an UPDATE here would be both a fabrication and a hard failure.

    A fabrication because it would stamp 0 onto fills whose cost was never measured, and a
    hard failure because 069's shared trigger raises on UPDATE against this table — so the
    migration would abort rather than quietly mislead. Either way it must not appear.
    """
    for verb in ("UPDATE ", "DELETE ", "INSERT "):
        assert verb not in sql.upper(), f"070 must not contain {verb.strip()}"


@pytest.mark.parametrize("column", COLUMNS)
def test_cost_columns_document_their_units(sql: str, column: str) -> None:
    """Total dollars for the whole fill — not per-share, not bps.

    Mixed units in adjacent numeric columns is silent wrongness rather than a crash, and a
    reader who has only the schema in front of them has nothing else to go on.
    """
    # The body is matched as a run of quoted literals rather than "everything up to the
    # first `;`": these comments contain a semicolon *inside* a literal ("a measured zero;
    # NULL means ..."), so the lazy-to-semicolon form silently truncates and every
    # assertion below it becomes vacuous.
    match = re.search(
        rf"COMMENT\s+ON\s+COLUMN\s+{re.escape(TABLE)}\.{column}\s+IS\s+"
        rf"(?P<body>(?:\s*'[^']*')+)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing COMMENT ON COLUMN for {column}"
    body = " ".join(match.group("body").split()).lower()
    assert "dollars" in body
    assert "predates migration 070" in body
