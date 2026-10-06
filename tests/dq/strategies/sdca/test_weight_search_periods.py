"""Leaf 5: per-oscillator *period* searches (DIG-1597 port of weight_search).

Ports ``search_oscillator_periods_by_backtest`` and
``search_oscillator_periods_by_cycle_overlap`` from the abandoned branch
``claude/sdca-develop-sync``, re-shaped onto develop's current API:

* develop still spells the composite's dedicated field ``valuation``. The
  branch's ``power_law`` rename is **not** ported (deferred breaking leaf,
  see ``test_deferred_power_law_rename_is_not_ported``), so the cycle-overlap
  search's special-case key here is ``"valuation"`` and its kwarg is
  ``base_valuation_z``.
* two guards the branch does not have are added and pinned below. The big one:
  ``SdcaCompositeWeights`` inherits pydantic's ``extra='ignore'`` default, so
  on the branch a misspelled ``indicator_name`` was silently dropped and every
  candidate scored identically under the unchanged base weights -- a
  meaningless "winner" with no error. See
  ``TestUnknownIndicatorNameIsRejected``.

The two searches deliberately share a shape and differ in one axis:

* by-backtest **probes** one indicator inside a fixed base weight set and ranks
  on mean in-sample vs-flat-DCA over walk-forward folds;
* by-cycle-overlap **solos** one indicator against the dual-timeframe overlap
  objective and ranks on ``score.objective``.

Both report OOS; neither lets OOS pick the winner.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from datetime import date, timedelta

import polars as pl
import pytest
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.cycle_windows import CycleKind, CycleWindow, SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.stage_a import ACCUMULATE_RISK_MAX, DISTRIBUTE_RISK_MIN
from digiquant.strategies.sdca.walk_forward import SdcaTrialMetrics, make_walk_forward_folds
from digiquant.strategies.sdca.weight_search import (
    search_oscillator_periods_by_backtest,
    search_oscillator_periods_by_cycle_overlap,
)

pytestmark = pytest.mark.unit

# The extra this module searches. A real ``SdcaCompositeWeights`` extra, not the
# dedicated ``valuation`` field.
_SEARCHED = "weekly_rsi"


def _dates(n: int = 120) -> list[date]:
    return [date(2020, 1, 1) + timedelta(days=i) for i in range(n)]


class _ConstRails:
    def rails(self, dates: pl.Series) -> pl.DataFrame:
        n = dates.len()
        return pl.DataFrame({"low": [50.0] * n, "median": [100.0] * n, "high": [200.0] * n})


def _fitter(dates: list[date], prices: list[float]) -> RiskModel:
    assert dates and prices
    return _ConstRails()


_SHAPE = SdcaCurveShape(
    buy_max_rate=4.0,
    buy_knee_risk=30.0,
    sell_knee_risk=70.0,
    sell_max_rate=5.0,
    buy_curvature=1.0,
    sell_curvature=2.0,
)


def _is_days(dates: list[date]) -> set[date]:
    """Every date the walk-forward folds score as in-sample."""
    folds, _holdout = make_walk_forward_folds(dates)
    return {d for f in folds for d in dates if f.is_start <= d <= f.is_end}


def _z_by_window(dates: list[date], in_sample: float, out_of_sample: float) -> list[float]:
    """z series that is ``in_sample`` inside IS folds and ``out_of_sample`` outside."""
    inside = _is_days(dates)
    return [in_sample if d in inside else out_of_sample for d in dates]


def _mean_z(extra_indicators: object, name: str = _SEARCHED) -> float:
    for ind in extra_indicators or []:  # type: ignore[union-attr]
        if getattr(ind, "name", "") == name:
            return float(ind.z.mean())
    return 0.0


def _z_mean_evaluator(
    window_dates: list[date],
    window_prices: list[float],
    model: RiskModel,
    shape: SdcaCurveShape,
    valuation_weight: float,
    extra_indicators: object = None,
) -> SdcaTrialMetrics:
    """Score by the searched indicator's mean z in this window.

    Higher mean z -> higher ``vs_flat_dca_pct``, so the winning candidate is a
    direct function of the series ``compute_indicator_z`` produced.
    """
    assert isinstance(model, _ConstRails)
    return SdcaTrialMetrics(
        vs_flat_dca_pct=_mean_z(extra_indicators),
        vs_lump_pct=-1.0,
        capital_deployed_pct=40.0,
        max_drawdown_pct=12.0,
    )


def _windows(dates: list[date]) -> tuple[SdcaCycleWindows, SdcaCycleWindows]:
    long_windows = SdcaCycleWindows(
        windows=(
            CycleWindow(name="t_long", kind=CycleKind.TROUGH, start=dates[0], end=dates[19]),
            CycleWindow(name="p_long", kind=CycleKind.PEAK, start=dates[100], end=dates[119]),
        )
    )
    medium_windows = SdcaCycleWindows(
        windows=(
            CycleWindow(name="t_med", kind=CycleKind.TROUGH, start=dates[40], end=dates[49]),
            CycleWindow(name="p_med", kind=CycleKind.PEAK, start=dates[60], end=dates[69]),
        )
    )
    return long_windows, medium_windows


def _cycle_z(dates: list[date], *, aligned: bool) -> list[float]:
    """z that puts risk low at troughs and high at peaks when ``aligned``.

    ``compute_composite_risk`` maps z -> risk as ``risk = 50 - z * 50/3``, so
    troughs need a *high* z and peaks a *low* one for overlap to score well.
    """
    troughs = {d for d in dates if d <= dates[19] or dates[40] <= d <= dates[49]}
    peaks = {d for d in dates if dates[60] <= d <= dates[69] or dates[100] <= d <= dates[119]}
    if not aligned:
        troughs, peaks = peaks, troughs
    return [
        3.0 if d in troughs else (-3.0 if d in peaks else 0.0)
        for d in dates
    ]


class TestSearchOscillatorPeriodsByBacktest:
    """Grid one indicator's construction periods, holding the weight set fixed."""

    def test_picks_the_candidate_with_the_best_mean_in_sample_score(self) -> None:
        dates = _dates()
        prices = [100.0 + 0.2 * i for i in range(len(dates))]

        def compute(params: Mapping[str, int]) -> Sequence[float | None]:
            return [float(params["length"])] * len(dates)

        result = search_oscillator_periods_by_backtest(
            dates,
            prices,
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 7}, {"length": 21}, {"length": 14}],
            compute_indicator_z=compute,
            base_extra_z={},
            base_weights=SdcaCompositeWeights(),
            rails_fitter=_fitter,
            evaluator=_z_mean_evaluator,
            shape=_SHAPE,
        )
        assert result.indicator_name == _SEARCHED
        # Scored by mean z, so the longest period wins.
        assert result.best.params == {"length": 21}
        assert result.num_evaluations == 3
        assert [s.params["length"] for s in result.all_scores] == [7, 21, 14]

    def test_out_of_sample_never_picks_the_winner(self) -> None:
        """IS-only ranking: a candidate that wins OOS must not win overall."""
        dates = _dates()
        prices = [100.0 + 0.2 * i for i in range(len(dates))]
        series = {
            7: _z_by_window(dates, in_sample=2.0, out_of_sample=-2.0),
            21: _z_by_window(dates, in_sample=-2.0, out_of_sample=2.0),
        }

        def compute(params: Mapping[str, int]) -> Sequence[float | None]:
            return series[params["length"]]

        result = search_oscillator_periods_by_backtest(
            dates,
            prices,
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 7}, {"length": 21}],
            compute_indicator_z=compute,
            base_extra_z={},
            base_weights=SdcaCompositeWeights(),
            rails_fitter=_fitter,
            evaluator=_z_mean_evaluator,
            shape=_SHAPE,
        )
        assert result.best.params == {"length": 7}
        assert result.best.mean_is_vs_flat_dca_pct > result.best.mean_oos_vs_flat_dca_pct
        # The runner-up is the OOS winner -- so this would fail if ranking used OOS.
        runner_up = next(s for s in result.all_scores if s.params == {"length": 21})
        assert runner_up.mean_oos_vs_flat_dca_pct > result.best.mean_oos_vs_flat_dca_pct

    def test_forces_the_searched_indicator_to_probe_weight(self) -> None:
        """The probe isolates marginal contribution even at base weight 0."""
        dates = _dates()
        prices = [100.0] * len(dates)
        seen: dict[str, float] = {}

        def evaluator(
            window_dates: list[date],
            window_prices: list[float],
            model: RiskModel,
            shape: SdcaCurveShape,
            valuation_weight: float,
            extra_indicators: object = None,
        ) -> SdcaTrialMetrics:
            for ind in extra_indicators or []:  # type: ignore[union-attr]
                seen[getattr(ind, "name", "")] = float(ind.weight)
            return SdcaTrialMetrics(
                vs_flat_dca_pct=1.0,
                vs_lump_pct=0.0,
                capital_deployed_pct=40.0,
                max_drawdown_pct=10.0,
            )

        search_oscillator_periods_by_backtest(
            dates,
            prices,
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 14}],
            compute_indicator_z=lambda p: [0.0] * len(dates),
            base_extra_z={},
            base_weights=SdcaCompositeWeights(valuation=1.0, weekly_rsi=0.0),
            rails_fitter=_fitter,
            evaluator=evaluator,
            shape=_SHAPE,
            probe_weight=0.5,
        )
        assert seen[_SEARCHED] == pytest.approx(0.5)

    def test_holds_every_other_base_weight_fixed(self) -> None:
        dates = _dates()
        prices = [100.0] * len(dates)
        seen: dict[str, float] = {}

        def evaluator(
            window_dates: list[date],
            window_prices: list[float],
            model: RiskModel,
            shape: SdcaCurveShape,
            valuation_weight: float,
            extra_indicators: object = None,
        ) -> SdcaTrialMetrics:
            seen["__valuation__"] = valuation_weight
            for ind in extra_indicators or []:  # type: ignore[union-attr]
                seen[getattr(ind, "name", "")] = float(ind.weight)
            return SdcaTrialMetrics(
                vs_flat_dca_pct=1.0,
                vs_lump_pct=0.0,
                capital_deployed_pct=40.0,
                max_drawdown_pct=10.0,
            )

        search_oscillator_periods_by_backtest(
            dates,
            prices,
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 14}],
            compute_indicator_z=lambda p: [0.0] * len(dates),
            base_extra_z={"m2": [0.0] * len(dates)},
            base_weights=SdcaCompositeWeights(valuation=0.75, m2=0.25, weekly_rsi=0.0),
            rails_fitter=_fitter,
            evaluator=evaluator,
            shape=_SHAPE,
        )
        assert seen["__valuation__"] == pytest.approx(0.75)
        assert seen["m2"] == pytest.approx(0.25)
        assert seen[_SEARCHED] == pytest.approx(1.0)

    def test_every_candidate_is_scored_with_the_same_fold_count(self) -> None:
        dates = _dates()
        prices = [100.0] * len(dates)
        folds, _holdout = make_walk_forward_folds(dates)

        result = search_oscillator_periods_by_backtest(
            dates,
            prices,
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 5}, {"length": 10}, {"length": 20}],
            compute_indicator_z=lambda p: [1.0] * len(dates),
            base_extra_z={},
            base_weights=SdcaCompositeWeights(),
            rails_fitter=_fitter,
            evaluator=_z_mean_evaluator,
            shape=_SHAPE,
        )
        assert len(result.all_scores) == len(folds)
        for score in result.all_scores:
            assert len(score.fold_scores) == len(folds)

    def test_rejects_empty_param_candidates(self) -> None:
        dates = _dates()
        with pytest.raises(ValueError, match="param_candidates"):
            search_oscillator_periods_by_backtest(
                dates,
                [100.0] * len(dates),
                indicator_name=_SEARCHED,
                param_candidates=[],
                compute_indicator_z=lambda p: [0.0] * len(dates),
                base_extra_z={},
                base_weights=SdcaCompositeWeights(),
                rails_fitter=_fitter,
                evaluator=_z_mean_evaluator,
                shape=_SHAPE,
            )

    def test_rejects_a_z_series_that_does_not_cover_the_calendar(self) -> None:
        dates = _dates()
        with pytest.raises(ValueError, match="returned 3 values"):
            search_oscillator_periods_by_backtest(
                dates,
                [100.0] * len(dates),
                indicator_name=_SEARCHED,
                param_candidates=[{"length": 14}],
                compute_indicator_z=lambda p: [0.0, 0.0, 0.0],
                base_extra_z={},
                base_weights=SdcaCompositeWeights(),
                rails_fitter=_fitter,
                evaluator=_z_mean_evaluator,
                shape=_SHAPE,
            )


