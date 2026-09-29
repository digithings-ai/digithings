#!/usr/bin/env python3
"""Gated macro drop-one (follow-up to the buy-zone occupancy finding).

Diagnosis: our index spends only 2.2% of days at risk<25 vs production's
~16% buy-zone occupancy, because macro votes (m2/dxy) vetoed 84% (592/706)
of power-law-cheap (z>+1.5) days -- e.g. Feb-2016 pl=+2.0 held at risk~42
by m2=-1.7. Production has no macro votes. This script gates three weight
variants (minus m2, minus dxy, minus both) with the FIXED cycle-4 shape
through the standard walk-forward protocol (per-fold rail refit,
duration-weighted OOS vs flat DCA), plus the unmodified live-weights
control (expect +43.21%, reproduction check).

No search, no settings writes. Sidecar: `.scratch/macro_dropone.json`.

Usage:
    uv run python scripts/run_macro_dropone_gate.py
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import run_aggregate_reweight_full17_fixed_index as reweight

from digiquant.strategies.sdca.curve_optimize import published_indicator_weights
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    btc_power_law_rails_fitter,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.two_stage import freeze_weight_params
from digiquant.strategies.sdca.walk_forward import shape_from_params

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
CYCLE4_PATH = DIGIQUANT_ROOT / ".scratch" / "periodic_cycle_4.json"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "macro_dropone.json"

GATE_OSCILLATORS = SdcaOscillatorSpec()


def main() -> None:
    cycle4 = json.loads(CYCLE4_PATH.read_text())
    shape = shape_from_params(cycle4["candidate_curve_shape"])
    print(f"fixed shape: {shape.model_dump()}")

    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    _fdates, _plz, extra_z, _long_w, _medium_w = reweight.load_inputs()

    live = published_indicator_weights()
    variants = {
        "control_live": live,
        "drop_m2": SdcaCompositeWeights(**{**live.model_dump(), "m2": 0.0}),
        "drop_dxy": SdcaCompositeWeights(**{**live.model_dump(), "dxy": 0.0}),
        "drop_both_macro": SdcaCompositeWeights(**{**live.model_dump(), "m2": 0.0, "dxy": 0.0}),
    }

    evaluator = functools.partial(evaluate_sdca_trial_curve_sim, oscillators=GATE_OSCILLATORS)
    results = {}
    for name, weights in variants.items():
        trial: dict[str, float | int | str] = dict(freeze_weight_params(weights))
        trial.update({k: v for k, v in shape.model_dump().items() if v is not None})
        result = run_sdca_walk_forward(
            dates,
            prices,
            [trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluator,
            evaluator_label="curve_simulator",
            extra_z=extra_z,
            fold_weighting="duration",
        )
        oos = result.mean_oos_vs_flat_dca_pct_duration_weighted
        folds = [
            {
                "fold": fs.fold.fold,
                "oos_vs_flat_dca_pct": fs.out_of_sample.vs_flat_dca_pct,
                "max_drawdown_pct": fs.out_of_sample.max_drawdown_pct,
                "feasible": fs.feasible,
            }
            for fs in result.fold_scores
        ]
        sens = result.sensitivity
        results[name] = {
            "duration_oos_vs_flat_dca_pct": oos,
            "beats_flat_dca_oos": bool(oos > 0),
            "folds": folds,
            "sensitivity_stable": sens.stable,
            "sensitivity_max_abs_delta": sens.max_abs_delta_oos_pct,
            "sensitivity_worst_neighbor": sens.worst_neighbor_key,
        }
        print(
            f"{name}: OOS={oos:+.2f}% "
            f"folds={[round(f['oos_vs_flat_dca_pct'], 2) for f in folds]} "
            f"feasible={[f['feasible'] for f in folds]} "
            f"sens_stable={sens.stable} (max_delta={sens.max_abs_delta_oos_pct:.2f}, "
            f"worst={sens.worst_neighbor_key})"
        )

    OUT_PATH.write_text(json.dumps(results, indent=2))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
