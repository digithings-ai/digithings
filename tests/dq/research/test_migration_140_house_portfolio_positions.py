"""Migration 140 pins public_portfolio_positions to the house book.

050's view uses ``max(date)`` over every workspace. After 139 the view is
security_invoker, so service_role (prices-live) and an authenticated member
who can also read their own book still see that unfiltered aggregate. A later
private date replaces the public ticker set. These checks lock the replacement
definition; they do not execute SQL.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION = MIGRATIONS / "140_house_public_portfolio_positions.sql"
HOUSE_ID = "6b753576-ced9-5319-9bfa-c5d0aacd9319"

PRIVATE_COLUMNS = (
    "rationale",
    "pm_notes",
    "thesis_id",
    "conviction",
    "stop_loss_pct",
    "target_pct_gain",
    "horizon_days",
)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"migration missing: {MIGRATION}"
    return _strip_comments(MIGRATION.read_text(encoding="utf-8"))


def _view_body(sql: str) -> str:
    match = re.search(
        r"CREATE OR REPLACE VIEW\s+public\.public_portfolio_positions\b.*?;",
        sql,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match, "public_portfolio_positions view not found"
    return match.group(0)


def test_migration_140_is_only_140() -> None:
    assert sorted(MIGRATIONS.glob("140_*.sql")) == [MIGRATION]


def test_view_stays_security_invoker(sql: str) -> None:
    body = _view_body(sql)
    assert re.search(r"security_invoker\s*=\s*true", body, re.I)
    assert "ALTER VIEW public.public_portfolio_positions SET (security_invoker = true);" in sql


def test_latest_date_subquery_is_house_only(sql: str) -> None:
    """The old ``max(date)`` scan had no workspace filter; a later private book won."""
    body = _view_body(sql)
    assert HOUSE_ID in body
    assert body.lower().count(HOUSE_ID) >= 2
    before, after = body.lower().split("max(date)", 1)
    assert "workspace_id" in before
    assert HOUSE_ID in before
    assert "workspace_id" in after
    assert HOUSE_ID in after
    assert "from public.positions" in after


@pytest.mark.parametrize("column", PRIVATE_COLUMNS)
def test_research_columns_stay_out(sql: str, column: str) -> None:
    assert not re.search(rf"\b{column}\b", _view_body(sql), re.I)


def test_does_not_touch_cutover_113(sql: str) -> None:
    assert "113_drop" not in sql
    assert "nav_history_pkey" not in sql.lower()
    assert "drop constraint" not in sql.lower()
