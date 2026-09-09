"""Structural contract tests for staged cutover 113 (not auto-applied)."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import pytest
from digiquant.dashboard.overlay.persist import (
    LEGACY_BOOK_UNIQUE_CODE,
    OverlayLegacyBookBlocked,
    require_overlay_legacy_book_safe,
)
from digiquant.dashboard.tenancy import house_workspace_id

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
CUTOVER_PATH = MIGRATIONS_DIR / "cutover" / "113_drop_legacy_book_uniques.sql"
CUTOVER_900 = MIGRATIONS_DIR / "cutover" / "900_drop_anon_read_cutover.sql"

LEGACY_KEYS_DROPPED = (
    "positions_date_ticker_key",
    "position_events_date_ticker_key",
    "nav_history_pkey",
    "portfolio_metrics_date_key",
)

WIDENED_UNIQUES_KEPT = (
    "uq_positions_workspace_date_ticker",
    "uq_position_events_workspace_date_ticker",
    "uq_nav_history_workspace_date",
    "uq_portfolio_metrics_workspace_date",
)

LEDGER_ONE_ROOT = (
    "uq_portfolio_ledger_commits_one_root",
    "uq_portfolio_ledger_approved_targets_one_root",
    "uq_portfolio_ledger_order_intents_one_root",
)


@pytest.fixture(scope="module")
def raw() -> str:
    assert CUTOVER_PATH.is_file(), f"cutover missing: {CUTOVER_PATH}"
    return CUTOVER_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


def test_cutover_stays_under_cutover_dir() -> None:
    assert CUTOVER_PATH.parent.name == "cutover"
    top_level = list(MIGRATIONS_DIR.glob("113_*.sql"))
    assert top_level == []
    assert CUTOVER_900.is_file()


def test_db_migrate_and_verify_are_maxdepth_one() -> None:
    migrate = (REPO_ROOT / ".github" / "workflows" / "db-migrate.yml").read_text(encoding="utf-8")
    verify = (
        REPO_ROOT / "digiquant" / "scripts" / "research" / "verify-supabase-migrations.sh"
    ).read_text(encoding="utf-8")
    rls = (REPO_ROOT / "scripts" / "rls_proof" / "run.sh").read_text(encoding="utf-8")
    assert "find digiquant/supabase/migrations -maxdepth 1" in migrate
    assert "-maxdepth 1 -name '*.sql'" in verify or '-maxdepth 1 -name "*.sql"' in verify
    assert "cutover/900_drop_anon_read_cutover.sql" in rls
    assert "113_drop_legacy_book_uniques" not in rls


def test_header_is_loud_human_gate(raw: str) -> None:
    upper = raw.upper()
    assert "NOT AUTO-APPLIED" in upper
    assert "DO NOT APPLY ON CORE" in upper
    assert "HUMAN GATE" in upper
    assert "42P10" in raw
    assert "require_overlay_legacy_book_safe" in raw
    assert "daily_snapshots" in raw


def test_drops_legacy_group_a_keys(sql: str) -> None:
    for name in LEGACY_KEYS_DROPPED:
        assert re.search(
            rf"DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+{name}\b",
            sql,
            re.I,
        ), name


def test_keeps_widened_uniques(sql: str) -> None:
    for name in WIDENED_UNIQUES_KEPT:
        assert not re.search(
            rf"DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+{name}\b",
            sql,
            re.I,
        ), name


def test_does_not_drop_daily_snapshots_unique(sql: str) -> None:
    assert "daily_snapshots" not in sql
    assert not re.search(
        r"DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+daily_snapshots",
        sql,
        re.I,
    )


def test_widens_ledger_one_root_indexes(sql: str) -> None:
    for name in LEDGER_ONE_ROOT:
        assert re.search(rf"DROP\s+INDEX\s+IF\s+EXISTS\s+public\.{name}\b", sql, re.I), name
        assert re.search(
            rf"CREATE\s+UNIQUE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+{name}\b",
            sql,
            re.I,
        ), name
    assert re.search(
        r"uq_portfolio_ledger_commits_one_root\s+"
        r"ON\s+public\.portfolio_ledger_commits\s*\(\s*workspace_id\s*,\s*run_date\s*\)",
        sql,
        re.I,
    )
    assert re.search(
        r"uq_portfolio_ledger_approved_targets_one_root\s+"
        r"ON\s+public\.portfolio_ledger_approved_targets\s*"
        r"\(\s*workspace_id\s*,\s*run_date\s*,\s*symbol\s*\)",
        sql,
        re.I,
    )
    assert re.search(
        r"uq_portfolio_ledger_order_intents_one_root\s+"
        r"ON\s+public\.portfolio_ledger_order_intents\s*"
        r"\(\s*workspace_id\s*,\s*run_date\s*,\s*symbol\s*\)",
        sql,
        re.I,
    )
    assert len(re.findall(r"WHERE\s+supersedes_id\s+IS\s+NULL", sql, re.I)) == 3


def test_does_not_drop_anon_or_rls_policies(sql: str) -> None:
    assert not re.search(r"DROP\s+POLICY\b", sql, re.I)
    assert not re.search(r"CREATE\s+POLICY\b", sql, re.I)


def test_staging_113_does_not_lift_overlay_python_gate() -> None:
    """Cutover file is inert until applied; overlay book writes stay fail-closed."""
    with pytest.raises(OverlayLegacyBookBlocked) as exc:
        require_overlay_legacy_book_safe(uuid4())
    assert exc.value.code == LEGACY_BOOK_UNIQUE_CODE
    require_overlay_legacy_book_safe(None)
    require_overlay_legacy_book_safe(house_workspace_id())
