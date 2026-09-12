#!/usr/bin/env python3
"""Stages 2b-4 of the Phase B indicator-addition playbook, restricted to the
2 on-chain survivors from the combined Stage 2 reweight
(``run_onchain_expanded_reweight.py``): ``onchain_mvrv`` and ``onchain_rhodl``
both earned weight strictly above the 0.1 floor there (both pinned at the
grid's 1.0 ceiling); ``onchain_asopr``/``onchain_puell`` collapsed exactly to
the floor and are dropped per Phase B step 3's own acceptance rule ("a
candidate pinned at the floor is contributing no signal beyond what the
floor forces, not real diversification value").

Stage 2b: re-run the floor-diversified combined reweight restricted to just
``power_law + m2 + dxy + onchain_mvrv + onchain_rhodl`` (5 dims instead of
7) -- dropping 2 dead dimensions can shift the joint optimum for the
survivors, so this is not simply "read off the old 7-dim result and drop
two entries."

Stage 3: freeze Stage 2b's winning weights into an index (on-chain series
built at the same construction windows Stage 1 selected --
``onchain_mvrv`` at 1095d, ``onchain_rhodl`` at 730d -- via
``run_onchain_solo_search.py``) and run the existing wide-knee curve search
against it. Index-then-curve: never reuse an old curve fit against a
changed index (AGENTS.md). ``n_random=400`` (matching
``run_published_curve_search``'s default) for a fast go/no-go pass, not the
production-scale search.

Stage 4: 3-fold walk-forward OOS validation of the frozen (Stage 2b weights
+ Stage 3 curve) candidate under both evaluators (curve_simulator and
nautilus), same convention as RESEARCH_STATE.md's documented
"+84.90%/+84.78% OOS" 3-weight baseline.

Diagnostic only until Chris's explicit accept -- does not touch
settings.json or RESEARCH_STATE.md.

Usage:
    uv run python scripts/run_onchain_survivors_validation.py
"""

from __future__ import annotations

import time
from datetime import date as Date
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve_optimize import params_from_shape, search_wide_knee_curve
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import onchain_mvrv_z, onchain_rhodl_z
from digiquant.strategies.sdca.nautilus_evaluator import evaluate_sdca_trial_nautilus
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import optimize_stage_a_weights_combined, risk_from_weighted_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

# Winning windows from run_onchain_solo_search.py's Stage 1 pass.
ONCHAIN_WINDOWS = {"onchain_mvrv": 1095, "onchain_rhodl": 730}

SEARCH_NAMES = ("m2", "dxy", "onchain_mvrv", "onchain_rhodl")
SEARCH_GRID = (0.1, 0.325, 0.55, 0.775, 1.0)
FLOOR = 0.1
MAX_WEIGHT = 1.0
CURVE_TRADE_START = Date(2018, 1, 1)


