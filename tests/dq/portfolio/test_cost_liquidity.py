"""WP7.2 — observational cost and liquidity model (#2703)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import polars as pl
import pytest
from digiquant.portfolio.action_cost_inputs import (
    ActionCostInput,
    ActionCostSide,
    RealizedCostInput,
)
from digiquant.portfolio.cost_liquidity import (
    METHOD_VERSION,
    adv_from_price_history,
    compare_action_cost,
    estimate_action_cost,
    prospective_observations_from_row,
)
from digiquant.portfolio.models.cost_liquidity import (
    CostComponentKind,
    CostEstimateStatus,
    CostOutcomeStatus,
    SpreadProxyMethod,
)
from digiquant.portfolio.risk_policy import resolve_risk_policy

pytestmark = pytest.mark.unit

_SESSION = date(2026, 8, 14)
_TS = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)
_CURRENCY = "USD"


def _action(
    *,
    side: ActionCostSide = ActionCostSide.BUY,
    quantity: Decimal = Decimal("100"),
    notional: Decimal | None = Decimal("15000.00"),
) -> ActionCostInput:
    return ActionCostInput(
        portfolio_commit_id=uuid4(),
        decision_intent_id=uuid4(),
        order_intent_id=uuid4(),
        run_date=_SESSION,
        symbol="AAPL",
        side=side,
        quantity=quantity,
        notional=notional,
        currency=_CURRENCY,
        effective_at=_TS,
        recorded_at=_TS,
    )


def _observations(
    *,
    close: Decimal = Decimal("150"),
    high: Decimal | None = Decimal("152"),
    low: Decimal | None = Decimal("148"),
    hist_vol_21: Decimal | None = Decimal("25"),
    adv_shares: Decimal | None = Decimal("1000000"),
    adv_dollars: Decimal | None = Decimal("150000000"),
) -> object:
    return prospective_observations_from_row(
        session_date=_SESSION,
        symbol="AAPL",
        row={
            "close": close,
            "high": high,
            "low": low,
            "volume": 1000000,
            "hist_vol_21": hist_vol_21,
        },
        observed_at=_TS,
        known_at=_TS,
        adv_shares=adv_shares,
        adv_dollars=adv_dollars,
    )


def _policy():
    return resolve_risk_policy(effective_at=_TS).policy


class TestEstimateActionCostComplete:
    def test_buy_decomposes_assumptions_and_observations(self) -> None:
        bundle = estimate_action_cost(_action(side=ActionCostSide.BUY), _observations(), _policy())
        est = bundle.estimate
        assert est.status is CostEstimateStatus.AVAILABLE
        assert est.method_version == METHOD_VERSION
        assert est.spread_proxy_method is SpreadProxyMethod.HIGH_LOW_RANGE_FRACTION
        assert est.total_cost is not None and est.total_cost > 0
        kinds = {c.kind: c for c in est.components}
        assert kinds[CostComponentKind.FEE].amount is not None
        assert kinds[CostComponentKind.SPREAD_HALF].amount is not None
        assert kinds[CostComponentKind.IMPACT].amount is not None
        assert kinds[CostComponentKind.TOTAL].amount == est.total_cost
        assert "fee_bps=" in kinds[CostComponentKind.FEE].assumption_label
        assert kinds[CostComponentKind.SPREAD_HALF].observation_label is not None

    def test_sell_matches_buy_economics_for_same_inputs(self) -> None:
        buy = estimate_action_cost(_action(side=ActionCostSide.BUY), _observations(), _policy())
        sell = estimate_action_cost(_action(side=ActionCostSide.SELL), _observations(), _policy())
        assert buy.estimate.total_cost == sell.estimate.total_cost

    def test_deterministic_hash_and_ids(self) -> None:
        action = _action()
        obs = _observations()
        policy = _policy()
        first = estimate_action_cost(action, obs, policy, estimated_at=_TS)
        second = estimate_action_cost(action, obs, policy, estimated_at=_TS)
        assert first.estimate.content_hash == second.estimate.content_hash
        assert first.estimate.estimate_id == second.estimate.estimate_id
        assert first.liquidity_snapshot.content_hash == second.liquidity_snapshot.content_hash
        assert len(first.estimate.content_hash) == 64


class TestEstimateMissingData:
    def test_missing_notional_is_unpriceable(self) -> None:
        action = _action(notional=None)
        obs = prospective_observations_from_row(
            session_date=_SESSION,
            symbol="AAPL",
            row={"close": None, "high": None, "low": None},
            observed_at=_TS,
            known_at=_TS,
        )
        bundle = estimate_action_cost(action, obs, _policy())
        assert bundle.estimate.status is CostEstimateStatus.UNPRICEABLE
        assert bundle.estimate.total_cost is None
        assert bundle.estimate.unavailable_reason == "notional_missing"
        for component in bundle.estimate.components:
            if component.kind is CostComponentKind.TOTAL:
                assert component.amount is None

    def test_missing_high_low_degrades_without_zero_spread(self) -> None:
        obs = prospective_observations_from_row(
            session_date=_SESSION,
            symbol="AAPL",
            row={"close": Decimal("150"), "high": None, "low": None, "hist_vol_21": Decimal("25")},
            observed_at=_TS,
            known_at=_TS,
            adv_shares=Decimal("1000000"),
        )
        bundle = estimate_action_cost(_action(), obs, _policy())
        spread = next(
            c for c in bundle.estimate.components if c.kind is CostComponentKind.SPREAD_HALF
        )
        assert spread.amount is None
        assert spread.unavailable_reason == "high_low_close_missing"
        assert bundle.estimate.status is CostEstimateStatus.DEGRADED
        assert bundle.estimate.total_cost is None

    def test_missing_vol_degrades_impact_not_zero(self) -> None:
        obs = prospective_observations_from_row(
            session_date=_SESSION,
            symbol="AAPL",
            row={
                "close": Decimal("150"),
                "high": Decimal("152"),
                "low": Decimal("148"),
                "hist_vol_21": None,
                "atr_pct": None,
            },
            observed_at=_TS,
            known_at=_TS,
            adv_shares=Decimal("1000000"),
        )
        bundle = estimate_action_cost(_action(), obs, _policy())
        impact = next(c for c in bundle.estimate.components if c.kind is CostComponentKind.IMPACT)
        assert impact.amount is None
        assert impact.unavailable_reason == "daily_sigma_missing"

    def test_missing_adv_degrades_liquidity_and_impact(self) -> None:
        obs = prospective_observations_from_row(
            session_date=_SESSION,
            symbol="AAPL",
            row={
                "close": Decimal("150"),
                "high": Decimal("152"),
                "low": Decimal("148"),
                "hist_vol_21": Decimal("25"),
            },
            observed_at=_TS,
            known_at=_TS,
            adv_shares=None,
        )
        bundle = estimate_action_cost(_action(), obs, _policy())
        assert bundle.liquidity_snapshot.status is CostEstimateStatus.DEGRADED
        impact = next(c for c in bundle.estimate.components if c.kind is CostComponentKind.IMPACT)
        assert impact.amount is None


class TestLiquidityExtremeParticipation:
    def test_extreme_participation_increases_days_to_liquidate(self) -> None:
        small_adv = Decimal("100")
        obs = prospective_observations_from_row(
            session_date=_SESSION,
            symbol="AAPL",
            row={
                "close": Decimal("150"),
                "high": Decimal("152"),
                "low": Decimal("148"),
                "hist_vol_21": Decimal("25"),
            },
            observed_at=_TS,
            known_at=_TS,
            adv_shares=small_adv,
        )
        bundle = estimate_action_cost(_action(quantity=Decimal("50")), obs, _policy())
        assert bundle.liquidity_snapshot.participation_pct == Decimal("50.00000000")
        assert bundle.liquidity_snapshot.days_to_liquidate is not None
        assert bundle.liquidity_snapshot.days_to_liquidate >= 2


class TestAdvFromPriceHistory:
    def test_polars_adv_computation(self) -> None:
        history = pl.DataFrame(
            {
                "date": [date(2026, 8, 12), date(2026, 8, 13), date(2026, 8, 14)],
                "ticker": ["AAPL", "AAPL", "AAPL"],
                "close": [100.0, 110.0, 120.0],
                "volume": [1000.0, 2000.0, 3000.0],
            }
        )
        adv_shares, adv_dollars = adv_from_price_history(
            history,
            symbol="AAPL",
            as_of_session=date(2026, 8, 14),
            lookback_days=3,
        )
        assert adv_shares == Decimal("2000.00000000")
        assert adv_dollars == Decimal("226666.67")


class TestCompareActionCost:
    def _realized(self, **overrides: object) -> RealizedCostInput:
        fields = dict(
            execution_id=uuid4(),
            order_intent_id=uuid4(),
            executed_date=date(2026, 8, 15),
            symbol="AAPL",
            side=ActionCostSide.BUY,
            quantity=Decimal("100"),
            price=Decimal("150"),
            notional=Decimal("15000"),
            currency=_CURRENCY,
            fee=Decimal("1.25"),
            slippage=Decimal("2.50"),
            executed_at=datetime(2026, 8, 15, 13, 0, tzinfo=UTC),
            recorded_at=datetime(2026, 8, 15, 13, 0, tzinfo=UTC),
        )
        fields.update(overrides)
        return RealizedCostInput(**fields)

    def test_expected_vs_realized_components(self) -> None:
        bundle = estimate_action_cost(_action(), _observations(), _policy(), estimated_at=_TS)
        outcome = compare_action_cost(bundle.estimate, self._realized(), compared_at=_TS)
        assert outcome.status is CostOutcomeStatus.COMPARED
        assert outcome.expected_total == bundle.estimate.total_cost
        assert outcome.realized_total == Decimal("3.75")
        assert outcome.residual == Decimal("3.75") - bundle.estimate.total_cost
        assert outcome.realized_fee == Decimal("1.25")
        assert outcome.realized_slippage == Decimal("2.50")
        assert len(outcome.expected_components) == len(bundle.estimate.components)

    def test_unpriceable_estimate_with_fill_is_unavailable(self) -> None:
        action = _action(notional=None)
        obs = prospective_observations_from_row(
            session_date=_SESSION,
            symbol="AAPL",
            row={"close": None},
            observed_at=_TS,
            known_at=_TS,
        )
        estimate = estimate_action_cost(action, obs, _policy()).estimate
        outcome = compare_action_cost(estimate, self._realized(), compared_at=_TS)
        assert outcome.status is CostOutcomeStatus.UNAVAILABLE
        assert outcome.unavailable_reason == "expected_cost_unpriceable"
        assert outcome.realized_total is None


class TestRiskPolicyCostCoefficients:
    def test_default_policy_resolves_observational_cost_leaves(self) -> None:
        policy = _policy()
        assert policy.cost_policy.available is True
        assert policy.cost_policy.enforced is False
        assert policy.liquidity_limits.available is True
        assert policy.liquidity_limits.enforced is False
        assert policy.liquidity_limits.limit == 25.0
        assert policy.cost_coefficients["fee_bps"].value == 5.0
        assert policy.cost_coefficients["impact_alpha"].value == 0.10

    def test_factor_stress_tail_remain_unavailable(self) -> None:
        policy = _policy()
        for cap in (policy.factor_limits, policy.stress_limits, policy.tail_limits):
            assert cap.available is False
            assert cap.reason == "phase1_not_implemented"
