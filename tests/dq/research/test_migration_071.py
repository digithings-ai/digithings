"""Contract tests for migration 071 — position_events book_source labeling (#2422)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "071_olympus_position_events_book_source.sql"

VIEWS = (
    "olympus_position_events",
    "olympus_position_events_authoritative",
)

LEDGER_TABLES = (
    "portfolio_ledger_commits",
    "portfolio_ledger_decision_intents",
    "portfolio_ledger_requested_targets",
    "portfolio_ledger_target_adjustments",
    "portfolio_ledger_approved_targets",
    "portfolio_ledger_order_intents",
    "portfolio_ledger_paper_executions",
    "portfolio_ledger_holding_lots",
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


def test_migration_is_the_only_071() -> None:
    assert sorted(MIGRATIONS_DIR.glob("071_*.sql")) == [MIGRATION_PATH]


def test_adds_book_source_default_legacy(sql: str) -> None:
    assert re.search(
        r"ADD COLUMN IF NOT EXISTS book_source\s+text\s+NOT NULL\s+DEFAULT\s+'legacy'",
        sql,
        re.I,
    )
    assert re.search(
        r"CHECK\s*\(\s*book_source\s+IN\s*\(\s*'legacy'\s*,\s*'authoritative'\s*\)\s*\)",
        sql,
        re.I,
    )


@pytest.mark.parametrize("view", VIEWS)
def test_views_exist_and_use_security_invoker(sql: str, view: str) -> None:
    body = _view_body(sql, view)
    assert re.search(r"security_invoker\s*=\s*true", body, re.I)


def test_authoritative_view_filters_book_source(sql: str) -> None:
    body = _view_body(sql, "olympus_position_events_authoritative")
    assert re.search(r"WHERE\s+book_source\s*=\s*'authoritative'", body, re.I)
    # Must not pull private ledger tables into the public projection.
    for table in LEDGER_TABLES:
        assert table not in body


def test_compat_view_reads_position_events_only(sql: str) -> None:
    body = _view_body(sql, "olympus_position_events")
    assert "FROM public.position_events" in body or re.search(
        r"FROM\s+public\.position_events", body, re.I
    )
    for table in LEDGER_TABLES:
        assert table not in body


def test_views_grant_select_without_exposing_ledger_tables(sql: str) -> None:
    assert "GRANT SELECT ON public.olympus_position_events" in sql
    assert "GRANT SELECT ON public.olympus_position_events_authoritative" in sql
    for table in LEDGER_TABLES:
        assert f"GRANT SELECT ON public.{table}" not in sql
        assert f"FROM public.{table}" not in sql
