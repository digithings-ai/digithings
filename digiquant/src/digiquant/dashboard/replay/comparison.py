"""WP16.6 — complete paired policy comparison reports (#2999).

Aggregates fold/arm evidence across research, signal, forecast, action,
portfolio, risk, and engine contributions. Observed and modeled evidence stay
distinct; missingness is typed; undersampled or breached reports cannot promote.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, TypeAlias
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from digiquant.dashboard.replay.governance_models import (
    PolicyComparisonReport as GovernanceComparisonEnvelope,
)
from digiquant.dashboard.replay.models import (
    PortfolioReplayResult,
    PortfolioReplayStatus,
    ReplayArmLabel,
    ReplayPairSpec,
    max_drawdown_from_nav_path,
)
from digiquant.dashboard.temporal import require_utc_datetime
from digiquant.portfolio.allocation_hashes import sha256_hex

__all__ = [
    "REQUIRED_METRIC_GROUPS",
    "ArmFoldEvidence",
    "ComparisonMetric",
    "ComparisonReportStatus",
    "EvidenceMode",
    "FoldComparisonEvidence",
    "MetricAvailability",
    "MetricDirection",
    "MetricGroup",
    "MetricGroupId",
    "OptionalArmTelemetry",
    "PolicyComparisonReport",
    "ResearchTelemetry",
    "SignalQualityTelemetry",
    "compare_policy_pair",
    "policy_comparison_report_content_hash",
]

NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
FiniteDec: TypeAlias = Annotated[Decimal, Field(allow_inf_nan=False)]
FiniteNonNegDec: TypeAlias = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
HashHex64: TypeAlias = Annotated[str, Field(min_length=64, max_length=64)]

_MONEY = Decimal("0.00000001")


class ComparisonContractModel(BaseModel):
    """Strict immutable base for policy comparison contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ComparisonReportStatus(StrEnum):
    """Typed outcome of one paired policy comparison."""

    COMPLETE = "complete"
    UNDERSAMPLED = "undersampled"
    INCONCLUSIVE = "inconclusive"
    INCOMPLETE = "incomplete"


class EvidenceMode(StrEnum):
    """How a metric leaf was produced — never pool across modes."""

    OBSERVED = "observed"
    MODELED = "modeled"
    COUNTERFACTUAL = "counterfactual"
    DESCRIPTIVE = "descriptive"
    UNAVAILABLE = "unavailable"


class MetricDirection(StrEnum):
    """Interpretation hint for absolute/delta values."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    NEUTRAL = "neutral"


class MetricAvailability(StrEnum):
    """Availability of one absolute/delta leaf."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INCONCLUSIVE = "inconclusive"


class MetricGroupId(StrEnum):
    """Required contribution groups for a complete comparison."""

    RESEARCH = "research"
    SIGNAL_QUALITY = "signal_quality"
    FORECAST = "forecast"
    ACTIONS = "actions"
    PORTFOLIO = "portfolio"
    RISK = "risk"
    ENGINE = "engine"


REQUIRED_METRIC_GROUPS: frozenset[MetricGroupId] = frozenset(MetricGroupId)


class ComparisonMetric(ComparisonContractModel):
    """One named absolute/delta leaf with provenance and evidence mode."""

    name: NonEmptyId
    direction: MetricDirection
    evidence_mode: EvidenceMode
    availability: MetricAvailability
    absolute_incumbent: FiniteDec | None = None
    absolute_challenger: FiniteDec | None = None
    delta: FiniteDec | None = None
    sample_count: Annotated[int, Field(ge=0)] = 0
    missing_count: Annotated[int, Field(ge=0)] = 0
    provenance: NonEmptyId
    unavailable_reason: NonEmptyId | None = None

    @model_validator(mode="after")
    def _validate_leaf(self) -> ComparisonMetric:
        if self.availability is MetricAvailability.AVAILABLE:
            if (
                self.absolute_incumbent is None
                or self.absolute_challenger is None
                or self.delta is None
            ):
                raise ValueError("available metric requires absolute and delta values")
            if self.unavailable_reason is not None:
                raise ValueError("available metric cannot carry unavailable_reason")
            expected = self.absolute_challenger - self.absolute_incumbent
            if abs(expected - self.delta) > _MONEY:
                raise ValueError("delta must equal challenger - incumbent")
            if self.evidence_mode is EvidenceMode.UNAVAILABLE:
                raise ValueError("available metric cannot use unavailable evidence_mode")
        else:
            if self.delta is not None:
                raise ValueError("non-available metric cannot carry delta")
            if self.unavailable_reason is None or not self.unavailable_reason.strip():
                raise ValueError("non-available metric requires unavailable_reason")
        return self


