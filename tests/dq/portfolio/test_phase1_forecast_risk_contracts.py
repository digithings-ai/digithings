"""Integration Task 1.1 — lock Phase 1 forecast/risk/cost contracts (#2713, #2719).

End-to-end composition gate: Phase 1 registries attach observational artifacts
without forking graph topology. H8 still books once; size follows canned H7
confidence (simulator default 0.7 → 70% AAPL, leftover stays cash).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID

import pytest
from digiquant.research import cost_liquidity_registry as clr
from digiquant.research import forecast_registry as fr
from digiquant.research import risk_policy_registry as rpr
from digiquant.research.graph import AtlasGraphDeps, AtlasInput, build_atlas_graph
from digiquant.research.phases.preflight import PreflightDeps, PreflightReflectDeps
from digiquant.research.phases.publish_phase import PublishDeps
from digiquant.research.phases.triage_phase import TriageDeps
from digiquant.research.state import AtlasConfigBundle, AtlasResearchState, PhaseHermesState
from digiquant.research.testing.simulator import simulated_pipeline
from digiquant.portfolio.graph import (
    HermesGraphDeps,
    ThesisGraphDeps,
    build_hermes_graph,
    build_hermes_phases_thesis,
)
from digiquant.portfolio.models.forecast import (
    AmendmentOutcome,
    ForecastTerms,
    PriceAnchor,
    PriceAnchorStatus,
)
from digiquant.portfolio.models.forecast_calibration import CalibrationArtifactStatus
from digiquant.portfolio.models.risk_policy import PolicyArtifactStatus
from digiquant.portfolio.phases.h6_deliberation import _resolve_from_debate
from digiquant.portfolio.phases.h9_commit_run import CommitRunDeps, _manifest_payload
from digiquant.portfolio.phases.phase7e_risk_sizing import RiskSizingDeps
from digiquant.portfolio.phases.portfolio_common import materialize_forecast_assessment
from digiquant.portfolio.sizing import TickerRisk, size_portfolio

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
    assert "sector-scorecard" not in nodes
    assert "sector-technology" in nodes
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
        pretrade_risk_registry={"pretrade_risk_registry_status": "shadow_invalid"},
    )
    assert manifest["schema_version"] == "1.6"
    assert manifest["forecast_registry_status"] == "ok"
    assert manifest["risk_policy_registry_status"] == "ok"
    assert manifest["cost_liquidity_registry_status"] == "ok"
    assert manifest["pretrade_risk_registry_status"] == "shadow_invalid"


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
    from digiquant.research import cost_liquidity_registry as clr
    from digiquant.research import forecast_registry as fr
    from digiquant.research import risk_policy_registry as rpr

    cutoff = datetime(2026, 8, 25, 16, 0, tzinfo=UTC)
    client = FakeSupabaseClient()
    missing = UUID("00000000-0000-4000-8000-000000000001")

    assert (
        fr.get_forecast_assessment(client=client, forecast_id=missing, knowledge_cutoff_at=cutoff)
        is None
    )
    assert rpr.get_risk_policy(client=client, policy_id=missing, knowledge_cutoff_at=cutoff) is None
    assert (
        clr.get_action_cost_estimate(client=client, estimate_id=missing, knowledge_cutoff_at=cutoff)
        is None
    )


def test_knowledge_cutoff_bounds_cost_estimate_visibility() -> None:
    from digiquant.research import cost_liquidity_registry as clr

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


def _run_phase1_pipeline(*, canned_extras: dict | None = None, overrides: dict | None = None):
    from tests.dq.hermes.phase1_e2e_fixtures import (
        PHASE1_PIPELINE_PREFERENCES,
        PHASE1_RUN_DATE,
        analyst_payload_override,
        seed_phase1_client,
    )

    extras = dict(canned_extras or {})
    merged_overrides = {"AnalystPayload": analyst_payload_override, **(overrides or {})}
    with patch(
        "digiquant.research.testing.simulator.seed_supabase_client",
        side_effect=seed_phase1_client,
    ):
        with simulated_pipeline(
            watchlist=("AAPL",),
            overrides=merged_overrides,
            canned_extras=extras,
            preferences=PHASE1_PIPELINE_PREFERENCES,
        ) as run:
            final = run.invoke(
                AtlasInput(run_date=PHASE1_RUN_DATE, watchlist=("AAPL",)),
            )
            return final, run


def test_phase1_composition_e2e_simulated_pipeline() -> None:
    """Full graph: registries populated, H7 lineage, H8/H9 observational artifacts, book once."""
    from tests.dq.hermes.phase1_e2e_fixtures import (
        LATE_KNOWN_AT,
        mature_cohort_outcome_rows,
        resolved_outcome_row,
        sized_book_weights,
    )

    final, run = _run_phase1_pipeline(
        canned_extras={
            "olympus_forecast_outcomes": [
                *mature_cohort_outcome_rows(count=3),
                resolved_outcome_row(salt=99, known_at=LATE_KNOWN_AT),
            ],
        },
    )
    hermes = final.phase_hermes
    manifest = hermes.commit_manifest or {}

    assert final.knowledge_cutoff_at is not None
    assert hermes.pm_direction_memo is not None
    for row in hermes.pm_direction_memo.roster:
        assert row.forecast_reference is not None
        assert row.forecast_reference.effective_forecast_id is not None
        assert row.forecast_reference.base_forecast_id is not None
        assert row.forecast_reference.ticker == row.ticker

    assert hermes.forecast_calibrations
    assert hermes.calibrated_forecasts
    cal = next(iter(hermes.forecast_calibrations.values()))
    assert cal["status"] == CalibrationArtifactStatus.AVAILABLE.value
    assert int(cal["sample_count"]) >= 3

    assert hermes.risk_policy is not None
    assert hermes.covariance_snapshot is not None
    assert hermes.risk_policy["status"] in (
        PolicyArtifactStatus.AVAILABLE.value,
        PolicyArtifactStatus.DEGRADED.value,
    )

    assert manifest["schema_version"] == "1.6"
    assert manifest["status"] == "committed"
    assert manifest["forecast_registry_status"] == "ok"
    assert manifest["risk_policy_registry_status"] == "ok"
    assert manifest["cost_liquidity_registry_status"] == "ok"
    assert manifest["pretrade_risk_registry_status"] in (
        "ok",
        "shadow_invalid",
        "skipped",
        "degraded",
    )
    assert manifest["forecast_registry_assessments_written"] >= 1
    assert manifest["risk_policy_registry_run_refs_written"] == 1
    assert manifest["cost_liquidity_registry_estimates_written"] >= 1

    assert len(run.client.store.get("olympus_forecast_assessments", [])) >= 1
    assert len(run.client.store.get("olympus_h8_risk_run_refs", [])) == 1
    assert len(run.client.store.get("olympus_action_cost_estimates", [])) >= 1
    assert len(run.client.store.get("positions", [])) >= 1
    assert len(run.client.store.get("portfolio_ledger_commits", [])) == 1

    # Simulator canned H7 memo sets AAPL confidence=0.7; H8 haircuts cash-first.
    aapl_row = next(row for row in hermes.pm_direction_memo.roster if row.ticker == "AAPL")
    assert aapl_row.confidence == pytest.approx(0.7)
    assert sized_book_weights(hermes.sized_book) == {"AAPL": 70.0}

    cutoff = final.knowledge_cutoff_at
    assert cutoff is not None
    assessment_id = UUID(str(run.client.store["olympus_forecast_assessments"][0]["forecast_id"]))
    assert (
        fr.get_forecast_assessment(
            client=run.client,
            forecast_id=assessment_id,
            knowledge_cutoff_at=cutoff,
        )
        is not None
    )
    policy_id = UUID(str(run.client.store["olympus_risk_policies"][0]["policy_id"]))
    assert (
        rpr.get_risk_policy(client=run.client, policy_id=policy_id, knowledge_cutoff_at=cutoff)
        is not None
    )
    estimate_id = UUID(str(run.client.store["olympus_action_cost_estimates"][0]["estimate_id"]))
    assert (
        clr.get_action_cost_estimate(
            client=run.client,
            estimate_id=estimate_id,
            knowledge_cutoff_at=cutoff,
        )
        is not None
    )


def test_phase1_shadow_calibration_sparse_cohort_when_no_outcomes() -> None:
    final, _run = _run_phase1_pipeline()
    hermes = final.phase_hermes
    assert hermes.calibrated_forecasts
    subject = hermes.calibrated_forecasts["AAPL"]
    assert subject["status"] == CalibrationArtifactStatus.UNAVAILABLE.value
    assert subject["unavailable_reason"] == "empty_cohort"


def test_phase1_cutoff_excludes_late_known_outcomes_from_calibration() -> None:
    from tests.dq.hermes.phase1_e2e_fixtures import LATE_KNOWN_AT, resolved_outcome_row

    final, _run = _run_phase1_pipeline(
        canned_extras={
            "olympus_forecast_outcomes": [resolved_outcome_row(salt=1, known_at=LATE_KNOWN_AT)]
        },
    )
    cal = next(iter(final.phase_hermes.forecast_calibrations.values()))
    assert cal["status"] == CalibrationArtifactStatus.UNAVAILABLE.value
    assert cal["unavailable_reason"] == "empty_cohort"


def test_phase1_invalid_amendment_preserves_base_effective() -> None:
    from datetime import date

    from tests.dq.hermes.phase1_e2e_fixtures import (
        invalid_forecast_amendment_dict,
        sample_forecast_terms_dict,
    )

    terms = ForecastTerms.model_validate(sample_forecast_terms_dict())
    cutoff = datetime(2026, 4, 26, 15, 0, tzinfo=UTC)
    assessment = materialize_forecast_assessment(
        ticker="AAPL",
        terms=terms,
        source_run_id="run-amend-red",
        provider_invocation_id="inv-h6",
        prompt_version="pv-test",
        artifact_version="av-test",
        price_anchor=PriceAnchor(
            status=PriceAnchorStatus.UNAVAILABLE,
            unavailable_reason="test",
        ),
        effective_at=cutoff,
        known_at=cutoff,
    )
    state = AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 4, 26),
        knowledge_cutoff_at=cutoff,
        phase_hermes=PhaseHermesState(),
    )
    analyst = {
        "ticker": "AAPL",
        "forecast_assessment": assessment.model_dump(mode="json"),
        "forecast": terms.model_dump(mode="json"),
    }
    effective, amendment = _resolve_from_debate(
        state=state,
        ticker="AAPL",
        analyst=analyst,
        amendment_terms_raw=invalid_forecast_amendment_dict(),
        amendment_reason="invalid probabilities",
    )
    assert amendment is None
    assert effective is not None
    assert effective.amendment_outcome is AmendmentOutcome.REJECTED
    assert effective.effective_id == assessment.forecast_id
    assert effective.degradation_reason == "amendment_rejected"


def test_phase1_unpriceable_action_is_typed_not_zero() -> None:

    from tests.dq.hermes.test_commit_run import _ledger_client, _run, _state

    client = _ledger_client()  # no price rows — SPY unpriceable
    state = _state(
        sized_book={
            "recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}],
            "actions": [],
            "notes": "",
        },
    )
    out = _run(client, state)
    manifest = out["phase_hermes"].commit_manifest or {}
    assert manifest["status"] == "committed"
    assert "SPY" in (manifest.get("ledger_unpriced_symbols") or [])
    assert manifest["cost_liquidity_registry_status"] in ("ok", "degraded", "skipped")


def test_phase1_degraded_risk_registry_keeps_book(monkeypatch: pytest.MonkeyPatch) -> None:

    from digiquant.portfolio.phases import h9_commit_run as h9

    from tests.dq.hermes.test_commit_run import _run, _state

    client = FakeSupabaseClient()
    state = _state()

    def boom(**_kwargs: object) -> None:
        raise RuntimeError("risk registry down")

    monkeypatch.setattr(h9, "persist_h8_risk_snapshots_from_state", boom)
    out = _run(client, state)
    manifest = out["phase_hermes"].commit_manifest or {}
    assert manifest["status"] == "committed"
    assert manifest["risk_policy_registry_status"] == "degraded"
    assert client.store.get("positions", [])


def test_phase1_h9_second_commit_with_same_book_is_noop() -> None:
    from tests.dq.hermes.test_commit_run import _ledger_client, _mirror_ledger, _run, _state

    client = _ledger_client(SPY=100.0)
    state = _state()
    first = _run(client, state)
    assert first["phase_hermes"].commit_manifest["status"] == "committed"
    positions_after_first = len(client.store.get("positions", []))
    _mirror_ledger(client)
    second = _run(client, state)
    assert second["phase_hermes"].commit_manifest["status"] == "noop"
    assert len(client.store.get("positions", [])) == positions_after_first
