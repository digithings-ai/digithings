#!/usr/bin/env python3
"""Diagnostic tearsheet for Blend Approach 3 (literal hybrid weight vector, round 8's curve reused).

Chris likes "the valuation index shape of the 17 indicator strat, then the
performance and behavior of the round 8 [strategy]." Approach 3 is the
cheapest blend: round 8's 5 nonzero weights held as fixed floors, Task #93
Round 2's other ~12 nonzero weights layered in at half value, round 8's
exact curve reused unchanged -- no new search at all
(``scripts/run_blend_approach3_hybrid_weights.py``).

Result: candidate mean_oos_vs_flat_dca_pct=+41.57% (both weightings),
beats_flat_dca_oos=True (numerically), but sensitivity.stable=False
(max_abs_delta_oos_pct=10.92 vs a 2.0 threshold -- notably MORE unstable
than round 8's own 4.25). REJECT under the standing accept gate. This is the
closest of the three blends to round 8's own profile (numerically beats
flat DCA, same failure mode -- fails sensitivity) but with a lower raw OOS
number and a much larger sensitivity spike, i.e. blending in Round 2's other
indicators at half weight did not improve on round 8, it degraded both the
OOS number and the stability margin.

This script never writes settings.json or RESEARCH_STATE.md's "Current best
validated candidate" section, and never pushes to Supabase.

Params/weights/curve source: duplicated verbatim from
``.scratch/blend/approach3_hybrid_weights_round8_curve.json``'s
``candidate_params`` (the output of
``run_blend_approach3_hybrid_weights.py``), reconstructed via
``shape_from_params``/``composite_weights_from_params`` so this tearsheet is
provably the exact config that was scored.

Usage:
    uv run python scripts/build_blend3_diagnostic_tearsheet.py
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
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z
from digiquant.strategies.sdca.walk_forward import composite_weights_from_params, shape_from_params
from digiquant.tearsheet_data import from_nautilus_run

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
RESULT_PATH = DIGIQUANT_ROOT / ".scratch" / "blend" / "approach3_hybrid_weights_round8_curve.json"
WEB_PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

SLUG = "btc_sdca_blend3"
INITIAL_CASH = 1000.0
TRADE_START = date_cls(2018, 1, 1)

# Duplicated verbatim from run_blend_approach3_hybrid_weights.py -- see that
# script's docstring for why ROUND23_OSCILLATORS governs the combined index
# build even though round 8's own floor indicators were originally scored
# under SdcaOscillatorSpec()'s defaults.
ROUND23_OSCILLATORS = SdcaOscillatorSpec(
    power_law_trend_window=180,
    rs_eth_window=60,
    rs_eth_fast_window=30,
    rsi_length=5,
    daily_rsi_length=5,
    macd_fast=12,
    macd_slow=26,
    macd_daily_fast=12,
    macd_daily_slow=26,
    sma_band_window=180,
    sma_band_fast_window=45,
    monthly_rsi_length=5,
    monthly_rsi_daily_length=5,
    monthly_macd_fast=4,
    monthly_macd_slow=9,
)

ROUND23_EXTRA_WINDOWS: dict[str, int] = {
    "dxy": 60,
    "onchain_mvrv": 365,
    "onchain_asopr": 365,
    "onchain_puell": 365,
    "onchain_rhodl": 365,
    "onchain_addr_ratio": 365,
    "fear_greed": 270,
}

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
    result = json.loads(RESULT_PATH.read_text())
    params = result["candidate_params"]
    if params.get("crash_override_enabled"):
        raise ValueError("this script assumes crash_override_enabled=False; params changed")

    shape = shape_from_params(params)
    weights = composite_weights_from_params(params)
    candidate = result["comparison"]["candidate"]
    mean_oos_unweighted = candidate["mean_oos_vs_flat_dca_pct_unweighted"]
    mean_oos_duration = candidate["mean_oos_vs_flat_dca_pct_duration_weighted"]
    sensitivity = candidate["sensitivity"]
    delta_pct = result["comparison"]["delta_mean_oos_vs_flat_dca_pct"]
    beats_baseline_oos = result["comparison"]["beats_baseline_oos"]
    print(f"Blend3 shape: {shape}")
    print(f"Blend3 weights: {weights.model_dump()}")
    print(
        f"mean_oos_unweighted={mean_oos_unweighted:+.2f}%  mean_oos_duration={mean_oos_duration:+.2f}%  "
        f"beats_flat_dca_oos={candidate['beats_flat_dca_oos']}  sensitivity_stable={sensitivity['stable']} "
        f"(max_abs_delta_oos_pct={sensitivity['max_abs_delta_oos_pct']:.2f})  "
        f"delta_vs_baseline={delta_pct:+.2f}%  beats_baseline_oos={beats_baseline_oos}"
    )

    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s,
        price_s,
        rails["low"],
        rails["median"],
        rails["high"],
        trend_window=ROUND23_OSCILLATORS.power_law_trend_window,
    ).to_list()
    extra_z = load_sdca_extra_z(
        dates,
        prices,
        data_path=DEFAULT_DATA_PATH,
        data_dir=None,
        oscillators=ROUND23_OSCILLATORS,
        extra_windows=ROUND23_EXTRA_WINDOWS,
    )
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
        preset="blend3_diagnostic",
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
        "DIAGNOSTIC ONLY -- NOT a validated or promoted strategy. Blend "
        "Approach 3: round 8's 5 nonzero weights (m2=1.0, rs_eth=0.1, "
        "onchain_asopr=0.1, fear_greed=0.1, weekly_monthly_rsi=0.1) held as "
        "fixed floors, Task #93 Round 2's other ~12 nonzero weights layered "
        "in at half their Round 2 value, round 8's exact curve reused "
        "unchanged -- no new curve search. It is not published to "
        "digiquant.io and settings.json was never modified.",
        f"Walk-forward vs. flat DCA: mean_oos_vs_flat_dca_pct(unweighted)="
        f"{mean_oos_unweighted:+.2f}%, mean_oos_vs_flat_dca_pct(duration)="
        f"{mean_oos_duration:+.2f}%, beats_flat_dca_oos="
        f"{candidate['beats_flat_dca_oos']} (numerically positive). "
        f"Walk-forward vs. the risk50-linear baseline: "
        f"delta_mean_oos_vs_flat_dca_pct={delta_pct:+.2f}%, "
        f"beats_baseline_oos={beats_baseline_oos}. BUT it FAILED the "
        f"sensitivity-neighbor stability gate "
        f"(max_abs_delta_oos_pct={sensitivity['max_abs_delta_oos_pct']:.2f} "
        f"vs a {sensitivity['spike_threshold_pct']:.1f} threshold) -- "
        "verdict is Not Promoted.",
        "Compared to round 8 (+52.01% OOS, max_abs_delta_oos_pct=4.25, both "
        "numerically beat flat DCA but fail sensitivity): Blend 3 has the "
        "same failure mode as round 8 but a lower raw OOS number and a "
        "notably larger sensitivity spike (10.92 vs 4.25) -- layering in "
        "Round 2's other indicators at half weight degraded both the return "
        "number and the stability margin rather than improving on round 8.",
        "Curve-simulator backtest (src/digiquant/strategies/sdca/backtest.py, "
        "a CI-only parity harness) -- not a NautilusTrader BacktestResult. "
        "Hybrid composite weights (see indicator_weights below); dominant "
        "member m2 (1.0, round 8's floor), with onchain_rhodl/"
        "onchain_addr_ratio/weekly_monthly_macd (0.5 each, half Round 2's "
        "1.0) as the largest Round-2-derived contributions.",
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
        "label": "BTC-SDCA (Blend 3: Hybrid weights, Round 8 curve)",
        "kind": "dca",
        # False per this field's own documented semantics ("do not claim an
        # OOS win") -- Blend 3 failed the stability gate despite beating both
        # flat DCA and the risk50-linear baseline numerically, same as round
        # 8 and Task #93 Round 2.
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
