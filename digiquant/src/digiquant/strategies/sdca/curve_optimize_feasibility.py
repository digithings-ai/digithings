"""Feasibility-aware curve scoring (SDCA #3174 follow-up).

``search_wide_knee_curve`` / ``score_shape_on_index`` (``curve_optimize.py``)
only ever optimize in-sample ``risk_adjusted_return`` (``total_return_pct /
max(max_drawdown_pct, 0.5)``). They have no awareness of whether the winning
curve shape keeps the strategy trading at a level that can survive the
walk-forward gate's own feasibility rails
(``SdcaOptimizeObjective.capital_deployed_floor_pct`` /
``max_drawdown_cap_pct``, ``walk_forward.py``). Two consecutive full
recalibration rounds on this branch were REJECTED post-hoc at Stage 4 for
exactly this: OOS folds with ``capital_deployed_pct`` of 0% (never traded
that window) or -35% (net seller -- sold more than it ever bought).

``capital_deployed_pct`` is not a new computation: ``run_backtest()`` already
puts it on ``SdcaBacktestReport`` as part of the very same simulation
``score_shape_on_index`` runs (``backtest.py::SdcaBacktestReport
.capital_deployed_pct``) -- it is simply not propagated by
``score_shape_on_index``'s ``CurveTrialScore`` return value. This module does
not change that. It is a strictly additive, opt-in alternative entry point:
``score_shape_on_index`` / ``search_wide_knee_curve`` and every other caller
of ``curve_optimize.py`` are untouched, byte for byte.

Trade-off, deliberately accepted: ``score_shape_on_index_feasibility_aware``
below calls both ``score_shape_on_index`` (for the existing gates /
``risk_adjusted_return``) and ``run_backtest`` directly (to read
``capital_deployed_pct`` off the report) -- i.e. it runs the backtest twice
per trial rather than reaching into ``curve_optimize.py``'s private
``_reject_reasons`` / ``_DRAWDOWN_EPSILON`` internals to build a single
merged pass. For a per-day-vectorizable but still O(n) Python backtest loop,
the 2x per-trial cost is a reasonable price for depending only on
``curve_optimize.py``'s public surface.
"""

