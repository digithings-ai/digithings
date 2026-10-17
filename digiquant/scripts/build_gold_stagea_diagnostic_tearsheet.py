#!/usr/bin/env python3
"""Diagnostic tearsheets for the gold SDCA Stage-A votes (#4804, Plan 18 Task 3).

Renders TWO votes from the EXISTING Stage-A ranking
(``digiquant/.scratch/gold_stage_a.json`` — no new search, no new fit):

- V1: the winner (valuation-only on the frozen generic_valuation /
  log_quadratic full-history rails). Diagnostic behavior reference ONLY —
  promotion-BARRED under the standing no-trend steer.
- V2: the best valuation-free combo (real_rate-only, valuation weight 0 —
  the steer-compliant candidate). Built as an extras-only composite:
  ``build_risk_index`` with ``valuation_weight=0`` omits the valuation leg
  entirely (no vote, no null mask), so the frozen rails choice does not
  affect V2's risk — the same rails object is passed for display only.

The reselect CURVE is HELD CONSTANT for both votes (shape from
``.scratch/gold_reselect_v6.json`` ``chosen_params``; sells vetoed outside
the frozen strict-box mask exactly as in the reselect render). Only the
risk-index vote changes, isolating the vote change.

Byte-mirror of ``build_gold_reselect_diagnostic_tearsheet.py`` except:
weights source (Stage-A ranking, not the v6b search JSON), risk model
(generic_valuation frozen rails, not rolling_z), ``--vote`` seam, and the
per-vote notes/slug. No ``--weights`` seam existed on any prior builder
(all hardcode weights), so this file is the brief-authorized mirror.

Research-only: slugs ``gold_sdca_stagea_v1`` / ``gold_sdca_stagea_v2``,
never pushed to Supabase, never touches settings.json or any
validated-candidate section. Full-history masked curve-sim renders
(diagnostic, NOT gate claims).

Usage:
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/build_gold_stagea_diagnostic_tearsheet.py [--vote v1|v2|both]
"""

from __future__ import annotations

import argparse
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
STAGE_A_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_stage_a.json"
RESELECT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_reselect_v6.json"
MASK_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_sell_mask.json"
WEB_PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

SLUGS = {"v1": "gold_sdca_stagea_v1", "v2": "gold_sdca_stagea_v2"}
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


def load_votes() -> tuple[SdcaCompositeWeights, dict, SdcaCompositeWeights, dict, float]:
    """Read V1 + V2 from the existing ranking (no search). Returns weights + rank rows + gap."""
    ranking = json.loads(STAGE_A_PATH.read_text())["top100"]
    v1_row = ranking[0]
    v1 = SdcaCompositeWeights(**v1_row["weights"])
    v2_row = next(r for r in ranking if r["weights"]["valuation"] == 0.0)
    v2 = SdcaCompositeWeights(**v2_row["weights"])
    assert all(v == 0.0 for k, v in v1_row["weights"].items() if k != "valuation"), (
        "V1 must be the valuation-only winner"
    )
    assert v1_row["weights"]["valuation"] > 0.0, "V1 must carry valuation weight"
    gap = float(v1_row["score"]["objective"]) - float(v2_row["score"]["objective"])
    return v1, v1_row, v2, v2_row, gap


