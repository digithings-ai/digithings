"""WP15.3 — assemble authoritative outcome episodes (#2963).

Red coverage: immature horizon, late-known exclusion, excluded/no-op/rejected
lineage, requested/capped/rounded/partial paths, accounting/benchmark/cost/risk
links, unreconciled accounting disables portfolio learning, optional gaps scoped
to components, idempotent assembly, correction supersedes, no source beyond cutoff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.accounting.models import PeriodStatus
from digiquant.olympus.hermes.models.forecast_calibration import (
    ForecastOutcome,
    OutcomeStatus,
    SessionPriceSnapshot,
    forecast_outcome_content_hash,
    forecast_outcome_id,
)
from digiquant.olympus.hermes.models.portfolio_ledger import (
    ApprovedTarget,
    DecisionAction,
    DecisionIntent,
    DecisionReason,
    OrderIntent,
    OrderIntentStatus,
    OrderRejectionReason,
    PaperExecution,
    PortfolioCommit,
    RequestedTarget,
    TargetAdjustment,
    TargetAdjustmentType,
    paper_execution_id,
)
from digiquant.olympus.learning.outcome_assembly import (
    AccountingSlice,
    AssemblyPassResult,
    CostEvidenceRef,
    MaturedForecastBinding,
    OutcomeEpisodeAssembler,
    RiskEvidenceRef,
    SymbolLineage,
    session_close_utc,
)
from digiquant.olympus.learning.outcome_models import (
    AttributionComponent,
    EpisodeDisposition,
    OutcomeQualityCode,
    UnavailableReason,
)
from digiquant.olympus.learning.outcome_store import OutcomeLearningStore

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
_MATURITY = date(2026, 8, 25)
_REF = date(2026, 8, 4)
_HORIZON_END = session_close_utc(_MATURITY)
_FORECAST_ID = UUID("11111111-1111-4111-8111-111111111111")
_SOURCE_RUN = "run-2026-08-04"
_MANDATE = "mandate-daily"
_COMMIT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_DECISION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
_REQUESTED_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
_APPROVED_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
_ORDER_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
_PERIOD_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
_CONTRIB_ID = UUID("10101010-1010-4101-8101-101010101010")


def _snapshot(session: date, price: str = "150.00") -> SessionPriceSnapshot:
    observed = session_close_utc(session)
    return SessionPriceSnapshot(
        session_date=session,
        price=Decimal(price),
        observed_at=observed,
        known_at=observed,
    )


def _outcome_payload(**overrides: object) -> dict[str, object]:
    maturity_session = overrides.get("maturity_session", _MATURITY)
    ref_session = overrides.get("reference_session", _REF)
    ref_snap = overrides.get(
        "reference_snapshot",
        _snapshot(ref_session if isinstance(ref_session, date) else _REF, "140.00"),
    )
    mat_snap = overrides.get(
        "maturity_snapshot",
        _snapshot(maturity_session if isinstance(maturity_session, date) else _MATURITY, "150.00"),
    )
    known_at = overrides.get("known_at", _TS - timedelta(days=1))
    event_time = overrides.get(
        "event_time", session_close_utc(ref_session if isinstance(ref_session, date) else _REF)
    )
    forecast_mean = Decimal("0.05")
    realized = Decimal("0.04")
    residual = realized - forecast_mean
    draft: dict[str, object] = dict(
        base_forecast_id=_FORECAST_ID,
        effective_forecast_id=_FORECAST_ID,
        ticker="AAPL",
        horizon_sessions=21,
        reference_session=ref_session,
        maturity_session=maturity_session,
        reference_snapshot=ref_snap,
        maturity_snapshot=mat_snap,
        forecast_mean_return=forecast_mean,
        realized_return=realized,
        signed_residual=residual,
        positive_label=True,
        status=OutcomeStatus.RESOLVED,
        unavailable_reason=None,
        event_time=event_time,
        known_at=known_at,
    )
    draft.update(overrides)
    payload = {
        "base_forecast_id": str(draft["base_forecast_id"]),
        "effective_forecast_id": str(draft["effective_forecast_id"]),
        "ticker": draft["ticker"],
        "horizon_sessions": draft["horizon_sessions"],
        "reference_session": draft["reference_session"].isoformat(),  # type: ignore[union-attr]
        "maturity_session": draft["maturity_session"].isoformat(),  # type: ignore[union-attr]
        "reference_snapshot": (
            None
            if draft.get("reference_snapshot") is None
            else draft["reference_snapshot"].model_dump(mode="json")  # type: ignore[union-attr]
        ),
        "maturity_snapshot": (
            None
            if draft.get("maturity_snapshot") is None
            else draft["maturity_snapshot"].model_dump(mode="json")  # type: ignore[union-attr]
        ),
        "forecast_mean_return": str(draft["forecast_mean_return"]),
        "realized_return": str(draft["realized_return"]),
        "signed_residual": str(draft["signed_residual"]),
        "positive_label": draft["positive_label"],
        "status": draft["status"].value
        if isinstance(draft["status"], OutcomeStatus)
        else draft["status"],
        "unavailable_reason": draft.get("unavailable_reason"),
        "event_time": draft["event_time"].isoformat(),  # type: ignore[union-attr]
        "known_at": draft["known_at"].isoformat(),  # type: ignore[union-attr]
    }
    content_hash = forecast_outcome_content_hash(payload=payload)
    draft.setdefault("content_hash", content_hash)
    draft.setdefault(
        "outcome_id",
        forecast_outcome_id(
            effective_forecast_id=draft["effective_forecast_id"],  # type: ignore[arg-type]
            maturity_session=draft["maturity_session"],  # type: ignore[arg-type]
            content_hash=content_hash,
        ),
    )
    return draft


def _resolved_outcome(**overrides: object) -> ForecastOutcome:
    return ForecastOutcome(**_outcome_payload(**overrides))


def _binding(**overrides: object) -> MaturedForecastBinding:
    outcome = overrides.pop("outcome", None) or _resolved_outcome()
    fields: dict[str, object] = dict(
        outcome=outcome,
        forecast_id=outcome.effective_forecast_id,
        source_run_id=_SOURCE_RUN,
        mandate_id=_MANDATE,
        effective_at=session_close_utc(_REF),
        policy_version_id="policy-v1",
    )
    fields.update(overrides)
    return MaturedForecastBinding(**fields)


@dataclass
class FakeForecastReader:
    bindings: tuple[MaturedForecastBinding, ...] = ()

    def list_matured_as_of(
        self,
        *,
        as_of: datetime,
        knowledge_cutoff_at: datetime,
    ) -> tuple[MaturedForecastBinding, ...]:
        cutoff = knowledge_cutoff_at
        out: list[MaturedForecastBinding] = []
        for binding in self.bindings:
            outcome = binding.outcome
            if outcome.status is not OutcomeStatus.RESOLVED:
                continue
            if outcome.known_at > cutoff:
                continue
            out.append(binding)
        return tuple(out)


@dataclass
class FakeLedgerReader:
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
class FakeAccountingReader:
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
class FakeCostReader:
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
class FakeRiskReader:
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


def _commit(recorded_at: datetime = _TS - timedelta(days=2)) -> PortfolioCommit:
    return PortfolioCommit(
        id=_COMMIT_ID,
        run_date=_REF,
        policy_version_id="policy-v1",
        effective_at=recorded_at - timedelta(hours=1),
        recorded_at=recorded_at,
    )


def _decision(action: DecisionAction, reason: DecisionReason) -> DecisionIntent:
    return DecisionIntent(
        id=_DECISION_ID,
        portfolio_commit_id=_COMMIT_ID,
        run_date=_REF,
        symbol="AAPL",
        action=action,
        reason=reason,
        effective_at=_TS - timedelta(days=2),
        recorded_at=_TS - timedelta(days=2),
    )


def _requested(weight: str = "0.06") -> RequestedTarget:
    return RequestedTarget(
        id=_REQUESTED_ID,
        decision_intent_id=_DECISION_ID,
        run_date=_REF,
        symbol="AAPL",
        requested_weight=Decimal(weight),
        effective_at=_TS - timedelta(days=2),
        recorded_at=_TS - timedelta(days=2),
    )


def _approved(weight: str = "0.04") -> ApprovedTarget:
    return ApprovedTarget(
        id=_APPROVED_ID,
        requested_target_id=_REQUESTED_ID,
        run_date=_REF,
        symbol="AAPL",
        approved_weight=Decimal(weight),
        effective_at=_TS - timedelta(days=2),
        recorded_at=_TS - timedelta(days=2),
    )


def _order(status: OrderIntentStatus = OrderIntentStatus.EXECUTED) -> OrderIntent:
    return OrderIntent(
        id=_ORDER_ID,
        approved_target_id=_APPROVED_ID,
        run_date=_REF,
        symbol="AAPL",
        quantity=Decimal("10"),
        status=status,
        effective_at=_TS - timedelta(days=2),
        recorded_at=_TS - timedelta(days=2),
        rejection_reason=OrderRejectionReason.RISK_LIMIT
        if status is OrderIntentStatus.REJECTED
        else None,
    )


def _execution() -> PaperExecution:
    executed_at = session_close_utc(_REF) + timedelta(hours=1)
    return PaperExecution(
        id=paper_execution_id(_ORDER_ID, _REF),
        order_intent_id=_ORDER_ID,
        executed_date=_REF,
        symbol="AAPL",
        quantity=Decimal("10"),
        price=Decimal("140.50"),
        fee=Decimal("1.25"),
        slippage=Decimal("-0.50"),
        executed_at=executed_at,
        recorded_at=executed_at,
    )


def _accounting_slice(
    status: PeriodStatus = PeriodStatus.FINAL,
    benchmark: str | None = "0.018",
) -> AccountingSlice:
    return AccountingSlice(
        period_id=_PERIOD_ID,
        contribution_id=_CONTRIB_ID,
        instrument_return=Decimal("0.042"),
        benchmark_return=Decimal(benchmark) if benchmark is not None else None,
        active_return=Decimal("0.024"),
        status=status,
        known_at=_TS - timedelta(days=1),
    )


def _authorized_lineage(**overrides: object) -> SymbolLineage:
    fields: dict[str, object] = dict(
        commit=_commit(),
        decision=_decision(DecisionAction.ADD, DecisionReason.NEW_CONVICTION),
        requested=_requested(),
        approved=_approved(),
        order=_order(),
        execution=_execution(),
        adjustments=(),
    )
    fields.update(overrides)
    return SymbolLineage(**fields)


def _assembler(
    *,
    forecasts: FakeForecastReader,
    ledger: FakeLedgerReader,
    accounting: FakeAccountingReader,
    costs: FakeCostReader | None = None,
    risk: FakeRiskReader | None = None,
    store: OutcomeLearningStore | None = None,
) -> OutcomeEpisodeAssembler:
    return OutcomeEpisodeAssembler(
        store=store or OutcomeLearningStore(),
        forecast_reader=forecasts,
        ledger_reader=ledger,
        accounting_reader=accounting,
        cost_reader=costs or FakeCostReader(),
        risk_reader=risk or FakeRiskReader(),
        recorded_at=_TS,
    )


def test_immature_before_horizon_blocks() -> None:
    future_maturity = date(2026, 9, 30)
    outcome = _resolved_outcome(
        maturity_session=future_maturity,
        maturity_snapshot=_snapshot(future_maturity),
    )
    binding = _binding(outcome=outcome)
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(binding,)),
        ledger=FakeLedgerReader(),
        accounting=FakeAccountingReader(),
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    assert result.blocked == 1
    assert result.assembled == 0
    blocker = result.results[0].blocker
    assert blocker is not None
    assert blocker.reason is UnavailableReason.IMMATURE_HORIZON


def test_late_known_outcome_excluded_from_pass() -> None:
    late_known = _TS + timedelta(days=1)
    outcome = _resolved_outcome(known_at=late_known)
    binding = _binding(outcome=outcome)
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(binding,)),
        ledger=FakeLedgerReader(),
        accounting=FakeAccountingReader(),
    )
    result = asm.assemble_pass(as_of=_TS + timedelta(days=2), knowledge_cutoff_at=_TS)
    assert result.blocked == 0
    assert result.assembled == 0
    assert result.results == ()


def test_excluded_episode_without_fabricated_returns() -> None:
    lineage = SymbolLineage(commit=_commit(), decision=None)
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=FakeAccountingReader(),
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    assert result.assembled == 1
    episode = result.results[0].episode
    assert episode is not None
    assert episode.disposition is EpisodeDisposition.EXCLUDED
    assert episode.realized is None
    assert episode.h9_links is None


def test_no_op_lineage() -> None:
    lineage = _authorized_lineage(
        decision=_decision(DecisionAction.NO_OP, DecisionReason.NO_SIGNAL_CHANGE),
        requested=None,
        approved=None,
        order=None,
        execution=None,
    )
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=FakeAccountingReader(),
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    episode = result.results[0].episode
    assert episode is not None
    assert episode.disposition is EpisodeDisposition.NO_OP


def test_rejected_lineage() -> None:
    lineage = _authorized_lineage(
        decision=_decision(DecisionAction.REJECT, DecisionReason.RISK_CAP_BREACH),
        requested=None,
        approved=None,
        order=None,
        execution=None,
    )
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=FakeAccountingReader(),
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    episode = result.results[0].episode
    assert episode is not None
    assert episode.disposition is EpisodeDisposition.REJECTED


def test_authorized_links_accounting_benchmark_cost_risk() -> None:
    lineage = _authorized_lineage()
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    accounting = FakeAccountingReader(
        slices={("AAPL", _MATURITY): _accounting_slice(benchmark="0.018")}
    )
    expected_id = UUID("20202020-2020-4202-8202-202020202020")
    realized_cost_id = UUID("30303030-3030-4303-8303-303030303030")
    risk_id = UUID("40404040-4040-4404-8404-404040404040")
    costs = FakeCostReader(
        refs={
            _ORDER_ID: CostEvidenceRef(
                expected_cost_id=expected_id,
                realized_cost_id=realized_cost_id,
                known_at=_TS - timedelta(days=1),
            )
        }
    )
    risk = FakeRiskReader(
        refs={
            _COMMIT_ID: RiskEvidenceRef(
                pre_trade_risk_report_id=risk_id,
                known_at=_TS - timedelta(days=1),
            )
        }
    )
    store = OutcomeLearningStore()
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=accounting,
        costs=costs,
        risk=risk,
        store=store,
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    episode = result.results[0].episode
    assert episode is not None
    assert episode.disposition is EpisodeDisposition.AUTHORIZED
    assert episode.realized is not None
    assert episode.realized.benchmark_return == Decimal("0.018")
    assert episode.expected_cost_id == expected_id
    assert episode.realized_cost_id == realized_cost_id
    assert episode.pre_trade_risk_report_id == risk_id
    assert episode.h8_lineage is not None
    assert episode.h8_lineage.requested_weight == Decimal("0.06")
    assert episode.h8_lineage.approved_weight == Decimal("0.04")


def test_capped_lineage_records_adjustment_codes() -> None:
    adjustment = TargetAdjustment(
        id=uuid4(),
        requested_target_id=_REQUESTED_ID,
        run_date=_REF,
        symbol="AAPL",
        adjustment_type=TargetAdjustmentType.SINGLE_NAME_CAP,
        original_value=Decimal("0.06"),
        adjusted_value=Decimal("0.04"),
        reason="single_name_cap",
        effective_at=_TS - timedelta(days=2),
        recorded_at=_TS - timedelta(days=2),
    )
    lineage = _authorized_lineage(adjustments=(adjustment,))
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    accounting = FakeAccountingReader(slices={("AAPL", _MATURITY): _accounting_slice()})
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=accounting,
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    episode = result.results[0].episode
    assert episode is not None
    assert episode.h8_lineage is not None
    assert "single_name_cap" in episode.h8_lineage.adjustment_codes


def test_unreconciled_accounting_disables_portfolio_learning() -> None:
    lineage = _authorized_lineage()
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    accounting = FakeAccountingReader(
        slices={("AAPL", _MATURITY): _accounting_slice(status=PeriodStatus.ESTIMATED)}
    )
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=accounting,
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    episode = result.results[0].episode
    assert episode is not None
    sizing = next(
        e for e in episode.component_eligibility if e.component is AttributionComponent.SIZING
    )
    assert sizing.eligible is False
    assert sizing.unavailable_reason is UnavailableReason.UNRECONCILED_ACCOUNTING


def test_missing_benchmark_affects_only_relevant_components() -> None:
    lineage = _authorized_lineage()
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    accounting = FakeAccountingReader(
        slices={("AAPL", _MATURITY): _accounting_slice(benchmark=None)}
    )
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=accounting,
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    episode = result.results[0].episode
    assert episode is not None
    forecast_eligible = next(
        e for e in episode.component_eligibility if e.component is AttributionComponent.FORECAST
    )
    assert forecast_eligible.eligible is True
    assert any(q.code is OutcomeQualityCode.MISSING_BENCHMARK for q in episode.quality_issues)


def test_idempotent_second_pass_skips() -> None:
    lineage = _authorized_lineage()
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    accounting = FakeAccountingReader(slices={("AAPL", _MATURITY): _accounting_slice()})
    store = OutcomeLearningStore()
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=accounting,
        store=store,
    )
    first = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    second = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    assert first.assembled == 1
    assert second.skipped == 1
    assert second.assembled == 0


def test_correction_supersedes_prior_version() -> None:
    lineage = _authorized_lineage()
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    accounting = FakeAccountingReader(
        slices={("AAPL", _MATURITY): _accounting_slice(benchmark="0.018")}
    )
    store = OutcomeLearningStore()
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=accounting,
        store=store,
    )
    first = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    first_ep = first.results[0].episode
    assert first_ep is not None

    accounting.slices[("AAPL", _MATURITY)] = _accounting_slice(benchmark="0.022")
    second = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    second_ep = second.results[0].episode
    assert second_ep is not None
    assert second_ep.supersedes_version_id == first_ep.episode_version_id
    assert second_ep.episode_version_id != first_ep.episode_version_id


def test_no_source_beyond_cutoff_hides_late_ledger() -> None:
    late_commit = _commit(recorded_at=_TS + timedelta(days=1))
    lineage = SymbolLineage(commit=late_commit, decision=None)
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=FakeAccountingReader(),
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    episode = result.results[0].episode
    assert episode is not None
    assert episode.disposition is EpisodeDisposition.EXCLUDED


def test_authorized_without_accounting_is_blocker_not_fabrication() -> None:
    lineage = _authorized_lineage()
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=FakeAccountingReader(),
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    blocker = result.results[0].blocker
    assert blocker is not None
    assert blocker.reason is UnavailableReason.MISSING_ACCOUNTING
    assert result.results[0].episode is None


def test_rejected_order_without_fill() -> None:
    lineage = _authorized_lineage(
        order=_order(OrderIntentStatus.REJECTED),
        execution=None,
    )
    ledger = FakeLedgerReader(lineages={(_SOURCE_RUN, "AAPL", _REF): lineage})
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=(_binding(),)),
        ledger=ledger,
        accounting=FakeAccountingReader(),
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    episode = result.results[0].episode
    assert episode is not None
    assert episode.disposition is EpisodeDisposition.REJECTED


def test_assembly_pass_result_counts() -> None:
    asm = _assembler(
        forecasts=FakeForecastReader(bindings=()),
        ledger=FakeLedgerReader(),
        accounting=FakeAccountingReader(),
    )
    result = asm.assemble_pass(as_of=_TS, knowledge_cutoff_at=_TS)
    assert isinstance(result, AssemblyPassResult)
    assert result.assembled == 0
    assert result.blocked == 0
    assert result.skipped == 0
