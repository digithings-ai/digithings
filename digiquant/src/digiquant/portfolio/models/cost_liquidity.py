"""Observational cost and liquidity contracts (#2703 / WP7.2).

Strict Pydantic v2 models for prospective trade economics and expected-vs-realized
comparison. Pure estimation lives in :mod:`digiquant.portfolio.cost_liquidity`.
Phase 1 is observational only — estimates do not veto or resize actions.

Style mirrors :mod:`digiquant.portfolio.models.forecast_calibration`: frozen,
``extra="forbid"``, UTC-only aware datetimes, Decimal economics, UUID5 identity,
content hashes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, TypeAlias
from uuid import UUID, uuid5

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from digiquant.portfolio.action_cost_inputs import ActionCostSide

_ACTION_COST_ESTIMATE_ID_NAMESPACE = UUID("a903c14e-6d2f-7a18-9e4b-1c2d3e4f5a60")
_LIQUIDITY_SNAPSHOT_ID_NAMESPACE = UUID("b014d25f-7e30-8b29-af5c-2d3e4f607b71")
_ACTION_COST_OUTCOME_ID_NAMESPACE = UUID("c125e36a-8f41-9c3a-b06d-3e4f50618c82")

NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
MoneyDecimal: TypeAlias = Annotated[
    Decimal, Field(allow_inf_nan=False, max_digits=20, decimal_places=8)
]
NonNegativeMoney: TypeAlias = Annotated[
    Decimal, Field(ge=0, allow_inf_nan=False, max_digits=20, decimal_places=8)
]
PositiveMoney: TypeAlias = Annotated[
    Decimal, Field(gt=0, allow_inf_nan=False, max_digits=20, decimal_places=8)
]
Symbol: TypeAlias = Annotated[str, Field(min_length=1, max_length=20)]


class CostLiquidityModel(BaseModel):
    """Strict immutable base for cost/liquidity contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CostEstimateStatus(StrEnum):
    """Whether an estimate or liquidity snapshot is usable."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNPRICEABLE = "unpriceable"
    UNAVAILABLE = "unavailable"


class CostOutcomeStatus(StrEnum):
    """Lifecycle of an expected-vs-realized comparison."""

    COMPARED = "compared"
    PENDING = "pending"
    UNAVAILABLE = "unavailable"


class CostComponentKind(StrEnum):
    """Decomposed observational cost line."""

    FEE = "fee"
    SPREAD_HALF = "spread_half"
    IMPACT = "impact"
    TOTAL = "total"


class SpreadProxyMethod(StrEnum):
    """Label for spread observation — never claims a live quote."""

    HIGH_LOW_RANGE_FRACTION = "high_low_range_fraction"


class CostComponent(CostLiquidityModel):
    """One labeled assumption/observation cost line."""

    kind: CostComponentKind
    amount: MoneyDecimal | None
    currency: str | None = None
    assumption_label: NonEmptyId
    observation_label: NonEmptyId | None = None
    unavailable_reason: NonEmptyId | None = None

    @model_validator(mode="after")
    def _validate_component(self) -> CostComponent:
        if self.amount is None and not self.unavailable_reason:
            raise ValueError("missing amount requires unavailable_reason")
        if self.amount is not None and self.unavailable_reason is not None:
            raise ValueError("available amount cannot carry unavailable_reason")
        if self.amount is not None and not self.currency:
            raise ValueError("priced component requires currency")
        return self


class ProspectiveMarketObservations(CostLiquidityModel):
    """One session OHLCV + technical inputs assembled by the caller."""

    session_date: date
    symbol: Symbol
    close: PositiveMoney | None = None
    high: PositiveMoney | None = None
    low: PositiveMoney | None = None
    volume: int | None = Field(default=None, ge=0)
    hist_vol_21: NonNegativeMoney | None = None
    atr_pct: NonNegativeMoney | None = None
    adv_shares: PositiveMoney | None = None
    adv_dollars: PositiveMoney | None = None
    observed_at: AwareDatetime
    known_at: AwareDatetime

    @model_validator(mode="after")
    def _validate_utc(self) -> ProspectiveMarketObservations:
        for label, ts in (("observed_at", self.observed_at), ("known_at", self.known_at)):
            if ts.tzinfo is None or ts.utcoffset() != timedelta(0):
                raise ValueError(f"{label} must be timezone-aware UTC")
        if self.high is not None and self.low is not None and self.high < self.low:
            raise ValueError("high must be >= low")
        return self


class LiquiditySnapshot(CostLiquidityModel):
    """Timestamped capacity evidence for one prospective action."""

    snapshot_id: UUID
    method_version: NonEmptyId
    symbol: Symbol
    as_of_session: date
    quantity: PositiveMoney
    adv_shares: PositiveMoney | None = None
    adv_dollars: PositiveMoney | None = None
    participation_pct: NonNegativeMoney | None = None
    days_to_liquidate: int | None = Field(default=None, ge=1)
    max_adv_participation_pct: NonNegativeMoney
    status: CostEstimateStatus
    unavailable_reason: NonEmptyId | None = None
    observations_hash: NonEmptyId
    resolved_at: AwareDatetime
    content_hash: NonEmptyId

    @model_validator(mode="after")
    def _validate_snapshot(self) -> LiquiditySnapshot:
        if self.resolved_at.utcoffset() != timedelta(0):
            raise ValueError("resolved_at must be timezone-aware UTC")
        if self.status in (
            CostEstimateStatus.UNPRICEABLE,
            CostEstimateStatus.UNAVAILABLE,
            CostEstimateStatus.DEGRADED,
        ):
            if not self.unavailable_reason:
                raise ValueError(
                    "degraded/unpriceable/unavailable snapshot requires unavailable_reason"
                )
        elif self.unavailable_reason is not None:
            raise ValueError("available snapshot cannot carry unavailable_reason")
        expected_hash = liquidity_snapshot_content_hash(payload=snapshot_hash_payload(self))
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical snapshot digest")
        expected_id = liquidity_snapshot_id(
            symbol=self.symbol,
            as_of_session=self.as_of_session,
            quantity=self.quantity,
            content_hash=self.content_hash,
        )
        if self.snapshot_id != expected_id:
            raise ValueError("snapshot_id must be UUID5 of symbol+session+quantity+content_hash")
        return self


class ActionCostEstimate(CostLiquidityModel):
    """Prospective decomposed cost for one authoritative action."""

    estimate_id: UUID
    method_version: NonEmptyId
    portfolio_commit_id: UUID
    decision_intent_id: UUID
    order_intent_id: UUID
    symbol: Symbol
    side: ActionCostSide
    quantity: PositiveMoney
    notional: PositiveMoney | None = None
    currency: NonEmptyId
    policy_id: UUID
    policy_content_hash: NonEmptyId
    liquidity_snapshot_id: UUID
    spread_proxy_method: SpreadProxyMethod
    components: tuple[CostComponent, ...]
    total_cost: NonNegativeMoney | None = None
    status: CostEstimateStatus
    unavailable_reason: NonEmptyId | None = None
    effective_at: AwareDatetime
    estimated_at: AwareDatetime
    content_hash: NonEmptyId

    @model_validator(mode="after")
    def _validate_estimate(self) -> ActionCostEstimate:
        for label, ts in (("effective_at", self.effective_at), ("estimated_at", self.estimated_at)):
            if ts.tzinfo is None or ts.utcoffset() != timedelta(0):
                raise ValueError(f"{label} must be timezone-aware UTC")
        kinds = {c.kind for c in self.components}
        if CostComponentKind.TOTAL not in kinds:
            raise ValueError("components must include TOTAL")
        if self.status in (CostEstimateStatus.UNPRICEABLE, CostEstimateStatus.UNAVAILABLE):
            if not self.unavailable_reason:
                raise ValueError("unpriceable/unavailable estimate requires unavailable_reason")
            if self.total_cost is not None:
                raise ValueError("unpriceable/unavailable estimate cannot carry total_cost")
        elif self.status is CostEstimateStatus.DEGRADED:
            if not self.unavailable_reason:
                raise ValueError("degraded estimate requires unavailable_reason")
        elif self.total_cost is None:
            raise ValueError("available estimate requires total_cost")
        elif self.unavailable_reason is not None:
            raise ValueError("available estimate cannot carry unavailable_reason")
        expected_hash = action_cost_estimate_content_hash(payload=estimate_hash_payload(self))
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical estimate digest")
        expected_id = action_cost_estimate_id(
            order_intent_id=self.order_intent_id,
            policy_content_hash=self.policy_content_hash,
            content_hash=self.content_hash,
        )
        if self.estimate_id != expected_id:
            raise ValueError("estimate_id must be UUID5 of order+policy+content_hash")
        return self


class ActionCostOutcome(CostLiquidityModel):
    """Expected-vs-realized comparison for one fill."""

    outcome_id: UUID
    estimate_id: UUID
    execution_id: UUID
    order_intent_id: UUID | None = None
    currency: NonEmptyId
    expected_total: NonNegativeMoney | None = None
    realized_total: NonNegativeMoney | None = None
    residual: MoneyDecimal | None = None
    expected_components: tuple[CostComponent, ...]
    realized_fee: NonNegativeMoney | None = None
    realized_slippage: MoneyDecimal | None = None
    status: CostOutcomeStatus
    unavailable_reason: NonEmptyId | None = None
    compared_at: AwareDatetime
    content_hash: NonEmptyId

    @model_validator(mode="after")
    def _validate_outcome(self) -> ActionCostOutcome:
        if self.compared_at.utcoffset() != timedelta(0):
            raise ValueError("compared_at must be timezone-aware UTC")
        if self.status is CostOutcomeStatus.COMPARED:
            if self.expected_total is None or self.realized_total is None or self.residual is None:
                raise ValueError("compared outcome requires expected, realized, and residual")
            if self.realized_fee is None or self.realized_slippage is None:
                raise ValueError("compared outcome requires realized fee and slippage")
        elif self.status is CostOutcomeStatus.UNAVAILABLE:
            if not self.unavailable_reason:
                raise ValueError("unavailable outcome requires unavailable_reason")
        elif self.status is CostOutcomeStatus.PENDING:
            if self.realized_total is not None:
                raise ValueError("pending outcome cannot carry realized_total")
        expected_hash = action_cost_outcome_content_hash(payload=outcome_hash_payload(self))
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical outcome digest")
        expected_id = action_cost_outcome_id(
            estimate_id=self.estimate_id,
            execution_id=self.execution_id,
            content_hash=self.content_hash,
        )
        if self.outcome_id != expected_id:
            raise ValueError("outcome_id must be UUID5 of estimate+execution+content_hash")
        return self


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def liquidity_snapshot_content_hash(*, payload: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def liquidity_snapshot_id(
    *,
    symbol: str,
    as_of_session: date,
    quantity: Decimal,
    content_hash: str,
) -> UUID:
    if not content_hash.strip():
        raise ValueError("content_hash is required")
    return uuid5(
        _LIQUIDITY_SNAPSHOT_ID_NAMESPACE,
        f"{symbol.strip().upper()}:{as_of_session.isoformat()}:{quantity}:{content_hash.strip()}",
    )


def action_cost_estimate_content_hash(*, payload: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def action_cost_estimate_id(
    *,
    order_intent_id: UUID,
    policy_content_hash: str,
    content_hash: str,
) -> UUID:
    if not policy_content_hash.strip() or not content_hash.strip():
        raise ValueError("policy_content_hash and content_hash are required")
    return uuid5(
        _ACTION_COST_ESTIMATE_ID_NAMESPACE,
        f"{order_intent_id}:{policy_content_hash.strip()}:{content_hash.strip()}",
    )


def action_cost_outcome_content_hash(*, payload: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def action_cost_outcome_id(
    *,
    estimate_id: UUID,
    execution_id: UUID,
    content_hash: str,
) -> UUID:
    if not content_hash.strip():
        raise ValueError("content_hash is required")
    return uuid5(
        _ACTION_COST_OUTCOME_ID_NAMESPACE,
        f"{estimate_id}:{execution_id}:{content_hash.strip()}",
    )


def _component_json(component: CostComponent) -> dict[str, object]:
    return component.model_dump(mode="json")


def snapshot_hash_payload(snapshot: LiquiditySnapshot) -> dict[str, object]:
    return {
        "method_version": snapshot.method_version,
        "symbol": snapshot.symbol,
        "as_of_session": snapshot.as_of_session.isoformat(),
        "quantity": str(snapshot.quantity),
        "adv_shares": str(snapshot.adv_shares) if snapshot.adv_shares is not None else None,
        "adv_dollars": str(snapshot.adv_dollars) if snapshot.adv_dollars is not None else None,
        "participation_pct": (
            str(snapshot.participation_pct) if snapshot.participation_pct is not None else None
        ),
        "days_to_liquidate": snapshot.days_to_liquidate,
        "max_adv_participation_pct": str(snapshot.max_adv_participation_pct),
        "status": snapshot.status.value,
        "observations_hash": snapshot.observations_hash,
    }


def estimate_hash_payload(estimate: ActionCostEstimate) -> dict[str, object]:
    return {
        "method_version": estimate.method_version,
        "order_intent_id": str(estimate.order_intent_id),
        "symbol": estimate.symbol,
        "side": estimate.side.value,
        "quantity": str(estimate.quantity),
        "notional": str(estimate.notional) if estimate.notional is not None else None,
        "currency": estimate.currency,
        "policy_content_hash": estimate.policy_content_hash,
        "liquidity_snapshot_id": str(estimate.liquidity_snapshot_id),
        "spread_proxy_method": estimate.spread_proxy_method.value,
        "components": [_component_json(c) for c in estimate.components],
        "total_cost": str(estimate.total_cost) if estimate.total_cost is not None else None,
        "status": estimate.status.value,
    }


def outcome_hash_payload(outcome: ActionCostOutcome) -> dict[str, object]:
    return {
        "estimate_id": str(outcome.estimate_id),
        "execution_id": str(outcome.execution_id),
        "currency": outcome.currency,
        "expected_total": (
            str(outcome.expected_total) if outcome.expected_total is not None else None
        ),
        "realized_total": str(outcome.realized_total)
        if outcome.realized_total is not None
        else None,
        "residual": str(outcome.residual) if outcome.residual is not None else None,
        "expected_components": [_component_json(c) for c in outcome.expected_components],
        "realized_fee": str(outcome.realized_fee) if outcome.realized_fee is not None else None,
        "realized_slippage": (
            str(outcome.realized_slippage) if outcome.realized_slippage is not None else None
        ),
        "status": outcome.status.value,
    }


__all__ = [
    "ActionCostEstimate",
    "ActionCostOutcome",
    "CostComponent",
    "CostComponentKind",
    "CostEstimateStatus",
    "CostOutcomeStatus",
    "LiquiditySnapshot",
    "ProspectiveMarketObservations",
    "SpreadProxyMethod",
    "action_cost_estimate_content_hash",
    "action_cost_estimate_id",
    "action_cost_outcome_content_hash",
    "action_cost_outcome_id",
    "estimate_hash_payload",
    "liquidity_snapshot_content_hash",
    "liquidity_snapshot_id",
    "outcome_hash_payload",
    "snapshot_hash_payload",
]
