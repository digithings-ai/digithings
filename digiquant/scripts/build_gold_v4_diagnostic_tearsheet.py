#!/usr/bin/env python3
"""Diagnostic tearsheet for the gold SDCA v4 no-trend candidate (#4804).

Rolling-z anchor (window 90 / z 1.0, no time trend) + m2/uup 0.5 +
oscillators 0.25, with the v4 gated shape. Gate record
(`.scratch/gold_curve_search_v4.json`, NOT recomputed here): causal
rolling evaluation, mean OOS +10.99%, beats_flat_dca_oos=True, 3/3 folds
feasible; sensitivity UNSTABLE (2.61 vs 2.0); holdout absent. This record
SUPERSEDES the void -6.49% non-result (IS-sliced eval starved the trailing
window: 0% deployed, null OOS rails).

Overlap disclosure: sma_band (price vs trailing SMA) and the rolling_z rails
anchor (price vs 90d trailing mean) vote the same mean-reversion family; the
anchor carries 1.0, sma_band 0.25. The gate prices the overlap, this script
only renders it.

Research-only: slug `gold_sdca_v4`, never pushed to Supabase, never touches
settings.json or any validated-candidate section.

Usage:
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/build_gold_v4_diagnostic_tearsheet.py
"""

from __future__ import annotations

import json
from datetime import date as date_cls
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.chart_series import SdcaCurveKnees
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.dca_metrics import (
    breakdown_from_daily,
    dca_current_signal,
    tearsheet_overlays,
)
from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    extra_indicators_for_window,
    extra_z_vectors,
)
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.providers import resolve_sdca_risk_model
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.walk_forward import shape_from_params
from digiquant.tearsheet_data import from_nautilus_run

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
SEARCH_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_curve_search_v4.json"
WEB_PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

SLUG = "gold_sdca_v4"
# Display constants only -- nothing published is touched by this script.
INITIAL_CASH = 1000.0
TRADE_START = date_cls(2010, 1, 1)

# 90d matches the oscillator horizon family (same literals as the v4 seed/gate).
ROLLING_WINDOW = 90
ROLLING_Z = 1.0

_EMPTY_DIR_METRICS = {
    "trades": 0,
    "net_profit": 0.0,
    "net_profit_pct": 0.0,
    "gross_profit": 0.0,
    "gross_loss": 0.0,
    "percent_profitable": 0.0,
    "profit_factor": None,
    "avg_trade": 0.0,
    "wins": 0,
    "losses": 0,
}


