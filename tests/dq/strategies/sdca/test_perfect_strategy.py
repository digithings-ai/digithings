"""Tests for the perfect-strategy oracle (#4804) — all-in / flat period path.

The parity pin is the important one: with every date in the buy set the oracle
is lump-sum buy-and-hold, and its equity path must equal
``dca_metrics.lump_mark_to_market`` element for element. That is what stops the
oracle from quietly becoming a second, softer backtest path.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from digiquant.strategies.sdca.dca_metrics import lump_mark_to_market
from digiquant.strategies.sdca.perfect_strategy import (
    PerfectStrategyMetrics,
    perfect_strategy_metrics,
    perfect_strategy_path,
)
from digiquant.strategies.sdca.risk_metrics import RiskMetrics

pytestmark = pytest.mark.unit

_START = date(2024, 1, 1)
_PRICES = (100.0, 120.0, 90.0, 150.0, 130.0)


def _days(n: int) -> list[date]:
    return [_START + timedelta(days=i) for i in range(n)]


def test_all_buy_path_equals_lump_mark_to_market() -> None:
    """PARITY PIN: an always-buy period set is lump-sum, not a softer DCA.

    EXACT equality, not ``pytest.approx``: both paths reach the same floats
    through the same ``units * price`` arithmetic, so any drift is a real
    divergence and a tolerance would only hide it (#4804 review, LOW).
    """
    dates = _days(len(_PRICES))
    values, exposure = perfect_strategy_path(dates, _PRICES, dates, [], 1000.0)
    lump = lump_mark_to_market(_PRICES, 1000.0)
    assert values == lump
    assert all(exposure)


def test_all_buy_metrics_equal_lump_return() -> None:
    dates = _days(len(_PRICES))
    metrics = perfect_strategy_metrics(dates, _PRICES, dates, [], 1000.0)
    lump_final = lump_mark_to_market(_PRICES, 1000.0)[-1]
    assert metrics.metrics.total_return_pct == pytest.approx((lump_final / 1000.0 - 1.0) * 100.0)
    assert metrics.exposure_pct == pytest.approx(100.0)


def test_all_sell_path_is_flat_cash() -> None:
    """Never-buy is the oracle's flat comparator: constant cash, zero exposure."""
    dates = _days(len(_PRICES))
    values, exposure = perfect_strategy_path(dates, _PRICES, [], dates, 1000.0)
    assert values == pytest.approx([1000.0] * len(_PRICES))
    assert not any(exposure)


def test_all_sell_metrics_are_zeroed() -> None:
    dates = _days(len(_PRICES))
    metrics = perfect_strategy_metrics(dates, _PRICES, [], dates, 1000.0)
    assert metrics.exposure_pct == pytest.approx(0.0)
    assert metrics.metrics.total_return_pct == pytest.approx(0.0)
    assert metrics.metrics.cagr_pct == pytest.approx(0.0)
    assert metrics.metrics.sharpe == pytest.approx(0.0)
    assert metrics.metrics.sortino == pytest.approx(0.0)
    assert metrics.metrics.calmar == pytest.approx(0.0)
    assert metrics.metrics.max_drawdown_pct == pytest.approx(0.0)


def test_buy_then_sell_realizes_the_swing_and_flats_the_rest() -> None:
    # Buy all-in at 100 (day 0), ride to 120 (day 1), sell all at 90 (day 2).
    dates = _days(3)
    values, exposure = perfect_strategy_path(
        dates, (100.0, 120.0, 90.0), [dates[0]], [dates[2]], 1000.0
    )
    assert values == pytest.approx([1000.0, 1200.0, 900.0])
    assert exposure == [True, True, False]
    metrics = perfect_strategy_metrics(dates, (100.0, 120.0, 90.0), [dates[0]], [dates[2]], 1000.0)
    assert metrics.metrics.total_return_pct == pytest.approx(-10.0)
    assert metrics.exposure_pct == pytest.approx(200.0 / 3.0)


def test_neutral_dates_hold_the_previous_position() -> None:
    """A date in neither set holds: the oracle never times an exit by omission."""
    dates = _days(4)
    values, exposure = perfect_strategy_path(
        dates, (100.0, 110.0, 90.0, 95.0), [dates[0]], [dates[3]], 1000.0
    )
    # 10 units from the day-0 all-in buy ride every neutral close.
    assert values == pytest.approx([1000.0, 1100.0, 900.0, 950.0])
    assert exposure == [True, True, True, False]


def test_a_later_buy_deploys_all_reinvested_cash() -> None:
    dates = _days(4)
    # Flat after the day-1 sell (90.0 → 900.0 cash), then all back in at 95.0.
    values, exposure = perfect_strategy_path(
        dates, (100.0, 90.0, 95.0, 190.0), [dates[0], dates[2]], [dates[1]], 1000.0
    )
    assert values == pytest.approx([1000.0, 900.0, 900.0, 1800.0])
    assert exposure == [True, False, True, True]


def test_sell_dates_win_when_a_date_is_in_both_sets() -> None:
    """Documented precedence: a sell vetoes a same-day buy (flat is the safe read)."""
    dates = _days(2)
    values, exposure = perfect_strategy_path(dates, (100.0, 110.0), [dates[0]], [dates[0]], 1000.0)
    assert values == pytest.approx([1000.0, 1000.0])
    assert exposure == [False, False]


def test_multi_day_period_sets_switch_position_on_their_edges() -> None:
    dates = _days(len(_PRICES))
    values, exposure = perfect_strategy_path(dates, _PRICES, dates[:2], dates[2:], 1000.0)
    # Buy 100, 120 → flat at 90 on day 2 → 900 cash held through 150 → 130.
    assert values == pytest.approx([1000.0, 1200.0, 900.0, 900.0, 900.0])
    assert exposure == [True, True, False, False, False]


def test_metrics_nest_risk_metrics_and_are_frozen() -> None:
    dates = _days(len(_PRICES))
    metrics = perfect_strategy_metrics(dates, _PRICES, dates[:2], dates[2:], 1000.0)
    assert isinstance(metrics, PerfectStrategyMetrics)
    assert isinstance(metrics.metrics, RiskMetrics)
    assert 0.0 <= metrics.exposure_pct <= 100.0
    with pytest.raises(Exception, match="frozen|immutable"):
        metrics.exposure_pct = 1.0  # type: ignore[misc]
    for name, field in PerfectStrategyMetrics.model_fields.items():
        assert field.description, f"{name} has no description"


def test_annualization_is_forwarded_to_the_risk_metrics() -> None:
    dates = _days(len(_PRICES))
    annual = perfect_strategy_metrics(dates, _PRICES, dates, [], 1000.0, annualization=252)
    weekly = perfect_strategy_metrics(dates, _PRICES, dates, [], 1000.0, annualization=63)
    assert weekly.metrics.sharpe == pytest.approx(annual.metrics.sharpe * 0.5, rel=1e-12)


@pytest.mark.parametrize(
    ("prices", "buy", "sell", "cash", "match"),
    [
        ([], [], [], 1000.0, "at least one"),
        ([100.0, 101.0], [], [], 0.0, "positive"),
        ([100.0, 101.0], [], [], -1.0, "positive"),
        ([100.0, 101.0], [], [], float("nan"), "positive"),
        ([100.0, 0.0], [date(2024, 1, 1)], [], 1000.0, "positive"),
        ([-100.0, -101.0], [date(2024, 1, 1)], [], 1000.0, "positive"),
    ],
)
def test_invalid_inputs_raise(
    prices: list[float],
    buy: list[date],
    sell: list[date],
    cash: float,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        perfect_strategy_path(_days(len(prices)), prices, buy, sell, cash)


def test_length_mismatch_between_dates_and_prices_raises() -> None:
    with pytest.raises(ValueError, match="same length"):
        perfect_strategy_path(_days(3), [100.0, 101.0], [], [], 1000.0)


def test_a_one_day_calendar_fails_at_the_metrics_wrapper() -> None:
    """#4804 review, LOW: the wrapper raises the same guard ``equity_metrics`` does.

    A 1-day calendar has no return at all, so it must fail with a message that
    names the wrapper and the reason rather than surfacing a bare risk_metrics
    error from two frames down.
    """
    dates = _days(1)
    with pytest.raises(ValueError, match="perfect_strategy_metrics requires at least two days"):
        perfect_strategy_metrics(dates, [100.0], dates, [], 1000.0)
    with pytest.raises(ValueError, match="perfect_strategy_metrics requires at least two days"):
        perfect_strategy_metrics([], [], [], [], 1000.0)


def test_out_of_window_dates_are_ignored() -> None:
    """Windows are pinned per asset; a pin outside the price calendar is a no-op."""
    dates = _days(3)
    values, exposure = perfect_strategy_path(
        dates,
        (100.0, 110.0, 120.0),
        [date(1999, 1, 1)],
        [date(2030, 1, 1)],
        1000.0,
    )
    assert values == pytest.approx([1000.0, 1000.0, 1000.0])
    assert exposure == [False, False, False]
