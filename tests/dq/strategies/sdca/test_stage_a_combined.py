"""Dual-timeframe Stage A weight search (long + medium cycle windows).

Leaf 3 of the SDCA research port from ``claude/sdca-develop-sync`` (DIG-1597).

This leaf is **additive only**. It lands the branch's dual-timeframe scoring
family — ``CombinedCycleOverlapScore``, ``CombinedStageAResult``,
``combined_cycle_overlap_score``, ``_floor_candidates``,
``optimize_stage_a_weights_combined`` and
``optimize_stage_a_weights_combined_multi_ratio`` — *alongside* develop's
single-timeframe ``optimize_stage_a_weights``. Nothing in the published Stage A
path moves: the new entry points are only reached by a caller that asks for them
by name, and the composite risk series they score is byte-identical to what
develop's search already builds.

Three discipline points this file pins hard:

* **The ``valuation`` → ``power_law`` rename is still deferred.** The branch
  renamed ``valuation_z`` → ``power_law_z``, ``valuation_grid`` →
  ``power_law_grid`` and ``SdcaCompositeWeights.valuation`` → ``.power_law``
  throughout this module. Develop still says ``valuation``, and that rename is
  a breaking change across every SDCA caller (stage_a, optimize, weight_search,
  the MCP weight-fit tool), so the ported defs here use develop's spelling.
  ``TestDevelopApiUnchanged`` fails if anyone "helpfully" copies the branch's
  names in.
* **The medium window set is a caller-supplied ``SdcaCycleWindows``**, not a
  new ``btc_medium_term_v1()`` constructor. Develop has no such constructor —
  the branch added one together with a ``cycle_windows.py`` change that also
  widened the published ``2025_peak`` window, and that is a different leaf.
  Scoring the two timeframes is separable from *which* windows define them, so
  every test below builds synthetic long/medium sets. Nothing here depends on
  the branch's historical window data.
* **The shared objective is a weighted sum, not a gate.** ``long_weight`` /
  ``medium_weight`` make a candidate weak on long-term overlap pay for it in
  the combined objective; they never disqualify it. That is what keeps a grid
  search's feasible set non-empty, and it is why the ratio can be swept
  (``optimize_stage_a_weights_combined_multi_ratio``) without any ratio making
  the search infeasible.

All inputs are deterministic synthetic series — no seeds, no fixtures to
regenerate — so every number below is reproducible from one command:

    PYTHONPATH="$PWD/digiquant/src" python -m pytest \
        tests/dq/strategies/sdca/test_stage_a_combined.py

The scoring arithmetic the tests rest on: ``cycle_overlap_score`` returns
``objective = spread + 25 * (trough_in_accumulate_frac + peak_in_distribute_frac)``
where spread is mean peak risk minus mean trough risk, and risk is the
composite-z mapped through ``risk = 50 - composite_z * 50 / 3``. Blending
indicators of equal magnitude ``z`` therefore drives ``v/T`` (valuation weight
over total weight), so ``trough_frac`` is 1 iff ``v/T >= 0.3`` and ``peak_frac``
is 1 iff ``v/T >= 0.6`` — which is what makes the floor tests below land on an
exact expected weight rather than "some winner".
"""

from __future__ import annotations

import datetime as _dt
import inspect
from datetime import date

import pytest
from digiquant.strategies.sdca import stage_a as stage_a_module
from digiquant.strategies.sdca.cycle_windows import (
    CycleKind,
    CycleWindow,
    SdcaCycleWindows,
)
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.stage_a import (
    CombinedCycleOverlapScore,
    CombinedStageAResult,
    CycleOverlapScore,
    combined_cycle_overlap_score,
    cycle_overlap_score,
    optimize_stage_a_weights,
    optimize_stage_a_weights_combined,
    optimize_stage_a_weights_combined_multi_ratio,
    risk_from_weighted_z,
)

pytestmark = pytest.mark.unit

