"""Pins for migration 139 — core security-advisor harden (#4630).

Asserts the SQL text contract: safe invoker flips, accepted DEFINER comments,
atlas_run_health drop, pg_net revoke from API roles, duplicate tags index drop.
Does not hit a live database.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    REPO_ROOT
    / "digiquant"
    / "supabase"
    / "migrations"
    / "139_core_advisor_harden.sql"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _sql_body() -> str:
    """Strip SQL line comments so pins ignore prose in -- headers."""
    lines = []
    for line in _sql().splitlines():
        stripped = line.lstrip()
        if stripped.startswith("--"):
            continue
        lines.append(re.sub(r"--.*$", "", line))
    return chr(10).join(lines)


def test_migration_139_exists() -> None:
    assert MIGRATION.is_file(), "139_core_advisor_harden.sql is missing"


def test_safe_invoker_flips() -> None:
    sql = _sql_body()
    assert (
        "ALTER VIEW public.public_portfolio_positions SET (security_invoker = true);"
        in sql
    )
    assert "ALTER VIEW public.public_nav_history SET (security_invoker = true);" in sql


def test_does_not_flip_run_health_or_accounting_to_invoker() -> None:
    sql = _sql_body()
    forbidden = (
        "ALTER VIEW public.run_health SET (security_invoker = true)",
        "ALTER VIEW public.run_event_trace SET (security_invoker = true)",
        "ALTER VIEW public.public_finalized_nav SET (security_invoker = true)",
        "ALTER VIEW public.public_daily_realized_attribution SET (security_invoker = true)",
        "ALTER VIEW public.public_accounting_nav_history SET (security_invoker = true)",
        "ALTER VIEW public.public_accounting_period_status SET (security_invoker = true)",
    )
    for stmt in forbidden:
        assert stmt not in sql, f"must keep DEFINER: found {stmt}"


def test_accepted_definer_comments_present() -> None:
    sql = _sql()
    for name in (
        "public_finalized_nav",
        "public_daily_realized_attribution",
        "public_accounting_nav_history",
        "public_accounting_period_status",
        "run_health",
        "run_event_trace",
    ):
        assert f"COMMENT ON VIEW public.{name} IS" in sql
    assert "Accepted SECURITY DEFINER projection (#4630)" in sql


def test_drops_atlas_run_health_compat() -> None:
    assert "DROP VIEW IF EXISTS public.atlas_run_health;" in _sql_body()


def test_pg_net_revokes_api_roles() -> None:
    sql = _sql_body()
    assert "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA net FROM anon;" in sql
    assert "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA net FROM authenticated;" in sql
    assert "REVOKE USAGE ON SCHEMA net FROM anon;" in sql
    assert "REVOKE USAGE ON SCHEMA net FROM authenticated;" in sql
    assert "ALTER EXTENSION" not in sql.upper()
    assert "SET SCHEMA" not in sql.upper()


def test_drops_duplicate_tags_index() -> None:
    assert "DROP INDEX IF EXISTS public.knowledge_notes_tags_idx;" in _sql_body()


def test_does_not_revoke_workspace_rpcs() -> None:
    sql = _sql_body().lower()
    assert "ensure_my_workspace" not in sql
    assert "my_access" not in sql
