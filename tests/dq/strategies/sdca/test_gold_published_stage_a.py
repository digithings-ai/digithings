"""Published Stage A keep/drop for GLD on in-sample vs-flat-DCA (#4804).

``digiquant/scripts/run_gold_published_stage_a.py`` is **glue**. The search itself is
the SHIPPED ``strategies/sdca/weight_search.py::optimize_stage_a_by_backtest``, on the
SHIPPED frozen grids it declares, and the objective is in-sample ``vs_flat_dca_pct``
subject to the 10% capital-deployed floor and the 50% drawdown cap — **not** vs-lump,
**not** Sharpe, and **not** the cycle-overlap diagnostic the preceding run used.

The script is loaded by FILE PATH (the local script-import pattern this directory
already uses in ``test_gold_stage_a_weights.py``), because it lives under
``digiquant/scripts/`` and not on ``src``'s package path.

What is pinned here, and how each pin can fail:

1. **The shipped function's own grids are used, un-widened and un-narrowed.** The test
   reads ``optimize_stage_a_by_backtest``'s signature defaults and asserts the runner
   never passes a ``grid`` / ``valuation_grid`` override. Widening or narrowing the grid
   is a silent change to the published keep/drop, so it is pinned at the source.
2. **An independent re-sweep must agree on the winner AND the evaluation count.** The
   test enumerates ``valuation_grid x grid**len(names)`` itself and scores with its own
   injected evaluator. A runner that quietly dropped a name, skipped a combo class, or
   invented a filter changes which row wins or the count, so the disagreement shows up.
   This is the pin that catches a silently-narrowed search.
3. **The feasibility narrowing is RECORDED, never silent.** Every name over the
   calendar-coverage limit is excluded *with its measured coverage*, a name exactly at
   the limit is kept (the boundary is inclusive), and the projected full-allowlist cost
   is carried in the artifact. A name that vanishes with no recorded reason fails here.
4. **OOS is reported and NEVER used to pick.** Two pins: a behavioural one (a fixture
   whose OOS is the *worst* available and whose IS is the best — the IS-argmax must
   still win), and a source-level one (the shipped rank function's source must not read
   the OOS field at all). Behaviour alone could be satisfied by luck.
5. **The valuation-only baseline always runs**, so every per-extra delta has a
   reference row and "extras add nothing" is a measurement rather than an assumption.
6. **Every allowlist name gets exactly one per-extra probe row**, so no name is
   unreported — including the ones the feasibility call excluded from the joint sweep.
7. **Determinism: two identical runs serialize byte-identically.** The artifact is a
   research record the owner diffs against itself.
8. **Genuine failures are clean ``ValueError``s**, never a bare ``assert`` in the script
   (which dies on ``python -O`` and hides the failure behind an unrecognisable
   ``AssertionError``) and never an ``IndexError`` from a mis-indexed lookup.
9. **The disclosures survive in the labels and the artifact**: no gold profile exists in
   ``asset_profile.py`` (so the runner builds one and says so), the objective does not
   consume cycle windows (so the profile's required field is inert), the shipped rank
   does not gate on the floor or the cap (so nothing may claim it did), and IN-SAMPLE
   and OOS are marked separately everywhere.

Nothing here reads the price history: every read is synthetic and every evaluator is
injected, so these pins are about the WIRING RULES, not about the numbers GLD happens to
produce.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import inspect
import itertools
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from digiquant.strategies.sdca.indicator_catalog import (
    GENERIC_TECHNICAL_NAMES,
    GOLD_MACRO_NAMES,
    SdcaCompositeWeights,
)
from digiquant.strategies.sdca.walk_forward import SdcaOptimizeObjective, SdcaTrialMetrics
from digiquant.strategies.sdca.weight_search import (
    optimize_stage_a_by_backtest,
    search_names_with_data,
)

REPO = Path(__file__).resolve().parents[4]
RUNNER_PATH = REPO / "digiquant" / "scripts" / "run_gold_published_stage_a.py"

pytestmark = pytest.mark.unit

# The shipped frozen grids, restated here ONLY so the test can assert the runner left
# them alone. The runner itself never hardcodes a grid.
SHIPPED_GRID = (0.0, 0.5, 1.0)
SHIPPED_VALUATION_GRID = (0.0, 0.5, 1.0)


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner() -> Any:
    return _load(RUNNER_PATH, "run_gold_published_stage_a")


# --------------------------------------------------------------------------- #
# Synthetic fixtures — an injected evaluator, no price history, no Nautilus
# --------------------------------------------------------------------------- #


def _dates(n: int, start: date = date(2020, 1, 1)) -> list[date]:
    return [start + _dt.timedelta(days=i) for i in range(n)]


def _cheap_at_bottoms(dates: list[date], *, trough_end: date, peak_start: date) -> list[float]:
    """A z that votes CHEAP (+z) early and RICH (-z) late."""
    return [3.0 if d <= trough_end else (-3.0 if d >= peak_start else 0.0) for d in dates]


def _inverted(dates: list[date], *, trough_end: date, peak_start: date) -> list[float]:
    """A z that votes the WRONG way: rich early, cheap late."""
    return [-v for v in _cheap_at_bottoms(dates, trough_end=trough_end, peak_start=peak_start)]


def _evaluator_factory(
    scores: dict[str, float],
    oos_dates: frozenset[date] | None = None,
    *,
    deployed_pct: float = 80.0,
    drawdown_pct: float = 12.0,
) -> Any:
    """An ``SdcaTrialEvaluator`` whose in-sample vs-flat-DCA depends only on the ENABLED SET.

    The score is a function of the frozenset of enabled extra names, so a sweep is fully
    determined by the weights and an independent re-sweep can reproduce it exactly.

    When ``oos_dates`` is given, an out-of-sample window scores the NEGATIVE of its
    in-sample score. That is what makes the "OOS was reported but never selected on" pin a
    real test rather than a coincidence: on this fixture the row that wins in-sample is
    exactly the row that loses out-of-sample, so a selector that peeked at OOS would pick a
    different winner.
    """

    def _evaluator(
        dates: Any,
        prices: Any,
        risk_model: Any,
        shape: Any,
        valuation_weight: float,
        extra_indicators: Any = None,
    ) -> SdcaTrialMetrics:
        enabled = tuple(sorted(ind.name for ind in (extra_indicators or [])))
        base = scores.get(enabled, 0.0)
        out_of_sample = bool(oos_dates) and bool(dates) and dates[0] in oos_dates
        return SdcaTrialMetrics(
            vs_flat_dca_pct=-base if out_of_sample else base,
            vs_lump_pct=-base,
            capital_deployed_pct=deployed_pct,
            capital_deployed_peak_pct=deployed_pct,
            max_drawdown_pct=drawdown_pct,
        )

    return _evaluator


def _oos_date_set(dates: list[date]) -> frozenset[date]:
    """Every out-of-sample day under the shipped fold geometry."""
    from digiquant.strategies.sdca.walk_forward import make_walk_forward_folds

    folds, _holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)
    return frozenset(
        day for fold in folds for day in dates if fold.oos_start <= day <= fold.oos_end
    )


def _rails_fitter(dates: Any, prices: Any) -> Any:
    """A ``RailsFitter`` that never touches prices — the fixture's rails are irrelevant."""
    return object()


