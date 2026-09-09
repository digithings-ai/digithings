"""Contract tests for migration 095, TargetAdjustment vocabulary widen (#2768)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "095_olympus_target_adjustment_types.sql"

SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)

H8_TYPES = (
    "conviction_floor",
    "single_name_cap",
    "sector_cap",
    "correlation_dedup",
    "volatility_scale",
    "drawdown_breaker",
    "grid_rounding",
    "cadence_hold",
    "minimum_hold_override",
    "continuity_carry",
    "final_gross_scale",
    "flat_exit",
)
LEGACY_TYPES = ("cap", "rounding", "carry")
REDUCING_TYPES = (
    "cap",
    "single_name_cap",
    "sector_cap",
    "correlation_dedup",
    "drawdown_breaker",
    "grid_rounding",
    "flat_exit",
)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


def test_migration_is_the_only_095() -> None:
    assert sorted(MIGRATIONS_DIR.glob("095_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_094() -> None:
    assert (MIGRATIONS_DIR / "094_olympus_policy_replay.sql").is_file()


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_no_historical_backfill(sql: str) -> None:
    assert "INSERT INTO" not in sql.upper()


def test_widens_adjustment_type_check(sql: str) -> None:
    assert "portfolio_ledger_target_adjustments_adjustment_type_check" in sql
    for value in (*LEGACY_TYPES, *H8_TYPES):
        assert f"'{value}'" in sql, f"missing vocabulary member {value}"


def test_reducing_types_check_covers_h8_reduce_only(sql: str) -> None:
    assert "chk_portfolio_ledger_target_adjustments_reducing_types" in sql
    for value in REDUCING_TYPES:
        assert f"'{value}'" in sql, f"reducing CHECK missing {value}"


def test_names_h9_as_producer(sql: str) -> None:
    assert "append_commit_chain" in sql or "H9" in sql
