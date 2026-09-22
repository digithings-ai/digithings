"""Stage A: cycle-window overlap for composite indicator weights."""

from __future__ import annotations

import datetime as _dt
from datetime import date

import pytest
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
    StageAResult,
    combined_cycle_overlap_score,
    cycle_overlap_score,
    optimize_stage_a_weights,
    optimize_stage_a_weights_combined,
    optimize_stage_a_weights_combined_multi_ratio,
    risk_from_weighted_z,
)

pytestmark = pytest.mark.unit


def _dates(n: int, start: date) -> list[date]:
    return [start + _dt.timedelta(days=i) for i in range(n)]


class TestSdcaCycleWindows:
    def test_btc_v1_pins_documented_extrema(self) -> None:
        windows = SdcaCycleWindows.btc_v1()
        names = {w.name: w for w in windows.windows}
        assert names["2017_peak"].kind == CycleKind.PEAK
        assert names["2017_peak"].start <= date(2017, 12, 17) <= names["2017_peak"].end
        assert names["2018_trough"].kind == CycleKind.TROUGH
        assert names["2018_trough"].start <= date(2018, 12, 15) <= names["2018_trough"].end
        assert names["2021_peak"].kind == CycleKind.PEAK
        assert names["2021_peak"].start <= date(2021, 11, 10) <= names["2021_peak"].end
        assert names["2022_trough"].kind == CycleKind.TROUGH
        assert names["2022_trough"].start <= date(2022, 11, 21) <= names["2022_trough"].end
        assert names["2025_peak"].kind == CycleKind.PEAK
        assert names["2025_peak"].start <= date(2025, 10, 6) <= names["2025_peak"].end

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            SdcaCycleWindows(windows=())

    def test_rejects_inverted_range(self) -> None:
        with pytest.raises(ValueError):
            CycleWindow(
                name="bad",
                kind=CycleKind.PEAK,
                start=date(2020, 2, 1),
                end=date(2020, 1, 1),
            )

    def test_btc_medium_term_v1_starts_2018_and_is_narrower_than_long_term(self) -> None:
        medium = SdcaCycleWindows.btc_medium_term_v1()
        assert len(medium.windows) > 0
        for w in medium.windows:
            assert w.start >= date(2018, 1, 1)
            assert (w.end - w.start) < _dt.timedelta(days=90)  # narrower than btc_v1's +/-45d span

    def test_btc_medium_term_v1_is_strictly_alternating(self) -> None:
        # The zigzag construction guarantees this; it's also the property
        # Chris asked for directly: "every top, there should be a bottom
        # signal" (2026-09-04 chart review).
        medium = SdcaCycleWindows.btc_medium_term_v1()
        kinds = [w.kind for w in medium.windows]
        for prev_kind, next_kind in zip(kinds, kinds[1:]):
            assert prev_kind != next_kind

    def test_btc_medium_term_v1_peaks_and_troughs_are_balanced(self) -> None:
        medium = SdcaCycleWindows.btc_medium_term_v1()
        assert abs(len(medium.peaks()) - len(medium.troughs())) <= 1


class TestCycleOverlapScore:
    def test_low_risk_in_trough_high_in_peak_scores_positive(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(90, start)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=date(2020, 1, 1),
                    end=date(2020, 1, 20),
                ),
                CycleWindow(
                    name="p",
                    kind=CycleKind.PEAK,
                    start=date(2020, 3, 1),
                    end=date(2020, 3, 20),
                ),
            )
        )
        risk = []
        for d in dates:
            if d <= date(2020, 1, 20):
                risk.append(10.0)
            elif d >= date(2020, 3, 1):
                risk.append(90.0)
            else:
                risk.append(50.0)
        score = cycle_overlap_score(dates, risk, windows)
        assert isinstance(score, CycleOverlapScore)
        assert score.spread > 50.0
        assert score.trough_in_accumulate_frac == pytest.approx(1.0)
        assert score.peak_in_distribute_frac == pytest.approx(1.0)
        assert score.objective > 0.0

    def test_inverted_risk_scores_worse(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(60, start)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=date(2020, 1, 1),
                    end=date(2020, 1, 20),
                ),
                CycleWindow(
                    name="p",
                    kind=CycleKind.PEAK,
                    start=date(2020, 2, 10),
                    end=date(2020, 2, 29),
                ),
            )
        )
        good = [10.0 if d <= date(2020, 1, 20) else 90.0 for d in dates]
        bad = [90.0 if d <= date(2020, 1, 20) else 10.0 for d in dates]
        assert (
            cycle_overlap_score(dates, good, windows).objective
            > cycle_overlap_score(dates, bad, windows).objective
        )


