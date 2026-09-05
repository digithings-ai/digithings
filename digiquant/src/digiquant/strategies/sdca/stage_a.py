"""Stage A: choose composite weights so risk bottoms/tops overlap cycle windows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from itertools import product

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.composite_risk import IndicatorWeight, compute_composite_risk
from digiquant.strategies.sdca.cycle_windows import CycleKind, SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import EXTRA_INDICATOR_NAMES, SdcaCompositeWeights

ACCUMULATE_RISK_MAX = 35.0
DISTRIBUTE_RISK_MIN = 80.0
_BAND_BONUS = 25.0


class CycleOverlapScore(BaseModel):
    """How well composite risk lines up with cycle troughs (buy) and peaks (sell)."""

    model_config = ConfigDict(frozen=True, strict=True)

    spread: float = Field(description="mean risk in peaks minus mean risk in troughs")
    trough_in_accumulate_frac: float = Field(ge=0.0, le=1.0)
    peak_in_distribute_frac: float = Field(ge=0.0, le=1.0)
    mean_trough_risk: float
    mean_peak_risk: float
    objective: float
    trough_days: int = Field(ge=0)
    peak_days: int = Field(ge=0)


class StageAResult(BaseModel):
    """Winning Stage A weights plus the overlap score that selected them."""

    model_config = ConfigDict(frozen=True, strict=True)

    weights: SdcaCompositeWeights
    score: CycleOverlapScore
    num_evaluations: int = Field(ge=0)


class CombinedCycleOverlapScore(BaseModel):
    """Long-term + medium-term overlap, blended into one dual-timeframe objective.

    Chris's design: one composite that never misses the long-term value
    areas and covers as many medium-term ones as it can, with long-term
    weighted more heavily. A plain unweighted sum would do the opposite by
    default — the medium-term window set is far denser (757+748 trough/peak
    days vs long-term's 182+273) and would dominate on raw volume alone.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    long: CycleOverlapScore
    medium: CycleOverlapScore
    long_weight: float = Field(gt=0.0)
    medium_weight: float = Field(gt=0.0)
    objective: float


class CombinedStageAResult(BaseModel):
    """Winning weights plus the combined long+medium score that selected them."""

    model_config = ConfigDict(frozen=True, strict=True)

    weights: SdcaCompositeWeights
    score: CombinedCycleOverlapScore
    num_evaluations: int = Field(ge=0)


def _weight_complexity(weights: SdcaCompositeWeights) -> tuple[int, float]:
    """Tie-break: fewer enabled extras, then higher power-law weight."""
    return (len(weights.enabled_extras()), -weights.power_law)


def _is_better(
    score: CycleOverlapScore,
    weights: SdcaCompositeWeights,
    incumbent: StageAResult | None,
) -> bool:
    if incumbent is None:
        return True
    if score.objective > incumbent.score.objective:
        return True
    if score.objective < incumbent.score.objective:
        return False
    return _weight_complexity(weights) < _weight_complexity(incumbent.weights)


def cycle_overlap_score(
    dates: Sequence[date],
    risk: Sequence[float | None],
    windows: SdcaCycleWindows,
    *,
    accumulate_risk_max: float = ACCUMULATE_RISK_MAX,
    distribute_risk_min: float = DISTRIBUTE_RISK_MIN,
) -> CycleOverlapScore:
    """Higher is better: low risk at troughs, high risk at peaks."""
    if len(dates) != len(risk):
        raise ValueError("dates and risk must be the same length")
    trough_vals: list[float] = []
    peak_vals: list[float] = []
    for day, raw in zip(dates, risk, strict=True):
        if raw is None:
            continue
        kind = windows.kind_on(day)
        if kind is CycleKind.TROUGH:
            trough_vals.append(float(raw))
        elif kind is CycleKind.PEAK:
            peak_vals.append(float(raw))
    if not trough_vals or not peak_vals:
        raise ValueError("cycle windows do not overlap the dated risk series")
    mean_trough = sum(trough_vals) / len(trough_vals)
    mean_peak = sum(peak_vals) / len(peak_vals)
    spread = mean_peak - mean_trough
    trough_frac = sum(v <= accumulate_risk_max for v in trough_vals) / len(trough_vals)
    peak_frac = sum(v >= distribute_risk_min for v in peak_vals) / len(peak_vals)
    return CycleOverlapScore(
        spread=spread,
        trough_in_accumulate_frac=trough_frac,
        peak_in_distribute_frac=peak_frac,
        mean_trough_risk=mean_trough,
        mean_peak_risk=mean_peak,
        objective=spread + _BAND_BONUS * (trough_frac + peak_frac),
        trough_days=len(trough_vals),
        peak_days=len(peak_vals),
    )


def risk_from_weighted_z(
    dates: Sequence[date],
    power_law_z: Sequence[float | None],
    extra_z: Mapping[str, Sequence[float | None]],
    weights: SdcaCompositeWeights,
) -> list[float | None]:
    """Blend power-law + extras the same way ``compute_composite_risk`` does."""
    if len(dates) != len(power_law_z):
        raise ValueError("dates and power_law_z must be the same length")
    indicators: list[IndicatorWeight] = []
    if weights.power_law > 0.0:
        indicators.append(
            IndicatorWeight(
                name="power_law",
                z=pl.Series(list(power_law_z), dtype=pl.Float64),
                weight=weights.power_law,
            )
        )
    for name, weight in weights.enabled_extras().items():
        series = extra_z.get(name)
        if series is None:
            raise ValueError(f"positive weight for {name!r} but no extra_z series")
        if len(series) != len(dates):
            raise ValueError(f"extra_z[{name!r}] length {len(series)} != dates length {len(dates)}")
        indicators.append(
            IndicatorWeight(name=name, z=pl.Series(list(series), dtype=pl.Float64), weight=weight)
        )
    return compute_composite_risk(indicators)["risk"].to_list()


def optimize_stage_a_weights(
    dates: Sequence[date],
    *,
    power_law_z: Sequence[float | None],
    extra_z: Mapping[str, Sequence[float | None]],
    windows: SdcaCycleWindows,
    search_names: Sequence[str] = EXTRA_INDICATOR_NAMES,
    grid: Sequence[float] = (0.0, 0.5, 1.0),
    power_law_grid: Sequence[float] = (0.0, 0.5, 1.0),
    require_extras: bool = False,
) -> StageAResult:
    """Grid-search extra weights so composite troughs/peaks overlap ``windows``.

    ``require_extras=True`` skips power-law-only (and other zero-extra) rows so
    the published composite is actually a blend, not a re-discovery of
    power-law-only risk.
    """
    best: StageAResult | None = None
    evaluated = 0
    names = tuple(search_names)
    for val in power_law_grid:
        for combo in product(grid, repeat=len(names)):
            payload = {name: float(weight) for name, weight in zip(names, combo, strict=True)}
            try:
                weights = SdcaCompositeWeights(power_law=float(val), **payload)
            except ValueError:
                continue
            if require_extras and not weights.enabled_extras():
                continue
            if any(name not in extra_z for name in weights.enabled_extras()):
                continue
            evaluated += 1
            try:
                risk = risk_from_weighted_z(dates, power_law_z, extra_z, weights)
                score = cycle_overlap_score(dates, risk, windows)
            except ValueError:
                # Warmup / missing extra z can leave windows all-null; skip that combo.
                continue
            if _is_better(score, weights, best):
                best = StageAResult(weights=weights, score=score, num_evaluations=evaluated)
    if best is None:
        raise ValueError("no valid Stage A weight combinations to evaluate")
    return StageAResult(
        weights=best.weights,
        score=best.score,
        num_evaluations=evaluated,
    )


def combined_cycle_overlap_score(
    dates: Sequence[date],
    risk: Sequence[float | None],
    long_windows: SdcaCycleWindows,
    medium_windows: SdcaCycleWindows,
    *,
    long_weight: float = 3.0,
    medium_weight: float = 1.0,
    accumulate_risk_max: float = ACCUMULATE_RISK_MAX,
    distribute_risk_min: float = DISTRIBUTE_RISK_MIN,
) -> CombinedCycleOverlapScore:
    """Score one risk series against both timeframes at once.

    ``long_weight``/``medium_weight`` (default 3:1) set how much each
    timeframe's overlap counts toward the blended objective — heavier
    long-term weighting is the mechanism for "never miss the long-term value
    areas," not a hard gate: a candidate that is weak on long-term overlap
    always pays for it in the combined objective, but there is no
    disqualification, so a grid search always has a feasible winner. The
    ratio is a named constant, not hard-coded, so a sensitivity sweep
    (e.g. 2:1/3:1/5:1) can show how the winning weight mix shifts before any
    one ratio is treated as final (see
    ``scripts/run_dual_timeframe_composite_search.py``).
    """
    if long_weight <= 0.0 or medium_weight <= 0.0:
        raise ValueError("long_weight and medium_weight must be positive")
    long_score = cycle_overlap_score(
        dates,
        risk,
        long_windows,
        accumulate_risk_max=accumulate_risk_max,
        distribute_risk_min=distribute_risk_min,
    )
    medium_score = cycle_overlap_score(
        dates,
        risk,
        medium_windows,
        accumulate_risk_max=accumulate_risk_max,
        distribute_risk_min=distribute_risk_min,
    )
    return CombinedCycleOverlapScore(
        long=long_score,
        medium=medium_score,
        long_weight=long_weight,
        medium_weight=medium_weight,
        objective=long_weight * long_score.objective + medium_weight * medium_score.objective,
    )


def _floor_candidates(candidates: Sequence[float], floor: float | None) -> tuple[float, ...]:
    """Grid values for one indicator, with ``0.0`` replaced by ``floor`` when set.

    This is the diversification mechanism for the aggregate-reweight stage:
    when ``floor`` is set, ``0.0`` is never a legal candidate, so a
    once-enabled indicator can be down-weighted but never zeroed back out of
    the composite — including ``power_law`` itself, the explicit hedge
    against that model degrading later.
    """
    if floor is None:
        return tuple(candidates)
    kept = sorted({c for c in candidates if c > 0.0} | {floor})
    return tuple(kept) if kept else (floor,)


def optimize_stage_a_weights_combined(
    dates: Sequence[date],
    *,
    power_law_z: Sequence[float | None],
    extra_z: Mapping[str, Sequence[float | None]],
    long_windows: SdcaCycleWindows,
    medium_windows: SdcaCycleWindows,
    search_names: Sequence[str] = EXTRA_INDICATOR_NAMES,
    grid: Sequence[float] = (0.0, 0.5, 1.0),
    power_law_grid: Sequence[float] = (0.0, 0.5, 1.0),
    long_weight: float = 3.0,
    medium_weight: float = 1.0,
    min_weight_floor: float | None = None,
) -> CombinedStageAResult:
    """Grid-search composite weights against the combined long+medium objective.

    Same grid-search shape as ``optimize_stage_a_weights``, scored via
    ``combined_cycle_overlap_score`` against both window sets at once instead
    of one. ``min_weight_floor`` (see ``_floor_candidates``) is the
    aggregate-reweight stage's diversification floor — pass it only once
    every indicator in ``search_names`` (plus ``power_law``, via
    ``power_law_grid``) has already survived individual optimization; an
    indicator that scored no better than noise on its own belongs excluded
    from ``search_names`` entirely, not floored here.

    No parsimony tie-break: the floor already prevents collapse to fewer
    indicators, so ties keep whichever candidate the grid reaches first.
    """
    names = tuple(search_names)
    extra_grid = _floor_candidates(grid, min_weight_floor)
    pl_grid = _floor_candidates(power_law_grid, min_weight_floor)

    best: CombinedStageAResult | None = None
    evaluated = 0
    for val in pl_grid:
        for combo in product(extra_grid, repeat=len(names)):
            payload = {name: float(weight) for name, weight in zip(names, combo, strict=True)}
            try:
                weights = SdcaCompositeWeights(power_law=float(val), **payload)
            except ValueError:
                continue
            if any(name not in extra_z for name in weights.enabled_extras()):
                continue
            evaluated += 1
            try:
                risk = risk_from_weighted_z(dates, power_law_z, extra_z, weights)
                score = combined_cycle_overlap_score(
                    dates,
                    risk,
                    long_windows,
                    medium_windows,
                    long_weight=long_weight,
                    medium_weight=medium_weight,
                )
            except ValueError:
                # Warmup / missing extra z can leave windows all-null; skip that combo.
                continue
            if best is None or score.objective > best.score.objective:
                best = CombinedStageAResult(weights=weights, score=score, num_evaluations=evaluated)
    if best is None:
        raise ValueError("no valid combined Stage A weight combinations to evaluate")
    return CombinedStageAResult(
        weights=best.weights,
        score=best.score,
        num_evaluations=evaluated,
    )


def optimize_stage_a_weights_combined_multi_ratio(
    dates: Sequence[date],
    *,
    power_law_z: Sequence[float | None],
    extra_z: Mapping[str, Sequence[float | None]],
    long_windows: SdcaCycleWindows,
    medium_windows: SdcaCycleWindows,
    search_names: Sequence[str] = EXTRA_INDICATOR_NAMES,
    grid: Sequence[float] = (0.0, 0.5, 1.0),
    power_law_grid: Sequence[float] = (0.0, 0.5, 1.0),
    ratios: Sequence[tuple[float, float]] = ((3.0, 1.0),),
    min_weight_floor: float | None = None,
) -> dict[tuple[float, float], CombinedStageAResult]:
    """Like ``optimize_stage_a_weights_combined``, but scores every candidate
    under several long:medium ratios in one pass instead of one pass per
    ratio.

    Per candidate weight combo, computing its composite risk series and
    long/medium ``cycle_overlap_score``s is the expensive part of the search
    (a full grid over 8 search names is ~262k combinations); combining those
    two already-computed scores into a ``CombinedCycleOverlapScore`` for a
    given ratio is a cheap scalar multiply-and-add. So a ratio-sensitivity
    sweep over N ratios costs the same as a single-ratio search, not N of
    them -- this is what a full grid search's Stage 5 (surviving-7) got away
    with by just re-running per ratio (cheap enough not to matter there),
    but doesn't scale to the all-9 search's larger grid.
    """
    if not ratios:
        raise ValueError("ratios must be non-empty")
    for lw, mw in ratios:
        if lw <= 0.0 or mw <= 0.0:
            raise ValueError("every ratio's long_weight and medium_weight must be positive")

    names = tuple(search_names)
    extra_grid = _floor_candidates(grid, min_weight_floor)
    pl_grid = _floor_candidates(power_law_grid, min_weight_floor)

    best: dict[tuple[float, float], CombinedStageAResult] = {}
    evaluated = 0
    for val in pl_grid:
        for combo in product(extra_grid, repeat=len(names)):
            payload = {name: float(weight) for name, weight in zip(names, combo, strict=True)}
            try:
                weights = SdcaCompositeWeights(power_law=float(val), **payload)
            except ValueError:
                continue
            if any(name not in extra_z for name in weights.enabled_extras()):
                continue
            evaluated += 1
            try:
                risk = risk_from_weighted_z(dates, power_law_z, extra_z, weights)
                long_score = cycle_overlap_score(dates, risk, long_windows)
                medium_score = cycle_overlap_score(dates, risk, medium_windows)
            except ValueError:
                # Warmup / missing extra z can leave windows all-null; skip that combo.
                continue
            for lw, mw in ratios:
                score = CombinedCycleOverlapScore(
                    long=long_score,
                    medium=medium_score,
                    long_weight=lw,
                    medium_weight=mw,
                    objective=lw * long_score.objective + mw * medium_score.objective,
                )
                incumbent = best.get((lw, mw))
                if incumbent is None or score.objective > incumbent.score.objective:
                    best[(lw, mw)] = CombinedStageAResult(
                        weights=weights, score=score, num_evaluations=evaluated
                    )
    if not best:
        raise ValueError("no valid combined Stage A weight combinations to evaluate")
    return best


__all__ = [
    "ACCUMULATE_RISK_MAX",
    "DISTRIBUTE_RISK_MIN",
    "CombinedCycleOverlapScore",
    "CombinedStageAResult",
    "CycleOverlapScore",
    "StageAResult",
    "combined_cycle_overlap_score",
    "cycle_overlap_score",
    "optimize_stage_a_weights",
    "optimize_stage_a_weights_combined",
    "optimize_stage_a_weights_combined_multi_ratio",
    "risk_from_weighted_z",
]
