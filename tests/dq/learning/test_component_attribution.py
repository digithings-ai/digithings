"""WP15.4 — honest component attribution (#2967).

Red coverage: forecast error identical horizon; proper scores where defined;
expected/realized execution cost; timing diagnostics non-causal; sizing unavailable
without replay; valid paired delta; no sum of one-at-a-time deltas; ordered
waterfall/residual; missing data unavailable; units/uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from digiquant.olympus.learning.component_attribution import (
    ComponentAttributor,
    CostAttributionSlice,
    ForecastAttributionSlice,
    PairedReplayEvidence,
    ReplayEvidenceError,
    TimingDiagnosticsSlice,
    attribution_report_id,
)
from digiquant.olympus.learning.outcome_models import (
    AttributionComponent,
    AttributionMethod,
    ComponentEligibility,
    EpisodeDisposition,
    EvidenceQuality,
    H8TargetLineage,
    H9ExecutionLinks,
    OutcomeEpisode,
    OutcomeTemporalContract,
    RealizedReturnObservation,
    UnavailableReason,
    episode_content_hash,
    episode_version_id,
)
from digiquant.olympus.learning.outcome_store import OutcomeLearningStore

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
_HORIZON_END = _TS + timedelta(days=21)
_AVAILABLE = _TS + timedelta(days=22)
_FORECAST_ID = UUID("11111111-1111-4111-8111-111111111111")
_OUTCOME_ID = UUID("22222222-2222-4222-8222-222222222222")
_REPLAY_ARTIFACT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_OTHER_REPLAY = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def _temporal(**overrides: object) -> OutcomeTemporalContract:
    fields: dict[str, object] = dict(
        effective_at=_TS - timedelta(days=21),
        known_at=_TS - timedelta(days=20),
        recorded_at=_TS,
        horizon_end=_HORIZON_END,
        available_at=_AVAILABLE,
        replay_as_of=_AVAILABLE,
    )
    fields.update(overrides)
    return OutcomeTemporalContract(**fields)


def _realized(**overrides: object) -> RealizedReturnObservation:
    fields: dict[str, object] = dict(
        instrument_return=Decimal("0.042"),
        benchmark_return=Decimal("0.018"),
        active_return=Decimal("0.024"),
        accounting_period_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        contribution_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    )
    fields.update(overrides)
    return RealizedReturnObservation(**fields)


def _episode(**overrides: object) -> OutcomeEpisode:
    fields: dict[str, object] = dict(
        episode_key=f"forecast:{_FORECAST_ID}:horizon:21s",
        forecast_id=_FORECAST_ID,
        outcome_id=_OUTCOME_ID,
        mandate_id="mandate-daily",
        instrument_id="AAPL",
        horizon_id="h-21s",
        source_run_id="run-2026-08-26",
        evidence_bundle_id=UUID("33333333-3333-4333-8333-333333333333"),
        research_state_version_id=UUID("44444444-4444-4444-8444-444444444444"),
        context_manifest_id=UUID("55555555-5555-4555-8555-555555555555"),
        policy_version_id="policy-v1",
        disposition=EpisodeDisposition.AUTHORIZED,
        temporal=_temporal(),
        h8_lineage=H8TargetLineage(
            requested_weight=Decimal("0.05"),
            approved_weight=Decimal("0.04"),
            adjustment_codes=("risk_cap",),
        ),
        h9_links=H9ExecutionLinks(
            action_id=UUID("66666666-6666-4666-8666-666666666666"),
            order_id=UUID("77777777-7777-4777-8777-777777777777"),
            fill_ids=(UUID("88888888-8888-4888-8888-888888888888"),),
            holding_id=UUID("99999999-9999-4999-8999-999999999999"),
        ),
        realized=_realized(),
        expected_cost_id=UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
        realized_cost_id=UUID("bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"),
        pre_trade_risk_report_id=UUID("cccccccc-dddd-4eee-8fff-000000000000"),
        component_eligibility=(
            ComponentEligibility(component=AttributionComponent.FORECAST, eligible=True),
            ComponentEligibility(component=AttributionComponent.EXECUTION, eligible=True),
            ComponentEligibility(
                component=AttributionComponent.SIZING,
                eligible=False,
                unavailable_reason=UnavailableReason.MISSING_REPLAY_ARTIFACT,
            ),
            ComponentEligibility(component=AttributionComponent.TIMING, eligible=True),
            ComponentEligibility(component=AttributionComponent.RESIDUAL, eligible=True),
        ),
        quality_issues=(),
        supersedes_version_id=None,
    )
    fields.update(overrides)
    content_hash = episode_content_hash(
        episode_key=str(fields["episode_key"]),
        forecast_id=fields["forecast_id"],  # type: ignore[arg-type]
        outcome_id=fields["outcome_id"],  # type: ignore[arg-type]
        mandate_id=str(fields["mandate_id"]),
        instrument_id=str(fields["instrument_id"]),
        horizon_id=str(fields["horizon_id"]),
        source_run_id=str(fields["source_run_id"]),
        disposition=fields["disposition"],  # type: ignore[arg-type]
        temporal=fields["temporal"],  # type: ignore[arg-type]
        realized=fields.get("realized"),  # type: ignore[arg-type]
        h8_lineage=fields.get("h8_lineage"),  # type: ignore[arg-type]
        h9_links=fields.get("h9_links"),  # type: ignore[arg-type]
        evidence_bundle_id=fields.get("evidence_bundle_id"),  # type: ignore[arg-type]
        research_state_version_id=fields.get("research_state_version_id"),  # type: ignore[arg-type]
        context_manifest_id=fields.get("context_manifest_id"),  # type: ignore[arg-type]
        policy_version_id=fields.get("policy_version_id"),  # type: ignore[arg-type]
        expected_cost_id=fields.get("expected_cost_id"),  # type: ignore[arg-type]
        realized_cost_id=fields.get("realized_cost_id"),  # type: ignore[arg-type]
        pre_trade_risk_report_id=fields.get("pre_trade_risk_report_id"),  # type: ignore[arg-type]
        component_eligibility=tuple(fields.get("component_eligibility", ())),  # type: ignore[arg-type]
        quality_issues=tuple(fields.get("quality_issues", ())),  # type: ignore[arg-type]
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "episode_version_id",
        episode_version_id(
            episode_key=str(fields["episode_key"]),
            content_hash=str(fields["content_hash"]),
            supersedes_version_id=fields.get("supersedes_version_id"),  # type: ignore[arg-type]
        ),
    )
    return OutcomeEpisode(**fields)


def _forecast_slice(**overrides: object) -> ForecastAttributionSlice:
    fields: dict[str, object] = dict(
        forecast_mean_return=Decimal("0.05"),
        realized_return=Decimal("0.04"),
        signed_residual=Decimal("-0.01"),
        positive_label=True,
        calibrated_positive_probability=Decimal("0.62"),
        forecast_error_std=Decimal("0.03"),
    )
    fields.update(overrides)
    return ForecastAttributionSlice(**fields)


def _cost_slice(**overrides: object) -> CostAttributionSlice:
    fields: dict[str, object] = dict(
        expected_cost_bps=Decimal("12.0"),
        realized_cost_bps=Decimal("18.5"),
    )
    fields.update(overrides)
    return CostAttributionSlice(**fields)


def _timing_slice(**overrides: object) -> TimingDiagnosticsSlice:
    fields: dict[str, object] = dict(
        latency_ms=Decimal("250"),
        price_drift_bps=Decimal("4.5"),
    )
    fields.update(overrides)
    return TimingDiagnosticsSlice(**fields)


@dataclass
class FakeReaders:
    forecast: ForecastAttributionSlice | None = None
    cost: CostAttributionSlice | None = None
    timing: TimingDiagnosticsSlice | None = None

    def load_forecast_slice(
        self,
        *,
        outcome_id: UUID,
        knowledge_cutoff_at: datetime,
    ) -> ForecastAttributionSlice | None:
        return self.forecast

    def load_cost_slice(
        self,
        *,
        expected_cost_id: UUID | None,
        realized_cost_id: UUID | None,
        knowledge_cutoff_at: datetime,
    ) -> CostAttributionSlice | None:
        return self.cost

    def load_timing_diagnostics(
        self,
        *,
        action_id: UUID,
        knowledge_cutoff_at: datetime,
    ) -> TimingDiagnosticsSlice | None:
        return self.timing


def _attributor(
    readers: FakeReaders,
    *,
    store: OutcomeLearningStore | None = None,
) -> ComponentAttributor:
    return ComponentAttributor(
        store=store or OutcomeLearningStore(),
        forecast_reader=readers,
        cost_reader=readers,
        timing_reader=readers,
    )


def _obs_by_metric(report, metric: str):
    return next(obs for obs in report.observations if obs.metric == metric)


# ── Forecast ──────────────────────────────────────────────────────────────────


def test_forecast_error_uses_identical_horizon_interval() -> None:
    episode = _episode()
    report = _attributor(FakeReaders(forecast=_forecast_slice())).attribute(episode)
    obs = _obs_by_metric(report, "forecast_error_bps")
    assert obs.component is AttributionComponent.FORECAST
    assert obs.method is AttributionMethod.OBSERVED
    assert obs.interval_start == episode.temporal.effective_at
    assert obs.interval_end == episode.temporal.horizon_end
    assert obs.value == Decimal("-100.0")


def test_brier_score_emitted_when_probability_defined() -> None:
    report = _attributor(FakeReaders(forecast=_forecast_slice())).attribute(_episode())
    obs = _obs_by_metric(report, "brier_score")
    assert obs.evidence_quality is EvidenceQuality.OBSERVED
    expected = (Decimal("0.62") - Decimal("1")) ** 2
    assert obs.value == expected


# ── Execution ─────────────────────────────────────────────────────────────────


def test_execution_compares_expected_and_realized_cost() -> None:
    report = _attributor(FakeReaders(forecast=_forecast_slice(), cost=_cost_slice())).attribute(
        _episode()
    )
    expected = _obs_by_metric(report, "expected_cost_bps")
    realized = _obs_by_metric(report, "realized_cost_bps")
    delta = _obs_by_metric(report, "execution_cost_delta_bps")
    assert expected.value == Decimal("12.0")
    assert realized.value == Decimal("18.5")
    assert delta.value == Decimal("6.5")
    assert delta.unit == "bps"


# ── Timing diagnostics (non-causal) ───────────────────────────────────────────


def test_timing_latency_diagnostic_is_non_causal() -> None:
    report = _attributor(
        FakeReaders(
            forecast=_forecast_slice(),
            cost=_cost_slice(),
            timing=_timing_slice(),
        )
    ).attribute(_episode())
    obs = _obs_by_metric(report, "timing_latency_ms")
    assert obs.component is AttributionComponent.TIMING
    assert obs.method is AttributionMethod.OBSERVED
    assert obs.evidence_quality is EvidenceQuality.DESCRIPTIVE
    assert obs.value == Decimal("250")


def test_timing_pnl_unavailable_without_paired_replay() -> None:
    report = _attributor(FakeReaders(forecast=_forecast_slice(), timing=_timing_slice())).attribute(
        _episode()
    )
    obs = _obs_by_metric(report, "timing_pnl_bps")
    assert obs.method is AttributionMethod.UNAVAILABLE
    assert obs.unavailable_reason is UnavailableReason.MISSING_REPLAY_ARTIFACT


# ── Sizing ────────────────────────────────────────────────────────────────────


def test_sizing_pnl_unavailable_without_replay() -> None:
    report = _attributor(FakeReaders(forecast=_forecast_slice())).attribute(_episode())
    obs = _obs_by_metric(report, "sizing_pnl_bps")
    assert obs.method is AttributionMethod.UNAVAILABLE
    assert obs.unavailable_reason is UnavailableReason.MISSING_REPLAY_ARTIFACT


def test_sizing_pnl_with_valid_paired_replay() -> None:
    replay = PairedReplayEvidence(
        replay_artifact_id=_REPLAY_ARTIFACT,
        paired_manifest_hash="manifest-hash-abc",
        baseline="approved_h8_policy",
        sizing_pnl_bps=Decimal("15.0"),
    )
    report = _attributor(FakeReaders(forecast=_forecast_slice())).attribute(
        _episode(),
        replay_evidence=replay,
    )
    obs = _obs_by_metric(report, "sizing_pnl_bps")
    assert obs.method is AttributionMethod.COUNTERFACTUAL_REPLAY
    assert obs.replay_artifact_id == _REPLAY_ARTIFACT
    assert obs.baseline == "approved_h8_policy"
    assert obs.value == Decimal("15.0")


def test_rejects_one_at_a_time_deltas_from_different_replay_artifacts() -> None:
    with pytest.raises(ReplayEvidenceError, match="paired"):
        PairedReplayEvidence(
            replay_artifact_id=_REPLAY_ARTIFACT,
            paired_manifest_hash="manifest-hash-abc",
            baseline="approved_h8_policy",
            sizing_pnl_bps=Decimal("10.0"),
            timing_pnl_bps=Decimal("-3.0"),
            timing_replay_artifact_id=_OTHER_REPLAY,
        )


# ── Waterfall / residual ──────────────────────────────────────────────────────


def test_waterfall_declares_order_baseline_and_residual() -> None:
    report = _attributor(FakeReaders(forecast=_forecast_slice(), cost=_cost_slice())).attribute(
        _episode()
    )
    order = _obs_by_metric(report, "waterfall_order")
    baseline = _obs_by_metric(report, "waterfall_baseline")
    residual = _obs_by_metric(report, "waterfall_residual_bps")
    assert order.evidence_quality is EvidenceQuality.DESCRIPTIVE
    assert order.baseline is not None and "forecast" in order.baseline
    assert baseline.baseline == "zero_active_return"
    assert residual.component is AttributionComponent.RESIDUAL
    # active 240 bps − execution drag 6.5 bps (forecast error is separate instrument metric)
    assert residual.value == Decimal("233.5")
    assert residual.unit == "bps"


def test_waterfall_does_not_sum_independent_counterfactual_deltas() -> None:
    replay = PairedReplayEvidence(
        replay_artifact_id=_REPLAY_ARTIFACT,
        paired_manifest_hash="paired-only",
        baseline="paired_manifest",
        sizing_pnl_bps=Decimal("10.0"),
        timing_pnl_bps=Decimal("-3.0"),
    )
    report = _attributor(FakeReaders(forecast=_forecast_slice(), cost=_cost_slice())).attribute(
        _episode(),
        replay_evidence=replay,
    )
    residual = _obs_by_metric(report, "waterfall_residual_bps")
    # residual must not assume 10 + (-3) independent sum in waterfall slot
    assert residual.value != Decimal("240") + Decimal("10") - Decimal("3")


# ── Missing data ──────────────────────────────────────────────────────────────


def test_missing_forecast_slice_marks_forecast_unavailable() -> None:
    report = _attributor(FakeReaders(forecast=None)).attribute(_episode())
    obs = _obs_by_metric(report, "forecast_error_bps")
    assert obs.method is AttributionMethod.UNAVAILABLE
    assert obs.unavailable_reason is UnavailableReason.LATE_KNOWN_DATA


def test_excluded_episode_marks_forecast_unavailable() -> None:
    episode = _episode(
        disposition=EpisodeDisposition.EXCLUDED,
        h8_lineage=None,
        h9_links=None,
        realized=None,
        component_eligibility=(
            ComponentEligibility(
                component=AttributionComponent.FORECAST,
                eligible=False,
                unavailable_reason=UnavailableReason.EXCLUDED_EPISODE,
            ),
        ),
    )
    report = _attributor(FakeReaders(forecast=_forecast_slice())).attribute(episode)
    obs = _obs_by_metric(report, "forecast_error_bps")
    assert obs.method is AttributionMethod.UNAVAILABLE
    assert obs.unavailable_reason is UnavailableReason.EXCLUDED_EPISODE


# ── Persistence ───────────────────────────────────────────────────────────────


def test_attribute_and_persist_appends_report_to_store() -> None:
    store = OutcomeLearningStore()
    episode = _episode()
    store.append_episode(episode)
    attributor = _attributor(
        FakeReaders(forecast=_forecast_slice(), cost=_cost_slice()), store=store
    )
    report = attributor.attribute_and_persist(episode)
    loaded = store.load_report(report.report_id)
    assert loaded.report_id == report.report_id
    assert loaded.episode_version_id == episode.episode_version_id


def test_report_id_is_deterministic() -> None:
    from digiquant.olympus.learning.component_attribution import attribution_report_content_hash

    episode = _episode()
    readers = FakeReaders(forecast=_forecast_slice(), cost=_cost_slice())
    first = _attributor(readers).attribute(episode)
    second = _attributor(readers).attribute(episode)
    assert first.report_id == second.report_id
    content_hash = attribution_report_content_hash(
        episode_version_id=episode.episode_version_id,
        observations=first.observations,
    )
    assert first.report_id == attribution_report_id(
        episode_version_id=episode.episode_version_id,
        content_hash=content_hash,
    )
