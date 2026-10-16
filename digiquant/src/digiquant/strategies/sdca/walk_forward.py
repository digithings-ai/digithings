"""Walk-forward schedule and DCA-native objective for SDCA (#3174).

The owner's curve *shape* is frozen (#3169). This module searches the six
bounded parameters plus composite indicator weights (``valuation_weight`` and
optional ``m2_weight`` / ``rs_eth_weight`` / ``dxy_weight`` plus price
oscillators ``weekly_rsi_weight`` / ``weekly_macd_weight`` / ``sma_band_weight``).
The primary score is ``vs_flat_dca_pct`` (did the signal beat blind averaging?)
subject to a capital-deployed floor and a drawdown cap. ``vs_lump_pct`` is
reported, never optimized — maximizing it collapses to lump-sum on an uptrend.

Rails leakage (#3173): a quadratic log-time fit on truncated history does
not extrapolate. Callers **must** refit rails on each fold's in-sample
window (``RailsFitter``) and evaluate OOS on those coefficients. Using a
full-history fit for every fold is forbidden here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.composite_risk import IndicatorWeight
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import (
    composite_weights_from_params,
    extra_indicators_for_window,
)
from digiquant.strategies.sdca.risk_model import RiskModel

RailsFitter = Callable[[Sequence[date], Sequence[float]], RiskModel]

# A 5% bump that moves mean OOS vs-flat-DCA by more than this many percentage
# points is treated as a spike, not a plateau (#3174 sensitivity).
SENSITIVITY_SPIKE_PCT = 2.0


class SdcaOptimizeObjective(BaseModel):
    """Maximize ``vs_flat_dca_pct`` subject to activity and drawdown rails.

    Justification: flat DCA already captures the averaging effect, so anything
    above it is attributable to the valuation signal. Total return / vs-lump
    reward buying everything on day 1 in a bull market and are rejected.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    capital_deployed_floor_pct: float = Field(10.0, ge=0.0, le=100.0)
    max_drawdown_cap_pct: float = Field(50.0, gt=0.0, le=100.0)


class WalkForwardFold(BaseModel):
    """One expanding/rolling window. Dates are inclusive."""

    model_config = ConfigDict(frozen=True, strict=True)

    fold: int = Field(ge=0)
    is_start: date
    is_end: date
    oos_start: date
    oos_end: date


class SdcaTrialMetrics(BaseModel):
    """Fitness numbers for one window. ``*_pct`` are ×100 true percents."""

    model_config = ConfigDict(frozen=True, strict=True)

    vs_flat_dca_pct: float
    vs_lump_pct: float
    capital_deployed_pct: float
    max_drawdown_pct: float = Field(
        ...,
        description="Drawdown as a ×100 percent magnitude (15.0 = 15% peak-to-trough)",
    )


class SdcaTrialEvaluator(Protocol):
    """Fitness for one window. Production implementations must use Nautilus fills."""

    def __call__(
        self,
        dates: Sequence[date],
        prices: Sequence[float],
        risk_model: RiskModel,
        shape: SdcaCurveShape,
        valuation_weight: float,
        extra_indicators: Sequence[IndicatorWeight] | None = None,
    ) -> SdcaTrialMetrics: ...


class FoldScore(BaseModel):
    """In-sample and out-of-sample scores for one fold."""

    model_config = ConfigDict(frozen=True, strict=True)

    fold: WalkForwardFold
    in_sample: SdcaTrialMetrics
    out_of_sample: SdcaTrialMetrics
    feasible: bool


def make_walk_forward_folds(
    dates: Sequence[date],
    *,
    n_folds: int = 3,
    holdout_frac: float = 0.2,
    oos_frac: float = 0.25,
) -> tuple[list[WalkForwardFold], tuple[date, date]]:
    """Rolling OOS folds plus a held-out tail that is never used for search.

    ``holdout_frac`` of the calendar is reserved as the final segment.
    The remainder is split into ``n_folds`` successive (IS, OOS) pairs where
    each OOS is the next ``oos_frac`` of the searchable span and IS is
    everything before it (expanding window).
    """
    if n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    if not (0.0 < holdout_frac < 0.5):
        raise ValueError("holdout_frac must be in (0, 0.5)")
    if not (0.0 < oos_frac < 0.5):
        raise ValueError("oos_frac must be in (0, 0.5)")
    if len(dates) < 20:
        raise ValueError(f"need at least 20 dates for walk-forward, got {len(dates)}")
    ordered = list(dates)
    n = len(ordered)
    holdout_n = max(1, int(n * holdout_frac))
    search_n = n - holdout_n
    if search_n < 10:
        raise ValueError("searchable span too short after holdout")
    holdout = (ordered[search_n], ordered[-1])
    oos_len = max(1, int(search_n * oos_frac))
    folds: list[WalkForwardFold] = []
    # Expanding IS; OOS windows tile the last n_folds * oos_len of the search span.
    for i in range(n_folds):
        oos_end_i = search_n - (n_folds - 1 - i) * oos_len
        oos_start_i = oos_end_i - oos_len
        is_end_i = oos_start_i
        if is_end_i < 5 or oos_start_i < 0:
            raise ValueError("not enough history to place walk-forward folds")
        folds.append(
            WalkForwardFold(
                fold=i,
                is_start=ordered[0],
                is_end=ordered[is_end_i - 1],
                oos_start=ordered[oos_start_i],
                oos_end=ordered[oos_end_i - 1],
            )
        )
    return folds, holdout


