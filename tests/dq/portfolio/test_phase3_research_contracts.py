"""Integration Task 3.1 — lock Phase 3 research contracts (#3019).

End-to-end composition gate across WP11–WP14: immutable bundles/amendments,
pinned research state, shadow attention routing, blinded role contexts, H6
selection round floor, and telemetry reconciliation — without planner graph
nodes or runtime policy promotion.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import date

import pytest
from digiquant.olympus.atlas.graph import AtlasGraphDeps, build_atlas_graph
from digiquant.olympus.atlas.phases.preflight import PreflightDeps
from digiquant.olympus.atlas.phases.publish_phase import PublishDeps
from digiquant.olympus.atlas.phases.triage_phase import TriageDeps
from digiquant.olympus.atlas.research_attention import resolve_research_attention_rollout_mode
from digiquant.olympus.atlas.state import AtlasConfigBundle
from digiquant.olympus.hermes.graph import (
    HermesGraphDeps,
    ThesisGraphDeps,
    build_hermes_graph,
    build_hermes_phases_thesis,
)
from digiquant.olympus.hermes.phases.h4_opportunity_screener import compute_focus_roster
from digiquant.olympus.hermes.phases.h9_commit_run import CommitRunDeps
from digiquant.olympus.hermes.phases.phase7e_risk_sizing import RiskSizingDeps
from digiquant.olympus.research_retrieval import (
    assert_blinded_h5_prompt,
    assert_blinded_h6_prompt,
    strip_blinded_forbidden_keys,
)
from digiquant.olympus.research_retrieval.context import ContextRole
from digiquant.olympus.research_retrieval.context_wiring import resolve_context_compiler_mode
from digiquant.olympus.research_retrieval.h7_decision_context import assert_h7_no_target_weights
from digiquant.olympus.research_retrieval.planner import (
    AttentionRolloutMode,
    H6Action,
    H6SelectionMode,
    incumbent_fallback_selection,
    resolve_h6_selection_mode,
)
from digiquant.olympus.research_retrieval.store import EvidenceBundleStore

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient
from tests.dq.hermes.phase3_e2e_fixtures import (
    ATLAS_COMPILED_NODES,
    FORBIDDEN_PHASE3_NODES,
    HERMES_COMPILED_NODES,
    PHASE3_RUN_ID,
    PRODUCTION_GUARD_PATHS,
    assert_research_plan_preserves_h4_roster,
    phase3_attention_plan,
    phase3_h6_selection,
    phase3_pinned_research_state,
    production_imports_enforce_promotion,
    run_phase3_composition,
)

pytestmark = pytest.mark.unit


def _graph_node_names(graph) -> set[str]:
    return set(graph.get_graph().nodes.keys())


# --------------------------------------------------------------------------- topology / no planner node


def test_atlas_graph_topology_unchanged_by_phase3() -> None:
    client = FakeSupabaseClient()
    deps = AtlasGraphDeps(
        preflight=PreflightDeps(
            client=client,
            config_loader=lambda: AtlasConfigBundle(watchlist=["AAPL"]),
        ),
        triage=TriageDeps(client=client),
        publish=PublishDeps(client=client),
    )
    graph = build_atlas_graph(deps=deps, watchlist=("AAPL", "MSFT"))
    nodes = _graph_node_names(graph)
    assert FORBIDDEN_PHASE3_NODES.isdisjoint(nodes)
    assert ATLAS_COMPILED_NODES.issubset(nodes)
    assert "sector-scorecard" not in nodes
    assert "sector-technology" in nodes


def test_hermes_graph_topology_unchanged_by_phase3() -> None:
    client = FakeSupabaseClient()
    deps = HermesGraphDeps(
        thesis=ThesisGraphDeps(client=client),
        risk_sizing=RiskSizingDeps(client=client),
        commit_run=CommitRunDeps(client=client),
    )
    graph = build_hermes_graph(watchlist=["AAPL", "MSFT"], deps=deps)
    nodes = _graph_node_names(graph)
    assert FORBIDDEN_PHASE3_NODES.isdisjoint(nodes)
    assert HERMES_COMPILED_NODES.issubset(nodes)
    phase_names = {p.name for p in build_hermes_phases_thesis(watchlist=["AAPL"], held=set())}
    for expected in (
        "hermes_h1_thesis_review",
        "hermes_h4_opportunity_screener",
        "hermes_h5_asset_analyst",
        "hermes_h6_deliberation",
        "hermes_h7_pm_direction",
        "hermes_h8_risk_sizing",
        "hermes_h9_commit_run",
    ):
        assert expected in phase_names


def test_h6_deliberation_module_disables_broad_live_search() -> None:
    path = (
        pathlib.Path(__file__).resolve().parents[3]
        / "digiquant/src/digiquant/olympus/hermes/phases/h6_deliberation.py"
    )
    source = path.read_text(encoding="utf-8")
    assert "live_search=True" not in source
    assert "live_search=False" in source


def test_planner_helpers_are_not_graph_nodes() -> None:
    """Static guard: research_attention / context_wiring stay helper modules."""
    for rel in (
        "digiquant/src/digiquant/olympus/hermes/research_attention.py",
        "digiquant/src/digiquant/olympus/atlas/research_attention.py",
        "digiquant/src/digiquant/olympus/research_retrieval/context_wiring.py",
    ):
        path = pathlib.Path(__file__).resolve().parents[3] / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.ClassDef) and "Graph" in node.name for node in ast.walk(tree)
        )


# --------------------------------------------------------------------------- H4 width / order / exploration


def test_h4_roster_unchanged_across_shadow_attention_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
    monkeypatch.setenv("HERMES_HELD_GATE", "off")
    roster_a = compute_focus_roster(
        watchlist=["AAPL", "MSFT", "SPY", "QQQ"],
        held={"AAPL"},
        run_date=date(2026, 8, 26),
    )
    roster_b = compute_focus_roster(
        watchlist=["AAPL", "MSFT", "SPY", "QQQ"],
        held={"AAPL"},
        run_date=date(2026, 8, 26),
    )
    tickers_a = [e.ticker for e in roster_a]
    tickers_b = [e.ticker for e in roster_b]
    assert tickers_a == tickers_b

    _, _, loaded = phase3_pinned_research_state()
    plan = phase3_attention_plan(state_version_id=loaded.version.state_version_id, roster=tickers_a)
    assert_research_plan_preserves_h4_roster(plan, tickers_a)


# --------------------------------------------------------------------------- bundles / amendments / replay


def test_phase3_full_fixture_byte_stable_over_serialize_reload() -> None:
    composed = run_phase3_composition()
    again = run_phase3_composition()
    assert composed["plan"] == again["plan"]
    assert composed["original_state_bytes"] == again["original_state_bytes"]
    assert composed["bundle_snapshot"] == again["bundle_snapshot"]
    assert composed["contexts"]["h5_capsule"].content_hash == (
        again["contexts"]["h5_capsule"].content_hash
    )
    assert composed["reloaded_bundles"].lineage_bytes() == composed["bundle_snapshot"]
    assert composed["reloaded_bundles"].unlinked_amendment_count() == 0


def test_base_bundle_content_hash_stable_after_amendment() -> None:
    composed = run_phase3_composition()
    bundle = composed["bundle"]
    reloaded = composed["reloaded_bundles"].load_base_bundle(bundle.bundle_id)
    assert reloaded.content_hash == bundle.content_hash
    assert reloaded == bundle
    assert composed["reloaded_bundles"].amendment_count_for_base(bundle.bundle_id) == 1


def test_exact_state_version_bytes_survive_newer_rows() -> None:
    composed = run_phase3_composition()
    version_id = composed["loaded"].version.state_version_id
    assert (
        composed["state_store"].exact_version_bytes(version_id) == composed["original_state_bytes"]
    )


# --------------------------------------------------------------------------- H6 selection / round floor / provenance


def test_selected_h6_meets_two_round_floor_in_shadow() -> None:
    selected = phase3_h6_selection(conflict=True)
    assert selected.action is H6Action.SELECT
    assert selected.budget.min_rounds >= 2
    assert selected.mode is H6SelectionMode.SHADOW
    assert selected.actuated is False


def test_low_value_carry_records_provenance_without_actuation() -> None:
    carry = phase3_h6_selection(conflict=False, low_value=True)
    assert carry.action is H6Action.CARRY
    assert carry.budget.max_provider_calls == 0
    assert carry.mode is H6SelectionMode.SHADOW
    assert carry.actuated is False


def test_incumbent_fallback_selection_is_typed_and_actuated_false() -> None:
    features = phase3_h6_selection(conflict=True).features
    fallback = incumbent_fallback_selection(features)
    assert fallback.reason.value == "incumbent_fallback"
    assert fallback.actuated is False
    assert fallback.budget.min_rounds >= 2


# --------------------------------------------------------------------------- blinded deterministic contexts


def test_role_contexts_are_blinded_and_h7_has_no_weights() -> None:
    composed = run_phase3_composition()
    wire = composed["contexts"]["h5_wire"]
    h5_inputs = strip_blinded_forbidden_keys(dict(wire.phase_inputs), role=ContextRole.H5_ANALYST)
    assert_blinded_h5_prompt(h5_inputs)
    h6_inputs = {
        "ticker": composed["bundle"].ticker,
        "structured_context": composed["contexts"]["h6_capsule"].body,
    }
    assert_blinded_h6_prompt(h6_inputs)
    h7 = composed["contexts"]["h7"]
    assert_h7_no_target_weights(h7.structured_body)
    assert h7.base_manifest.state_version_id == composed["loaded"].version.state_version_id


def test_h5_h6_manifests_share_pinned_state_version() -> None:
    composed = run_phase3_composition()
    state_id = composed["loaded"].version.state_version_id
    assert composed["contexts"]["h5_manifest"].state_version_id == state_id
    assert composed["contexts"]["h6_manifest"].state_version_id == state_id
    assert composed["contexts"]["h7"].base_manifest.state_version_id == state_id


# --------------------------------------------------------------------------- telemetry reconciliation


def test_pre_call_manifest_links_wp1_tokens_without_mutation() -> None:
    composed = run_phase3_composition()
    link = composed["telemetry"]
    manifest = composed["contexts"]["h5_manifest"]
    assert link.manifest_id == manifest.manifest_id
    assert link.actual_prompt_tokens == 900
    assert manifest.estimated_tokens is not None


# --------------------------------------------------------------------------- shadow defaults / no promotion


def test_default_rollout_modes_are_shadow_not_enforce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OLYMPUS_RESEARCH_ATTENTION_MODE", raising=False)
    monkeypatch.delenv("OLYMPUS_CONTEXT_COMPILER_MODE", raising=False)
    monkeypatch.delenv("OLYMPUS_H6_SELECTION_MODE", raising=False)
    assert resolve_research_attention_rollout_mode() is AttentionRolloutMode.SHADOW
    assert resolve_context_compiler_mode().value == "shadow"
    assert resolve_h6_selection_mode() is H6SelectionMode.SHADOW


def test_production_surfaces_do_not_import_policy_promotion() -> None:
    for path in PRODUCTION_GUARD_PATHS:
        hits = production_imports_enforce_promotion(path)
        assert hits == [], f"{path.name} imports promotion modules: {hits}"


def test_attention_plan_shadow_never_actuates() -> None:
    _, _, loaded = phase3_pinned_research_state()
    plan = phase3_attention_plan(state_version_id=loaded.version.state_version_id)
    assert plan.rollout_mode is AttentionRolloutMode.SHADOW
    assert plan.actuated is False
    assert plan.run_id == PHASE3_RUN_ID


def test_evidence_bundle_snapshot_matches_pipeline_reload_contract() -> None:
    composed = run_phase3_composition()
    roundtrip = EvidenceBundleStore.from_snapshot(composed["bundle_snapshot"])
    assert roundtrip.lineage_bytes() == composed["bundle_snapshot"]
    assert roundtrip.lineage_bytes() == composed["reloaded_bundles"].lineage_bytes()