def render_vote(
    vote: str,
    weights: SdcaCompositeWeights,
    rank_row: dict,
    gap_vs_v1: float,
    shape_doc: str,
) -> dict:
    slug = SLUGS[vote]
    shape = shape_from_params(json.loads(RESELECT_PATH.read_text())["chosen_params"])
    assert shape.buy_mid_knee_risk is None and shape.sell_mid_knee_risk is None, (
        "reselect rank #1 is single-knee; mid-tier keys must stay unset"
    )
    mask_doc = json.loads(MASK_PATH.read_text())
    sell_dates = {date_cls.fromisoformat(d) for d in mask_doc["mask_days"]}

    # Frozen generic_valuation log_quadratic full-history rails — the same
    # rails Stage-A scored on (Task-2 repro gate: rebuild max abs diff 0.0
    # vs gold_seed.json). For V2 (valuation weight 0) the leg is omitted
    # from the composite entirely; rails are display only.
    dates, prices = load_sdca_ohlcv(symbols=["GLD-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    risk_model = resolve_sdca_risk_model(
        "generic_valuation", dates=date_s, price=price_s, form="log_quadratic"
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
    # semantics as the reselect render). Vetoed days keep negative rate in
    # frame; fills (daily_trade_usd) are the veto-aware signal.
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
        preset=f"gold reselect rank #1, HELD CONSTANT for Stage-A {vote.upper()}",
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

    years = (date_cls.fromisoformat(date_strs[-1]) - date_cls.fromisoformat(date_strs[0])).days
    years /= 365.25
    non_null_risk = [r for r in risk_vals if r is not None]
    acc = sum(1 for r in non_null_risk if r <= 35.0)
    dst = sum(1 for r in non_null_risk if r >= 80.0)

    score = rank_row["score"]
    if vote == "v1":
        vote_line = (
            "V1 = Stage-A rank #1 (valuation-only on the frozen "
            "generic_valuation/log_quadratic full-history rails): IN-SAMPLE "
            "cycle-overlap winner, diagnostic behavior reference ONLY — "
            "promotion-BARRED under the standing no-trend steer (the rails "
            "are the in-sample trend fit voting for itself)."
        )
    else:
        vote_line = (
            "V2 = best valuation-free combo (rank #49, real_rate-only, "
            "valuation weight 0 — the steer-compliant candidate). Separation "
            f"gap vs V1: {gap_vs_v1:+.2f} objective points "
            f"({score['objective']:.2f} vs V1 "
            f"{score['objective'] + gap_vs_v1:.2f}). Built as an extras-only "
            "composite (valuation leg omitted entirely — no vote, no null "
            "mask); frozen rails are display only. Exact tie with rank #50 "
            "(real_rate 1.0 — same normalized blend); first-seen 0.5 kept."
        )
    notes = [
        f"DIAGNOSTIC ONLY, NO GATE CLAIM — gold SDCA Stage-A {vote.upper()} "
        f"({slug}), rendered for behavior inspection (fills, allocation, "
        "knees). " + vote_line,
        "Reselect curve HELD CONSTANT (shape from "
        "`.scratch/gold_reselect_v6.json` chosen_params, "
        f"{shape_doc}; sells vetoed outside the frozen strict-box mask, "
        f"{mask_doc['mask_count']} days): only the risk-index vote differs "
        "from the reselect render, isolating the vote change. A vetoed day "
        "holds exactly like a null-risk day but keeps its negative rate in "
        "frame — key visuals/analysis off daily_trade_usd / fill sell days, "
        "NOT rate sign. Not published anywhere; settings.json never "
        "modified.",
        "Stage-A is IN-SAMPLE (overlap maximized on the same full-history "
        "series it is measured on; holdout absent) and selects nothing "
        "shippable; only the Stage-B gate judges. The equity curve here is "
        "a FULL-HISTORY masked curve-simulator backtest "
        "(src/digiquant/strategies/sdca/backtest.py, a CI-only parity "
        "harness, sell_dates applied as in the reselect render) — not a "
        "NautilusTrader BacktestResult and not the OOS gate. Trade window "
        f"from {TRADE_START}, initial cash ${INITIAL_CASH:,.0f} (display "
        "constants only).",
        "Remaining-book SDCA (buy % of remaining cash / sell % of remaining "
        "holdings), marked to market. Research candidate only.",
    ]

    label = f"GLD-SDCA Stage-A {vote.upper()} (diagnostic — no gate claim)"
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
        beats_flat_dca_oos=False,
    )

    WEB_PUBLIC_STRATEGIES.mkdir(parents=True, exist_ok=True)
    out_path = WEB_PUBLIC_STRATEGIES / f"{slug}.json"
    out_path.write_text(td.to_json())
    stats = {
        "slug": slug,
        "separation": score["objective"],
        "fill_buy_days": dca_block.fill_buy_days,
        "fill_sell_days": dca_block.fill_sell_days,
        "fills_per_year": dca_block.fill_sell_days / years,
        "sell_days_per_year": dca_block.sell_days / years,
        "band_accumulate_pct": acc / len(non_null_risk) * 100.0,
        "band_distribute_pct": dst / len(non_null_risk) * 100.0,
        "vs_flat_dca_pct": dca_block.vs_flat_dca_pct,
        "vs_lump_pct": dca_block.vs_lump_pct,
        "years": years,
    }
    print(
        f"wrote {out_path}  net_profit_pct={td.net_profit_pct:.1f}%  "
        f"max_drawdown_pct={td.max_drawdown_pct:.1f}%  bars={len(equity_curve)}  "
        f"fill_sell_days={dca_block.fill_sell_days}"
    )
    print(
        f"  fills/yr={stats['fills_per_year']:.2f}  "
        f"sell-days/yr={stats['sell_days_per_year']:.1f}  "
        f"acc={stats['band_accumulate_pct']:.1f}%  dst={stats['band_distribute_pct']:.1f}%  "
        f"vs_flat={dca_block.vs_flat_dca_pct:+.1f}%  vs_lump={dca_block.vs_lump_pct:+.1f}%  "
        "(diagnostic, not gate)"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Stage-A V1/V2 diagnostic tearsheets.")
    parser.add_argument("--vote", choices=("v1", "v2", "both"), default="both")
    args = parser.parse_args()

    v1, v1_row, v2, v2_row, gap = load_votes()
    print(f"V1 weights: {v1.model_dump()}")
    print(f"V2 weights: {v2.model_dump()}")
    print(
        f"V1 separation={v1_row['score']['objective']:.6f}  "
        f"V2 separation={v2_row['score']['objective']:.6f}  gap={gap:.6f}"
    )
    reselect = json.loads(RESELECT_PATH.read_text())
    cp = reselect["chosen_params"]
    shape_doc = (
        f"buy {cp['buy_max_rate']:.0f}/{cp['buy_knee_risk']:.0f}, sell "
        f"{cp['sell_knee_risk']:.0f}/{cp['sell_max_rate']:.0f}, single-knee"
    )
    print(f"Reselect curve (HELD CONSTANT): {shape_doc}")

    votes = ("v1", "v2") if args.vote == "both" else (args.vote,)
    by_vote = {"v1": (v1, v1_row, 0.0), "v2": (v2, v2_row, gap)}
    for vote in votes:
        weights, rank_row, vote_gap = by_vote[vote]
        render_vote(vote, weights, rank_row, vote_gap, shape_doc)
    print(
        "\nDiagnostic only, no gate claim -- never pushed to Supabase, never touches settings.json."
    )


if __name__ == "__main__":
    main()
