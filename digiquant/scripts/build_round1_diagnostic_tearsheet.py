#!/usr/bin/env python3
"""Diagnostic tearsheet for SDCA recalibration v1 Round 1 (NOT promoted).

Round 1 (2026-09-24, commit `9abe32429`, `RESEARCH_STATE.md` "Immediate
backlog" item 7) set Phase 3's curve search to a tight blanket drawdown gate
(`MAX_DRAWDOWN_CAP_PCT`/`MAX_DRAWDOWN_COMFORT_PCT` = 30.0/25.0, a *binding*
search-time constraint, not a backstop) and ran Phase 4
(`scripts/run_recalibration_v1_full_resolution.py`) with
`crash_override_enabled=True`. **Failed outright**: mean OOS (duration
-weighted) `-37.31%` vs. flat DCA, `beats_flat_dca_oos=False`,
`beats_baseline_oos=False` (that run's own risk50-linear baseline came in at
`-27.32%`). This is the hollow-win/capital-starved failure mode: the tight
cap forced the search to resolve the drawdown/capital-deployed tension by
starving capital deployment instead of finding a genuinely safer shape
(fold 0 `capital_deployed=-94.1%`, fold 1 `0.3%`, fold 2 `-9.4%` — barely
investing at all). This script does NOT sand that down; the numbers below
are the real, unpromoted result.

This script never writes ``settings.json`` or ``RESEARCH_STATE.md``'s
"Current best validated candidate" section, and never pushes to Supabase.

Purpose: let Chris visually inspect Round 1's shape and equity curve in the
same ``TearsheetData`` schema / UI the real digiquant.io strategy pages
render, via a local-only ``next dev`` build — not the live site. Output is
written to a distinct diagnostic slug (``btc_sdca_round1``), never
``btc_sdca``. Mirrors ``scripts/build_round8_diagnostic_tearsheet.py``'s
pattern exactly.

Data source: ``backtest.py::run_backtest``, the CI-only curve-simulator
parity harness — never Nautilus-authoritative. Reuses the exact Phase 1
composite-risk computation (12-name floored weight search, primary 3:1
ratio) plus ``crash_override`` (verified against the real 2020-03-12 COVID
crash) that every round in this recalibration used, per
``scripts/run_recalibration_v1_full_resolution.py``.

Usage:
    uv run python scripts/build_round1_diagnostic_tearsheet.py
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
import json

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
WEB_PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

SLUG = "btc_sdca_round1"
# Display constants only, copied read-only from src/digiquant/strategies/settings.json's
# `defaults` block (btc_sdca's published trade window / capital) -- settings.json itself
# is never touched by this script. Same constants round 8's diagnostic uses, so every
# round's tearsheet in this comparison starts from the same capital base.
INITIAL_CASH = 1000.0
TRADE_START = date_cls(2018, 1, 1)

# Frozen Stage 1 oscillator winners + macro/on-chain window override -- identical across
# every round of this recalibration (scripts/run_recalibration_v1_full_resolution.py,
# .scratch/recalibration_v1_round{3,4}.py).
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
# in this recalibration (rounds 1-4 all held this fixed; only the curve shape changed).
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

# Round 1's winning shape under the tight 30/25 drawdown gate
# (RESEARCH_STATE.md "Round 1 result", commit 9abe32429).
ROUND1_SHAPE = SdcaCurveShape(
    buy_max_rate=15.0,
    buy_knee_risk=30.0,
    sell_knee_risk=45.0,
    sell_max_rate=15.0,
    buy_curvature=1.5,
    sell_curvature=1.0,
)

# crash_override calibrated defaults, verified against the real 2020-03-12 COVID crash --
# unchanged across every round in this recalibration.
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
    shape = ROUND1_SHAPE
    print(f"Round 1 shape: {shape}")
    print(
        "Full walk-forward vs. risk50-linear baseline (RESEARCH_STATE.md): "
        "mean_oos_vs_flat_dca_pct=-37.31%  beats_flat_dca_oos=False  "
        "beats_baseline_oos=False (baseline -27.32%)"
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

    # crash_override was enabled for round 1's Phase 4 evaluation -- apply it here too
    # so this diagnostic reflects the same risk series round 1 was actually scored on.
    crash_z = fast_crash_vol_z(date_s, price_s, window=CRASH_WINDOW, min_samples=CRASH_MIN_SAMPLES)
    risk_with_override = pl.Series(
        "risk_override",
        apply_crash_override(
            risk_plain, crash_z, trigger_z=CRASH_TRIGGER_Z, ramp_z=CRASH_RAMP_Z,
            override_risk=CRASH_OVERRIDE_RISK,
        ),
    )

    # Window to the published trade_start (same pattern as round 8's diagnostic /
    # generate_tearsheets.py's window_ohlcv_to_trade_start) -- the backtest's cash
    # book starts fresh here.
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
        preset="round1_recalibration_diagnostic",
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
        "recalibration v1's Round 1 candidate (2026-09-24, commit 9abe32429), "
        "rendered here so the shape and equity curve can be inspected visually. "
        "It is not published to digiquant.io and settings.json was never modified.",
        "Full walk-forward vs. risk50-linear baseline: mean OOS (duration-weighted) "
        "vs. flat DCA = -37.31%, beats_flat_dca_oos=False, beats_baseline_oos=False "
        "(that run's own baseline came in at -27.32%). This round FAILED outright -- "
        "it is not a close miss.",
        "Root cause: Phase 3's curve search used a tight blanket drawdown gate "
        "(comfort=25%, cap=30%) as a BINDING search-time constraint rather than a "
        "backstop. The search resolved the drawdown/capital-deployed tension by "
        "starving capital deployment instead of finding a genuinely safer shape -- "
        "fold 0 capital_deployed=-94.1%, fold 1 capital_deployed=0.3%, fold 2 "
        "capital_deployed=-9.4% (barely investing at all across every OOS fold). "
        "This is the hollow-win/capital-starved failure mode this recalibration set "
        "out to move past in round 2.",
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
        "label": "BTC-SDCA (Round 1 diagnostic — not promoted)",
        "kind": "dca",
        # Round 1 failed outright on both bars -- never claim an OOS win here.
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