def _null_series(dates: list[date], frac: float) -> list[float | None]:
    """A z that is null for the last ``frac`` share of days (a late-starting macro leg)."""
    cut = int(len(dates) * (1.0 - frac))
    return [None if i >= cut else 1.0 for i in range(len(dates))]


# --------------------------------------------------------------------------- #
# 1. The shipped grids are used, un-widened and un-narrowed
# --------------------------------------------------------------------------- #


def test_the_shipped_function_still_declares_the_frozen_grids() -> None:
    """If the shipped grids move, THIS test fails first — before any runner behaviour."""
    params = inspect.signature(optimize_stage_a_by_backtest).parameters
    assert tuple(params["grid"].default) == SHIPPED_GRID
    assert tuple(params["valuation_grid"].default) == SHIPPED_VALUATION_GRID
    assert params["n_folds"].default == 3
    assert params["holdout_frac"].default == 0.2
    assert params["oos_frac"].default == 0.25


def test_the_runner_never_overrides_a_grid_or_the_fold_geometry(runner: Any) -> None:
    """The runner must add no ``grid=`` / ``valuation_grid=`` / ``n_folds=`` argument."""
    source = RUNNER_PATH.read_text()
    for forbidden in ("grid=", "valuation_grid=", "n_folds=", "holdout_frac=", "oos_frac="):
        assert forbidden not in source, f"the runner must not override {forbidden!r}"
    assert runner.FROZEN_GRID_SOURCE, "the runner must name where its grids came from"
    assert "optimize_stage_a_by_backtest" in runner.FROZEN_GRID_SOURCE
    assert "weight_search" in runner.FROZEN_GRID_SOURCE


def test_the_objective_is_vs_flat_dca_on_a_10pct_floor_and_a_50pct_dd_cap(runner: Any) -> None:
    objective = runner.objective()
    assert objective == SdcaOptimizeObjective()
    assert objective.capital_deployed_floor_pct == 10.0
    assert objective.max_drawdown_cap_pct == 50.0
    assert "vs_flat_dca_pct" in runner.OBJECTIVE_LABEL
    assert "IN-SAMPLE" in runner.OBJECTIVE_LABEL
    # The label must name what the objective is NOT, so nobody re-reads it as vs-lump or
    # Sharpe. Checked positively: a negative check would forbid the words themselves.
    assert "Not vs-lump" in runner.OBJECTIVE_LABEL
    assert "not Sharpe" in runner.OBJECTIVE_LABEL
    assert "not cycle overlap" in runner.OBJECTIVE_LABEL


# --------------------------------------------------------------------------- #
# 2. An independent re-sweep must agree on winner AND evaluation count
# --------------------------------------------------------------------------- #