def main() -> None:
    search = json.loads(SEARCH_PATH.read_text())
    weights = SdcaCompositeWeights(**search["weights"])
    shape = shape_from_params(search["gated_shape"])
    assert shape.buy_mid_knee_risk is None and shape.sell_mid_knee_risk is None, (
        "gold v4 winner is single-knee; mid-tier keys must stay unset"
    )
    gate = search["gate"]
    label = "GLD-SDCA (v4 no-trend candidate diagnostic)"
    print(f"Gold v4 shape: {shape}")
    print(f"Gold v4 weights: {weights.model_dump()}")
    print(
        f"Gate mean_oos={gate['mean_oos_vs_flat_dca_pct']:+.2f}%  "
        f"beats_flat_dca_oos={gate['beats_flat_dca_oos']}  "
        f"sensitivity_stable={gate['sensitivity_stable']} "
        f"(max_abs_delta={gate['sensitivity_max_abs_delta']:.2f})"
    )

    # Full-calendar rolling rails (causal trailing op, same as the v4 seed:
    # each output uses only inputs <= t -- NOT an OOS fit).
    dates, prices = load_sdca_ohlcv(symbols=["GLD-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    risk_model = resolve_sdca_risk_model(
        "rolling_z",
        dates=date_s,
        price=price_s,
        rolling_window=ROLLING_WINDOW,
        rolling_z=ROLLING_Z,
    )
    sources = load_sdca_extra_sources(DEFAULT_DATA_PATH.parent)
    extra_z = extra_z_vectors(date_s, price_s, weights, sources)
    extras = extra_indicators_for_window(date_s.to_list(), date_s.to_list(), extra_z, weights)
    index = build_risk_index(
        date_s,
        price_s,
        risk_model,
        extras,
        valuation_weight=weights.valuation,
    )
    risk_list = index["risk"].to_list()

    idx = [i for i, d in enumerate(dates) if d >= TRADE_START]
    if not idx:
        raise ValueError(f"No bars on/after trade_start={TRADE_START}")
    date_w = date_s[idx]
    price_w = price_s[idx]
    risk_w = pl.Series("risk", [risk_list[i] for i in idx], dtype=pl.Float64)
    valuation_z_w = index["valuation_z"].to_list()
    valuation_z_w = [valuation_z_w[i] for i in idx]

    curve = AccumDistCurve(shape.to_nodes())
    _report, frame = run_backtest(date_w, price_w, risk_w, curve, INITIAL_CASH)

    date_strs = [str(d) for d in frame["date"].to_list()]
    price_vals = frame["price"].to_list()
    risk_vals = frame["risk"].to_list()
    rate_vals = frame["rate"].to_list()
    daily_trade_usd_vals = frame["daily_trade_usd"].to_list()
    net_deployed_vals = frame["net_deployed"].to_list()
    asset_units_vals = frame["asset_units"].to_list()
    portfolio_values = frame["portfolio_value"].to_list()

    dca_block = breakdown_from_daily(
        prices=price_vals,
        portfolio_values=portfolio_values,
        daily_trade_usd=daily_trade_usd_vals,
        net_deployed=net_deployed_vals,
        asset_units=asset_units_vals,
        risk=risk_vals,
        rate=rate_vals,
        initial_cash=INITIAL_CASH,
    )

    rails = risk_model.rails(date_s)
    low_w = [rails["low"][i] for i in idx]
    median_w = [rails["median"][i] for i in idx]
    high_w = [rails["high"][i] for i in idx]
    rail_tuples = list(zip(low_w, median_w, high_w, strict=True))
    indicator_z: dict[str, list] = {"valuation": valuation_z_w}
    for name in weights.enabled_extras():
        series = extra_z.get(name)
        if series is not None:
            indicator_z[name] = [series[i] for i in idx]

    overlays = tearsheet_overlays(
        dates=date_strs,
        prices=price_vals,
        daily_trade_usd=daily_trade_usd_vals,
        net_deployed=net_deployed_vals,
        initial_cash=INITIAL_CASH,
        rails=rail_tuples,
        risk=risk_vals,
        asset_units=asset_units_vals,
        indicator_z=indicator_z,
        weights=weights.model_dump(),
    )
    overlays["curve_knees"] = SdcaCurveKnees(
        buy_knee_risk=shape.buy_knee_risk,
        sell_knee_risk=shape.sell_knee_risk,
        preset="gold v4 no-trend candidate (single-knee)",
    ).model_dump(mode="json")

    signal = dca_current_signal(
        last_date=date_strs[-1],
        last_price=price_vals[-1],
        last_risk=risk_vals[-1],
        last_rate=rate_vals[-1],
        units_accumulated=dca_block.units_accumulated,
    )

    equity_curve = list(zip(date_strs, portfolio_values, strict=True))
    final_equity = portfolio_values[-1]
    net_profit_pct = (final_equity / INITIAL_CASH - 1.0) * 100.0
    peak, max_dd = INITIAL_CASH, 0.0
    for eq in portfolio_values:
        peak = max(peak, eq)
        if peak > 0:
            max_dd = min(max_dd, (eq - peak) / peak * 100.0)

    summary = {
        "strategy": SLUG,
        "symbol": "GLD-USD",
        "period": f"{date_strs[0]} → {date_strs[-1]}",
        "bars": len(date_strs),
        "initial_capital": INITIAL_CASH,
        "final_equity": final_equity,
        "net_profit_pct": net_profit_pct,
        "max_drawdown_pct": max_dd,
        "all": dict(_EMPTY_DIR_METRICS),
        "long": dict(_EMPTY_DIR_METRICS),
        "short": dict(_EMPTY_DIR_METRICS),
    }

    fold_str = "; ".join(
        f"fold {f['fold']}: oos_vs_flat={f['oos_vs_flat_dca_pct']:+.2f}% "
        f"max_dd={f['max_drawdown_pct']:.2f}% feasible={f['feasible']}"
        for f in gate["per_fold"]
    )
    notes = [
        "DIAGNOSTIC ONLY -- gold SDCA v4 no-trend candidate, rendered for "
        "visual inspection (fills, allocation, knees). Rolling-z anchor "
        "(window 90d / z 1.0, no time trend) + m2/uup 0.5 + weekly RSI / "
        "weekly log-MACD / SMA band 0.25, v4 gated shape "
        f"(buy {shape.buy_max_rate:.0f}/{shape.buy_knee_risk:.0f}, sell "
        f"{shape.sell_knee_risk:.0f}/{shape.sell_max_rate:.0f}). Not "
        "published anywhere; settings.json never modified.",
        "Gate record (`.scratch/gold_curve_search_v4.json`, causal rolling "
        "evaluation, NOT recomputed here): "
        f"mean OOS={gate['mean_oos_vs_flat_dca_pct']:+.2f}%, "
        f"beats_flat_dca_oos={gate['beats_flat_dca_oos']}; {fold_str}; "
        "sensitivity UNSTABLE "
        f"(max_abs_delta={gate['sensitivity_max_abs_delta']:.2f} vs 2.0, "
        f"worst {gate['sensitivity_worst_neighbor_key']}); holdout absent. "
        "This record SUPERSEDES the void -6.49% non-result (0% deployed, "
        "null OOS rails -- the vote never traded). v4 is a measurement, "
        "not a promotion claim.",
        "Overlap disclosure: sma_band and the rolling anchor vote the same "
        "mean-reversion family (anchor 1.0, sma_band 0.25); the gate prices "
        "the overlap against v3 (no oscillators).",
        "The equity curve in this artifact is a FULL-HISTORY curve-simulator "
        "backtest (src/digiquant/strategies/sdca/backtest.py, a CI-only "
        "parity harness) -- not a NautilusTrader BacktestResult and not the "
        "OOS gate. Trade window from "
        f"{TRADE_START}, initial cash ${INITIAL_CASH:,.0f} (display constants "
        "only).",
        "Remaining-book SDCA (buy % of remaining cash / sell % of remaining "
        "holdings), marked to market. Research candidate only.",
    ]

    td = from_nautilus_run(
        summary,
        [],
        equity_curve,
        data_source="GLD daily OHLCV (yfinance) -- curve-simulator diagnostic, not published",
        notes=notes,
        dca=dca_block,
        current_signal=signal,
        rails=overlays.get("rails"),
        risk_curve=overlays.get("risk_curve"),
        cost_basis_curve=overlays.get("cost_basis_curve"),
        capital_deployed_curve=overlays.get("capital_deployed_curve"),
        lump_equity_curve=overlays.get("lump_equity_curve"),
        flat_dca_equity_curve=overlays.get("flat_dca_equity_curve"),
        allocated_pct_curve=overlays.get("allocated_pct_curve"),
        fill_markers=overlays.get("fill_markers"),
        indicator_curves=overlays.get("indicator_curves"),
        indicator_weights=overlays.get("indicator_weights"),
        curve_knees=overlays.get("curve_knees"),
        label=label,
        kind="dca",
        beats_flat_dca_oos=bool(gate["mean_oos_vs_flat_dca_pct"] > 0),
    )

    WEB_PUBLIC_STRATEGIES.mkdir(parents=True, exist_ok=True)
    out_path = WEB_PUBLIC_STRATEGIES / f"{SLUG}.json"
    out_path.write_text(td.to_json())
    print(
        f"wrote {out_path}  net_profit_pct={td.net_profit_pct:.1f}%  "
        f"max_drawdown_pct={td.max_drawdown_pct:.1f}%  bars={len(equity_curve)}"
    )
    print("\nDiagnostic only -- never pushed to Supabase, never touches settings.json.")


if __name__ == "__main__":
    main()
