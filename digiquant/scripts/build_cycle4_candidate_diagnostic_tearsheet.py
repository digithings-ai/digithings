#!/usr/bin/env python3
"""Diagnostic tearsheet for the periodic-loop cycle-4/6 curve candidate.

Shape buy 35/45, sell 50/30, curvatures 1.5/2.5, mid-knees buy 15 / sell 85
on the live 5-weight config (power_law=1.0, m2=0.5, dxy=0.5, weekly_rsi=0.25,
weekly_macd=0.5). First candidate ever to beat flat DCA OOS (+43.21%
duration-weighted), live (-38.47%), and risk50-linear (+36.57pp); full gate
still not cleared (fold-1 drawdown veto 51.84 vs 50 cap, sensitivity unstable
5.62 on the buy-knee cliff). Cycle 6 reproduced it byte-identically, so this
one artifact covers both. This script never writes `settings.json` or
RESEARCH_STATE.md's validated-candidate section, and never pushes to Supabase.

Purpose: Chris asked to visualize the strategy -- this renders the loop
candidate in the same `TearsheetData` schema the live site uses, via a
local-only `next dev` build. Output goes to a distinct diagnostic slug
(`btc_sdca_cycle4_candidate`), never `btc_sdca`.

Params source: `.scratch/periodic_cycle_4.json`'s `candidate_weights` /
`candidate_curve_shape` -- a frozen snapshot from the cycle-4 run, read as
data (not reconstructed from live presets), so this tearsheet can't silently
drift if settings.json changes after this script was written.

Index source: the Task-7 frozen index via
`run_aggregate_reweight_full17_fixed_index.load_inputs()` -- the exact same
`dates` / `power_law_z` / `extra_z` the cycle runs gated on. NOT the default
`load_sdca_extra_z` path (different windows); using that here would render a
different index than the one behind the +43.21% number.

IMPORTANT: the equity curve below is a full-history curve-simulator backtest
for visualization (fills, allocation, knees) -- it is NOT the OOS gate. The
gate numbers (+43.21% OOS, folds 0/2 pass, fold-1 dd veto, sensitivity) are
quoted from `.scratch/periodic_cycle_4.json` in the notes, not recomputed.

Usage:
    uv run python scripts/build_cycle4_candidate_diagnostic_tearsheet.py
"""

from __future__ import annotations

import json
from datetime import date as date_cls
from pathlib import Path

import polars as pl

# Cross-script import works because `uv run python scripts/<this file>.py`
# puts `scripts/` (this file's own directory) at sys.path[0], and both files
# live there (same pattern as run_periodic_self_optimization_cycle.py).
import run_aggregate_reweight_full17_fixed_index as reweight

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.chart_series import SdcaCurveKnees
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.dca_metrics import (
    breakdown_from_daily,
    dca_current_signal,
    tearsheet_overlays,
)
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_ohlcv
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z
from digiquant.tearsheet_data import from_nautilus_run

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
CYCLE4_PATH = DIGIQUANT_ROOT / ".scratch" / "periodic_cycle_4.json"
WEB_PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

