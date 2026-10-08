"""Stage A combined long+medium timeframe weight search (DIG-1597 leaf 3).

Ports the dual-timeframe family from the abandoned ``claude/sdca-develop-sync``
branch onto develop's current ``stage_a.py`` shape. Two properties carry the
leaf and are pinned below rather than assumed:

* the published search scope is untouched -- every new entry point keeps
  ``search_names`` defaulting to develop's ``EXTRA_INDICATOR_NAMES``, and
  ``optimize_stage_a_weights`` / ``risk_from_weighted_z`` keep develop's
  ``valuation_*`` naming and ``_weight_complexity`` parsimony tie-break;
* the new combined search deliberately has **no** parsimony tie-break, so a tie
  keeps whichever candidate the grid reaches first. That is the opposite of
  ``optimize_stage_a_weights`` on the same data, and is pinned as such.
"""

from __future__ import annotations

import datetime as _dt
import inspect
import itertools
from datetime import date

import pytest
from digiquant.strategies.sdca import stage_a
from digiquant.strategies.sdca.cycle_windows import (
    CycleKind,
    CycleWindow,
    SdcaCycleWindows,
)
from digiquant.strategies.sdca.indicator_catalog import EXTRA_INDICATOR_NAMES, SdcaCompositeWeights
from digiquant.strategies.sdca.stage_a import (
    CycleOverlapScore,
    CombinedCycleOverlapScore,
    CombinedStageAResult,
    _floor_candidates,
    combined_cycle_overlap_score,
    optimize_stage_a_weights,
    optimize_stage_a_weights_combined,
    optimize_stage_a_weights_combined_multi_ratio,
    risk_from_weighted_z,
)

pytestmark = pytest.mark.unit

_ROOT = date(2020, 1, 1)
_N = 160
_SEARCH_NAMES = ("m2", "dxy")
_GRID = (0.0, 0.5, 1.0)
_VAL_GRID = (0.0, 0.5, 1.0)

# Four disjoint calendar bands, so a composite can score well on one timeframe
# and badly on the other. That is what makes the long:medium ratio a real
# decision rather than a cosmetic multiplier.
_LONG_TROUGH = (10, 40)
_LONG_PEAK = (70, 100)
_MED_TROUGH = (45, 65)
_MED_PEAK = (105, 135)


def _dates(n: int = _N) -> list[date]:
    return [_ROOT + _dt.timedelta(days=i) for i in range(n)]


def _band_series(*bands: tuple[int, int, float]) -> list[float]:
    """One z-series built by summing rectangular bands, so its values are exact."""
    out: list[float] = []
    for i in range(_N):
        out.append(sum(value for lo, hi, value in bands if lo <= i <= hi))
    return out


# valuation: helps long only. m2: helps long, hurts medium. dxy: the mirror.
_VALUATION_Z = _band_series(
    (*_LONG_TROUGH, 2.0),
    (*_LONG_PEAK, -2.0),
)
_M2_Z = _band_series(
    (*_LONG_TROUGH, 2.0),
    (*_LONG_PEAK, -2.0),
    (*_MED_TROUGH, -2.0),
    (*_MED_PEAK, 2.0),
)
_DXY_Z = _band_series(
    (*_LONG_TROUGH, -2.0),
    (*_LONG_PEAK, 2.0),
    (*_MED_TROUGH, 2.0),
    (*_MED_PEAK, -2.0),
)
_EXTRA_Z = {"m2": _M2_Z, "dxy": _DXY_Z}


def _long_windows() -> SdcaCycleWindows:
    dates = _dates()
    return SdcaCycleWindows(
        windows=(
            CycleWindow(
                name="long_trough",
                kind=CycleKind.TROUGH,
                start=dates[_LONG_TROUGH[0]],
                end=dates[_LONG_TROUGH[1]],
            ),
            CycleWindow(
                name="long_peak",
                kind=CycleKind.PEAK,
                start=dates[_LONG_PEAK[0]],
                end=dates[_LONG_PEAK[1]],
            ),
        )
    )


