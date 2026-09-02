"""Deterministic helpers for Integration 4.1 Phase 4 learning/replay lock (#3015).

Composes WP15 outcome episodes → lessons → WP16 replay → comparison → gate →
human decision without production activation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

from digiquant.dashboard.accounting.models import PeriodStatus
from digiquant.research.phases.outcome_maturation import (
    OutcomeMaturationDeps,
    pin_outcome_lesson_for_preflight,
)
from digiquant.portfolio.allocation_hashes import sha256_hex
from digiquant.portfolio.models.forecast_calibration import (
    ForecastOutcome,
    OutcomeStatus,
    SessionPriceSnapshot,
    forecast_outcome_content_hash,
    forecast_outcome_id,
)
from digiquant.portfolio.models.portfolio_ledger import (
    ApprovedTarget,
    DecisionAction,
    DecisionIntent,
    DecisionReason,
    OrderIntent,
    OrderIntentStatus,
    PaperExecution,
    PortfolioCommit,
    RequestedTarget,
    paper_execution_id,
)
from digiquant.dashboard.learning.component_attribution import (
    ComponentAttributor,
    CostAttributionSlice,
    ForecastAttributionSlice,
    TimingDiagnosticsSlice,
)
from digiquant.dashboard.learning.lesson_registry import (
    LessonCompilationPolicy,
    LessonCompiler,
    cohort_key,
)
from digiquant.dashboard.learning.outcome_assembly import (
    AccountingSlice,
    CostEvidenceRef,
    MaturedForecastBinding,
    OutcomeEpisodeAssembler,
    RiskEvidenceRef,
    SymbolLineage,
    session_close_utc,
)
from digiquant.dashboard.learning.outcome_models import (
    AttributionComponent,
    EpisodeDisposition,
    OutcomeEpisode,
)
from digiquant.dashboard.learning.outcome_store import OutcomeLearningStore
from digiquant.dashboard.replay.canonical import (
    cost_hash_from_execution,
    data_hash_from_request,
    execution_policy_hash,
    fill_fraction_hash,
    policy_bundle_content_hash,
    random_seed_hash,
    replay_input_manifest_content_hash,
)
from digiquant.dashboard.replay.comparison import (
    ArmFoldEvidence,
    EvidenceMode,
    MetricDirection,
    OptionalArmTelemetry,
    ResearchTelemetry,
    SignalQualityTelemetry,
    compare_policy_pair,
)
from digiquant.dashboard.replay.governance import (
    AuthenticatedPrincipal,
    ConfidenceBoundRule,
    GateCriterion,
    GateKind,
    HumanAuthoredGateCriteria,
    MetricComparisonKind,
    MissingDataRule,
    evaluate_gate_criteria,
    gate_criteria_content_hash,
    persist_gate_evaluation,
    record_policy_governance_decision,
)
from digiquant.dashboard.replay.governance_models import GovernanceDecisionKind
from digiquant.dashboard.replay.models import (
    ExecutionPolicy,
    FillRecord,
    HoldingSnapshot,
    InstrumentBarSeries,
    NavPoint,
    OhlcvBar,
    PolicyBundle,
    PolicyFamily,
    PolicyVersionRef,
    PortfolioReplayRequest,
    PortfolioReplayResult,
    PortfolioReplayStatus,
    ReplayArmLabel,
    ReplayArmSpec,
    ReplayInputManifest,
    SharedInputIdentity,
    TargetWeight,
    build_replay_pair,
    portfolio_replay_result_content_hash,
)
from digiquant.dashboard.replay.store import PolicyReplayStore
from digiquant.dashboard.replay.walk_forward import (
    WalkForwardScheduleParams,
    assign_episodes_to_fold,
    build_walk_forward_folds,
    verify_fold_assignments,
)

PHASE4_RUN_ID = "run-phase4-3015"
PHASE4_MANDATE = "mandate-daily"
PHASE4_POLICY = "policy-v1"

# Two-instrument multi-date cutoffs (timezone-aware UTC).
_CUTOFF_EARLY = datetime(2026, 9, 2, 20, 0, tzinfo=UTC)
_CUTOFF_LATE = datetime(2026, 9, 16, 20, 0, tzinfo=UTC)
_REPLAY_AS_OF = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

_REF_AAPL = date(2026, 8, 4)
_REF_MSFT = date(2026, 8, 11)
_REF_NOOP = date(2026, 8, 18)
_MAT_AAPL = date(2026, 8, 25)
_MAT_MSFT = date(2026, 9, 1)

_FORECAST_AAPL = UUID("11111111-1111-4111-8111-111111111111")
_FORECAST_MSFT = UUID("22222222-2222-4222-8222-222222222222")
_FORECAST_NOOP = UUID("33333333-3333-4333-8333-333333333333")

_COMMIT_AAPL = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_COMMIT_MSFT = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
_COMMIT_NOOP = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")

_DECISION_AAPL = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
_DECISION_NOOP = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")

_REQUESTED_AAPL = UUID("10101010-1010-4101-8101-101010101010")
_APPROVED_AAPL = UUID("20202020-2020-4202-8202-202020202020")
_ORDER_AAPL = UUID("30303030-3030-4303-8303-303030303030")

_PERIOD_AAPL = UUID("40404040-4040-4404-8404-404040404040")
_CONTRIB_AAPL = UUID("50505050-5050-4505-8505-505050505050")

_EXPECTED_COST = UUID("60606060-6060-4606-8606-606060606060")
_REALIZED_COST = UUID("70707070-7070-4707-8707-707070707070")
_RISK_REPORT = UUID("80808080-8080-4808-8808-808080808080")

_NUMERIC_TOLERANCE = Decimal("0.00000001")
_COMPARISON_ID = UUID("99999999-9999-4999-8999-999999999999")
_CRITERIA_VERSION_ID = UUID("88888888-8888-4888-8888-888888888888")


def _snapshot(session: date, price: str) -> SessionPriceSnapshot:
    observed = session_close_utc(session)
    return SessionPriceSnapshot(
        session_date=session,
        price=Decimal(price),
        observed_at=observed,
        known_at=observed,
    )


def _outcome(
    *,
    forecast_id: UUID,
    ticker: str,
    ref_session: date,
    maturity_session: date,
    ref_price: str,
    mat_price: str,
    forecast_mean: str = "0.05",
    realized: str = "0.04",
    known_at: datetime | None = None,
) -> ForecastOutcome:
    ref_snap = _snapshot(ref_session, ref_price)
    mat_snap = _snapshot(maturity_session, mat_price)
    known = known_at or session_close_utc(maturity_session) + timedelta(hours=6)
    residual = Decimal(realized) - Decimal(forecast_mean)
    positive = Decimal(realized) > 0
    payload = {
        "base_forecast_id": str(forecast_id),
        "effective_forecast_id": str(forecast_id),
        "ticker": ticker,
        "horizon_sessions": 21,
        "reference_session": ref_session.isoformat(),
        "maturity_session": maturity_session.isoformat(),
        "reference_snapshot": ref_snap.model_dump(mode="json"),
        "maturity_snapshot": mat_snap.model_dump(mode="json"),
        "forecast_mean_return": forecast_mean,
        "realized_return": realized,
        "signed_residual": str(residual),
        "positive_label": positive,
        "status": OutcomeStatus.RESOLVED.value,
        "unavailable_reason": None,
        "event_time": session_close_utc(ref_session).isoformat(),
        "known_at": known.isoformat(),
    }
    content_hash = forecast_outcome_content_hash(payload=payload)
    return ForecastOutcome(
        outcome_id=forecast_outcome_id(
            effective_forecast_id=forecast_id,
            maturity_session=maturity_session,
            content_hash=content_hash,
        ),
        base_forecast_id=forecast_id,
        effective_forecast_id=forecast_id,
        ticker=ticker,
        horizon_sessions=21,
        reference_session=ref_session,
        maturity_session=maturity_session,
        reference_snapshot=ref_snap,
        maturity_snapshot=mat_snap,
        forecast_mean_return=Decimal(forecast_mean),
        realized_return=Decimal(realized),
        signed_residual=residual,
        positive_label=positive,
        status=OutcomeStatus.RESOLVED,
        unavailable_reason=None,
        event_time=session_close_utc(ref_session),
        known_at=known,
        content_hash=content_hash,
    )


def _binding(
    outcome: ForecastOutcome, *, source_run: str = PHASE4_RUN_ID
) -> MaturedForecastBinding:
    return MaturedForecastBinding(
        outcome=outcome,
        forecast_id=outcome.effective_forecast_id,
        source_run_id=source_run,
        mandate_id=PHASE4_MANDATE,
        effective_at=session_close_utc(outcome.reference_session),
        policy_version_id=PHASE4_POLICY,
    )


@dataclass
class _FakeAttributionReaders:
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


def _attribution_readers() -> _FakeAttributionReaders:
    return _FakeAttributionReaders(
        forecast=ForecastAttributionSlice(
            forecast_mean_return=Decimal("0.05"),
            realized_return=Decimal("0.04"),
            signed_residual=Decimal("-0.01"),
            positive_label=True,
        ),
        cost=CostAttributionSlice(
            expected_cost_bps=Decimal("12.0"),
            realized_cost_bps=Decimal("18.5"),
        ),
        timing=TimingDiagnosticsSlice(
            latency_ms=Decimal("240"),
            price_drift_bps=Decimal("3.5"),
        ),
    )


@dataclass
class _FakeForecastReader:
    bindings: tuple[MaturedForecastBinding, ...] = ()

    def list_matured_as_of(
        self,
        *,
        as_of: datetime,
        knowledge_cutoff_at: datetime,
    ) -> tuple[MaturedForecastBinding, ...]:
        out: list[MaturedForecastBinding] = []
        for binding in self.bindings:
            outcome = binding.outcome
            if outcome.status is not OutcomeStatus.RESOLVED:
                continue
            if outcome.known_at > knowledge_cutoff_at:
                continue
            out.append(binding)
        return tuple(out)


@dataclass
class _FakeLedgerReader:
    lineages: dict[tuple[str, str, date], SymbolLineage] = field(default_factory=dict)

    def load_symbol_lineage(
        self,
        *,
        source_run_id: str,
        symbol: str,
        session_date: date,
        knowledge_cutoff_at: datetime,
    ) -> SymbolLineage | None:
        key = (source_run_id, symbol.strip().upper(), session_date)
        lineage = self.lineages.get(key)
        if lineage is None:
            return None
        if lineage.commit is not None and lineage.commit.recorded_at > knowledge_cutoff_at:
            return None
        return lineage


@dataclass
class _FakeAccountingReader:
    slices: dict[tuple[str, date], AccountingSlice] = field(default_factory=dict)

    def load_contribution_slice(
        self,
        *,
        symbol: str,
        maturity_session: date,
        knowledge_cutoff_at: datetime,
    ) -> AccountingSlice | None:
        key = (symbol.strip().upper(), maturity_session)
        slice_ = self.slices.get(key)
        if slice_ is None:
            return None
        if slice_.known_at > knowledge_cutoff_at:
            return None
        return slice_


@dataclass
class _FakeCostReader:
    refs: dict[UUID, CostEvidenceRef] = field(default_factory=dict)

    def load_cost_refs(
        self,
        *,
        order_intent_id: UUID,
        knowledge_cutoff_at: datetime,
    ) -> CostEvidenceRef | None:
        ref = self.refs.get(order_intent_id)
        if ref is None:
            return None
        if ref.known_at is not None and ref.known_at > knowledge_cutoff_at:
            return None
        return ref


@dataclass
class _FakeRiskReader:
    refs: dict[UUID, RiskEvidenceRef] = field(default_factory=dict)

    def load_risk_ref(
        self,
        *,
        portfolio_commit_id: UUID,
        knowledge_cutoff_at: datetime,
    ) -> RiskEvidenceRef | None:
        ref = self.refs.get(portfolio_commit_id)
        if ref is None:
            return None
        if ref.known_at is not None and ref.known_at > knowledge_cutoff_at:
            return None
        return ref


def _commit(commit_id: UUID, run_date: date, recorded_at: datetime) -> PortfolioCommit:
    return PortfolioCommit(
        id=commit_id,
        run_date=run_date,
        policy_version_id=PHASE4_POLICY,
        effective_at=recorded_at - timedelta(hours=1),
        recorded_at=recorded_at,
    )


def _decision(
    decision_id: UUID,
    commit_id: UUID,
    run_date: date,
    symbol: str,
    action: DecisionAction,
    reason: DecisionReason,
    recorded_at: datetime,
) -> DecisionIntent:
    return DecisionIntent(
        id=decision_id,
        portfolio_commit_id=commit_id,
        run_date=run_date,
        symbol=symbol,
        action=action,
        reason=reason,
        effective_at=recorded_at - timedelta(hours=1),
        recorded_at=recorded_at,
    )


def _accounting_slice(
    *,
    benchmark: str = "0.018",
    instrument: str = "0.042",
    status: PeriodStatus = PeriodStatus.FINAL,
    known_at: datetime,
) -> AccountingSlice:
    return AccountingSlice(
        period_id=_PERIOD_AAPL,
        contribution_id=_CONTRIB_AAPL,
        instrument_return=Decimal(instrument),
        benchmark_return=Decimal(benchmark),
        active_return=Decimal(instrument) - Decimal(benchmark),
        status=status,
        known_at=known_at,
    )


def _authorized_aapl_lineage(recorded_at: datetime) -> SymbolLineage:
    return SymbolLineage(
        commit=_commit(_COMMIT_AAPL, _REF_AAPL, recorded_at),
        decision=_decision(
            _DECISION_AAPL,
            _COMMIT_AAPL,
            _REF_AAPL,
            "AAPL",
            DecisionAction.ADD,
            DecisionReason.NEW_CONVICTION,
            recorded_at,
        ),
        requested=RequestedTarget(
            id=_REQUESTED_AAPL,
            decision_intent_id=_DECISION_AAPL,
            run_date=_REF_AAPL,
            symbol="AAPL",
            requested_weight=Decimal("0.06"),
            effective_at=recorded_at - timedelta(hours=1),
            recorded_at=recorded_at,
        ),
        approved=ApprovedTarget(
            id=_APPROVED_AAPL,
            requested_target_id=_REQUESTED_AAPL,
            run_date=_REF_AAPL,
            symbol="AAPL",
            approved_weight=Decimal("0.04"),
            effective_at=recorded_at - timedelta(hours=1),
            recorded_at=recorded_at,
        ),
        order=OrderIntent(
            id=_ORDER_AAPL,
            approved_target_id=_APPROVED_AAPL,
            run_date=_REF_AAPL,
            symbol="AAPL",
            quantity=Decimal("10"),
            status=OrderIntentStatus.EXECUTED,
            effective_at=recorded_at - timedelta(hours=1),
            recorded_at=recorded_at,
            rejection_reason=None,
        ),
        execution=PaperExecution(
            id=paper_execution_id(_ORDER_AAPL, _REF_AAPL),
            order_intent_id=_ORDER_AAPL,
            executed_date=_REF_AAPL,
            symbol="AAPL",
            quantity=Decimal("10"),
            price=Decimal("140.50"),
            fee=Decimal("1.25"),
            slippage=Decimal("-0.50"),
            executed_at=session_close_utc(_REF_AAPL) + timedelta(hours=1),
            recorded_at=recorded_at,
        ),
        adjustments=(),
    )


def _noop_aapl_lineage(recorded_at: datetime) -> SymbolLineage:
    return SymbolLineage(
        commit=_commit(_COMMIT_NOOP, _REF_NOOP, recorded_at),
        decision=_decision(
            _DECISION_NOOP,
            _COMMIT_NOOP,
            _REF_NOOP,
            "AAPL",
            DecisionAction.NO_OP,
            DecisionReason.NO_SIGNAL_CHANGE,
            recorded_at,
        ),
        requested=None,
        approved=None,
        order=None,
        execution=None,
        adjustments=(),
    )


def _excluded_msft_lineage(recorded_at: datetime) -> SymbolLineage:
    return SymbolLineage(
        commit=_commit(_COMMIT_MSFT, _REF_MSFT, recorded_at),
        decision=None,
        requested=None,
        approved=None,
        order=None,
        execution=None,
        adjustments=(),
    )


def _bar(day: int, close: str) -> OhlcvBar:
    px = Decimal(close)
    return OhlcvBar(
        ts=datetime(2026, 8, day, tzinfo=UTC),
        open=px,
        high=px + Decimal("1"),
        low=px - Decimal("1"),
        close=px,
        volume=Decimal("1000000"),
    )


def _series(ticker: str, closes: list[str]) -> InstrumentBarSeries:
    return InstrumentBarSeries(
        ticker=ticker,
        bars=tuple(_bar(i + 10, c) for i, c in enumerate(closes)),
    )


def phase4_replay_request(
    *,
    request_id: str = "phase4-req",
    targets: tuple[tuple[str, str], ...] = (("AAPL", "0.35"), ("MSFT", "0.35")),
    commission: str = "0.001",
) -> PortfolioReplayRequest:
    closes = ["100", "101", "102", "103", "104", "105"]
    msft = [str(Decimal(c) * Decimal("1.8")) for c in closes]
    return PortfolioReplayRequest(
        request_id=request_id,
        starting_cash=Decimal("100000"),
        series=(_series("AAPL", closes), _series("MSFT", msft)),
        target_weights=tuple(TargetWeight(ticker=t, weight=Decimal(w)) for t, w in targets),
        execution=ExecutionPolicy(
            commission_rate=Decimal(commission),
            random_seed=42,
            next_bar_execution=True,
        ),
    )


def _ok_replay_result(
    request: PortfolioReplayRequest,
    *,
    ending_nav: str,
    ending_cash: str = "15000",
    commission: str = "75",
) -> PortfolioReplayResult:
    holdings = (
        HoldingSnapshot(
            ticker="AAPL",
            quantity=Decimal("120"),
            last_price=Decimal("105"),
            market_value=Decimal("12600"),
        ),
        HoldingSnapshot(
            ticker="MSFT",
            quantity=Decimal("80"),
            last_price=Decimal("189"),
            market_value=Decimal("15120"),
        ),
    )
    path = (
        NavPoint(ts=datetime(2026, 8, 11, tzinfo=UTC), nav=Decimal("100000")),
        NavPoint(ts=datetime(2026, 8, 15, tzinfo=UTC), nav=Decimal(ending_nav)),
    )
    fills = (
        FillRecord(
            ts=datetime(2026, 8, 12, tzinfo=UTC),
            ticker="AAPL",
            side="buy",
            quantity=Decimal("20"),
            price=Decimal("102"),
            commission=Decimal(commission),
        ),
    )
    draft = PortfolioReplayResult.model_construct(
        schema_version="1.0",
        request_id=request.request_id,
        request_content_hash=request.content_hash(),
        status=PortfolioReplayStatus.OK,
        starting_cash=request.starting_cash,
        ending_cash=Decimal(ending_cash),
        ending_nav=Decimal(ending_nav),
        total_commission=Decimal(commission),
        rebalance_commission=Decimal(commission),
        holdings=holdings,
        fills=fills,
        nav_path=path,
        message="",
        result_content_hash=None,
    )
    digest = portfolio_replay_result_content_hash(draft)
    return PortfolioReplayResult.model_validate(
        {**draft.model_dump(mode="python"), "result_content_hash": digest}
    )


def _manifest(request: PortfolioReplayRequest) -> ReplayInputManifest:
    shared = SharedInputIdentity(
        data_hash=data_hash_from_request(request),
        cost_hash=cost_hash_from_execution(request.execution),
        execution_hash=execution_policy_hash(request.execution),
        random_seed_hash=random_seed_hash(request.execution.random_seed),
        fill_fraction_hash=fill_fraction_hash(request.execution.fill_fraction),
        starting_cash=request.starting_cash,
    )
    dataset_hash = data_hash_from_request(request)
    sources = tuple(
        sorted(
            (
                PolicyVersionRef(
                    family=PolicyFamily.DATA_SOURCE,
                    version_id="bars-v1",
                    content_hash=dataset_hash,
                ),
                PolicyVersionRef(
                    family=PolicyFamily.COST_SCHEDULE,
                    version_id="cost-v1",
                    content_hash=shared.cost_hash,
                ),
            ),
            key=lambda ref: (ref.family.value, ref.version_id),
        )
    )
    content_hash = replay_input_manifest_content_hash(
        manifest_id="phase4-manifest",
        replay_as_of=_REPLAY_AS_OF,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        fold=None,
    )
    return ReplayInputManifest(
        manifest_id="phase4-manifest",
        replay_as_of=_REPLAY_AS_OF,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        manifest_content_hash=content_hash,
        fold=None,
    )


def _arm(
    arm: ReplayArmLabel,
    manifest: ReplayInputManifest,
    *,
    arm_id: str,
    weights_fp: str,
    portfolio_version: str,
) -> ReplayArmSpec:
    bundle = PolicyBundle(
        portfolio_target=PolicyVersionRef(
            family=PolicyFamily.PORTFOLIO_TARGET,
            version_id=portfolio_version,
            content_hash=sha256_hex({"weights_fingerprint": weights_fp}),
        ),
    )
    return ReplayArmSpec(
        arm=arm,
        arm_id=arm_id,
        manifest_content_hash=manifest.manifest_content_hash,
        policy_bundle=bundle,
        weights_fingerprint=weights_fp,
        arm_content_hash=policy_bundle_content_hash(bundle, weights_fingerprint=weights_fp),
    )


def _telemetry(*, tail_loss: str = "-0.06", scenario_pnl: str = "-0.03") -> OptionalArmTelemetry:
    return OptionalArmTelemetry(
        research=ResearchTelemetry(
            calls=8,
            searches=3,
            tokens=900,
            cost_usd=Decimal("0.35"),
            latency_ms=Decimal("720"),
            budget_usd=Decimal("1.00"),
            evidence_mode=EvidenceMode.OBSERVED,
            provenance="wp13.telemetry",
            sample_count=4,
            missing_count=0,
        ),
        signal_quality=SignalQualityTelemetry(
            novelty=Decimal("0.25"),
            conflict=Decimal("0.05"),
            coverage=Decimal("0.85"),
            exploration=Decimal("0.15"),
            staleness_days=Decimal("1"),
            evidence_mode=EvidenceMode.OBSERVED,
            provenance="wp13.signal_quality",
            sample_count=4,
            missing_count=0,
        ),
        forecast_brier=Decimal("0.16"),
        forecast_log_score=Decimal("-0.48"),
        forecast_uncertainty=Decimal("0.20"),
        forecast_evidence_mode=EvidenceMode.OBSERVED,
        forecast_provenance="wp5.calibration",
        forecast_sample_count=8,
        forecast_missing_count=0,
        active_return=Decimal("0.012"),
        benchmark_return=Decimal("0.006"),
        tail_loss=Decimal(tail_loss),
        scenario_pnl=Decimal(scenario_pnl),
        hard_constraint_breaches=(),
        accounting_breach=False,
        engine_status="ok",
        data_status="ok",
        failure_codes=(),
    )


def _criterion(
    *,
    criterion_id: str,
    metric_name: str,
    threshold: str = "0",
    comparison_kind: MetricComparisonKind = MetricComparisonKind.PAIRED_DELTA,
    direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER,
) -> GateCriterion:
    return GateCriterion(
        criterion_id=criterion_id,
        gate_kind=GateKind.PROMOTION,
        metric_name=metric_name,
        cohort="all",
        comparison_kind=comparison_kind,
        direction=direction,
        threshold=Decimal(threshold),
        evidence_mode=EvidenceMode.OBSERVED,
        min_sample_count=1,
        min_folds=1,
        min_duration_days=0,
        missing_data_rule=MissingDataRule.FAIL_CLOSED,
        confidence_bound_rule=ConfidenceBoundRule.REQUIRE_AVAILABLE,
    )


def _criteria(*criteria: GateCriterion) -> HumanAuthoredGateCriteria:
    draft = HumanAuthoredGateCriteria.model_construct(
        schema_version="1.0",
        criteria_key="phase4-golden-v1",
        criteria_version_id=_CRITERIA_VERSION_ID,
        author="human-governance@olympus",
        rationale="pre-versioned Phase 4 golden gate",
        effective_at=_CUTOFF_LATE,
        recorded_at=_CUTOFF_LATE,
        content_hash="0" * 64,
        criteria=tuple(criteria),
        require_identical_manifest=True,
        require_eligible_comparison=True,
        reject_accounting_breach=True,
        reject_hard_constraint_breach=True,
        supersedes_version_id=None,
    )
    digest = gate_criteria_content_hash(draft)
    return HumanAuthoredGateCriteria.model_validate(
        {**draft.model_dump(mode="python"), "content_hash": digest}
    )


def build_phase4_learning_stack(
    *,
    apply_correction: bool = False,
) -> dict[str, Any]:
    """Assemble episodes, attribute, compile lessons at early/late cutoffs."""
    recorded_aapl = _CUTOFF_EARLY - timedelta(days=5)
    recorded_msft = _CUTOFF_EARLY - timedelta(days=4)
    recorded_noop = _CUTOFF_EARLY - timedelta(days=3)
    known_aapl = session_close_utc(_MAT_AAPL) + timedelta(hours=6)
    known_msft = session_close_utc(_MAT_MSFT) + timedelta(hours=6)

    outcome_aapl = _outcome(
        forecast_id=_FORECAST_AAPL,
        ticker="AAPL",
        ref_session=_REF_AAPL,
        maturity_session=_MAT_AAPL,
        ref_price="140.00",
        mat_price="150.00",
        known_at=known_aapl,
    )
    outcome_msft = _outcome(
        forecast_id=_FORECAST_MSFT,
        ticker="MSFT",
        ref_session=_REF_MSFT,
        maturity_session=_MAT_MSFT,
        ref_price="280.00",
        mat_price="290.00",
        known_at=known_msft,
    )
    outcome_noop = _outcome(
        forecast_id=_FORECAST_NOOP,
        ticker="AAPL",
        ref_session=_REF_NOOP,
        maturity_session=_MAT_AAPL,
        ref_price="145.00",
        mat_price="150.00",
        known_at=known_aapl + timedelta(days=2),
    )

    ledger = _FakeLedgerReader(
        lineages={
            (PHASE4_RUN_ID, "AAPL", _REF_AAPL): _authorized_aapl_lineage(recorded_aapl),
            (PHASE4_RUN_ID, "MSFT", _REF_MSFT): _excluded_msft_lineage(recorded_msft),
            (PHASE4_RUN_ID, "AAPL", _REF_NOOP): _noop_aapl_lineage(recorded_noop),
        }
    )
    accounting = _FakeAccountingReader(
        slices={
            ("AAPL", _MAT_AAPL): _accounting_slice(
                benchmark="0.018",
                instrument="0.042",
                known_at=known_aapl - timedelta(hours=2),
            ),
            ("MSFT", _MAT_MSFT): _accounting_slice(
                benchmark="0.012",
                instrument="0.028",
                known_at=known_msft - timedelta(hours=2),
            ),
        }
    )
    costs = _FakeCostReader(
        refs={
            _ORDER_AAPL: CostEvidenceRef(
                expected_cost_id=_EXPECTED_COST,
                realized_cost_id=_REALIZED_COST,
                known_at=recorded_aapl,
            )
        }
    )
    risk = _FakeRiskReader(
        refs={
            _COMMIT_AAPL: RiskEvidenceRef(
                pre_trade_risk_report_id=_RISK_REPORT,
                known_at=recorded_aapl,
            )
        }
    )
    forecasts = _FakeForecastReader(
        bindings=(
            _binding(outcome_aapl),
            _binding(outcome_msft),
            _binding(outcome_noop),
        )
    )

    store = OutcomeLearningStore()
    attr_readers = _attribution_readers()
    early_assembler = OutcomeEpisodeAssembler(
        store=store,
        forecast_reader=forecasts,
        ledger_reader=ledger,
        accounting_reader=accounting,
        cost_reader=costs,
        risk_reader=risk,
        recorded_at=_CUTOFF_EARLY,
    )
    assembler = OutcomeEpisodeAssembler(
        store=store,
        forecast_reader=forecasts,
        ledger_reader=ledger,
        accounting_reader=accounting,
        cost_reader=costs,
        risk_reader=risk,
        recorded_at=_CUTOFF_LATE,
    )
    attributor = ComponentAttributor(
        store=store,
        forecast_reader=attr_readers,
        cost_reader=attr_readers,
        timing_reader=attr_readers,
    )
    policy = LessonCompilationPolicy(
        policy_id="forecast-error-v1",
        component=AttributionComponent.FORECAST,
        metric="forecast_error_bps",
        min_sample=1,
        prior=Decimal("-10.0"),
    )
    compiler = LessonCompiler(store=store)

    first_pass = early_assembler.assemble_pass(
        as_of=_CUTOFF_EARLY,
        knowledge_cutoff_at=_CUTOFF_EARLY,
    )
    for item in first_pass.results:
        if item.episode is not None:
            attributor.attribute_and_persist(item.episode, knowledge_cutoff_at=_CUTOFF_EARLY)

    lesson_cohort = cohort_key(
        next(
            item.episode
            for item in first_pass.results
            if item.episode is not None
            and item.episode.disposition is EpisodeDisposition.AUTHORIZED
        )
    )

    lesson_early = compiler.compile_and_persist(
        policy=policy,
        cohort=lesson_cohort,
        horizon_id="h-21s",
        compilation_cutoff=_CUTOFF_EARLY,
        knowledge_cutoff_at=_CUTOFF_EARLY,
        consuming_run_id=f"{PHASE4_RUN_ID}-late",
    )

    first_aapl_key = f"forecast:{_FORECAST_AAPL}:horizon:21s"
    first_aapl = store.select_episode_as_of(
        episode_key=first_aapl_key,
        as_of=_CUTOFF_EARLY,
        knowledge_cutoff_at=_CUTOFF_EARLY,
    )

    correction_episode = None
    if apply_correction:
        accounting.slices[("AAPL", _MAT_AAPL)] = _accounting_slice(
            benchmark="0.022",
            instrument="0.045",
            known_at=_CUTOFF_EARLY + timedelta(days=1),
        )
        late_assembler = OutcomeEpisodeAssembler(
            store=store,
            forecast_reader=forecasts,
            ledger_reader=ledger,
            accounting_reader=accounting,
            cost_reader=costs,
            risk_reader=risk,
            recorded_at=_CUTOFF_LATE,
        )
        correction_pass = late_assembler.assemble_pass(
            as_of=_CUTOFF_LATE,
            knowledge_cutoff_at=_CUTOFF_LATE,
        )
        correction_episode = correction_pass.results[0].episode
        if correction_episode is not None:
            attributor.attribute_and_persist(
                correction_episode,
                knowledge_cutoff_at=_CUTOFF_LATE,
            )
        assembler = late_assembler

    lesson_late = compiler.compile_and_persist(
        policy=policy,
        cohort=lesson_cohort,
        horizon_id="h-21s",
        compilation_cutoff=_CUTOFF_LATE,
        knowledge_cutoff_at=_CUTOFF_LATE,
        consuming_run_id=f"{PHASE4_RUN_ID}-late",
    )

    maturation_deps = OutcomeMaturationDeps(
        store=store,
        assembler=assembler,
        attributor=attributor,
        compiler=compiler,
        policy=policy,
        cohort=lesson_cohort,
        horizon_id="h-21s",
    )
    pin_early = pin_outcome_lesson_for_preflight(
        maturation_deps,
        knowledge_cutoff_at=_CUTOFF_EARLY,
        consuming_run_id=f"{PHASE4_RUN_ID}-late",
    )
    pin_late = pin_outcome_lesson_for_preflight(
        maturation_deps,
        knowledge_cutoff_at=_CUTOFF_LATE,
        consuming_run_id=f"{PHASE4_RUN_ID}-late",
    )

    episodes_visible_early = _visible_episodes(
        store,
        as_of=_CUTOFF_EARLY,
        knowledge_cutoff_at=_CUTOFF_EARLY,
    )
    episodes_visible_late = _visible_episodes(
        store,
        as_of=_CUTOFF_LATE,
        knowledge_cutoff_at=_CUTOFF_LATE,
    )

    return {
        "store": store,
        "first_pass": first_pass,
        "first_aapl": first_aapl,
        "correction_episode": correction_episode,
        "lesson_early": lesson_early,
        "lesson_late": lesson_late,
        "pin_early": pin_early,
        "pin_late": pin_late,
        "episodes_visible_early": episodes_visible_early,
        "episodes_visible_late": episodes_visible_late,
        "accounting": accounting,
        "assembler": assembler,
        "attributor": attributor,
        "compiler": compiler,
        "maturation_deps": maturation_deps,
    }


def build_phase4_replay_evidence(
    *,
    accounting_breach: bool = False,
    challenger_nav: str = "108000",
) -> dict[str, Any]:
    """Paired replay comparison + gate evaluations (eligible/ineligible/insufficient)."""
    request = phase4_replay_request(request_id="phase4-inc")
    ch_request = phase4_replay_request(
        request_id="phase4-ch",
        targets=(("AAPL", "0.45"), ("MSFT", "0.25")),
    )
    manifest = _manifest(request)
    ch_manifest = _manifest(ch_request)
    assert manifest.manifest_content_hash == ch_manifest.manifest_content_hash

    incumbent = _arm(
        ReplayArmLabel.INCUMBENT,
        manifest,
        arm_id="inc",
        weights_fp="w-inc-phase4",
        portfolio_version="incumbent@v1",
    )
    challenger = _arm(
        ReplayArmLabel.CHALLENGER,
        manifest,
        arm_id="ch",
        weights_fp="w-ch-phase4",
        portfolio_version="challenger@v1",
    )
    pair = build_replay_pair(
        pair_id="phase4-pair",
        shared_manifest=manifest,
        incumbent=incumbent,
        challenger=challenger,
    )
    assert pair.shared_manifest.manifest_content_hash == manifest.manifest_content_hash

    tel_inc = _telemetry()
    tel_ch = _telemetry()
    if accounting_breach:
        tel_ch = tel_ch.model_copy(update={"accounting_breach": True})

    inc_result = _ok_replay_result(request, ending_nav="105000")
    ch_result = _ok_replay_result(ch_request, ending_nav=challenger_nav)

    report = compare_policy_pair(
        pair=pair,
        incumbent_folds=(
            ArmFoldEvidence(
                arm=ReplayArmLabel.INCUMBENT,
                fold_id="fold-1",
                manifest_content_hash=manifest.manifest_content_hash,
                request_content_hash=request.content_hash(),
                result=inc_result,
                telemetry=tel_inc,
            ),
        ),
        challenger_folds=(
            ArmFoldEvidence(
                arm=ReplayArmLabel.CHALLENGER,
                fold_id="fold-1",
                manifest_content_hash=manifest.manifest_content_hash,
                request_content_hash=ch_request.content_hash(),
                result=ch_result,
                telemetry=tel_ch,
            ),
        ),
        recorded_at=_CUTOFF_LATE,
        comparison_id=_COMPARISON_ID,
        min_eval_folds=1,
    )

    criteria_eligible = _criteria(
        _criterion(criterion_id="nav-delta", metric_name="ending_nav", threshold="0"),
    )
    criteria_insufficient = _criteria(
        _criterion(criterion_id="missing-metric", metric_name="does_not_exist", threshold="0"),
    )

    eval_eligible = evaluate_gate_criteria(
        criteria=criteria_eligible,
        report=report,
        recorded_at=_CUTOFF_LATE,
    )
    eval_ineligible = evaluate_gate_criteria(
        criteria=criteria_eligible,
        report=compare_policy_pair(
            pair=pair,
            incumbent_folds=(
                ArmFoldEvidence(
                    arm=ReplayArmLabel.INCUMBENT,
                    fold_id="fold-1",
                    manifest_content_hash=manifest.manifest_content_hash,
                    request_content_hash=request.content_hash(),
                    result=inc_result,
                    telemetry=tel_inc,
                ),
            ),
            challenger_folds=(
                ArmFoldEvidence(
                    arm=ReplayArmLabel.CHALLENGER,
                    fold_id="fold-1",
                    manifest_content_hash=manifest.manifest_content_hash,
                    request_content_hash=ch_request.content_hash(),
                    result=ch_result,
                    telemetry=tel_ch.model_copy(update={"accounting_breach": True}),
                ),
            ),
            recorded_at=_CUTOFF_LATE,
            comparison_id=_COMPARISON_ID,
            min_eval_folds=1,
        ),
        recorded_at=_CUTOFF_LATE,
    )
    eval_insufficient = evaluate_gate_criteria(
        criteria=criteria_insufficient,
        report=report,
        recorded_at=_CUTOFF_LATE,
    )

    replay_store = PolicyReplayStore()
    replay_store.append_manifest(manifest, recorded_at=_CUTOFF_LATE)
    replay_store.append_pair(pair, recorded_at=_CUTOFF_LATE)
    persisted_eval = persist_gate_evaluation(
        replay_store,
        criteria=criteria_eligible,
        report=report,
        detail=eval_eligible,
    )

    decision = None
    if eval_eligible.eligible_for_human_review:
        decision = record_policy_governance_decision(
            replay_store,
            principal=AuthenticatedPrincipal(
                subject="key:phase4-reviewer",
                principal_kind="api_key",
            ),
            evaluation_id=persisted_eval.evaluation_id,
            decision_kind=GovernanceDecisionKind.APPROVE,
            rationale="golden fixture approval — record only",
            recorded_at=_CUTOFF_LATE,
        )

    return {
        "request": request,
        "manifest": manifest,
        "pair": pair,
        "report": report,
        "inc_result": inc_result,
        "ch_result": ch_result,
        "eval_eligible": eval_eligible,
        "eval_ineligible": eval_ineligible,
        "eval_insufficient": eval_insufficient,
        "replay_store": replay_store,
        "decision": decision,
    }


def _visible_episodes(
    store: OutcomeLearningStore,
    *,
    as_of: datetime,
    knowledge_cutoff_at: datetime,
) -> tuple[OutcomeEpisode, ...]:
    """Newest visible version per episode_key at cutoff."""
    by_key: dict[str, OutcomeEpisode] = {}
    for episode in store.list_episode_versions():
        if episode.temporal.available_at > as_of:
            continue
        if episode.temporal.known_at > knowledge_cutoff_at:
            continue
        current = by_key.get(episode.episode_key)
        if current is None or episode.temporal.available_at >= current.temporal.available_at:
            by_key[episode.episode_key] = episode
    return tuple(sorted(by_key.values(), key=lambda e: e.episode_key))


def build_phase4_walk_forward(episodes: tuple[OutcomeEpisode, ...]) -> dict[str, Any]:
    """Build purged walk-forward folds from golden episodes."""
    params = WalkForwardScheduleParams(
        params_id="phase4-wf-v1",
        train_days=30,
        eval_days=7,
        calibration_days=0,
        step_days=7,
        embargo_days=3,
        purge_horizon_days=21,
        min_train_episodes=1,
        min_eval_episodes=1,
    )
    build = build_walk_forward_folds(
        episodes=episodes,
        replay_as_of=_REPLAY_AS_OF,
        params=params,
        history_start=date(2026, 1, 1),
        history_end=date(2026, 9, 30),
    )
    plan = None
    if build.status.value == "ok" and build.folds:
        fold = build.folds[0].fold
        plan = assign_episodes_to_fold(
            fold=fold,
            episodes=episodes,
            replay_as_of=_REPLAY_AS_OF,
        )
        verify_fold_assignments(
            plan,
            episode_by_key={ep.episode_key: ep for ep in episodes},
            replay_as_of=_REPLAY_AS_OF,
        )
    return {"build": build, "plan": plan, "params": params}


def run_phase4_composition(*, apply_correction: bool = True) -> dict[str, Any]:
    """Full Phase 4 closed loop for golden assertions."""
    learning = build_phase4_learning_stack(apply_correction=apply_correction)
    replay = build_phase4_replay_evidence()
    episodes = _visible_episodes(
        learning["store"],
        as_of=_CUTOFF_LATE,
        knowledge_cutoff_at=_CUTOFF_LATE,
    )
    walk_forward = build_phase4_walk_forward(episodes)

    rerun = build_phase4_replay_evidence()
    return {
        **learning,
        **replay,
        "walk_forward": walk_forward,
        "rerun_report_hash": rerun["report"].report_content_hash,
        "rerun_inc_hash": rerun["inc_result"].result_content_hash,
        "cutoff_early": _CUTOFF_EARLY,
        "cutoff_late": _CUTOFF_LATE,
    }


__all__ = [
    "PHASE4_RUN_ID",
    "PHASE4_MANDATE",
    "_NUMERIC_TOLERANCE",
    "build_phase4_learning_stack",
    "build_phase4_replay_evidence",
    "build_phase4_walk_forward",
    "phase4_replay_request",
    "run_phase4_composition",
]
