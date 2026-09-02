"""Stage A: choose composite weights by in-sample backtest, not cycle overlap.

Cycle-window overlap (``stage_a.optimize_stage_a_weights``) is kept as a
diagnostic. Keep/drop of extras is ``vs_flat_dca_pct`` on walk-forward
*in-sample* folds with a frozen curve; OOS is reported and must not pick
the winner. Rails are fit once per fold (independent of weights) so a
full extra grid does not re-run QuantReg per trial.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
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


class OscillatorPeriodScore(BaseModel):
    """One period-candidate's walk-forward IS/OOS score for a single indicator."""

    model_config = ConfigDict(frozen=True, strict=True)

    params: dict[str, int]
    mean_is_vs_flat_dca_pct: float
    mean_oos_vs_flat_dca_pct: float
    fold_scores: list[FoldScore]


class OscillatorPeriodSearchResult(BaseModel):
    """Ranked oscillator sub-parameter search for one indicator, IS-ranked only."""

    model_config = ConfigDict(frozen=True, strict=True)

    indicator_name: str
    best: OscillatorPeriodScore
    all_scores: list[OscillatorPeriodScore]
    num_evaluations: int = Field(ge=0)


def search_oscillator_periods_by_backtest(
    dates: Sequence[date],
    prices: Sequence[float],
    *,
    indicator_name: str,
    param_candidates: Sequence[Mapping[str, int]],
    compute_indicator_z: Callable[[Mapping[str, int]], Sequence[float | None]],
    base_extra_z: Mapping[str, Sequence[float | None]],
    base_weights: SdcaCompositeWeights,
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    shape: SdcaCurveShape,
    probe_weight: float = 1.0,
    objective: SdcaOptimizeObjective | None = None,
    n_folds: int = 3,
    holdout_frac: float = 0.2,
    oos_frac: float = 0.25,
) -> OscillatorPeriodSearchResult:
    """Search an oscillator's sub-parameters (e.g. RSI period) by IS backtest.

    Reuses the Stage A walk-forward fold/evaluator/rank machinery, but grids
    over one indicator's *construction* parameters instead of composite
    weights: ``base_weights`` is held fixed except ``indicator_name``, which
    is forced to ``probe_weight`` so each candidate's marginal contribution
    is isolated (AGENTS.md "one evaluator per question" / "pull one research
    candidate at a time"). OOS is reported per candidate, never used to pick
    the winner — same discipline as ``optimize_stage_a_by_backtest``.

    ``compute_indicator_z`` builds one full-calendar z series per candidate
    param set, e.g.::

        lambda p: rsi_confluence_z(
            dates, prices, weekly_length=p["weekly_length"], daily_length=p["daily_length"]
        ).to_list()

    The same shape works for a future MACD or SMA-band window search — swap
    the closure and ``indicator_name``, everything else is unchanged.
    """
    if not param_candidates:
        raise ValueError("param_candidates must not be empty")
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

    probe_payload = base_weights.model_dump()
    probe_payload[indicator_name] = probe_weight
    probe_weights = SdcaCompositeWeights(**probe_payload)

    scores: list[OscillatorPeriodScore] = []
    for params in param_candidates:
        z_series = compute_indicator_z(params)
        if len(z_series) != len(date_list):
            raise ValueError(
                f"compute_indicator_z({params!r}) returned {len(z_series)} values, "
                f"expected {len(date_list)}"
            )
        extra_z = {**base_extra_z, indicator_name: z_series}
        fold_scores = _score_weights_on_cached_folds(
            probe_weights,
            date_list,
            price_list,
            folds,
            models,
            evaluator,
            shape,
            extra_z,
            obj,
        )
        scores.append(
            OscillatorPeriodScore(
                params=dict(params),
                mean_is_vs_flat_dca_pct=_mean_is(fold_scores),
                mean_oos_vs_flat_dca_pct=_mean_oos(fold_scores),
                fold_scores=fold_scores,
            )
        )
    best = max(scores, key=lambda s: s.mean_is_vs_flat_dca_pct)
    return OscillatorPeriodSearchResult(
        indicator_name=indicator_name,
        best=best,
        all_scores=scores,
        num_evaluations=len(scores),
    )


__all__ = [
    "OscillatorPeriodScore",
    "OscillatorPeriodSearchResult",
    "StageABacktestResult",
    "optimize_stage_a_by_backtest",
    "search_names_with_data",
    "search_oscillator_periods_by_backtest",
]