def print_wf_row(label: str, result) -> None:
    holdout = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics else float("nan")
    print(
        f"{label:>16} | IS {result.mean_is_vs_flat_dca_pct:7.2f} | OOS {result.mean_oos_vs_flat_dca_pct:7.2f} "
        f"| gap {result.is_oos_gap_pct:7.2f} | holdout {holdout:7.2f} | beats_oos {str(result.beats_flat_dca_oos):>5}"
    )
    for fs in result.fold_scores:
        oos = fs.out_of_sample
        print(
            f"    fold {fs.fold.fold}: IS={fs.in_sample.vs_flat_dca_pct:8.2f}%  "
            f"OOS={oos.vs_flat_dca_pct:8.2f}%  feasible={fs.feasible}  "
            f"OOS_drawdown={oos.max_drawdown_pct:6.2f}%  OOS_capital_deployed={oos.capital_deployed_pct:6.2f}%"
        )
    if result.holdout_metrics is not None:
        h = result.holdout_metrics
        print(
            f"    holdout: vs_flat_dca={h.vs_flat_dca_pct:.2f}%  vs_lump={h.vs_lump_pct:.2f}%  "
            f"capital_deployed={h.capital_deployed_pct:.2f}%  max_drawdown={h.max_drawdown_pct:.2f}%"
        )
    print(
        f"    sensitivity: stable={result.sensitivity.stable}  "
        f"max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp"
    )


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=180,
    ).to_list()

    base_extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    sources = load_sdca_extra_sources(data_path.parent)
    if sources.onchain_mvrv_dates is None or sources.onchain_rhodl_dates is None:
        raise SystemExit("missing onchain_mvrv/onchain_rhodl source data")

    extra_z = dict(base_extra_z)
    extra_z["onchain_mvrv"] = onchain_mvrv_z(
        date_s, sources.onchain_mvrv_dates, sources.onchain_mvrv_values,
        window=ONCHAIN_WINDOWS["onchain_mvrv"],
    ).to_list()
    extra_z["onchain_rhodl"] = onchain_rhodl_z(
        date_s, sources.onchain_rhodl_dates, sources.onchain_rhodl_values,
        window=ONCHAIN_WINDOWS["onchain_rhodl"],
    ).to_list()

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    print(f"=== Stage 2b: survivors-only reweight (floor=0.1/max=1.0, grid={SEARCH_GRID}) ===\n")
    t0 = time.monotonic()
    stage2b = optimize_stage_a_weights_combined(
        dates,
        power_law_z=power_law_z,
        extra_z=extra_z,
        long_windows=long_windows,
        medium_windows=medium_windows,
        search_names=SEARCH_NAMES,
        grid=SEARCH_GRID,
        power_law_grid=SEARCH_GRID,
        long_weight=long_weight,
        medium_weight=medium_weight,
        min_weight_floor=FLOOR,
    )
    elapsed = time.monotonic() - t0
    print(f"  evaluated: {stage2b.num_evaluations} combinations in {elapsed:.1f}s")
    print(
        f"  score: long={stage2b.score.long.objective:.2f} medium={stage2b.score.medium.objective:.2f} "
        f"combined={stage2b.score.objective:.2f}"
    )
    for name in ("power_law",) + SEARCH_NAMES:
        w = getattr(stage2b.weights, name)
        note = "at floor -- no real signal beyond diversification" if abs(w - FLOOR) < 1e-9 else ""
        print(f"    {name:<16} {w:.3f}  {note}")
    print()

    print(f"=== Stage 3: wide-knee curve search on frozen Stage-2b index (trade_start={CURVE_TRADE_START}) ===\n")
    risk_list = risk_from_weighted_z(dates, power_law_z, extra_z, stage2b.weights)
    risk_s = pl.Series("risk", risk_list, dtype=pl.Float64)
    idx = pl.DataFrame({"date": date_s, "price": price_s, "risk": risk_s})
    idx = idx.filter(pl.col("date") >= CURVE_TRADE_START)
    null_count = idx["risk"].null_count()
    print(f"  frozen index: {idx['date'][0]}..{idx['date'][-1]} ({len(idx)} bars, {null_count} null risk rows)")
    if null_count > 0:
        idx = idx.filter(pl.col("risk").is_not_null())
        print(f"  dropped null rows -> {len(idx)} bars remain")

    t0 = time.monotonic()
    curve_result = search_wide_knee_curve(
        idx["date"], idx["price"], idx["risk"],
        initial_cash=1000.0,
        frozen_weights=stage2b.weights,
        n_random=400,
        seed=42,
        include_grid=True,
    )
    elapsed = time.monotonic() - t0
    print(
        f"  evaluated: {curve_result.num_evaluations} trials ({curve_result.num_feasible} feasible) "
        f"in {elapsed:.1f}s"
    )
    print(
        f"  baseline (published curve): risk_adjusted_return={curve_result.baseline.risk_adjusted_return:.3f} "
        f"total_return={curve_result.baseline.total_return_pct:.1f}% "
        f"max_dd={curve_result.baseline.max_drawdown_pct:.1f}%"
    )
    print(
        f"  winner: risk_adjusted_return={curve_result.best.risk_adjusted_return:.3f} "
        f"total_return={curve_result.best.total_return_pct:.1f}% "
        f"max_dd={curve_result.best.max_drawdown_pct:.1f}% "
        f"beats_baseline={curve_result.beats_baseline_return}"
    )
    print(f"  winning shape: {curve_result.best.shape.model_dump()}")
    print()

    print("=== Stage 4: 3-fold walk-forward OOS validation ===\n")
    weight_params: dict[str, float] = {}
    for name in ("power_law",) + SEARCH_NAMES:
        key = "power_law_weight" if name == "power_law" else f"{name}_weight"
        weight_params[key] = float(getattr(stage2b.weights, name))
    trial = {**SDCA_SHAPE_DEFAULTS, **weight_params, **params_from_shape(curve_result.best.shape)}
    print(f"  frozen trial: {trial}\n")

    print("--- curve_simulator evaluator ---")
    result_cs = run_sdca_walk_forward(
        dates, prices, [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/onchain_mvrv_rhodl",
        extra_z=extra_z,
    )
    print_wf_row("curve_simulator", result_cs)
    print()

    print("--- nautilus evaluator ---")
    result_nt = run_sdca_walk_forward(
        dates, prices, [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_nautilus,
        evaluator_label="nautilus/onchain_mvrv_rhodl",
        extra_z=extra_z,
    )
    print_wf_row("nautilus", result_nt)
    print()

    print("=== Summary vs RESEARCH_STATE.md baseline (+84.90% cs / +84.78% nt OOS) ===")
    print(
        f"  onchain_mvrv_rhodl (curve_sim): OOS {result_cs.mean_oos_vs_flat_dca_pct:.2f}%  "
        f"beats_oos={result_cs.beats_flat_dca_oos}  sensitivity_stable={result_cs.sensitivity.stable}"
    )
    print(
        f"  onchain_mvrv_rhodl (nautilus):  OOS {result_nt.mean_oos_vs_flat_dca_pct:.2f}%  "
        f"beats_oos={result_nt.beats_flat_dca_oos}  sensitivity_stable={result_nt.sensitivity.stable}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
