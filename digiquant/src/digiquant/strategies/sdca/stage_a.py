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


__all__ = [
    "ACCUMULATE_RISK_MAX",
    "DISTRIBUTE_RISK_MIN",
    "CycleOverlapScore",
    "StageAResult",
    "cycle_overlap_score",
    "optimize_stage_a_weights",
    "risk_from_weighted_z",
]