class TestStageAWeightSearch:
    def test_dummy_trough_indicator_gets_high_weight(self) -> None:
        """An extra that is cheap only in troughs must beat a constant-zero extra."""
        start = date(2020, 1, 1)
        dates = _dates(90, start)
        trough_end = date(2020, 1, 25)
        peak_start = date(2020, 3, 1)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=start,
                    end=trough_end,
                ),
                CycleWindow(
                    name="p",
                    kind=CycleKind.PEAK,
                    start=peak_start,
                    end=date(2020, 3, 30),
                ),
            )
        )
        dummy = []
        noise = []
        for d in dates:
            if d <= trough_end:
                dummy.append(3.0)  # cheap / buy
            elif d >= peak_start:
                dummy.append(-3.0)  # rich / sell
            else:
                dummy.append(0.0)
            noise.append(0.0)
        power_law = [0.0] * len(dates)
        result = optimize_stage_a_weights(
            dates,
            power_law_z=power_law,
            extra_z={"weekly_rsi": dummy, "sma_band": noise},
            windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 1.0),
        )
        assert isinstance(result, StageAResult)
        assert result.weights.weekly_rsi > result.weights.sma_band
        assert result.weights.weekly_rsi == pytest.approx(1.0)
        assert result.weights.sma_band == pytest.approx(0.0)

    def test_uninformative_extras_lose_to_power_law_only(self) -> None:
        """Equal overlap prefers fewer extras and power_law=1 (parsimony)."""
        start = date(2020, 1, 1)
        dates = _dates(90, start)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=start,
                    end=date(2020, 1, 25),
                ),
                CycleWindow(
                    name="p",
                    kind=CycleKind.PEAK,
                    start=date(2020, 3, 1),
                    end=date(2020, 3, 30),
                ),
            )
        )
        power_law = [3.0 if d <= date(2020, 1, 25) else -3.0 for d in dates]
        zeros = [0.0] * len(dates)
        result = optimize_stage_a_weights(
            dates,
            power_law_z=power_law,
            extra_z={"weekly_rsi": zeros, "sma_band": zeros},
            windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 1.0),
            power_law_grid=(0.5, 1.0),
        )
        assert result.weights.weekly_rsi == pytest.approx(0.0)
        assert result.weights.sma_band == pytest.approx(0.0)
        assert result.weights.power_law == pytest.approx(1.0)

    def test_require_extras_skips_power_law_only(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(90, start)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=start,
                    end=date(2020, 1, 25),
                ),
                CycleWindow(
                    name="p",
                    kind=CycleKind.PEAK,
                    start=date(2020, 3, 1),
                    end=date(2020, 3, 30),
                ),
            )
        )
        power_law = [3.0 if d <= date(2020, 1, 25) else -3.0 for d in dates]
        dummy = [-3.0 if d <= date(2020, 1, 25) else 3.0 for d in dates]
        zeros = [0.0] * len(dates)
        result = optimize_stage_a_weights(
            dates,
            power_law_z=power_law,
            extra_z={"weekly_rsi": dummy, "sma_band": zeros},
            windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 1.0),
            power_law_grid=(1.0,),
            require_extras=True,
        )
        # Power-law-only is skipped; any non-zero extra satisfies require_extras
        # (sma_band zeros still count as an enabled extra and dilute power_law).
        assert result.weights.enabled_extras()
        assert result.weights.power_law == pytest.approx(1.0)
        assert sum(result.weights.enabled_extras().values()) > 0.0

    def test_all_null_extra_combos_are_skipped_not_aborted(self) -> None:
        """Warmup-null extras must not abort the grid; power_law-only still wins."""
        start = date(2020, 1, 1)
        dates = _dates(60, start)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=start,
                    end=date(2020, 1, 20),
                ),
                CycleWindow(
                    name="p",
                    kind=CycleKind.PEAK,
                    start=date(2020, 2, 10),
                    end=date(2020, 2, 25),
                ),
            )
        )
        power_law = [3.0 if d <= date(2020, 1, 20) else -3.0 for d in dates]
        result = optimize_stage_a_weights(
            dates,
            power_law_z=power_law,
            extra_z={"weekly_rsi": [None] * len(dates)},
            windows=windows,
            search_names=("weekly_rsi",),
            grid=(0.0, 1.0),
            power_law_grid=(1.0,),
        )
        assert result.weights.weekly_rsi == pytest.approx(0.0)
        assert result.weights.power_law == pytest.approx(1.0)

    def test_risk_from_weighted_z_matches_composite_formula(self) -> None:
        dates = [date(2020, 1, 1), date(2020, 1, 2)]
        risk = risk_from_weighted_z(
            dates,
            power_law_z=[0.0, 0.0],
            extra_z={"weekly_rsi": [3.0, 3.0]},
            weights=SdcaCompositeWeights(power_law=1.0, weekly_rsi=1.0),
        )
        # composite_z = (0 + 3) / 2 = 1.5 → risk = 50 - 1.5 * 50/3 = 25
        assert risk[0] == pytest.approx(25.0)
        assert risk[1] == pytest.approx(25.0)


