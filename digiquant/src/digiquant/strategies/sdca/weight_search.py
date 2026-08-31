"""Stage A: choose composite weights by in-sample backtest, not cycle overlap.

Cycle-window overlap (``stage_a.optimize_stage_a_weights``) is kept as a
diagnostic. Keep/drop of extras is ``vs_flat_dca_pct`` on walk-forward
*in-sample* folds with a frozen curve; OOS is reported and must not pick
the winner. Rails are fit once per fold (independent of weights) so a
full extra grid does not re-run QuantReg per trial.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from itertools import product

from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    SdcaCompositeWeights,
    extra_indicators_for_window,
    missing_extra_names,
)
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.walk_forward import (
    FoldScore,
    RailsFitter,
    SdcaOptimizeObjective,
    SdcaTrialEvaluator,
    WalkForwardFold,
    is_feasible,
    make_walk_forward_folds,
    window_slice,
)


class StageABacktestResult(BaseModel):
    """Winning extra weights selected on in-sample vs-flat-DCA."""

    model_config = ConfigDict(frozen=True, strict=True)

    weights: SdcaCompositeWeights
    mean_is_vs_flat_dca_pct: float
    mean_oos_vs_flat_dca_pct: float
    num_evaluations: int = Field(ge=0)
    search_names: tuple[str, ...]
    fold_scores: list[FoldScore]


def search_names_with_data(
    allowlist: Sequence[str],
    extra_z: Mapping[str, Sequence[float | None]],
) -> tuple[str, ...]:
    """Allowlisted extras that have a precomputed z series (order preserved)."""
    have = set(extra_z)
    return tuple(name for name in allowlist if name in have)


def _weight_complexity(weights: SdcaCompositeWeights) -> tuple[int, float]:
    """Tie-break: fewer enabled extras, then higher valuation weight."""
    return (len(weights.enabled_extras()), -weights.valuation)


def _is_better(
    rank: float,
    weights: SdcaCompositeWeights,
    best_rank: float,
    best_weights: SdcaCompositeWeights | None,
) -> bool:
    if best_weights is None:
        return True
    if rank > best_rank:
        return True
    if rank < best_rank:
        return False
    return _weight_complexity(weights) < _weight_complexity(best_weights)


def _mean_is(scores: Sequence[FoldScore]) -> float:
    if not scores:
        return float("-inf")
    return sum(s.in_sample.vs_flat_dca_pct for s in scores) / len(scores)


def _mean_oos(scores: Sequence[FoldScore]) -> float:
    if not scores:
        return float("-inf")
    return sum(s.out_of_sample.vs_flat_dca_pct for s in scores) / len(scores)


def _is_rank_score(scores: Sequence[FoldScore], objective: SdcaOptimizeObjective) -> float:
    """Mean IS vs-flat-DCA across folds. OOS is not used.

    Stage B's drawdown cap and an all-folds capital floor are not applied
    here. Early expanding IS windows can sit in the sell zone with an
    all-cash book even when later folds trade; requiring every fold to
    clear 10% deployed dropped the whole extra grid.
    """
    if not scores:
        return float("-inf")
    return sum(s.in_sample.vs_flat_dca_pct for s in scores) / len(scores)


def _score_weights_on_cached_folds(
    weights: SdcaCompositeWeights,
    dates: Sequence[date],
    prices: Sequence[float],
    folds: Sequence[WalkForwardFold],
    models: Sequence[RiskModel],
    evaluator: SdcaTrialEvaluator,
    shape: SdcaCurveShape,
    extra_z: Mapping[str, Sequence[float | None]],
    objective: SdcaOptimizeObjective,
) -> list[FoldScore]:
    zmap = extra_z
    scores: list[FoldScore] = []
    for fold, model in zip(folds, models, strict=True):
        is_dates, is_prices = window_slice(dates, prices, fold.is_start, fold.is_end)
        oos_dates, oos_prices = window_slice(dates, prices, fold.oos_start, fold.oos_end)
        extras_is = extra_indicators_for_window(is_dates, dates, zmap, weights)
        extras_oos = extra_indicators_for_window(oos_dates, dates, zmap, weights)
        in_sample = evaluator(is_dates, is_prices, model, shape, weights.valuation, extras_is)
        out_of_sample = evaluator(
            oos_dates, oos_prices, model, shape, weights.valuation, extras_oos
        )
        scores.append(
            FoldScore(
                fold=fold,
                in_sample=in_sample,
                out_of_sample=out_of_sample,
                feasible=in_sample.capital_deployed_pct >= objective.capital_deployed_floor_pct,
            )
        )
    return scores


def optimize_stage_a_by_backtest(
    dates: Sequence[date],
    prices: Sequence[float],
    *,
    extra_z: Mapping[str, Sequence[float | None]],
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    shape: SdcaCurveShape,
    search_names: Sequence[str] = EXTRA_INDICATOR_NAMES,
    grid: Sequence[float] = (0.0, 0.5, 1.0),
    valuation_grid: Sequence[float] = (0.0, 0.5, 1.0),
    objective: SdcaOptimizeObjective | None = None,
    n_folds: int = 3,
    holdout_frac: float = 0.2,
    oos_frac: float = 0.25,
) -> StageABacktestResult:
    """Grid-search extras; keep weights that raise in-sample vs-flat-DCA.

    Combinations that enable an extra with no ``extra_z`` series are skipped.
    Rails are fit once per fold on the IS window (#3173).
    """
    obj = objective or SdcaOptimizeObjective()
    names = search_names_with_data(search_names, extra_z)
    date_list = list(dates)
    price_list = list(prices)
    folds, _holdout = make_walk_forward_folds(
        date_list, n_folds=n_folds, holdout_frac=holdout_frac, oos_frac=oos_frac
    )
    models: list[RiskModel] = []
    for fold in folds:
        is_dates, is_prices = window_slice(date_list, price_list, fold.is_start, fold.is_end)
        models.append(rails_fitter(is_dates, is_prices))

    best_weights: SdcaCompositeWeights | None = None
    best_rank = float("-inf")
    best_scores: list[FoldScore] | None = None
    evaluated = 0
    for val in valuation_grid:
        for combo in product(grid, repeat=len(names)):
            payload = {name: float(weight) for name, weight in zip(names, combo, strict=True)}
            try:
                weights = SdcaCompositeWeights(valuation=float(val), **payload)
            except ValueError:
                continue
            if missing_extra_names(weights, extra_z):
                continue
            evaluated += 1
            scores = _score_weights_on_cached_folds(
                weights,
                date_list,
                price_list,
                folds,
                models,
                evaluator,
                shape,
                extra_z,
                obj,
            )
            rank = _is_rank_score(scores, obj)
            if rank == float("-inf"):
                continue
            if _is_better(rank, weights, best_rank, best_weights):
                best_weights = weights
                best_rank = rank
                best_scores = scores
    if best_weights is None or best_scores is None:
        raise ValueError("no valid Stage A backtest weight combinations to evaluate")
    return StageABacktestResult(
        weights=best_weights,
        mean_is_vs_flat_dca_pct=_mean_is(best_scores),
        mean_oos_vs_flat_dca_pct=_mean_oos(best_scores),
        num_evaluations=evaluated,
        search_names=names,
        fold_scores=list(best_scores),
    )


def optimize_stage_1_survivor_weights(
    dates: Sequence[date],
    prices: Sequence[float],
    *,
    extra_z: Mapping[str, Sequence[float | None]],
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    shape: SdcaCurveShape,
    survivor_names: Sequence[str],
    grid: Sequence[float] = (0.5, 1.0),
    objective: SdcaOptimizeObjective | None = None,
    n_folds: int = 3,
    holdout_frac: float = 0.2,
    oos_frac: float = 0.25,
) -> StageABacktestResult:
    """Weight search among Stage 0 survivors. Grid must be ``(0, 1]`` — no 0.

    Rank is mean **OOS** vs-flat-DCA on the same expanding folds, with Stage B
    capital/drawdown feasibility on every OOS window. Power-law-only skips
    the grid and returns the published valuation-only weights.
    """
    if any(float(g) <= 0.0 for g in grid):
        raise ValueError("Stage 1 grid must be (0, 1]; 0 would cheaply beat the incumbent")
    extras = tuple(name for name in survivor_names if name != "valuation")
    if not extras:
        return StageABacktestResult(
            weights=SdcaCompositeWeights(),
            mean_is_vs_flat_dca_pct=0.0,
            mean_oos_vs_flat_dca_pct=0.0,
            num_evaluations=0,
            search_names=(),
            fold_scores=[],
        )
    obj = objective or SdcaOptimizeObjective()
    date_list = list(dates)
    price_list = list(prices)
    folds, _holdout = make_walk_forward_folds(
        date_list, n_folds=n_folds, holdout_frac=holdout_frac, oos_frac=oos_frac
    )
    models: list[RiskModel] = []
    for fold in folds:
        is_dates, is_prices = window_slice(date_list, price_list, fold.is_start, fold.is_end)
        models.append(rails_fitter(is_dates, is_prices))

    best_weights: SdcaCompositeWeights | None = None
    best_rank = float("-inf")
    best_scores: list[FoldScore] | None = None
    evaluated = 0
    val_grid = grid if "valuation" in survivor_names else (1.0,)
    for val in val_grid:
        for combo in product(grid, repeat=len(extras)):
            payload = {name: float(weight) for name, weight in zip(extras, combo, strict=True)}
            try:
                weights = SdcaCompositeWeights(valuation=float(val), **payload)
            except ValueError:
                continue
            if missing_extra_names(weights, extra_z):
                continue
            evaluated += 1
            scores = _score_weights_on_cached_folds(
                weights,
                date_list,
                price_list,
                folds,
                models,
                evaluator,
                shape,
                extra_z,
                obj,
            )
            if not all(is_feasible(s.out_of_sample, obj) for s in scores):
                continue
            rank = _mean_oos(scores)
            if rank == float("-inf"):
                continue
            if _is_better(rank, weights, best_rank, best_weights):
                best_weights = weights
                best_rank = rank
                best_scores = scores
    if best_weights is None or best_scores is None:
        raise ValueError("no valid Stage 1 survivor weight combinations to evaluate")
    return StageABacktestResult(
        weights=best_weights,
        mean_is_vs_flat_dca_pct=_mean_is(best_scores),
        mean_oos_vs_flat_dca_pct=_mean_oos(best_scores),
        num_evaluations=evaluated,
        search_names=extras,
        fold_scores=list(best_scores),
    )


__all__ = [
    "StageABacktestResult",
    "optimize_stage_a_by_backtest",
    "optimize_stage_1_survivor_weights",
    "search_names_with_data",
]
