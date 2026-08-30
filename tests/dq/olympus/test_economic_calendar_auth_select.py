"""Structural contract: economic_calendar authenticated SELECT is ledger 114."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_114 = MIGRATIONS_DIR / "114_economic_calendar_authenticated_select.sql"


def _sql_without_line_comments(raw: str) -> str:
    kept = [
        line for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("--")
    ]
    return re.sub(r"\s+", " ", "\n".join(kept)).strip()


def test_authenticated_select_is_ledger_114_not_113() -> None:
    """Do not steal cutover number 113 (#3321 collision). Pin executable SQL."""
    assert MIGRATION_114.is_file()
    assert list(MIGRATIONS_DIR.glob("113_*.sql")) == []
    raw = MIGRATION_114.read_text(encoding="utf-8")
    sql = _sql_without_line_comments(raw)
    assert "cutover/113_drop_legacy_book_uniques.sql" in raw
    assert (
        "DROP POLICY IF EXISTS economic_calendar_authenticated_select ON public.economic_calendar;"
    ) in sql
    assert (
        "CREATE POLICY economic_calendar_authenticated_select ON public.economic_calendar "
        "FOR SELECT TO authenticated USING (true);"
    ) in sql
    assert re.search(r"\bFOR ALL\b", sql) is None
    assert re.search(r"\b(INSERT|UPDATE|DELETE)\b", sql, flags=re.IGNORECASE) is None
