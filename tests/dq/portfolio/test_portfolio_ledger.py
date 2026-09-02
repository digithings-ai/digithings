"""Tests for the append-only portfolio lineage contracts (#2415, OLY-REV-009).

Covers the full replayable chain — PortfolioCommit -> DecisionIntent ->
RequestedTarget -> TargetAdjustment -> ApprovedTarget -> OrderIntent ->
PaperExecution -> HoldingLot — with fixtures for add, trim, exit, no-op,
rejection, cap, rounding, carry, and supersession, plus the immutability,
idempotency, and never-coerced-to-zero invariants called out in the issue's
acceptance criteria.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from digiquant.olympus.hermes.models.portfolio_ledger import (
    ApprovedTarget,
    DecisionAction,
    DecisionIntent,
    DecisionReason,
    HoldingLot,
    HoldingLotStatus,
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
from digiquant.olympus.tenancy import house_workspace_id
from pydantic import ValidationError

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 8, 14)


def _ts(hour: int = 21, minute: int = 0) -> datetime:
    return datetime(2026, 8, 14, hour, minute, tzinfo=UTC)


def make_commit(**overrides: object) -> PortfolioCommit:
    fields = dict(
        id=uuid4(),
        run_date=RUN_DATE,
        policy_version_id="policy-v1",
        effective_at=_ts(),
        recorded_at=_ts(),
    )
    fields.update(overrides)
    return PortfolioCommit(**fields)


def make_decision(
    action: DecisionAction, reason: DecisionReason, **overrides: object
) -> DecisionIntent:
    fields = dict(
        id=uuid4(),
        portfolio_commit_id=uuid4(),
        run_date=RUN_DATE,
        symbol="AAPL",
        action=action,
        reason=reason,
        effective_at=_ts(),
        recorded_at=_ts(),
    )
    fields.update(overrides)
    return DecisionIntent(**fields)


class TestPortfolioLedgerModel:
    """Known limitation (accepted, LOW severity) — see the ``PortfolioLedgerModel``
    docstring in ``portfolio_ledger.py``. Pinned here as a regression test so the gap
    stays a documented, tested fact about upstream Pydantic v2 rather than something
    that silently gets "fixed" by a future refactor's assumptions, or silently
    reappears as a surprise if a caller ever does reach for ``model_copy``."""

    def test_defaults_workspace_id_to_house(self) -> None:
        """T0 (#5-T0 / #c326219d): house pipeline omits workspace_id; default is house."""
        commit = make_commit()
        assert commit.workspace_id == house_workspace_id()

    def test_accepts_stamped_workspace_id_on_read_back(self) -> None:
        """Writers stamp workspace_id before insert; extra=forbid must not reject it.

        Without the field on PortfolioLedgerModel, model_validate of PostgREST
        rows degraded H9 cost-liquidity evidence (#c326219d).
        """
        overlay = uuid4()
        commit = make_commit(workspace_id=overlay)
        assert commit.workspace_id == overlay
        # Wire form uses a UUID string (same as PostgREST JSON).
        payload = commit.model_dump(mode="json")
        assert payload["workspace_id"] == str(overlay)
        roundtrip = PortfolioCommit.model_validate(payload)
        assert roundtrip.workspace_id == overlay

    def test_model_copy_bypasses_freeze_and_validation(self) -> None:
        commit = make_commit()

        # Construction rejects self-supersession, per validate_lifecycle.
        with pytest.raises(ValidationError):
            make_commit(id=commit.id, supersedes_id=commit.id)

        # Confirm frozen=True is actually live on this instance (see
        # test_frozen_prevents_mutation_after_execution / test_frozen_raises_on_mutation
        # for the same guard on OrderIntent/PaperExecution) before showing model_copy
        # routes around it below.
        with pytest.raises(ValidationError):
            commit.supersedes_id = commit.id  # type: ignore[misc]

        # model_copy(update=...) is a shallow field copy, not re-validated
        # construction: it bypasses both the frozen assignment guard just confirmed
        # above *and* validate_lifecycle (no error on the same self-supersede case that
        # __init__ rejects above). This is expected Pydantic v2 behavior on any frozen
        # model, not specific to PortfolioCommit or this module.
        copied = commit.model_copy(update={"supersedes_id": commit.id})
        assert copied.supersedes_id == commit.id


class TestDecimalFieldsRejectNonFiniteValues:
    """Weight, Quantity, PositiveQuantity, and PositivePrice all pin
    ``allow_inf_nan=False`` explicitly (CodeRabbit review on #2432): Pydantic v2's
    implicit default for a constrained Decimal field is not a reliable guarantee across
    versions, and a NaN/Infinity slipping through any of these would break every
    downstream arithmetic comparison (``ge``/``le``/``gt`` all evaluate as false against
    NaN) without ever raising."""

    def test_weight_rejects_infinity(self) -> None:
        with pytest.raises(ValidationError):
            RequestedTarget(
                id=uuid4(),
                decision_intent_id=uuid4(),
                run_date=RUN_DATE,
                symbol="AAPL",
                requested_weight=Decimal("Infinity"),
                effective_at=_ts(),
                recorded_at=_ts(),
            )

    def test_quantity_rejects_nan(self) -> None:
        with pytest.raises(ValidationError):
            RequestedTarget(
                id=uuid4(),
                decision_intent_id=uuid4(),
                run_date=RUN_DATE,
                symbol="AAPL",
                requested_quantity=Decimal("NaN"),
                effective_at=_ts(),
                recorded_at=_ts(),
            )

    def test_positive_quantity_rejects_infinity(self) -> None:
        with pytest.raises(ValidationError):
            OrderIntent(
                id=uuid4(),
                approved_target_id=uuid4(),
                run_date=RUN_DATE,
                symbol="AAPL",
                quantity=Decimal("Infinity"),
                status=OrderIntentStatus.PENDING,
                effective_at=_ts(),
                recorded_at=_ts(),
            )

    def test_positive_price_rejects_nan(self) -> None:
        order_intent_id = uuid4()
        executed_date = RUN_DATE
        with pytest.raises(ValidationError):
            PaperExecution(
                id=paper_execution_id(order_intent_id, executed_date),
                order_intent_id=order_intent_id,
                executed_date=executed_date,
                symbol="AAPL",
                quantity=Decimal("100"),
                price=Decimal("NaN"),
                executed_at=_ts(),
                recorded_at=_ts(),
            )


class TestPortfolioCommit:
    def test_root_commit_has_no_supersedes_id(self) -> None:
        commit = make_commit()  # no raise
        assert commit.supersedes_id is None

    def test_supersedes_id_ok(self) -> None:
        """A changed same-date commit is a new row pointing back at the one it
        replaces — currency is structural (the partial unique index), not a status."""
        commit = make_commit(supersedes_id=uuid4())
        assert commit.supersedes_id is not None

    def test_self_supersession_raises(self) -> None:
        shared_id = uuid4()
        with pytest.raises(ValidationError):
            make_commit(id=shared_id, supersedes_id=shared_id)

    def test_non_utc_effective_at_rejected(self) -> None:
        skewed = datetime(2026, 8, 14, 21, 0, tzinfo=timezone(timedelta(hours=2)))
        with pytest.raises(ValidationError):
            make_commit(effective_at=skewed)


class TestDecisionIntentActionReason:
    """DecisionIntent.reason is required (never bare null) and must match action."""

    @pytest.mark.parametrize(
        ("action", "reason"),
        [
            (DecisionAction.ADD, DecisionReason.NEW_CONVICTION),
            (DecisionAction.TRIM, DecisionReason.CONVICTION_REDUCED),
            (DecisionAction.EXIT, DecisionReason.THESIS_INVALIDATED),
            (DecisionAction.NO_OP, DecisionReason.NO_SIGNAL_CHANGE),
            (DecisionAction.NO_OP, DecisionReason.DATA_UNAVAILABLE),
            (DecisionAction.REJECT, DecisionReason.RISK_CAP_BREACH),
            (DecisionAction.REJECT, DecisionReason.LOW_CONVICTION),
            (DecisionAction.REJECT, DecisionReason.DATA_UNAVAILABLE),
        ],
    )
    def test_valid_action_reason_pairs(
        self, action: DecisionAction, reason: DecisionReason
    ) -> None:
        make_decision(action, reason)

    def test_mismatched_action_reason_raises(self) -> None:
        with pytest.raises(ValidationError):
            make_decision(DecisionAction.ADD, DecisionReason.THESIS_INVALIDATED)

    def test_reason_field_is_required(self) -> None:
        with pytest.raises(ValidationError):
            DecisionIntent(
                id=uuid4(),
                portfolio_commit_id=uuid4(),
                run_date=RUN_DATE,
                symbol="AAPL",
                action=DecisionAction.NO_OP,
                effective_at=_ts(),
                recorded_at=_ts(),
            )  # type: ignore[call-arg]

    def test_no_op_requires_reason_not_null(self) -> None:
        """A no-op decision must carry a reason; there is no valid null-reason path."""
        decision = make_decision(DecisionAction.NO_OP, DecisionReason.NO_SIGNAL_CHANGE)
        assert decision.reason is not None

    def test_reject_requires_reason_not_null(self) -> None:
        decision = make_decision(DecisionAction.REJECT, DecisionReason.LOW_CONVICTION)
        assert decision.reason is not None


class TestRequestedTargetPresence:
    def test_weight_only_ok(self) -> None:
        RequestedTarget(
            id=uuid4(),
            decision_intent_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            requested_weight=Decimal("0.05"),
            effective_at=_ts(),
            recorded_at=_ts(),
        )

    def test_quantity_only_ok(self) -> None:
        RequestedTarget(
            id=uuid4(),
            decision_intent_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            requested_quantity=Decimal("100"),
            effective_at=_ts(),
            recorded_at=_ts(),
        )

    def test_explicit_zero_weight_is_legal_full_exit(self) -> None:
        """Explicit 0 (a real full-exit target) is distinct from missing/None."""
        target = RequestedTarget(
            id=uuid4(),
            decision_intent_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            requested_weight=Decimal("0"),
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        assert target.requested_weight == Decimal("0")

    def test_both_absent_raises(self) -> None:
        with pytest.raises(ValidationError):
            RequestedTarget(
                id=uuid4(),
                decision_intent_id=uuid4(),
                run_date=RUN_DATE,
                symbol="AAPL",
                effective_at=_ts(),
                recorded_at=_ts(),
            )

    def test_both_present_raises(self) -> None:
        """Exactly one of weight/quantity is legal (XOR, not OR): carrying both would
        leave every downstream TargetAdjustment against this row dimensionally
        ambiguous. Mirrors the migration's presence CHECK exactly."""
        with pytest.raises(ValidationError):
            RequestedTarget(
                id=uuid4(),
                decision_intent_id=uuid4(),
                run_date=RUN_DATE,
                symbol="AAPL",
                requested_weight=Decimal("0.05"),
                requested_quantity=Decimal("100"),
                effective_at=_ts(),
                recorded_at=_ts(),
            )

    def test_missing_quantity_stays_none_never_coerced_to_zero(self) -> None:
        target = RequestedTarget(
            id=uuid4(),
            decision_intent_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            requested_weight=Decimal("0.05"),
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        assert target.requested_quantity is None
        assert target.requested_quantity != Decimal("0")


class TestTargetAdjustmentCapRoundingCarry:
    def _adjustment(
        self, adjustment_type: TargetAdjustmentType, **overrides: object
    ) -> TargetAdjustment:
        fields = dict(
            id=uuid4(),
            requested_target_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            adjustment_type=adjustment_type,
            original_value=Decimal("0.10"),
            adjusted_value=Decimal("0.08"),
            reason="risk cap binds at 8% gross",
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        fields.update(overrides)
        return TargetAdjustment(**fields)

    def test_cap_reduces_value(self) -> None:
        adj = self._adjustment(TargetAdjustmentType.CAP)
        assert adj.adjusted_value < adj.original_value

    def test_cap_increasing_value_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._adjustment(
                TargetAdjustmentType.CAP,
                original_value=Decimal("0.05"),
                adjusted_value=Decimal("0.08"),
            )

    def test_correlation_dedup_reduces_value(self) -> None:
        adj = self._adjustment(
            TargetAdjustmentType.CORRELATION_DEDUP,
            reason="trimmed for overlap with an existing correlated position",
        )
        assert adj.adjusted_value < adj.original_value

    def test_correlation_dedup_increasing_value_raises(self) -> None:
        """Regression for #2417 CodeRabbit review on #2434: CORRELATION_DEDUP was
        missing from ``_REDUCING_ADJUSTMENT_TYPES``, so ``validate_lifecycle`` let
        an increasing correlation-dedup record through unchallenged."""
        with pytest.raises(ValidationError):
            self._adjustment(
                TargetAdjustmentType.CORRELATION_DEDUP,
                original_value=Decimal("0.05"),
                adjusted_value=Decimal("0.08"),
                reason="trimmed for overlap with an existing correlated position",
            )

    def test_rounding_adjustment_ok(self) -> None:
        adj = self._adjustment(
            TargetAdjustmentType.ROUNDING,
            original_value=Decimal("100.4"),
            adjusted_value=Decimal("100"),
            reason="round to whole share lot",
        )
        assert adj.adjustment_type is TargetAdjustmentType.ROUNDING

    def test_carry_adjustment_ok(self) -> None:
        adj = self._adjustment(
            TargetAdjustmentType.CARRY,
            original_value=Decimal("0.05"),
            adjusted_value=Decimal("0.05"),
            reason="carried unchanged from prior run_date, fingerprint_skip",
        )
        assert adj.adjustment_type is TargetAdjustmentType.CARRY

    def test_reason_required_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            self._adjustment(TargetAdjustmentType.CAP, reason="")


class TestApprovedTargetSupersession:
    def _approved(self, **overrides: object) -> ApprovedTarget:
        fields = dict(
            id=uuid4(),
            requested_target_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            approved_weight=Decimal("0.05"),
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        fields.update(overrides)
        return ApprovedTarget(**fields)

    def test_both_absent_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._approved(approved_weight=None)

    def test_self_supersession_raises(self) -> None:
        shared_id = uuid4()
        with pytest.raises(ValidationError):
            self._approved(id=shared_id, supersedes_id=shared_id)

    def test_changed_same_date_target_supersedes_prior(self) -> None:
        """A changed same-date target is a new row pointing back to the one it replaces."""
        first = self._approved(approved_weight=Decimal("0.05"))
        second = self._approved(approved_weight=Decimal("0.08"), supersedes_id=first.id)
        assert second.supersedes_id == first.id
        assert second.approved_weight != first.approved_weight


class TestOrderIntentLifecycle:
    def _order(self, **overrides: object) -> OrderIntent:
        fields = dict(
            id=uuid4(),
            approved_target_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            quantity=Decimal("100"),
            status=OrderIntentStatus.PENDING,
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        fields.update(overrides)
        return OrderIntent(**fields)

    def test_pending_ok(self) -> None:
        order = self._order()
        assert order.status is OrderIntentStatus.PENDING

    def test_pending_forbids_rejection_reason(self) -> None:
        with pytest.raises(ValidationError):
            self._order(rejection_reason=OrderRejectionReason.STALE_TARGET)

    def test_pending_with_supersedes_id_ok(self) -> None:
        """supersedes_id is a backward link orthogonal to status: a still-pending order
        can legally point back at the row it replaces."""
        order = self._order(supersedes_id=uuid4())
        assert order.supersedes_id is not None
        assert order.status is OrderIntentStatus.PENDING

    def test_self_supersession_raises(self) -> None:
        shared_id = uuid4()
        with pytest.raises(ValidationError):
            self._order(id=shared_id, supersedes_id=shared_id)

    def test_rejected_requires_rejection_reason(self) -> None:
        with pytest.raises(ValidationError):
            self._order(status=OrderIntentStatus.REJECTED)

    def test_rejected_with_reason_ok(self) -> None:
        order = self._order(
            status=OrderIntentStatus.REJECTED,
            rejection_reason=OrderRejectionReason.INSUFFICIENT_CASH,
        )
        assert order.rejection_reason is OrderRejectionReason.INSUFFICIENT_CASH

    def test_executed_forbids_rejection_reason(self) -> None:
        order = self._order(status=OrderIntentStatus.EXECUTED)
        assert order.rejection_reason is None

    def test_executed_order_cannot_be_constructed_with_a_rejection_reason(self) -> None:
        """An 'executed' order can never simultaneously carry a rejection reason —
        append-only forbids the UPDATE and the PRIMARY KEY forbids re-INSERTing the
        same id, so no later write can rewrite it regardless."""
        with pytest.raises(ValidationError):
            self._order(
                status=OrderIntentStatus.EXECUTED,
                rejection_reason=OrderRejectionReason.MARKET_CLOSED,
            )

    def test_frozen_prevents_mutation_after_execution(self) -> None:
        order = self._order(status=OrderIntentStatus.EXECUTED)
        with pytest.raises(ValidationError):
            order.status = OrderIntentStatus.PENDING  # type: ignore[misc]

    def test_changed_same_date_target_supersedes_pending_order(self) -> None:
        """A changed same-date ApprovedTarget supersedes a pending OrderIntent: the
        replacement is a brand-new row with a backward link to the one it replaces —
        the original row is never rewritten, only ever pointed at."""
        pending = self._order(status=OrderIntentStatus.PENDING)
        replacement = self._order(
            approved_target_id=pending.approved_target_id,
            status=OrderIntentStatus.PENDING,
            supersedes_id=pending.id,
        )
        assert replacement.id != pending.id
        assert replacement.supersedes_id == pending.id


class TestPaperExecutionImmutabilityAndIdempotency:
    def _execution(
        self, order_intent_id, executed_date: date, **overrides: object
    ) -> PaperExecution:
        fields = dict(
            id=paper_execution_id(order_intent_id, executed_date),
            order_intent_id=order_intent_id,
            executed_date=executed_date,
            symbol="AAPL",
            quantity=Decimal("100"),
            price=Decimal("189.32"),
            executed_at=_ts(),
            recorded_at=_ts(),
        )
        fields.update(overrides)
        return PaperExecution(**fields)

    def test_frozen_raises_on_mutation(self) -> None:
        order_intent_id = uuid4()
        execution = self._execution(order_intent_id, RUN_DATE)
        with pytest.raises(ValidationError):
            execution.quantity = Decimal("200")  # type: ignore[misc]

    def test_wrong_id_raises(self) -> None:
        order_intent_id = uuid4()
        with pytest.raises(ValidationError):
            self._execution(order_intent_id, RUN_DATE, id=uuid4())

    def test_missing_quantity_or_price_raises_never_zero(self) -> None:
        order_intent_id = uuid4()
        with pytest.raises(ValidationError):
            self._execution(order_intent_id, RUN_DATE, quantity=None)
        with pytest.raises(ValidationError):
            self._execution(order_intent_id, RUN_DATE, price=None)
        with pytest.raises(ValidationError):
            self._execution(order_intent_id, RUN_DATE, quantity=Decimal("0"))
        with pytest.raises(ValidationError):
            self._execution(order_intent_id, RUN_DATE, price=Decimal("0"))

    def test_exact_same_date_retry_is_idempotent(self) -> None:
        """Same order_intent_id + same executed_date + same inputs => field-identical
        output, including the same deterministic id — the definition of idempotent."""
        order_intent_id = uuid4()
        first = self._execution(order_intent_id, RUN_DATE)
        second = self._execution(order_intent_id, RUN_DATE)
        assert first.id == second.id
        assert first.model_dump() == second.model_dump()

    def test_different_executed_date_yields_different_id(self) -> None:
        order_intent_id = uuid4()
        first = self._execution(order_intent_id, RUN_DATE)
        second = self._execution(order_intent_id, RUN_DATE + timedelta(days=1))
        assert first.id != second.id


class TestHoldingLotLifecycle:
    def _lot(self, **overrides: object) -> HoldingLot:
        fields = dict(
            id=uuid4(),
            opened_by_execution_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            quantity=Decimal("100"),
            open_price=Decimal("189.32"),
            status=HoldingLotStatus.OPEN,
            opened_at=_ts(),
            recorded_at=_ts(),
        )
        fields.update(overrides)
        return HoldingLot(**fields)

    def test_open_forbids_closed_fields(self) -> None:
        lot = self._lot()
        assert lot.closed_at is None
        assert lot.closed_by_execution_id is None

    def test_open_with_closed_at_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._lot(closed_at=_ts(22))

    def test_closed_requires_both_fields(self) -> None:
        with pytest.raises(ValidationError):
            self._lot(status=HoldingLotStatus.CLOSED, closed_at=_ts(22))
        with pytest.raises(ValidationError):
            self._lot(status=HoldingLotStatus.CLOSED, closed_by_execution_id=uuid4())

    def test_closed_with_both_fields_ok(self) -> None:
        lot = self._lot(
            status=HoldingLotStatus.CLOSED,
            closed_at=_ts(22),
            closed_by_execution_id=uuid4(),
        )
        assert lot.status is HoldingLotStatus.CLOSED

    def test_closed_at_before_opened_at_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._lot(
                status=HoldingLotStatus.CLOSED,
                opened_at=_ts(21),
                closed_at=_ts(20),
                closed_by_execution_id=uuid4(),
            )

    def test_same_execution_cannot_open_and_close_raises(self) -> None:
        execution_id = uuid4()
        with pytest.raises(ValidationError):
            self._lot(
                opened_by_execution_id=execution_id,
                status=HoldingLotStatus.CLOSED,
                closed_at=_ts(22),
                closed_by_execution_id=execution_id,
            )


class TestChainFixtures:
    """One fixture per acceptance-criteria scenario: add, trim, exit, no-op, rejection,
    cap, rounding, carry, supersession. Each builds enough of the chain to demonstrate
    the scenario without nullable semantic ambiguity anywhere along it."""

    def test_add(self) -> None:
        decision = make_decision(DecisionAction.ADD, DecisionReason.NEW_CONVICTION)
        requested = RequestedTarget(
            id=uuid4(),
            decision_intent_id=decision.id,
            run_date=RUN_DATE,
            symbol="AAPL",
            requested_weight=Decimal("0.04"),
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        assert requested.requested_weight is not None and requested.requested_weight > 0

    def test_trim(self) -> None:
        decision = make_decision(DecisionAction.TRIM, DecisionReason.CONVICTION_REDUCED)
        requested = RequestedTarget(
            id=uuid4(),
            decision_intent_id=decision.id,
            run_date=RUN_DATE,
            symbol="AAPL",
            requested_weight=Decimal("0.02"),
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        assert requested.requested_weight == Decimal("0.02")

    def test_exit(self) -> None:
        decision = make_decision(DecisionAction.EXIT, DecisionReason.THESIS_INVALIDATED)
        requested = RequestedTarget(
            id=uuid4(),
            decision_intent_id=decision.id,
            run_date=RUN_DATE,
            symbol="AAPL",
            requested_weight=Decimal("0"),
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        # An explicit full-exit 0 is legal and distinct from "unknown".
        assert requested.requested_weight == Decimal("0")

    def test_no_op(self) -> None:
        decision = make_decision(DecisionAction.NO_OP, DecisionReason.NO_SIGNAL_CHANGE)
        assert decision.action is DecisionAction.NO_OP
        assert decision.reason is DecisionReason.NO_SIGNAL_CHANGE

    def test_rejection(self) -> None:
        decision = make_decision(DecisionAction.REJECT, DecisionReason.RISK_CAP_BREACH)
        order = OrderIntent(
            id=uuid4(),
            approved_target_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            quantity=Decimal("50"),
            status=OrderIntentStatus.REJECTED,
            rejection_reason=OrderRejectionReason.RISK_LIMIT,
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        assert decision.action is DecisionAction.REJECT
        assert order.rejection_reason is OrderRejectionReason.RISK_LIMIT

    def test_cap(self) -> None:
        adjustment = TargetAdjustment(
            id=uuid4(),
            requested_target_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            adjustment_type=TargetAdjustmentType.CAP,
            original_value=Decimal("0.10"),
            adjusted_value=Decimal("0.08"),
            reason="gross exposure cap",
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        assert adjustment.adjusted_value < adjustment.original_value

    def test_rounding(self) -> None:
        adjustment = TargetAdjustment(
            id=uuid4(),
            requested_target_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            adjustment_type=TargetAdjustmentType.ROUNDING,
            original_value=Decimal("100.7"),
            adjusted_value=Decimal("100"),
            reason="whole-share rounding",
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        assert adjustment.adjustment_type is TargetAdjustmentType.ROUNDING

    def test_carry(self) -> None:
        adjustment = TargetAdjustment(
            id=uuid4(),
            requested_target_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            adjustment_type=TargetAdjustmentType.CARRY,
            original_value=Decimal("0.03"),
            adjusted_value=Decimal("0.03"),
            reason="carried from prior run_date (fingerprint_skip)",
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        assert adjustment.original_value == adjustment.adjusted_value

    def test_supersession_end_to_end(self) -> None:
        first_target = ApprovedTarget(
            id=uuid4(),
            requested_target_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            approved_weight=Decimal("0.05"),
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        second_target = ApprovedTarget(
            id=uuid4(),
            requested_target_id=uuid4(),
            run_date=RUN_DATE,
            symbol="AAPL",
            approved_weight=Decimal("0.07"),
            supersedes_id=first_target.id,
            effective_at=_ts(1),
            recorded_at=_ts(1),
        )
        first_order = OrderIntent(
            id=uuid4(),
            approved_target_id=first_target.id,
            run_date=RUN_DATE,
            symbol="AAPL",
            quantity=Decimal("50"),
            status=OrderIntentStatus.PENDING,
            effective_at=_ts(),
            recorded_at=_ts(),
        )
        second_order = OrderIntent(
            id=uuid4(),
            approved_target_id=second_target.id,
            run_date=RUN_DATE,
            symbol="AAPL",
            quantity=Decimal("70"),
            status=OrderIntentStatus.PENDING,
            supersedes_id=first_order.id,
            effective_at=_ts(1),
            recorded_at=_ts(1),
        )
        assert second_target.supersedes_id == first_target.id
        assert second_order.supersedes_id == first_order.id
        assert second_order.id != first_order.id