class TestCombinedCycleOverlapScore:
    def test_combined_score_matches_manual_weighted_sum(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(90, start)
        long_windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=date(2020, 1, 1),
                    end=date(2020, 1, 20),
                ),
                CycleWindow(
                    name="p",
                    kind=CycleKind.PEAK,
                    start=date(2020, 3, 1),
                    end=date(2020, 3, 20),
                ),
            )
        )
        medium_windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t2",
                    kind=CycleKind.TROUGH,
                    start=date(2020, 1, 25),
                    end=date(2020, 2, 5),
                ),
                CycleWindow(
                    name="p2",
                    kind=CycleKind.PEAK,
                    start=date(2020, 2, 15),
                    end=date(2020, 2, 25),
                ),
            )
        )
        risk = []
        for d in dates:
            if d <= date(2020, 1, 20):
                risk.append(10.0)
            elif d >= date(2020, 3, 1):
                risk.append(90.0)
            else:
                risk.append(50.0)
        combined = combined_cycle_overlap_score(
            dates, risk, long_windows, medium_windows, long_weight=3.0, medium_weight=1.0
        )
        assert isinstance(combined, CombinedCycleOverlapScore)
        manual_long = cycle_overlap_score(dates, risk, long_windows)
        manual_medium = cycle_overlap_score(dates, risk, medium_windows)
        assert combined.long == manual_long
        assert combined.medium == manual_medium
        assert combined.objective == pytest.approx(
            3.0 * manual_long.objective + 1.0 * manual_medium.objective
        )

    def test_rejects_nonpositive_weights(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(30, start)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=start,
                    end=date(2020, 1, 10),
                ),
                CycleWindow(
                    name="p",
                    kind=CycleKind.PEAK,
                    start=date(2020, 1, 20),
                    end=date(2020, 1, 29),
                ),
            )
        )
        risk = [50.0] * len(dates)
        with pytest.raises(ValueError, match="positive"):
            combined_cycle_overlap_score(dates, risk, windows, windows, long_weight=0.0)


