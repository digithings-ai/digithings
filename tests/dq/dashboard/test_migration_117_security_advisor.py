"""Structural contract tests for migration 117 (security advisor Now pile, #3461)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "117_security_advisor_now_pile.sql"

INITPLAN_TABLES = (
    "workspaces",
    "workspace_members",
    "positions",
    "position_events",
    "nav_history",
    "portfolio_metrics",
    "documents",
    "portfolio_ledger_commits",
    "portfolio_ledger_decision_intents",
    "portfolio_ledger_requested_targets",
    "portfolio_ledger_target_adjustments",
    "portfolio_ledger_approved_targets",
    "portfolio_ledger_order_intents",
    "portfolio_ledger_paper_executions",
    "portfolio_ledger_holding_lots",
    "olympus_accounting_periods",
    "olympus_accounting_contributions",
    "olympus_accounting_holdings",
    "olympus_profile_config",
)

SEARCH_PATH_FUNCTIONS = (
    "ensure_position_instrument",
    "set_instruments_updated_at",
    "search_architecture_notes",
    "reject_olympus_accounting_mutation",
    "reject_olympus_profile_config_mutation",
    "reject_olympus_research_corpus_mutation",
    "plan_tier_rank",
    "max_plan_tier",
)


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


def test_migration_is_the_only_117() -> None:
    assert sorted(MIGRATIONS_DIR.glob("117_*.sql")) == [MIGRATION_PATH]


def test_does_not_touch_public_tape_views(sql: str) -> None:
    forbidden = (
        "public_portfolio_positions",
        "public_price_latest",
        "public_nav_history",
        "public_accounting",
        "atlas_run_health",
        "olympus_run_event_trace",
    )
    lower = sql.lower()
    for name in forbidden:
        assert name not in lower, f"must not alter public tape view {name}"


def test_does_not_drop_unused_indexes(sql: str) -> None:
    assert "drop index" not in sql.lower()


def test_pins_search_path_on_listed_functions(sql: str) -> None:
    for name in SEARCH_PATH_FUNCTIONS:
        assert re.search(
            rf"ALTER\s+FUNCTION\s+public\.{re.escape(name)}\b[\s\S]*?SET\s+search_path\s*=",
            sql,
            re.I,
        ), name
    assert "knowledge_notes_set_updated_at" in sql


def test_revokes_anon_execute_on_workspace_bootstrap(sql: str) -> None:
    for fn in (
        "ensure_personal_workspace(uuid)",
        "ensure_my_workspace()",
        "handle_new_auth_user_workspace()",
        "my_access()",
    ):
        assert re.search(
            rf"REVOKE\s+ALL\s+ON\s+FUNCTION\s+public\.{re.escape(fn)}[\s\S]*?\bFROM\b[\s\S]*?\banon\b",
            sql,
            re.I,
        ), fn
    assert re.search(
        r"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+public\.ensure_my_workspace\(\)\s+"
        r"TO\s+authenticated,\s*service_role",
        sql,
        re.I,
    )
    assert re.search(
        r"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+public\.my_access\(\)\s+"
        r"TO\s+authenticated,\s*service_role",
        sql,
        re.I,
    )
    assert not re.search(
        r"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+public\.ensure_personal_workspace\(uuid\)\s+"
        r"TO\s+[^\n]*\banon\b",
        sql,
        re.I,
    )


def test_initplan_wraps_auth_uid_on_all_listed_tables(sql: str) -> None:
    created = {
        m.group(1)
        for m in re.finditer(
            r'CREATE\s+POLICY\s+"[^"]+"\s+ON\s+(?:public\.)?(\w+)',
            sql,
            re.I,
        )
    }
    assert created == set(INITPLAN_TABLES)
    wrapped = re.findall(r"\(SELECT\s+auth\.uid\(\)\)", sql, re.I)
    assert len(wrapped) == len(INITPLAN_TABLES)
    stripped = re.sub(r"\(SELECT\s+auth\.uid\(\)\)", "", sql, flags=re.I)
    assert "auth.uid()" not in stripped


def test_preserves_house_teaser_on_group_a(sql: str) -> None:
    house = "6b753576-ced9-5319-9bfa-c5d0aacd9319"
    for table in ("positions", "position_events", "nav_history", "portfolio_metrics"):
        assert re.search(
            rf"ON\s+(?:public\.)?{table}[\s\S]*?{house}",
            sql,
            re.I,
        ), table


def test_preserves_documents_house_and_system(sql: str) -> None:
    assert "6b753576-ced9-5319-9bfa-c5d0aacd9319" in sql
    assert "1105372f-4109-5815-be5a-21091ccfc8ad" in sql
    assert re.search(
        r'CREATE\s+POLICY\s+"authenticated_select_documents"\s+ON\s+(?:public\.)?documents',
        sql,
        re.I,
    )