def _independent_argmax(
    dates: list[date],
    prices: list[float],
    extra_z: dict[str, list[float | None]],
    names: tuple[str, ...],
    evaluator: Any,
    shape: Any,
) -> tuple[SdcaCompositeWeights, float, int]:
    """Sweep the shipped grid here, independently of the runner.

    Deliberately re-implemented rather than delegated: the point is that a narrowed
    search in the runner cannot agree with a full sweep done from the spec. It mirrors the
    shipped loop's skips (all-zero weights raise; an enabled name with no series is
    skipped) and its tie-break (higher mean IS, then fewer enabled extras, then higher
    valuation).
    """
    from digiquant.strategies.sdca.indicator_catalog import extra_indicators_for_window
    from digiquant.strategies.sdca.walk_forward import make_walk_forward_folds, window_slice

    folds, _holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)
    best: SdcaCompositeWeights | None = None
    best_rank = float("-inf")
    evaluated = 0
    for value in SHIPPED_VALUATION_GRID:
        for combo in itertools.product(SHIPPED_GRID, repeat=len(names)):
            payload = {name: float(w) for name, w in zip(names, combo, strict=True)}
            try:
                weights = SdcaCompositeWeights(valuation=float(value), **payload)
            except ValueError:
                continue
            if any(n not in extra_z for n in weights.enabled_extras()):
                continue
            evaluated += 1
            total = 0.0
            for fold in folds:
                is_d, is_p = window_slice(dates, prices, fold.is_start, fold.is_end)
                metrics = evaluator(
                    is_d,
                    is_p,
                    _rails_fitter(None, None),
                    shape,
                    weights.valuation,
                    extra_indicators_for_window(is_d, dates, extra_z, weights),
                )
                total += metrics.vs_flat_dca_pct
            rank = total / len(folds)
            complexity = (len(weights.enabled_extras()), -weights.valuation)
            incumbent = (len(best.enabled_extras()), -best.valuation) if best is not None else None
            if best is None or rank > best_rank or (rank == best_rank and complexity < incumbent):
                best, best_rank = weights, rank
    assert best is not None
    return best, best_rank, evaluated


def test_the_winner_is_the_argmax_of_an_independently_swept_full_grid(runner: Any) -> None:
    """The pin that catches a silently-narrowed search."""
    dates = _dates(200)
    shape = runner.curve_shape()
    names = ("weekly_rsi", "sma_band", "weekly_macd")
    cheap_early, cheap_late = date(2020, 1, 20), date(2020, 4, 1)
    extra_z = {
        "weekly_rsi": _cheap_at_bottoms(dates, trough_end=cheap_early, peak_start=cheap_late),
        "sma_band": _cheap_at_bottoms(dates, trough_end=cheap_early, peak_start=cheap_late),
        # An INVERTED leg: a positive weight on it must HURT, so a grid that quietly
        # skipped it would pick different weights.
        "weekly_macd": _inverted(dates, trough_end=cheap_early, peak_start=cheap_late),
    }
    scores = {
        (): 1.0,
        ("weekly_rsi",): 5.0,
        ("sma_band",): 5.0,
        ("weekly_rsi", "sma_band"): 9.0,
        ("weekly_rsi", "weekly_macd"): 2.0,
        ("sma_band", "weekly_macd"): 2.0,
        ("weekly_rsi", "sma_band", "weekly_macd"): 5.0,
        ("weekly_macd",): -5.0,
    }
    evaluator = _evaluator_factory(scores, _oos_date_set(dates))
    prices = [100.0 + i for i in range(len(dates))]

    run = runner.run_published(
        dates,
        prices,
        extra_z=extra_z,
        rails_fitter=_rails_fitter,
        evaluator=evaluator,
        shape=shape,
        search_names=names,
        objective=runner.objective(),
        label="joint",
    )

    expected, expected_is, expected_evaluations = _independent_argmax(
        dates, prices, extra_z, names, evaluator, shape
    )
    assert run.weights == expected, "the winner must be the full-grid argmax on in-sample"
    assert run.mean_is_vs_flat_dca_pct == pytest.approx(expected_is)
    assert run.num_evaluations == expected_evaluations, (
        "the evaluation count is the grid's width; a narrowed sweep shows up here"
    )
    assert run.mean_oos_vs_flat_dca_pct == pytest.approx(-expected_is), (
        "on this fixture the IS winner is the OOS loser, so reporting both proves they "
        "are different numbers"
    )


def test_the_joint_sweep_reaches_every_searched_name(runner: Any) -> None:
    """A searched name with a series is searched; one without is not invented."""
    dates = _dates(200)
    result = runner.run_published(
        dates,
        [100.0 + i for i in range(len(dates))],
        extra_z={"weekly_rsi": [0.0] * len(dates)},
        rails_fitter=_rails_fitter,
        evaluator=_evaluator_factory({(): 1.0, ("weekly_rsi",): 2.0}),
        shape=runner.curve_shape(),
        search_names=("weekly_rsi", "sma_band"),
        objective=runner.objective(),
        label="data",
    )
    assert result.search_names == ("weekly_rsi",), (
        "a name with no z series must drop out through search_names_with_data, not be invented"
    )
    assert search_names_with_data(("weekly_rsi", "sma_band"), {"weekly_rsi": [0.0]}) == (
        "weekly_rsi",
    )


def test_every_searched_name_has_a_built_z_series(runner: Any) -> None:
    with pytest.raises(ValueError, match="without a built z series"):
        runner.require_built_series(("weekly_rsi", "sma_band"), {"weekly_rsi": [0.0] * 120})


# --------------------------------------------------------------------------- #
# 3. The feasibility narrowing is RECORDED, never silent
# --------------------------------------------------------------------------- #


def test_a_name_over_the_coverage_limit_is_excluded_and_recorded(runner: Any) -> None:
    rows = (
        runner.CoverageRow(name="breakeven_5y", searched=True, span_null_pct=1.7),
        runner.CoverageRow(
            name="gvz",
            searched=False,
            span_null_pct=20.6,
            worst_window_null_pct=82.5,
            worst_window="fold0_is",
        ),
        runner.CoverageRow(
            name="hy_oas",
            searched=False,
            span_null_pct=100.0,
            worst_window_null_pct=100.0,
            worst_window="fold0_is",
        ),
    )
    plan = runner.partition_search_names(rows, limit_pct=runner.NULL_COVERAGE_LIMIT_PCT)
    assert plan.search_names == ("breakeven_5y",)
    reasons = {e.name: e.reason for e in plan.exclusions}
    assert reasons == {
        "gvz": "calendar coverage over the feasibility limit",
        "hy_oas": "calendar coverage over the feasibility limit",
    }
    for exclusion in plan.exclusions:
        assert f"{runner.NULL_COVERAGE_LIMIT_PCT:g}%" in exclusion.detail
        assert "%" in exclusion.detail, "the measured coverage must be quoted, not paraphrased"
    detail = next(e.detail for e in plan.exclusions if e.name == "gvz")
    assert "82.5%" in detail and "fold0_is" in detail, (
        "the detail must name the window that failed, not just an averaged share"
    )
    assert "20.6%" in detail, "and it must still quote the span average for contrast"
    assert "FEASIBILITY CALL" in plan.detail