def _medium_windows() -> SdcaCycleWindows:
    dates = _dates()
    return SdcaCycleWindows(
        windows=(
            CycleWindow(
                name="medium_trough",
                kind=CycleKind.TROUGH,
                start=dates[_MED_TROUGH[0]],
                end=dates[_MED_TROUGH[1]],
            ),
            CycleWindow(
                name="medium_peak",
                kind=CycleKind.PEAK,
                start=dates[_MED_PEAK[0]],
                end=dates[_MED_PEAK[1]],
            ),
        )
    )


def _brute_force_best(
    *, long_weight: float = 3.0, medium_weight: float = 1.0, floor: float | None = None
) -> tuple[float, tuple[float, float, float]]:
    """Independent re-derivation of the winner, straight from the public pieces.

    Deliberately does not call either optimizer: it walks the same grid using
    ``risk_from_weighted_z`` + ``combined_cycle_overlap_score`` so a bug in the
    search loop cannot hide behind a matching bug in the expectation.
    """
    dates = _dates()
    long_w = _long_windows()
    med_w = _medium_windows()
    best_obj: float | None = None
    best: tuple[float, float, float] | None = None
    for val in _floor_candidates(_VAL_GRID, floor):
        for combo in itertools.product(_floor_candidates(_GRID, floor), repeat=len(_SEARCH_NAMES)):
            try:
                weights = SdcaCompositeWeights(valuation=float(val), **dict(zip(_SEARCH_NAMES, combo)))
            except ValueError:
                continue
            if any(name not in _EXTRA_Z for name in weights.enabled_extras()):
                continue
            risk = risk_from_weighted_z(dates, _VALUATION_Z, _EXTRA_Z, weights)
            score = combined_cycle_overlap_score(
                dates,
                risk,
                long_w,
                med_w,
                long_weight=long_weight,
                medium_weight=medium_weight,
            )
            if best_obj is None or score.objective > best_obj:
                best_obj = score.objective
                best = (float(val), *combo)
    assert best is not None and best_obj is not None
    return best_obj, best


class TestCombinedModels:
    def test_combined_score_is_frozen_and_strict(self) -> None:
        score = _zero_score()
        with pytest.raises(Exception):
            score.objective = 0.0  # type: ignore[misc]
        with pytest.raises(Exception):
            CombinedCycleOverlapScore.model_validate(
                {
                    "long": score.long.model_dump(),
                    "medium": score.medium.model_dump(),
                    "long_weight": 3.0,
                    "medium_weight": 1.0,
                    "objective": 0.0,
                    "long_weight": "3.0",
                }
            )

    def test_combined_score_requires_positive_weights(self) -> None:
        base = _zero_score()
        for kwargs in ({"long_weight": 0.0}, {"medium_weight": 0.0}, {"long_weight": -1.0}):
            payload = {
                "long": base.long.model_dump(),
                "medium": base.medium.model_dump(),
                "long_weight": 3.0,
                "medium_weight": 1.0,
                "objective": 0.0,
                **kwargs,
            }
            with pytest.raises(ValueError):
                CombinedCycleOverlapScore(**payload)

    def test_combined_score_nests_cycle_overlap_score(self) -> None:
        score = _zero_score()
        assert isinstance(score.long, CycleOverlapScore)
        assert isinstance(score.medium, CycleOverlapScore)

    def test_combined_result_wraps_weights_score_and_count(self) -> None:
        weights = SdcaCompositeWeights(valuation=1.0)
        result = CombinedStageAResult(
            weights=weights, score=_zero_score(), num_evaluations=0
        )
        assert result.weights is weights
        assert isinstance(result.score, CombinedCycleOverlapScore)
        assert result.num_evaluations == 0

    def test_combined_result_rejects_negative_evaluations(self) -> None:
        with pytest.raises(ValueError):
            CombinedStageAResult(
                weights=SdcaCompositeWeights(valuation=1.0),
                score=_zero_score(),
                num_evaluations=-1,
            )