# develop's stage_a exports, before this leaf.
_DEVELOP_ALL = {
    "ACCUMULATE_RISK_MAX",
    "DISTRIBUTE_RISK_MIN",
    "CycleOverlapScore",
    "StageAResult",
    "cycle_overlap_score",
    "optimize_stage_a_weights",
    "risk_from_weighted_z",
}
_LEAF3_ALL = {
    "CombinedCycleOverlapScore",
    "CombinedStageAResult",
    "combined_cycle_overlap_score",
    "optimize_stage_a_weights_combined",
    "optimize_stage_a_weights_combined_multi_ratio",
}


def _dates(n: int, start: date) -> list[date]:
    return [start + _dt.timedelta(days=i) for i in range(n)]


def _params(fn) -> list[str]:
    return list(inspect.signature(fn).parameters)


def _long_medium_windows(dates: list[date]) -> tuple[SdcaCycleWindows, SdcaCycleWindows]:
    """Two disjoint trough/peak pairs at different points of the sample."""
    long_windows = SdcaCycleWindows(
        windows=(
            CycleWindow(name="t_long", kind=CycleKind.TROUGH, start=dates[0], end=dates[19]),
            CycleWindow(name="p_long", kind=CycleKind.PEAK, start=dates[100], end=dates[119]),
        )
    )
    medium_windows = SdcaCycleWindows(
        windows=(
            CycleWindow(name="t_medium", kind=CycleKind.TROUGH, start=dates[40], end=dates[49]),
            CycleWindow(name="p_medium", kind=CycleKind.PEAK, start=dates[60], end=dates[69]),
        )
    )
    return long_windows, medium_windows


def _perfect_extra(dates: list[date], active_days: set[date], sign_days: set[date]) -> list[float]:
    """+3 on ``sign_days``, -3 on the other ``active_days``, 0.0 elsewhere."""
    return [3.0 if d in sign_days else (-3.0 if d in active_days else 0.0) for d in dates]


class TestDevelopApiUnchanged:
    """This leaf must not disturb what develop already publishes."""

    def test_develop_exports_are_all_still_exported(self) -> None:
        assert _DEVELOP_ALL <= set(stage_a_module.__all__)

    def test_only_the_six_new_names_were_added(self) -> None:
        assert set(stage_a_module.__all__) == _DEVELOP_ALL | _LEAF3_ALL

    def test_cycle_overlap_score_signature_is_unchanged(self) -> None:
        assert _params(cycle_overlap_score) == [
            "dates",
            "risk",
            "windows",
            "accumulate_risk_max",
            "distribute_risk_min",
        ]

    def test_risk_from_weighted_z_still_speaks_valuation(self) -> None:
        """The deferred rename must not have leaked into the shared helper."""
        assert _params(risk_from_weighted_z) == [
            "dates",
            "valuation_z",
            "extra_z",
            "weights",
        ]

    def test_optimize_stage_a_weights_keeps_its_single_timeframe_shape(self) -> None:
        """No ``long_windows``/``medium_windows`` on develop's search.

        The branch's version of this function is a different function. Widening
        it would silently repoint every existing caller at a dual-timeframe
        objective, which is a behaviour change with a measured delta attached
        to it — not a port.
        """
        assert _params(optimize_stage_a_weights) == [
            "dates",
            "valuation_z",
            "extra_z",
            "windows",
            "search_names",
            "grid",
            "valuation_grid",
            "require_extras",
        ]

    def test_weight_complexity_tiebreak_still_reads_valuation(self) -> None:
        """Develop's parsimony tie-break is unchanged in the shared helper."""
        from digiquant.strategies.sdca.stage_a import _weight_complexity

        assert _weight_complexity(SdcaCompositeWeights(valuation=0.25)) == (0, -0.25)
        assert _weight_complexity(
            SdcaCompositeWeights(valuation=0.25, weekly_rsi=0.5, sma_band=0.5)
        ) == (2, -0.25)

    def test_the_branch_valuation_to_power_law_rename_is_still_deferred(self) -> None:
        assert "power_law" not in SdcaCompositeWeights.model_fields
        for fn in (
            cycle_overlap_score,
            risk_from_weighted_z,
            optimize_stage_a_weights,
            combined_cycle_overlap_score,
            optimize_stage_a_weights_combined,
            optimize_stage_a_weights_combined_multi_ratio,
        ):
            assert "power_law" not in "".join(_params(fn)), fn.__name__

    def test_cycle_overlap_score_objective_formula_is_unchanged(self) -> None:
        """The shared scorer both timeframes delegate to still uses +25 x bands."""
        dates = _dates(60, date(2020, 1, 1))
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[19]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[40], end=dates[59]),
            )
        )
        # All four trough days are cheap, three of four peak days are rich.
        risk = [10.0] * 20 + [50.0] * 20 + [90.0] * 17 + [50.0] * 3
        score = cycle_overlap_score(dates, risk, windows)
        assert isinstance(score, CycleOverlapScore)
        assert score.trough_in_accumulate_frac == pytest.approx(1.0)
        assert score.peak_in_distribute_frac == pytest.approx(17 / 20)
        assert score.objective == pytest.approx(
            score.spread + 25.0 * (score.trough_in_accumulate_frac + score.peak_in_distribute_frac)
        )


