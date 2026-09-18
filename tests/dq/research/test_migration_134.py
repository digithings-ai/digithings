"""Unit tests for migration 134 — Phase B olympus_* rename (#4295 gap G5).

Migration 134 reverses migration 132: it drops the Phase-A new-name views,
renames every ``olympus_*`` base object to its stripped name, and recreates the
old names as compatibility views so any pre-approval old-name code keeps
working. These tests pin the safety properties the design depends on:

* every base table is renamed exactly once, and no table is dropped;
* every recreated old-name base view is ``security_invoker = true`` (a definer
  view would bypass base-table RLS — the documented ``atlas_run_health`` defect);
* the three pre-existing views keep their original ``security_invoker`` setting;
* ``olympus_position_events`` maps to ``position_events_labeled`` (``position_events``
  is a base table since migration 001);
* the 15 ``reject_olympus_*()`` functions, 64 standalone indexes, 97 named
  constraints and 93 triggers are renamed by prefix strip;
* grants are re-issued on the old names, and no old-name view is ever granted
  UPDATE/DELETE/TRUNCATE;
* the file never touches the ``olympus_schema_migrations`` ledger and is not
  self-wrapped in a transaction.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
M134 = MIGRATIONS_DIR / "134_rename_phase_b_olympus_objects.sql"

SELF_WRAP_REGEX = re.compile(r"(^|[\s])(begin|commit)[\s]*;", re.IGNORECASE)

# The 47 base tables being renamed (new name -> old olympus_ name).
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

# The 3 pre-existing views (old name -> (new name, original invoker setting)).
VIEW_SOURCES = {
    "olympus_run_event_trace": ("run_event_trace", "false"),
    "olympus_position_events": ("position_events_labeled", "true"),
    "olympus_position_events_authoritative": ("position_events_authoritative", "true"),
}

AUTHENTICATED_SELECT = {
    "accounting_periods",
    "accounting_contributions",
    "accounting_holdings",
    "profile_config",
}

FUNCTIONS = {
    "reject_accounting_mutation": "reject_olympus_accounting_mutation",
    "reject_attention_context_mutation": "reject_olympus_attention_context_mutation",
    "reject_cost_liquidity_mutation": "reject_olympus_cost_liquidity_mutation",
    "reject_evidence_amendment_base_mismatch": "reject_olympus_evidence_amendment_base_mismatch",
    "reject_evidence_bundle_mutation": "reject_olympus_evidence_bundle_mutation",
    "reject_forecast_calibration_mutation": "reject_olympus_forecast_calibration_mutation",
    "reject_forecast_registry_mutation": "reject_olympus_forecast_registry_mutation",
    "reject_outcome_learning_mutation": "reject_olympus_outcome_learning_mutation",
    "reject_policy_replay_mutation": "reject_olympus_policy_replay_mutation",
    "reject_pretrade_risk_report_mutation": "reject_olympus_pretrade_risk_report_mutation",
    "reject_profile_config_mutation": "reject_olympus_profile_config_mutation",
    "reject_provider_telemetry_mutation": "reject_olympus_provider_telemetry_mutation",
    "reject_research_corpus_mutation": "reject_olympus_research_corpus_mutation",
    "reject_research_state_mutation": "reject_olympus_research_state_mutation",
    "reject_risk_policy_snapshot_mutation": "reject_olympus_risk_policy_snapshot_mutation",
}

EXPECTED_INDEX_RENAMES = 64
EXPECTED_CONSTRAINT_RENAMES = 97
EXPECTED_TRIGGER_RENAMES = 93

RENAME_TABLE_RE = re.compile(r"ALTER TABLE public\.(olympus_[a-z0-9_]+) RENAME TO ([a-z0-9_]+);")
DROP_VIEW_RE = re.compile(r"DROP VIEW IF EXISTS public\.([a-z0-9_]+);")
BASE_VIEW_RE = re.compile(
    r"CREATE VIEW public\.(olympus_[a-z0-9_]+) WITH \(security_invoker = (true|false)\) AS\s+"
    r"SELECT \* FROM public\.([a-z0-9_]+);"
)
RENAME_FUNCTION_RE = re.compile(
    r"ALTER FUNCTION public\.(reject_olympus_[a-z0-9_]+)\(\) RENAME TO ([a-z0-9_]+);"
)
RENAME_INDEX_RE = re.compile(r"ALTER INDEX public\.([a-z0-9_]+) RENAME TO ([a-z0-9_]+);")
RENAME_CONSTRAINT_RE = re.compile(
    r"ALTER TABLE public\.([a-z0-9_]+) RENAME CONSTRAINT ([a-z0-9_]+) TO ([a-z0-9_]+);"
)
RENAME_TRIGGER_RE = re.compile(
    r"ALTER TRIGGER ([a-z0-9_]+) ON public\.([a-z0-9_]+) RENAME TO ([a-z0-9_]+);"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert M134.is_file(), f"missing {M134.name}"
    return M134.read_text()


def test_renames_every_base_table_exactly_once(sql: str) -> None:
    renames = {old: new for old, new in RENAME_TABLE_RE.findall(sql)}
    assert len(RENAME_TABLE_RE.findall(sql)) == len(BASE_TABLES)
    assert renames == {old: new for new, old in BASE_TABLES.items()}


def test_drops_the_phase_a_views(sql: str) -> None:
    dropped = set(DROP_VIEW_RE.findall(sql))
    expected = set(BASE_TABLES) | {new for new, _ in VIEW_SOURCES.values()}
    assert expected <= dropped
    assert "DROP VIEW IF EXISTS public.position_events;" not in sql


def test_never_drops_a_table(sql: str) -> None:
    assert "drop table" not in sql.lower()


def test_recreates_base_views_as_single_table_security_invoker(sql: str) -> None:
    views = {name: (invoker, source) for name, invoker, source in BASE_VIEW_RE.findall(sql)}
    for new, old in BASE_TABLES.items():
        assert old in views, old
        assert views[old] == ("true", new), old
    assert len(views) == len(BASE_TABLES)


def test_existing_views_keep_original_invoker_setting(sql: str) -> None:
    created = dict(
        (m.group(1), m.group(2))
        for m in re.finditer(
            r"CREATE VIEW public\.(olympus_[a-z0-9_]+) "
            r"WITH \(security_invoker = (true|false)\) AS",
            sql,
        )
    )
    for old, (_new, invoker) in VIEW_SOURCES.items():
        assert created[old] == invoker, old


def test_position_events_collision_uses_labeled_name(sql: str) -> None:
    assert "ALTER VIEW public.olympus_position_events RENAME TO position_events_labeled;" in sql
    assert "RENAME TO position_events;" not in sql
    assert "CREATE VIEW public.position_events " not in sql


def test_renames_all_trigger_functions(sql: str) -> None:
    renames = dict(RENAME_FUNCTION_RE.findall(sql))
    assert renames == {old: new for new, old in FUNCTIONS.items()}


def test_renames_indexes_constraints_and_triggers(sql: str) -> None:
    index_renames = RENAME_INDEX_RE.findall(sql)
    assert len(index_renames) == EXPECTED_INDEX_RENAMES
    constraint_renames = RENAME_CONSTRAINT_RE.findall(sql)
    assert len(constraint_renames) == EXPECTED_CONSTRAINT_RENAMES
    trigger_renames = RENAME_TRIGGER_RE.findall(sql)
    assert len(trigger_renames) == EXPECTED_TRIGGER_RENAMES

    for old, _new in index_renames + [(o, n) for _t, o, n in constraint_renames]:
        assert "olympus" in old
    for _table, old, _new in constraint_renames:
        assert "olympus" in old
    for old, _table, _new in trigger_renames:
        assert "olympus" in old

    # Every target name is the source with a single `olympus_` strip.
    for old, new in index_renames:
        assert new == old.replace("olympus_", "", 1)
    for _table, old, new in constraint_renames:
        assert new == old.replace("olympus_", "", 1)
    for old, _table, new in trigger_renames:
        assert new == old.replace("olympus_", "", 1)


def test_never_touches_the_ledger(sql: str) -> None:
    lowered = sql.lower()
    for ledger in ("olympus_schema_migrations", "schema_migrations"):
        assert f"insert into {ledger}" not in lowered
        assert f"alter table {ledger}" not in lowered
        assert f"alter table public.{ledger}" not in lowered
        assert f"drop table {ledger}" not in lowered
        assert f"rename to {ledger}" not in lowered
        assert f"alter index {ledger}" not in lowered
        assert f"on public.{ledger}" not in lowered


def test_no_self_wrapping_transaction(sql: str) -> None:
    assert not SELF_WRAP_REGEX.search(sql)


def test_grant_union_on_recreated_old_name_views(sql: str) -> None:
    for new, old in BASE_TABLES.items():
        assert (
            f"REVOKE ALL ON public.{old} FROM PUBLIC, anon, authenticated, service_role;" in sql
        ), old
        assert f"GRANT SELECT, INSERT ON public.{old} TO service_role;" in sql, old
        if new in AUTHENTICATED_SELECT:
            assert f"GRANT SELECT ON public.{old} TO authenticated;" in sql, old

    assert (
        "GRANT SELECT ON public.olympus_run_event_trace TO anon, authenticated, service_role;"
        in sql
    )
    for old in ("olympus_position_events", "olympus_position_events_authoritative"):
        assert f"GRANT SELECT ON public.{old} TO authenticated, service_role;" in sql, old


def test_never_grants_mutations_on_old_name_views(sql: str) -> None:
    forbidden = re.compile(
        r"GRANT[^\n]*\b(UPDATE|DELETE|TRUNCATE)\b[^\n]*\bON public\.olympus_[a-z0-9_]+",
        re.IGNORECASE,
    )
    assert not forbidden.search(sql)


def test_old_name_base_views_are_select_star_auto_updatable(sql: str) -> None:
    # A single-table `SELECT *` view is auto-updatable; assert no join/where on
    # the 47 base-table compatibility views (they must remain writable).
    for old in BASE_TABLES.values():
        match = re.search(
            rf"CREATE VIEW public\.{old} WITH \(security_invoker = true\) AS\s+"
            r"SELECT \* FROM public\.[a-z0-9_]+;",
            sql,
        )
        assert match, old
