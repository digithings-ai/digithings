"""WP15.3 — assemble authoritative outcome episodes (#2963).

Builds one deterministic :class:`~digiquant.dashboard.learning.outcome_models.OutcomeEpisode`
for every matured typed forecast by joining typed reader protocols only — never
direct legacy-table queries or current-book inference.

Readers are ``typing.Protocol`` boundaries mirroring WP2 ledger, WP3 accounting,
WP5 forecast outcomes, WP7 cost evidence, and WP9 pre-trade risk packages.
Assembly failures return :class:`AssemblyBlocker` without fabricating partial numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from digiquant.dashboard.accounting.io import contribution_row_id
from digiquant.dashboard.accounting.models import PeriodStatus
from digiquant.dashboard.learning.outcome_models import (
    AttributionComponent,
    ComponentEligibility,
    EpisodeDisposition,
    H8TargetLineage,
    H9ExecutionLinks,
    OutcomeEpisode,
    OutcomeQualityCode,
    OutcomeQualityIssue,
    OutcomeTemporalContract,
    RealizedReturnObservation,
    UnavailableReason,
    episode_content_hash,
    episode_version_id,
)
from digiquant.dashboard.learning.outcome_store import OutcomeLearningStore
from digiquant.dashboard.temporal import require_utc_datetime
from digiquant.portfolio.models.forecast_calibration import ForecastOutcome
from digiquant.portfolio.models.portfolio_ledger import (
    DecisionAction,
    OrderIntentStatus,
    PortfolioCommit,
    TargetAdjustment,
)

_SESSION_CLOSE_HOUR_UTC = 20


def session_close_utc(session: date) -> datetime:
    """US equity cash close proxy when only a session date is known."""
    return datetime.combine(
        session,
        time(hour=_SESSION_CLOSE_HOUR_UTC, minute=0),
        tzinfo=UTC,
    )


@dataclass(frozen=True)
class MaturedForecastBinding:
    """Matured forecast plus lineage metadata required for episode assembly."""

    outcome: ForecastOutcome
    forecast_id: UUID
    source_run_id: str
    mandate_id: str
    effective_at: datetime
    evidence_bundle_id: UUID | None = None
    research_state_version_id: UUID | None = None
    context_manifest_id: UUID | None = None
    policy_version_id: str | None = None


@dataclass(frozen=True)
class SymbolLineage:
    """Typed portfolio-ledger slice for one symbol on the decision session."""

    commit: PortfolioCommit | None = None
    decision: object | None = None
    requested: object | None = None
    adjustments: tuple[TargetAdjustment, ...] = ()
    approved: object | None = None
    order: object | None = None
    execution: object | None = None
    holding: object | None = None


@dataclass(frozen=True)
class AccountingSlice:
    """Authoritative realized return slice for one symbol at maturity."""

    period_id: UUID
    contribution_id: UUID
    instrument_return: Decimal
    benchmark_return: Decimal | None
    active_return: Decimal | None
    status: PeriodStatus
    known_at: datetime


@dataclass(frozen=True)
class CostEvidenceRef:
    """Expected/realized cost artifact IDs visible at cutoff."""

    expected_cost_id: UUID | None = None
    realized_cost_id: UUID | None = None
    known_at: datetime | None = None


@dataclass(frozen=True)
class RiskEvidenceRef:
    """Pre-trade risk report visible at cutoff."""

    pre_trade_risk_report_id: UUID | None = None
    known_at: datetime | None = None


@dataclass(frozen=True)
class AssemblyBlocker:
    """Typed assembly failure — never paired with a partial episode."""

    episode_key: str
    forecast_id: UUID
    outcome_id: UUID
    reason: UnavailableReason
    message: str


@dataclass(frozen=True)
class EpisodeAssemblyResult:
    """Per-forecast assembly outcome."""

    outcome_id: UUID
    forecast_id: UUID
    episode_key: str
    episode: OutcomeEpisode | None = None
    blocker: AssemblyBlocker | None = None
    skipped_idempotent: bool = False


@dataclass(frozen=True)
class AssemblyPassResult:
    """Summary of one assembler pass."""

    results: tuple[EpisodeAssemblyResult, ...]
    assembled: int
    blocked: int
    skipped: int


class MaturedForecastReader(Protocol):
    """WP5 — matured forecast outcomes visible at cutoff."""

    def list_matured_as_of(
        self,
        *,
        as_of: datetime,
        knowledge_cutoff_at: datetime,
    ) -> tuple[MaturedForecastBinding, ...]: ...


class PortfolioLedgerReader(Protocol):
    """WP2 — portfolio commit chain for one symbol."""

    def load_symbol_lineage(
        self,
        *,
        source_run_id: str,
        symbol: str,
        session_date: date,
        knowledge_cutoff_at: datetime,
    ) -> SymbolLineage | None: ...


class AccountingSliceReader(Protocol):
    """WP3 — reconciled contribution slice at maturity."""

    def load_contribution_slice(
        self,
        *,
        symbol: str,
        maturity_session: date,
        knowledge_cutoff_at: datetime,
    ) -> AccountingSlice | None: ...


class CostEvidenceReader(Protocol):
    """WP7 — prospective/realized cost IDs for an order."""

    def load_cost_refs(
        self,
        *,
        order_intent_id: UUID,
        knowledge_cutoff_at: datetime,
    ) -> CostEvidenceRef | None: ...


class PreTradeRiskReader(Protocol):
    """WP9 — pre-trade risk report for a commit."""

    def load_risk_ref(
        self,
        *,
        portfolio_commit_id: UUID,
        knowledge_cutoff_at: datetime,
    ) -> RiskEvidenceRef | None: ...


_PORTFOLIO_COMPONENTS: frozenset[AttributionComponent] = frozenset(
    {
        AttributionComponent.SIZING,
        AttributionComponent.TIMING,
        AttributionComponent.EXECUTION,
        AttributionComponent.RESIDUAL,
    }
)


def _episode_key(forecast_id: UUID, horizon_sessions: int) -> str:
    return f"forecast:{forecast_id}:horizon:{horizon_sessions}s"


def _horizon_id(horizon_sessions: int) -> str:
    return f"h-{horizon_sessions}s"


def _disposition_from_lineage(lineage: SymbolLineage | None) -> EpisodeDisposition:
    if lineage is None or lineage.decision is None:
        return EpisodeDisposition.EXCLUDED
    action = lineage.decision.action
    if action is DecisionAction.REJECT:
        return EpisodeDisposition.REJECTED
    if action is DecisionAction.NO_OP:
        return EpisodeDisposition.NO_OP
    if lineage.order is not None and lineage.order.status is OrderIntentStatus.REJECTED:
        return EpisodeDisposition.REJECTED
    if lineage.execution is not None:
        return EpisodeDisposition.AUTHORIZED
    if action in (DecisionAction.ADD, DecisionAction.TRIM, DecisionAction.EXIT):
        return EpisodeDisposition.REJECTED
    return EpisodeDisposition.EXCLUDED


def _adjustment_codes(adjustments: tuple[TargetAdjustment, ...]) -> tuple[str, ...]:
    codes: list[str] = []
    for adj in adjustments:
        code = adj.adjustment_type.value
        if code not in codes:
            codes.append(code)
    return tuple(codes)


def _h8_lineage(lineage: SymbolLineage | None) -> H8TargetLineage | None:
    if lineage is None or lineage.requested is None:
        return None
    requested_weight = lineage.requested.requested_weight
    approved_weight = lineage.approved.approved_weight if lineage.approved is not None else None
    codes = _adjustment_codes(lineage.adjustments)
    if requested_weight is None and approved_weight is None and not codes:
        return None
    return H8TargetLineage(
        requested_weight=requested_weight,
        approved_weight=approved_weight,
        adjustment_codes=codes,
    )


def _h9_links(lineage: SymbolLineage | None) -> H9ExecutionLinks | None:
    if lineage is None or lineage.decision is None or lineage.execution is None:
        return None
    return H9ExecutionLinks(
        action_id=lineage.decision.id,
        order_id=lineage.order.id if lineage.order is not None else None,
        fill_ids=(lineage.execution.id,),
        holding_id=lineage.holding.id if lineage.holding is not None else None,
    )


def _component_eligibility(
    *,
    disposition: EpisodeDisposition,
    accounting: AccountingSlice | None,
    has_execution_cost: bool,
    missing_benchmark: bool,
) -> tuple[ComponentEligibility, ...]:
    entries: list[ComponentEligibility] = []

    forecast_reason: UnavailableReason | None = None
    if disposition is EpisodeDisposition.EXCLUDED:
        forecast_reason = UnavailableReason.EXCLUDED_EPISODE
    elif disposition is EpisodeDisposition.NO_OP:
        forecast_reason = UnavailableReason.NO_OP_EPISODE
    elif disposition is EpisodeDisposition.REJECTED:
        forecast_reason = UnavailableReason.REJECTED_EPISODE

    entries.append(
        ComponentEligibility(
            component=AttributionComponent.FORECAST,
            eligible=forecast_reason is None,
            unavailable_reason=forecast_reason,
        )
    )

    unreconciled = accounting is not None and accounting.status is not PeriodStatus.FINAL

    for component in _PORTFOLIO_COMPONENTS:
        reason: UnavailableReason | None = None
        if disposition is not EpisodeDisposition.AUTHORIZED:
            if disposition is EpisodeDisposition.EXCLUDED:
                reason = UnavailableReason.EXCLUDED_EPISODE
            elif disposition is EpisodeDisposition.NO_OP:
                reason = UnavailableReason.NO_OP_EPISODE
            else:
                reason = UnavailableReason.REJECTED_EPISODE
        elif unreconciled:
            reason = UnavailableReason.UNRECONCILED_ACCOUNTING
        elif component is AttributionComponent.EXECUTION and not has_execution_cost:
            reason = UnavailableReason.MISSING_FILL_DATA

        entries.append(
            ComponentEligibility(
                component=component,
                eligible=reason is None,
                unavailable_reason=reason,
            )
        )

    return tuple(entries)


def _quality_issues(
    *,
    accounting: AccountingSlice | None,
    disposition: EpisodeDisposition,
    missing_benchmark: bool,
    partial_fill: bool,
) -> tuple[OutcomeQualityIssue, ...]:
    issues: list[OutcomeQualityIssue] = []
    if accounting is not None and accounting.status is not PeriodStatus.FINAL:
        issues.append(
            OutcomeQualityIssue(
                code=OutcomeQualityCode.UNRECONCILED_ACCOUNTING,
                message="accounting period is not final",
            )
        )
    if missing_benchmark and disposition is EpisodeDisposition.AUTHORIZED:
        issues.append(
            OutcomeQualityIssue(
                code=OutcomeQualityCode.MISSING_BENCHMARK,
                message="benchmark return unavailable at maturity",
            )
        )
    if partial_fill:
        issues.append(
            OutcomeQualityIssue(
                code=OutcomeQualityCode.PARTIAL_FILL,
                message="order intent rejected or execution missing",
            )
        )
    return tuple(issues)


def _available_at(
    *,
    horizon_end: datetime,
    outcome_known_at: datetime,
    accounting: AccountingSlice | None,
    cost_ref: CostEvidenceRef | None,
    risk_ref: RiskEvidenceRef | None,
) -> datetime:
    stamps = [horizon_end, outcome_known_at]
    if accounting is not None:
        stamps.append(accounting.known_at)
    if cost_ref is not None and cost_ref.known_at is not None:
        stamps.append(cost_ref.known_at)
    if risk_ref is not None and risk_ref.known_at is not None:
        stamps.append(risk_ref.known_at)
    return max(stamps)


class OutcomeEpisodeAssembler:
    """Deterministic episode assembler over typed reader protocols."""

    def __init__(
        self,
        *,
        store: OutcomeLearningStore,
        forecast_reader: MaturedForecastReader,
        ledger_reader: PortfolioLedgerReader,
        accounting_reader: AccountingSliceReader,
        cost_reader: CostEvidenceReader,
        risk_reader: PreTradeRiskReader,
        recorded_at: datetime,
    ) -> None:
        self._store = store
        self._forecast_reader = forecast_reader
        self._ledger_reader = ledger_reader
        self._accounting_reader = accounting_reader
        self._cost_reader = cost_reader
        self._risk_reader = risk_reader
        self._recorded_at = require_utc_datetime(recorded_at, field_name="recorded_at")

    def assemble_pass(
        self,
        *,
        as_of: datetime,
        knowledge_cutoff_at: datetime,
    ) -> AssemblyPassResult:
        bound = require_utc_datetime(as_of, field_name="as_of")
        cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
        bindings = self._forecast_reader.list_matured_as_of(
            as_of=bound,
            knowledge_cutoff_at=cutoff,
        )
        results: list[EpisodeAssemblyResult] = []
        assembled = 0
        blocked = 0
        skipped = 0
        for binding in bindings:
            item = self._assemble_one(
                binding=binding,
                as_of=bound,
                knowledge_cutoff_at=cutoff,
            )
            results.append(item)
            if item.skipped_idempotent:
                skipped += 1
            elif item.blocker is not None:
                blocked += 1
            elif item.episode is not None:
                assembled += 1
        return AssemblyPassResult(
            results=tuple(results),
            assembled=assembled,
            blocked=blocked,
            skipped=skipped,
        )

    def _assemble_one(
        self,
        *,
        binding: MaturedForecastBinding,
        as_of: datetime,
        knowledge_cutoff_at: datetime,
    ) -> EpisodeAssemblyResult:
        outcome = binding.outcome
        episode_key = _episode_key(binding.forecast_id, outcome.horizon_sessions)

        horizon_end = session_close_utc(outcome.maturity_session)
        if horizon_end > as_of:
            blocker = AssemblyBlocker(
                episode_key=episode_key,
                forecast_id=binding.forecast_id,
                outcome_id=outcome.outcome_id,
                reason=UnavailableReason.IMMATURE_HORIZON,
                message="maturity session not reached at as_of",
            )
            return EpisodeAssemblyResult(
                outcome_id=outcome.outcome_id,
                forecast_id=binding.forecast_id,
                episode_key=episode_key,
                blocker=blocker,
            )

        lineage = self._ledger_reader.load_symbol_lineage(
            source_run_id=binding.source_run_id,
            symbol=outcome.ticker,
            session_date=outcome.reference_session,
            knowledge_cutoff_at=knowledge_cutoff_at,
        )
        disposition = _disposition_from_lineage(lineage)

        accounting: AccountingSlice | None = None
        cost_ref: CostEvidenceRef | None = None
        risk_ref: RiskEvidenceRef | None = None

        if disposition is EpisodeDisposition.AUTHORIZED:
            accounting = self._accounting_reader.load_contribution_slice(
                symbol=outcome.ticker,
                maturity_session=outcome.maturity_session,
                knowledge_cutoff_at=knowledge_cutoff_at,
            )
            if accounting is None:
                blocker = AssemblyBlocker(
                    episode_key=episode_key,
                    forecast_id=binding.forecast_id,
                    outcome_id=outcome.outcome_id,
                    reason=UnavailableReason.MISSING_ACCOUNTING,
                    message="authoritative accounting slice missing at maturity",
                )
                return EpisodeAssemblyResult(
                    outcome_id=outcome.outcome_id,
                    forecast_id=binding.forecast_id,
                    episode_key=episode_key,
                    blocker=blocker,
                )
            if lineage is not None and lineage.order is not None:
                cost_ref = self._cost_reader.load_cost_refs(
                    order_intent_id=lineage.order.id,
                    knowledge_cutoff_at=knowledge_cutoff_at,
                )
            if lineage is not None and lineage.commit is not None:
                risk_ref = self._risk_reader.load_risk_ref(
                    portfolio_commit_id=lineage.commit.id,
                    knowledge_cutoff_at=knowledge_cutoff_at,
                )

        missing_benchmark = (
            accounting is not None
            and disposition is EpisodeDisposition.AUTHORIZED
            and accounting.benchmark_return is None
        )
        partial_fill = (
            disposition is EpisodeDisposition.REJECTED
            and lineage is not None
            and lineage.decision is not None
            and lineage.decision.action
            in (DecisionAction.ADD, DecisionAction.TRIM, DecisionAction.EXIT)
        )

        realized: RealizedReturnObservation | None = None
        if disposition is EpisodeDisposition.AUTHORIZED and accounting is not None:
            realized = RealizedReturnObservation(
                instrument_return=accounting.instrument_return,
                benchmark_return=accounting.benchmark_return,
                active_return=accounting.active_return,
                accounting_period_id=accounting.period_id,
                contribution_id=accounting.contribution_id,
            )

        known_at = require_utc_datetime(outcome.known_at, field_name="known_at")
        effective_at = require_utc_datetime(binding.effective_at, field_name="effective_at")
        available_at = _available_at(
            horizon_end=horizon_end,
            outcome_known_at=known_at,
            accounting=accounting,
            cost_ref=cost_ref,
            risk_ref=risk_ref,
        )
        temporal = OutcomeTemporalContract(
            effective_at=effective_at,
            known_at=known_at,
            recorded_at=self._recorded_at,
            horizon_end=horizon_end,
            available_at=available_at,
            replay_as_of=min(as_of, available_at),
        )

        has_execution_cost = cost_ref is not None and cost_ref.realized_cost_id is not None
        component_eligibility = _component_eligibility(
            disposition=disposition,
            accounting=accounting,
            has_execution_cost=has_execution_cost,
            missing_benchmark=missing_benchmark,
        )
        quality_issues = _quality_issues(
            accounting=accounting,
            disposition=disposition,
            missing_benchmark=missing_benchmark,
            partial_fill=partial_fill,
        )

        h8_lineage = _h8_lineage(lineage)
        h9_links = _h9_links(lineage) if disposition is EpisodeDisposition.AUTHORIZED else None

        prior = self._store.select_episode_as_of(
            episode_key=episode_key,
            as_of=as_of,
            knowledge_cutoff_at=knowledge_cutoff_at,
        )
        supersedes = prior.episode_version_id if prior is not None else None

        content_hash = episode_content_hash(
            episode_key=episode_key,
            forecast_id=binding.forecast_id,
            outcome_id=outcome.outcome_id,
            mandate_id=binding.mandate_id,
            instrument_id=outcome.ticker,
            horizon_id=_horizon_id(outcome.horizon_sessions),
            source_run_id=binding.source_run_id,
            disposition=disposition,
            temporal=temporal,
            realized=realized,
            h8_lineage=h8_lineage,
            h9_links=h9_links,
            evidence_bundle_id=binding.evidence_bundle_id,
            research_state_version_id=binding.research_state_version_id,
            context_manifest_id=binding.context_manifest_id,
            policy_version_id=binding.policy_version_id,
            expected_cost_id=cost_ref.expected_cost_id if cost_ref else None,
            realized_cost_id=cost_ref.realized_cost_id if cost_ref else None,
            pre_trade_risk_report_id=risk_ref.pre_trade_risk_report_id if risk_ref else None,
            component_eligibility=component_eligibility,
            quality_issues=quality_issues,
        )

        if prior is not None and prior.content_hash == content_hash:
            return EpisodeAssemblyResult(
                outcome_id=outcome.outcome_id,
                forecast_id=binding.forecast_id,
                episode_key=episode_key,
                episode=prior,
                skipped_idempotent=True,
            )

        version_id = episode_version_id(
            episode_key=episode_key,
            content_hash=content_hash,
            supersedes_version_id=supersedes,
        )

        episode = OutcomeEpisode(
            episode_key=episode_key,
            episode_version_id=version_id,
            content_hash=content_hash,
            supersedes_version_id=supersedes,
            forecast_id=binding.forecast_id,
            outcome_id=outcome.outcome_id,
            mandate_id=binding.mandate_id,
            instrument_id=outcome.ticker,
            horizon_id=_horizon_id(outcome.horizon_sessions),
            source_run_id=binding.source_run_id,
            evidence_bundle_id=binding.evidence_bundle_id,
            research_state_version_id=binding.research_state_version_id,
            context_manifest_id=binding.context_manifest_id,
            policy_version_id=binding.policy_version_id,
            disposition=disposition,
            temporal=temporal,
            h8_lineage=h8_lineage,
            h9_links=h9_links,
            realized=realized,
            expected_cost_id=cost_ref.expected_cost_id if cost_ref else None,
            realized_cost_id=cost_ref.realized_cost_id if cost_ref else None,
            pre_trade_risk_report_id=risk_ref.pre_trade_risk_report_id if risk_ref else None,
            component_eligibility=component_eligibility,
            quality_issues=quality_issues,
        )
        stored = self._store.append_episode(episode)
        return EpisodeAssemblyResult(
            outcome_id=outcome.outcome_id,
            forecast_id=binding.forecast_id,
            episode_key=episode_key,
            episode=stored,
        )


def accounting_slice_from_period(
    *,
    period_id: UUID,
    symbol: str,
    instrument_return: Decimal,
    benchmark_return: Decimal | None,
    active_return: Decimal | None,
    status: PeriodStatus,
    known_at: datetime,
) -> AccountingSlice:
    """Helper for tests and future accounting reader adapters."""
    return AccountingSlice(
        period_id=period_id,
        contribution_id=contribution_row_id(period_id=period_id, symbol=symbol),
        instrument_return=instrument_return,
        benchmark_return=benchmark_return,
        active_return=active_return,
        status=status,
        known_at=require_utc_datetime(known_at, field_name="known_at"),
    )


__all__ = [
    "AccountingSlice",
    "AccountingSliceReader",
    "AssemblyBlocker",
    "AssemblyPassResult",
    "CostEvidenceReader",
    "CostEvidenceRef",
    "EpisodeAssemblyResult",
    "MaturedForecastBinding",
    "MaturedForecastReader",
    "OutcomeEpisodeAssembler",
    "PortfolioLedgerReader",
    "PreTradeRiskReader",
    "RiskEvidenceRef",
    "SymbolLineage",
    "accounting_slice_from_period",
    "session_close_utc",
]
