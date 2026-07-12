"""Unit tests for migration 051 (strategy-store lockdown, #1462).

Hermetic pure-SQL parse checks in the ``test_migration_050.py`` mold: no
Postgres, no network. The load-bearing guarantee is that the lockdown covers
exactly the three ruled tables (user ruling 2026-07-10, #1462) — dropping
their anon policies AND revoking their grants — while never touching
``strategy_tearsheets`` (which stays public) or destroying any object.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "supabase"
    / "migrations"
    / "051_lock_strategy_store.sql"
)

LOCKED_TABLES = ("strategies", "strategy_signals", "strategy_trades")


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def statements(sql: str) -> str:
    """The migration with comment lines stripped, so assertions bind to executable SQL."""
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def test_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


@pytest.mark.parametrize("table", LOCKED_TABLES)
def test_drops_the_anon_policy(statements: str, table: str) -> None:
    assert re.search(
        rf"DROP POLICY IF EXISTS {table}_anon_select ON public\.{table}\b",
        statements,
    ), f"missing idempotent anon-policy drop for {table}"


@pytest.mark.parametrize("table", LOCKED_TABLES)
def test_revokes_table_grants(statements: str, table: str) -> None:
    assert re.search(
        rf"REVOKE ALL ON public\.{table}\s+FROM PUBLIC, anon, authenticated",
        statements,
    ), f"missing grant revoke for {table}"


def test_strategy_tearsheets_untouched(statements: str) -> None:
    # strategy_tearsheets keeps its anon policy by ruling — the migration must not
    # reference it in any executable statement.
    assert "strategy_tearsheets" not in statements


def test_nothing_destroyed_and_no_regrants(statements: str) -> None:
    assert not re.search(r"\bDROP TABLE\b|\bTRUNCATE\b|\bDELETE FROM\b", statements, re.I)
    assert not re.search(r"\bGRANT\b", statements, re.I), "lockdown must not grant anything"
    assert not re.search(r"\bCREATE POLICY\b", statements, re.I)


def test_service_role_untouched(statements: str) -> None:
    assert "service_role" not in statements