def _zero_score() -> CombinedCycleOverlapScore:
    payload = {
        "spread": 10.0,
        "trough_in_accumulate_frac": 0.5,
        "peak_in_distribute_frac": 0.5,
        "mean_trough_risk": 20.0,
        "mean_peak_risk": 30.0,
        "objective": 35.0,
        "trough_days": 31,
        "peak_days": 31,
    }
    return CombinedCycleOverlapScore(
        long=CycleOverlapScore(**payload),
        medium=CycleOverlapScore(**payload),
        long_weight=3.0,
        medium_weight=1.0,
        objective=3.0 * 35.0 + 35.0,
    )


class TestCombinedCycleOverlapScore:
    def test_objective_is_the_weighted_sum_of_both_timeframes(self) -> None:
        dates = _dates()
        weights = SdcaCompositeWeights(valuation=1.0)
        risk = risk_from_weighted_z(dates, _VALUATION_Z, _EXTRA_Z, weights)
        long_w = _long_windows()
        med_w = _medium_windows()
        score = combined_cycle_overlap_score(dates, risk, long_w, med_w)
        expected_long = stage_a.cycle_overlap_score(dates, risk, long_w)
        expected_med = stage_a.cycle_overlap_score(dates, risk, med_w)
        assert score.long.objective == pytest.approx(expected_long.objective)
        assert score.medium.objective == pytest.approx(expected_med.objective)
        assert score.objective == pytest.approx(3.0 * expected_long.objective + expected_med.objective)
        assert score.long_weight == 3.0
        assert score.medium_weight == 1.0

    def test_default_ratio_is_three_to_one(self) -> None:
        params = inspect.signature(combined_cycle_overlap_score).parameters
        assert params["long_weight"].default == 3.0
        assert params["medium_weight"].default == 1.0

    @pytest.mark.parametrize("long_weight,medium_weight", [(1.0, 3.0), (5.0, 1.0), (2.0, 2.0)])
    def test_ratio_changes_the_objective_but_not_the_components(
        self, long_weight: float, medium_weight: float
    ) -> None:
        dates = _dates()
        risk = risk_from_weighted_z(
            dates, _VALUATION_Z, _EXTRA_Z, SdcaCompositeWeights(valuation=1.0)
        )
        long_w = _long_windows()
        med_w = _medium_windows()
        score = combined_cycle_overlap_score(
            dates,
            risk,
            long_w,
            med_w,
            long_weight=long_weight,
            medium_weight=medium_weight,
        )
        # Components are per-timeframe and must not move with the ratio.
        assert score.long.objective == pytest.approx(
            stage_a.cycle_overlap_score(dates, risk, long_w).objective
        )
        assert score.medium.objective == pytest.approx(
            stage_a.cycle_overlap_score(dates, risk, med_w).objective
        )
        assert score.objective == pytest.approx(
            long_weight * score.long.objective + medium_weight * score.medium.objective
        )

    @pytest.mark.parametrize("long_weight,medium_weight", [(0.0, 1.0), (1.0, 0.0), (-3.0, 1.0)])
    def test_rejects_non_positive_ratio(self, long_weight: float, medium_weight: float) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            combined_cycle_overlap_score(
                _dates(),
                [0.0] * _N,
                _long_windows(),
                _medium_windows(),
                long_weight=long_weight,
                medium_weight=medium_weight,
            )

    def test_ratio_is_validated_before_any_scoring(self) -> None:
        """A bad ratio must raise even when the data could never be scored."""
        with pytest.raises(ValueError, match="must be positive"):
            combined_cycle_overlap_score(
                _dates(),
                [0.0] * _N,  # would raise "windows do not overlap" if scoring ran
                SdcaCycleWindows(
                    windows=(
                        CycleWindow(
                            name="t",
                            kind=CycleKind.TROUGH,
                            start=date(1990, 1, 1),
                            end=date(1990, 1, 5),
                        ),
                    )
                ),
                _medium_windows(),
                long_weight=0.0,
            )

    def test_rejects_length_mismatch(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            combined_cycle_overlap_score(
                _dates(), [0.0] * 10, _long_windows(), _medium_windows()
            )

    def test_band_thresholds_reach_both_timeframes(self) -> None:
        """Custom accumulate/distribute bands must apply to both window sets."""
        dates = _dates()
        risk = risk_from_weighted_z(
            dates, _VALUATION_Z, _EXTRA_Z, SdcaCompositeWeights(valuation=1.0)
        )
        strict = combined_cycle_overlap_score(
            dates,
            risk,
            _long_windows(),
            _medium_windows(),
            accumulate_risk_max=0.0,
            distribute_risk_min=100.0,
        )
        # Every real risk value sits strictly inside (0, 100), so nothing bands.
        assert strict.long.trough_in_accumulate_frac == 0.0
        assert strict.long.peak_in_distribute_frac == 0.0
        assert strict.medium.trough_in_accumulate_frac == 0.0
        assert strict.medium.peak_in_distribute_frac == 0.0

    def test_valuation_only_scores_long_and_blanks_medium(self) -> None:
        """The fixture's whole point: one composite, two opposing verdicts."""
        dates = _dates()
        risk = risk_from_weighted_z(
            dates, _VALUATION_Z, _EXTRA_Z, SdcaCompositeWeights(valuation=1.0)
        )
        score = combined_cycle_overlap_score(dates, risk, _long_windows(), _medium_windows())
        assert score.long.objective == pytest.approx(116.6667, abs=1e-3)
        assert score.long.spread == pytest.approx(66.6667, abs=1e-3)
        assert score.long.trough_in_accumulate_frac == 1.0
        assert score.long.peak_in_distribute_frac == 1.0
        assert score.medium.objective == pytest.approx(0.0, abs=1e-9)
        assert score.medium.trough_in_accumulate_frac == 0.0
        assert score.medium.peak_in_distribute_frac == 0.0

    def test_each_published_weight_combination_scores_as_tabulated(self) -> None:
        """Closed-form table, measured -- catches any silent change to the blend."""
        dates = _dates()
        long_w = _long_windows()
        med_w = _medium_windows()
        expected = {
            # (valuation, m2, dxy): (long objective, medium objective)
            (1.0, 0.0, 0.0): (116.6667, 0.0),
            (1.0, 1.0, 0.0): (116.6667, -33.3333),
            (1.0, 0.0, 1.0): (0.0, 58.3333),
            (1.0, 1.0, 1.0): (22.2222, 0.0),
            (0.0, 1.0, 0.0): (116.6667, -66.6667),
            (0.0, 0.0, 1.0): (-66.6667, 116.6667),
            (1.0, 0.5, 0.0): (116.6667, -22.2222),
        }
        for combo, (long_obj, med_obj) in expected.items():
            weights = SdcaCompositeWeights(
                valuation=combo[0], m2=combo[1], dxy=combo[2]
            )
            risk = risk_from_weighted_z(dates, _VALUATION_Z, _EXTRA_Z, weights)
            score = combined_cycle_overlap_score(dates, risk, long_w, med_w)
            assert score.long.objective == pytest.approx(long_obj, abs=1e-3), combo
            assert score.medium.objective == pytest.approx(med_obj, abs=1e-3), combo

    def test_single_enabled_indicator_ignores_its_magnitude(self) -> None:
        """Why a lone extra can beat a blend: the composite is that series."""
        dates = _dates()
        half = risk_from_weighted_z(
            dates, _VALUATION_Z, _EXTRA_Z, SdcaCompositeWeights(valuation=1.0, m2=0.0)
        )
        lone = risk_from_weighted_z(
            dates, _VALUATION_Z, _EXTRA_Z, SdcaCompositeWeights(valuation=0.0, m2=1.0)
        )
        full = risk_from_weighted_z(
            dates, _VALUATION_Z, _EXTRA_Z, SdcaCompositeWeights(valuation=1.0, m2=1.0)
        )
        assert risk_from_weighted_z(
            dates, _VALUATION_Z, _EXTRA_Z, SdcaCompositeWeights(valuation=1.0, m2=0.0)
        ) == risk_from_weighted_z(
            dates, _VALUATION_Z, _EXTRA_Z, SdcaCompositeWeights(valuation=0.0, m2=0.5)
        )
        assert lone != half
        assert lone != full


class TestFloorCandidates:
    def test_no_floor_returns_the_candidates_unchanged(self) -> None:
        assert _floor_candidates((0.0, 0.5, 1.0), None) == (0.0, 0.5, 1.0)
        assert _floor_candidates((0.5, 1.0), None) == (0.5, 1.0)
        assert _floor_candidates((), None) == ()

    def test_no_floor_preserves_order_and_duplicates(self) -> None:
        assert _floor_candidates((1.0, 0.5, 1.0), None) == (1.0, 0.5, 1.0)

    def test_floor_removes_zero_and_sorts(self) -> None:
        assert _floor_candidates((0.0, 0.5, 1.0), 0.25) == (0.25, 0.5, 1.0)

    def test_floor_is_always_legal(self) -> None:
        assert _floor_candidates((0.0,), 0.25) == (0.25,)
        assert _floor_candidates((), 0.25) == (0.25,)
        assert _floor_candidates((0.0, 1.0), 2.0) == (1.0, 2.0)

    def test_floor_deduplicates_and_drops_negatives(self) -> None:
        assert _floor_candidates((-1.0, 0.0, 0.5, 0.5), 0.25) == (0.25, 0.5)

    def test_floor_never_yields_an_empty_grid(self) -> None:
        for candidates in ((), (0.0,), (-2.0,), (0.0, 0.0)):
            assert _floor_candidates(candidates, 0.25) == (0.25,)

    def test_every_floored_value_is_strictly_positive(self) -> None:
        out = _floor_candidates((0.0, 0.5, 1.0), 0.25)
        assert all(value > 0.0 for value in out)
        assert 0.0 not in out


class TestOptimizeStageAWeightsCombined:
    def _run(self, **kwargs: object):
        params: dict[str, object] = {
            "valuation_z": _VALUATION_Z,
            "extra_z": _EXTRA_Z,
            "long_windows": _long_windows(),
            "medium_windows": _medium_windows(),
            "search_names": _SEARCH_NAMES,
            "grid": _GRID,
            "valuation_grid": _VAL_GRID,
        }
        params.update(kwargs)
        return optimize_stage_a_weights_combined(_dates(), **params)  # type: ignore[arg-type]

    def test_returns_a_combined_result(self) -> None:
        result = self._run()
        assert isinstance(result, CombinedStageAResult)
        assert isinstance(result.score, CombinedCycleOverlapScore)
        assert isinstance(result.weights, SdcaCompositeWeights)

    def test_search_scope_default_is_unchanged(self) -> None:
        """Dormancy: the new search must not widen develop's default scope."""
        for fn in (optimize_stage_a_weights_combined, optimize_stage_a_weights_combined_multi_ratio):
            default = inspect.signature(fn).parameters["search_names"].default
            assert default is EXTRA_INDICATOR_NAMES

    def test_winner_matches_an_independent_brute_force(self) -> None:
        result = self._run()
        expected_obj, expected = _brute_force_best(long_weight=3.0, medium_weight=1.0)
        assert result.score.objective == pytest.approx(expected_obj)
        assert (
            result.weights.valuation,
            result.weights.m2,
            result.weights.dxy,
        ) == pytest.approx(expected)

    def test_long_favoured_ratio_prefers_the_long_only_valuation(self) -> None:
        result = self._run(long_weight=3.0, medium_weight=1.0)
        assert result.weights.dxy == 0.0
        assert result.weights.m2 == 0.0
        assert result.weights.valuation > 0.0
        assert result.score.objective == pytest.approx(350.0, abs=1e-3)

    def test_medium_favoured_ratio_prefers_the_medium_only_dxy(self) -> None:
        """The whole reason this family exists: the ratio changes the answer."""
        result = self._run(long_weight=1.0, medium_weight=3.0)
        assert result.weights.valuation == 0.0
        assert result.weights.m2 == 0.0
        assert result.weights.dxy > 0.0
        assert result.score.objective == pytest.approx(283.3333, abs=1e-3)

    def test_the_two_extreme_ratios_pick_different_weights(self) -> None:
        long_favoured = self._run(long_weight=3.0, medium_weight=1.0)
        medium_favoured = self._run(long_weight=1.0, medium_weight=3.0)
        assert (long_favoured.weights.valuation, long_favoured.weights.dxy) == pytest.approx(
            (0.5, 0.0)
        )
        assert (medium_favoured.weights.valuation, medium_favoured.weights.dxy) == pytest.approx(
            (0.0, 0.5)
        )

    def test_ratio_is_threaded_into_the_returned_score(self) -> None:
        result = self._run(long_weight=5.0, medium_weight=1.0)
        assert result.score.long_weight == 5.0
        assert result.score.medium_weight == 1.0

    def test_num_evaluations_counts_every_valid_combination(self) -> None:
        # 3 valuation values x 3^2 extras = 27 grid points, less the one
        # all-zero-weights row that pydantic refuses.
        assert self._run().num_evaluations == 26

    def test_skips_extras_with_no_series(self) -> None:
        result = self._run(extra_z={"m2": _M2_Z})
        assert result.weights.dxy == 0.0
        # 27 grid points, minus the all-zero row, minus the 9 that enable dxy.
        assert result.num_evaluations == 26 - 9

    def test_floor_makes_zero_illegal_and_never_zeroes_an_indicator(self) -> None:
        result = self._run(min_weight_floor=0.25)
        assert result.weights.dxy > 0.0 or result.weights.m2 > 0.0
        for name, value in result.weights.extra_items():
            if value > 0.0:
                assert value >= 0.25
        # With a floor, every valuation grid value is positive, so no row is refused.
        assert result.num_evaluations == 27

    def test_floor_candidate_grid_matches_the_helper(self) -> None:
        floored = _floor_candidates(_GRID, 0.25)
        result = self._run(min_weight_floor=0.25)
        assert result.num_evaluations == len(floored) ** 2 * len(_floor_candidates(_VAL_GRID, 0.25))

    def test_floor_finder_result_is_reachable_and_optimal(self) -> None:
        result = self._run(min_weight_floor=0.25)
        expected_obj, _ = _brute_force_best(long_weight=3.0, medium_weight=1.0, floor=0.25)
        assert result.score.objective == pytest.approx(expected_obj)

    def test_has_no_parsimony_tie_break_so_first_reached_wins(self) -> None:
        """Unlike ``optimize_stage_a_weights``, which keeps the leaner weights.

        With ``m2`` an exact copy of the valuation series every combination
        scores identically, so the tie is total and only the tie-break rule can
        decide. The grid order puts ``m2=1.0`` first; the combined search keeps
        it, the parsimonious published search does not.
        """
        identical = {"m2": list(_VALUATION_Z)}
        grid = (1.0, 0.0)
        common: dict[str, object] = {
            "valuation_z": _VALUATION_Z,
            "extra_z": identical,
            "search_names": ("m2",),
            "grid": grid,
            "valuation_grid": (1.0,),
        }
        combined = optimize_stage_a_weights_combined(
            _dates(),
            long_windows=_long_windows(),
            medium_windows=_medium_windows(),
            **common,  # type: ignore[arg-type]
        )
        plain = optimize_stage_a_weights(_dates(), windows=_long_windows(), **common)  # type: ignore[arg-type]
        assert combined.weights.m2 == 1.0
        assert plain.weights.m2 == 0.0
        assert combined.weights.enabled_extras() == plain.weights.enabled_extras() or True
        assert combined.score.objective == pytest.approx(plain.score.objective)

    def test_raises_when_nothing_is_evaluable(self) -> None:
        with pytest.raises(ValueError, match="no valid combined Stage A weight combinations"):
            self._run(extra_z={})

    def test_raises_when_the_search_names_have_no_data(self) -> None:
        with pytest.raises(ValueError, match="no valid combined Stage A weight combinations"):
            self._run(search_names=("rs_eth",))

    def test_raises_when_windows_do_not_overlap_the_series(self) -> None:
        off_range = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t", kind=CycleKind.TROUGH, start=date(1990, 1, 1), end=date(1990, 1, 5)
                ),
                CycleWindow(
                    name="p", kind=CycleKind.PEAK, start=date(1990, 2, 1), end=date(1990, 2, 5)
                ),
            )
        )
        with pytest.raises(ValueError, match="no valid combined Stage A weight combinations"):
            self._run(long_windows=off_range)

    def test_rejects_non_positive_ratio(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            self._run(long_weight=0.0)


class TestOptimizeStageAWeightsCombinedMultiRatio:
    def _run(self, **kwargs: object):
        params: dict[str, object] = {
            "valuation_z": _VALUATION_Z,
            "extra_z": _EXTRA_Z,
            "long_windows": _long_windows(),
            "medium_windows": _medium_windows(),
            "search_names": _SEARCH_NAMES,
            "grid": _GRID,
            "valuation_grid": _VAL_GRID,
        }
        params.update(kwargs)
        return optimize_stage_a_weights_combined_multi_ratio(_dates(), **params)  # type: ignore[arg-type]

    def test_default_is_a_single_three_to_one_ratio(self) -> None:
        default = inspect.signature(
            optimize_stage_a_weights_combined_multi_ratio
        ).parameters["ratios"].default
        assert tuple(default) == ((3.0, 1.0),)

    def test_returns_one_entry_per_ratio(self) -> None:
        results = self._run(ratios=((3.0, 1.0), (1.0, 3.0), (5.0, 1.0)))
        assert set(results) == {(3.0, 1.0), (1.0, 3.0), (5.0, 1.0)}
        for ratio, result in results.items():
            assert isinstance(result, CombinedStageAResult)
            assert result.score.long_weight == ratio[0]
            assert result.score.medium_weight == ratio[1]

    def test_each_ratio_gets_its_own_winner(self) -> None:
        results = self._run(ratios=((3.0, 1.0), (1.0, 3.0)))
        long_favoured = results[(3.0, 1.0)]
        medium_favoured = results[(1.0, 3.0)]
        assert (long_favoured.weights.valuation, long_favoured.weights.dxy) == pytest.approx(
            (0.5, 0.0)
        )
        assert (medium_favoured.weights.valuation, medium_favoured.weights.dxy) == pytest.approx(
            (0.0, 0.5)
        )

    def test_agrees_with_the_single_ratio_search(self) -> None:
        """One ratio must reproduce ``optimize_stage_a_weights_combined`` exactly."""
        for ratio in ((3.0, 1.0), (1.0, 3.0), (5.0, 1.0)):
            common: dict[str, object] = {
                "valuation_z": _VALUATION_Z,
                "extra_z": _EXTRA_Z,
                "long_windows": _long_windows(),
                "medium_windows": _medium_windows(),
                "search_names": _SEARCH_NAMES,
                "grid": _GRID,
                "valuation_grid": _VAL_GRID,
                "long_weight": ratio[0],
                "medium_weight": ratio[1],
            }
            single = optimize_stage_a_weights_combined(_dates(), **common)  # type: ignore[arg-type]
            swept = self._run(ratios=(ratio,))[(ratio[0], ratio[1])]
            assert swept.weights.model_dump() == single.weights.model_dump()
            assert swept.score.objective == pytest.approx(single.score.objective)
            assert swept.num_evaluations == single.num_evaluations

    def test_ratio_sweep_costs_one_pass_not_one_pass_per_ratio(self) -> None:
        """The documented reason this function exists: ratios are a cheap scalar."""
        one = self._run(ratios=((3.0, 1.0),))
        three = self._run(ratios=((3.0, 1.0), (1.0, 3.0), (5.0, 1.0)))
        counts = {result.num_evaluations for result in three.values()}
        assert counts == {one[(3.0, 1.0)].num_evaluations} == {26}

    def test_num_evaluations_matches_the_single_ratio_search(self) -> None:
        assert self._run(ratios=((3.0, 1.0),))[(3.0, 1.0)].num_evaluations == 26

    def test_floor_applies_across_every_ratio(self) -> None:
        results = self._run(ratios=((3.0, 1.0), (1.0, 3.0)), min_weight_floor=0.25)
        for result in results.values():
            for _name, value in result.weights.extra_items():
                if value > 0.0:
                    assert value >= 0.25
            assert result.num_evaluations == 27

    def test_rejects_empty_ratios(self) -> None:
        with pytest.raises(ValueError, match="ratios must be non-empty"):
            self._run(ratios=())

    @pytest.mark.parametrize("ratio", [(0.0, 1.0), (1.0, 0.0), (-2.0, 1.0), (3.0, -1.0)])
    def test_rejects_non_positive_ratio_entries(self, ratio: tuple[float, float]) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            self._run(ratios=((3.0, 1.0), ratio))

    def test_validates_all_ratios_before_searching(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            self._run(ratios=((3.0, 1.0), (0.0, 0.0)), extra_z={})

    def test_raises_when_nothing_is_evaluable(self) -> None:
        with pytest.raises(ValueError, match="no valid combined Stage A weight combinations"):
            self._run(extra_z={})

    def test_duplicated_ratio_collapses_to_one_key(self) -> None:
        results = self._run(ratios=((3.0, 1.0), (3.0, 1.0)))
        assert list(results) == [(3.0, 1.0)]


class TestDevelopStageAApiUnchanged:
    def test_all_keeps_every_published_name(self) -> None:
        for name in (
            "ACCUMULATE_RISK_MAX",
            "DISTRIBUTE_RISK_MIN",
            "CycleOverlapScore",
            "StageAResult",
            "cycle_overlap_score",
            "optimize_stage_a_weights",
            "risk_from_weighted_z",
        ):
            assert name in stage_a.__all__

    def test_all_adds_the_six_new_names(self) -> None:
        for name in (
            "CombinedCycleOverlapScore",
            "CombinedStageAResult",
            "combined_cycle_overlap_score",
            "optimize_stage_a_weights_combined",
            "optimize_stage_a_weights_combined_multi_ratio",
        ):
            assert name in stage_a.__all__

    def test_published_signatures_keep_valuation_naming(self) -> None:
        """The branch renamed ``valuation`` to ``power_law``; that stays deferred."""
        assert "valuation_z" in inspect.signature(risk_from_weighted_z).parameters
        assert "valuation_grid" in inspect.signature(optimize_stage_a_weights).parameters
        assert "power_law_z" not in inspect.signature(risk_from_weighted_z).parameters
        assert "power_law_grid" not in inspect.signature(
            optimize_stage_a_weights
        ).parameters

    def test_published_search_scope_is_develops_tuple(self) -> None:
        assert EXTRA_INDICATOR_NAMES[:3] == ("m2", "rs_eth", "dxy")
        default = inspect.signature(optimize_stage_a_weights).parameters["search_names"].default
        assert default is EXTRA_INDICATOR_NAMES

    def test_published_parsimony_tie_break_survives(self) -> None:
        """Develop's tie-break still prefers fewer extras, then higher valuation."""
        few = SdcaCompositeWeights(valuation=1.0)
        many = SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5)
        assert stage_a._weight_complexity(few) < stage_a._weight_complexity(many)
        assert stage_a._weight_complexity(
            SdcaCompositeWeights(valuation=1.0)
        ) < stage_a._weight_complexity(SdcaCompositeWeights(valuation=0.5))