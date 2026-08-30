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
    CycleOverlapScore,
    StageAResult,
    cycle_overlap_score,
    optimize_stage_a_weights,
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
        assert names["2025_peak"].start <= date(2025, 1, 20) <= names["2025_peak"].end

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
        valuation = [0.0] * len(dates)
        result = optimize_stage_a_weights(
            dates,
            valuation_z=valuation,
            extra_z={"weekly_rsi": dummy, "sma_band": noise},
            windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 1.0),
        )
        assert isinstance(result, StageAResult)
        assert result.weights.weekly_rsi > result.weights.sma_band
        assert result.weights.weekly_rsi == pytest.approx(1.0)
        assert result.weights.sma_band == pytest.approx(0.0)

    def test_uninformative_extras_lose_to_valuation_only(self) -> None:
        """Equal overlap prefers fewer extras and valuation=1 (parsimony)."""
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
        valuation = [3.0 if d <= date(2020, 1, 25) else -3.0 for d in dates]
        zeros = [0.0] * len(dates)
        result = optimize_stage_a_weights(
            dates,
            valuation_z=valuation,
            extra_z={"weekly_rsi": zeros, "sma_band": zeros},
            windows=windows,
            search_names=("weekly_rsi", "sma_band"),
            grid=(0.0, 1.0),
            valuation_grid=(0.5, 1.0),
        )
        assert result.weights.weekly_rsi == pytest.approx(0.0)
        assert result.weights.sma_band == pytest.approx(0.0)
        assert result.weights.valuation == pytest.approx(1.0)

    def test_all_null_extra_combos_are_skipped_not_aborted(self) -> None:
        """Warmup-null extras must not abort the grid; valuation-only still wins."""
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
        valuation = [3.0 if d <= date(2020, 1, 20) else -3.0 for d in dates]
        result = optimize_stage_a_weights(
            dates,
            valuation_z=valuation,
            extra_z={"weekly_rsi": [None] * len(dates)},
            windows=windows,
            search_names=("weekly_rsi",),
            grid=(0.0, 1.0),
            valuation_grid=(1.0,),
        )
        assert result.weights.weekly_rsi == pytest.approx(0.0)
        assert result.weights.valuation == pytest.approx(1.0)

    def test_risk_from_weighted_z_matches_composite_formula(self) -> None:
        dates = [date(2020, 1, 1), date(2020, 1, 2)]
        risk = risk_from_weighted_z(
            dates,
            valuation_z=[0.0, 0.0],
            extra_z={"weekly_rsi": [3.0, 3.0]},
            weights=SdcaCompositeWeights(valuation=1.0, weekly_rsi=1.0),
        )
        # composite_z = (0 + 3) / 2 = 1.5 → risk = 50 - 1.5 * 50/3 = 25
        assert risk[0] == pytest.approx(25.0)
        assert risk[1] == pytest.approx(25.0)
