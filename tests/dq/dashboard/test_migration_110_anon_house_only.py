"""Structural contract tests for migration 110 (anon house-only private books)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "110_anon_house_only_private_books.sql"
HOUSE_UUID = "6b753576-ced9-5319-9bfa-c5d0aacd9319"
SYSTEM_UUID = "1105372f-4109-5815-be5a-21091ccfc8ad"
BOOK_TABLES = ("positions", "position_events", "nav_history", "portfolio_metrics")


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


def _anon_policy_body(sql: str, table: str) -> str:
    match = re.search(
        rf'CREATE\s+POLICY\s+"anon_read"\s+ON\s+public\.{table}\b([\s\S]*?);',
        sql,
        re.I,
    )
    assert match, f"missing anon_read recreate for {table}"
    return match.group(1)


def test_migration_is_the_only_110() -> None:
    assert sorted(MIGRATIONS_DIR.glob("110_*.sql")) == [MIGRATION_PATH]


def test_keeps_anon_read_policy_name_for_cutover_drop(sql: str) -> None:
    for table in (*BOOK_TABLES, "documents"):
        assert re.search(
            rf'DROP\s+POLICY\s+IF\s+EXISTS\s+"anon_read"\s+ON\s+public\.{table}',
            sql,
            re.I,
        ), table
        body = _anon_policy_body(sql, table)
        assert re.search(r"FOR\s+SELECT\s+TO\s+anon", body, re.I), table


def test_book_tables_are_house_uuid_only(sql: str) -> None:
    for table in BOOK_TABLES:
        body = _anon_policy_body(sql, table)
        assert HOUSE_UUID in body, table
        assert SYSTEM_UUID not in body, table
        assert "USING (true)" not in body.replace(" ", "").lower()
        assert "workspace_members" not in body


def test_documents_allow_house_and_system_not_overlay(sql: str) -> None:
    body = _anon_policy_body(sql, "documents")
    assert HOUSE_UUID in body
    assert SYSTEM_UUID in body
    assert "workspace_members" not in body
    assert "USING (true)" not in body.replace(" ", "").lower()


def test_does_not_touch_shared_teasers_or_cutover_900(sql: str) -> None:
    assert "daily_snapshots" not in sql
    assert "theses" not in sql
    assert "instruments" not in sql
    assert "public_daily_research" not in sql
    assert "drop_anon_read" not in sql.lower()
    assert "current_book_lookback" not in sql
