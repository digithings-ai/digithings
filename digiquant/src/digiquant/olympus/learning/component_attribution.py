"""WP15.4 — compute honest component attribution (#2967).

Produces independent typed component observations from an :class:`OutcomeEpisode`
plus optional paired replay evidence. Separates causal, diagnostic, descriptive,
estimated, and unavailable evidence — never sums one-at-a-time counterfactual
deltas or substitutes zero for missing data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid5

from digiquant.olympus.hermes.allocation_hashes import sha256_hex
from digiquant.olympus.learning.outcome_models import (
    AttributionComponent,
    AttributionMethod,
    ComponentAttributionReport,
    ComponentEligibility,
    ComponentObservation,
    EvidenceQuality,
    OutcomeEpisode,
    UnavailableReason,
)
from digiquant.olympus.learning.outcome_store import OutcomeLearningStore
from digiquant.olympus.temporal import require_utc_datetime

_BPS_SCALE = Decimal("10000")
_REPORT_ID_NS = UUID("f3b4c5d6-7e8f-9a0b-1c2d-3e4f5a6b7c8d")

_WATERFALL_ORDER: tuple[AttributionComponent, ...] = (
    AttributionComponent.FORECAST,
    AttributionComponent.SIZING,
    AttributionComponent.TIMING,
    AttributionComponent.EXECUTION,
    AttributionComponent.RESIDUAL,
)
_WATERFALL_BASELINE = "zero_active_return"


class ReplayEvidenceError(ValueError):
    """Paired replay evidence failed validation."""


@dataclass(frozen=True)
class ForecastAttributionSlice:
    """Forecast outcome economics for identical-horizon error."""

    forecast_mean_return: Decimal
    realized_return: Decimal
    signed_residual: Decimal
    positive_label: bool
    calibrated_positive_probability: Decimal | None = None
    forecast_error_std: Decimal | None = None


@dataclass(frozen=True)
class CostAttributionSlice:
    """Expected vs realized execution cost in basis points."""

    expected_cost_bps: Decimal
    realized_cost_bps: Decimal


@dataclass(frozen=True)
class TimingDiagnosticsSlice:
    """Non-causal timing diagnostics — never sizing/timing P&L."""

    latency_ms: Decimal
    price_drift_bps: Decimal | None = None


@dataclass(frozen=True)
class PairedReplayEvidence:
    """Paired counterfactual replay artifact for causal sizing/timing P&L."""

    replay_artifact_id: UUID
    paired_manifest_hash: str
    baseline: str
    sizing_pnl_bps: Decimal | None = None
    timing_pnl_bps: Decimal | None = None
    timing_replay_artifact_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.paired_manifest_hash.strip():
            raise ValueError("paired_manifest_hash is required")
        if not self.baseline.strip():
            raise ValueError("baseline is required")
        if self.sizing_pnl_bps is None and self.timing_pnl_bps is None:
            raise ValueError("paired replay requires at least one causal delta")
        if self.timing_pnl_bps is not None and self.sizing_pnl_bps is not None:
            other = self.timing_replay_artifact_id
            if other is not None and other != self.replay_artifact_id:
                raise ReplayEvidenceError(
                    "one-at-a-time counterfactual deltas from different replay artifacts "
                    "cannot be combined — require a single paired manifest"
                )


class ForecastAttributionReader(Protocol):
    def load_forecast_slice(
        self,
        *,
        outcome_id: UUID,
        knowledge_cutoff_at: datetime,
    ) -> ForecastAttributionSlice | None: ...


class CostAttributionReader(Protocol):
    def load_cost_slice(
        self,
        *,
        expected_cost_id: UUID | None,
        realized_cost_id: UUID | None,
        knowledge_cutoff_at: datetime,
    ) -> CostAttributionSlice | None: ...


class TimingDiagnosticsReader(Protocol):
    def load_timing_diagnostics(
        self,
        *,
        action_id: UUID,
        knowledge_cutoff_at: datetime,
    ) -> TimingDiagnosticsSlice | None: ...


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def attribution_report_content_hash(
    *,
    episode_version_id: UUID,
    observations: tuple[ComponentObservation, ...],
) -> str:
    payload = {
        "episode_version_id": str(episode_version_id),
        "observations": [obs.model_dump(mode="json") for obs in observations],
    }
    return sha256_hex(payload)


def attribution_report_id(
    *,
    episode_version_id: UUID,
    content_hash: str,
) -> UUID:
    seed = _canonical_json(
        {"episode_version_id": str(episode_version_id), "content_hash": content_hash}
    )
    return uuid5(_REPORT_ID_NS, seed)


def _bps_from_return(value: Decimal) -> Decimal:
    return value * _BPS_SCALE


def _eligibility_map(
    episode: OutcomeEpisode,
) -> dict[AttributionComponent, ComponentEligibility]:
    return {item.component: item for item in episode.component_eligibility}


def _unavailable_observation(
    *,
    component: AttributionComponent,
    metric: str,
    reason: UnavailableReason,
    unit: str = "unitless",
) -> ComponentObservation:
    return ComponentObservation(
        component=component,
        metric=metric,
        value=None,
        unit=unit,
        uncertainty=None,
        baseline=None,
        evidence_quality=EvidenceQuality.UNAVAILABLE,
        method=AttributionMethod.UNAVAILABLE,
        unavailable_reason=reason,
    )


def _forecast_observations(
    episode: OutcomeEpisode,
    slice_: ForecastAttributionSlice | None,
    eligibility: dict[AttributionComponent, ComponentEligibility],
) -> list[ComponentObservation]:
    interval_start = episode.temporal.effective_at
    interval_end = episode.temporal.horizon_end
    artifact_ids = (episode.outcome_id,)

    forecast_eligible = eligibility.get(AttributionComponent.FORECAST)
    if forecast_eligible is not None and not forecast_eligible.eligible:
        reason = forecast_eligible.unavailable_reason or UnavailableReason.EXCLUDED_EPISODE
        return [
            _unavailable_observation(
                component=AttributionComponent.FORECAST,
                metric="forecast_error_bps",
                reason=reason,
                unit="bps",
            )
        ]

    if slice_ is None:
        return [
            _unavailable_observation(
                component=AttributionComponent.FORECAST,
                metric="forecast_error_bps",
                reason=UnavailableReason.LATE_KNOWN_DATA,
                unit="bps",
            )
        ]

    observations: list[ComponentObservation] = [
        ComponentObservation(
            component=AttributionComponent.FORECAST,
            metric="forecast_error_bps",
            value=_bps_from_return(slice_.signed_residual),
            unit="bps",
            uncertainty=(
                _bps_from_return(slice_.forecast_error_std)
                if slice_.forecast_error_std is not None
                else None
            ),
            baseline="point_forecast",
            interval_start=interval_start,
            interval_end=interval_end,
            artifact_ids=artifact_ids,
            evidence_quality=EvidenceQuality.OBSERVED,
            method=AttributionMethod.OBSERVED,
        ),
        ComponentObservation(
            component=AttributionComponent.FORECAST,
            metric="signed_residual_return",
            value=slice_.signed_residual,
            unit="return_fraction",
            uncertainty=slice_.forecast_error_std,
            baseline="point_forecast",
            interval_start=interval_start,
            interval_end=interval_end,
            artifact_ids=artifact_ids,
            evidence_quality=EvidenceQuality.OBSERVED,
            method=AttributionMethod.OBSERVED,
        ),
    ]

    if slice_.calibrated_positive_probability is not None:
        label = Decimal("1") if slice_.positive_label else Decimal("0")
        brier = (slice_.calibrated_positive_probability - label) ** 2
        observations.append(
            ComponentObservation(
                component=AttributionComponent.FORECAST,
                metric="brier_score",
                value=brier,
                unit="probability_squared",
                uncertainty=None,
                baseline="empirical_label",
                interval_start=interval_start,
                interval_end=interval_end,
                artifact_ids=artifact_ids,
                evidence_quality=EvidenceQuality.OBSERVED,
                method=AttributionMethod.OBSERVED,
            )
        )

    return observations


def _execution_observations(
    episode: OutcomeEpisode,
    slice_: CostAttributionSlice | None,
    eligibility: dict[AttributionComponent, ComponentEligibility],
) -> list[ComponentObservation]:
    exec_eligible = eligibility.get(AttributionComponent.EXECUTION)
    if exec_eligible is not None and not exec_eligible.eligible:
        reason = exec_eligible.unavailable_reason or UnavailableReason.MISSING_FILL_DATA
        return [
            _unavailable_observation(
                component=AttributionComponent.EXECUTION,
                metric="execution_cost_delta_bps",
                reason=reason,
                unit="bps",
            )
        ]

    if slice_ is None or episode.expected_cost_id is None or episode.realized_cost_id is None:
        return [
            _unavailable_observation(
                component=AttributionComponent.EXECUTION,
                metric="execution_cost_delta_bps",
                reason=UnavailableReason.MISSING_FILL_DATA,
                unit="bps",
            )
        ]

    artifact_ids = (episode.expected_cost_id, episode.realized_cost_id)
    delta = slice_.realized_cost_bps - slice_.expected_cost_bps
    return [
        ComponentObservation(
            component=AttributionComponent.EXECUTION,
            metric="expected_cost_bps",
            value=slice_.expected_cost_bps,
            unit="bps",
            uncertainty=None,
            baseline="pre_trade_estimate",
            artifact_ids=(episode.expected_cost_id,),
            evidence_quality=EvidenceQuality.MODELED,
            method=AttributionMethod.MODEL_ESTIMATE,
        ),
        ComponentObservation(
            component=AttributionComponent.EXECUTION,
            metric="realized_cost_bps",
            value=slice_.realized_cost_bps,
            unit="bps",
            uncertainty=None,
            baseline="authoritative_fill",
            artifact_ids=(episode.realized_cost_id,),
            evidence_quality=EvidenceQuality.OBSERVED,
            method=AttributionMethod.OBSERVED,
        ),
        ComponentObservation(
            component=AttributionComponent.EXECUTION,
            metric="execution_cost_delta_bps",
            value=delta,
            unit="bps",
            uncertainty=None,
            baseline="expected_cost_bps",
            artifact_ids=artifact_ids,
            evidence_quality=EvidenceQuality.OBSERVED,
            method=AttributionMethod.OBSERVED,
        ),
    ]


def _timing_observations(
    episode: OutcomeEpisode,
    diagnostics: TimingDiagnosticsSlice | None,
    replay: PairedReplayEvidence | None,
    eligibility: dict[AttributionComponent, ComponentEligibility],
) -> list[ComponentObservation]:
    observations: list[ComponentObservation] = []

    if diagnostics is not None:
        action_id = episode.h9_links.action_id if episode.h9_links is not None else None
        artifact_ids = (action_id,) if action_id is not None else ()
        observations.append(
            ComponentObservation(
                component=AttributionComponent.TIMING,
                metric="timing_latency_ms",
                value=diagnostics.latency_ms,
                unit="ms",
                uncertainty=None,
                baseline="decision_timestamp",
                artifact_ids=artifact_ids,
                evidence_quality=EvidenceQuality.DESCRIPTIVE,
                method=AttributionMethod.OBSERVED,
            )
        )
        if diagnostics.price_drift_bps is not None:
            observations.append(
                ComponentObservation(
                    component=AttributionComponent.TIMING,
                    metric="timing_price_drift_bps",
                    value=diagnostics.price_drift_bps,
                    unit="bps",
                    uncertainty=None,
                    baseline="decision_reference_price",
                    artifact_ids=artifact_ids,
                    evidence_quality=EvidenceQuality.DESCRIPTIVE,
                    method=AttributionMethod.OBSERVED,
                )
            )

    timing_eligible = eligibility.get(AttributionComponent.TIMING)
    if replay is not None and replay.timing_pnl_bps is not None:
        observations.append(
            ComponentObservation(
                component=AttributionComponent.TIMING,
                metric="timing_pnl_bps",
                value=replay.timing_pnl_bps,
                unit="bps",
                uncertainty=None,
                baseline=replay.baseline,
                artifact_ids=(replay.replay_artifact_id,),
                evidence_quality=EvidenceQuality.COUNTERFACTUAL,
                method=AttributionMethod.COUNTERFACTUAL_REPLAY,
                replay_artifact_id=replay.replay_artifact_id,
            )
        )
        return observations

    if timing_eligible is not None and not timing_eligible.eligible:
        reason = timing_eligible.unavailable_reason or UnavailableReason.MISSING_REPLAY_ARTIFACT
        observations.append(
            _unavailable_observation(
                component=AttributionComponent.TIMING,
                metric="timing_pnl_bps",
                reason=reason,
                unit="bps",
            )
        )
        return observations

    observations.append(
        _unavailable_observation(
            component=AttributionComponent.TIMING,
            metric="timing_pnl_bps",
            reason=UnavailableReason.MISSING_REPLAY_ARTIFACT,
            unit="bps",
        )
    )

    return observations


def _sizing_observations(
    episode: OutcomeEpisode,
    replay: PairedReplayEvidence | None,
    eligibility: dict[AttributionComponent, ComponentEligibility],
) -> list[ComponentObservation]:
    observations: list[ComponentObservation] = []

    if episode.h8_lineage is not None:
        requested = episode.h8_lineage.requested_weight
        approved = episode.h8_lineage.approved_weight
        if requested is not None and approved is not None:
            delta = approved - requested
            observations.append(
                ComponentObservation(
                    component=AttributionComponent.SIZING,
                    metric="weight_adjustment_fraction",
                    value=delta,
                    unit="weight_fraction",
                    uncertainty=None,
                    baseline="requested_h8_weight",
                    artifact_ids=(),
                    evidence_quality=EvidenceQuality.DESCRIPTIVE,
                    method=AttributionMethod.OBSERVED,
                )
            )

    sizing_eligible = eligibility.get(AttributionComponent.SIZING)
    if replay is not None and replay.sizing_pnl_bps is not None:
        observations.append(
            ComponentObservation(
                component=AttributionComponent.SIZING,
                metric="sizing_pnl_bps",
                value=replay.sizing_pnl_bps,
                unit="bps",
                uncertainty=None,
                baseline=replay.baseline,
                artifact_ids=(replay.replay_artifact_id,),
                evidence_quality=EvidenceQuality.COUNTERFACTUAL,
                method=AttributionMethod.COUNTERFACTUAL_REPLAY,
                replay_artifact_id=replay.replay_artifact_id,
            )
        )
        return observations

    if sizing_eligible is not None and not sizing_eligible.eligible:
        reason = sizing_eligible.unavailable_reason or UnavailableReason.MISSING_REPLAY_ARTIFACT
        observations.append(
            _unavailable_observation(
                component=AttributionComponent.SIZING,
                metric="sizing_pnl_bps",
                reason=reason,
                unit="bps",
            )
        )
        return observations

    observations.append(
        _unavailable_observation(
            component=AttributionComponent.SIZING,
            metric="sizing_pnl_bps",
            reason=UnavailableReason.MISSING_REPLAY_ARTIFACT,
            unit="bps",
        )
    )

    return observations


def _waterfall_observations(
    episode: OutcomeEpisode,
    forecast_slice: ForecastAttributionSlice | None,
    cost_slice: CostAttributionSlice | None,
    replay: PairedReplayEvidence | None,
    eligibility: dict[AttributionComponent, ComponentEligibility],
) -> list[ComponentObservation]:
    residual_eligible = eligibility.get(AttributionComponent.RESIDUAL)
    if residual_eligible is not None and not residual_eligible.eligible:
        reason = residual_eligible.unavailable_reason or UnavailableReason.UNRECONCILED_ACCOUNTING
        return [
            _unavailable_observation(
                component=AttributionComponent.RESIDUAL,
                metric="waterfall_residual_bps",
                reason=reason,
                unit="bps",
            )
        ]

    if episode.realized is None or episode.realized.active_return is None:
        return [
            _unavailable_observation(
                component=AttributionComponent.RESIDUAL,
                metric="waterfall_residual_bps",
                reason=UnavailableReason.MISSING_ACCOUNTING,
                unit="bps",
            )
        ]

    active_bps = _bps_from_return(episode.realized.active_return)
    included: list[Decimal] = []

    forecast_bps: Decimal | None = None
    if forecast_slice is not None:
        forecast_bps = _bps_from_return(forecast_slice.signed_residual)

    sizing_bps: Decimal | None = None
    if replay is not None and replay.sizing_pnl_bps is not None:
        sizing_bps = replay.sizing_pnl_bps
        included.append(sizing_bps)

    timing_bps: Decimal | None = None
    if replay is not None and replay.timing_pnl_bps is not None:
        timing_bps = replay.timing_pnl_bps
        included.append(timing_bps)

    execution_drag_bps: Decimal | None = None
    if cost_slice is not None:
        execution_drag_bps = cost_slice.realized_cost_bps - cost_slice.expected_cost_bps
        included.append(execution_drag_bps)

    # Forecast error is reported separately on instrument-return horizon — not summed here.
    residual_bps = active_bps - sum(included, start=Decimal("0"))

    order_label = ",".join(component.value for component in _WATERFALL_ORDER)
    observations: list[ComponentObservation] = [
        ComponentObservation(
            component=AttributionComponent.RESIDUAL,
            metric="waterfall_order",
            value=Decimal(len(_WATERFALL_ORDER)),
            unit="components",
            uncertainty=None,
            baseline=order_label,
            evidence_quality=EvidenceQuality.DESCRIPTIVE,
            method=AttributionMethod.OBSERVED,
        ),
        ComponentObservation(
            component=AttributionComponent.RESIDUAL,
            metric="waterfall_baseline",
            value=Decimal("0"),
            unit="return_fraction",
            uncertainty=None,
            baseline=_WATERFALL_BASELINE,
            evidence_quality=EvidenceQuality.DESCRIPTIVE,
            method=AttributionMethod.OBSERVED,
        ),
        ComponentObservation(
            component=AttributionComponent.RESIDUAL,
            metric="waterfall_residual_bps",
            value=residual_bps,
            unit="bps",
            uncertainty=None,
            baseline=_WATERFALL_BASELINE,
            evidence_quality=EvidenceQuality.OBSERVED,
            method=AttributionMethod.OBSERVED,
        ),
    ]

    if forecast_bps is not None:
        observations.append(
            ComponentObservation(
                component=AttributionComponent.FORECAST,
                metric="waterfall_forecast_bps",
                value=forecast_bps,
                unit="bps",
                uncertainty=None,
                baseline=_WATERFALL_BASELINE,
                evidence_quality=EvidenceQuality.OBSERVED,
                method=AttributionMethod.OBSERVED,
            )
        )
    if sizing_bps is not None:
        observations.append(
            ComponentObservation(
                component=AttributionComponent.SIZING,
                metric="waterfall_sizing_bps",
                value=sizing_bps,
                unit="bps",
                uncertainty=None,
                baseline=_WATERFALL_BASELINE,
                evidence_quality=EvidenceQuality.COUNTERFACTUAL,
                method=AttributionMethod.COUNTERFACTUAL_REPLAY,
                replay_artifact_id=replay.replay_artifact_id if replay else None,
            )
        )
    if timing_bps is not None:
        observations.append(
            ComponentObservation(
                component=AttributionComponent.TIMING,
                metric="waterfall_timing_bps",
                value=timing_bps,
                unit="bps",
                uncertainty=None,
                baseline=_WATERFALL_BASELINE,
                evidence_quality=EvidenceQuality.COUNTERFACTUAL,
                method=AttributionMethod.COUNTERFACTUAL_REPLAY,
                replay_artifact_id=replay.replay_artifact_id if replay else None,
            )
        )
    if execution_drag_bps is not None:
        observations.append(
            ComponentObservation(
                component=AttributionComponent.EXECUTION,
                metric="waterfall_execution_bps",
                value=execution_drag_bps,
                unit="bps",
                uncertainty=None,
                baseline=_WATERFALL_BASELINE,
                evidence_quality=EvidenceQuality.OBSERVED,
                method=AttributionMethod.OBSERVED,
            )
        )

    return observations


def build_component_attribution_report(
    episode: OutcomeEpisode,
    *,
    forecast_slice: ForecastAttributionSlice | None = None,
    cost_slice: CostAttributionSlice | None = None,
    timing_diagnostics: TimingDiagnosticsSlice | None = None,
    replay_evidence: PairedReplayEvidence | None = None,
) -> ComponentAttributionReport:
    """Build a typed attribution report without persistence."""
    eligibility = _eligibility_map(episode)
    observations: list[ComponentObservation] = []
    observations.extend(_forecast_observations(episode, forecast_slice, eligibility))
    observations.extend(_execution_observations(episode, cost_slice, eligibility))
    observations.extend(
        _timing_observations(episode, timing_diagnostics, replay_evidence, eligibility)
    )
    observations.extend(_sizing_observations(episode, replay_evidence, eligibility))
    observations.extend(
        _waterfall_observations(episode, forecast_slice, cost_slice, replay_evidence, eligibility)
    )

    obs_tuple = tuple(observations)
    content_hash = attribution_report_content_hash(
        episode_version_id=episode.episode_version_id,
        observations=obs_tuple,
    )
    report_id = attribution_report_id(
        episode_version_id=episode.episode_version_id,
        content_hash=content_hash,
    )
    return ComponentAttributionReport(
        report_id=report_id,
        episode_version_id=episode.episode_version_id,
        observations=obs_tuple,
    )


class ComponentAttributor:
    """Attribute one episode version and optionally persist the report."""

    def __init__(
        self,
        *,
        store: OutcomeLearningStore,
        forecast_reader: ForecastAttributionReader,
        cost_reader: CostAttributionReader,
        timing_reader: TimingDiagnosticsReader,
    ) -> None:
        self._store = store
        self._forecast_reader = forecast_reader
        self._cost_reader = cost_reader
        self._timing_reader = timing_reader

    def attribute(
        self,
        episode: OutcomeEpisode,
        *,
        replay_evidence: PairedReplayEvidence | None = None,
        knowledge_cutoff_at: datetime | None = None,
    ) -> ComponentAttributionReport:
        cutoff = knowledge_cutoff_at or episode.temporal.replay_as_of
        cutoff = require_utc_datetime(cutoff, field_name="knowledge_cutoff_at")

        forecast_slice = self._forecast_reader.load_forecast_slice(
            outcome_id=episode.outcome_id,
            knowledge_cutoff_at=cutoff,
        )
        cost_slice = self._cost_reader.load_cost_slice(
            expected_cost_id=episode.expected_cost_id,
            realized_cost_id=episode.realized_cost_id,
            knowledge_cutoff_at=cutoff,
        )
        timing_diagnostics: TimingDiagnosticsSlice | None = None
        if episode.h9_links is not None:
            timing_diagnostics = self._timing_reader.load_timing_diagnostics(
                action_id=episode.h9_links.action_id,
                knowledge_cutoff_at=cutoff,
            )

        return build_component_attribution_report(
            episode,
            forecast_slice=forecast_slice,
            cost_slice=cost_slice,
            timing_diagnostics=timing_diagnostics,
            replay_evidence=replay_evidence,
        )

    def attribute_and_persist(
        self,
        episode: OutcomeEpisode,
        *,
        replay_evidence: PairedReplayEvidence | None = None,
        knowledge_cutoff_at: datetime | None = None,
    ) -> ComponentAttributionReport:
        report = self.attribute(
            episode,
            replay_evidence=replay_evidence,
            knowledge_cutoff_at=knowledge_cutoff_at,
        )
        return self._store.append_report(report)


__all__ = [
    "ComponentAttributor",
    "CostAttributionSlice",
    "ForecastAttributionSlice",
    "PairedReplayEvidence",
    "ReplayEvidenceError",
    "TimingDiagnosticsSlice",
    "attribution_report_content_hash",
    "attribution_report_id",
    "build_component_attribution_report",
]
