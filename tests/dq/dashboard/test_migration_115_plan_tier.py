"""Structural contract tests for migration 115 (Brief/Desk/Studio plan_tier)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "115_plan_tier_brief_desk_studio.sql"


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


def test_migration_is_the_only_115() -> None:
    assert sorted(MIGRATIONS_DIR.glob("115_*.sql")) == [MIGRATION_PATH]


def test_does_not_steal_cutover_113(sql: str) -> None:
    assert not re.search(r"\b113_", sql)


def test_maps_baseline_and_custom_rows(sql: str) -> None:
    assert re.search(
        r"WHEN\s+'baseline'\s+THEN\s+'desk'",
        sql,
        re.I,
    )
    assert re.search(
        r"WHEN\s+'custom'\s+THEN\s+'studio'",
        sql,
        re.I,
    )
    assert "workspaces" in sql
    assert "entitlement_grants" in sql


def test_new_plan_tier_check(sql: str) -> None:
    assert re.search(
        r"workspaces_plan_tier_check[\s\S]*?"
        r"plan_tier\s+IN\s*\(\s*'free'\s*,\s*'brief'\s*,\s*'desk'\s*,\s*'studio'\s*,\s*'enterprise'\s*\)",
        sql,
        re.I,
    )
    assert re.search(
        r"entitlement_grants_plan_floor_check[\s\S]*?"
        r"plan_floor\s+IN\s*\(\s*'brief'\s*,\s*'desk'\s*,\s*'studio'\s*,\s*'enterprise'\s*\)",
        sql,
        re.I,
    )
    assert "'baseline'" in sql  # mapping source only
    assert not re.search(
        r"CHECK\s*\(\s*plan_tier\s+IN\s*\([^)]*'baseline'",
        sql,
        re.I,
    )


def test_plan_tier_rank_ladders_brief_desk_studio(sql: str) -> None:
    assert re.search(r"WHEN\s+'brief'\s+THEN\s+1", sql, re.I)
    assert re.search(r"WHEN\s+'desk'\s+THEN\s+2", sql, re.I)
    assert re.search(r"WHEN\s+'studio'\s+THEN\s+3", sql, re.I)
    assert re.search(r"WHEN\s+'enterprise'\s+THEN\s+4", sql, re.I)


def test_creator_seed_floor_is_studio(sql: str) -> None:
    assert "chris.stefan@proton.me" in sql
    assert re.search(
        r"'chris\.stefan@proton\.me'[\s\S]{0,80}'studio'",
        sql,
        re.I,
    )


def test_drops_old_checks_before_add(sql: str) -> None:
    drop_ws = sql.upper().find("DROP CONSTRAINT IF EXISTS WORKSPACES_PLAN_TIER_CHECK")
    add_ws = sql.upper().find("ADD CONSTRAINT WORKSPACES_PLAN_TIER_CHECK")
    assert drop_ws != -1 and add_ws != -1 and drop_ws < add_ws