def test_a_name_exactly_at_the_coverage_limit_is_kept(runner: Any) -> None:
    """The boundary is inclusive, so the limit is a stated rule and not a tuned threshold."""
    limit = runner.NULL_COVERAGE_LIMIT_PCT
    rows = (
        runner.CoverageRow(
            name="edge", searched=True, span_null_pct=1.0, worst_window_null_pct=limit
        ),
        runner.CoverageRow(
            name="over",
            searched=False,
            span_null_pct=1.0,
            worst_window_null_pct=limit + 0.1,
        ),
    )
    plan = runner.partition_search_names(rows, limit_pct=limit)
    assert plan.search_names == ("edge",)
    assert [e.name for e in plan.exclusions] == ["over"]


def test_the_gate_is_the_worst_scored_window_not_the_span_average(runner: Any) -> None:
    """A leg that averages well but misses half of the first fold must be held out.

    This is the failure that nearly shipped: the macro legs' missing history is
    concentrated in the earliest in-sample fold, so a span-average rule lets them through
    and the joint sweep becomes infeasible again.
    """
    dates = _dates(1000)
    # Absent through most of fold 0's in-sample window, present everywhere after. The
    # searchable span is 4x the first fold's window, so 90% missing there averages to 22.5%
    # across the span and would sail under a span-average rule.
    late = [None] * 180 + [1.0] * 820
    rows = runner.measure_coverage(dates, {"late": late}, limit_pct=runner.NULL_COVERAGE_LIMIT_PCT)
    assert rows[0].span_null_pct < runner.NULL_COVERAGE_LIMIT_PCT, (
        "the span average alone would clear the budget — that is the trap"
    )
    assert rows[0].worst_window == "fold0_is"
    assert rows[0].worst_window_null_pct == pytest.approx(90.0)
    assert rows[0].searched is False
    assert rows[0].worst_window.startswith("fold")


def test_a_leg_missing_only_at_the_very_end_of_the_span_is_still_searched(runner: Any) -> None:
    """The window rule must not become a tripwire that rejects a merely late leg.

    ``fold2_oos`` is the last scored window; a leg missing only its final sliver clears the
    budget everywhere and must be searched.
    """
    dates = _dates(1000)
    almost = [1.0] * 780 + [None] * 220
    rows = runner.measure_coverage(
        dates, {"almost": almost}, limit_pct=runner.NULL_COVERAGE_LIMIT_PCT
    )
    assert rows[0].worst_window == "fold2_oos"
    assert rows[0].worst_window_null_pct == pytest.approx(10.0)
    assert rows[0].searched is True


def test_the_feasibility_call_names_the_projected_cost_and_the_subset(runner: Any) -> None:
    assert "FEASIBILITY CALL" in runner.FEASIBILITY_NOTE
    for token in ("stage_a_search_names", "3**", "ms/eval", "h"):
        assert token in runner.FEASIBILITY_NOTE, f"the feasibility note must state {token!r}"
    assert runner.NULL_COVERAGE_LIMIT_PCT == 25.0, (
        "the coverage limit is a stated quarter-of-the-calendar budget, not a tuned threshold"
    )


def test_coverage_is_measured_on_the_searchable_span_not_the_full_calendar(runner: Any) -> None:
    """The holdout tail is never scored by the search, so it must not count toward coverage."""
    dates = _dates(100)
    # Null only in the LAST scored window, so the span average is small but the last
    # window is half-gone — the two measures genuinely disagree.
    series = [1.0] * 70 + [None] * 30
    rows = runner.measure_coverage(
        dates,
        {"late": series},
        limit_pct=runner.NULL_COVERAGE_LIMIT_PCT,
    )
    assert len(rows) == 1
    # The searchable span is the first 80 bars, of which the last 10 are null -> 12.5%.
    assert rows[0].span_null_pct == pytest.approx(12.5)
    assert rows[0].full_null_pct == pytest.approx(30.0)
    assert rows[0].worst_window == "fold2_oos"
    assert rows[0].worst_window_null_pct == pytest.approx(50.0)
    assert rows[0].searched is False, (
        "50% missing in a scored window is over the budget even though the span reads 12.5%"
    )


# --------------------------------------------------------------------------- #
# 4. OOS is reported and NEVER used to pick
# --------------------------------------------------------------------------- #


