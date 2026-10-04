"""Migration 142 house-scopes the two remaining public accounting definer views.

123 left public_accounting_period_status and public_daily_realized_attribution
security_invoker=false, granted to anon, and unfiltered by workspace. After 134
the bases are accounting_periods / accounting_contributions / accounting_holdings;
135 dropped the old-name views. These projections stay security definer and
publish only the house workspace. Static parse only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION = MIGRATIONS / "142_house_accounting_status_attribution.sql"
HOUSE_ID = "6b753576-ced9-5319-9bfa-c5d0aacd9319"
RENAMED = (
    "accounting_periods",
    "accounting_contributions",
    "accounting_holdings",
)
DROPPED = (
    "olympus_accounting_periods",
    "olympus_accounting_contributions",
    "olympus_accounting_holdings",
)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"migration missing: {MIGRATION}"
    return _strip_comments(MIGRATION.read_text(encoding="utf-8"))


def _view_body(sql: str, view: str) -> str:
    match = re.search(
        rf"CREATE OR REPLACE VIEW\s+public\.{view}\b.*?;",
        sql,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match, f"CREATE OR REPLACE VIEW for {view} not found"
    return match.group(0)


def test_migration_142_is_only_142() -> None:
    assert sorted(MIGRATIONS.glob("142_*.sql")) == [MIGRATION]


@pytest.mark.parametrize(
    "view",
    ["public_accounting_period_status", "public_daily_realized_attribution"],
)
def test_views_stay_definer_and_house_scoped(sql: str, view: str) -> None:
    body = _view_body(sql, view)
    assert re.search(r"security_invoker\s*=\s*false", body, re.I)
    assert re.search(r"security_barrier\s*=\s*true", body, re.I)
    assert (
        f"ALTER VIEW public.{view} SET (security_invoker = false, security_barrier = true);"
    ) in sql
    assert HOUSE_ID in body
    assert re.search(r"p\.workspace_id\s*=", body, re.I)
    assert re.search(
        rf"GRANT\s+SELECT\s+ON\s+public\.{view}\s+TO\s+anon\s*,\s*authenticated",
        sql,
        re.I,
    )


def test_period_status_keeps_credible_tip_and_renamed_tables(sql: str) -> None:
    body = _view_body(sql, "public_accounting_period_status")
    assert "accounting_period_status" in body
    assert "quality_reasons" in body
    assert "supersedes_id" in body
    for table in RENAMED:
        assert re.search(rf"public\.{table}\b", body), table
    assert re.search(r"status\s*=\s*'final'", body) is None


def test_attribution_keeps_final_tip_and_renamed_tables(sql: str) -> None:
    body = _view_body(sql, "public_daily_realized_attribution")
    assert "daily_realized_attribution" in body
    assert re.search(r"status\s*=\s*'final'", body, re.I)
    assert "cardinality" in body.lower()
    assert re.search(r"public\.accounting_contributions\s+c\b", body, re.I)
    assert re.search(r"JOIN\s+public\.accounting_periods\s+p\b", body, re.I)
    assert re.search(r"public\.accounting_holdings\b", body, re.I)


def test_executable_sql_does_not_name_dropped_views(sql: str) -> None:
    for dropped in DROPPED:
        assert dropped not in sql, dropped


def test_no_anon_grant_on_accounting_bases(sql: str) -> None:
    for table in (*DROPPED, *RENAMED):
        assert not re.search(
            rf"GRANT\s+SELECT\s+ON\s+(?:public\.)?{table}\s+TO\s+(?:anon|authenticated)",
            sql,
            re.I,
        )


def test_does_not_replace_history_or_cutover_113(sql: str) -> None:
    assert "public_accounting_nav_history" not in sql
    assert "public_finalized_nav" not in sql
    assert "113_drop" not in sql
    assert "drop constraint" not in sql.lower()