class TestSearchOscillatorPeriodsByCycleOverlap:
    """Grid one indicator's construction periods against the combined objective."""

    def test_picks_the_candidate_with_the_best_objective(self) -> None:
        dates = _dates()
        long_windows, medium_windows = _windows(dates)

        def compute(params: Mapping[str, int]) -> Sequence[float | None]:
            return _cycle_z(dates, aligned=params["length"] == 21)

        result = search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 7}, {"length": 21}],
            compute_indicator_z=compute,
            base_valuation_z=[0.0] * len(dates),
            base_extra_z={},
            long_windows=long_windows,
            medium_windows=medium_windows,
        )
        assert result.indicator_name == _SEARCHED
        assert result.best.params == {"length": 21}
        assert result.num_evaluations == 2

    def test_aligned_candidate_beats_an_inverted_one_on_both_timeframes(self) -> None:
        """Trough-low-risk / peak-high-risk must actually move the objective."""
        dates = _dates()
        long_windows, medium_windows = _windows(dates)

        def compute(params: Mapping[str, int]) -> Sequence[float | None]:
            return _cycle_z(dates, aligned=params["length"] == 21)

        result = search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 7}, {"length": 21}],
            compute_indicator_z=compute,
            base_valuation_z=[0.0] * len(dates),
            base_extra_z={},
            long_windows=long_windows,
            medium_windows=medium_windows,
        )
        aligned = next(s for s in result.all_scores if s.params == {"length": 21})
        inverted = next(s for s in result.all_scores if s.params == {"length": 7})
        for horizon in ("long", "medium"):
            good = getattr(aligned.score, horizon)
            bad = getattr(inverted.score, horizon)
            assert good.spread > bad.spread
            assert good.mean_trough_risk <= ACCUMULATE_RISK_MAX
            assert good.mean_peak_risk >= DISTRIBUTE_RISK_MIN
            assert good.trough_in_accumulate_frac == pytest.approx(1.0)
            assert good.peak_in_distribute_frac == pytest.approx(1.0)
        assert aligned.score.objective > inverted.score.objective

    def test_scores_both_timeframes_and_applies_the_weight_ratio(self) -> None:
        dates = _dates()
        long_windows, medium_windows = _windows(dates)

        result = search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 21}],
            compute_indicator_z=lambda p: _cycle_z(dates, aligned=True),
            base_valuation_z=[0.0] * len(dates),
            base_extra_z={},
            long_windows=long_windows,
            medium_windows=medium_windows,
            long_weight=5.0,
            medium_weight=2.0,
        )
        score = result.best.score
        assert score.long_weight == pytest.approx(5.0)
        assert score.medium_weight == pytest.approx(2.0)
        assert score.long.trough_days > 0
        assert score.long.peak_days > 0
        assert score.medium.trough_days > 0
        assert score.medium.peak_days > 0

    def test_solos_the_searched_indicator_and_zeroes_everything_else(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Marginal contribution is the question, so nothing else may vote."""
        import digiquant.strategies.sdca.weight_search as ws

        dates = _dates()
        long_windows, medium_windows = _windows(dates)
        captured: list[SdcaCompositeWeights] = []
        real = ws.risk_from_weighted_z

        def spy(dates_, valuation_z, extra_z, weights):  # type: ignore[no-untyped-def]
            captured.append(weights)
            return real(dates_, valuation_z, extra_z, weights)

        monkeypatch.setattr(ws, "risk_from_weighted_z", spy)

        search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 21}],
            compute_indicator_z=lambda p: _cycle_z(dates, aligned=True),
            base_valuation_z=[0.0] * len(dates),
            base_extra_z={"m2": [0.0] * len(dates)},
            long_windows=long_windows,
            medium_windows=medium_windows,
        )
        assert captured
        weights = captured[0]
        assert weights.valuation == pytest.approx(0.0)
        assert weights.enabled_extras() == {_SEARCHED: pytest.approx(1.0)}

    def test_valuation_is_the_special_case_on_develops_spelling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``valuation`` is a dedicated field, so the candidate z replaces it.

        On the abandoned branch this key was ``power_law``. develop still says
        ``valuation``, and the branch spelling must not leak in.
        """
        import digiquant.strategies.sdca.weight_search as ws

        dates = _dates()
        long_windows, medium_windows = _windows(dates)
        captured: list[tuple[SdcaCompositeWeights, object, object]] = []
        real = ws.risk_from_weighted_z

        def spy(dates_, valuation_z, extra_z, weights):  # type: ignore[no-untyped-def]
            captured.append((weights, valuation_z, extra_z))
            return real(dates_, valuation_z, extra_z, weights)

        monkeypatch.setattr(ws, "risk_from_weighted_z", spy)

        candidate = _cycle_z(dates, aligned=True)
        result = search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name="valuation",
            param_candidates=[{"length": 21}],
            compute_indicator_z=lambda p: candidate,
            base_valuation_z=[0.0] * len(dates),
            base_extra_z={},
            long_windows=long_windows,
            medium_windows=medium_windows,
        )
        assert result.indicator_name == "valuation"
        assert captured
        weights, valuation_z, extra_z = captured[0]
        # Plain default: valuation carries the vote, every extra stays 0.
        assert weights.valuation == pytest.approx(1.0)
        assert weights.enabled_extras() == {}
        # The candidate series stands in for base_valuation_z, and nothing
        # leaked into the extras map.
        assert list(valuation_z) == candidate
        assert extra_z == {}

    def test_rejects_empty_param_candidates(self) -> None:
        dates = _dates()
        long_windows, medium_windows = _windows(dates)
        with pytest.raises(ValueError, match="param_candidates"):
            search_oscillator_periods_by_cycle_overlap(
                dates,
                indicator_name=_SEARCHED,
                param_candidates=[],
                compute_indicator_z=lambda p: [0.0] * len(dates),
                base_valuation_z=[0.0] * len(dates),
                base_extra_z={},
                long_windows=long_windows,
                medium_windows=medium_windows,
            )

    def test_rejects_a_z_series_that_does_not_cover_the_calendar(self) -> None:
        dates = _dates()
        long_windows, medium_windows = _windows(dates)
        with pytest.raises(ValueError, match="returned 3 values"):
            search_oscillator_periods_by_cycle_overlap(
                dates,
                indicator_name=_SEARCHED,
                param_candidates=[{"length": 14}],
                compute_indicator_z=lambda p: [0.0, 0.0, 0.0],
                base_valuation_z=[0.0] * len(dates),
                base_extra_z={},
                long_windows=long_windows,
                medium_windows=medium_windows,
            )