def test_oos_is_reported_but_never_selects_the_winner(runner: Any) -> None:
    """Behavioural pin: the fixture's OOS is the negative of its IS, so IS wins."""
    dates = _dates(200)
    scores = {(): 1.0, ("weekly_rsi",): 7.0, ("sma_band",): 2.0, ("weekly_rsi", "sma_band"): 3.0}
    run = runner.run_published(
        dates,
        [100.0 + i for i in range(len(dates))],
        extra_z={
            "weekly_rsi": [0.0] * len(dates),
            "sma_band": [0.0] * len(dates),
        },
        rails_fitter=_rails_fitter,
        evaluator=_evaluator_factory(scores, _oos_date_set(dates)),
        shape=runner.curve_shape(),
        search_names=("weekly_rsi", "sma_band"),
        objective=runner.objective(),
        label="oos",
    )
    assert run.weights.enabled_extras() == {"weekly_rsi": 0.5} or run.weights.enabled_extras() == {
        "weekly_rsi": 1.0
    }, "the winner is the IS-best enabled set, whichever weight carries it"
    assert run.mean_is_vs_flat_dca_pct == pytest.approx(7.0)
    assert run.mean_oos_vs_flat_dca_pct == pytest.approx(-7.0), (
        "the same row's OOS is the worst available; it was reported, not chosen on"
    )


def test_an_all_cash_oos_is_detected_and_never_presented_as_evidence(runner: Any) -> None:
    """The no-trend rails cannot produce rails outside their fit window, so OOS goes void.

    This is computed, not asserted in prose: the disclosure must be true of the run it
    describes, or it is worse than silence. The detector is exercised on hand-built runs
    rather than through the sweep, because what is under test is the DETECTOR — whether it
    can tell a traded OOS from an all-cash one — not the sweep.
    """
    fold = runner_extra_fold()
    scores = (
        runner.FoldScore(
            fold=fold,
            in_sample=_metrics(vs_flat=3.0, peak=80.0),
            out_of_sample=_metrics(vs_flat=-1.0, peak=0.0),
            feasible=True,
        ),
    )
    assert runner.oos_is_degenerate((_run(runner, scores),)) is True

    traded = (
        runner.FoldScore(
            fold=fold,
            in_sample=_metrics(vs_flat=3.0, peak=80.0),
            out_of_sample=_metrics(vs_flat=-1.0, peak=55.0),
            feasible=True,
        ),
    )
    assert runner.oos_is_degenerate((_run(runner, traded),)) is False
    assert runner.oos_is_degenerate(()) is False, "no folds is not a claim of degeneracy"

    body = runner.payload(
        runs=(_run(runner, scores),),
        plan=_synthetic_plan(runner),
        coverage=_synthetic_plan(runner).coverage,
        probes=(),
        allowlist=("weekly_rsi",),
        projected_full_cost=runner.ProjectedCost(
            names=1, evaluations=9, ms_per_eval=1.0, hours=0.0
        ),
    )
    assert body["oos_is_degenerate"] is True
    assert "RollingZRiskModel" in body["oos_void_label"], (
        "the disclosure must name the mechanism, so the owner can act on it"
    )
    assert "rails" in body["oos_void_label"]


def _metrics(*, vs_flat: float, peak: float) -> SdcaTrialMetrics:
    return SdcaTrialMetrics(
        vs_flat_dca_pct=vs_flat,
        vs_lump_pct=0.0,
        capital_deployed_pct=peak,
        capital_deployed_peak_pct=peak,
        max_drawdown_pct=5.0,
    )


def _run(runner: Any, fold_scores: tuple[Any, ...]) -> Any:
    return runner.PublishedRun(
        label="fixture",
        weights=SdcaCompositeWeights(valuation=1.0),
        search_names=(),
        mean_is_vs_flat_dca_pct=1.0,
        mean_oos_vs_flat_dca_pct=-1.0,
        num_evaluations=1,
        feasible_folds=1,
        wall_seconds=0.0,
        fold_scores=fold_scores,
    )


def runner_extra_fold() -> Any:
    from digiquant.strategies.sdca.walk_forward import WalkForwardFold

    return WalkForwardFold(
        fold=0,
        is_start=date(2020, 1, 1),
        is_end=date(2020, 6, 1),
        oos_start=date(2020, 6, 2),
        oos_end=date(2020, 12, 1),
    )


def test_the_floor_basis_difference_between_the_two_stages_is_stated(runner: Any) -> None:
    """Stage A measures the floor on NET deployed; Stage B measures it on PEAK."""
    from digiquant.strategies.sdca import walk_forward, weight_search

    stage_a = inspect.getsource(weight_search._score_weights_on_cached_folds)
    stage_b = inspect.getsource(walk_forward.is_feasible)
    assert "capital_deployed_pct >=" in stage_a and "capital_deployed_peak_pct" not in stage_a
    assert "capital_deployed_peak_pct" in stage_b
    assert "PEAK" in runner.FLOOR_BASIS_LABEL
    assert "NET" in runner.FLOOR_BASIS_LABEL


def test_the_shipped_rank_function_cannot_read_the_oos_field() -> None:
    """Source-level pin. Behaviour alone could be satisfied by luck.

    ``_is_rank_score`` is the shipped Stage A rank. If it ever grows an OOS term the
    published keep/drop stops being an in-sample selection, and this test says so before
    any gold number moves.
    """
    from digiquant.strategies.sdca import weight_search

    source = inspect.getsource(weight_search._is_rank_score)
    assert "out_of_sample" not in source, (
        "the shipped Stage A rank must stay in-sample only; it grew an OOS read"
    )
    assert "vs_flat_dca_pct" in source