class TestOptimizeStageAWeightsCombined:
    def test_combined_optimizer_ratio_controls_which_timeframe_wins(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(120, start)
        long_windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t_long",
                    kind=CycleKind.TROUGH,
                    start=dates[0],
                    end=dates[19],
                ),
                CycleWindow(
                    name="p_long",
                    kind=CycleKind.PEAK,
                    start=dates[100],
                    end=dates[119],
                ),
            )
        )
        medium_windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t_medium",
                    kind=CycleKind.TROUGH,
                    start=dates[40],
                    end=dates[49],
                ),
                CycleWindow(
                    name="p_medium",
                    kind=CycleKind.PEAK,
                    start=dates[60],
                    end=dates[69],
                ),
            )
        )
        long_days = set(dates[0:20]) | set(dates[100:120])
        medium_days = set(dates[40:50]) | set(dates[60:70])

        def _dummy(active_days: set[date], sign_days: set[date]) -> list[float]:
            out = []
            for d in dates:
                if d not in active_days:
                    out.append(0.0)
                elif d in sign_days:
                    out.append(3.0)
                else:
                    out.append(-3.0)
            return out

        long_trough_days = set(dates[0:20])
        medium_trough_days = set(dates[40:50])
        weekly_rsi = _dummy(long_days, long_trough_days)
        sma_band = _dummy(medium_days, medium_trough_days)
        power_law = [0.0] * len(dates)

        result_long_favored = optimize_stage_a_weights_combined(
            dates,
            power_law_z=power_law,
            extra_z={"weekly_rsi": weekly_rsi, "sma_band": sma_band},
            long_windows=long_windows,
            medium_windows=medium_windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 1.0),
            power_law_grid=(0.0,),
            long_weight=100.0,
            medium_weight=1.0,
        )
        assert isinstance(result_long_favored, CombinedStageAResult)
        assert result_long_favored.weights.weekly_rsi == pytest.approx(1.0)
        assert result_long_favored.weights.sma_band == pytest.approx(0.0)

        result_medium_favored = optimize_stage_a_weights_combined(
            dates,
            power_law_z=power_law,
            extra_z={"weekly_rsi": weekly_rsi, "sma_band": sma_band},
            long_windows=long_windows,
            medium_windows=medium_windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 1.0),
            power_law_grid=(0.0,),
            long_weight=1.0,
            medium_weight=100.0,
        )
        assert result_medium_favored.weights.weekly_rsi == pytest.approx(0.0)
        assert result_medium_favored.weights.sma_band == pytest.approx(1.0)

    def test_floor_grid_never_selects_zero_for_enabled_indicator(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(90, start)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=start,
                    end=date(2020, 1, 25),
                ),
                CycleWindow(
                    name="p",
                    kind=CycleKind.PEAK,
                    start=date(2020, 3, 1),
                    end=date(2020, 3, 30),
                ),
            )
        )
        power_law = [3.0 if d <= date(2020, 1, 25) else -3.0 for d in dates]
        zeros = [0.0] * len(dates)

        # power_law_grid is fixed at a single value here: when power_law is the
        # sole nonzero-weight contributor, its own weight magnitude cancels out
        # of the weighted average, so searching it would only add scoring ties
        # that are irrelevant to what this test checks (the extras' floor).
        without_floor = optimize_stage_a_weights_combined(
            dates,
            power_law_z=power_law,
            extra_z={"weekly_rsi": zeros, "sma_band": zeros},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 0.25, 0.5, 0.75, 1.0),
            power_law_grid=(1.0,),
        )
        assert without_floor.weights.weekly_rsi == pytest.approx(0.0)
        assert without_floor.weights.sma_band == pytest.approx(0.0)
        assert without_floor.weights.power_law == pytest.approx(1.0)

        with_floor = optimize_stage_a_weights_combined(
            dates,
            power_law_z=power_law,
            extra_z={"weekly_rsi": zeros, "sma_band": zeros},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 0.25, 0.5, 0.75, 1.0),
            power_law_grid=(0.0, 0.25, 0.5, 0.75, 1.0),
            min_weight_floor=0.25,
        )
        assert with_floor.weights.weekly_rsi == pytest.approx(0.25)
        assert with_floor.weights.sma_band == pytest.approx(0.25)
        assert with_floor.weights.power_law == pytest.approx(1.0)

    def test_multi_ratio_matches_single_ratio_per_ratio(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(90, start)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t", kind=CycleKind.TROUGH, start=start, end=date(2020, 1, 25)
                ),
                CycleWindow(
                    name="p", kind=CycleKind.PEAK, start=date(2020, 3, 1), end=date(2020, 3, 30)
                ),
            )
        )
        power_law = [3.0 if d <= date(2020, 1, 25) else -3.0 for d in dates]
        weekly_rsi = [-3.0 if d <= date(2020, 1, 25) else 3.0 for d in dates]
        ratios = ((2.0, 1.0), (3.0, 1.0), (5.0, 1.0))

        multi = optimize_stage_a_weights_combined_multi_ratio(
            dates,
            power_law_z=power_law,
            extra_z={"weekly_rsi": weekly_rsi},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi",),
            grid=(0.0, 0.5, 1.0),
            power_law_grid=(0.0, 0.5, 1.0),
            ratios=ratios,
        )
        assert set(multi.keys()) == set(ratios)
        for lw, mw in ratios:
            single = optimize_stage_a_weights_combined(
                dates,
                power_law_z=power_law,
                extra_z={"weekly_rsi": weekly_rsi},
                long_windows=windows,
                medium_windows=windows,
                search_names=("weekly_rsi",),
                grid=(0.0, 0.5, 1.0),
                power_law_grid=(0.0, 0.5, 1.0),
                long_weight=lw,
                medium_weight=mw,
            )
            got = multi[(lw, mw)]
            assert got.weights.power_law == pytest.approx(single.weights.power_law)
            assert got.weights.weekly_rsi == pytest.approx(single.weights.weekly_rsi)
            assert got.score.objective == pytest.approx(single.score.objective)

    def test_multi_ratio_respects_diversification_floor(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(90, start)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t", kind=CycleKind.TROUGH, start=start, end=date(2020, 1, 25)
                ),
                CycleWindow(
                    name="p", kind=CycleKind.PEAK, start=date(2020, 3, 1), end=date(2020, 3, 30)
                ),
            )
        )
        power_law = [3.0 if d <= date(2020, 1, 25) else -3.0 for d in dates]
        zeros = [0.0] * len(dates)

        multi = optimize_stage_a_weights_combined_multi_ratio(
            dates,
            power_law_z=power_law,
            extra_z={"weekly_rsi": zeros, "sma_band": zeros},
            long_windows=windows,
            medium_windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 0.25, 0.5, 0.75, 1.0),
            power_law_grid=(0.0, 0.25, 0.5, 0.75, 1.0),
            ratios=((2.0, 1.0), (5.0, 1.0)),
            min_weight_floor=0.25,
        )
        for lw, mw in ((2.0, 1.0), (5.0, 1.0)):
            result = multi[(lw, mw)]
            assert result.weights.weekly_rsi == pytest.approx(0.25)
            assert result.weights.sma_band == pytest.approx(0.25)
            assert result.weights.power_law == pytest.approx(1.0)

    def test_multi_ratio_rejects_empty_or_nonpositive_ratios(self) -> None:
        start = date(2020, 1, 1)
        dates = _dates(30, start)
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(name="t", kind=CycleKind.TROUGH, start=start, end=dates[9]),
                CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[20], end=dates[29]),
            )
        )
        power_law = [0.0] * len(dates)
        with pytest.raises(ValueError, match="non-empty"):
            optimize_stage_a_weights_combined_multi_ratio(
                dates,
                power_law_z=power_law,
                extra_z={},
                long_windows=windows,
                medium_windows=windows,
                search_names=(),
                ratios=(),
            )
        with pytest.raises(ValueError, match="positive"):
            optimize_stage_a_weights_combined_multi_ratio(
                dates,
                power_law_z=power_law,
                extra_z={},
                long_windows=windows,
                medium_windows=windows,
                search_names=(),
                ratios=((0.0, 1.0),),
            )
