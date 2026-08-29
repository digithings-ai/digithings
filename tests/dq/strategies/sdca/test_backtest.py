"""Tests for the SDCA daily backtest loop vs. a lump-sum buy-&-hold benchmark."""

from __future__ import annotations

import polars as pl
import pytest
from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import AccumDistCurve

pytestmark = pytest.mark.unit

EXPORT_COLUMNS = {
    "date",
    "price",
    "risk",
    "rate",
    "daily_trade_usd",
    "cash",
    "asset_units",
    "net_deployed",
    "portfolio_value",
    "buy_hold_value",
}


def _dates(n: int) -> pl.Series:
    return pl.date_range(pl.date(2024, 1, 1), pl.date(2024, 1, n), interval="1d", eager=True)


class TestRunBacktestSingleDay:
    def test_no_trade_when_risk_is_null(self) -> None:
        report, frame = run_backtest(
            dates=_dates(1),
            price=pl.Series([100.0]),
            risk=pl.Series([None], dtype=pl.Float64),
            curve=AccumDistCurve(),
            initial_cash=1000.0,
        )
        assert report.no_trade_days == 1
        assert report.buy_days == 0
        assert report.sell_days == 0
        assert frame["cash"][0] == pytest.approx(1000.0)
        assert frame["asset_units"][0] == pytest.approx(0.0)

    def test_buy_day_deploys_cash_at_curve_rate(self) -> None:
        # default curve: risk=0 -> rate=10%/day
        report, frame = run_backtest(
            dates=_dates(1),
            price=pl.Series([100.0]),
            risk=pl.Series([0.0]),
            curve=AccumDistCurve(),
            initial_cash=1000.0,
        )
        assert frame["daily_trade_usd"][0] == pytest.approx(100.0)
        assert frame["cash"][0] == pytest.approx(900.0)
        assert frame["asset_units"][0] == pytest.approx(1.0)
        assert frame["net_deployed"][0] == pytest.approx(100.0)
        assert report.buy_days == 1

    def test_buy_clamped_to_available_cash(self) -> None:
        overbuy_curve = AccumDistCurve(nodes=tuple(200.0 for _ in range(21)))
        report, frame = run_backtest(
            dates=_dates(1),
            price=pl.Series([100.0]),
            risk=pl.Series([0.0]),
            curve=overbuy_curve,
            initial_cash=1000.0,
        )
        assert frame["cash"][0] == pytest.approx(0.0)
        assert frame["asset_units"][0] == pytest.approx(10.0)


class TestRunBacktestMultiDay:
    def test_sell_day_reduces_holdings_at_curve_rate(self) -> None:
        # day 1: risk=0 -> buy 10% of cash. day 2: risk=100 -> sell 10% of btc.
        report, frame = run_backtest(
            dates=_dates(2),
            price=pl.Series([100.0, 100.0]),
            risk=pl.Series([0.0, 100.0]),
            curve=AccumDistCurve(),
            initial_cash=1000.0,
        )
        # after day1: cash=900, btc=1.0. day2 rate=-10% -> sell 0.1 btc @100 = $10
        assert frame["daily_trade_usd"][1] == pytest.approx(-10.0)
        assert frame["asset_units"][1] == pytest.approx(0.9)
        assert frame["cash"][1] == pytest.approx(910.0)
        assert report.sell_days == 1

    def test_sell_clamped_to_available_holdings(self) -> None:
        oversell_curve = AccumDistCurve(nodes=tuple(-200.0 for _ in range(21)))
        report, frame = run_backtest(
            dates=_dates(2),
            price=pl.Series([100.0, 100.0]),
            risk=pl.Series([0.0, 100.0]),
            curve=oversell_curve,
            initial_cash=1000.0,
        )
        # day1 buys nothing (rate<0 with 0 btc held -> clamp to 0)
        assert frame["asset_units"][0] == pytest.approx(0.0)
        assert frame["cash"][1] == pytest.approx(1000.0)

    def test_buy_hold_value_is_lump_sum_at_day0_price(self) -> None:
        report, frame = run_backtest(
            dates=_dates(2),
            price=pl.Series([100.0, 150.0]),
            risk=pl.Series([None, None], dtype=pl.Float64),
            curve=AccumDistCurve(),
            initial_cash=1000.0,
        )
        # 10 btc bought at 100 on day0, marked at 150 on day1
        assert frame["buy_hold_value"][0] == pytest.approx(1000.0)
        assert frame["buy_hold_value"][1] == pytest.approx(1500.0)

    def test_portfolio_value_is_cash_plus_holdings_marked_to_market(self) -> None:
        report, frame = run_backtest(
            dates=_dates(2),
            price=pl.Series([100.0, 200.0]),
            risk=pl.Series([0.0, None], dtype=pl.Float64),
            curve=AccumDistCurve(),
            initial_cash=1000.0,
        )
        # day0: cash=900, btc=1.0 -> value=1000. day1: no trade, price doubles -> value=900+200=1100
        assert frame["portfolio_value"][1] == pytest.approx(1100.0)

    def test_max_drawdown_reflects_peak_to_trough_decline(self) -> None:
        # never trade (all null risk); price rises then falls 20% from peak
        report, frame = run_backtest(
            dates=_dates(3),
            price=pl.Series([100.0, 200.0, 160.0]),
            risk=pl.Series([None, None, None], dtype=pl.Float64),
            curve=AccumDistCurve(),
            initial_cash=1000.0,
        )
        assert report.buy_hold_max_drawdown_pct == pytest.approx(-0.20)

    def test_report_pnl_and_return_pct(self) -> None:
        report, frame = run_backtest(
            dates=_dates(2),
            price=pl.Series([100.0, 200.0]),
            risk=pl.Series([0.0, None], dtype=pl.Float64),
            curve=AccumDistCurve(),
            initial_cash=1000.0,
        )
        assert report.total_pnl == pytest.approx(100.0)
        assert report.total_return_pct == pytest.approx(10.0)

    def test_avg_risk_and_avg_rate_ignore_null_days(self) -> None:
        report, frame = run_backtest(
            dates=_dates(3),
            price=pl.Series([100.0, 100.0, 100.0]),
            risk=pl.Series([0.0, None, 100.0], dtype=pl.Float64),
            curve=AccumDistCurve(),
            initial_cash=1000.0,
        )
        assert report.avg_risk == pytest.approx(50.0)
        assert report.avg_rate == pytest.approx(0.0)
        assert report.no_trade_days == 1

    def test_export_frame_matches_documented_columns(self) -> None:
        _, frame = run_backtest(
            dates=_dates(1),
            price=pl.Series([100.0]),
            risk=pl.Series([0.0]),
            curve=AccumDistCurve(),
            initial_cash=1000.0,
        )
        assert set(frame.columns) == EXPORT_COLUMNS


