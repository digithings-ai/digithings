#!/usr/bin/env python3
"""Diagnostic tearsheet for post-mortem ablation Round 8 (NOT promoted).

Round 8 (SDCA post-mortem follow-up Phase 4/5 --
``.scratch/ablation/best_round_full_resolution.json``) numerically beat the
risk50-linear baseline in the full walk-forward comparison
(``delta_mean_oos_vs_flat_dca_pct`` positive, ``beats_baseline_oos=True``) but
FAILED the sensitivity-neighbor stability gate -- see
``src/digiquant/strategies/sdca/RESEARCH_STATE.md`` item 10 and the "Standard
trial protocol". It is explicitly **not** the validated candidate. This
script never writes ``settings.json`` or ``RESEARCH_STATE.md``'s
"Current best validated candidate" section, and never pushes to Supabase.

Purpose: let Chris visually inspect Round 8's shape in the same
``TearsheetData`` schema / UI the real digiquant.io strategy pages render,
via a local-only ``next dev`` build -- not the live site. Output is written
to a distinct diagnostic slug (``btc_sdca_round8``), never ``btc_sdca``.

Data source: ``backtest.py::run_backtest``, the CI-only curve-simulator
parity harness (see its own docstring) -- never Nautilus-authoritative.
Reuses the exact same risk-weighting computation
(``power_law_confluence_z`` + ``load_sdca_extra_z`` + ``risk_from_weighted_z``
with ``ROUND8_WEIGHTS``) that produced and validated Round 8's curve shape in
``run_ablation_best_round_full_resolution.py``, so this diagnostic reflects
the same signal Round 8 was actually scored on.

Usage:
    uv run python scripts/build_round8_diagnostic_tearsheet.py
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
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.dca_metrics import (
    breakdown_from_daily,
    dca_current_signal,
    tearsheet_overlays,
)
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z
from digiquant.tearsheet_data import from_nautilus_run

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
BEST_ROUND_PATH = DIGIQUANT_ROOT / ".scratch" / "ablation" / "best_round_full_resolution.json"
WEB_PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

SLUG = "btc_sdca_round8"
# Display constants only, copied read-only from src/digiquant/strategies/settings.json's
# `defaults` block (btc_sdca's published trade window / capital) -- settings.json itself
# is never touched by this script.
INITIAL_CASH = 1000.0
TRADE_START = date_cls(2018, 1, 1)

# Duplicated verbatim from scripts/run_ablation_best_round_full_resolution.py --
# Round 8's weights were scored against extra_z built with these windows.
EXTRA_WINDOWS: dict[str, int] = {
    "dxy": 60,
    "onchain_mvrv": 365,
    "onchain_asopr": 365,
    "onchain_puell": 365,
    "onchain_rhodl": 365,
    "onchain_addr_ratio": 365,
    "fear_greed": 270,
}

ROUND8_WEIGHTS = SdcaCompositeWeights(
    power_law=0.0,
    m2=1.0,
    rs_eth=0.1,
    onchain_asopr=0.1,
    fear_greed=0.1,
    weekly_monthly_rsi=0.1,
)

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
    best_round = json.loads(BEST_ROUND_PATH.read_text())
    params = best_round["candidate"]["best_params"]
    shape = SdcaCurveShape(
        buy_max_rate=params["buy_max_rate"],
        buy_knee_risk=params["buy_knee_risk"],
        sell_knee_risk=params["sell_knee_risk"],
        sell_max_rate=params["sell_max_rate"],
        buy_curvature=params["buy_curvature"],
        sell_curvature=params["sell_curvature"],
    )
    delta_pct = best_round["delta_mean_oos_vs_flat_dca_pct"]
    beats_baseline_oos = best_round["beats_baseline_oos"]
    print(f"Round 8 shape: {shape}")
    print(f"delta_mean_oos_vs_flat_dca_pct={delta_pct:+.2f}%  beats_baseline_oos={beats_baseline_oos}")

    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=180
    ).to_list()
    extra_z = load_sdca_extra_z(
        dates, prices, data_path=DEFAULT_DATA_PATH, data_dir=None, extra_windows=EXTRA_WINDOWS
    )
    risk_list = risk_from_weighted_z(dates, power_law_z, extra_z, ROUND8_WEIGHTS)

    # Window to the published trade_start (same pattern as generate_tearsheets.py's
    # window_ohlcv_to_trade_start) -- the backtest's cash book starts fresh here.
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
    for name in ROUND8_WEIGHTS.enabled_extras():
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
        weights=ROUND8_WEIGHTS.model_dump(),
    )
    # No real preset backs round 8's shape (it's an ablation search result, not
    # a published preset) -- build curve_knees directly instead of going
    # through knees_from_preset(), which only resolves known preset names.
    overlays["curve_knees"] = SdcaCurveKnees(
        buy_knee_risk=shape.buy_knee_risk,
        sell_knee_risk=shape.sell_knee_risk,
        preset="round8_ablation_diagnostic",
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
        "DIAGNOSTIC ONLY -- NOT a validated or promoted strategy. This is the "
        "post-mortem follow-up's iterative-ablation Round 8 candidate "
        "(scripts/run_ablation_best_round_full_resolution.py), rendered here so "
        "the shape can be inspected visually. It is not published to "
        "digiquant.io and settings.json was never modified.",
        f"Full walk-forward vs. risk50-linear baseline: "
        f"delta_mean_oos_vs_flat_dca_pct={delta_pct:+.2f}%, "
        f"beats_baseline_oos={beats_baseline_oos}. Numerically ahead of the "
        "baseline, but FAILED the sensitivity-neighbor stability gate "
        "(RESEARCH_STATE.md item 10) -- verdict is Not Promoted, not a "
        "validated win.",
        "Curve-simulator backtest (src/digiquant/strategies/sdca/backtest.py, "
        "a CI-only parity harness) -- not a NautilusTrader BacktestResult. "
        f"Weights: m2:{ROUND8_WEIGHTS.m2}/rs_eth:{ROUND8_WEIGHTS.rs_eth}/"
        f"onchain_asopr:{ROUND8_WEIGHTS.onchain_asopr}/"
        f"fear_greed:{ROUND8_WEIGHTS.fear_greed}/"
        f"weekly_monthly_rsi:{ROUND8_WEIGHTS.weekly_monthly_rsi} "
        f"(power_law weight 0 -- dropped this round).",
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
        "label": "BTC-SDCA (Round 8 diagnostic — not promoted)",
        "kind": "dca",
        # False per this field's own documented semantics ("do not claim an OOS
        # win") -- Round 8 failed the stability gate despite beating the
        # baseline numerically.
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
