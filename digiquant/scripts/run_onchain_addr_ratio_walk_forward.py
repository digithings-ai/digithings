#!/usr/bin/env python3
"""Stage 4 of the Phase B indicator-addition playbook: OOS walk-forward gate
for the ``onchain_addr_ratio`` candidate.

Frozen candidate (nothing re-searched here):
  - weights: Stage 2 winner (run_onchain_addr_ratio_expanded_reweight.py) --
    power_law + m2 + dxy + all 4 Bitview on-chain ratios + the new CoinMetrics
    onchain_addr_ratio.
  - curve shape: Stage 3 winner (run_onchain_addr_ratio_curve_search.py),
    which beat the published baseline shape on the same frozen index
    (total_return_pct +6.3%, risk_adjusted_return +6.4%).

``load_sdca_extra_z`` -- like ``load_frozen_index`` in Stage 3 -- only
accepts one shared ``window`` across every onchain ratio indicator
(``onchain_mvrv``/``onchain_asopr``/``onchain_puell``/``onchain_rhodl``/
``onchain_addr_ratio``), but Stage 1 found each series wants a different
window (1095/1095/1095/730/365 days). This script applies the same manual
override already proven in Stage 3: call ``load_sdca_extra_z`` for the
extras that don't need per-indicator windows (m2, dxy), then overwrite the 5
onchain-ratio entries with manually-computed z-series at their Stage-1
windows before handing ``extra_z`` to ``run_sdca_walk_forward``.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md. Report
the full IS/OOS table + sensitivity check to Chris for explicit accept
first, per the standing playbook gate.

Usage:
    uv run python scripts/run_onchain_addr_ratio_walk_forward.py
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import (
    onchain_addr_ratio_z,
    onchain_asopr_z,
    onchain_mvrv_z,
    onchain_puell_z,
    onchain_rhodl_z,
)
from digiquant.strategies.sdca.nautilus_evaluator import evaluate_sdca_trial_nautilus
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Stage 2 winner (run_onchain_addr_ratio_expanded_reweight.py).
FROZEN_WEIGHT_PARAMS = {
    "power_law_weight": 0.325,
    "m2_weight": 0.1,
    "dxy_weight": 0.1,
    "onchain_mvrv_weight": 1.0,
    "onchain_asopr_weight": 0.1,
    "onchain_puell_weight": 0.1,
    "onchain_rhodl_weight": 1.0,
    "onchain_addr_ratio_weight": 1.0,
}

# Stage 1 winning windows (run_onchain_solo_search.py, run_onchain_addr_ratio_solo_search.py).
ONCHAIN_WINDOWS = {
    "onchain_mvrv": 1095,
    "onchain_asopr": 1095,
    "onchain_puell": 1095,
    "onchain_rhodl": 730,
    "onchain_addr_ratio": 365,
}

ONCHAIN_Z_FNS = {
    "onchain_mvrv": onchain_mvrv_z,
    "onchain_asopr": onchain_asopr_z,
    "onchain_puell": onchain_puell_z,
    "onchain_rhodl": onchain_rhodl_z,
}

# Wide-knee curve winner from run_onchain_addr_ratio_curve_search.py.
FROZEN_SHAPE_PARAMS = {
    "buy_max_rate": 37.5087,
    "buy_knee_risk": 30.4901,
    "sell_knee_risk": 58.6791,
    "sell_max_rate": 13.2248,
    "buy_curvature": 3.1084,
    "sell_curvature": 5.9465,
}


def build_extra_z(dates: list, prices: list, cache_dir: Path) -> dict:
    # m2/dxy don't need per-indicator window overrides in this mix; reuse the
    # standard loader for those, then overwrite the 5 onchain ratio series
    # with their Stage-1-winning windows.
    extra_z: dict = load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(cache_dir))
    sources = load_sdca_extra_sources(cache_dir)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    for name, z_fn in ONCHAIN_Z_FNS.items():
        src_dates = getattr(sources, f"{name}_dates")
        src_values = getattr(sources, f"{name}_values")
        if src_dates is None:
            raise SystemExit(f"no {name} source found -- expected all 4 on-chain series present")
        extra_z[name] = z_fn(date_s, src_dates, src_values, window=ONCHAIN_WINDOWS[name]).to_list()
    if sources.onchain_addr_ratio_dates is None:
        raise SystemExit("no onchain_addr_ratio source found")
    extra_z["onchain_addr_ratio"] = onchain_addr_ratio_z(
        date_s, price_s, sources.onchain_addr_ratio_dates, sources.onchain_addr_ratio_values,
        window=ONCHAIN_WINDOWS["onchain_addr_ratio"],
    ).to_list()
    return extra_z


def print_wf_row(label: str, result) -> None:
    holdout = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics else float("nan")
    print(
        f"{label:>40} | IS {result.mean_is_vs_flat_dca_pct:7.2f} | OOS {result.mean_oos_vs_flat_dca_pct:7.2f} "
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
    print(f"    sensitivity: stable={result.sensitivity.stable}  max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp")


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    extra_z = build_extra_z(dates, prices, cache_dir)
    trial = {**SDCA_SHAPE_DEFAULTS, **FROZEN_SHAPE_PARAMS, **FROZEN_WEIGHT_PARAMS}

    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"frozen weights: {FROZEN_WEIGHT_PARAMS}")
    print(f"frozen onchain windows: {ONCHAIN_WINDOWS}")
    print(f"frozen curve shape: {FROZEN_SHAPE_PARAMS}\n")

    print("=== curve_simulator evaluator (3-fold walk-forward, single frozen candidate) ===")
    result_cs = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/onchain_addr_ratio",
        extra_z=extra_z,
    )
    print_wf_row("curve_simulator", result_cs)
    print()

    print("=== nautilus evaluator (3-fold walk-forward, single frozen candidate) ===")
    result_nt = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_nautilus,
        evaluator_label="nautilus/onchain_addr_ratio",
        extra_z=extra_z,
    )
    print_wf_row("nautilus", result_nt)
    print()

    print("=== Summary (mean_OOS / holdout, vs-flat-DCA %) ===")
    print(
        f"{'RESEARCH_STATE.md current baseline':>40} | OOS  84.90 (curve_simulator) / 84.78 (nautilus) "
        f"| holdout n/a here (power_law/m2/dxy only, see RESEARCH_STATE.md)"
    )
    cs_holdout = result_cs.holdout_metrics.vs_flat_dca_pct if result_cs.holdout_metrics else float("nan")
    nt_holdout = result_nt.holdout_metrics.vs_flat_dca_pct if result_nt.holdout_metrics else float("nan")
    print(
        f"{'onchain_addr_ratio (curve_sim)':>40} | OOS {result_cs.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {cs_holdout:6.2f}"
    )
    print(
        f"{'onchain_addr_ratio (nautilus)':>40} | OOS {result_nt.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {nt_holdout:6.2f}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
