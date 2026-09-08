"""Contract tests for migration 085 — tip views require complete children (#2780)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "085_olympus_accounting_tip_children_complete.sql"

TIP_VIEWS = (
    "public_accounting_period_status",
    "public_finalized_nav",
    "public_daily_realized_attribution",
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


def _view_body(sql: str, view: str) -> str:
    match = re.search(
        rf"CREATE OR REPLACE VIEW\s+public\.{view}\b.*?;",
        sql,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match, f"CREATE OR REPLACE VIEW for {view} not found"
    return match.group(0)


def test_migration_is_the_only_085() -> None:
    assert sorted(MIGRATIONS_DIR.glob("085_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_084() -> None:
    assert (MIGRATIONS_DIR / "084_olympus_accounting_day_return_pct.sql").is_file()
    numbers = sorted(
        int(p.name.split("_", 1)[0]) for p in MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")
    )
    assert 85 in numbers
    assert numbers.index(84) < numbers.index(85)


@pytest.mark.parametrize("view", TIP_VIEWS)
def test_tip_views_require_contribution_when_active(sql: str, view: str) -> None:
    body = _view_body(sql, view)
    assert "olympus_accounting_contributions" in body
    assert re.search(r"net_pnl_total\s*<>\s*0", body, re.I) or re.search(
        r"net_pnl_total\s*!=\s*0", body, re.I
    )
    assert "EXISTS" in body.upper()


@pytest.mark.parametrize("view", TIP_VIEWS)
def test_tip_views_require_holding_for_positive_qty(sql: str, view: str) -> None:
    body = _view_body(sql, view)
    assert "olympus_accounting_holdings" in body
    assert re.search(r"closing_quantity\s*>\s*0", body, re.I)
    assert re.search(r"upper\s*\(\s*h\.symbol\s*\)", body, re.I)


def test_finalized_nav_still_final_only(sql: str) -> None:
    body = _view_body(sql, "public_finalized_nav")
    assert re.search(r"status\s*=\s*'final'", body, re.I)
    assert "supersedes_id" in body


def test_period_status_still_allows_non_final(sql: str) -> None:
    body = _view_body(sql, "public_accounting_period_status")
    assert not re.search(r"WHERE\s+p\.status\s*=\s*'final'", body, re.I)


def test_no_base_table_grants(sql: str) -> None:
    for table in (
        "olympus_accounting_periods",
        "olympus_accounting_contributions",
        "olympus_accounting_holdings",
    ):
        assert not re.search(
            rf"GRANT\s+SELECT\s+ON\s+public\.{table}\s+TO\s+(?:anon|authenticated)",
            sql,
            re.I,
        )


def test_documents_period_children_complete(raw: str) -> None:
    lower = raw.lower()
    assert "period_children_complete" in lower or "children" in lower
    assert "2780" in raw
