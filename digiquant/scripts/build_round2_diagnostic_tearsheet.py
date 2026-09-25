#!/usr/bin/env python3
"""Diagnostic tearsheet for SDCA recalibration v1 Round 2 (NOT promoted).

Round 2 (2026-09-24→25, commit `f748630`, `RESEARCH_STATE.md` "Round 2
result") loosened Phase 3's curve search drawdown gate to
`MAX_DRAWDOWN_CAP_PCT`/`MAX_DRAWDOWN_COMFORT_PCT` = 50.0/45.0 (a true
backstop, no longer the dominant force shaping the search; same shared
driver script as round 1, `scripts/run_recalibration_v1_full_resolution.py`,
just with the module-level constants in `curve_optimize_feasibility.py`
edited between runs) and re-ran the identical Phase 1→4 pipeline with
`crash_override_enabled=True`. This directly fixed round 1's capital
-starvation problem and, headline-wise, is a REAL win: mean OOS (duration
-weighted) `+3.53%` vs. flat DCA, `beats_flat_dca_oos=True`,
`beats_baseline_oos=True` (`+36.30%` over that run's own risk50-linear
baseline of `-32.76%`) -- the first round to clear both bars. Still not
promoted: fold 2 `max_drawdown_pct=50.8%` breaches even the loosened 50%
backstop, and **all three OOS folds fail `walk_forward.py`'s own
`capital_deployed_floor_pct=10.0` gate** (fold 0 `-28.5%`, fold 1 `-1.1%`,
fold 2 `-7.8%` -- net sellers over every OOS window). Per-fold `vs_flat_dca`:
fold 0 `+37.21%`, fold 1 `-13.30%`, fold 2 `-13.31%` -- the strong headline
average is carried entirely by fold 0; folds 1 and 2 individually still lose
to flat DCA. Round 2's shape is also the one round 4 (see
`build_round4_diagnostic_tearsheet.py`) converged back to independently via
a completely different search axis (dead-zone width), confirming it as a
genuine local optimum under this weight set -- not promoted regardless.

This script never writes ``settings.json`` or ``RESEARCH_STATE.md``'s
"Current best validated candidate" section, and never pushes to Supabase.

Purpose: let Chris visually inspect Round 2's shape and equity curve in the
same ``TearsheetData`` schema / UI the real digiquant.io strategy pages
render, via a local-only ``next dev`` build — not the live site. Output is
written to a distinct diagnostic slug (``btc_sdca_round2``), never
``btc_sdca``. Mirrors ``scripts/build_round8_diagnostic_tearsheet.py``'s
pattern exactly.

Data source: ``backtest.py::run_backtest``, the CI-only curve-simulator
parity harness — never Nautilus-authoritative.

Usage:
    uv run python scripts/build_round2_diagnostic_tearsheet.py
"""

from __future__ import annotations

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.chart_series import SdcaCurveKnees
from digiquant.strategies.sdca.crash_override import apply_crash_override
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.dca_metrics import (
    breakdown_from_daily,
    dca_current_signal,
    tearsheet_overlays,
)
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights, fast_crash_vol_z
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z
from digiquant.tearsheet_data import from_nautilus_run

from datetime import date as date_cls
from pathlib import Path

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
WEB_PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

SLUG = "btc_sdca_round2"
# Display constants only, copied read-only from src/digiquant/strategies/settings.json's
# `defaults` block -- settings.json itself is never touched by this script.
INITIAL_CASH = 1000.0
TRADE_START = date_cls(2018, 1, 1)

