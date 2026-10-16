"""Contract tests for migration 078 — documents.category planner (#2622)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "078_attention_plan_category.sql"


def test_migration_078_registers_planner_category() -> None:
    assert MIGRATION_PATH.is_file()
    raw = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "COMMIT;" not in raw.upper()
    assert "'planner'" in raw
    assert "'learning'" in raw
    assert "chk_documents_category" in raw
    assert sorted(MIGRATIONS_DIR.glob("078_*.sql")) == [MIGRATION_PATH]
