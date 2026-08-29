"""Pure observational cost and liquidity estimator (#2703 / WP7.2).

Consumes :class:`ActionCostInput` from WP7.1, prospective OHLCV/technicals, and a
resolved :class:`RiskPolicy`. No Supabase I/O; no production control path in Phase 1.

Spread proxies use labeled high-low range fractions — never bid/ask quotes.
Missing economics map to typed unpriceable/degraded states, never zero-by-omission.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

import polars as pl

from digiquant.olympus.hermes.action_cost_inputs import ActionCostInput, RealizedCostInput
from digiquant.olympus.hermes.models.cost_liquidity import (
    ActionCostEstimate,
    ActionCostOutcome,
    CostComponent,
    CostComponentKind,
    CostEstimateStatus,
    CostOutcomeStatus,
    LiquiditySnapshot,
    ProspectiveMarketObservations,
    SpreadProxyMethod,
    action_cost_estimate_content_hash,
    action_cost_estimate_id,
    action_cost_outcome_content_hash,
    action_cost_outcome_id,
    estimate_hash_payload,
    liquidity_snapshot_content_hash,
    liquidity_snapshot_id,
    outcome_hash_payload,
    snapshot_hash_payload,
)
from digiquant.olympus.hermes.models.risk_policy import RiskPolicy

METHOD_VERSION = "observational-cost@v1"
"""Implementation version stamped on every estimate and liquidity snapshot."""

SPREAD_PROXY_METHOD = SpreadProxyMethod.HIGH_LOW_RANGE_FRACTION
"""Persisted label — range proxy, not a live quote."""

_ANNUALIZE_TRADING_DAYS = Decimal("252")
_MONEY_QUANTUM = Decimal("0.01")
_RATIO_QUANTUM = Decimal("0.00000001")

_DEFAULT_FEE_BPS = Decimal("5")
_DEFAULT_IMPACT_ALPHA = Decimal("0.10")
_DEFAULT_SPREAD_RANGE_FRACTION = Decimal("0.50")
_DEFAULT_ADV_LOOKBACK_DAYS = 21
_DEFAULT_MAX_ADV_PARTICIPATION_PCT = Decimal("25")
_DEFAULT_CONSERVATIVE_MULTIPLIER = Decimal("2.0")

DEFAULT_FEE_BPS = _DEFAULT_FEE_BPS
DEFAULT_IMPACT_ALPHA = _DEFAULT_IMPACT_ALPHA
DEFAULT_SPREAD_RANGE_FRACTION = _DEFAULT_SPREAD_RANGE_FRACTION
DEFAULT_ADV_LOOKBACK_DAYS = _DEFAULT_ADV_LOOKBACK_DAYS
DEFAULT_MAX_ADV_PARTICIPATION_PCT = _DEFAULT_MAX_ADV_PARTICIPATION_PCT
DEFAULT_CONSERVATIVE_MULTIPLIER = _DEFAULT_CONSERVATIVE_MULTIPLIER

COST_CONFIG_KEYS: dict[str, str] = {
    "fee_bps": "cost_fee_bps",
    "impact_alpha": "cost_impact_alpha",
    "spread_range_fraction": "cost_spread_range_fraction",
    "adv_lookback_days": "cost_adv_lookback_days",
    "max_adv_participation_pct": "cost_max_adv_participation_pct",
    "conservative_multiplier": "cost_conservative_multiplier",
}


@dataclass(frozen=True)
class ResolvedCostCoefficients:
    """Fully resolved observational cost coefficients from policy leaves."""

    fee_bps: Decimal
    impact_alpha: Decimal
    spread_range_fraction: Decimal
    adv_lookback_days: int
    max_adv_participation_pct: Decimal
    conservative_multiplier: Decimal


@dataclass(frozen=True)
class CostLiquidityBundle:
    """Liquidity snapshot plus prospective estimate for one action."""

    liquidity_snapshot: LiquiditySnapshot
    estimate: ActionCostEstimate


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _ratio(value: Decimal) -> Decimal:
    return value.quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_UP)


def _observations_hash(observations: ProspectiveMarketObservations) -> str:
    payload = {
        "session_date": observations.session_date.isoformat(),
        "symbol": observations.symbol,
        "close": str(observations.close) if observations.close is not None else None,
        "high": str(observations.high) if observations.high is not None else None,
        "low": str(observations.low) if observations.low is not None else None,
        "volume": observations.volume,
        "hist_vol_21": (
            str(observations.hist_vol_21) if observations.hist_vol_21 is not None else None
        ),
        "atr_pct": str(observations.atr_pct) if observations.atr_pct is not None else None,
        "adv_shares": (
            str(observations.adv_shares) if observations.adv_shares is not None else None
        ),
        "adv_dollars": (
            str(observations.adv_dollars) if observations.adv_dollars is not None else None
        ),
        "observed_at": observations.observed_at.isoformat(),
        "known_at": observations.known_at.isoformat(),
    }
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def cost_coefficients_from_policy(policy: RiskPolicy) -> ResolvedCostCoefficients:
    """Read observational coefficients from resolved policy leaves."""
    leaves = policy.cost_coefficients
    return ResolvedCostCoefficients(
        fee_bps=Decimal(str(leaves["fee_bps"].value)),
        impact_alpha=Decimal(str(leaves["impact_alpha"].value)),
        spread_range_fraction=Decimal(str(leaves["spread_range_fraction"].value)),
        adv_lookback_days=int(leaves["adv_lookback_days"].value),
        max_adv_participation_pct=Decimal(str(leaves["max_adv_participation_pct"].value)),
        conservative_multiplier=Decimal(str(leaves["conservative_multiplier"].value)),
    )


def adv_from_price_history(
    history: pl.DataFrame,
    *,
    symbol: str,
    as_of_session: date,
    lookback_days: int,
) -> tuple[Decimal | None, Decimal | None]:
    """Compute ADV shares and dollars from a Polars OHLCV frame (no pandas)."""
    if history.is_empty():
        return None, None
    frame = history.filter(
        pl.col("ticker").str.to_uppercase() == symbol.strip().upper(),
        pl.col("date") <= as_of_session,
    )
    if frame.is_empty():
        return None, None
    frame = frame.sort("date", descending=True).head(lookback_days)
    if frame.height == 0:
        return None, None
    if "volume" not in frame.columns or "close" not in frame.columns:
        return None, None
    vol = frame.select(pl.col("volume").cast(pl.Float64)).to_series()
    close = frame.select(pl.col("close").cast(pl.Float64)).to_series()
    if vol.null_count() == vol.len() or close.null_count() == close.len():
        return None, None
    adv_shares = Decimal(str(vol.mean()))
    adv_dollars = Decimal(str((vol * close).mean()))
    if adv_shares <= 0 or adv_dollars <= 0:
        return None, None
    return _ratio(adv_shares), _money(adv_dollars)


def prospective_observations_from_row(
    *,
    session_date: date,
    symbol: str,
    row: dict[str, object],
    observed_at: datetime,
    known_at: datetime,
    adv_shares: Decimal | None = None,
    adv_dollars: Decimal | None = None,
) -> ProspectiveMarketObservations:
    """Build observations from one OHLCV/technicals row dict."""

    def _dec(key: str) -> Decimal | None:
        raw = row.get(key)
        if raw is None:
            return None
        return Decimal(str(raw))

    volume_raw = row.get("volume")
    volume = int(volume_raw) if volume_raw is not None else None

    return ProspectiveMarketObservations(
        session_date=session_date,
        symbol=symbol,
        close=_dec("close"),
        high=_dec("high"),
        low=_dec("low"),
        volume=volume,
        hist_vol_21=_dec("hist_vol_21"),
        atr_pct=_dec("atr_pct"),
        adv_shares=adv_shares,
        adv_dollars=adv_dollars,
        observed_at=observed_at,
        known_at=known_at,
    )


def _daily_sigma(observations: ProspectiveMarketObservations) -> Decimal | None:
    if observations.hist_vol_21 is not None and observations.hist_vol_21 > 0:
        annual = observations.hist_vol_21 / Decimal("100")
        return _ratio(annual / _ANNUALIZE_TRADING_DAYS.sqrt())
    if observations.atr_pct is not None and observations.atr_pct > 0:
        return _ratio(observations.atr_pct / Decimal("100"))
    return None


def _resolve_notional(
    action: ActionCostInput,
    observations: ProspectiveMarketObservations,
) -> Decimal | None:
    if action.notional is not None:
        return action.notional
    if observations.close is None:
        return None
    return _money(action.quantity * observations.close)


def _build_liquidity_snapshot(
    *,
    action: ActionCostInput,
    observations: ProspectiveMarketObservations,
    coeffs: ResolvedCostCoefficients,
    resolved_at: datetime,
) -> LiquiditySnapshot:
    obs_hash = _observations_hash(observations)
    adv_shares = observations.adv_shares
    adv_dollars = observations.adv_dollars
    participation: Decimal | None = None
    days_to_liquidate: int | None = None
    status = CostEstimateStatus.AVAILABLE
    unavailable_reason: str | None = None

    if adv_shares is None or adv_shares <= 0:
        status = CostEstimateStatus.DEGRADED
        unavailable_reason = "adv_shares_missing"
    else:
        participation = _ratio((action.quantity / adv_shares) * Decimal("100"))
        if coeffs.max_adv_participation_pct > 0:
            days = math.ceil(float(participation / coeffs.max_adv_participation_pct))
            days_to_liquidate = max(1, days)

    draft = LiquiditySnapshot.model_construct(
        snapshot_id=liquidity_snapshot_id(
            symbol=action.symbol,
            as_of_session=observations.session_date,
            quantity=action.quantity,
            content_hash="0" * 64,
        ),
        method_version=METHOD_VERSION,
        symbol=action.symbol,
        as_of_session=observations.session_date,
        quantity=action.quantity,
        adv_shares=adv_shares,
        adv_dollars=adv_dollars,
        participation_pct=participation,
        days_to_liquidate=days_to_liquidate,
        max_adv_participation_pct=coeffs.max_adv_participation_pct,
        status=status,
        unavailable_reason=unavailable_reason,
        observations_hash=obs_hash,
        resolved_at=resolved_at,
        content_hash="0" * 64,
    )
    content_hash = liquidity_snapshot_content_hash(payload=snapshot_hash_payload(draft))
    snapshot_id = liquidity_snapshot_id(
        symbol=action.symbol,
        as_of_session=observations.session_date,
        quantity=action.quantity,
        content_hash=content_hash,
    )
    return LiquiditySnapshot.model_validate(
        {
            **draft.model_dump(),
            "content_hash": content_hash,
            "snapshot_id": snapshot_id,
        }
    )


def _component(
    *,
    kind: CostComponentKind,
    amount: Decimal | None,
    currency: str | None,
    assumption_label: str,
    observation_label: str | None = None,
    unavailable_reason: str | None = None,
) -> CostComponent:
    return CostComponent(
        kind=kind,
        amount=_money(amount) if amount is not None else None,
        currency=currency,
        assumption_label=assumption_label,
        observation_label=observation_label,
        unavailable_reason=unavailable_reason,
    )


def estimate_action_cost(
    action: ActionCostInput,
    observations: ProspectiveMarketObservations,
    policy: RiskPolicy,
    *,
    estimated_at: datetime | None = None,
) -> CostLiquidityBundle:
    """Estimate observational fees, spread proxy, impact, and liquidity for one action."""
    at = estimated_at or datetime.now(tz=UTC)
    if at.tzinfo is None or at.utcoffset() != timedelta(0):
        raise ValueError("estimated_at must be timezone-aware UTC")

    coeffs = cost_coefficients_from_policy(policy)
    liquidity = _build_liquidity_snapshot(
        action=action,
        observations=observations,
        coeffs=coeffs,
        resolved_at=at,
    )

    currency = action.currency.strip().upper()
    notional = _resolve_notional(action, observations)
    if notional is None:
        components = (
            _component(
                kind=CostComponentKind.FEE,
                amount=None,
                currency=None,
                assumption_label=f"fee_bps={coeffs.fee_bps}",
                unavailable_reason="notional_missing",
            ),
            _component(
                kind=CostComponentKind.SPREAD_HALF,
                amount=None,
                currency=None,
                assumption_label=SPREAD_PROXY_METHOD.value,
                unavailable_reason="notional_missing",
            ),
            _component(
                kind=CostComponentKind.IMPACT,
                amount=None,
                currency=None,
                assumption_label=f"impact_alpha={coeffs.impact_alpha}",
                unavailable_reason="notional_missing",
            ),
            _component(
                kind=CostComponentKind.TOTAL,
                amount=None,
                currency=None,
                assumption_label="sum_components",
                unavailable_reason="notional_missing",
            ),
        )
        return _finalize_estimate(
            action=action,
            policy=policy,
            liquidity=liquidity,
            components=components,
            total_cost=None,
            status=CostEstimateStatus.UNPRICEABLE,
            unavailable_reason="notional_missing",
            notional=None,
            estimated_at=at,
        )

    fee_amount = _money(notional * coeffs.fee_bps / Decimal("10000"))
    fee_component = _component(
        kind=CostComponentKind.FEE,
        amount=fee_amount,
        currency=currency,
        assumption_label=f"fee_bps={coeffs.fee_bps}",
        observation_label=f"notional={notional}",
    )

    spread_amount: Decimal | None = None
    spread_reason: str | None = None
    if (
        observations.high is not None
        and observations.low is not None
        and observations.close is not None
        and observations.high >= observations.low
    ):
        range_spread = coeffs.spread_range_fraction * (observations.high - observations.low)
        half_spread_per_share = range_spread / Decimal("2")
        spread_amount = _money(half_spread_per_share * action.quantity)
    else:
        spread_reason = "high_low_close_missing"

    spread_component = _component(
        kind=CostComponentKind.SPREAD_HALF,
        amount=spread_amount,
        currency=currency if spread_amount is not None else None,
        assumption_label=(
            f"{SPREAD_PROXY_METHOD.value}|range_fraction={coeffs.spread_range_fraction}"
        ),
        observation_label=(
            f"high={observations.high}|low={observations.low}"
            if spread_amount is not None
            else None
        ),
        unavailable_reason=spread_reason,
    )

    impact_amount: Decimal | None = None
    impact_reason: str | None = None
    daily_sigma = _daily_sigma(observations)
    adv_shares = observations.adv_shares
    if daily_sigma is None:
        impact_reason = "daily_sigma_missing"
    elif adv_shares is None or adv_shares <= 0:
        impact_reason = "adv_shares_missing"
    elif observations.close is None:
        impact_reason = "close_missing"
    else:
        participation_ratio = action.quantity / adv_shares
        raw_impact = (
            coeffs.impact_alpha
            * daily_sigma
            * participation_ratio.sqrt()
            * action.quantity
            * observations.close
        )
        if liquidity.status is CostEstimateStatus.DEGRADED:
            raw_impact *= coeffs.conservative_multiplier
        impact_amount = _money(raw_impact)

    impact_component = _component(
        kind=CostComponentKind.IMPACT,
        amount=impact_amount,
        currency=currency if impact_amount is not None else None,
        assumption_label=f"impact_alpha={coeffs.impact_alpha}",
        observation_label=(
            f"daily_sigma={daily_sigma}|adv_shares={adv_shares}"
            if impact_amount is not None
            else None
        ),
        unavailable_reason=impact_reason,
    )

    degraded = any(
        c.amount is None and c.kind != CostComponentKind.TOTAL
        for c in (fee_component, spread_component, impact_component)
    )
    if degraded:
        total_cost: Decimal | None = None
        total_reason = "component_missing"
        status = CostEstimateStatus.DEGRADED
        unavailable_reason = "partial_cost_components"
    else:
        total_cost = _money(fee_amount + spread_amount + impact_amount)
        total_reason = None
        status = CostEstimateStatus.AVAILABLE
        unavailable_reason = None

    total_component = _component(
        kind=CostComponentKind.TOTAL,
        amount=total_cost,
        currency=currency if total_cost is not None else None,
        assumption_label="sum_components",
        unavailable_reason=total_reason,
    )

    return _finalize_estimate(
        action=action,
        policy=policy,
        liquidity=liquidity,
        components=(fee_component, spread_component, impact_component, total_component),
        total_cost=total_cost,
        status=status,
        unavailable_reason=unavailable_reason,
        notional=notional,
        estimated_at=at,
    )


def _finalize_estimate(
    *,
    action: ActionCostInput,
    policy: RiskPolicy,
    liquidity: LiquiditySnapshot,
    components: Sequence[CostComponent],
    total_cost: Decimal | None,
    status: CostEstimateStatus,
    unavailable_reason: str | None,
    notional: Decimal | None,
    estimated_at: datetime,
) -> CostLiquidityBundle:
    draft = ActionCostEstimate.model_construct(
        estimate_id=action_cost_estimate_id(
            order_intent_id=action.order_intent_id,
            policy_content_hash=policy.content_hash,
            content_hash="0" * 64,
        ),
        method_version=METHOD_VERSION,
        portfolio_commit_id=action.portfolio_commit_id,
        decision_intent_id=action.decision_intent_id,
        order_intent_id=action.order_intent_id,
        symbol=action.symbol,
        side=action.side,
        quantity=action.quantity,
        notional=notional,
        currency=action.currency.strip().upper(),
        policy_id=policy.policy_id,
        policy_content_hash=policy.content_hash,
        liquidity_snapshot_id=liquidity.snapshot_id,
        spread_proxy_method=SPREAD_PROXY_METHOD,
        components=tuple(components),
        total_cost=total_cost,
        status=status,
        unavailable_reason=unavailable_reason,
        effective_at=action.effective_at,
        estimated_at=estimated_at,
        content_hash="0" * 64,
    )
    content_hash = action_cost_estimate_content_hash(payload=estimate_hash_payload(draft))
    estimate_id = action_cost_estimate_id(
        order_intent_id=action.order_intent_id,
        policy_content_hash=policy.content_hash,
        content_hash=content_hash,
    )
    estimate = ActionCostEstimate.model_validate(
        {
            **draft.model_dump(),
            "content_hash": content_hash,
            "estimate_id": estimate_id,
        }
    )
    return CostLiquidityBundle(liquidity_snapshot=liquidity, estimate=estimate)


def compare_action_cost(
    estimate: ActionCostEstimate,
    realized: RealizedCostInput,
    *,
    compared_at: datetime | None = None,
) -> ActionCostOutcome:
    """Compare a prospective estimate with an authoritative realized fill."""
    at = compared_at or datetime.now(tz=UTC)
    if at.tzinfo is None or at.utcoffset() != timedelta(0):
        raise ValueError("compared_at must be timezone-aware UTC")

    currency = realized.currency.strip().upper()
    if estimate.currency != currency:
        draft = ActionCostOutcome.model_construct(
            outcome_id=action_cost_outcome_id(
                estimate_id=estimate.estimate_id,
                execution_id=realized.execution_id,
                content_hash="0" * 64,
            ),
            estimate_id=estimate.estimate_id,
            execution_id=realized.execution_id,
            order_intent_id=realized.order_intent_id,
            currency=currency,
            expected_total=None,
            realized_total=None,
            residual=None,
            expected_components=estimate.components,
            realized_fee=None,
            realized_slippage=None,
            status=CostOutcomeStatus.UNAVAILABLE,
            unavailable_reason="currency_mismatch",
            compared_at=at,
            content_hash="0" * 64,
        )
        content_hash = action_cost_outcome_content_hash(payload=outcome_hash_payload(draft))
        outcome_id = action_cost_outcome_id(
            estimate_id=estimate.estimate_id,
            execution_id=realized.execution_id,
            content_hash=content_hash,
        )
        return ActionCostOutcome.model_validate(
            {**draft.model_dump(), "content_hash": content_hash, "outcome_id": outcome_id}
        )

    if estimate.status in (CostEstimateStatus.UNPRICEABLE, CostEstimateStatus.UNAVAILABLE):
        draft = ActionCostOutcome.model_construct(
            outcome_id=action_cost_outcome_id(
                estimate_id=estimate.estimate_id,
                execution_id=realized.execution_id,
                content_hash="0" * 64,
            ),
            estimate_id=estimate.estimate_id,
            execution_id=realized.execution_id,
            order_intent_id=realized.order_intent_id,
            currency=currency,
            expected_total=None,
            realized_total=None,
            residual=None,
            expected_components=estimate.components,
            realized_fee=None,
            realized_slippage=None,
            status=CostOutcomeStatus.UNAVAILABLE,
            unavailable_reason="expected_cost_unpriceable",
            compared_at=at,
            content_hash="0" * 64,
        )
        content_hash = action_cost_outcome_content_hash(payload=outcome_hash_payload(draft))
        outcome_id = action_cost_outcome_id(
            estimate_id=estimate.estimate_id,
            execution_id=realized.execution_id,
            content_hash=content_hash,
        )
        return ActionCostOutcome.model_validate(
            {**draft.model_dump(), "content_hash": content_hash, "outcome_id": outcome_id}
        )

    realized_total = _money(realized.fee + abs(realized.slippage))
    expected_total = estimate.total_cost
    residual = _money(realized_total - expected_total) if expected_total is not None else None

    draft = ActionCostOutcome.model_construct(
        outcome_id=action_cost_outcome_id(
            estimate_id=estimate.estimate_id,
            execution_id=realized.execution_id,
            content_hash="0" * 64,
        ),
        estimate_id=estimate.estimate_id,
        execution_id=realized.execution_id,
        order_intent_id=realized.order_intent_id,
        currency=currency,
        expected_total=expected_total,
        realized_total=realized_total,
        residual=residual,
        expected_components=estimate.components,
        realized_fee=realized.fee,
        realized_slippage=realized.slippage,
        status=CostOutcomeStatus.COMPARED,
        unavailable_reason=None,
        compared_at=at,
        content_hash="0" * 64,
    )
    content_hash = action_cost_outcome_content_hash(payload=outcome_hash_payload(draft))
    outcome_id = action_cost_outcome_id(
        estimate_id=estimate.estimate_id,
        execution_id=realized.execution_id,
        content_hash=content_hash,
    )
    return ActionCostOutcome.model_validate(
        {**draft.model_dump(), "content_hash": content_hash, "outcome_id": outcome_id}
    )


__all__ = [
    "COST_CONFIG_KEYS",
    "CostLiquidityBundle",
    "DEFAULT_ADV_LOOKBACK_DAYS",
    "DEFAULT_CONSERVATIVE_MULTIPLIER",
    "DEFAULT_FEE_BPS",
    "DEFAULT_IMPACT_ALPHA",
    "DEFAULT_MAX_ADV_PARTICIPATION_PCT",
    "DEFAULT_SPREAD_RANGE_FRACTION",
    "METHOD_VERSION",
    "ResolvedCostCoefficients",
    "SPREAD_PROXY_METHOD",
    "adv_from_price_history",
    "compare_action_cost",
    "cost_coefficients_from_policy",
    "estimate_action_cost",
    "prospective_observations_from_row",
]
