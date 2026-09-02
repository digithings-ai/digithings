"""Bind Phase 0 action, fill, and accounting records to cost-model inputs (#2700 / WP7.1).

Adapters translate authoritative ledger and accounting Pydantic contracts into
``ActionCostInput`` (prospective) and ``RealizedCostInput`` (observed fill) without
inferring economics from weights, NAV, or legacy dictionaries. Missing typed fields
raise :class:`ActionCostBindingError` so WP7 stops rather than guessing.

Phase 0 gap — currency is not stored on ledger or accounting rows; callers must pass
an explicit ``currency`` string (e.g. portfolio ``investor_currency``). Notional on
prospective actions is absent unless a caller supplies an authoritative mark price
separately — never derived from NAV.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from digiquant.olympus.accounting.models import FillSide, PeriodFill
from digiquant.olympus.hermes.models.portfolio_ledger import (
    DecisionAction,
    DecisionIntent,
    OrderIntent,
    PaperExecution,
    PortfolioCommit,
)

_MONEY_QUANTUM = Decimal("0.01")


class ActionCostBindingError(ValueError):
    """Required Phase 0 field absent or action is not cost-bindable."""


class ActionCostSide(StrEnum):
    """Trade direction for cost estimation — mirrors accounting ``FillSide``."""

    BUY = "buy"
    SELL = "sell"


CurrencyCode: type = Annotated[str, Field(min_length=3, max_length=12)]
PositiveDecimal: type = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
NonNegFee: type = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
SignedAmount: type = Annotated[Decimal, Field(allow_inf_nan=False)]
Symbol: type = Annotated[str, Field(min_length=1, max_length=20)]


class ActionCostModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActionCostInput(ActionCostModel):
    """Prospective cost input from an authoritative decision + order intent chain."""

    portfolio_commit_id: UUID
    decision_intent_id: UUID
    order_intent_id: UUID
    run_date: date
    symbol: Symbol
    side: ActionCostSide
    quantity: PositiveDecimal
    notional: PositiveDecimal | None = None
    currency: CurrencyCode
    effective_at: AwareDatetime
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def validate_utc(self) -> ActionCostInput:
        for label, ts in (("effective_at", self.effective_at), ("recorded_at", self.recorded_at)):
            if ts.tzinfo is None or ts.utcoffset() != timedelta(0):
                raise ValueError(f"{label} must be timezone-aware UTC")
        return self


class RealizedCostInput(ActionCostModel):
    """Observed fill cost input from an authoritative execution or accounting fill."""

    execution_id: UUID
    order_intent_id: UUID | None = None
    decision_intent_id: UUID | None = None
    executed_date: date
    symbol: Symbol
    side: ActionCostSide
    quantity: PositiveDecimal
    price: PositiveDecimal
    notional: PositiveDecimal
    currency: CurrencyCode
    fee: NonNegFee
    slippage: SignedAmount
    executed_at: AwareDatetime
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def validate_utc(self) -> RealizedCostInput:
        for label, ts in (("executed_at", self.executed_at), ("recorded_at", self.recorded_at)):
            if ts.tzinfo is None or ts.utcoffset() != timedelta(0):
                raise ValueError(f"{label} must be timezone-aware UTC")
        return self


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _side_from_decision(action: DecisionAction) -> ActionCostSide:
    if action is DecisionAction.ADD:
        return ActionCostSide.BUY
    if action in (DecisionAction.TRIM, DecisionAction.EXIT):
        return ActionCostSide.SELL
    raise ActionCostBindingError(f"decision action {action.value!r} is not tradeable")


def _side_from_fill_side(side: FillSide) -> ActionCostSide:
    return ActionCostSide(side.value)


def _require_currency(currency: str) -> str:
    code = str(currency or "").strip().upper()
    if len(code) < 3:
        raise ActionCostBindingError("currency must be an explicit non-empty code")
    return code


def _notional_from_fill(*, quantity: Decimal, price: Decimal) -> Decimal:
    return _money(quantity * price)


def action_cost_input_from_order(
    *,
    commit: PortfolioCommit,
    decision: DecisionIntent,
    order: OrderIntent,
    currency: str,
    mark_price: Decimal | None = None,
) -> ActionCostInput:
    """Bind prospective cost input from authoritative commit + decision + order rows.

    ``mark_price`` is optional and must be supplied explicitly when notional is
    required — never inferred from NAV or portfolio weights.
    """
    if decision.portfolio_commit_id != commit.id:
        raise ActionCostBindingError("decision_intent portfolio_commit_id does not match commit")
    if decision.run_date != order.run_date or decision.symbol != order.symbol:
        raise ActionCostBindingError("decision_intent and order_intent symbol/run_date mismatch")
    if decision.run_date != commit.run_date:
        raise ActionCostBindingError("commit run_date does not match decision run_date")

    side = _side_from_decision(decision.action)
    notional = (
        _notional_from_fill(quantity=order.quantity, price=mark_price) if mark_price else None
    )

    return ActionCostInput(
        portfolio_commit_id=commit.id,
        decision_intent_id=decision.id,
        order_intent_id=order.id,
        run_date=order.run_date,
        symbol=order.symbol,
        side=side,
        quantity=order.quantity,
        notional=notional,
        currency=_require_currency(currency),
        effective_at=order.effective_at,
        recorded_at=order.recorded_at,
    )


def realized_cost_input_from_execution(
    *,
    execution: PaperExecution,
    decision: DecisionIntent,
    order_intent_id: UUID,
    currency: str,
) -> RealizedCostInput:
    """Bind realized cost input from an authoritative paper execution + decision."""
    if execution.order_intent_id != order_intent_id:
        raise ActionCostBindingError("execution order_intent_id does not match supplied order")
    if decision.symbol != execution.symbol:
        raise ActionCostBindingError("decision_intent symbol does not match execution symbol")
    if execution.fee is None or execution.slippage is None:
        raise ActionCostBindingError(
            "execution fee and slippage must be explicit (predates migration 070 is not bindable)"
        )

    side = _side_from_decision(decision.action)
    notional = _notional_from_fill(quantity=execution.quantity, price=execution.price)

    return RealizedCostInput(
        execution_id=execution.id,
        order_intent_id=execution.order_intent_id,
        decision_intent_id=decision.id,
        executed_date=execution.executed_date,
        symbol=execution.symbol,
        side=side,
        quantity=execution.quantity,
        price=execution.price,
        notional=notional,
        currency=_require_currency(currency),
        fee=execution.fee,
        slippage=execution.slippage,
        executed_at=execution.executed_at,
        recorded_at=execution.recorded_at,
    )


def realized_cost_input_from_period_fill(*, fill: PeriodFill, currency: str) -> RealizedCostInput:
    """Bind realized cost input from an authoritative accounting ``PeriodFill``."""
    if fill.execution_id is None:
        raise ActionCostBindingError("period fill execution_id is required for realized binding")

    notional = _notional_from_fill(quantity=fill.quantity, price=fill.price)

    return RealizedCostInput(
        execution_id=fill.execution_id,
        order_intent_id=None,
        decision_intent_id=None,
        executed_date=fill.executed_at.date(),
        symbol=fill.symbol,
        side=_side_from_fill_side(fill.side),
        quantity=fill.quantity,
        price=fill.price,
        notional=notional,
        currency=_require_currency(currency),
        fee=fill.fee,
        slippage=fill.slippage,
        executed_at=fill.executed_at,
        recorded_at=fill.executed_at,
    )


__all__ = [
    "ActionCostBindingError",
    "ActionCostInput",
    "ActionCostSide",
    "RealizedCostInput",
    "action_cost_input_from_order",
    "realized_cost_input_from_execution",
    "realized_cost_input_from_period_fill",
]