SLUG = "btc_sdca_cycle4_candidate"
# Display constants only, copied read-only from settings.json's `defaults`
# block -- settings.json itself is never touched by this script.
INITIAL_CASH = 1000.0
TRADE_START = date_cls(2018, 1, 1)

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
    cycle = json.loads(CYCLE4_PATH.read_text())
    assert cycle["cycle"] == 4 and cycle["cycle_type"] == "curve", (
        "params source changed -- this script is pinned to periodic_cycle_4.json"
    )
    weights = SdcaCompositeWeights(**cycle["candidate_weights"])
    shape = SdcaCurveShape(**cycle["candidate_curve_shape"])
    candidate = cycle["walk_forward_vs_baseline"]["candidate"]
    mean_oos = candidate["mean_oos_vs_flat_dca_pct_duration_weighted"]
    sensitivity = candidate["sensitivity"]
    per_fold = cycle["per_fold"]
    print(f"Cycle-4 shape: {shape}")
    print(f"Cycle-4 weights: {weights.model_dump()}")
    print(
        f"Gate OOS={mean_oos:+.2f}%  "
        f"beats_flat_dca_oos={candidate['beats_flat_dca_oos']}  "
        f"beats_live_oos={cycle['beats_live_oos']}  "
        f"sensitivity_stable={sensitivity['stable']} "
        f"(worst_neighbor={sensitivity['worst_neighbor_key']}, "
        f"max_abs_delta={sensitivity['max_abs_delta_oos_pct']:.2f})"
    )

    # Identical frozen index to the cycle runs (Task 7 setup): load_inputs()
    # builds power_law_z / extra_z on the signal-delayed frame, and prices
    # come from the same load_sdca_ohlcv call the driver asserts equality on.
    dates, power_law_z, extra_z, _long_windows, _medium_windows = reweight.load_inputs()
    _dates2, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    assert list(_dates2) == list(dates), "price dates diverged from frozen index dates"
    risk_list = risk_from_weighted_z(dates, power_law_z, extra_z, weights)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    risk_s = pl.Series("risk", risk_list, dtype=pl.Float64)

    idx = [i for i, d in enumerate(dates) if d >= TRADE_START]
    if not idx:
        raise ValueError(f"No bars on/after trade_start={TRADE_START}")
    date_w = date_s[idx]
    price_w = price_s[idx]
    risk_w = risk_s[idx]
    power_law_z_w = [power_law_z[i] for i in idx]

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

    # Same rails construction load_inputs() uses internally (identical
    # coefficients/model), sliced to the trade window for the overlay.
    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    low_w = [rails["low"][i] for i in idx]
    median_w = [rails["median"][i] for i in idx]
    high_w = [rails["high"][i] for i in idx]
    rail_tuples = list(zip(low_w, median_w, high_w, strict=True))
    indicator_z: dict[str, list] = {"power_law": power_law_z_w}
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
        preset="cycle-4 loop candidate (mid-knees buy 15 / sell 85)",
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
        "symbol": "BTC-USD",
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
        f"max_dd={f['max_drawdown_pct']:.2f}% feasible={f['feasible']} passes={f['passes']}"
        for f in per_fold
    )
    notes = [
        "DIAGNOSTIC ONLY -- rendered so the periodic-loop candidate can be "
        "inspected visually (fills, allocation, knees) and compared against "
        "every other SDCA calibration attempt. This is the cycle-4 curve "
        "candidate (byte-identically reproduced by cycle 6): tiered robust-"
        "search winner on live weights (power_law=1.0, m2=0.5, dxy=0.5, "
        "weekly_rsi=0.25, weekly_macd=0.5), shape buy 35/45 sell 50/30, "
        "curvatures 1.5/2.5, mid-knees buy 15 / sell 85. It is not published "
        "to digiquant.io and settings.json was never modified.",
        "Gate record (`.scratch/periodic_cycle_4.json`, NOT recomputed here): "
        f"duration-weighted OOS={mean_oos:+.2f}% vs live -38.47% "
        f"(beats_live_oos={cycle['beats_live_oos']}), "
        f"beats_flat_dca_oos={candidate['beats_flat_dca_oos']}, "
        "beats_risk50_linear=True delta=+36.57% (cycle-4 stdout, not in JSON); "
        f"{fold_str}; "
        "sensitivity unstable "
        f"(worst_neighbor={sensitivity['worst_neighbor_key']}, "
        f"max_abs_delta={sensitivity['max_abs_delta_oos_pct']:.2f} vs 2.0). "
        "Full parity gate NOT cleared: fold 1 scores +94.35% OOS but "
        "max_dd=51.84% breaches the 50 cap (OOS window covers Mar-2020).",
        "The equity curve in this artifact is a FULL-HISTORY curve-simulator "
        "backtest (src/digiquant/strategies/sdca/backtest.py, a CI-only "
        "parity harness) -- not a NautilusTrader BacktestResult and not the "
        "OOS gate. Index is the Task-7 frozen index (same dates/power_law_z/"
        "extra_z the cycles gated on), trade window from "
        f"{TRADE_START}, initial cash ${INITIAL_CASH:,.0f} (display constants "
        "only).",
        "Remaining-book SDCA (buy % of remaining cash / sell % of remaining "
        "holdings), marked to market. Research candidate only -- promotion "
        "needs the fold-1 drawdown veto and the buy-knee sensitivity cliff "
        "resolved and explicitly accepted.",
    ]

    dca_kwargs = {
        "current_signal": signal,
        "rails": overlays.get("rails"),
        "risk_curve": overlays.get("risk_curve"),
        "cost_basis_curve": overlays.get("cost_basis_curve"),
        "capital_deployed_curve": overlays.get("capital_deployed_curve"),
        "lump_equity_curve": overlays.get("lump_equity_curve"),
        "flat_dca_equity_curve": overlays.get("flat_dca_equity_curve"),
        "allocated_pct_curve": overlays.get("allocated_pct_curve"),
        "fill_markers": overlays.get("fill_markers"),
        "indicator_curves": overlays.get("indicator_curves"),
        "indicator_weights": overlays.get("indicator_weights"),
        "curve_knees": overlays.get("curve_knees"),
        "label": "BTC-SDCA (Cycle-4 loop candidate)",
        "kind": "dca",
        # Cycle-4's own gate verdict, quoted from periodic_cycle_4.json.
        "beats_flat_dca_oos": True,
    }

    td = from_nautilus_run(
        summary,
        [],
        equity_curve,
        data_source="Coinbase daily OHLCV (CCXT) -- curve-simulator diagnostic, not published",
        notes=notes,
        dca=dca_block,
        **dca_kwargs,
    )

    WEB_PUBLIC_STRATEGIES.mkdir(parents=True, exist_ok=True)
    out_path = WEB_PUBLIC_STRATEGIES / f"{SLUG}.json"
    out_path.write_text(td.to_json())
    print(f"wrote {out_path}")
    print(
        f"  net_profit_pct={td.net_profit_pct:.1f}%  max_drawdown_pct={td.max_drawdown_pct:.1f}%  "
        f"bars={len(equity_curve)}"
    )
    print(
        "\nDiagnostic only -- never pushed to Supabase, never touches settings.json "
        "or RESEARCH_STATE.md's validated-candidate section."
    )


if __name__ == "__main__":
    main()
