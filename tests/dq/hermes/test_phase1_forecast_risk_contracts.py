"""Integration Task 1.1 — lock Phase 1 forecast/risk/cost contracts (#2713).

End-to-end composition gate: Phase 1 registries attach observational artifacts
without forking graph topology or changing incumbent H8 sized-book economics.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from digiquant.olympus.atlas.graph import AtlasGraphDeps, build_atlas_graph
from digiquant.olympus.atlas.phases.preflight import PreflightDeps, PreflightReflectDeps
from digiquant.olympus.atlas.phases.publish_phase import PublishDeps
from digiquant.olympus.atlas.phases.triage_phase import TriageDeps
from digiquant.olympus.atlas.state import AtlasConfigBundle
from digiquant.olympus.hermes.graph import (
    HermesGraphDeps,
    ThesisGraphDeps,
    build_hermes_graph,
    build_hermes_phases_thesis,
)
from digiquant.olympus.hermes.phases.h9_commit_run import CommitRunDeps, _manifest_payload
from digiquant.olympus.hermes.phases.phase7e_risk_sizing import RiskSizingDeps
from digiquant.olympus.hermes.sizing import TickerRisk, size_portfolio

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient
from tests.dq.hermes.incumbent_risk_fixtures import (
    assert_book_matches_golden,
    load_incumbent_risk_fixture,
    sizing_result_snapshot,
)

pytestmark = pytest.mark.unit

_FORBIDDEN_PHASE1_NODES = frozenset(
    {
        "forecast-calibration",
        "forecast-calibrator",
        "cost-liquidity",
        "cost-resolver",
        "risk-policy-resolver",
        "covariance-resolver",
    }
)

_HERMES_COMPILED_NODES = frozenset(
    {
        "hermes/thesis/market-review",
        "hermes/thesis/market-exploration",
        "hermes/thesis/vehicle-map",
        "hermes/thesis/opportunity-screener",
        "hermes/portfolio/asset-analyst-worker",
        "hermes/portfolio/deliberation-worker",
        "hermes/portfolio/pm-direction",
        "hermes/portfolio/risk-sizing",
        "hermes/portfolio/commit-run",
    }
)

_ATLAS_COMPILED_NODES = frozenset(
    {
        "preflight",
        "triage",
        "alt-sentiment-news",
        "alt-cta-positioning",
        "inst-institutional-flows",
        "macro",
        "bonds",
        "crypto",
        "equity",
        "sector-technology",
        "sector-scorecard",
        "consolidate",
        "master-digest",
    }
)


def _graph_node_names(graph) -> set[str]:
    return set(graph.get_graph().nodes.keys())


def test_hermes_graph_topology_unchanged_by_phase1() -> None:
    client = FakeSupabaseClient()
    deps = HermesGraphDeps(
        thesis=ThesisGraphDeps(client=client),
        risk_sizing=RiskSizingDeps(client=client),
        commit_run=CommitRunDeps(client=client),
    )
    graph = build_hermes_graph(watchlist=["AAPL"], deps=deps)
    nodes = _graph_node_names(graph)
    assert _FORBIDDEN_PHASE1_NODES.isdisjoint(nodes)
    assert _HERMES_COMPILED_NODES.issubset(nodes)
    phase_names = {p.name for p in build_hermes_phases_thesis(watchlist=["AAPL"], held=set())}
    for expected in (
        "hermes_h1_thesis_review",
        "hermes_h7_pm_direction",
        "hermes_h8_risk_sizing",
        "hermes_h9_commit_run",
    ):
        assert expected in phase_names


def test_atlas_graph_topology_unchanged_by_phase1() -> None:
    client = FakeSupabaseClient()
    deps = AtlasGraphDeps(
        preflight=PreflightDeps(
            client=client,
            config_loader=lambda: AtlasConfigBundle(watchlist=["AAPL"]),
        ),
        preflight_reflect=PreflightReflectDeps(client=client),
        triage=TriageDeps(client=client),
        publish=PublishDeps(client=client),
    )
    graph = build_atlas_graph(deps=deps, watchlist=("AAPL",))
    nodes = _graph_node_names(graph)
    assert _FORBIDDEN_PHASE1_NODES.isdisjoint(nodes)
    assert _ATLAS_COMPILED_NODES.issubset(nodes)
    for forbidden in (
        "technical-analyst-AAPL",
        "pm-rebalance",
        "forecast-calibration",
    ):
        assert forbidden not in nodes


def test_h9_manifest_carries_phase1_registry_fields() -> None:
    manifest = _manifest_payload(
        source_run_id="run-test",
        status="committed",
        weights={"SPY": 50.0, "CASH": 50.0},
        forecast_registry={"forecast_registry_status": "ok"},
        risk_policy_registry={"risk_policy_registry_status": "ok"},
        cost_liquidity_registry={"cost_liquidity_registry_status": "ok"},
    )
    assert manifest["schema_version"] == "1.5"
    assert manifest["forecast_registry_status"] == "ok"
    assert manifest["risk_policy_registry_status"] == "ok"
    assert manifest["cost_liquidity_registry_status"] == "ok"


def test_incumbent_sized_book_golden_unchanged_in_phase1() -> None:
    golden = load_incumbent_risk_fixture()["representative_books"]["default_caps_equity_bond"]
    result = size_portfolio(
        convictions={"SPY": 4.0, "TLT": 4.0},
        stances={"SPY": "buy", "TLT": "buy"},
        risk={
            "SPY": TickerRisk("SPY", hist_vol_21=20.0, sector="broad", asset_class="EQUITY"),
            "TLT": TickerRisk("TLT", hist_vol_21=8.0, sector="bonds", asset_class="FIXED_INCOME"),
        },
    )
    assert_book_matches_golden(sizing_result_snapshot(result), golden)


def test_phase1_registry_modules_export_cutoff_reads() -> None:
    from digiquant.olympus.atlas import cost_liquidity_registry as clr
    from digiquant.olympus.atlas import forecast_registry as fr
    from digiquant.olympus.atlas import risk_policy_registry as rpr

    cutoff = datetime(2026, 8, 25, 16, 0, tzinfo=UTC)
    client = FakeSupabaseClient()
    missing = UUID("00000000-0000-4000-8000-000000000001")

    assert (
        fr.get_forecast_assessment(client=client, forecast_id=missing, knowledge_cutoff_at=cutoff)
        is None
    )
    assert rpr.get_risk_policy(client=client, policy_id=missing, knowledge_cutoff_at=cutoff) is None
    assert (
        clr.get_action_cost_estimate(
            client=client, estimate_id=missing, knowledge_cutoff_at=cutoff
        )
        is None
    )


def test_knowledge_cutoff_bounds_cost_estimate_visibility() -> None:
    from digiquant.olympus.atlas import cost_liquidity_registry as clr

    from tests.dq.atlas.test_cost_liquidity_registry import CostRegistryFake, _bundle

    client = CostRegistryFake()
    bundle = _bundle()
    clr.persist_cost_liquidity_bundle(client=client, bundle=bundle)

    visible = clr.get_action_cost_estimate(
        client=client,
        estimate_id=bundle.estimate.estimate_id,
        knowledge_cutoff_at=bundle.estimate.effective_at + timedelta(hours=1),
    )
    hidden = clr.get_action_cost_estimate(
        client=client,
        estimate_id=bundle.estimate.estimate_id,
        knowledge_cutoff_at=bundle.estimate.effective_at - timedelta(hours=1),
    )
    assert visible is not None
    assert hidden is None