class TestCombinedCycleOverlapScore:
    def test_combined_score_matches_manual_weighted_sum(self) -> None:
        start = date(2020, 1, 1)
        # 120 days: ``_long_medium_windows`` puts the long peak at dates[100:120].
        dates = _dates(120, start)
        long_windows, medium_windows = _long_medium_windows(dates)
        risk = [10.0 if d <= date(2020, 1, 20) else 90.0 for d in dates]
        combined = combined_cycle_overlap_score(
            dates, risk, long_windows, medium_windows, long_weight=3.0, medium_weight=1.0
        )
        assert isinstance(combined, CombinedCycleOverlapScore)
        manual_long = cycle_overlap_score(dates, risk, long_windows)
        manual_medium = cycle_overlap_score(dates, risk, medium_windows)
        assert combined.long == manual_long
        assert combined.medium == manual_medium
        assert combined.long_weight == pytest.approx(3.0)
        assert combined.medium_weight == pytest.approx(1.0)
        assert combined.objective == pytest.approx(
            3.0 * manual_long.objective + 1.0 * manual_medium.objective
        )

    def test_the_ratio_is_a_weight_not_a_gate(self) -> None:
        """A medium-only series still scores — it just pays in the objective.

        This is the property that keeps a ratio sweep feasible: no ratio can
        disqualify every candidate, so ``optimize_stage_a_weights_combined``
        always has a winner to find.
        """
        start = date(2020, 1, 1)
        dates = _dates(120, start)
        long_windows, medium_windows = _long_medium_windows(dates)
        # Scores beautifully on medium, is flat on long.
        medium_only = [10.0 if dates[40] <= d <= dates[49] else 90.0 for d in dates]
        combined = combined_cycle_overlap_score(
            dates, medium_only, long_windows, medium_windows, long_weight=1000.0
        )
        assert combined.medium.objective > 0.0
        assert combined.long.objective < combined.medium.objective
        assert combined.objective == pytest.approx(
            1000.0 * combined.long.objective + combined.medium.objective
        )

    def test_band_thresholds_reach_both_timeframes(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(120, start)
        long_windows, medium_windows = _long_medium_windows(dates)
        # Trough risk 40 and peak risk 70: outside the default 35/80 bands.
        risk = [40.0 if d <= dates[19] else 70.0 for d in dates]
        default = combined_cycle_overlap_score(dates, risk, long_windows, medium_windows)
        assert default.long.trough_in_accumulate_frac == pytest.approx(0.0)
        assert default.long.peak_in_distribute_frac == pytest.approx(0.0)
        widened = combined_cycle_overlap_score(
            dates,
            risk,
            long_windows,
            medium_windows,
            accumulate_risk_max=50.0,
            distribute_risk_min=60.0,
        )
        assert widened.long.trough_in_accumulate_frac == pytest.approx(1.0)
        assert widened.long.peak_in_distribute_frac == pytest.approx(1.0)
        assert widened.objective > default.objective

    def test_rejects_nonpositive_weights(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(30, start)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=start, end=dates[9]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[20], end=dates[29]),
            )
        )
        risk = [50.0] * len(dates)
        with pytest.raises(ValueError, match="positive"):
            combined_cycle_overlap_score(dates, risk, windows, windows, long_weight=0.0)
        with pytest.raises(ValueError, match="positive"):
            combined_cycle_overlap_score(dates, risk, windows, windows, medium_weight=-1.0)

    def test_unscorable_timeframe_raises_rather_than_scoring_zero(self) -> None:
        """A window set that misses the sample is an error, not a silent 0."""
        dates = _dates(90, date(2020, 1, 1))
        # One window lands in the sample, its partner never does — so that
        # timeframe has a trough bucket but an empty peak bucket.
        half_missing = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[19]),
                CycleWindow(
                    name="p", kind=CycleKind.PEAK, start=date(2021, 1, 1), end=date(2021, 2, 1)
                ),
            )
        )
        in_sample = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t2", kind=CycleKind.TROUGH, start=dates[40], end=dates[49]),
                CycleWindow(name="p2", kind=CycleKind.PEAK, start=dates[60], end=dates[69]),
            )
        )
        with pytest.raises(ValueError, match="do not overlap"):
            combined_cycle_overlap_score(dates, [50.0] * len(dates), half_missing, in_sample)