class TestUnknownIndicatorNameIsRejected:
    """The defect this port fixes rather than inherits.

    ``SdcaCompositeWeights`` sets no ``extra=``, so pydantic's default
    ``extra='ignore'`` silently drops an unknown key. On the abandoned branch
    ``search_oscillator_periods_by_backtest`` did
    ``probe_payload[indicator_name] = probe_weight`` and constructed the model
    from that: a typo'd name vanished, every candidate scored under the
    unchanged base weights, and the search returned a meaningless "winner" with
    no error at all. The cycle-overlap search only failed accidentally, because
    dropping the only soloed weight tripped ``_at_least_one_positive``.

    Both now validate the name up front, and the message names it -- which is
    what distinguishes a real guard from the accidental trip.
    """

    def _by_backtest_kwargs(self, dates: list[date]) -> dict[str, object]:
        return {
            "dates": dates,
            "prices": [100.0] * len(dates),
            "indicator_name": "weekly_rsi_typo",
            "param_candidates": [{"length": 14}],
            "compute_indicator_z": lambda p: [0.0] * len(dates),
            "base_extra_z": {},
            "base_weights": SdcaCompositeWeights(),
            "rails_fitter": _fitter,
            "evaluator": _z_mean_evaluator,
            "shape": _SHAPE,
        }

    def test_by_backtest_rejects_an_unknown_name(self) -> None:
        dates = _dates()
        with pytest.raises(ValueError) as excinfo:
            search_oscillator_periods_by_backtest(**self._by_backtest_kwargs(dates))  # type: ignore[arg-type]
        assert "weekly_rsi_typo" in str(excinfo.value)

    def test_by_backtest_rejects_the_dedicated_valuation_field(self) -> None:
        """``valuation`` reaches the evaluator positionally, never via extra_z.

        Soloing it here would build ``extra_z["valuation"]``, which
        ``_score_weights_on_cached_folds`` never reads -- a silent no-op, so it
        is rejected rather than quietly ignored.
        """
        dates = _dates()
        kwargs = self._by_backtest_kwargs(dates)
        kwargs["indicator_name"] = "valuation"
        with pytest.raises(ValueError) as excinfo:
            search_oscillator_periods_by_backtest(**kwargs)  # type: ignore[arg-type]
        assert "valuation" in str(excinfo.value)

    def test_cycle_overlap_rejects_an_unknown_name(self) -> None:
        dates = _dates()
        long_windows, medium_windows = _windows(dates)
        with pytest.raises(ValueError) as excinfo:
            search_oscillator_periods_by_cycle_overlap(
                dates,
                indicator_name="weekly_rsi_typo",
                param_candidates=[{"length": 14}],
                compute_indicator_z=lambda p: [0.0] * len(dates),
                base_valuation_z=[0.0] * len(dates),
                base_extra_z={},
                long_windows=long_windows,
                medium_windows=medium_windows,
            )
        assert "weekly_rsi_typo" in str(excinfo.value)

    def test_the_model_really_would_have_dropped_it_silently(self) -> None:
        """Pin the reason the guard is needed, so it is not deleted as redundant."""
        weights = SdcaCompositeWeights(valuation=1.0, weekly_rsi_typo=1.0)
        assert "weekly_rsi_typo" not in weights.model_dump()


