#!/usr/bin/env python3
"""Diagnostic tearsheets for the top-3 gated SDCA calibrations.

All three run the same cycle-4 tiered curve shape (buy 35/45, sell 50/30,
curvatures 1.5/2.5, mid-knees buy 15 / sell 85) and differ only in weights:

1. ``btc_sdca_top1_drop_rsi`` -- live minus weekly_rsi, gated OOS +44.10%
2. ``btc_sdca_top2_drop_macd`` -- live minus weekly_macd, gated OOS +43.28%
3. ``btc_sdca_top3_live`` -- live weights, gated OOS +43.21%

Gate numbers are quoted from `.scratch/oscillator_dropone.json` (top 1-2)
and `.scratch/periodic_cycle_4.json` (top 3), NOT recomputed. Spreads are
<=1pp (established as in-sample noise in the oscillator gate verdict), so
expect near-identical equity curves -- the set documents robustness, not a
ranking to act on. Research-only: never touches settings.json, never pushes
to Supabase, never writes RESEARCH_STATE.md's validated-candidate section.

Index source: the Task-7 frozen index via
`run_aggregate_reweight_full17_fixed_index.load_inputs()` -- the exact
series the gates ran on. Same builder pattern as
`build_cycle4_candidate_diagnostic_tearsheet.py`.

Usage:
    uv run python scripts/build_top3_diagnostic_tearsheets.py
"""

from __future__ import annotations

import json
from datetime import date as date_cls
from pathlib import Path

import polars as pl

# Cross-script import works because `uv run python scripts/<this file>.py`
# puts `scripts/` (this file's own directory) at sys.path[0] (same pattern
# as run_periodic_self_optimization_cycle.py).
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
from digiquant.strategies.sdca.walk_forward import shape_from_params
from digiquant.tearsheet_data import from_nautilus_run

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
CYCLE4_PATH = DIGIQUANT_ROOT / ".scratch" / "periodic_cycle_4.json"
OSC_DROPONE_PATH = DIGIQUANT_ROOT / ".scratch" / "oscillator_dropone.json"
WEB_PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

# Display constants only -- settings.json itself is never touched.
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


def build_one(
    slug: str,
    label: str,
    weights: SdcaCompositeWeights,
    shape: SdcaCurveShape,
    gate_oos: float,
    gate_folds: list[dict],
    gate_sens_stable: bool,
    gate_sens_delta: float,
    gate_sens_worst: str,
    gate_provenance: str,
    weight_note: str,
    dates: list,
    prices: list[float],
    power_law_z: list,
    extra_z: dict,
) -> None:
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

    # Same rails construction load_inputs() uses internally, sliced to window.
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
        preset=f"{label} (mid-knees buy 15 / sell 85)",
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
        "strategy": slug,
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
        f"max_dd={f['max_drawdown_pct']:.2f}% feasible={f['feasible']}"
        for f in gate_folds
    )
    notes = [
        "DIAGNOSTIC ONLY -- one of the top-3 gated SDCA calibrations, "
        f"rendered for visual comparison ({label}). {weight_note} "
        "Curve shape is the cycle-4 tiered winner in all three (buy 35/45, "
        "sell 50/30, curvatures 1.5/2.5, mid-knees buy 15 / sell 85). Not "
        "published to digiquant.io; settings.json never modified.",
        f"Gate record ({gate_provenance}, NOT recomputed here): "
        f"duration-weighted OOS={gate_oos:+.2f}%; {fold_str}; "
        f"sensitivity stable={gate_sens_stable} "
        f"(worst_neighbor={gate_sens_worst}, "
        f"max_abs_delta={gate_sens_delta:.2f} vs 2.0).",
        "The equity curve in this artifact is a FULL-HISTORY curve-simulator "
        "backtest (src/digiquant/strategies/sdca/backtest.py, a CI-only "
        "parity harness) -- not a NautilusTrader BacktestResult and not the "
        "OOS gate. Index is the Task-7 frozen index, trade window from "
        f"{TRADE_START}, initial cash ${INITIAL_CASH:,.0f} (display constants "
        "only).",
        "Remaining-book SDCA (buy % of remaining cash / sell % of remaining "
        "holdings), marked to market. Research candidates only.",
    ]

    td = from_nautilus_run(
        summary,
        [],
        equity_curve,
        data_source="Coinbase daily OHLCV (CCXT) -- curve-simulator diagnostic, not published",
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
        label=f"BTC-SDCA ({label})",
        kind="dca",
        beats_flat_dca_oos=bool(gate_oos > 0),
    )

    WEB_PUBLIC_STRATEGIES.mkdir(parents=True, exist_ok=True)
    out_path = WEB_PUBLIC_STRATEGIES / f"{slug}.json"
    out_path.write_text(td.to_json())
    print(
        f"wrote {out_path}  net_profit_pct={td.net_profit_pct:.1f}%  "
        f"max_drawdown_pct={td.max_drawdown_pct:.1f}%  bars={len(equity_curve)}"
    )


