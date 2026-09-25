#!/usr/bin/env python3
"""Diagnostic tearsheet for the ACTUAL live settings.json `btc_sdca` config.

This is RESEARCH_STATE.md's "Known discrepancy" candidate: settings.json's
`btc_sdca` block currently carries `weekly_rsi=0.25, weekly_macd=0.5` on top
of the validated baseline's `power_law=1.0, m2=0.5, dxy=0.5` -- added by an
unrelated "Cursor Agent" commit (`82cd1ddcc`) that itself documents
`beats_flat_dca_oos: false`. This 5-weight config has been walk-forward-
validated twice this session and loses badly both times. This script never
writes `settings.json` or RESEARCH_STATE.md's "Current best validated
candidate" section, and never pushes to Supabase.

Purpose: Chris asked how to compare against "the current version of the
strategy" -- this IS that comparison. It is deliberately NOT the same thing
as `btc_sdca_validated_baseline`; the whole point of this tearsheet is to
make that gap visible side by side.

Params source: `.scratch/baseline_relative_rescore.json`'s
`live_settings_json.candidate.best_params` -- a frozen snapshot from this
session's baseline-relative re-score (`run_baseline_relative_rescore.py`,
Phase 3), reconstructed via `shape_from_params` / `composite_weights_from_params`
rather than reading settings.json live, so this tearsheet reflects the exact
config that was actually scored at -34.80% OOS, immune to any settings.json
drift since.

Usage:
    uv run python scripts/build_live_settings_diagnostic_tearsheet.py
"""

from __future__ import annotations

import json
from datetime import date as date_cls
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.chart_series import SdcaCurveKnees
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.dca_metrics import (
    breakdown_from_daily,
    dca_current_signal,
    tearsheet_overlays,
)
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z
from digiquant.strategies.sdca.walk_forward import composite_weights_from_params, shape_from_params
from digiquant.tearsheet_data import from_nautilus_run

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
RESCORE_PATH = DIGIQUANT_ROOT / ".scratch" / "baseline_relative_rescore.json"
WEB_PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

SLUG = "btc_sdca_live_settings"
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
    rescore = json.loads(RESCORE_PATH.read_text())
    candidate = rescore["live_settings_json"]["candidate"]
    params = candidate["best_params"]
    if params.get("crash_override_enabled"):
        raise ValueError("this script assumes crash_override_enabled=False; params changed")

    shape = shape_from_params(params)
    weights = composite_weights_from_params(params)
    mean_oos = candidate["mean_oos_vs_flat_dca_pct"]
    sensitivity = candidate["sensitivity"]
    delta_pct = rescore["live_settings_json"]["delta_mean_oos_vs_flat_dca_pct"]
    beats_baseline_oos = rescore["live_settings_json"]["beats_baseline_oos"]
    print(f"Live-settings shape: {shape}")
    print(f"Live-settings weights: {weights.model_dump()}")
    print(
        f"mean_oos_vs_flat_dca_pct={mean_oos:+.2f}%  beats_flat_dca_oos="
        f"{candidate['beats_flat_dca_oos']}  sensitivity_stable={sensitivity['stable']}  "
        f"delta_vs_baseline={delta_pct:+.2f}%  beats_baseline_oos={beats_baseline_oos}"
    )

    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=180
    ).to_list()
    extra_z = load_sdca_extra_z(dates, prices, data_path=DEFAULT_DATA_PATH, data_dir=None)
    risk_list = risk_from_weighted_z(dates, power_law_z, extra_z, weights)

    idx = [i for i, d in enumerate(dates) if d >= TRADE_START]
    if not idx:
        raise ValueError(f"No bars on/after trade_start={TRADE_START}")
    date_w = pl.Series("date", [dates[i] for i in idx], dtype=pl.Date)
    price_w = pl.Series("price", [prices[i] for i in idx], dtype=pl.Float64)
    risk_w = pl.Series("risk", [risk_list[i] for i in idx], dtype=pl.Float64)
    power_law_z_w = [power_law_z[i] for i in idx]
    low_w = [rails["low"][i] for i in idx]
    median_w = [rails["median"][i] for i in idx]
    high_w = [rails["high"][i] for i in idx]

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
        preset="btc_optimized (curve unchanged; weights are the live drift)",
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

    notes = [
        "DIAGNOSTIC ONLY -- this is what's ACTUALLY live in "
        "settings.json's btc_sdca block right now, not the validated "
        "baseline. It carries weekly_rsi=0.25, weekly_macd=0.5 on top of "
        "the validated power_law=1.0/m2=0.5/dxy=0.5 -- added by an unrelated "
        "\"Cursor Agent\" commit (82cd1ddcc) that itself documents "
        "beats_flat_dca_oos: false. This script never modified settings.json "
        "and is not published to digiquant.io.",
        f"Walk-forward vs. flat DCA: mean_oos_vs_flat_dca_pct={mean_oos:+.2f}%, "
        f"beats_flat_dca_oos={candidate['beats_flat_dca_oos']}. Walk-forward "
        f"vs. the risk50-linear baseline (run_baseline_relative_rescore.py): "
        f"delta_mean_oos_vs_flat_dca_pct={delta_pct:+.2f}%, "
        f"beats_baseline_oos={beats_baseline_oos}. This config has now been "
        "walk-forward-validated three times total (twice previously per "
        "RESEARCH_STATE.md's Known discrepancy section at -16.21% and "
        "-46.23% to -51.28% OOS, plus this session's rescore) and loses "
        "every time.",
        "Curve-simulator backtest (src/digiquant/strategies/sdca/backtest.py, "
        "a CI-only parity harness) -- not a NautilusTrader BacktestResult. "
        f"Weights: power_law:{weights.power_law}/m2:{weights.m2}/"
        f"dxy:{weights.dxy}/weekly_rsi:{weights.weekly_rsi}/"
        f"weekly_macd:{weights.weekly_macd}.",
        f"Remaining-book SDCA (buy % of remaining cash / sell % of remaining "
        f"holdings), marked to market, trade window from {TRADE_START}, "
        f"initial cash ${INITIAL_CASH:,.0f} (display constants only, matching "
        "the published btc_sdca settings.json).",
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
        "label": "BTC-SDCA (Live settings.json -- NOT validated)",
        "kind": "dca",
        "beats_flat_dca_oos": False,
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
