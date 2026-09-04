"""Contract tests for migration 073 — lookback vs realized attribution (#2598)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "073_olympus_lookback_vs_realized.sql"

ACCOUNTING_TABLES = (
    "olympus_accounting_periods",
    "olympus_accounting_contributions",
    "olympus_accounting_holdings",
)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


def _view_body(sql: str, view: str) -> str:
    match = re.search(
        rf"CREATE OR REPLACE VIEW\s+public\.{view}\b.*?;",
        sql,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match, f"CREATE OR REPLACE VIEW for {view} not found"
    return match.group(0)


def test_migration_is_the_only_073() -> None:
    assert sorted(MIGRATIONS_DIR.glob("073_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_072() -> None:
    assert (MIGRATIONS_DIR / "072_olympus_period_accounting.sql").is_file()
    numbers = sorted(
        int(p.name.split("_", 1)[0]) for p in MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")
    )
    assert 73 in numbers
    assert numbers.index(72) < numbers.index(73)


def test_renames_base_table_to_current_book_lookback(sql: str) -> None:
    assert re.search(
        r"ALTER TABLE\s+public\.position_attribution\s+RENAME TO\s+current_book_lookback",
        sql,
        re.I,
    )


def test_adds_interval_and_contract_columns(sql: str) -> None:
    assert re.search(r"ADD COLUMN IF NOT EXISTS window_start_date\s+date", sql, re.I)
    assert re.search(r"ADD COLUMN IF NOT EXISTS window_end_date\s+date", sql, re.I)
    assert re.search(r"ADD COLUMN IF NOT EXISTS lookback_days\s+integer", sql, re.I)
    assert re.search(
        r"ADD COLUMN IF NOT EXISTS contract\s+text\s+NOT NULL\s+DEFAULT\s+'current_book_lookback'",
        sql,
        re.I,
    )
    assert re.search(r"CHECK\s*\(\s*contract\s*=\s*'current_book_lookback'\s*\)", sql, re.I)


def test_position_attribution_is_compat_view_not_base(sql: str) -> None:
    body = _view_body(sql, "position_attribution")
    assert re.search(r"security_invoker\s*=\s*true", body, re.I)
    assert "FROM public.current_book_lookback" in body
    assert "CREATE TABLE" not in body.upper() or "CREATE TABLE" not in body


def test_daily_realized_view_only_final_tip(sql: str) -> None:
    body = _view_body(sql, "daily_realized_attribution")
    assert re.search(r"security_invoker\s*=\s*true", body, re.I)
    assert "olympus_accounting_contributions" in body
    assert "olympus_accounting_periods" in body
    assert re.search(r"status\s*=\s*'final'", body, re.I)
    assert "supersedes_id" in body
    assert "current_book_lookback" not in body
    assert "position_attribution" not in body


@pytest.mark.parametrize("table", ACCOUNTING_TABLES)
def test_realized_view_does_not_grant_anon_on_private_bases(sql: str, table: str) -> None:
    # View itself must not grant anon; private bases stay locked.
    assert not re.search(
        rf"GRANT\s+SELECT\s+ON\s+public\.{table}\s+TO\s+anon",
        sql,
        re.I,
    )
    assert re.search(
        r"REVOKE ALL ON public\.daily_realized_attribution FROM PUBLIC, anon, authenticated",
        sql,
        re.I,
    )
    assert re.search(
        r"GRANT SELECT ON public\.daily_realized_attribution TO service_role",
        sql,
        re.I,
    )


def test_no_lookback_substitution_in_realized_view(raw: str) -> None:
    assert "never includes current_book_lookback" in raw.lower() or (
        "Never includes current_book_lookback" in raw
    )
