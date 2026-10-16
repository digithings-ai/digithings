"""Unit tests for migration 132 — Phase A olympus_* compat views (#4295 gap G5).

Migration 132 is ADDITIVE: it creates new-name compatibility views over the
existing ``olympus_*`` objects and never renames, alters, or drops them. These
tests pin the safety properties the Phase A design depends on:

* every base-table compat view is ``security_invoker = true`` (a definer view
  would bypass base-table RLS — the documented ``atlas_run_health`` defect);
* the three pre-existing views keep their original ``security_invoker`` setting;
* ``olympus_position_events`` maps to ``position_events_labeled`` (the name
  ``position_events`` is a base table since migration 001);
* grants mirror the current effective state, including the anon tightening from
  ``129_tighten_anon_read.sql``;
* the file is additive-only, self-wrap free, and never touches the ledger.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
M132 = MIGRATIONS_DIR / "132_rename_phase_a_compat_views.sql"

SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)

VIEW_RE = re.compile(
    r"CREATE OR REPLACE VIEW public\.(?P<name>[a-z0-9_]+) "
    r"WITH \(security_invoker = (?P<invoker>true|false)\) AS\s+"
    r"SELECT \* FROM public\.(?P<source>[a-z0-9_]+);",
    re.IGNORECASE,
)

# The 47 base tables being aliased (new name -> old olympus_ name).
BASE_TABLES = {
    "run_events": "olympus_run_events",
    "node_runs": "olympus_node_runs",
    "provider_calls": "olympus_provider_calls",
    "provider_attempts": "olympus_provider_attempts",
    "accounting_periods": "olympus_accounting_periods",
    "accounting_contributions": "olympus_accounting_contributions",
    "accounting_holdings": "olympus_accounting_holdings",
    "profile_config": "olympus_profile_config",
    "research_corpus": "olympus_research_corpus",
    "forecast_assessments": "olympus_forecast_assessments",
    "forecast_amendments": "olympus_forecast_amendments",
    "forecast_outcomes": "olympus_forecast_outcomes",
    "forecast_calibrations": "olympus_forecast_calibrations",
    "calibrated_forecasts": "olympus_calibrated_forecasts",
    "risk_policies": "olympus_risk_policies",
    "covariance_snapshots": "olympus_covariance_snapshots",
    "h8_risk_run_refs": "olympus_h8_risk_run_refs",
    "liquidity_snapshots": "olympus_liquidity_snapshots",
    "action_cost_estimates": "olympus_action_cost_estimates",
    "action_cost_outcomes": "olympus_action_cost_outcomes",
    "pretrade_risk_reports": "olympus_pretrade_risk_reports",
    "research_evidence": "olympus_research_evidence",
    "research_belief_versions": "olympus_research_belief_versions",
    "research_expected_event_versions": "olympus_research_expected_event_versions",
    "research_patches": "olympus_research_patches",
    "research_legacy_refs": "olympus_research_legacy_refs",
    "research_state_versions": "olympus_research_state_versions",
    "research_state_pins": "olympus_research_state_pins",
    "ticker_evidence_bundles": "olympus_ticker_evidence_bundles",
    "missing_fact_requests": "olympus_missing_fact_requests",
    "evidence_bundle_amendments": "olympus_evidence_bundle_amendments",
    "attention_plans": "olympus_attention_plans",
    "attention_decisions": "olympus_attention_decisions",
    "attention_decision_attempts": "olympus_attention_decision_attempts",
    "attention_context_manifests": "olympus_attention_context_manifests",
    "attention_policy_evaluations": "olympus_attention_policy_evaluations",
    "outcome_episodes": "olympus_outcome_episodes",
    "component_attribution_reports": "olympus_component_attribution_reports",
    "outcome_lesson_versions": "olympus_outcome_lesson_versions",
    "replay_input_manifests": "olympus_replay_input_manifests",
    "replay_pairs": "olympus_replay_pairs",
    "replay_run_events": "olympus_replay_run_events",
    "replay_arm_results": "olympus_replay_arm_results",
    "policy_comparison_reports": "olympus_policy_comparison_reports",
    "gate_criteria_versions": "olympus_gate_criteria_versions",
    "gate_evaluations": "olympus_gate_evaluations",
    "policy_governance_decisions": "olympus_policy_governance_decisions",
}

# The 3 pre-existing views (new name -> old olympus_ name, original invoker setting).
VIEW_SOURCES = {
    "run_event_trace": ("olympus_run_event_trace", "false"),
    "position_events_labeled": ("olympus_position_events", "true"),
    "position_events_authoritative": ("olympus_position_events_authoritative", "true"),
}

AUTHENTICATED_SELECT = {
    "accounting_periods",
    "accounting_contributions",
    "accounting_holdings",
    "profile_config",
}


@pytest.fixture(scope="module")
def sql() -> str:
    assert M132.is_file(), f"missing {M132.name}"
    return M132.read_text()


@pytest.fixture(scope="module")
def views(sql: str) -> dict[str, str]:
    return {m.group("name"): m.group("invoker") for m in VIEW_RE.finditer(sql)}


def test_creates_every_expected_view(views: dict[str, str]) -> None:
    assert set(views) == set(BASE_TABLES) | set(VIEW_SOURCES)


def test_base_table_views_are_security_invoker(views: dict[str, str]) -> None:
    assert all(views[name] == "true" for name in BASE_TABLES)


def test_existing_views_keep_original_invoker_setting(views: dict[str, str]) -> None:
    for new, (_old, invoker) in VIEW_SOURCES.items():
        assert views[new] == invoker, new


def test_position_events_collision_uses_labeled_name() -> None:
    body = M132.read_text()
    assert "CREATE OR REPLACE VIEW public.position_events_labeled" in body
    assert "CREATE OR REPLACE VIEW public.position_events " not in body


def test_sources_are_the_expected_olympus_objects(sql: str) -> None:
    sources = {m.group("source") for m in VIEW_RE.finditer(sql)}
    expected = set(BASE_TABLES.values()) | {src for src, _ in VIEW_SOURCES.values()}
    assert sources == expected


def test_is_additive_only(sql: str) -> None:
    lowered = sql.lower()
    assert "alter table" not in lowered
    assert "alter view" not in lowered
    assert "drop view" not in lowered
    assert "drop table" not in lowered
    assert "rename to" not in lowered


def test_no_self_wrapping_transaction(sql: str) -> None:
    assert not SELF_WRAP_REGEX.search(sql)


def test_never_touches_the_ledger(sql: str) -> None:
    lowered = sql.lower()
    for new_name in ("olympus_schema_migrations", "schema_migrations"):
        assert f"insert into {new_name}" not in lowered
        assert f"alter table {new_name}" not in lowered
        assert f"alter table public.{new_name}" not in lowered
        assert f"drop table {new_name}" not in lowered
        assert f"rename to {new_name}" not in lowered


def test_every_view_revokes_all_and_gets_service_role_select_insert(sql: str) -> None:
    for name in set(BASE_TABLES) - {"run_events"}:
        revoke = f"REVOKE ALL ON public.{name} FROM PUBLIC, anon, authenticated, service_role;"
        assert revoke in sql, name
        grant = f"GRANT SELECT, INSERT ON public.{name} TO service_role;"
        assert grant in sql, name
    assert "REVOKE ALL ON public.run_events FROM PUBLIC, anon, authenticated, service_role;" in sql


def test_run_events_also_gets_service_role_delete(sql: str) -> None:
    assert "GRANT SELECT, INSERT, DELETE ON public.run_events TO service_role;" in sql


def test_authenticated_select_matches_migration_098_posture(sql: str) -> None:
    for name in AUTHENTICATED_SELECT:
        assert f"GRANT SELECT ON public.{name} TO authenticated;" in sql, name
    # No other base table grants authenticated SELECT; the two position projections do.
    granted = set(re.findall(r"GRANT SELECT ON public\.([a-z0-9_]+) TO authenticated", sql))
    assert granted == AUTHENTICATED_SELECT | {
        "position_events_labeled",
        "position_events_authoritative",
    }
    assert "GRANT SELECT ON public.run_event_trace TO anon, authenticated, service_role;" in sql


def test_anon_read_surface_matches_tighten_anon_read_129(sql: str) -> None:
    # run_event_trace keeps its curated anon read...
    assert "GRANT SELECT ON public.run_event_trace TO anon, authenticated, service_role;" in sql
    # ...but the two position_events projections lost anon in 129.
    for name in ("position_events_labeled", "position_events_authoritative"):
        assert f"GRANT SELECT ON public.{name} TO authenticated, service_role;" in sql, name
        assert "TO anon" not in _grant_line(sql, name)
    # anon appears on no base-table view.
    for name in BASE_TABLES:
        assert "TO anon" not in _grant_line(sql, name), name


def _grant_line(sql: str, name: str) -> str:
    match = re.search(rf"GRANT[^\n]*\bON public\.{name}\b[^\n]*", sql)
    assert match, name
    return match.group(0)
