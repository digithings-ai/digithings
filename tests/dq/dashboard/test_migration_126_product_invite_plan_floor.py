"""Structural contract tests for migration 126 (tiered invite plan_floor)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "126_product_invite_plan_floor.sql"


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    raw = MIGRATION_PATH.read_text(encoding="utf-8")
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


def test_migration_is_the_only_126() -> None:
    assert sorted(MIGRATIONS_DIR.glob("126_*.sql")) == [MIGRATION_PATH]


def test_adds_plan_floor_column_with_known_tiers(sql: str) -> None:
    assert "ADD COLUMN IF NOT EXISTS plan_floor text" in sql
    for tier in ("brief", "desk", "studio", "enterprise"):
        assert f"'{tier}'" in sql
    # Nullable — product grant without a tier bump stays valid.
    assert "plan_floor is null or plan_floor in" in sql


def test_does_not_relax_product_key_or_grant_anon(sql: str) -> None:
    assert "product_key drop not null" not in sql.lower()
    assert "TO anon" not in sql
    assert "TO PUBLIC" not in sql