from __future__ import annotations

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_optimize import (
    WIDE_KNEE_COARSE_GRID,
    WIDE_KNEE_SEARCH_BOUNDS,
    CurveOptimizeGates,
    CurveTrialScore,
    params_from_shape,
    published_curve_shape,
    sample_wide_knee_curve_trials,
    score_shape_on_index,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.walk_forward import SdcaOptimizeObjective

# Anchor the floor on the walk-forward gate's own default (walk_forward.py)
# rather than a second hardcoded literal, so this can't silently drift from
# what Stage 4 will actually enforce OOS.
CAPITAL_DEPLOYED_FLOOR_PCT: float = SdcaOptimizeObjective().capital_deployed_floor_pct

# A comfort margin above the bare floor. In-sample capital deployment tends
# to run higher than the *same shape's* OOS deployment on a different window
# (the search overfits to one window's price path/regime), so a curve that
# only just clears the floor in-sample is a good bet to land under it
# out-of-sample -- precisely the failure mode behind both rejected rounds.
# Candidates between the floor and this comfort line are down-weighted, not
# hard-rejected: they are not known-bad, just a worse bet than one with
# headroom.
CAPITAL_DEPLOYED_COMFORT_PCT: float = CAPITAL_DEPLOYED_FLOOR_PCT + 5.0

# Upper bound. ``run_backtest`` clamps every buy to the cash remaining
# (``backtest.py::size_trade``), so under the current evaluator
# ``capital_deployed_pct`` cannot structurally exceed 100% -- this branch is
# a defensive guard against a future evaluator (e.g. a margin/leverage-aware
# one) that doesn't share that invariant, so a shape is never rewarded for
# "deploying" more capital than it actually has.
CAPITAL_DEPLOYED_UPPER_PCT: float = 100.0

# Dominates any real risk_adjusted_return (for a plausible SDCA shape this
# stays within roughly [-5, 10]: total_return_pct / max(drawdown_pct, 0.5))
# so a hard-infeasible trial always ranks last regardless of the sign of its
# unpenalized score. Finite (not -inf) so results stay JSON/CSV
# round-trippable.
INFEASIBLE_SCORE: float = -1_000_000.0

# How much to subtract, at most, from risk_adjusted_return for a trial that
# is technically feasible but only barely -- sized to be comparable to
# typical risk_adjusted_return magnitudes so it can actually move the
# ranking, without being so large it acts like a second hard cliff right at
# the comfort line.
SOFT_ZONE_PENALTY_SCALE: float = 5.0

# Mirrors the capital-deployed floor/comfort/cap pattern above, but for
# ``max_drawdown_pct`` (2026-09-24 recalibration, round 8's realized -61.32%
# OOS drawdown). Chris's target is "best possible risk-adjusted return, with
# a drawdown around 30%, not exactly 30%" -- so 30.0 is a hard cap the
# search itself refuses to cross (never trade this off against return past
# that point), and 25.0 a comfort margin below it: same overfitting risk as
# capital deployment -- an in-sample shape that only just clears the cap is
# a good bet to land over it out-of-sample, so it is penalized, not treated
# as equally good as one with headroom.
MAX_DRAWDOWN_CAP_PCT: float = 30.0
MAX_DRAWDOWN_COMFORT_PCT: float = 25.0


class FeasibilityAwareCurveTrialScore(BaseModel):
    """``score_shape_on_index``'s trial, plus capital-deployment- and
    drawdown-aware scoring.

    ``risk_adjusted_return`` / ``capital_deployed_pct`` are the raw,
    unpenalized numbers (same definitions as ``CurveTrialScore`` /
    ``SdcaTrialMetrics``; ``base.max_drawdown_pct`` carries the drawdown
    equivalent). ``feasibility_adjusted_score`` is what a feasibility-aware
    search should rank candidates on.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    shape: SdcaCurveShape
    risk_adjusted_return: float
    capital_deployed_pct: float
    feasibility_adjusted_score: float
    capital_deployed_reject: bool = Field(
        description="True when capital_deployed_pct fell outside "
        "[CAPITAL_DEPLOYED_FLOOR_PCT, CAPITAL_DEPLOYED_UPPER_PCT] (the same "
        "band the walk-forward gate enforces OOS), or score_shape_on_index's "
        "own gates already rejected this shape."
    )
    drawdown_reject: bool = Field(
        description="True when base.max_drawdown_pct exceeded "
        "MAX_DRAWDOWN_CAP_PCT, or score_shape_on_index's own gates already "
        "rejected this shape."
    )
    base: CurveTrialScore


def _capital_deployed_penalty(
    capital_deployed_pct: float, risk_adjusted_return: float
) -> tuple[float, bool]:
    """Return ``(feasibility_adjusted_score, hard_reject)`` for one trial."""
    if (
        capital_deployed_pct < CAPITAL_DEPLOYED_FLOOR_PCT
        or capital_deployed_pct > CAPITAL_DEPLOYED_UPPER_PCT
    ):
        return INFEASIBLE_SCORE, True
    if capital_deployed_pct < CAPITAL_DEPLOYED_COMFORT_PCT:
        shortfall_frac = (CAPITAL_DEPLOYED_COMFORT_PCT - capital_deployed_pct) / (
            CAPITAL_DEPLOYED_COMFORT_PCT - CAPITAL_DEPLOYED_FLOOR_PCT
        )
        return risk_adjusted_return - SOFT_ZONE_PENALTY_SCALE * shortfall_frac, False
    return risk_adjusted_return, False


def _drawdown_penalty(max_drawdown_pct: float, risk_adjusted_return: float) -> tuple[float, bool]:
    """Return ``(feasibility_adjusted_score, hard_reject)`` for one trial.

    Same soft-then-hard shape as ``_capital_deployed_penalty``, just
    inverted: here the trial is penalized for being *above* a threshold
    (too much drawdown) instead of *below* one (too little capital
    deployed).
    """
    if max_drawdown_pct > MAX_DRAWDOWN_CAP_PCT:
        return INFEASIBLE_SCORE, True
    if max_drawdown_pct > MAX_DRAWDOWN_COMFORT_PCT:
        overage_frac = (max_drawdown_pct - MAX_DRAWDOWN_COMFORT_PCT) / (
            MAX_DRAWDOWN_CAP_PCT - MAX_DRAWDOWN_COMFORT_PCT
        )
        return risk_adjusted_return - SOFT_ZONE_PENALTY_SCALE * overage_frac, False
    return risk_adjusted_return, False


def score_shape_on_index_feasibility_aware(
    dates: pl.Series,
    prices: pl.Series,
    risk: pl.Series,
    shape: SdcaCurveShape,
    initial_cash: float,
    *,
    gates: CurveOptimizeGates | None = None,
) -> FeasibilityAwareCurveTrialScore:
    """``score_shape_on_index``, plus a capital-deployment-aware objective.

    Additive and opt-in: ``score_shape_on_index`` itself, ``search_curve``
    and ``search_wide_knee_curve`` are untouched -- this is a separate
    function callers must choose to use.
    """
    g = gates or CurveOptimizeGates()
    base = score_shape_on_index(dates, prices, risk, shape, initial_cash, gates=g)
    report, _frame = run_backtest(
        dates, prices, risk, AccumDistCurve(shape.to_nodes()), initial_cash
    )
    capital_deployed_pct = report.capital_deployed_pct
    if not base.feasible:
        # score_shape_on_index's own gates (no_sells, negative_cash,
        # long_only, ...) already win outright -- healthy capital deployment
        # or drawdown can't rescue an otherwise-infeasible shape.
        feasibility_adjusted_score = INFEASIBLE_SCORE
        capital_deployed_reject = True
        drawdown_reject = True
    else:
        capital_score, capital_deployed_reject = _capital_deployed_penalty(
            capital_deployed_pct, base.risk_adjusted_return
        )
        drawdown_score, drawdown_reject = _drawdown_penalty(
            base.max_drawdown_pct, base.risk_adjusted_return
        )
        if capital_deployed_reject or drawdown_reject:
            feasibility_adjusted_score = INFEASIBLE_SCORE
        else:
            # Both penalties are independent soft-zone deductions from the
            # same base.risk_adjusted_return -- combine by summing the two
            # deductions rather than taking the worse (min) score, so a
            # trial that is only-just-okay on both dimensions is penalized
            # for both, not let off for whichever one looks less bad.
            capital_penalty = base.risk_adjusted_return - capital_score
            drawdown_penalty = base.risk_adjusted_return - drawdown_score
            feasibility_adjusted_score = (
                base.risk_adjusted_return - capital_penalty - drawdown_penalty
            )
    return FeasibilityAwareCurveTrialScore(
        shape=shape,
        risk_adjusted_return=base.risk_adjusted_return,
        capital_deployed_pct=capital_deployed_pct,
        feasibility_adjusted_score=feasibility_adjusted_score,
        capital_deployed_reject=capital_deployed_reject,
        drawdown_reject=drawdown_reject,
        base=base,
    )


class FeasibilityAwareCurveSearchResult(BaseModel):
    """Outcome of ``search_wide_knee_curve_feasibility_aware``."""

    model_config = ConfigDict(frozen=True, strict=True)

    best: FeasibilityAwareCurveTrialScore
    baseline: FeasibilityAwareCurveTrialScore
    num_evaluations: int
    num_capital_deployed_rejected: int = Field(
        description="Trials with capital_deployed_reject=True, i.e. outside "
        "[CAPITAL_DEPLOYED_FLOOR_PCT, CAPITAL_DEPLOYED_UPPER_PCT] or already "
        "rejected by score_shape_on_index's own gates."
    )
    num_drawdown_rejected: int = Field(
        description="Trials with drawdown_reject=True, i.e. "
        "base.max_drawdown_pct > MAX_DRAWDOWN_CAP_PCT or already rejected by "
        "score_shape_on_index's own gates."
    )
    notes: str


def search_wide_knee_curve_feasibility_aware(
    dates: pl.Series,
    prices: pl.Series,
    risk: pl.Series,
    *,
    initial_cash: float,
    n_random: int = 3000,
    seed: int = 42,
    include_grid: bool = True,
    bounds: dict[str, tuple[float, float]] = WIDE_KNEE_SEARCH_BOUNDS,
    grid: dict[str, tuple[float, ...]] = WIDE_KNEE_COARSE_GRID,
    gates: CurveOptimizeGates | None = None,
) -> FeasibilityAwareCurveSearchResult:
    """Same trial grid as ``search_wide_knee_curve``, ranked by
    ``feasibility_adjusted_score`` instead of raw ``risk_adjusted_return``.

    Additive and opt-in: ``search_wide_knee_curve`` itself is untouched.
    In-sample only -- a winner here still has to clear the walk-forward OOS
    gate at Stage 4, this only makes the search itself steer away from
    shapes that gate is likely to flag.
    """
    g = gates or CurveOptimizeGates()
    trials = sample_wide_knee_curve_trials(
        n_random=n_random, seed=seed, include_grid=include_grid, bounds=bounds, grid=grid
    )
    baseline = score_shape_on_index_feasibility_aware(
        dates, prices, risk, published_curve_shape(), initial_cash, gates=g
    )
    scored: list[FeasibilityAwareCurveTrialScore] = []
    for params in trials:
        try:
            shape = SdcaCurveShape(
                buy_max_rate=float(params["buy_max_rate"]),
                buy_knee_risk=float(params["buy_knee_risk"]),
                sell_knee_risk=float(params["sell_knee_risk"]),
                sell_max_rate=float(params["sell_max_rate"]),
                buy_curvature=float(params["buy_curvature"]),
                sell_curvature=float(params["sell_curvature"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        scored.append(
            score_shape_on_index_feasibility_aware(
                dates, prices, risk, shape, initial_cash, gates=g
            )
        )
    if not scored:
        raise ValueError("no valid curve trials to evaluate")
    best = max(scored, key=lambda s: s.feasibility_adjusted_score)
    n_capital_rejected = sum(1 for s in scored if s.capital_deployed_reject)
    n_drawdown_rejected = sum(1 for s in scored if s.drawdown_reject)
    notes = (
        "Objective=feasibility_adjusted_score (risk_adjusted_return, "
        f"penalized below capital_deployed_pct={CAPITAL_DEPLOYED_COMFORT_PCT:.1f}% "
        f"and above max_drawdown_pct={MAX_DRAWDOWN_COMFORT_PCT:.1f}%, hard-rejected "
        f"outside [{CAPITAL_DEPLOYED_FLOOR_PCT:.1f}%, {CAPITAL_DEPLOYED_UPPER_PCT:.1f}%] "
        f"capital deployed, above {MAX_DRAWDOWN_CAP_PCT:.1f}% drawdown, or already "
        "rejected by score_shape_on_index's own gates). "
        f"best feasibility_adjusted_score={best.feasibility_adjusted_score:.4f} "
        f"(risk_adjusted_return={best.risk_adjusted_return:.4f}, "
        f"capital_deployed_pct={best.capital_deployed_pct:.2f}%, "
        f"max_drawdown_pct={best.base.max_drawdown_pct:.2f}%) "
        f"shape={params_from_shape(best.shape)}. "
        f"{n_capital_rejected}/{len(scored)} trials capital-deployed-rejected, "
        f"{n_drawdown_rejected}/{len(scored)} trials drawdown-rejected. "
        "In-sample only -- still subject to the walk-forward OOS gate."
    )
    return FeasibilityAwareCurveSearchResult(
        best=best,
        baseline=baseline,
        num_evaluations=len(scored),
        num_capital_deployed_rejected=n_capital_rejected,
        num_drawdown_rejected=n_drawdown_rejected,
        notes=notes,
    )


__all__ = [
    "CAPITAL_DEPLOYED_COMFORT_PCT",
    "CAPITAL_DEPLOYED_FLOOR_PCT",
    "CAPITAL_DEPLOYED_UPPER_PCT",
    "INFEASIBLE_SCORE",
    "MAX_DRAWDOWN_CAP_PCT",
    "MAX_DRAWDOWN_COMFORT_PCT",
    "SOFT_ZONE_PENALTY_SCALE",
    "FeasibilityAwareCurveSearchResult",
    "FeasibilityAwareCurveTrialScore",
    "score_shape_on_index_feasibility_aware",
    "search_wide_knee_curve_feasibility_aware",
]
