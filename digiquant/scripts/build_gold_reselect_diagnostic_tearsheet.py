#!/usr/bin/env python3
"""Diagnostic tearsheet for the gold SDCA reselected shape (#4804, Plan 16).

Renders ONLY (STOP: no gate/seed re-run, no weight/window/threshold/curve
change, no re-selection, no new sens — all numbers below are read from the
Task-1/Task-2 records, never recomputed here).

Buy vote = v4/v6 vote unchanged (rolling-z anchor window 90 / z 1.0, no time
trend, + m2/uup 0.5 + weekly RSI / weekly log-MACD / SMA band 0.25), with
sells vetoed outside the frozen strict-box mask (z <= -2.0 & m >= 1.5,
``digiquant/.scratch/gold_sell_mask.json``, 74 days).

Selection record (``.scratch/gold_reselect_v6.json``, attempt 1 of the
frozen ≤3-attempt bound): frozen criterion argmax min(mean_flat, mean_lump)
with tie-breaks higher-lump then lower-DD; 144 eligible; selected rank #1
(buy 35/60, sell 65/30, curvatures 1.0/1.0, single-knee): criterion min
+3.85 = mean OOS vs flat +24.32 / vs lump +3.85; fresh sens STABLE
(max_abs_delta 1.63 ≤ 2.0 over 48 neighbors, worst sell_knee_risk:-5%);
3/3 folds feasible (Rule-B frontier). Verdict: BEATS-BOTH (conditional).

Overlap disclosure: sma_band (price vs trailing SMA) and the rolling_z
rails anchor (price vs 90d trailing mean) vote the same mean-reversion
family; the anchor carries 1.0, sma_band 0.25. The gate prices the
overlap, this script only renders it.

Veto accounting: vetoed days keep their negative curve ``rate`` in frame
and hold exactly like null-risk days — visuals/analysis key off
``daily_trade_usd`` / fill sell days, NOT rate sign.

Research-only: slug ``gold_sdca_v6_reselect``, never pushed to Supabase,
never touches settings.json or any validated-candidate section.

Usage:
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/build_gold_reselect_diagnostic_tearsheet.py
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
SEARCH_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_curve_search_v6b.json"
RESELECT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_reselect_v6.json"
MASK_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_sell_mask.json"
WEB_PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

SLUG = "gold_sdca_v6_reselect"
# Display constants only -- nothing published is touched by this script.
INITIAL_CASH = 1000.0
TRADE_START = date_cls(2010, 1, 1)

# 90d matches the v4/v6 buy vote (same literals as the v4 seed / v6 gate).
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
    reselect = json.loads(RESELECT_PATH.read_text())
    weights = SdcaCompositeWeights(**search["weights"])
    shape = shape_from_params(reselect["chosen_params"])
    assert shape.buy_mid_knee_risk is None and shape.sell_mid_knee_risk is None, (
        "reselected rank #1 is single-knee; mid-tier keys must stay unset"
    )
    means = reselect["chosen_table_means"]
    sens = reselect["fresh_sens"]
    per_fold = reselect["fresh_per_fold"]
    mask_doc = json.loads(MASK_PATH.read_text())
    sell_dates = {date_cls.fromisoformat(d) for d in mask_doc["mask_days"]}
    label = "GLD-SDCA (reselected-shape diagnostic — BEATS-BOTH conditional)"
    print(f"Reselected shape: {shape}")
    print(f"Vote weights: {weights.model_dump()}")
    print(f"Mask days: {mask_doc['mask_count']} ({mask_doc['thresholds']})")
    print(
        f"Chosen mean_flat={means['flat']:+.2f}%  mean_lump={means['lump']:+.2f}%  "
        f"sens_stable={sens['stable']} (max_abs_delta={sens['max_abs_delta']:.2f})"
    )

    # Full-calendar rolling rails (causal trailing op, same as the v4 seed /
    # v6 gate: each output uses only inputs <= t -- NOT an OOS fit).
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

    # Masked full-history render: sells fire only on mask days (same veto
    # semantics as the v6 gate). Vetoed days keep negative rate in frame;
    # fills (daily_trade_usd) are the veto-aware signal.
    curve = AccumDistCurve(shape.to_nodes())
    _report, frame = run_backtest(
        date_w, price_w, risk_w, curve, INITIAL_CASH, sell_dates=sell_dates
    )

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
        preset="gold reselected rank #1 (single-knee, v4/v6-identical vote)",
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
        f"oos_vs_lump={f['oos_vs_lump_dca_pct']:+.2f}% feasible={f['feasible']} "
        f"mask_days={f['oos_sell_mask_days']}"
        for f in per_fold
    )
    mask_days = mask_doc["mask_days"]
    mask_span = f"{mask_days[0]}..{mask_days[-1]}" if mask_days else "none"
    notes = [
        "DIAGNOSTIC ONLY, BEATS-BOTH (conditional) verdict — gold SDCA "
        "reselected shape (Plan 16, rank #1 of the v6b frontier), rendered "
        "for visual inspection (fills, allocation, knees). Buy vote = v4/v6 "
        "vote unchanged: rolling-z anchor (window 90d / z 1.0, no time "
        "trend) + m2/uup 0.5 + weekly RSI / weekly log-MACD / SMA band 0.25, "
        "reselected shape "
        f"(buy {shape.buy_max_rate:.0f}/{shape.buy_knee_risk:.0f}, sell "
        f"{shape.sell_knee_risk:.0f}/{shape.sell_max_rate:.0f}, single-knee). "
        "Sells vetoed outside the frozen strict-box mask (z<=-2.0 & m>=1.5, "
        f"{mask_doc['mask_count']} days, {mask_span}); a vetoed day holds "
        "exactly like a null-risk day but keeps its negative rate in frame — "
        "key visuals/analysis off daily_trade_usd / fill sell days, NOT "
        "rate sign. Not published anywhere; settings.json never modified. "
        "This artifact renders the selection; it is not a promotion claim.",
        "Selection record (`.scratch/gold_reselect_v6.json`, attempt "
        f"{reselect['attempt']} of the frozen 3-attempt bound, NOT recomputed "
        "here): frozen criterion argmax min(mean_flat, mean_lump) with "
        "tie-breaks higher-lump then lower-DD; "
        f"{reselect['eligible_count']} eligible; selected rank #1 "
        f"(criterion min={reselect['top5'][0]['criterion_min']:+.2f}% = mean "
        f"flat={means['flat']:+.2f}% / mean lump={means['lump']:+.2f}%). "
        "DISCLOSURE (1/4) selection optimism: the shape was selected ON the "
        "reported metric, so expect optimism — these means are "
        "selection-flavored, not unbiased estimates. DISCLOSURE (4/4) "
        "projection tie: ranks #2–#4 carry an identical gated eval "
        "(mid-tier projection tie — same min/flat/lump/DD to shown "
        "precision); rank #1 wins only on the recorded tie-break order, not "
        "on a measured edge.",
        "Fresh sens + per-fold (same record, 1 attempt, NOT recomputed "
        "here): sensitivity STABLE "
        f"(max_abs_delta={sens['max_abs_delta']:.2f} ≤ 2.0 over "
        f"{sens['neighbor_count']} neighbors, worst "
        f"{sens['worst_neighbor_key']}); {fold_str}; all folds feasible "
        "(Rule-B frontier). DISCLOSURE (2/4) thin lump margin: the mean "
        f"lump edge is only {means['lump']:+.2f}%, and fold 2's lump is "
        "negative (−0.81%, on 1 mask day). DISCLOSURE (3/4) fold 1 has ZERO "
        "mask days (selection barely sees the mask there; mask evidence = "
        "fold-0 73 days + v6 robustness).",
        "The equity curve in this artifact is a FULL-HISTORY masked "
        "curve-simulator backtest "
        "(src/digiquant/strategies/sdca/backtest.py, a CI-only parity "
        "harness, sell_dates applied as in the v6 gate) -- not a "
        "NautilusTrader BacktestResult and not the OOS gate. Trade window "
        f"from {TRADE_START}, initial cash ${INITIAL_CASH:,.0f} (display "
        "constants only).",
        "Remaining-book SDCA (buy % of remaining cash / sell % of remaining "
        "holdings), marked to market. Research candidate only. "
        "Frontier-reselect is Plan 16; the verdict word is BEATS-BOTH "
        "(conditional), carried with all four disclosures above.",
    ]

    td = from_nautilus_run(
        summary,
        [],
        equity_curve,
        data_source="GLD daily OHLCV (yfinance) -- masked curve-simulator diagnostic, not published",
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
        beats_flat_dca_oos=bool(means["flat"] > 0),
    )

    WEB_PUBLIC_STRATEGIES.mkdir(parents=True, exist_ok=True)
    out_path = WEB_PUBLIC_STRATEGIES / f"{SLUG}.json"
    out_path.write_text(td.to_json())
    print(
        f"wrote {out_path}  net_profit_pct={td.net_profit_pct:.1f}%  "
        f"max_drawdown_pct={td.max_drawdown_pct:.1f}%  bars={len(equity_curve)}  "
        f"fill_sell_days={dca_block.fill_sell_days}"
    )
    print(
        "\nDiagnostic only, BEATS-BOTH (conditional) -- never pushed to Supabase, never touches settings.json."
    )


if __name__ == "__main__":
    main()