class TestOptimizeStageAWeightsCombined:
    def test_the_ratio_controls_which_timeframe_wins(self) -> None:
        dates = _dates(120, date(2020, 1, 1))
        long_windows, medium_windows = _long_medium_windows(dates)
        long_days = set(dates[0:20]) | set(dates[100:120])
        medium_days = set(dates[40:50]) | set(dates[60:70])
        # Each extra is perfect on its own timeframe and silent on the other.
        weekly_rsi = _perfect_extra(dates, long_days, set(dates[0:20]))
        sma_band = _perfect_extra(dates, medium_days, set(dates[40:50]))
        zeros = [0.0] * len(dates)

        long_favored = optimize_stage_a_weights_combined(
            dates,
            valuation_z=zeros,
            extra_z={"weekly_rsi": weekly_rsi, "sma_band": sma_band},
            long_windows=long_windows,
            medium_windows=medium_windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 1.0),
            valuation_grid=(0.0,),
            long_weight=100.0,
            medium_weight=1.0,
        )
        assert isinstance(long_favored, CombinedStageAResult)
        assert long_favored.weights.weekly_rsi == pytest.approx(1.0)
        assert long_favored.weights.sma_band == pytest.approx(0.0)
        assert long_favored.score.long.objective > long_favored.score.medium.objective

        medium_favored = optimize_stage_a_weights_combined(
            dates,
            valuation_z=zeros,
            extra_z={"weekly_rsi": weekly_rsi, "sma_band": sma_band},
            long_windows=long_windows,
            medium_windows=medium_windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 1.0),
            valuation_grid=(0.0,),
            long_weight=1.0,
            medium_weight=100.0,
        )
        assert medium_favored.weights.weekly_rsi == pytest.approx(0.0)
        assert medium_favored.weights.sma_band == pytest.approx(1.0)

    def test_the_same_risk_series_feeds_both_timeframes(self) -> None:
        """One composite, two scorers — not a per-timeframe blend."""
        dates = _dates(90, date(2020, 1, 1))
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[24]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[60], end=dates[89]),
            )
        )
        valuation_z = [3.0 if d <= dates[24] else -3.0 for d in dates]
        zeros = [0.0] * len(dates)
        result = optimize_stage_a_weights_combined(
            dates,
            valuation_z=valuation_z,
            extra_z={"weekly_rsi": zeros},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi",),
            grid=(0.0, 1.0),
            valuation_grid=(1.0,),
        )
        # Both scorers see the identical series, so both sub-scores are equal.
        assert result.score.long == result.score.medium
        # valuation alone scores a perfect spread + both bands; enabling a zero
        # extra only dilutes it.
        assert result.weights.valuation == pytest.approx(1.0)
        assert result.weights.weekly_rsi == pytest.approx(0.0)

    def test_floor_grid_never_selects_zero_for_an_enabled_indicator(self) -> None:
        dates = _dates(90, date(2020, 1, 1))
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[24]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[60], end=dates[89]),
            )
        )
        valuation_z = [3.0 if d <= dates[24] else -3.0 for d in dates]
        zeros = [0.0] * len(dates)
        grid = (0.0, 0.25, 0.5, 0.75, 1.0)

        # valuation_grid is pinned to a single value here: when valuation is the
        # sole non-zero contributor its own weight cancels out of the weighted
        # average, so searching it would only add scoring ties.
        without_floor = optimize_stage_a_weights_combined(
            dates,
            valuation_z=valuation_z,
            extra_z={"weekly_rsi": zeros, "sma_band": zeros},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=grid,
            valuation_grid=(1.0,),
        )
        assert without_floor.weights.weekly_rsi == pytest.approx(0.0)
        assert without_floor.weights.sma_band == pytest.approx(0.0)
        assert without_floor.weights.valuation == pytest.approx(1.0)

        with_floor = optimize_stage_a_weights_combined(
            dates,
            valuation_z=valuation_z,
            extra_z={"weekly_rsi": zeros, "sma_band": zeros},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=grid,
            valuation_grid=grid,
            min_weight_floor=0.25,
        )
        # Every search name stays enabled at the floor, and the floor — not a
        # parsimony tie-break — is what keeps them there.
        assert with_floor.weights.weekly_rsi == pytest.approx(0.25)
        assert with_floor.weights.sma_band == pytest.approx(0.25)
        assert set(with_floor.weights.enabled_extras()) == {"weekly_rsi", "sma_band"}
        assert with_floor.weights.valuation == pytest.approx(1.0)
        assert with_floor.score.objective < without_floor.score.objective

    def test_a_floor_of_zero_is_the_same_as_no_floor(self) -> None:
        """``0.0`` means "no floor", documented rather than silently honoured."""
        dates = _dates(90, date(2020, 1, 1))
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[24]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[60], end=dates[89]),
            )
        )
        valuation_z = [3.0 if d <= dates[24] else -3.0 for d in dates]
        zeros = [0.0] * len(dates)
        grid = (0.0, 0.25, 0.5, 1.0)
        kwargs = dict(
            dates=dates,
            valuation_z=valuation_z,
            extra_z={"weekly_rsi": zeros, "sma_band": zeros},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=grid,
            valuation_grid=(1.0,),
        )
        none_floor = optimize_stage_a_weights_combined(**kwargs)
        zero_floor = optimize_stage_a_weights_combined(**kwargs, min_weight_floor=0.0)
        assert zero_floor == none_floor

    def test_a_floor_above_the_grid_adds_its_own_candidate(self) -> None:
        """A floor outside the grid still has to be reachable."""
        dates = _dates(90, date(2020, 1, 1))
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[24]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[60], end=dates[89]),
            )
        )
        valuation_z = [3.0 if d <= dates[24] else -3.0 for d in dates]
        zeros = [0.0] * len(dates)

        # 0.4 is in no grid value, so _floor_candidates has to add it — and it
        # leads the tuple, so a tie falls to the allocation the caller asked for.
        assert stage_a_module._floor_candidates((0.0, 0.1), 0.4) == (0.4, 0.1)
        assert stage_a_module._floor_candidates((0.0, 0.1), 0.1) == (0.1,)
        assert stage_a_module._floor_candidates((0.0, 0.1), None) == (0.0, 0.1)

        # 0.0 leaves the grid entirely, so the extra is enabled either way.
        result = optimize_stage_a_weights_combined(
            dates,
            valuation_z=valuation_z,
            extra_z={"weekly_rsi": zeros},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi",),
            grid=(0.0, 0.1),
            valuation_grid=(1.0,),
            min_weight_floor=0.4,
        )
        # A flat extra only dilutes, so 0.1 legitimately outscores 0.4 here —
        # what the floor guarantees is that neither of them is zero.
        assert result.weights.weekly_rsi in (0.1, 0.4)
        assert 0.0 not in result.weights.enabled_extras().values()

    def test_a_negative_floor_cannot_produce_a_negative_weight(self) -> None:
        """``SdcaCompositeWeights`` is ``ge=0.0``, so a bad floor is skipped."""
        dates = _dates(90, date(2020, 1, 1))
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[24]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[60], end=dates[89]),
            )
        )
        valuation_z = [3.0 if d <= dates[24] else -3.0 for d in dates]
        zeros = [0.0] * len(dates)
        result = optimize_stage_a_weights_combined(
            dates,
            valuation_z=valuation_z,
            extra_z={"weekly_rsi": zeros},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi",),
            grid=(0.0, 0.5, 1.0),
            valuation_grid=(1.0,),
            min_weight_floor=-0.5,
        )
        assert result.weights.weekly_rsi == pytest.approx(0.0)
        assert min(result.weights.model_dump().values()) >= 0.0

    def test_raises_when_no_candidate_is_scorable(self) -> None:
        dates = _dates(60, date(2020, 1, 1))
        offsample = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t", kind=CycleKind.TROUGH, start=date(2010, 1, 1), end=date(2010, 2, 1)
                ),
                CycleWindow(
                    name="p", kind=CycleKind.PEAK, start=date(2010, 6, 1), end=date(2010, 7, 1)
                ),
            )
        )
        with pytest.raises(ValueError, match="no valid combined Stage A weight combinations"):
            optimize_stage_a_weights_combined(
                dates,
                valuation_z=[0.0] * len(dates),
                extra_z={},
                long_windows=offsample,
                medium_windows=offsample,
                search_names=(),
            )

    def test_missing_extra_series_skips_that_combo_not_the_search(self) -> None:
        dates = _dates(90, date(2020, 1, 1))
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[24]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[60], end=dates[89]),
            )
        )
        valuation_z = [3.0 if d <= dates[24] else -3.0 for d in dates]
        result = optimize_stage_a_weights_combined(
            dates,
            valuation_z=valuation_z,
            extra_z={},  # weekly_rsi requested but no series present
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi",),
            grid=(0.0, 1.0),
            valuation_grid=(1.0,),
        )
        assert result.weights.weekly_rsi == pytest.approx(0.0)
        assert result.weights.valuation == pytest.approx(1.0)