def test_the_rank_does_not_gate_on_the_floor_or_the_cap_and_that_is_disclosed(runner: Any) -> None:
    """The floor and cap are RECORDED per fold but do not veto a row at Stage A.

    The shipped rank is the plain mean in-sample ``vs_flat_dca_pct``. Reporting that
    honestly matters more than sounding stricter than the function is.
    """
    dates = _dates(200)
    # A row that is badly infeasible — 0% deployed, 95% drawdown — yet the best on IS.
    run = runner.run_published(
        dates,
        [100.0 + i for i in range(len(dates))],
        extra_z={"weekly_rsi": [0.0] * len(dates)},
        rails_fitter=_rails_fitter,
        evaluator=_evaluator_factory(
            {(): 1.0, ("weekly_rsi",): 9.0}, deployed_pct=0.0, drawdown_pct=95.0
        ),
        shape=runner.curve_shape(),
        search_names=("weekly_rsi",),
        objective=runner.objective(),
        label="infeasible",
    )
    assert run.mean_is_vs_flat_dca_pct == pytest.approx(9.0), (
        "the shipped Stage A rank does not veto on the floor or the cap"
    )
    assert run.feasible_folds == 0, "and the fold's infeasibility is still recorded"
    assert "does NOT gate" in runner.RANK_NOT_GATED_LABEL
    assert "not" in runner.RANK_NOT_GATED_LABEL.lower()


# --------------------------------------------------------------------------- #
# 5 + 6. Baseline row, and one per-extra probe per allowlist name
# --------------------------------------------------------------------------- #


def _fixture(runner: Any) -> tuple[Any, list[date], list[float], dict[str, list[float | None]]]:
    """Synthetic evaluator plus a z series for EVERY allowlist name.

    The per-extra table must cover the whole allowlist, so the fixture cannot carry z for
    only the three names the assertions happen to look at.
    """
    dates = _dates(200)
    prices = [100.0 + i for i in range(len(dates))]
    extra_z = {name: [0.0] * len(dates) for name in GOLD_MACRO_NAMES + GENERIC_TECHNICAL_NAMES}
    scores = {
        (): 1.0,
        ("weekly_rsi",): 5.0,
        ("sma_band",): 3.0,
        ("real_rate",): -2.0,
    }
    evaluator = _evaluator_factory(scores, _oos_date_set(dates))
    return evaluator, dates, prices, extra_z


def test_the_valuation_only_baseline_always_runs_and_is_recorded(runner: Any) -> None:
    evaluator, dates, prices, extra_z = _fixture(runner)
    baseline = runner.run_baseline(dates, prices, evaluator=evaluator, rails_fitter=_rails_fitter)
    assert baseline.enabled_extras == {}
    assert baseline.weights.valuation > 0.0
    assert baseline.mean_is_vs_flat_dca_pct == pytest.approx(1.0)
    assert baseline.num_evaluations == 2, "valuation 0.0 with no extras is the one invalid row"


def test_every_allowlist_name_gets_exactly_one_per_extra_probe_row(runner: Any) -> None:
    evaluator, dates, prices, extra_z = _fixture(runner)
    allowlist = GOLD_MACRO_NAMES + GENERIC_TECHNICAL_NAMES
    rows = runner.per_extra_probes(
        dates,
        prices,
        extra_z=extra_z,
        rails_fitter=_rails_fitter,
        evaluator=evaluator,
        shape=runner.curve_shape(),
        objective=runner.objective(),
        allowlist=allowlist,
        baseline_is=1.0,
        baseline_oos=-1.0,
    )
    probed = [row.name for row in rows]
    assert sorted(probed) == sorted(allowlist), "no allowlist name may go unreported"
    assert len(probed) == len(set(probed)), "one row per name, never two"
    by_name = {row.name: row for row in rows}
    assert by_name["weekly_rsi"].decision == "keep"
    assert by_name["weekly_rsi"].mean_is_vs_flat_dca_pct == pytest.approx(5.0)
    assert by_name["weekly_rsi"].delta_is_vs_flat_dca_pct == pytest.approx(4.0)
    assert by_name["weekly_rsi"].mean_oos_vs_flat_dca_pct == pytest.approx(-5.0)
    assert by_name["weekly_rsi"].delta_oos_vs_flat_dca_pct == pytest.approx(-4.0)
    assert by_name["real_rate"].decision == "flat", (
        "a one-name sweep shares its grid with the valuation-only row, so its best can never "
        "fall below the baseline — 'flat' (no keep earned) is the honest verdict, not 'drop'"
    )
    assert by_name["real_rate"].delta_is_vs_flat_dca_pct == pytest.approx(0.0)
    assert by_name["real_rate"].in_joint_sweep is False, (
        "a name outside the joint sweep must be marked, not silently presented as if it were in"
    )


def test_a_per_extra_probe_for_a_name_with_no_series_is_refused(runner: Any) -> None:
    evaluator, dates, prices, extra_z = _fixture(runner)
    without_gvz = {k: v for k, v in extra_z.items() if k != "gvz"}
    with pytest.raises(ValueError, match="without a built z series"):
        runner.per_extra_probes(
            dates,
            prices,
            extra_z=without_gvz,
            rails_fitter=_rails_fitter,
            evaluator=evaluator,
            shape=runner.curve_shape(),
            objective=runner.objective(),
            allowlist=("weekly_rsi", "gvz"),
            baseline_is=0.0,
            baseline_oos=0.0,
        )


def test_a_flat_delta_is_reported_as_flat_not_silently_kept(runner: Any) -> None:
    evaluator, dates, prices, extra_z = _fixture(runner)
    rows = runner.per_extra_probes(
        dates,
        prices,
        extra_z={**extra_z, "nfci": [0.0] * len(dates)},
        rails_fitter=_rails_fitter,
        evaluator=evaluator,
        shape=runner.curve_shape(),
        objective=runner.objective(),
        allowlist=("nfci",),
        baseline_is=1.0,
        baseline_oos=-1.0,
    )
    assert rows[0].delta_is_vs_flat_dca_pct == pytest.approx(0.0)
    assert rows[0].decision == "flat"


