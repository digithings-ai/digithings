"""Unit tests for migration 025 (thesis daily fields — spec §7.1)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "supabase"
    / "migrations"
    / "025_thesis_daily_fields.sql"
)

NEW_COLUMNS = (
    "confidence",
    "validation_criteria",
    "invalidation_criteria",
    "horizon",
    "thesis_kind",
    "linked_market_thesis_id",
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _strip_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


@pytest.mark.unit
class TestMigration025ThesisDailyFields:
    def test_file_exists_and_nonempty(self, sql: str) -> None:
        assert len(sql) > 200

    def test_alters_theses_table(self, sql: str) -> None:
        body = _strip_comments(sql)
        assert re.search(r"ALTER TABLE\s+theses\b", body)

    @pytest.mark.parametrize("col", NEW_COLUMNS)
    def test_adds_column(self, sql: str, col: str) -> None:
        body = _strip_comments(sql)
        assert re.search(rf"ADD COLUMN IF NOT EXISTS\s+{col}\b", body), f"missing ADD COLUMN {col}"

    def test_confidence_range_check(self, sql: str) -> None:
        body = _strip_comments(sql)
        assert "chk_theses_confidence" in body
        assert re.search(r"confidence\s+>=\s*0", body)
        assert re.search(r"confidence\s+<=\s*1", body)

    def test_thesis_kind_check(self, sql: str) -> None:
        body = _strip_comments(sql)
        assert "chk_theses_kind" in body
        assert "'market'" in body and "'vehicle'" in body

    def test_begin_commit_wraps_body(self, sql: str) -> None:
        body = _strip_comments(sql)
        assert body.count("BEGIN;") >= 1
        assert body.count("COMMIT;") >= 1