class TestRunBacktestInputValidation:
    def test_empty_series_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one row"):
            run_backtest(
                dates=pl.Series([], dtype=pl.Date),
                price=pl.Series([], dtype=pl.Float64),
                risk=pl.Series([], dtype=pl.Float64),
                curve=AccumDistCurve(),
                initial_cash=1000.0,
            )

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            run_backtest(
                dates=_dates(2),
                price=pl.Series([100.0, 100.0]),
                risk=pl.Series([0.0]),
                curve=AccumDistCurve(),
                initial_cash=1000.0,
            )

    def test_non_positive_price_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            run_backtest(
                dates=_dates(1),
                price=pl.Series([0.0]),
                risk=pl.Series([0.0]),
                curve=AccumDistCurve(),
                initial_cash=1000.0,
            )

    def test_non_finite_price_raises(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            run_backtest(
                dates=_dates(1),
                price=pl.Series([float("inf")]),
                risk=pl.Series([0.0]),
                curve=AccumDistCurve(),
                initial_cash=1000.0,
            )

    def test_null_price_raises(self) -> None:
        with pytest.raises(ValueError, match="null"):
            run_backtest(
                dates=_dates(1),
                price=pl.Series([None], dtype=pl.Float64),
                risk=pl.Series([0.0]),
                curve=AccumDistCurve(),
                initial_cash=1000.0,
            )

    def test_non_positive_initial_cash_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            run_backtest(
                dates=_dates(1),
                price=pl.Series([100.0]),
                risk=pl.Series([0.0]),
                curve=AccumDistCurve(),
                initial_cash=0.0,
            )

    def test_non_finite_initial_cash_raises(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            run_backtest(
                dates=_dates(1),
                price=pl.Series([100.0]),
                risk=pl.Series([0.0]),
                curve=AccumDistCurve(),
                initial_cash=float("nan"),
            )

    def test_reversed_dates_raises(self) -> None:
        reversed_dates = pl.Series(list(reversed(_dates(2).to_list())))
        with pytest.raises(ValueError, match="strictly increasing"):
            run_backtest(
                dates=reversed_dates,
                price=pl.Series([100.0, 100.0]),
                risk=pl.Series([0.0, 0.0]),
                curve=AccumDistCurve(),
                initial_cash=1000.0,
            )

    def test_duplicate_dates_raises(self) -> None:
        one_date = _dates(1)[0]
        duplicate_dates = pl.Series([one_date, one_date])
        with pytest.raises(ValueError, match="strictly increasing"):
            run_backtest(
                dates=duplicate_dates,
                price=pl.Series([100.0, 100.0]),
                risk=pl.Series([0.0, 0.0]),
                curve=AccumDistCurve(),
                initial_cash=1000.0,
            )

    def test_null_date_raises(self) -> None:
        with pytest.raises(ValueError, match="null"):
            run_backtest(
                dates=pl.Series([None], dtype=pl.Date),
                price=pl.Series([100.0]),
                risk=pl.Series([0.0]),
                curve=AccumDistCurve(),
                initial_cash=1000.0,
            )