class TestOptimizeStageAWeightsCombinedMultiRatio:
    def test_matches_one_single_ratio_run_per_ratio(self) -> None:
        dates = _dates(90, date(2020, 1, 1))
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[24]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[60], end=dates[89]),
            )
        )
        valuation_z = [3.0 if d <= dates[24] else -3.0 for d in dates]
        weekly_rsi = [-3.0 if d <= dates[24] else 3.0 for d in dates]
        ratios = ((2.0, 1.0), (3.0, 1.0), (5.0, 1.0))
        kwargs = dict(
            dates=dates,
            valuation_z=valuation_z,
            extra_z={"weekly_rsi": weekly_rsi},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi",),
            grid=(0.0, 0.5, 1.0),
            valuation_grid=(0.0, 0.5, 1.0),
        )

        multi = optimize_stage_a_weights_combined_multi_ratio(**kwargs, ratios=ratios)
        assert set(multi.keys()) == set(ratios)
        for lw, mw in ratios:
            single = optimize_stage_a_weights_combined(**kwargs, long_weight=lw, medium_weight=mw)
            got = multi[(lw, mw)]
            assert got.weights == single.weights
            assert got.score.objective == pytest.approx(single.score.objective)
            assert got.score.long_weight == pytest.approx(lw)
            assert got.score.medium_weight == pytest.approx(mw)
            assert got.score.long == single.score.long
            assert got.score.medium == single.score.medium

    def test_candidates_are_counted_once_not_once_per_ratio(self) -> None:
        """The whole point of the single pass: N ratios cost one search."""
        dates = _dates(90, date(2020, 1, 1))
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[24]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[60], end=dates[89]),
            )
        )
        valuation_z = [3.0 if d <= dates[24] else -3.0 for d in dates]
        zeros = [0.0] * len(dates)
        kwargs = dict(
            dates=dates,
            valuation_z=valuation_z,
            extra_z={"weekly_rsi": zeros, "sma_band": zeros},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 0.5, 1.0),
            valuation_grid=(0.0, 0.5, 1.0),
        )
        ratios = ((2.0, 1.0), (3.0, 1.0), (5.0, 1.0))
        multi = optimize_stage_a_weights_combined_multi_ratio(**kwargs, ratios=ratios)
        single = optimize_stage_a_weights_combined(**kwargs, long_weight=2.0, medium_weight=1.0)
        for result in multi.values():
            assert result.num_evaluations == single.num_evaluations

    def test_respects_the_diversification_floor(self) -> None:
        dates = _dates(90, date(2020, 1, 1))
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[24]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[60], end=dates[89]),
            )
        )
        valuation_z = [3.0 if d <= dates[24] else -3.0 for d in dates]
        zeros = [0.0] * len(dates)
        grid = (0.0, 0.25, 0.5, 0.75, 1.0)
        multi = optimize_stage_a_weights_combined_multi_ratio(
            dates,
            valuation_z=valuation_z,
            extra_z={"weekly_rsi": zeros, "sma_band": zeros},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=grid,
            valuation_grid=grid,
            ratios=((2.0, 1.0), (5.0, 1.0)),
            min_weight_floor=0.25,
        )
        for result in multi.values():
            assert result.weights.weekly_rsi == pytest.approx(0.25)
            assert result.weights.sma_band == pytest.approx(0.25)
            assert result.weights.valuation == pytest.approx(1.0)

    def test_a_ratio_can_select_a_different_winner(self) -> None:
        """The sweep is not cosmetic — the ratio changes the answer."""
        dates = _dates(120, date(2020, 1, 1))
        long_windows, medium_windows = _long_medium_windows(dates)
        long_days = set(dates[0:20]) | set(dates[100:120])
        medium_days = set(dates[40:50]) | set(dates[60:70])
        weekly_rsi = _perfect_extra(dates, long_days, set(dates[0:20]))
        sma_band = _perfect_extra(dates, medium_days, set(dates[40:50]))
        multi = optimize_stage_a_weights_combined_multi_ratio(
            dates,
            valuation_z=[0.0] * len(dates),
            extra_z={"weekly_rsi": weekly_rsi, "sma_band": sma_band},
            long_windows=long_windows,
            medium_windows=medium_windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 1.0),
            valuation_grid=(0.0,),
            ratios=((5.0, 1.0), (1.0, 5.0)),
        )
        assert multi[(5.0, 1.0)].weights.weekly_rsi == pytest.approx(1.0)
        assert multi[(5.0, 1.0)].weights.sma_band == pytest.approx(0.0)
        assert multi[(1.0, 5.0)].weights.weekly_rsi == pytest.approx(0.0)
        assert multi[(1.0, 5.0)].weights.sma_band == pytest.approx(1.0)

    def test_rejects_empty_or_nonpositive_ratios(self) -> None:
        dates = _dates(30, date(2020, 1, 1))
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[9]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[20], end=dates[29]),
            )
        )
        kwargs = dict(
            dates=dates,
            valuation_z=[0.0] * len(dates),
            extra_z={},
            long_windows=windows,
            medium_windows=windows,
            search_names=(),
        )
        with pytest.raises(ValueError, match="non-empty"):
            optimize_stage_a_weights_combined_multi_ratio(**kwargs, ratios=())
        with pytest.raises(ValueError, match="positive"):
            optimize_stage_a_weights_combined_multi_ratio(**kwargs, ratios=((0.0, 1.0),))
        with pytest.raises(ValueError, match="positive"):
            optimize_stage_a_weights_combined_multi_ratio(**kwargs, ratios=((1.0, -0.5),))

    def test_raises_when_no_candidate_is_scorable(self) -> None:
        dates = _dates(60, date(2020, 1, 1))
        offsample = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t", kind=CycleKind.TROUGH, start=date(2010, 1, 1), end=date(2010, 2, 1)
                ),
                CycleWindow(
                    name="p", kind=CycleKind.PEAK, start=date(2010, 6, 1), end=date(2010, 7, 1)
                ),
            )
        )
        with pytest.raises(ValueError, match="no valid combined Stage A weight combinations"):
            optimize_stage_a_weights_combined_multi_ratio(
                dates,
                valuation_z=[0.0] * len(dates),
                extra_z={},
                long_windows=offsample,
                medium_windows=offsample,
                search_names=(),
                ratios=((3.0, 1.0),),
            )
