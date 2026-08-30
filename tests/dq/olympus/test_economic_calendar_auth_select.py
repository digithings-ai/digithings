"""Structural contract: economic_calendar authenticated SELECT is ledger 114."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_114 = MIGRATIONS_DIR / "114_economic_calendar_authenticated_select.sql"


def test_authenticated_select_is_ledger_114_not_113() -> None:
    """Do not steal cutover number 113 (#3321 collision)."""
    assert MIGRATION_114.is_file()
    assert list(MIGRATIONS_DIR.glob("113_*.sql")) == []
    sql = MIGRATION_114.read_text(encoding="utf-8")
    assert "economic_calendar_authenticated_select" in sql
    assert "TO authenticated" in sql
    assert "DROP POLICY IF EXISTS economic_calendar_authenticated_select" in sql
    assert "CREATE POLICY economic_calendar_authenticated_select" in sql
    assert "cutover/113_drop_legacy_book_uniques.sql" in sql