STAGE1_OSCILLATORS = SdcaOscillatorSpec(
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
EXTRA_WINDOWS: dict[str, int] = {
    "dxy": 60,
    "onchain_mvrv": 365,
    "onchain_asopr": 365,
    "onchain_puell": 365,
    "onchain_rhodl": 365,
    "onchain_addr_ratio": 365,
    "fear_greed": 270,
}

# Phase 1 weights (floored 12-name search, primary 3:1 ratio) -- shared by every round
# in this recalibration.
PHASE1_WEIGHTS = SdcaCompositeWeights(
    power_law=1.0,
    m2=0.1,
    rs_eth=0.1,
    dxy=0.1,
    onchain_mvrv=0.1,
    onchain_asopr=0.1,
    onchain_puell=0.1,
    onchain_rhodl=0.1,
    onchain_addr_ratio=0.1,
    fear_greed=0.1,
    weekly_monthly_rsi=0.1,
    weekly_monthly_macd=0.5,
)

# Round 2's winning shape under the loosened 50/45 drawdown gate
# (RESEARCH_STATE.md "Round 2 result", commit f748630). Numerically identical
# to round 4's shape (see build_round4_diagnostic_tearsheet.py) -- round 4
# converged back here independently via the dead-zone-width search axis.
ROUND2_SHAPE = SdcaCurveShape(
    buy_max_rate=25.0,
    buy_knee_risk=40.0,
    sell_knee_risk=70.0,
    sell_max_rate=30.0,
    buy_curvature=1.5,
    sell_curvature=1.0,
)

CRASH_TRIGGER_Z = -2.0
CRASH_RAMP_Z = 1.0
CRASH_OVERRIDE_RISK = 95.0
CRASH_WINDOW = 14
CRASH_MIN_SAMPLES = 7

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
    shape = ROUND2_SHAPE
    print(f"Round 2 shape: {shape}")
    print(
        "Full walk-forward vs. risk50-linear baseline (RESEARCH_STATE.md): "
        "mean_oos_vs_flat_dca_pct=+3.53%  beats_flat_dca_oos=True  "
        "beats_baseline_oos=True (+36.30% over baseline -32.76%) -- but fold 2 "
        "drawdown breaches the 50% backstop and all 3 OOS folds fail the "
        "capital_deployed_floor_pct=10.0 gate, so still not promoted."
    )

    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"],
        trend_window=STAGE1_OSCILLATORS.power_law_trend_window,
    ).to_list()
    extra_z = load_sdca_extra_z(
        dates, prices, data_path=DEFAULT_DATA_PATH, data_dir=None,
        oscillators=STAGE1_OSCILLATORS, extra_windows=EXTRA_WINDOWS,
    )
    risk_list = risk_from_weighted_z(dates, power_law_z, extra_z, PHASE1_WEIGHTS)
    risk_plain = pl.Series("risk", risk_list, dtype=pl.Float64)

    crash_z = fast_crash_vol_z(date_s, price_s, window=CRASH_WINDOW, min_samples=CRASH_MIN_SAMPLES)
    risk_with_override = pl.Series(
        "risk_override",
        apply_crash_override(
            risk_plain, crash_z, trigger_z=CRASH_TRIGGER_Z, ramp_z=CRASH_RAMP_Z,
            override_risk=CRASH_OVERRIDE_RISK,
        ),
    )

    idx = [i for i, d in enumerate(dates) if d >= TRADE_START]
    if not idx:
        raise ValueError(f"No bars on/after trade_start={TRADE_START}")
    date_w = pl.Series("date", [dates[i] for i in idx], dtype=pl.Date)
    price_w = pl.Series("price", [prices[i] for i in idx], dtype=pl.Float64)
    risk_w = pl.Series("risk", [risk_with_override[i] for i in idx], dtype=pl.Float64)
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
    for name in PHASE1_WEIGHTS.enabled_extras():
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
        weights=PHASE1_WEIGHTS.model_dump(),
    )
    overlays["curve_knees"] = SdcaCurveKnees(
        buy_knee_risk=shape.buy_knee_risk,
        sell_knee_risk=shape.sell_knee_risk,
        preset="round2_recalibration_diagnostic",
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
        "DIAGNOSTIC ONLY -- NOT a validated or promoted strategy. This is SDCA "
        "recalibration v1's Round 2 candidate (2026-09-24, commit f748630), "
        "rendered here so the shape and equity curve can be inspected visually. "
        "It is not published to digiquant.io and settings.json was never modified.",
        "Full walk-forward vs. risk50-linear baseline: mean OOS (duration-weighted) "
        "vs. flat DCA = +3.53%, beats_flat_dca_oos=True, beats_baseline_oos=True "
        "(+36.30% over that run's own baseline of -32.76%) -- the first round to "
        "clear both bars headline-wise. Per-fold vs_flat_dca: fold 0 +37.21%, "
        "fold 1 -13.30%, fold 2 -13.31% -- fold 0 alone carries the average; "
        "folds 1 and 2 individually still lose to flat DCA.",
        "Why still not promoted despite the headline win: fold 2's "
        "max_drawdown_pct=50.8% breaches even this round's own loosened 50% "
        "backstop, and ALL THREE OOS folds fail walk_forward.py's own "
        "capital_deployed_floor_pct=10.0 gate (fold 0 -28.5%, fold 1 -1.1%, "
        "fold 2 -7.8% -- net sellers over every OOS window, not net buyers). "
        "The improved headline return comes from correctly selling out of and "
        "staying out of two bad windows, not from staying invested through "
        "them -- fold 1's OOS window swallows the entire 2020-21 bull run and "
        "fold 2's swallows the 2023-24 recovery, both missed entirely.",
        "Change from round 1: loosened Phase 3's curve-search drawdown gate from "
        "comfort=25%/cap=30% to comfort=45%/cap=50% (a true backstop, no longer "
        "the dominant force shaping the search), fixing round 1's capital "
        "-starvation failure. Same Phase 1→4 pipeline, same crash_override, "
        "otherwise unchanged from round 1.",
        "Curve-simulator backtest (src/digiquant/strategies/sdca/backtest.py, a "
        "CI-only parity harness) -- not a NautilusTrader BacktestResult. Phase 1 "
        "weights (12-name floored search, primary 3:1 ratio): power_law:1.0, "
        "everything else at the 0.1 floor except weekly_monthly_macd:0.5. "
        "crash_override enabled (trigger_z=-2.0, ramp_z=1.0, override_risk=95.0).",
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
        "label": "BTC-SDCA (Round 2 diagnostic — not promoted)",
        "kind": "dca",
        # Round 2 beat the baseline but not flat DCA -- never claim an OOS win here.
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
