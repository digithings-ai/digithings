"""Pins for migration 129 — the anon read-surface tightening (#4115).

The migration revokes anon SELECT on the relations nobody reads and drops the
two policies that only widen the public surface. These tests pin the exact
statements, the idempotent policy form, and — just as importantly — that the
migration does NOT touch the surfaces the dashboard renders for anon users
(the security_invoker attribution chain, every public_* view, the
browser-read tables).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "digiquant" / "supabase" / "migrations" / "129_tighten_anon_read.sql"

# (table, policy) pairs whose anon policy is dropped idempotently.
REVOKED_POLICIES: tuple[tuple[str, str], ...] = (
    ("architecture_notes", "architecture_notes_anon_select"),
    ("onchain_cohort_positioning", "onchain_cohort_positioning_anon_select"),
    ("trading_calendar", "trading_calendar_anon_select"),
    ("knowledge_notes", "knowledge_notes_read"),
)

REVOKED_GRANTS: tuple[str, ...] = (
    "architecture_notes",
    "onchain_cohort_positioning",
    "trading_calendar",
    "olympus_position_events",
    "olympus_position_events_authoritative",
    "atlas_run_diagnostics",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
    "strategy_calibrations",
)

# Surfaces the dashboard (or the deliberate anon read-model) still reads.
KEPT: tuple[str, ...] = (
    "current_book_lookback",
    "position_attribution",
    "atlas_run_health",
    "olympus_run_event_trace",
    "analyst_coverage",
    "daily_snapshots",
    "decision_log",
    "documents",
    "economic_calendar",
    "instruments",
    "macro_series_observations",
    "nav_history",
    "portfolio_metrics",
    "position_events",
    "positions",
    "prices_live",
    "strategy_tearsheets",
    "theses",
    "thesis_vehicles",
)


def _statements() -> list[str]:
    sql = MIGRATION.read_text(encoding="utf-8")
    return [
        line.strip()
        for line in sql.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]


def test_migration_129_exists() -> None:
    assert MIGRATION.is_file(), "129_tighten_anon_read.sql is missing"


def test_every_revoked_policy_drops_idempotently() -> None:
    statements = _statements()
    for table, policy in REVOKED_POLICIES:
        expected = f"DROP POLICY IF EXISTS {policy} ON public.{table};"
        assert expected in statements, f"missing: {expected}"


def test_every_revoked_grant_targets_anon() -> None:
    statements = _statements()
    for relation in REVOKED_GRANTS:
        expected = f"REVOKE SELECT ON public.{relation} FROM anon;"
        assert expected in statements, f"missing: {expected}"


def test_only_anon_loses_access() -> None:
    joined = "\n".join(_statements())
    assert "authenticated" not in joined, "migration 129 must not touch authenticated grants"
    assert "GRANT" not in joined.upper(), "migration 129 is a tightening — no new grants"


def test_kept_surfaces_are_untouched() -> None:
    joined = "\n".join(_statements())
    for relation in KEPT:
        assert re.search(rf"\b{relation}\b", joined) is None, (
            f"migration 129 must not touch the kept surface {relation!r}"
        )