class TestPurityAndNonMutation:
    """A grid search must not mutate what the caller handed it."""

    def test_base_extra_z_is_not_mutated_by_the_backtest_search(self) -> None:
        dates = _dates()
        base_extra_z: dict[str, list[float]] = {"m2": [0.25] * len(dates)}
        snapshot = {"m2": list(base_extra_z["m2"])}

        search_oscillator_periods_by_backtest(
            dates,
            [100.0] * len(dates),
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 14}],
            compute_indicator_z=lambda p: [1.0] * len(dates),
            base_extra_z=base_extra_z,
            base_weights=SdcaCompositeWeights(valuation=0.5, m2=0.5),
            rails_fitter=_fitter,
            evaluator=_z_mean_evaluator,
            shape=_SHAPE,
        )
        assert base_extra_z == snapshot

    def test_base_extra_z_is_not_mutated_by_the_cycle_overlap_search(self) -> None:
        dates = _dates()
        long_windows, medium_windows = _windows(dates)
        base_extra_z: dict[str, list[float]] = {"m2": [0.25] * len(dates)}
        snapshot = {"m2": list(base_extra_z["m2"])}

        search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 21}],
            compute_indicator_z=lambda p: _cycle_z(dates, aligned=True),
            base_valuation_z=[0.0] * len(dates),
            base_extra_z=base_extra_z,
            long_windows=long_windows,
            medium_windows=medium_windows,
        )
        assert base_extra_z == snapshot

    def test_base_weights_are_not_mutated(self) -> None:
        dates = _dates()
        base_weights = SdcaCompositeWeights(valuation=1.0, weekly_rsi=0.25)
        before = base_weights.model_dump()

        search_oscillator_periods_by_backtest(
            dates,
            [100.0] * len(dates),
            indicator_name=_SEARCHED,
            param_candidates=[{"length": 14}],
            compute_indicator_z=lambda p: [0.0] * len(dates),
            base_extra_z={},
            base_weights=base_weights,
            rails_fitter=_fitter,
            evaluator=_z_mean_evaluator,
            shape=_SHAPE,
            probe_weight=1.0,
        )
        assert base_weights.model_dump() == before


def test_deferred_power_law_rename_is_not_ported() -> None:
    """Leaf 5 keeps develop's ``valuation``; the rename stays its own breaking leaf."""
    import digiquant.strategies.sdca.weight_search as ws

    assert "power_law" not in SdcaCompositeWeights.model_fields
    params = inspect.signature(search_oscillator_periods_by_cycle_overlap).parameters
    assert "base_valuation_z" in params
    assert "base_power_law_z" not in params
    assert "power_law" not in ws.__all__