"""SDCA diagnostic chart series: allocation %, fill markers, power-law labels."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from digiquant.charts.sdca import render_sdca_diagnostic_charts
from digiquant.strategies.sdca.chart_series import (
    allocated_pct,
    allocated_pct_series,
    catalog_indicator_curves,
    chart_inputs_from_payload,
    fill_markers_from_daily,
    indicator_curve_from_z,
    knees_from_preset,
    reconstruct_allocated_pct,
    reconstruct_fill_markers,
)
from digiquant.strategies.sdca.composite_risk import z_to_risk
from digiquant.strategies.sdca.dca_metrics import (
    SdcaFill,
    daily_state_from_fills,
    tearsheet_overlays,
)
from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    indicator_display_name,
)
from digiquant.tearsheet_data import TearsheetDcaBreakdown, from_nautilus_run, from_pine

pytestmark = pytest.mark.unit


def test_indicator_display_name_renames_valuation_to_power_law() -> None:
    assert indicator_display_name("valuation") == "power law"
    assert indicator_display_name("m2") == "M2 liquidity"


def test_allocated_pct_is_mark_to_market_not_capital_deployed() -> None:
    # 500 cash, 0.5 BTC @ 1000 → 50% allocated.
    assert allocated_pct(500.0, 0.5, 1000.0) == pytest.approx(50.0)
    # After sells, cash can exceed initial stake; deployed = initial - cash < 0.
    cash, units, price = 6046.0, 0.989, 79000.0
    initial = 1000.0
    port = cash + units * price
    allocated = allocated_pct(cash, units, price)
    deployed_pct = (initial - cash) / initial * 100.0
    assert deployed_pct < 0
    assert 0.0 < allocated < 100.0
    assert allocated == pytest.approx(100.0 * (units * price) / port)
    assert allocated != pytest.approx(deployed_pct)


def test_allocated_pct_series_tracks_buys() -> None:
    pct = allocated_pct_series(
        cash=[1000.0, 500.0],
        units=[0.0, 5.0],
        prices=[100.0, 100.0],
    )
    assert pct[0] == pytest.approx(0.0)
    assert pct[1] == pytest.approx(50.0)


def test_fill_markers_use_daily_trade_usd_not_curve_rate_sign() -> None:
    # Curve would have called this a buy day (rate > 0); the fill is a sell.
    markers = fill_markers_from_daily(
        dates=["2025-01-20", "2025-01-21"],
        daily_trade_usd=[-525.0, 0.0],
        portfolio_values=[80000.0, 81000.0],
        prices=[102145.0, 103000.0],
    )
    assert len(markers) == 1
    assert markers[0].side == "sell"
    assert markers[0].t == "2025-01-20"
    assert markers[0].book_frac == pytest.approx(525.0 / 80000.0)
    assert markers[0].trade_usd == pytest.approx(-525.0)


def test_indicator_curve_maps_z_to_risk_and_labels_power_law() -> None:
    # z = +3 → risk 0 (cheap); z = -3 → risk 100 (rich).
    curve = indicator_curve_from_z(
        name="valuation",
        dates=["2020-01-01", "2020-01-02"],
        z_values=[3.0, -3.0],
        weight=1.0,
    )
    assert curve.display_name == "power law"
    assert curve.in_index is True
    assert curve.points[0]["v"] == pytest.approx(0.0)
    assert curve.points[1]["v"] == pytest.approx(100.0)
    assert z_to_risk(0.0) == pytest.approx(50.0)


def test_catalog_keeps_zero_weight_extras_out_of_index() -> None:
    weights = SdcaCompositeWeights(valuation=1.0)
    curves = catalog_indicator_curves(
        dates=["2020-01-01"],
        z_by_name={"valuation": [0.0]},
        weights=weights,
    )
    by_name = {c.name: c for c in curves}
    assert by_name["valuation"].in_index is True
    assert by_name["valuation"].display_name == "power law"
    assert by_name["m2"].in_index is False
    assert by_name["m2"].weight == pytest.approx(0.0)
    assert by_name["m2"].points == []


def test_btc_optimized_knees_are_25_and_70() -> None:
    knees = knees_from_preset("btc_optimized")
    assert knees.buy_knee_risk == pytest.approx(25.0)
    assert knees.sell_knee_risk == pytest.approx(70.0)


def test_tearsheet_overlays_emit_allocated_and_fill_markers() -> None:
    overlays = tearsheet_overlays(
        dates=["2020-01-01", "2020-01-02"],
        prices=[100.0, 110.0],
        daily_trade_usd=[50.0, -20.0],
        net_deployed=[50.0, 30.0],
        initial_cash=100.0,
        rails=[(90.0, 100.0, 120.0), (91.0, 101.0, 121.0)],
        risk=[20.0, 80.0],
        asset_units=[0.5, 0.5 - 20.0 / 110.0],
        weights=SdcaCompositeWeights(valuation=1.0),
        preset_name="btc_optimized",
        indicator_z={"valuation": [1.0, -1.0]},
    )
    alloc = overlays["allocated_pct_curve"]
    assert alloc[0]["v"] == pytest.approx(50.0)  # 0.5 * 100 / (50 + 50)
    # capital_deployed stays the trap metric; allocation must differ after a sell
    # that returns cash (net_deployed 30 on 100 initial = 30%, not 50%).
    assert overlays["capital_deployed_curve"][1]["v"] == pytest.approx(30.0)
    markers = overlays["fill_markers"]
    assert markers[0]["side"] == "buy"
    assert markers[1]["side"] == "sell"
    power = next(c for c in overlays["indicator_curves"] if c["name"] == "valuation")
    assert power["display_name"] == "power law"
    assert overlays["curve_knees"]["buy_knee_risk"] == pytest.approx(25.0)


def test_reconstruct_allocated_from_negative_capital_deployed() -> None:
    # Ending 6046 cash on 1000 initial → deployed -504.6%; equity 84232.
    allocated = reconstruct_allocated_pct(
        equity=[84232.0],
        capital_deployed_pct=[-504.63549],
        initial_cash=1000.0,
    )
    cash = 1000.0 * (1.0 - (-504.63549) / 100.0)
    assert cash == pytest.approx(6046.3549)
    assert allocated[0] == pytest.approx(100.0 * (84232.0 - cash) / 84232.0)
    assert 0.0 < allocated[0] < 100.0


def test_fill_replay_matches_overlay_markers() -> None:
    fills = [
        SdcaFill(date="2025-01-20", side="sell", qty=0.00514, price=102145.0),
        SdcaFill(date="2025-01-21", side="buy", qty=0.01, price=100000.0),
    ]
    bars = [("2025-01-20", 102145.0), ("2025-01-21", 100000.0)]
    # Warmup: already holding 1 BTC bought at 10k (seed cash 1000 would bounce;
    # start with a fill before the window).
    fills = [
        SdcaFill(date="2025-01-19", side="buy", qty=1.0, price=900.0),
        *fills,
    ]
    state = daily_state_from_fills(fills, bars, 1000.0)
    markers = fill_markers_from_daily(
        dates=["2025-01-20", "2025-01-21"],
        daily_trade_usd=state["daily_trade_usd"],
        portfolio_values=state["portfolio_values"],
        prices=state["prices"],
    )
    assert markers[0].side == "sell"
    assert markers[1].side == "buy"


def test_chart_inputs_from_2025_style_payload_reconstructs_sells() -> None:
    payload = {
        "strategy": "btc_sdca",
        "symbol": "BTC-USD",
        "initial_capital": 1000.0,
        "period_start": "2025-01-19",
        "period_end": "2025-01-21",
        "notes": ["Coefficients 2015-07-20 → 2026-08-29. Preset btc_optimized."],
        "equity_curve": [
            {"t": "2025-01-19", "v": 1100.0},
            {"t": "2025-01-20", "v": 1050.0},
            {"t": "2025-01-21", "v": 1080.0},
        ],
        "capital_deployed_curve": [
            {"t": "2025-01-19", "v": 90.0},
            {"t": "2025-01-20", "v": -50.0},
            {"t": "2025-01-21", "v": -20.0},
        ],
        "ohlc_bars": [
            {"t": "2025-01-19", "o": 100.0, "h": 100.0, "l": 100.0, "c": 100.0},
            {"t": "2025-01-20", "o": 110.0, "h": 110.0, "l": 110.0, "c": 110.0},
            {"t": "2025-01-21", "o": 105.0, "h": 105.0, "l": 105.0, "c": 105.0},
        ],
        "rails": [
            {"t": "2025-01-19", "low": 50.0, "median": 100.0, "high": 200.0},
            {"t": "2025-01-20", "low": 50.0, "median": 100.0, "high": 200.0},
            {"t": "2025-01-21", "low": 50.0, "median": 100.0, "high": 200.0},
        ],
        "risk_curve": [
            {"t": "2025-01-19", "v": 20.0},
            {"t": "2025-01-20", "v": 75.0},
            {"t": "2025-01-21", "v": 40.0},
        ],
        "lump_equity_curve": [
            {"t": "2025-01-19", "v": 1000.0},
            {"t": "2025-01-20", "v": 1100.0},
            {"t": "2025-01-21", "v": 1050.0},
        ],
    }
    bundle = chart_inputs_from_payload(payload)
    assert "cash_pct" not in bundle
    assert bundle["knees"].buy_knee_risk == pytest.approx(25.0)
    assert bundle["knees"].sell_knee_risk == pytest.approx(70.0)
    power = next(c for c in bundle["indicators"] if c.name == "valuation")
    assert power.display_name == "power law"
    assert power.in_index is True
    # Negative deployed on 2025-01-20 is a sell (cash rose).
    sells = [m for m in bundle["fill_markers"] if m.side == "sell"]
    assert sells
    assert sells[0].t == "2025-01-20"
    for pct in bundle["allocated_pct"]:
        assert 0.0 <= pct <= 100.0


def test_reconstruct_fill_markers_delta_units() -> None:
    markers = reconstruct_fill_markers(
        dates=["2020-01-01", "2020-01-02"],
        equity=[1000.0, 1100.0],
        capital_deployed_pct=[0.0, 50.0],
        prices=[100.0, 100.0],
        initial_cash=1000.0,
    )
    # Day 0: no prior units. Day 1: cash 500, equity 1100 → units 6, buy.
    buys = [m for m in markers if m.side == "buy"]
    assert buys


def test_from_nautilus_run_roundtrips_new_overlay_keys() -> None:

    dca = TearsheetDcaBreakdown(
        vs_lump_pct=1.0,
        vs_flat_dca_pct=2.0,
        avg_cost_basis=50.0,
        final_cost_basis_vs_price=50.0,
        capital_deployed_pct=-10.0,
        capital_deployed_peak_pct=90.0,
        units_accumulated=1.0,
    )
    ts = from_nautilus_run(
        {
            "strategy": "btc_sdca",
            "symbol": "BTC-USD",
            "period": "2020-01-01 → 2020-01-02",
            "bars": 2,
            "initial_capital": 1000.0,
            "final_equity": 1100.0,
            "net_profit_pct": 10.0,
            "max_drawdown_pct": -1.0,
            "all": {},
        },
        [],
        equity_curve=[("2020-01-01", 1000.0), ("2020-01-02", 1100.0)],
        dca=dca,
        allocated_pct_curve=[("2020-01-01", 0.0), ("2020-01-02", 40.0)],
        fill_markers=[
            {
                "t": "2020-01-02",
                "side": "buy",
                "book_frac": 0.1,
                "price": 100.0,
                "trade_usd": 110.0,
            }
        ],
        indicator_curves=[
            {
                "name": "valuation",
                "display_name": "power law",
                "weight": 1.0,
                "in_index": True,
                "points": [{"t": "2020-01-01", "v": 50.0}],
            }
        ],
        indicator_weights={"valuation": 1.0, "m2": 0.0},
        curve_knees={"buy_knee_risk": 25.0, "sell_knee_risk": 70.0, "preset": "btc_optimized"},
        beats_flat_dca_oos=False,
    )
    dumped = json.loads(ts.to_json())
    assert dumped["allocated_pct_curve"][1]["v"] == pytest.approx(40.0)
    assert dumped["fill_markers"][0]["side"] == "buy"
    assert dumped["indicator_curves"][0]["display_name"] == "power law"
    assert dumped["curve_knees"]["buy_knee_risk"] == pytest.approx(25.0)
    assert dumped["beats_flat_dca_oos"] is False
    # Slapper identity: a dump without these kwargs still omits them.
    slapper = json.loads(
        from_pine(
            {
                "strategy": "btc_slapper",
                "symbol": "BTC-USD",
                "period": "2020-01-01 → 2020-01-02",
                "bars": 2,
                "initial_capital": 1000.0,
                "final_equity": 1100.0,
                "net_profit_pct": 10.0,
                "max_drawdown_pct": -1.0,
                "all": {
                    "trades": 1,
                    "net_profit": 100.0,
                    "net_profit_pct": 10.0,
                    "percent_profitable": 100.0,
                    "avg_trade": 100.0,
                    "wins": 1,
                    "losses": 0,
                },
            },
            [],
            equity_curve=[],
        ).to_json()
    )
    assert "allocated_pct_curve" not in slapper
    assert "fill_markers" not in slapper
    assert "beats_flat_dca_oos" not in slapper


@pytest.mark.skipif(
    importlib.util.find_spec("matplotlib") is None,
    reason="matplotlib not installed",
)
def test_render_sdca_charts_writes_four_pngs(tmp_path: Path) -> None:

    payload = {
        "strategy": "btc_sdca",
        "symbol": "BTC-USD",
        "initial_capital": 1000.0,
        "period_start": "2025-01-19",
        "period_end": "2025-01-21",
        "notes": ["Preset btc_optimized."],
        "equity_curve": [
            {"t": "2025-01-19", "v": 1100.0},
            {"t": "2025-01-20", "v": 2000.0},
            {"t": "2025-01-21", "v": 1800.0},
        ],
        "capital_deployed_curve": [
            {"t": "2025-01-19", "v": 50.0},
            {"t": "2025-01-20", "v": 90.0},
            {"t": "2025-01-21", "v": -20.0},
        ],
        "ohlc_bars": [
            {"t": "2025-01-19", "o": 100.0, "h": 100.0, "l": 100.0, "c": 100.0},
            {"t": "2025-01-20", "o": 120.0, "h": 120.0, "l": 120.0, "c": 120.0},
            {"t": "2025-01-21", "o": 110.0, "h": 110.0, "l": 110.0, "c": 110.0},
        ],
        "rails": [
            {"t": "2025-01-19", "low": 50.0, "median": 100.0, "high": 200.0},
            {"t": "2025-01-20", "low": 50.0, "median": 100.0, "high": 200.0},
            {"t": "2025-01-21", "low": 50.0, "median": 100.0, "high": 200.0},
        ],
        "risk_curve": [
            {"t": "2025-01-19", "v": 20.0},
            {"t": "2025-01-20", "v": 75.0},
            {"t": "2025-01-21", "v": 40.0},
        ],
        "lump_equity_curve": [
            {"t": "2025-01-19", "v": 1000.0},
            {"t": "2025-01-20", "v": 1200.0},
            {"t": "2025-01-21", "v": 1100.0},
        ],
    }
    paths = render_sdca_diagnostic_charts(payload, tmp_path, prefix="test")
    assert len(paths) == 4
    names = {p.name for p in paths}
    assert "test_power_law_risk.png" in names
    for path in paths:
        assert path.exists()
        assert path.stat().st_size > 8_000
    zoomed = render_sdca_diagnostic_charts(
        payload, tmp_path / "zoom", prefix="zoom", date_start="2025-01-20", date_end="2025-01-21"
    )
    assert len(zoomed) == 4
    for path in zoomed:
        assert path.exists()
