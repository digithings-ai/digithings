"""WP7.1 — bind Phase 0 action/fill/accounting records to cost inputs (#2700)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from digiquant.dashboard.accounting.models import FillSide, PeriodFill
from digiquant.portfolio.action_cost_inputs import (
    ActionCostBindingError,
    ActionCostSide,
    action_cost_input_from_order,
    realized_cost_input_from_execution,
    realized_cost_input_from_period_fill,
)
from digiquant.portfolio.models.portfolio_ledger import (
    DecisionAction,
    DecisionReason,
    OrderIntent,
    OrderIntentStatus,
    PaperExecution,
    paper_execution_id,
)

from tests.dq.hermes.test_portfolio_ledger import _ts, make_commit, make_decision

pytestmark = pytest.mark.unit

EXECUTED_DATE = date(2026, 8, 15)
CURRENCY = "USD"


def _order(**overrides: object) -> OrderIntent:
    fields = dict(
        id=uuid4(),
        approved_target_id=uuid4(),
        run_date=date(2026, 8, 14),
        symbol="AAPL",
        quantity=Decimal("10.5"),
        status=OrderIntentStatus.PENDING,
        effective_at=_ts(),
        recorded_at=_ts(),
    )
    fields.update(overrides)
    return OrderIntent(**fields)


def _execution(*, order: OrderIntent, **overrides: object) -> PaperExecution:
    execution_id = paper_execution_id(order.id, EXECUTED_DATE)
    fields = dict(
        id=execution_id,
        order_intent_id=order.id,
        executed_date=EXECUTED_DATE,
        symbol=order.symbol,
        quantity=order.quantity,
        price=Decimal("150.25"),
        fee=Decimal("0.00"),
        slippage=Decimal("0.00"),
        executed_at=datetime(2026, 8, 15, 13, 31, tzinfo=UTC),
        recorded_at=datetime(2026, 8, 15, 13, 31, tzinfo=UTC),
    )
    fields.update(overrides)
    return PaperExecution(**fields)


class TestActionCostInputFromOrder:
    def test_buy_add_retains_authoritative_ids_and_amounts(self) -> None:
        commit = make_commit()
        decision = make_decision(
            DecisionAction.ADD,
            DecisionReason.NEW_CONVICTION,
            portfolio_commit_id=commit.id,
            symbol="AAPL",
        )
        order = _order(symbol="AAPL", quantity=Decimal("12.000001"))

        bound = action_cost_input_from_order(
            commit=commit,
            decision=decision,
            order=order,
            currency=CURRENCY,
            mark_price=Decimal("100.00"),
        )

        assert bound.portfolio_commit_id == commit.id
        assert bound.decision_intent_id == decision.id
        assert bound.order_intent_id == order.id
        assert bound.side is ActionCostSide.BUY
        assert bound.quantity == order.quantity
        assert bound.notional == Decimal("1200.00")
        assert bound.currency == "USD"
        assert bound.effective_at == order.effective_at
        assert bound.recorded_at == order.recorded_at

    def test_sell_trim_without_mark_has_no_notional(self) -> None:
        commit = make_commit()
        decision = make_decision(
            DecisionAction.TRIM,
            DecisionReason.CONVICTION_REDUCED,
            portfolio_commit_id=commit.id,
        )
        order = _order()

        bound = action_cost_input_from_order(
            commit=commit,
            decision=decision,
            order=order,
            currency=CURRENCY,
        )

        assert bound.side is ActionCostSide.SELL
        assert bound.notional is None

    def test_rejects_non_tradeable_decision(self) -> None:
        commit = make_commit()
        decision = make_decision(
            DecisionAction.NO_OP,
            DecisionReason.NO_SIGNAL_CHANGE,
            portfolio_commit_id=commit.id,
        )
        order = _order()

        with pytest.raises(ActionCostBindingError, match="not tradeable"):
            action_cost_input_from_order(
                commit=commit,
                decision=decision,
                order=order,
                currency=CURRENCY,
            )

    def test_rejects_mismatched_chain(self) -> None:
        commit = make_commit()
        decision = make_decision(
            DecisionAction.ADD,
            DecisionReason.NEW_CONVICTION,
            portfolio_commit_id=uuid4(),
        )
        order = _order()

        with pytest.raises(ActionCostBindingError, match="portfolio_commit_id"):
            action_cost_input_from_order(
                commit=commit,
                decision=decision,
                order=order,
                currency=CURRENCY,
            )

    def test_rejects_missing_currency(self) -> None:
        commit = make_commit()
        decision = make_decision(
            DecisionAction.ADD,
            DecisionReason.NEW_CONVICTION,
            portfolio_commit_id=commit.id,
        )
        order = _order()

        with pytest.raises(ActionCostBindingError, match="currency"):
            action_cost_input_from_order(
                commit=commit,
                decision=decision,
                order=order,
                currency="",
            )


class TestRealizedCostInputFromExecution:
    def test_fill_retains_exact_ids_and_measured_costs(self) -> None:
        decision = make_decision(
            DecisionAction.EXIT,
            DecisionReason.THESIS_INVALIDATED,
        )
        order = _order(quantity=Decimal("5"))
        execution = _execution(
            order=order,
            fee=Decimal("1.25"),
            slippage=Decimal("-0.50"),
        )

        bound = realized_cost_input_from_execution(
            execution=execution,
            decision=decision,
            order_intent_id=order.id,
            currency=CURRENCY,
        )

        assert bound.execution_id == execution.id
        assert bound.order_intent_id == order.id
        assert bound.decision_intent_id == decision.id
        assert bound.side is ActionCostSide.SELL
        assert bound.quantity == execution.quantity
        assert bound.price == execution.price
        assert bound.notional == Decimal("751.25")
        assert bound.fee == Decimal("1.25")
        assert bound.slippage == Decimal("-0.50")
        assert bound.executed_at == execution.executed_at

    def test_rejects_predates_cost_tracking_null_fee(self) -> None:
        order = _order()
        execution = _execution(order=order, fee=None, slippage=Decimal("0"))
        decision = make_decision(DecisionAction.ADD, DecisionReason.NEW_CONVICTION)

        with pytest.raises(ActionCostBindingError, match="fee and slippage"):
            realized_cost_input_from_execution(
                execution=execution,
                decision=decision,
                order_intent_id=order.id,
                currency=CURRENCY,
            )

    def test_rejects_order_intent_mismatch(self) -> None:
        order = _order()
        execution = _execution(order=order)
        decision = make_decision(DecisionAction.ADD, DecisionReason.NEW_CONVICTION)

        with pytest.raises(ActionCostBindingError, match="order_intent_id"):
            realized_cost_input_from_execution(
                execution=execution,
                decision=decision,
                order_intent_id=uuid4(),
                currency=CURRENCY,
            )


class TestRealizedCostInputFromPeriodFill:
    def test_accounting_fill_binds_with_execution_id(self) -> None:
        execution_id = uuid4()
        executed_at = datetime(2026, 8, 15, 13, 31, tzinfo=UTC)
        fill = PeriodFill(
            symbol="MSFT",
            side=FillSide.BUY,
            quantity=Decimal("3"),
            price=Decimal("400.00"),
            fee=Decimal("0"),
            slippage=Decimal("0"),
            executed_at=executed_at,
            execution_id=execution_id,
        )

        bound = realized_cost_input_from_period_fill(fill=fill, currency=CURRENCY)

        assert bound.execution_id == execution_id
        assert bound.order_intent_id is None
        assert bound.side is ActionCostSide.BUY
        assert bound.notional == Decimal("1200.00")
        assert bound.executed_at == executed_at

    def test_rejects_fill_without_execution_id(self) -> None:
        fill = PeriodFill(
            symbol="MSFT",
            side=FillSide.SELL,
            quantity=Decimal("1"),
            price=Decimal("100.00"),
            executed_at=datetime(2026, 8, 15, 13, 31, tzinfo=UTC),
            execution_id=None,
        )

        with pytest.raises(ActionCostBindingError, match="execution_id"):
            realized_cost_input_from_period_fill(fill=fill, currency=CURRENCY)
