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
# ``max_drawdown_pct``. 2026-09-24 recalibration round 2: a tight 30/25
# cap/comfort here was found to fight the capital-deployed feasibility gate
# -- the search resolved the tension by starving capital deployment instead
# of finding a genuinely lower-drawdown shape (a "hollow win": low in-sample
# drawdown from barely investing, which then cratered OOS return). Per
# Chris's direction, crash_override (crash_override.py, applied at
# walk-forward-evaluation time on top of whatever curve this search picks)
# is now the primary, event-driven crash-response lever -- it should only
# bind during genuine fast-crash conditions. This gate becomes a true
# backstop instead: 50.0/45.0 is well above what a working curve should
# ever hit, so it stops being the dominant force shaping the curve search
# and only guards against a shape that is actually broken.
MAX_DRAWDOWN_CAP_PCT: float = 50.0
MAX_DRAWDOWN_COMFORT_PCT: float = 45.0


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


class RobustCurveTrialScore(BaseModel):
    """A trial's worst-case ``vs_flat_dca_pct`` across several windows.

    ``capital_deployed_pct`` is end-of-window ``initial_cash - cash``
    (``backtest.py::SdcaBacktestReport.capital_deployed_pct``) -- a cash
    SNAPSHOT, not a participation measure. It goes negative whenever a curve
    has sold more (in realized dollars) than it ever bought, which is exactly
    what a curve *should* do if it sells appreciated BTC into a rally near a
    window's end. Round 2's own OOS fold 0 proves this isn't a defect on its
    own: ``vs_flat_dca=+37.21%`` (crushes the benchmark) with
    ``capital_deployed=-28.5%`` (recalibration_v1_round2.log). Fold 1 and
    fold 2, by contrast, show real underperformance (``vs_flat_dca=-13.30%``,
    ``-13.31%``) alongside their own negative capital_deployed_pct -- that
    pairing, not the capital_deployed sign alone, is what marks genuine
    non-participation. This type ranks on worst-case ``vs_flat_dca_pct``
    directly instead.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    shape: SdcaCurveShape
    worst_vs_flat_dca_pct: float
    worst_max_drawdown_pct: float
    capital_deployed_pct: float = Field(
        description="capital_deployed_pct on the primary (first) window, "
        "informational only -- not gated on. See class docstring."
    )
    feasible: bool
    base: CurveTrialScore


def score_shape_on_windows_robust(
    windows: list[tuple[pl.Series, pl.Series, pl.Series]],
    shape: SdcaCurveShape,
    initial_cash: float,
    *,
    gates: CurveOptimizeGates | None = None,
) -> RobustCurveTrialScore:
    """Rank a shape on worst-case ``vs_flat_dca_pct`` across ``windows``
    (SDCA non-participation follow-up, 2026-09-25).

    Pass ``windows`` as the full-history index plus each walk-forward fold's
    IS window (``walk_forward.make_walk_forward_folds`` / ``window_slice``,
    sliced against the same risk series). ``windows[0]`` is the "primary"
    window: ``score_shape_on_index``'s own hard gates (``feasible``) are
    taken from it, same as the rest of this module. The drawdown cap/comfort
    (``MAX_DRAWDOWN_CAP_PCT``/``MAX_DRAWDOWN_COMFORT_PCT``) is still enforced,
    using the worst drawdown across all windows -- unlike capital_deployed_pct,
    a large intra-window drawdown is bad regardless of where the window ends,
    so that check is not endpoint-dependent the way capital_deployed_pct is.
    """
    if not windows:
        raise ValueError("windows must be non-empty")
    g = gates or CurveOptimizeGates()
    primary_dates, primary_prices, primary_risk = windows[0]
    base = score_shape_on_index(
        primary_dates, primary_prices, primary_risk, shape, initial_cash, gates=g
    )
    primary_report, _frame = run_backtest(
        primary_dates, primary_prices, primary_risk, AccumDistCurve(shape.to_nodes()), initial_cash
    )
    if not base.feasible:
        return RobustCurveTrialScore(
            shape=shape,
            worst_vs_flat_dca_pct=base.vs_flat_dca_pct,
            worst_max_drawdown_pct=base.max_drawdown_pct,
            capital_deployed_pct=primary_report.capital_deployed_pct,
            feasible=False,
            base=base,
        )
    vs_flat_dca_pcts = [base.vs_flat_dca_pct]
    max_drawdown_pcts = [base.max_drawdown_pct]
    for w_dates, w_prices, w_risk in windows[1:]:
        w_score = score_shape_on_index(w_dates, w_prices, w_risk, shape, initial_cash, gates=g)
        vs_flat_dca_pcts.append(w_score.vs_flat_dca_pct)
        max_drawdown_pcts.append(w_score.max_drawdown_pct)
    worst_vs_flat_dca_pct = min(vs_flat_dca_pcts)
    worst_max_drawdown_pct = max(max_drawdown_pcts)
    _drawdown_score, drawdown_reject = _drawdown_penalty(worst_max_drawdown_pct, base.risk_adjusted_return)
    return RobustCurveTrialScore(
        shape=shape,
        worst_vs_flat_dca_pct=worst_vs_flat_dca_pct,
        worst_max_drawdown_pct=worst_max_drawdown_pct,
        capital_deployed_pct=primary_report.capital_deployed_pct,
        feasible=not drawdown_reject,
        base=base,
    )


def search_wide_knee_curve_multi_window_robust(
    windows: list[tuple[pl.Series, pl.Series, pl.Series]],
    *,
    initial_cash: float,
    n_random: int = 3000,
    seed: int = 42,
    include_grid: bool = True,
    bounds: dict[str, tuple[float, float]] = WIDE_KNEE_SEARCH_BOUNDS,
    grid: dict[str, tuple[float, ...]] = WIDE_KNEE_COARSE_GRID,
    gates: CurveOptimizeGates | None = None,
) -> "RobustCurveSearchResult":
    """Same trial grid as ``search_wide_knee_curve_feasibility_aware``, ranked
    on worst-case ``vs_flat_dca_pct`` across ``windows`` instead of raw
    in-sample ``risk_adjusted_return`` on a single index.

    Additive and opt-in: every other search function in this module and
    ``curve_optimize.py`` is untouched. In-sample only -- a winner here still
    has to clear the walk-forward OOS gate at Stage 4.
    """
    g = gates or CurveOptimizeGates()
    trials = sample_wide_knee_curve_trials(
        n_random=n_random, seed=seed, include_grid=include_grid, bounds=bounds, grid=grid
    )
    baseline = score_shape_on_windows_robust(
        windows, published_curve_shape(), initial_cash, gates=g
    )
    scored: list[RobustCurveTrialScore] = []
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
        scored.append(score_shape_on_windows_robust(windows, shape, initial_cash, gates=g))
    if not scored:
        raise ValueError("no valid curve trials to evaluate")
    feasible_scored = [s for s in scored if s.feasible]
    pool = feasible_scored or scored
    best = max(pool, key=lambda s: s.worst_vs_flat_dca_pct)
    n_drawdown_rejected = sum(1 for s in scored if not s.feasible)
    notes = (
        "Objective=worst-case vs_flat_dca_pct across "
        f"{len(windows)} windows (full history + each walk-forward fold's IS "
        f"window), subject to max_drawdown_pct<={MAX_DRAWDOWN_CAP_PCT:.1f}% "
        "(comfort-penalized above "
        f"{MAX_DRAWDOWN_COMFORT_PCT:.1f}%) on the worst window, or already "
        "rejected by score_shape_on_index's own gates on the primary window. "
        f"capital_deployed_pct is reported, not gated on (endpoint snapshot -- "
        "see RobustCurveTrialScore docstring). "
        f"best worst_vs_flat_dca_pct={best.worst_vs_flat_dca_pct:.2f}% "
        f"(worst_max_drawdown_pct={best.worst_max_drawdown_pct:.2f}%, "
        f"capital_deployed_pct[primary]={best.capital_deployed_pct:.2f}%) "
        f"shape={params_from_shape(best.shape)}. "
        f"{n_drawdown_rejected}/{len(scored)} trials drawdown-rejected "
        f"({len(feasible_scored)}/{len(scored)} feasible). "
        "In-sample only -- still subject to the walk-forward OOS gate."
    )
    return RobustCurveSearchResult(
        best=best,
        baseline=baseline,
        num_evaluations=len(scored),
        num_drawdown_rejected=n_drawdown_rejected,
        notes=notes,
    )


class RobustCurveSearchResult(BaseModel):
    """Outcome of ``search_wide_knee_curve_multi_window_robust``."""

    model_config = ConfigDict(frozen=True, strict=True)

    best: RobustCurveTrialScore
    baseline: RobustCurveTrialScore
    num_evaluations: int
    num_drawdown_rejected: int
    notes: str


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
    "RobustCurveSearchResult",
    "RobustCurveTrialScore",
    "score_shape_on_index_feasibility_aware",
    "score_shape_on_windows_robust",
    "search_wide_knee_curve_feasibility_aware",
    "search_wide_knee_curve_multi_window_robust",
]