def shape_from_params(params: dict[str, float | int | str]) -> SdcaCurveShape:
    """Build ``SdcaCurveShape`` from an optimizer param dict. May raise ValueError."""
    return SdcaCurveShape(
        buy_max_rate=float(params["buy_max_rate"]),
        buy_knee_risk=float(params["buy_knee_risk"]),
        sell_knee_risk=float(params["sell_knee_risk"]),
        sell_max_rate=float(params["sell_max_rate"]),
        buy_curvature=float(params["buy_curvature"]),
        sell_curvature=float(params["sell_curvature"]),
    )


def params_are_valid(params: dict[str, float | int | str]) -> bool:
    """True when shape invariants hold and at least one indicator weight is > 0."""
    try:
        shape_from_params(params)
        composite_weights_from_params(params)
    except (KeyError, TypeError, ValueError):
        return False
    return True


def valuation_weight_from_params(params: dict[str, float | int | str]) -> float:
    """Valuation rail weight; defaults to 1.0 (valuation-only) when omitted."""
    return composite_weights_from_params(params).valuation


def window_slice(
    dates: Sequence[date],
    prices: Sequence[float],
    start: date,
    end: date,
) -> tuple[list[date], list[float]]:
    """Inclusive calendar slice. Raises if the window is empty."""
    if len(dates) != len(prices):
        raise ValueError("dates and prices must be the same length")
    out_d: list[date] = []
    out_p: list[float] = []
    for d, p in zip(dates, prices, strict=True):
        if start <= d <= end:
            out_d.append(d)
            out_p.append(float(p))
    if not out_d:
        raise ValueError(f"empty walk-forward window {start}..{end}")
    return out_d, out_p


def max_drawdown_magnitude_pct(values: Sequence[float]) -> float:
    """Peak-to-trough as a ×100 percent magnitude (15.0 = 15%)."""
    if not values:
        raise ValueError("max_drawdown_magnitude_pct requires at least one value")
    peak = float(values[0])
    worst = 0.0
    for raw in values:
        v = float(raw)
        peak = max(peak, v)
        if peak > 0.0:
            worst = min(worst, (v - peak) / peak)
    return abs(worst) * 100.0


def score_trial_on_folds(
    params: dict[str, float | int | str],
    dates: Sequence[date],
    prices: Sequence[float],
    folds: Sequence[WalkForwardFold],
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    objective: SdcaOptimizeObjective,
    extra_z: Mapping[str, Sequence[float | None]] | None = None,
) -> list[FoldScore]:
    """Refit rails on each fold's IS window, then score IS and OOS on those rails.

    OOS never enters ``rails_fitter`` — #3173 truncated quadratic log-time fits
    do not extrapolate, so a full-history fit would leak and mislead. Extra-z
    series are sliced from a full-calendar causal precompute (no OOS refit).
    """
    if not params_are_valid(params):
        raise ValueError("params do not form a valid SdcaCurveShape")
    shape = shape_from_params(params)
    weights = composite_weights_from_params(params)
    zmap = extra_z or {}
    scores: list[FoldScore] = []
    for fold in folds:
        is_dates, is_prices = window_slice(dates, prices, fold.is_start, fold.is_end)
        oos_dates, oos_prices = window_slice(dates, prices, fold.oos_start, fold.oos_end)
        model = rails_fitter(is_dates, is_prices)
        in_sample = evaluator(
            is_dates,
            is_prices,
            model,
            shape,
            weights.valuation,
            extra_indicators_for_window(is_dates, dates, zmap, weights),
        )
        out_of_sample = evaluator(
            oos_dates,
            oos_prices,
            model,
            shape,
            weights.valuation,
            extra_indicators_for_window(oos_dates, dates, zmap, weights),
        )
        scores.append(
            FoldScore(
                fold=fold,
                in_sample=in_sample,
                out_of_sample=out_of_sample,
                feasible=is_feasible(out_of_sample, objective),
            )
        )
    return scores


def sensitivity_neighbors(
    params: dict[str, float | int | str],
    *,
    frac: float = 0.05,
) -> list[dict[str, float | int | str]]:
    """±``frac`` on each numeric param. Invalid shapes are dropped."""
    neighbors: list[dict[str, float | int | str]] = []
    for key, val in params.items():
        if not isinstance(val, (int, float)):
            continue
        for sign in (1.0, -1.0):
            bumped = dict(params)
            bumped[key] = float(val) * (1.0 + sign * frac)
            if params_are_valid(bumped):
                neighbors.append(bumped)
    return neighbors


def is_feasible(metrics: SdcaTrialMetrics, objective: SdcaOptimizeObjective) -> bool:
    """Capital-deployed floor and drawdown cap. Drawdown is a positive magnitude."""
    if metrics.capital_deployed_pct < objective.capital_deployed_floor_pct:
        return False
    if metrics.max_drawdown_pct > objective.max_drawdown_cap_pct:
        return False
    return True


def objective_score(metrics: SdcaTrialMetrics, objective: SdcaOptimizeObjective) -> float:
    """Primary: ``vs_flat_dca_pct``. Infeasible trials score −inf."""
    if not is_feasible(metrics, objective):
        return float("-inf")
    return metrics.vs_flat_dca_pct


__all__ = [
    "FoldScore",
    "RailsFitter",
    "SENSITIVITY_SPIKE_PCT",
    "SdcaOptimizeObjective",
    "SdcaTrialEvaluator",
    "SdcaTrialMetrics",
    "WalkForwardFold",
    "is_feasible",
    "make_walk_forward_folds",
    "max_drawdown_magnitude_pct",
    "objective_score",
    "params_are_valid",
    "score_trial_on_folds",
    "sensitivity_neighbors",
    "shape_from_params",
    "valuation_weight_from_params",
    "window_slice",
]
