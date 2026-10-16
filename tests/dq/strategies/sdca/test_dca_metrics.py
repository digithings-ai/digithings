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
    assert dca.allocated_pct is not None
    assert 0.0 <= dca.allocated_pct <= 100.0
    assert dca.fill_buy_days == sum(1 for u in state["daily_trade_usd"] if u > 1e-8)
    assert dca.fill_sell_days == sum(1 for u in state["daily_trade_usd"] if u < -1e-8)
    # 100×: vs_flat_dca is a true percent on this rising-then-falling book.
    assert dca.vs_flat_dca_pct != pytest.approx(dca.vs_flat_dca_pct / 100.0)


def test_daily_state_seeds_fills_before_first_bar() -> None:
    """Published trade window must carry the book, not start empty at $1000."""
    fills = [
        SdcaFill(date="2017-12-31", side="buy", qty=1.0, price=100.0),
        SdcaFill(date="2018-01-01", side="buy", qty=0.5, price=200.0),
    ]
    bars = [("2018-01-01", 200.0), ("2018-01-02", 220.0)]
    state = daily_state_from_fills(fills, bars, 1000.0)
    assert state["asset_units"][0] == pytest.approx(1.5)
    assert state["asset_units"][1] == pytest.approx(1.5)
    assert state["prices"][0] == pytest.approx(200.0)
    # $100 warmup + $100 window buy → $200 deployed, $800 cash + 1.5 * 200 MTM.
    assert state["net_deployed"][0] == pytest.approx(200.0)
    assert state["portfolio_values"][0] == pytest.approx(1100.0)
    assert state["portfolio_values"][1] == pytest.approx(1130.0)


class _Empty:
    empty = True
    shape = (0, 0)


def test_empty_nautilus_fills_report_is_empty_list() -> None:
    assert fills_from_nautilus_report(_Empty()) == []
    assert fills_from_nautilus_report(None) == []


def test_risk_band_label_matches_frontend() -> None:
    from digiquant.strategies.sdca.dca_metrics import risk_band_label

    assert risk_band_label(0.0) == "Fire sale"
    assert risk_band_label(9.9) == "Fire sale"
    assert risk_band_label(10.0) == "Accumulate"
    assert risk_band_label(25.0) == "Value"
    assert risk_band_label(50.0) == "Above mid"
    assert risk_band_label(75.0) == "Hot"
    assert risk_band_label(95.0) == "Bubble"
    assert risk_band_label(None) is None


def test_tearsheet_overlays_copy_rails_and_three_way_equity() -> None:
    from digiquant.strategies.sdca.dca_metrics import tearsheet_overlays

    overlays = tearsheet_overlays(
        dates=["2020-01-01", "2020-01-02"],
        prices=[100.0, 110.0],
        daily_trade_usd=[50.0, 0.0],
        net_deployed=[50.0, 50.0],
        initial_cash=100.0,
        rails=[(90.0, 100.0, 120.0), (91.0, 101.0, 121.0)],
        risk=[20.0, 22.0],
    )
    assert overlays["rails"][0] == {
        "t": "2020-01-01",
        "low": 90.0,
        "median": 100.0,
        "high": 120.0,
    }
    assert overlays["risk_curve"][1]["v"] == 22.0
    assert overlays["cost_basis_curve"][0]["v"] == pytest.approx(100.0)
    assert overlays["capital_deployed_curve"][0]["v"] == pytest.approx(50.0)
    assert len(overlays["lump_equity_curve"]) == 2
    assert len(overlays["flat_dca_equity_curve"]) == 2


def test_dca_current_signal_is_risk_band_rate_not_mr_long() -> None:
    from digiquant.strategies.sdca.dca_metrics import dca_current_signal

    sig = dca_current_signal(
        last_date="2020-01-02",
        last_price=110.0,
        last_risk=12.0,
        last_rate=4.0,
        units_accumulated=0.5,
    )
    assert sig["band"] == "Accumulate"
    assert sig["daily_rate_pct"] == 4.0
    assert sig["risk"] == 12.0
    assert sig["entry_label"] == "Accumulate"
    assert sig["position"] in {"long", "flat"}
