"""Baseline-relative evaluation vs the naive risk50-linear curve (post-mortem follow-up).

Binary in/out-of-zone timing correctness isn't the bar Chris wants: a candidate
must beat a simple, non-optimized reference (buy below composite risk 50, sell
above, linear rate schedule) on both a single frozen index
(:func:`compare_to_baseline`) and under walk-forward OOS
(:func:`run_sdca_walk_forward_vs_baseline`).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict

from digiquant.strategies.sdca.curve_optimize import (
    CurveOptimizeGates,
    CurveTrialScore,
    params_from_shape,
    score_shape_on_index,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape, risk50_linear_reference_curve
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    SdcaWalkForwardResult,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.walk_forward import (
    RailsFitter,
    SdcaOptimizeObjective,
    SdcaTrialEvaluator,
)

__all__ = [
    "BaselineComparison",
    "WalkForwardBaselineComparison",
    "compare_to_baseline",
    "run_sdca_walk_forward_vs_baseline",
]


class BaselineComparison(BaseModel):
    """Candidate vs the risk50-linear baseline on one frozen index."""

    model_config = ConfigDict(frozen=True, strict=True)

    candidate: CurveTrialScore
    baseline: CurveTrialScore
    beats_baseline: bool


class WalkForwardBaselineComparison(BaseModel):
    """Candidate vs the risk50-linear baseline under identical walk-forward folds."""

    model_config = ConfigDict(frozen=True, strict=True)

    candidate: SdcaWalkForwardResult
    baseline: SdcaWalkForwardResult
    delta_mean_oos_vs_flat_dca_pct: float
    beats_baseline_oos: bool


def compare_to_baseline(
    dates: pl.Series,
    prices: pl.Series,
    risk: pl.Series,
    candidate_shape: SdcaCurveShape,
    initial_cash: float,
    *,
    baseline_max_rate: float | None = None,
    gates: CurveOptimizeGates | None = None,
) -> BaselineComparison:
    """Score ``candidate_shape`` against the naive risk50-linear baseline.

    Both are scored on the *same* frozen index via
    :func:`score_shape_on_index` (reused unchanged, no new objective).
    ``beats_baseline`` requires the candidate to beat the baseline on both
    ``total_return_pct`` and ``risk_adjusted_return`` -- matching
    ``search_curve``'s existing beat-baseline convention.
    """
    max_rate = baseline_max_rate if baseline_max_rate is not None else candidate_shape.buy_max_rate
    baseline_shape = risk50_linear_reference_curve(max_rate)
    candidate_score = score_shape_on_index(
        dates, prices, risk, candidate_shape, initial_cash, gates=gates
    )
    baseline_score = score_shape_on_index(
        dates, prices, risk, baseline_shape, initial_cash, gates=gates
    )
    beats_baseline = (
        candidate_score.total_return_pct > baseline_score.total_return_pct + 1e-9
        and candidate_score.risk_adjusted_return > baseline_score.risk_adjusted_return + 1e-9
    )
    return BaselineComparison(
        candidate=candidate_score, baseline=baseline_score, beats_baseline=beats_baseline
    )


def run_sdca_walk_forward_vs_baseline(
    dates: list[date],
    prices: list[float],
    candidate_params: dict[str, float | int | str],
    *,
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    evaluator_label: str,
    objective: SdcaOptimizeObjective | None = None,
    n_folds: int = 3,
    holdout_frac: float = 0.2,
    oos_frac: float = 0.25,
    sensitivity_frac: float = 0.05,
    extra_z: dict[str, list[float | None]] | None = None,
    fold_weighting: Literal["unweighted", "duration"] = "unweighted",
    baseline_max_rate: float | None = None,
) -> WalkForwardBaselineComparison:
    """Run ``candidate_params`` and the risk50-linear baseline through identical folds.

    The baseline keeps every one of the candidate's indicator weights (and
    any other non-shape param) -- only the six curve-shape fields are
    replaced by :func:`risk50_linear_reference_curve`'s linear ramp. Both
    calls share ``dates``/``n_folds``/``holdout_frac``/``oos_frac``, so
    :func:`make_walk_forward_folds` (invoked identically inside each
    ``run_sdca_walk_forward`` call) produces the same folds and holdout for
    both -- this is what makes the comparison apples-to-apples.
    """
    merged_candidate = {**SDCA_SHAPE_DEFAULTS, **candidate_params}
    max_rate = (
        baseline_max_rate
        if baseline_max_rate is not None
        else float(merged_candidate["buy_max_rate"])
    )
    baseline_shape = risk50_linear_reference_curve(max_rate)
    baseline_params = {**merged_candidate, **params_from_shape(baseline_shape)}

    shared_kwargs = {
        "rails_fitter": rails_fitter,
        "evaluator": evaluator,
        "evaluator_label": evaluator_label,
        "objective": objective,
        "n_folds": n_folds,
        "holdout_frac": holdout_frac,
        "oos_frac": oos_frac,
        "sensitivity_frac": sensitivity_frac,
        "extra_z": extra_z,
        "fold_weighting": fold_weighting,
    }
    candidate_result = run_sdca_walk_forward(dates, prices, [candidate_params], **shared_kwargs)
    baseline_result = run_sdca_walk_forward(dates, prices, [baseline_params], **shared_kwargs)
    delta = candidate_result.mean_oos_vs_flat_dca_pct - baseline_result.mean_oos_vs_flat_dca_pct
    return WalkForwardBaselineComparison(
        candidate=candidate_result,
        baseline=baseline_result,
        delta_mean_oos_vs_flat_dca_pct=delta,
        beats_baseline_oos=delta > 1e-9,
    )