class MetricGroup(ComparisonContractModel):
    """One required contribution group."""

    group_id: MetricGroupId
    metrics: tuple[ComparisonMetric, ...]
    group_unavailable_reason: NonEmptyId | None = None

    @field_validator("metrics", mode="before")
    @classmethod
    def _coerce_metrics(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_group(self) -> MetricGroup:
        if not self.metrics:
            raise ValueError(f"{self.group_id.value} must expose at least one metric leaf")
        # Distinct leaves may mix evidence modes; pooling into one leaf is rejected
        # upstream when incumbent/challenger modes diverge for the same metric name.
        return self


class FoldComparisonEvidence(ComparisonContractModel):
    """Retained fold identity for one paired comparison."""

    fold_id: NonEmptyId
    incumbent_result_status: PortfolioReplayStatus
    challenger_result_status: PortfolioReplayStatus
    incumbent_result_content_hash: NonEmptyId | None = None
    challenger_result_content_hash: NonEmptyId | None = None


class ResearchTelemetry(ComparisonContractModel):
    """Optional research resource counters for one arm/fold."""

    calls: Annotated[int, Field(ge=0)]
    searches: Annotated[int, Field(ge=0)]
    tokens: Annotated[int, Field(ge=0)]
    cost_usd: FiniteNonNegDec
    latency_ms: FiniteNonNegDec
    budget_usd: FiniteNonNegDec
    evidence_mode: EvidenceMode
    provenance: NonEmptyId
    sample_count: Annotated[int, Field(ge=0)] = 0
    missing_count: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _reject_unavailable_mode(self) -> ResearchTelemetry:
        if self.evidence_mode is EvidenceMode.UNAVAILABLE:
            raise ValueError("research telemetry evidence_mode cannot be unavailable")
        return self


class SignalQualityTelemetry(ComparisonContractModel):
    """Optional novelty/conflict/coverage signal quality for one arm/fold."""

    novelty: FiniteNonNegDec
    conflict: FiniteNonNegDec
    coverage: FiniteNonNegDec
    exploration: FiniteNonNegDec
    staleness_days: FiniteNonNegDec
    evidence_mode: EvidenceMode
    provenance: NonEmptyId
    sample_count: Annotated[int, Field(ge=0)] = 0
    missing_count: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _reject_unavailable_mode(self) -> SignalQualityTelemetry:
        if self.evidence_mode is EvidenceMode.UNAVAILABLE:
            raise ValueError("signal quality evidence_mode cannot be unavailable")
        return self


class OptionalArmTelemetry(ComparisonContractModel):
    """Optional non-portfolio evidence attached to one arm/fold result."""

    research: ResearchTelemetry | None = None
    signal_quality: SignalQualityTelemetry | None = None
    forecast_brier: FiniteDec | None = None
    forecast_log_score: FiniteDec | None = None
    forecast_uncertainty: FiniteNonNegDec | None = None
    forecast_evidence_mode: EvidenceMode = EvidenceMode.UNAVAILABLE
    forecast_provenance: NonEmptyId = "forecast_not_provided"
    forecast_sample_count: Annotated[int, Field(ge=0)] = 0
    forecast_missing_count: Annotated[int, Field(ge=0)] = 0
    active_return: FiniteDec | None = None
    benchmark_return: FiniteDec | None = None
    tail_loss: FiniteDec | None = None
    scenario_pnl: FiniteDec | None = None
    hard_constraint_breaches: tuple[str, ...] = ()
    accounting_breach: bool = False
    engine_status: NonEmptyId = "unknown"
    data_status: NonEmptyId = "unknown"
    failure_codes: tuple[str, ...] = ()

    @field_validator("hard_constraint_breaches", "failure_codes", mode="before")
    @classmethod
    def _coerce_tuples(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class ArmFoldEvidence(ComparisonContractModel):
    """One arm's result for one walk-forward fold (or single-window replay)."""

    arm: ReplayArmLabel
    fold_id: NonEmptyId
    manifest_content_hash: HashHex64
    request_content_hash: NonEmptyId
    result: PortfolioReplayResult
    telemetry: OptionalArmTelemetry = Field(default_factory=OptionalArmTelemetry)


class PolicyComparisonReport(ComparisonContractModel):
    """Complete paired comparison across all required metric groups."""

    schema_version: str = "1.0"
    comparison_id: UUID
    pair_content_hash: HashHex64
    shared_manifest_content_hash: HashHex64
    report_content_hash: HashHex64
    recorded_at: datetime
    status: ComparisonReportStatus
    metric_groups: tuple[MetricGroup, ...]
    folds: tuple[FoldComparisonEvidence, ...]
    undersampled: bool
    eligible_for_governance: bool
    promotion_blocked: bool
    promotion_blockers: tuple[str, ...] = ()
    accounting_breach_visible: bool
    hard_constraint_breach_visible: bool
    metric_groups_present: tuple[str, ...] = ()

    @field_validator(
        "metric_groups",
        "folds",
        "promotion_blockers",
        "metric_groups_present",
        mode="before",
    )
    @classmethod
    def _coerce_tuples(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("recorded_at")
    @classmethod
    def _require_recorded_utc(cls, value: datetime) -> datetime:
        return require_utc_datetime(value, field_name="recorded_at")

    @model_validator(mode="after")
    def _validate_report(self) -> PolicyComparisonReport:
        present = {g.group_id for g in self.metric_groups}
        if present != REQUIRED_METRIC_GROUPS:
            missing = sorted(g.value for g in REQUIRED_METRIC_GROUPS - present)
            raise ValueError(f"report missing required metric groups: {missing}")
        expected_present = tuple(sorted(g.group_id.value for g in self.metric_groups))
        if self.metric_groups_present != expected_present:
            raise ValueError("metric_groups_present must list every group sorted")
        expected_hash = policy_comparison_report_content_hash(self)
        if self.report_content_hash != expected_hash:
            raise ValueError("report_content_hash must match canonical digest")
        if self.undersampled and self.eligible_for_governance:
            raise ValueError("undersampled report cannot be eligible_for_governance")
        if self.promotion_blocked and self.eligible_for_governance:
            raise ValueError("promotion-blocked report cannot be eligible_for_governance")
        return self

    def to_governance_envelope(self) -> GovernanceComparisonEnvelope:
        """Project the rich report into the WP16.2 store persistence envelope."""
        return GovernanceComparisonEnvelope(
            comparison_id=self.comparison_id,
            pair_content_hash=self.pair_content_hash,
            shared_manifest_content_hash=self.shared_manifest_content_hash,
            report_content_hash=self.report_content_hash,
            recorded_at=self.recorded_at,
            status=self.status.value,
            metric_groups_present=self.metric_groups_present,
        )


def policy_comparison_report_content_hash(report: PolicyComparisonReport) -> str:
    """Stable digest excluding the self-referential report hash field."""
    payload = {
        "schema_version": report.schema_version,
        "comparison_id": str(report.comparison_id),
        "pair_content_hash": report.pair_content_hash,
        "shared_manifest_content_hash": report.shared_manifest_content_hash,
        "recorded_at": report.recorded_at.isoformat(),
        "status": report.status.value,
        "metric_groups": [g.model_dump(mode="json") for g in report.metric_groups],
        "folds": [f.model_dump(mode="json") for f in report.folds],
        "undersampled": report.undersampled,
        "eligible_for_governance": report.eligible_for_governance,
        "promotion_blocked": report.promotion_blocked,
        "promotion_blockers": list(report.promotion_blockers),
        "accounting_breach_visible": report.accounting_breach_visible,
        "hard_constraint_breach_visible": report.hard_constraint_breach_visible,
        "metric_groups_present": list(report.metric_groups_present),
    }
    return sha256_hex(payload)


def _unavailable_metric(
    *,
    name: str,
    direction: MetricDirection,
    reason: str,
    provenance: str,
    sample_count: int = 0,
    missing_count: int = 0,
    availability: MetricAvailability = MetricAvailability.UNAVAILABLE,
) -> ComparisonMetric:
    return ComparisonMetric(
        name=name,
        direction=direction,
        evidence_mode=EvidenceMode.UNAVAILABLE,
        availability=availability,
        provenance=provenance,
        unavailable_reason=reason,
        sample_count=sample_count,
        missing_count=missing_count,
    )


def _available_metric(
    *,
    name: str,
    direction: MetricDirection,
    evidence_mode: EvidenceMode,
    incumbent: Decimal,
    challenger: Decimal,
    provenance: str,
    sample_count: int,
    missing_count: int,
) -> ComparisonMetric:
    return ComparisonMetric(
        name=name,
        direction=direction,
        evidence_mode=evidence_mode,
        availability=MetricAvailability.AVAILABLE,
        absolute_incumbent=incumbent,
        absolute_challenger=challenger,
        delta=challenger - incumbent,
        provenance=provenance,
        sample_count=sample_count,
        missing_count=missing_count,
    )


def _index_folds(
    folds: tuple[ArmFoldEvidence, ...],
    *,
    expected_arm: ReplayArmLabel,
    shared_manifest_hash: str,
) -> dict[str, ArmFoldEvidence]:
    indexed: dict[str, ArmFoldEvidence] = {}
    for row in folds:
        if row.arm is not expected_arm:
            raise ValueError(f"expected {expected_arm.value} arm evidence")
        if row.manifest_content_hash != shared_manifest_hash:
            raise ValueError("arm fold must reference identical shared manifest")
        if row.fold_id in indexed:
            raise ValueError(f"duplicate fold_id {row.fold_id!r} for {expected_arm.value}")
        indexed[row.fold_id] = row
    return indexed


def _aggregate_research(
    incumbent: tuple[ArmFoldEvidence, ...],
    challenger: tuple[ArmFoldEvidence, ...],
) -> MetricGroup:
    names = (
        ("calls", MetricDirection.LOWER_IS_BETTER, "calls"),
        ("searches", MetricDirection.LOWER_IS_BETTER, "searches"),
        ("tokens", MetricDirection.LOWER_IS_BETTER, "tokens"),
        ("cost_usd", MetricDirection.LOWER_IS_BETTER, "cost_usd"),
        ("latency_ms", MetricDirection.LOWER_IS_BETTER, "latency_ms"),
        ("budget_usd", MetricDirection.NEUTRAL, "budget_usd"),
    )
    metrics: list[ComparisonMetric] = []
    for name, direction, attr in names:
        metrics.append(
            _pair_optional_scalar_attr(
                name=name,
                direction=direction,
                incumbent=incumbent,
                challenger=challenger,
                getter=lambda arm, a=attr: (
                    None
                    if arm.telemetry.research is None
                    else Decimal(str(getattr(arm.telemetry.research, a)))
                ),
                mode_getter=lambda arm: (
                    None if arm.telemetry.research is None else arm.telemetry.research.evidence_mode
                ),
                provenance_getter=lambda arm: (
                    "research_not_provided"
                    if arm.telemetry.research is None
                    else arm.telemetry.research.provenance
                ),
                sample_getter=lambda arm: (
                    0 if arm.telemetry.research is None else arm.telemetry.research.sample_count
                ),
                missing_getter=lambda arm: (
                    1 if arm.telemetry.research is None else arm.telemetry.research.missing_count
                ),
                missing_reason="research_telemetry_not_provided",
            )
        )
    return MetricGroup(group_id=MetricGroupId.RESEARCH, metrics=tuple(metrics))


def _aggregate_signal_quality(
    incumbent: tuple[ArmFoldEvidence, ...],
    challenger: tuple[ArmFoldEvidence, ...],
) -> MetricGroup:
    names = (
        ("novelty", MetricDirection.NEUTRAL, "novelty"),
        ("conflict", MetricDirection.LOWER_IS_BETTER, "conflict"),
        ("coverage", MetricDirection.HIGHER_IS_BETTER, "coverage"),
        ("exploration", MetricDirection.NEUTRAL, "exploration"),
        ("staleness_days", MetricDirection.LOWER_IS_BETTER, "staleness_days"),
    )
    metrics: list[ComparisonMetric] = []
    for name, direction, attr in names:
        metrics.append(
            _pair_optional_scalar_attr(
                name=name,
                direction=direction,
                incumbent=incumbent,
                challenger=challenger,
                getter=lambda arm, a=attr: (
                    None
                    if arm.telemetry.signal_quality is None
                    else getattr(arm.telemetry.signal_quality, a)
                ),
                mode_getter=lambda arm: (
                    None
                    if arm.telemetry.signal_quality is None
                    else arm.telemetry.signal_quality.evidence_mode
                ),
                provenance_getter=lambda arm: (
                    "signal_quality_not_provided"
                    if arm.telemetry.signal_quality is None
                    else arm.telemetry.signal_quality.provenance
                ),
                sample_getter=lambda arm: (
                    0
                    if arm.telemetry.signal_quality is None
                    else arm.telemetry.signal_quality.sample_count
                ),
                missing_getter=lambda arm: (
                    1
                    if arm.telemetry.signal_quality is None
                    else arm.telemetry.signal_quality.missing_count
                ),
                missing_reason="signal_quality_not_provided",
            )
        )
    return MetricGroup(group_id=MetricGroupId.SIGNAL_QUALITY, metrics=tuple(metrics))


def _aggregate_forecast(
    incumbent: tuple[ArmFoldEvidence, ...],
    challenger: tuple[ArmFoldEvidence, ...],
) -> MetricGroup:
    specs = (
        ("brier", MetricDirection.LOWER_IS_BETTER, "forecast_brier"),
        ("log_score", MetricDirection.HIGHER_IS_BETTER, "forecast_log_score"),
        ("uncertainty", MetricDirection.LOWER_IS_BETTER, "forecast_uncertainty"),
    )
    metrics: list[ComparisonMetric] = []
    for name, direction, attr in specs:
        metrics.append(
            _pair_optional_scalar_attr(
                name=name,
                direction=direction,
                incumbent=incumbent,
                challenger=challenger,
                getter=lambda arm, a=attr: getattr(arm.telemetry, a),
                mode_getter=lambda arm: (
                    None
                    if getattr(arm.telemetry, "forecast_brier") is None
                    and getattr(arm.telemetry, "forecast_log_score") is None
                    and getattr(arm.telemetry, "forecast_uncertainty") is None
                    else arm.telemetry.forecast_evidence_mode
                ),
                provenance_getter=lambda arm: arm.telemetry.forecast_provenance,
                sample_getter=lambda arm: arm.telemetry.forecast_sample_count,
                missing_getter=lambda arm: (
                    arm.telemetry.forecast_missing_count
                    if getattr(arm.telemetry, attr) is not None
                    else max(1, arm.telemetry.forecast_missing_count)
                ),
                missing_reason="forecast_metrics_not_provided",
            )
        )
    return MetricGroup(group_id=MetricGroupId.FORECAST, metrics=tuple(metrics))


def _mean_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        raise ValueError("cannot average empty values")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _pair_optional_scalar_attr(
    *,
    name: str,
    direction: MetricDirection,
    incumbent: tuple[ArmFoldEvidence, ...],
    challenger: tuple[ArmFoldEvidence, ...],
    getter,
    mode_getter,
    provenance_getter,
    sample_getter,
    missing_getter,
    missing_reason: str,
) -> ComparisonMetric:
    inc_values: list[Decimal] = []
    ch_values: list[Decimal] = []
    inc_modes: set[EvidenceMode] = set()
    ch_modes: set[EvidenceMode] = set()
    sample = 0
    missing = 0
    provenances: list[str] = []

    for arm in incumbent:
        value = getter(arm)
        mode = mode_getter(arm)
        sample += int(sample_getter(arm))
        missing += int(missing_getter(arm))
        provenances.append(str(provenance_getter(arm)))
        if value is None or mode is None or mode is EvidenceMode.UNAVAILABLE:
            missing += 1
            continue
        inc_values.append(Decimal(str(value)))
        inc_modes.add(mode)
    for arm in challenger:
        value = getter(arm)
        mode = mode_getter(arm)
        sample += int(sample_getter(arm))
        missing += int(missing_getter(arm))
        provenances.append(str(provenance_getter(arm)))
        if value is None or mode is None or mode is EvidenceMode.UNAVAILABLE:
            missing += 1
            continue
        ch_values.append(Decimal(str(value)))
        ch_modes.add(mode)

    provenance = "|".join(sorted(set(provenances))) or missing_reason
    if not inc_values or not ch_values:
        return _unavailable_metric(
            name=name,
            direction=direction,
            reason=missing_reason,
            provenance=provenance,
            sample_count=sample,
            missing_count=max(missing, 1),
        )

    modes = inc_modes | ch_modes
    if len(modes) != 1:
        return _unavailable_metric(
            name=name,
            direction=direction,
            reason="heterogeneous_evidence_modes_not_pooled",
            provenance=provenance,
            sample_count=sample,
            missing_count=missing,
        )
    mode = next(iter(modes))
    return _available_metric(
        name=name,
        direction=direction,
        evidence_mode=mode,
        incumbent=_mean_decimal(inc_values),
        challenger=_mean_decimal(ch_values),
        provenance=provenance,
        sample_count=sample,
        missing_count=missing,
    )


def _turnover_from_fills(result: PortfolioReplayResult) -> Decimal:
    notional = Decimal("0")
    for fill in result.fills:
        if fill.is_seed:
            continue
        notional += fill.quantity * fill.price
    if result.starting_cash == 0:
        return Decimal("0")
    return notional / result.starting_cash


def _fill_count(result: PortfolioReplayResult) -> Decimal:
    return Decimal(sum(1 for fill in result.fills if not fill.is_seed))


def _aggregate_actions(
    incumbent: tuple[ArmFoldEvidence, ...],
    challenger: tuple[ArmFoldEvidence, ...],
) -> MetricGroup:
    return MetricGroup(
        group_id=MetricGroupId.ACTIONS,
        metrics=(
            _pair_result_metric(
                name="action_count",
                direction=MetricDirection.NEUTRAL,
                incumbent=incumbent,
                challenger=challenger,
                extractor=_fill_count,
                provenance="portfolio_replay.fills",
            ),
            _pair_result_metric(
                name="turnover",
                direction=MetricDirection.LOWER_IS_BETTER,
                incumbent=incumbent,
                challenger=challenger,
                extractor=_turnover_from_fills,
                provenance="portfolio_replay.fills",
            ),
            _pair_result_metric(
                name="execution_cost",
                direction=MetricDirection.LOWER_IS_BETTER,
                incumbent=incumbent,
                challenger=challenger,
                extractor=lambda r: (
                    r.total_commission
                    if r.status is PortfolioReplayStatus.OK and r.total_commission is not None
                    else None
                ),
                provenance="portfolio_replay.total_commission",
            ),
            _pair_result_metric(
                name="fill_count",
                direction=MetricDirection.NEUTRAL,
                incumbent=incumbent,
                challenger=challenger,
                extractor=_fill_count,
                provenance="portfolio_replay.fills",
            ),
        ),
    )


def _pair_result_metric(
    *,
    name: str,
    direction: MetricDirection,
    incumbent: tuple[ArmFoldEvidence, ...],
    challenger: tuple[ArmFoldEvidence, ...],
    extractor,
    provenance: str,
) -> ComparisonMetric:
    inc_values: list[Decimal] = []
    ch_values: list[Decimal] = []
    sample = 0
    missing = 0
    for arm in incumbent:
        sample += 1
        if arm.result.status is not PortfolioReplayStatus.OK:
            missing += 1
            continue
        value = extractor(arm.result)
        if value is None:
            missing += 1
            continue
        inc_values.append(Decimal(str(value)))
    for arm in challenger:
        sample += 1
        if arm.result.status is not PortfolioReplayStatus.OK:
            missing += 1
            continue
        value = extractor(arm.result)
        if value is None:
            missing += 1
            continue
        ch_values.append(Decimal(str(value)))
    if not inc_values or not ch_values:
        return _unavailable_metric(
            name=name,
            direction=direction,
            reason="portfolio_result_not_ok_or_missing",
            provenance=provenance,
            sample_count=sample,
            missing_count=max(missing, 1),
            availability=MetricAvailability.INCONCLUSIVE,
        )
    return _available_metric(
        name=name,
        direction=direction,
        evidence_mode=EvidenceMode.OBSERVED,
        incumbent=_mean_decimal(inc_values),
        challenger=_mean_decimal(ch_values),
        provenance=provenance,
        sample_count=sample,
        missing_count=missing,
    )


def _nav_return(result: PortfolioReplayResult) -> Decimal | None:
    if result.status is not PortfolioReplayStatus.OK or result.ending_nav is None:
        return None
    if result.starting_cash == 0:
        return None
    return (result.ending_nav - result.starting_cash) / result.starting_cash


def _ending_nav(result: PortfolioReplayResult) -> Decimal | None:
    if result.status is not PortfolioReplayStatus.OK:
        return None
    return result.ending_nav


def _drawdown(result: PortfolioReplayResult) -> Decimal | None:
    if result.status is not PortfolioReplayStatus.OK:
        return None
    return max_drawdown_from_nav_path(result.nav_path)


def _aggregate_portfolio(
    incumbent: tuple[ArmFoldEvidence, ...],
    challenger: tuple[ArmFoldEvidence, ...],
) -> MetricGroup:
    active = _pair_optional_scalar_attr(
        name="active_return",
        direction=MetricDirection.HIGHER_IS_BETTER,
        incumbent=incumbent,
        challenger=challenger,
        getter=lambda arm: arm.telemetry.active_return,
        mode_getter=lambda arm: (
            EvidenceMode.OBSERVED if arm.telemetry.active_return is not None else None
        ),
        provenance_getter=lambda arm: (
            "wp3.active_return"
            if arm.telemetry.active_return is not None
            else "active_return_missing"
        ),
        sample_getter=lambda arm: 1 if arm.telemetry.active_return is not None else 0,
        missing_getter=lambda arm: 0 if arm.telemetry.active_return is not None else 1,
        missing_reason="active_return_not_provided",
    )
    return MetricGroup(
        group_id=MetricGroupId.PORTFOLIO,
        metrics=(
            _pair_result_metric(
                name="nav_return",
                direction=MetricDirection.HIGHER_IS_BETTER,
                incumbent=incumbent,
                challenger=challenger,
                extractor=_nav_return,
                provenance="portfolio_replay.ending_nav",
            ),
            _pair_result_metric(
                name="ending_nav",
                direction=MetricDirection.HIGHER_IS_BETTER,
                incumbent=incumbent,
                challenger=challenger,
                extractor=_ending_nav,
                provenance="portfolio_replay.ending_nav",
            ),
            active,
            _pair_result_metric(
                name="max_drawdown",
                direction=MetricDirection.HIGHER_IS_BETTER,
                incumbent=incumbent,
                challenger=challenger,
                extractor=_drawdown,
                provenance="portfolio_replay.nav_path",
            ),
        ),
    )


def _aggregate_risk(
    incumbent: tuple[ArmFoldEvidence, ...],
    challenger: tuple[ArmFoldEvidence, ...],
) -> MetricGroup:
    tail = _pair_optional_scalar_attr(
        name="tail_loss",
        direction=MetricDirection.HIGHER_IS_BETTER,
        incumbent=incumbent,
        challenger=challenger,
        getter=lambda arm: arm.telemetry.tail_loss,
        mode_getter=lambda arm: (
            EvidenceMode.MODELED if arm.telemetry.tail_loss is not None else None
        ),
        provenance_getter=lambda arm: (
            "wp9.tail" if arm.telemetry.tail_loss is not None else "tail_not_provided"
        ),
        sample_getter=lambda arm: 1 if arm.telemetry.tail_loss is not None else 0,
        missing_getter=lambda arm: 0 if arm.telemetry.tail_loss is not None else 1,
        missing_reason="tail_not_provided",
    )
    scenario = _pair_optional_scalar_attr(
        name="scenario_pnl",
        direction=MetricDirection.HIGHER_IS_BETTER,
        incumbent=incumbent,
        challenger=challenger,
        getter=lambda arm: arm.telemetry.scenario_pnl,
        mode_getter=lambda arm: (
            EvidenceMode.MODELED if arm.telemetry.scenario_pnl is not None else None
        ),
        provenance_getter=lambda arm: (
            "wp9.scenario" if arm.telemetry.scenario_pnl is not None else "scenario_not_provided"
        ),
        sample_getter=lambda arm: 1 if arm.telemetry.scenario_pnl is not None else 0,
        missing_getter=lambda arm: 0 if arm.telemetry.scenario_pnl is not None else 1,
        missing_reason="scenario_not_provided",
    )
    breach_counts_inc = [Decimal(len(arm.telemetry.hard_constraint_breaches)) for arm in incumbent]
    breach_counts_ch = [Decimal(len(arm.telemetry.hard_constraint_breaches)) for arm in challenger]
    hard = _available_metric(
        name="hard_constraint_breach_count",
        direction=MetricDirection.LOWER_IS_BETTER,
        evidence_mode=EvidenceMode.OBSERVED,
        incumbent=_mean_decimal(breach_counts_inc),
        challenger=_mean_decimal(breach_counts_ch),
        provenance="telemetry.hard_constraint_breaches",
        sample_count=len(incumbent) + len(challenger),
        missing_count=0,
    )
    return MetricGroup(
        group_id=MetricGroupId.RISK,
        metrics=(tail, scenario, hard),
    )


def _status_code(label: str) -> Decimal:
    mapping = {
        "ok": Decimal("1"),
        "unknown": Decimal("0"),
        "error": Decimal("-1"),
        "failed": Decimal("-1"),
        "degraded": Decimal("0"),
    }
    return mapping.get(label.lower(), Decimal("0"))


def _aggregate_engine(
    incumbent: tuple[ArmFoldEvidence, ...],
    challenger: tuple[ArmFoldEvidence, ...],
) -> MetricGroup:
    engine = _pair_optional_scalar_attr(
        name="engine_status_code",
        direction=MetricDirection.HIGHER_IS_BETTER,
        incumbent=incumbent,
        challenger=challenger,
        getter=lambda arm: _status_code(arm.telemetry.engine_status),
        mode_getter=lambda arm: EvidenceMode.OBSERVED,
        provenance_getter=lambda arm: f"engine:{arm.telemetry.engine_status}",
        sample_getter=lambda _arm: 1,
        missing_getter=lambda _arm: 0,
        missing_reason="engine_status_missing",
    )
    data = _pair_optional_scalar_attr(
        name="data_status_code",
        direction=MetricDirection.HIGHER_IS_BETTER,
        incumbent=incumbent,
        challenger=challenger,
        getter=lambda arm: _status_code(arm.telemetry.data_status),
        mode_getter=lambda arm: EvidenceMode.OBSERVED,
        provenance_getter=lambda arm: f"data:{arm.telemetry.data_status}",
        sample_getter=lambda _arm: 1,
        missing_getter=lambda _arm: 0,
        missing_reason="data_status_missing",
    )
    failure = _available_metric(
        name="failure_code_count",
        direction=MetricDirection.LOWER_IS_BETTER,
        evidence_mode=EvidenceMode.OBSERVED,
        incumbent=_mean_decimal([Decimal(len(arm.telemetry.failure_codes)) for arm in incumbent]),
        challenger=_mean_decimal([Decimal(len(arm.telemetry.failure_codes)) for arm in challenger]),
        provenance="telemetry.failure_codes",
        sample_count=len(incumbent) + len(challenger),
        missing_count=0,
    )
    replay_ok = _available_metric(
        name="replay_ok_rate",
        direction=MetricDirection.HIGHER_IS_BETTER,
        evidence_mode=EvidenceMode.OBSERVED,
        incumbent=_mean_decimal(
            [
                Decimal("1") if arm.result.status is PortfolioReplayStatus.OK else Decimal("0")
                for arm in incumbent
            ]
        ),
        challenger=_mean_decimal(
            [
                Decimal("1") if arm.result.status is PortfolioReplayStatus.OK else Decimal("0")
                for arm in challenger
            ]
        ),
        provenance="portfolio_replay.status",
        sample_count=len(incumbent) + len(challenger),
        missing_count=0,
    )
    return MetricGroup(
        group_id=MetricGroupId.ENGINE,
        metrics=(engine, data, failure, replay_ok),
    )


def compare_policy_pair(
    *,
    pair: ReplayPairSpec,
    incumbent_folds: tuple[ArmFoldEvidence, ...],
    challenger_folds: tuple[ArmFoldEvidence, ...],
    recorded_at: datetime,
    comparison_id: UUID | None = None,
    min_eval_folds: int = 1,
) -> PolicyComparisonReport:
    """Aggregate paired fold/arm evidence into a complete comparison report.

    Incomplete pairing raises. Undersampled or breached reports remain complete
    in structure but set ``eligible_for_governance=False`` and
    ``promotion_blocked=True``.
    """
    if min_eval_folds < 1:
        raise ValueError("min_eval_folds must be >= 1")
    stamp = require_utc_datetime(recorded_at, field_name="recorded_at")
    shared_hash = pair.shared_manifest.manifest_content_hash
    if pair.incumbent.manifest_content_hash != shared_hash:
        raise ValueError("pair incumbent must reference identical shared manifest")
    if pair.challenger.manifest_content_hash != shared_hash:
        raise ValueError("pair challenger must reference identical shared manifest")

    inc_index = _index_folds(
        incumbent_folds,
        expected_arm=ReplayArmLabel.INCUMBENT,
        shared_manifest_hash=shared_hash,
    )
    ch_index = _index_folds(
        challenger_folds,
        expected_arm=ReplayArmLabel.CHALLENGER,
        shared_manifest_hash=shared_hash,
    )
    if set(inc_index) != set(ch_index):
        raise ValueError("paired fold ids must match across incumbent and challenger")
    if not inc_index:
        raise ValueError("paired fold evidence required")

    fold_ids = tuple(sorted(inc_index))
    ordered_inc = tuple(inc_index[fid] for fid in fold_ids)
    ordered_ch = tuple(ch_index[fid] for fid in fold_ids)

    fold_rows = tuple(
        FoldComparisonEvidence(
            fold_id=fold_id,
            incumbent_result_status=inc_index[fold_id].result.status,
            challenger_result_status=ch_index[fold_id].result.status,
            incumbent_result_content_hash=inc_index[fold_id].result.result_content_hash,
            challenger_result_content_hash=ch_index[fold_id].result.result_content_hash,
        )
        for fold_id in fold_ids
    )

    groups = (
        _aggregate_research(ordered_inc, ordered_ch),
        _aggregate_signal_quality(ordered_inc, ordered_ch),
        _aggregate_forecast(ordered_inc, ordered_ch),
        _aggregate_actions(ordered_inc, ordered_ch),
        _aggregate_portfolio(ordered_inc, ordered_ch),
        _aggregate_risk(ordered_inc, ordered_ch),
        _aggregate_engine(ordered_inc, ordered_ch),
    )
    # Stable group order for hashing / present list.
    groups = tuple(sorted(groups, key=lambda g: g.group_id.value))
    present = tuple(g.group_id.value for g in groups)

    accounting_breach = any(arm.telemetry.accounting_breach for arm in (*ordered_inc, *ordered_ch))
    hard_breach = any(arm.telemetry.hard_constraint_breaches for arm in (*ordered_inc, *ordered_ch))
    any_inconclusive = any(
        arm.result.status is not PortfolioReplayStatus.OK for arm in (*ordered_inc, *ordered_ch)
    )
    undersampled = len(fold_ids) < min_eval_folds

    blockers: list[str] = []
    if undersampled:
        blockers.append(f"undersampled: folds={len(fold_ids)} < min_eval_folds={min_eval_folds}")
    if accounting_breach:
        blockers.append("accounting_breach_visible")
    if hard_breach:
        blockers.append("hard_constraint_breach_visible")
    if any_inconclusive:
        blockers.append("arm_replay_not_ok")

    promotion_blocked = bool(blockers)
    eligible = not promotion_blocked
    if undersampled:
        status = ComparisonReportStatus.UNDERSAMPLED
    elif any_inconclusive:
        status = ComparisonReportStatus.INCONCLUSIVE
    elif promotion_blocked:
        status = ComparisonReportStatus.INCOMPLETE
    else:
        status = ComparisonReportStatus.COMPLETE

    report_id = comparison_id or uuid4()
    draft = PolicyComparisonReport.model_construct(
        schema_version="1.0",
        comparison_id=report_id,
        pair_content_hash=pair.pair_content_hash,
        shared_manifest_content_hash=shared_hash,
        report_content_hash="0" * 64,
        recorded_at=stamp,
        status=status,
        metric_groups=groups,
        folds=fold_rows,
        undersampled=undersampled,
        eligible_for_governance=eligible,
        promotion_blocked=promotion_blocked,
        promotion_blockers=tuple(blockers),
        accounting_breach_visible=accounting_breach,
        hard_constraint_breach_visible=hard_breach,
        metric_groups_present=present,
    )
    digest = policy_comparison_report_content_hash(draft)
    return PolicyComparisonReport.model_validate(
        {**draft.model_dump(mode="python"), "report_content_hash": digest}
    )
