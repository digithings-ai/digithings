"""Structural contract tests for migration 109 (authenticated house teaser read)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "109_authenticated_house_teaser_read.sql"
HOUSE_UUID = "6b753576-ced9-5319-9bfa-c5d0aacd9319"


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


def test_migration_is_the_only_109() -> None:
    assert sorted(MIGRATIONS_DIR.glob("109_*.sql")) == [MIGRATION_PATH]


def test_does_not_touch_anon_read(sql: str) -> None:
    assert not re.search(r"DROP\s+POLICY[^;]*anon_read", sql, re.I)
    assert not re.search(r'CREATE\s+POLICY\s+"anon_read"', sql, re.I)
    assert "TO anon" not in sql


def test_teaser_policies_on_shared_tables(sql: str) -> None:
    for table in ("daily_snapshots", "theses", "instruments"):
        assert re.search(
            rf'CREATE\s+POLICY\s+"authenticated_read_house_teaser"\s+ON\s+public\.{table}\b',
            sql,
            re.I,
        ), table
        assert re.search(
            rf'CREATE\s+POLICY\s+"authenticated_read_house_teaser"\s+ON\s+public\.{table}\b'
            rf'[\s\S]*?FOR\s+SELECT\s+TO\s+authenticated[\s\S]*?USING\s*\(\s*true\s*\)',
            sql,
            re.I,
        ), table


def test_house_or_membership_on_book_tables(sql: str) -> None:
    for table in ("positions", "position_events", "nav_history", "portfolio_metrics"):
        assert re.search(
            rf'CREATE\s+POLICY\s+"authenticated_select_own_workspace"\s+ON\s+public\.{table}\b',
            sql,
            re.I,
        ), table
        assert HOUSE_UUID in sql
        assert "workspace_members" in sql
        # System workspace must NOT be granted on the private book (098 stance).
        assert "1105372f-4109-5815-be5a-21091ccfc8ad" not in sql


def test_no_cutover_900_content(sql: str) -> None:
    assert "public_daily_research" not in sql
    assert "drop_anon_read" not in sql.lower()
