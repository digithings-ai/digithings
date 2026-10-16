#!/usr/bin/env python3
"""Diagnostic tearsheet for the first gold SDCA candidate (#4804).

Single-knee shape buy 35/60, sell 65/30, linear, on seed weights
(valuation=1.0, m2=0.5, dxy=0.5) over the frozen full-history
generic_valuation index. Gate record (`.scratch/gold_curve_search.json`,
NOT recomputed here): unweighted mean OOS +14.52%, beats_flat_dca_oos=True;
fold 0 +38.20% infeasible, fold 1 -11.19% feasible, fold 2 +16.54%
feasible; sensitivity unstable (3.86 vs 2.0). Full gate NOT cleared.

Attribution (`.scratch/gold_attribution.json`): m2 and dxy are each
load-bearing raw-IS (~-67/-69pp alone, -26pp together); log_linear-form
challenger rails are byte-identical to the seed.

Research-only: slug `gld_sdca_candidate`, never pushed to Supabase, never
touches settings.json or any validated-candidate section.

Usage:
    uv run python scripts/build_gold_diagnostic_tearsheet.py
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
from digiquant.strategies.sdca.generic_valuation import (
    GenericValuationRiskModel,
    fit_generic_valuation,
)
from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    extra_indicators_for_window,
)
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.walk_forward import shape_from_params
from digiquant.tearsheet_data import from_nautilus_run

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
SEARCH_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_curve_search.json"
WEB_PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

SLUG = "gld_sdca_candidate"
# Display constants only -- nothing published is touched by this script.
INITIAL_CASH = 1000.0
TRADE_START = date_cls(2010, 1, 1)

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
    shape = shape_from_params(search["search"]["shape"])
    assert shape.buy_mid_knee_risk is None and shape.sell_mid_knee_risk is None, (
        "gold winner is single-knee; mid-tier keys must stay unset"
    )
    gate = search["gate"]
    label = "GLD-SDCA (gold candidate diagnostic)"
    print(f"Gold shape: {shape}")
    print(f"Gold weights: {weights.model_dump()}")
    print(
        f"Gate mean_oos={gate['mean_oos_vs_flat_dca_pct']:+.2f}%  "
        f"beats_flat_dca_oos={gate['beats_flat_dca_oos']}  "
        f"sensitivity_stable={gate['sensitivity_stable']} "
        f"(max_abs_delta={gate['sensitivity_max_abs_delta']:.2f})"
    )

    # Frozen full-history generic_valuation index, same construction as the
    # seed/search scripts (full-history fit -- Task-7 caveat documented in
    # run_gold_frozen_index.py; NOT the OOS gate).
    dates, prices = load_sdca_ohlcv(symbols=["GLD-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    risk_model = GenericValuationRiskModel(fit_generic_valuation(date_s, price_s))
    extra_z = load_sdca_extra_z(dates, prices, data_path=DEFAULT_DATA_PATH, data_dir=None)
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
        preset="gold loop candidate (single-knee, linear)",
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
        "DIAGNOSTIC ONLY -- first gold SDCA candidate, rendered for visual "
        "inspection (fills, allocation, knees). Single-knee shape buy 35/60, "
        "sell 65/30, linear, on seed weights (valuation=1.0, m2=0.5, "
        "dxy=0.5) over the frozen full-history generic_valuation index. Not "
        "published anywhere; settings.json never modified.",
        "Gate record (`.scratch/gold_curve_search.json`, NOT recomputed "
        f"here): mean OOS={gate['mean_oos_vs_flat_dca_pct']:+.2f}%, "
        f"beats_flat_dca_oos={gate['beats_flat_dca_oos']}; {fold_str}; "
        "sensitivity unstable "
        f"(max_abs_delta={gate['sensitivity_max_abs_delta']:.2f} vs 2.0). "
        "Full gate NOT cleared: fold 1 is OOS-negative and sensitivity is "
        "unstable.",
        "Attribution (`.scratch/gold_attribution.json`): m2 and dxy each "
        "load-bearing raw-IS; valuation-only trails the seed; the "
        "log_linear-form challenger index is identical to the seed.",
        "The equity curve in this artifact is a FULL-HISTORY curve-simulator "
        "backtest (src/digiquant/strategies/sdca/backtest.py, a CI-only "
        "parity harness) -- not a NautilusTrader BacktestResult and not the "
        "OOS gate. Trade window from "
        f"{TRADE_START}, initial cash ${INITIAL_CASH:,.0f} (display constants "
        "only).",
        "Remaining-book SDCA (buy % of remaining cash / sell % of remaining "
        "holdings), marked to market. Research candidate only -- promotion "
        "needs the fold-1 OOS negative and sensitivity resolved and "
        "explicitly accepted.",
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
