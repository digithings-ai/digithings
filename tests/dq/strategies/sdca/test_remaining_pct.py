"""Remaining-cash / remaining-holdings compounding for SDCA sizing.

The daily curve rate is a percent of the *current* book, never of initial
cash or of the original position. Two cheap days at 50%/day therefore leave
25% cash (not zero); two rich days at 50%/day of holdings leave 25% of the
units that were held when selling started.
"""

from __future__ import annotations

import inspect

import polars as pl
import pytest
from digiquant.strategies.sdca.backtest import run_backtest, size_trade
from digiquant.strategies.sdca.curve import AccumDistCurve

pytestmark = pytest.mark.unit


def _dates(n: int) -> pl.Series:
    return pl.date_range(pl.date(2024, 1, 1), pl.date(2024, 1, n), interval="1d", eager=True)


def _flat_curve(rate: float) -> AccumDistCurve:
    return AccumDistCurve(nodes=tuple(rate for _ in range(21)))


class TestSizeTradeRemainingBook:
    def test_buy_is_percent_of_current_cash_not_a_fixed_notional(self) -> None:
        buy_usd, sell_units = size_trade(50.0, cash=1000.0, asset_units=0.0)
        assert sell_units == 0.0
        assert buy_usd == pytest.approx(500.0)

        buy_usd_2, _ = size_trade(50.0, cash=500.0, asset_units=5.0)
        assert buy_usd_2 == pytest.approx(250.0)

    def test_sell_is_percent_of_current_holdings_not_original_position(self) -> None:
        buy_usd, sell_units = size_trade(-50.0, cash=0.0, asset_units=10.0)
        assert buy_usd == 0.0
        assert sell_units == pytest.approx(5.0)

        _, sell_units_2 = size_trade(-50.0, cash=500.0, asset_units=5.0)
        assert sell_units_2 == pytest.approx(2.5)


class TestRemainingCashCompounding:
    def test_two_cheap_days_at_50_pct_leave_quarter_cash_not_zero(self) -> None:
        """50% of remaining cash twice → 25% left.

        If the rate were applied to initial cash, two days of 50% would
        empty the book (1000 − 500 − 500 = 0).
        """
        _, frame = run_backtest(
            dates=_dates(2),
            price=pl.Series([100.0, 100.0]),
            risk=pl.Series([0.0, 0.0]),
            curve=_flat_curve(50.0),
            initial_cash=1000.0,
        )
        assert frame["daily_trade_usd"][0] == pytest.approx(500.0)
        assert frame["cash"][0] == pytest.approx(500.0)
        assert frame["daily_trade_usd"][1] == pytest.approx(250.0)
        assert frame["cash"][1] == pytest.approx(250.0)
        assert frame["cash"][1] != pytest.approx(0.0)
        assert frame["asset_units"][1] == pytest.approx(7.5)

    def test_cash_is_never_negative_and_never_hits_zero_below_100_pct_rate(self) -> None:
        _, frame = run_backtest(
            dates=_dates(5),
            price=pl.Series([100.0] * 5),
            risk=pl.Series([0.0] * 5),
            curve=_flat_curve(50.0),
            initial_cash=1000.0,
        )
        cash = frame["cash"].to_list()
        assert cash == pytest.approx([500.0, 250.0, 125.0, 62.5, 31.25])
        assert all(c > 0.0 for c in cash)


class TestRemainingHoldingsCompounding:
    def test_two_rich_days_at_50_pct_leave_quarter_holdings_not_zero(self) -> None:
        """50% of remaining holdings twice → 25% of the post-buy position.

        Day 0 buys 100% of cash (10 units @ 100). Days 1–2 sell 50% of
        whatever is still held. Applying 50% of the *original* 10 units
        twice would flatten to zero; remaining-position sizing leaves 2.5.
        """
        nodes = tuple(100.0 if i < 11 else -50.0 for i in range(21))
        _, frame = run_backtest(
            dates=_dates(3),
            price=pl.Series([100.0, 100.0, 100.0]),
            risk=pl.Series([0.0, 100.0, 100.0]),
            curve=AccumDistCurve(nodes=nodes),
            initial_cash=1000.0,
        )
        assert frame["asset_units"][0] == pytest.approx(10.0)
        assert frame["cash"][0] == pytest.approx(0.0)
        assert frame["asset_units"][1] == pytest.approx(5.0)
        assert frame["daily_trade_usd"][1] == pytest.approx(-500.0)
        assert frame["asset_units"][2] == pytest.approx(2.5)
        assert frame["asset_units"][2] != pytest.approx(0.0)
        assert frame["cash"][2] == pytest.approx(750.0)


class TestNautilusOnBarUsesRemainingBook:
    def test_on_bar_passes_shadow_cash_and_holdings_into_size_trade(self) -> None:
        pytest.importorskip("nautilus_trader")
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy

        src = inspect.getsource(SdcaStrategy.on_bar)
        assert "size_trade(rate, self._cash, self._asset_units)" in src
        assert "self.config.initial_cash" not in src