def main() -> None:
    cycle4 = json.loads(CYCLE4_PATH.read_text())
    shape = shape_from_params(cycle4["candidate_curve_shape"])
    live = SdcaCompositeWeights(**cycle4["candidate_weights"])
    osc = json.loads(OSC_DROPONE_PATH.read_text())

    dates, power_law_z, extra_z, _long_w, _medium_w = reweight.load_inputs()
    _dates2, prices = load_sdca_ohlcv(
        symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None
    )
    assert list(_dates2) == list(dates), "price dates diverged from frozen index dates"

    no_rsi = SdcaCompositeWeights(**{**live.model_dump(), "weekly_rsi": 0.0})
    no_macd = SdcaCompositeWeights(**{**live.model_dump(), "weekly_macd": 0.0})

    calibrations = [
        {
            "slug": "btc_sdca_top1_drop_rsi",
            "label": "Top-1 gated (drop weekly_rsi)",
            "weights": no_rsi,
            "sidecar": osc["drop_weekly_rsi"],
            "provenance": ".scratch/oscillator_dropone.json :: drop_weekly_rsi",
            "weight_note": "Live 5-weights minus weekly_rsi (0.25 -> 0.0).",
        },
        {
            "slug": "btc_sdca_top2_drop_macd",
            "label": "Top-2 gated (drop weekly_macd)",
            "weights": no_macd,
            "sidecar": osc["drop_weekly_macd"],
            "provenance": ".scratch/oscillator_dropone.json :: drop_weekly_macd",
            "weight_note": "Live 5-weights minus weekly_macd (0.5 -> 0.0).",
        },
        {
            "slug": "btc_sdca_top3_live",
            "label": "Top-3 gated (live weights)",
            "weights": live,
            "sidecar": {
                "duration_oos_vs_flat_dca_pct": cycle4["walk_forward_vs_baseline"]["candidate"][
                    "mean_oos_vs_flat_dca_pct_duration_weighted"
                ],
                "folds": [
                    {
                        "fold": f["fold"],
                        "oos_vs_flat_dca_pct": f["oos_vs_flat_dca_pct"],
                        "max_drawdown_pct": f["max_drawdown_pct"],
                        "feasible": f["feasible"],
                    }
                    for f in cycle4["per_fold"]
                ],
                "sensitivity_stable": cycle4["walk_forward_vs_baseline"]["candidate"][
                    "sensitivity"
                ]["stable"],
                "sensitivity_max_abs_delta": cycle4["walk_forward_vs_baseline"]["candidate"][
                    "sensitivity"
                ]["max_abs_delta_oos_pct"],
                "sensitivity_worst_neighbor": cycle4["walk_forward_vs_baseline"]["candidate"][
                    "sensitivity"
                ]["worst_neighbor_key"],
            },
            "provenance": ".scratch/periodic_cycle_4.json",
            "weight_note": "Unmodified live 5-weights "
            "(power_law=1.0, m2=0.5, dxy=0.5, weekly_rsi=0.25, weekly_macd=0.5).",
        },
    ]

    for cal in calibrations:
        sidecar = cal["sidecar"]
        build_one(
            slug=cal["slug"],
            label=cal["label"],
            weights=cal["weights"],
            shape=shape,
            gate_oos=sidecar["duration_oos_vs_flat_dca_pct"],
            gate_folds=sidecar["folds"],
            gate_sens_stable=sidecar["sensitivity_stable"],
            gate_sens_delta=sidecar["sensitivity_max_abs_delta"],
            gate_sens_worst=sidecar["sensitivity_worst_neighbor"],
            gate_provenance=cal["provenance"],
            weight_note=cal["weight_note"],
            dates=dates,
            prices=prices,
            power_law_z=power_law_z,
            extra_z=extra_z,
        )
    print("\nDiagnostic only -- never pushed to Supabase, never touches settings.json.")


if __name__ == "__main__":
    main()
