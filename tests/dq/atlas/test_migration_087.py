"""Contract tests for migration 087, outcome horizon + natural unique (#2797)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "087_olympus_forecast_outcome_horizon_unique.sql"


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_migration_is_the_only_087() -> None:
    assert sorted(MIGRATIONS_DIR.glob("087_*.sql")) == [MIGRATION_PATH]


def test_adds_horizon_sessions_column(raw: str) -> None:
    assert "ADD COLUMN IF NOT EXISTS horizon_sessions" in raw
    assert "horizon_sessions > 0" in raw


def test_unique_natural_key(raw: str) -> None:
    assert "uq_olympus_forecast_outcomes_effective_maturity" in raw
    assert re.search(
        r"UNIQUE\s+INDEX[\s\S]*\(effective_forecast_id,\s*maturity_session\)",
        raw,
        re.IGNORECASE,
    )


def test_no_historical_backfill(raw: str) -> None:
    assert "INSERT INTO" not in raw.upper()
    assert not re.search(r"\bUPDATE\b", raw, re.IGNORECASE)