# --------------------------------------------------------------------------- #
# 7. Determinism
# --------------------------------------------------------------------------- #


def _synthetic_runs(runner: Any) -> tuple[Any, ...]:
    evaluator, dates, prices, extra_z = _fixture(runner)
    return (
        runner.run_published(
            dates,
            prices,
            extra_z=extra_z,
            rails_fitter=_rails_fitter,
            evaluator=evaluator,
            shape=runner.curve_shape(),
            search_names=("weekly_rsi", "sma_band", "real_rate"),
            objective=runner.objective(),
            label="joint",
        ),
        runner.run_baseline(dates, prices, evaluator=evaluator, rails_fitter=_rails_fitter),
    )


def _synthetic_plan(runner: Any) -> Any:
    return runner.partition_search_names(
        (
            runner.CoverageRow(name="weekly_rsi", searched=True, span_null_pct=1.0),
            runner.CoverageRow(
                name="gvz",
                searched=False,
                span_null_pct=20.6,
                worst_window_null_pct=82.5,
                worst_window="fold0_is",
            ),
        ),
        limit_pct=runner.NULL_COVERAGE_LIMIT_PCT,
    )


def test_two_identical_runs_serialize_byte_identically(runner: Any) -> None:
    def body() -> dict[str, Any]:
        return runner.payload(
            runs=_synthetic_runs(runner),
            plan=_synthetic_plan(runner),
            coverage=_synthetic_plan(runner).coverage,
            probes=(),
            allowlist=("weekly_rsi", "gvz"),
            projected_full_cost=runner.ProjectedCost(
                names=2,
                evaluations=3 * 3**2,
                ms_per_eval=33.0,
                hours=0.09,
            ),
        )

    first = json.dumps(body(), indent=2) + "\n"
    second = json.dumps(body(), indent=2) + "\n"
    assert first == second, "the artifact is a research record the owner diffs against itself"


def test_the_artifact_separates_in_sample_from_oos_and_carries_the_disclosures(
    runner: Any,
) -> None:
    body = runner.payload(
        runs=_synthetic_runs(runner),
        plan=_synthetic_plan(runner),
        coverage=_synthetic_plan(runner).coverage,
        probes=(),
        allowlist=("weekly_rsi", "gvz"),
        projected_full_cost=runner.ProjectedCost(
            names=2, evaluations=27, ms_per_eval=33.0, hours=0.09
        ),
    )
    assert set(body) >= {
        "symbol",
        "objective",
        "in_sample_label",
        "oos_label",
        "oos_is_degenerate",
        "oos_void_label",
        "floor_basis_label",
        "rank_not_gated_label",
        "profile_not_in_src_label",
        "cycle_windows_inert_label",
        "feasibility_note",
        "btc_sdca_reference_shape",
        "runs",
        "coverage",
        "per_extra",
    }
    for run in body["runs"]:
        assert set(run) >= {
            "label",
            "weights",
            "enabled_extras",
            "mean_is_vs_flat_dca_pct",
            "mean_oos_vs_flat_dca_pct",
            "num_evaluations",
            "search_names",
            "feasible_folds",
            "folds",
        }
        assert run["in_sample"] is True
        for fold in run["folds"]:
            assert set(fold) >= {
                "fold",
                "is_start",
                "is_end",
                "oos_start",
                "oos_end",
                "in_sample",
                "out_of_sample",
                "feasible",
            }
            assert set(fold["in_sample"]) >= {
                "vs_flat_dca_pct",
                "vs_lump_pct",
                "capital_deployed_pct",
                "capital_deployed_peak_pct",
                "max_drawdown_pct",
            }
    assert body["btc_sdca_reference_shape"] == dict(runner.BTC_SDCA_REFERENCE)
    assert body["projected_full_cost"]["names"] == 2
    assert "vs_flat_dca_pct" in body["oos_label"]
    assert "NOT" in body["oos_label"]


# --------------------------------------------------------------------------- #
# 8. Genuine failures are clean ValueErrors, and nothing live is touched
# --------------------------------------------------------------------------- #


def test_the_curve_is_the_shipped_no_trend_gold_curve_not_a_power_law(runner: Any) -> None:
    """Owner ruling: no power-law steer for gold, and generic log_linear/log_quadratic
    are out. The curve must come from the SHIPPED gold preset, resolved by name."""
    assert runner.CURVE_PRESET == "gold_reselect"
    shape = runner.curve_shape()
    assert shape.buy_max_rate == 35.0
    assert shape.buy_knee_risk == 60.0
    assert shape.sell_knee_risk == 65.0
    assert shape.sell_max_rate == 30.0
    assert shape.buy_mid_knee_risk is None and shape.sell_mid_knee_risk is None
    assert runner.CURVE_SOURCE, "the runner must name where its curve came from"
    assert "gold_reselect" in runner.CURVE_SOURCE


def test_the_rails_are_the_shipped_rolling_z_anchor_no_time_trend(runner: Any) -> None:
    """The valuation steer is the shipped rolling-z anchor — refit per fold, never a trend fit."""
    assert runner.RAILS_KIND == "rolling_z"
    assert runner.RAILS_WINDOW_DAYS == 90
    assert runner.RAILS_Z == 1.0
    model = runner.rails_fitter(
        [_dt.date(2020, 1, 1) + _dt.timedelta(days=i) for i in range(40)],
        [100.0 + i for i in range(40)],
    )
    assert model.window == 90 and model.z == 1.0
    for banned in ("btc_power_law", "log_linear", "log_quadratic"):
        assert banned not in runner.RAILS_LABEL


