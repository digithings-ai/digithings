"""Tests for DCA tearsheet metrics (#3171) — harness vs fill reconstruction."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.dca_metrics import (
    SdcaFill,
    breakdown_from_daily,
    daily_state_from_fills,
    fills_from_nautilus_report,
    flat_dca_mark_to_market,
)

pytestmark = pytest.mark.unit


def test_flat_dca_two_day_hand_derived() -> None:
    # 100 cash, prices 100 then 200 → spend 50/day → 0.5 + 0.25 units → 150.
    values = flat_dca_mark_to_market([100.0, 200.0], 100.0)
    assert values[0] == pytest.approx(100.0)
    assert values[1] == pytest.approx(150.0)


def test_harness_and_fill_replay_agree() -> None:
    dates = pl.date_range(date(2024, 1, 1), date(2024, 1, 5), interval="1d", eager=True)
    report, frame = run_backtest(
        dates=dates,
        price=pl.Series([100.0, 110.0, 90.0, 120.0, 130.0]),
        risk=pl.Series([0.0, 20.0, None, 80.0, 100.0], dtype=pl.Float64),
        curve=AccumDistCurve(),
        initial_cash=1000.0,
    )
    fills: list[SdcaFill] = []
    for d, trade, price in zip(
        frame["date"].to_list(),
        frame["daily_trade_usd"].to_list(),
        frame["price"].to_list(),
        strict=True,
    ):
        if trade > 0:
            fills.append(SdcaFill(date=str(d), side="buy", qty=trade / price, price=price))
        elif trade < 0:
            fills.append(SdcaFill(date=str(d), side="sell", qty=(-trade) / price, price=price))
    bars = [(str(d), float(p)) for d, p in zip(frame["date"].to_list(), frame["price"].to_list())]
    state = daily_state_from_fills(fills, bars, 1000.0)
    dca = breakdown_from_daily(
        prices=state["prices"],
        portfolio_values=state["portfolio_values"],
        daily_trade_usd=state["daily_trade_usd"],
        net_deployed=state["net_deployed"],
        asset_units=state["asset_units"],
        risk=frame["risk"].to_list(),
        rate=frame["rate"].to_list(),
        initial_cash=1000.0,
    )
    assert dca.vs_lump_pct == pytest.approx(report.vs_lump_pct)
    assert dca.vs_flat_dca_pct == pytest.approx(report.vs_flat_dca_pct)
    assert dca.avg_cost_basis == pytest.approx(report.avg_cost_basis)
    assert dca.final_cost_basis_vs_price == pytest.approx(report.final_cost_basis_vs_price)
    assert dca.capital_deployed_pct == pytest.approx(report.capital_deployed_pct)
    assert dca.units_accumulated == pytest.approx(report.units_accumulated)
    assert dca.buy_days == report.buy_days
    assert dca.sell_days == report.sell_days
    # 100×: vs_flat_dca is a true percent on this rising-then-falling book.
    assert dca.vs_flat_dca_pct != pytest.approx(dca.vs_flat_dca_pct / 100.0)


class _Empty:
    empty = True
    shape = (0, 0)


def test_empty_nautilus_fills_report_is_empty_list() -> None:
    assert fills_from_nautilus_report(_Empty()) == []
    assert fills_from_nautilus_report(None) == []