def test_the_profile_is_built_from_the_module_surface_and_says_so(runner: Any) -> None:
    """No gold profile exists in ``asset_profile.py``; the runner builds one and says why."""
    from digiquant.strategies.sdca import asset_profile

    factories = {
        name
        for name in dir(asset_profile.SdcaAssetProfile)
        if not name.startswith("_")
        and isinstance(inspect.getattr_static(asset_profile.SdcaAssetProfile, name), classmethod)
    }
    assert "btc_v1" in factories and "eth_research_v1" in factories
    assert not any("gold" in name for name in factories), (
        "if a gold factory ever ships, this test fails so the runner stops building its own"
    )
    profile = runner.gold_profile()
    assert profile.symbol == "GLD-USD"
    assert profile.risk_model == "rolling_z"
    assert profile.extra_indicators == GOLD_MACRO_NAMES + GENERIC_TECHNICAL_NAMES
    assert "asset_profile.py" in runner.PROFILE_NOT_IN_SRC_LABEL
    assert "no gold" in runner.PROFILE_NOT_IN_SRC_LABEL.lower()


def test_the_search_name_set_is_the_profile_allowlist_never_hand_picked(runner: Any) -> None:
    from digiquant.strategies.sdca.asset_profile import stage_a_search_names

    profile = runner.gold_profile()
    assert stage_a_search_names(profile) == GOLD_MACRO_NAMES + GENERIC_TECHNICAL_NAMES
    assert runner.declared_search_names(profile) == stage_a_search_names(profile)


def test_the_objective_does_not_consume_cycle_windows_and_that_is_stated(runner: Any) -> None:
    """``optimize_stage_a_by_backtest`` builds its own folds; there is no cycle-window
    parameter. ONE run is therefore correct, and the profile's required field is inert."""
    params = inspect.signature(optimize_stage_a_by_backtest).parameters
    assert "windows" not in params
    assert "cycle_windows" not in params
    assert "SdcaCycleWindows" not in inspect.getsource(optimize_stage_a_by_backtest)
    assert runner.SINGLE_RUN_BECAUSE_NO_CYCLE_WINDOWS is True
    assert "cycle" in runner.CYCLE_WINDOWS_INERT_LABEL.lower()
    assert "inert" in runner.CYCLE_WINDOWS_INERT_LABEL.lower()


def test_the_runner_writes_only_to_scratch_and_never_touches_settings_or_supabase(
    runner: Any,
) -> None:
    assert runner.OUT_PATH.parent == runner.DIGIQUANT_ROOT / ".scratch"
    source = RUNNER_PATH.read_text()
    for banned in ("settings.json", "push-supabase", "push_supabase", "nautilus"):
        assert banned not in source, f"the runner must never reference {banned!r}"
    assert "run_backtest" not in source, "the runner must not reimplement the buy/sell loop"


def test_the_runner_has_no_bare_assert_statements() -> None:
    source = RUNNER_PATH.read_text()
    assert "assert " not in source.replace("  # assert ", "")


def test_an_unknown_allowlist_name_is_a_clean_refusal(runner: Any) -> None:
    with pytest.raises(ValueError, match="unknown extra_indicators"):
        runner.profile_for(symbol="GLD-USD", extra_indicators=("not_an_indicator",))


# --------------------------------------------------------------------------- #
# 9. The shape comparison and the labelling discipline
# --------------------------------------------------------------------------- #


def test_the_reported_btc_sdca_shape_is_the_published_composite(runner: Any) -> None:
    assert dict(runner.BTC_SDCA_REFERENCE) == {
        "valuation": 1.0,
        "m2": 0.5,
        "dxy": 0.5,
        "weekly_macd": 0.5,
        "weekly_rsi": 0.25,
    }
    assert "shape comparison only" in runner.BTC_REFERENCE_LABEL
    assert "not a tuning target" in runner.BTC_REFERENCE_LABEL


def test_in_sample_and_oos_are_labelled_separately_everywhere(runner: Any) -> None:
    assert "IN-SAMPLE" in runner.IN_SAMPLE_LABEL
    assert "NOT" in runner.OOS_LABEL
    assert "used" in runner.OOS_LABEL.lower()
    assert runner.IN_SAMPLE_LABEL != runner.OOS_LABEL


def test_the_diagnostic_and_the_published_objective_are_never_blended(runner: Any) -> None:
    assert "DIFFERENT OBJECTIVE" in runner.NOT_THE_DIAGNOSTIC_LABEL
    assert "optimize_stage_a_weights" in runner.NOT_THE_DIAGNOSTIC_LABEL
    assert "cycle" in runner.NOT_THE_DIAGNOSTIC_LABEL.lower()
    assert "must not be blended" in runner.NOT_THE_DIAGNOSTIC_LABEL


def test_no_performance_claim_beyond_the_returned_metrics(runner: Any) -> None:
    """The console/report text must not assert a return, Sharpe or edge in prose."""
    for label in (
        runner.IN_SAMPLE_LABEL,
        runner.OOS_LABEL,
        runner.OBJECTIVE_LABEL,
        runner.RANK_NOT_GATED_LABEL,
        runner.FEASIBILITY_NOTE,
    ):
        lowered = label.lower()
        assert "beats" not in lowered
        assert "outperform" not in lowered
    assert "no performance claim" in runner.IN_SAMPLE_LABEL.lower()
