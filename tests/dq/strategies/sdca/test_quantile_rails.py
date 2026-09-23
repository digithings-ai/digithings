"""Tests for shared quantile-rail reconciliation (#3175 band-crossing fix)."""

from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.unit


class TestDetectCrossings:
    def test_flags_rows_with_adjacent_inversions(self) -> None:
        from digiquant.strategies.sdca.quantile_rails import detect_crossings

        values = np.array(
            [
                [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],  # natural ascending order
                [1.0, 2.0, 3.0, 4.0, 12.0, 8.8, 13.0],  # q75 (idx 4) > q95 (idx 5)
            ]
        )
        crossed = detect_crossings(values)
        assert list(crossed) == [False, True]

    def test_nan_rows_never_flagged(self) -> None:
        from digiquant.strategies.sdca.quantile_rails import detect_crossings

        values = np.array(
            [
                [np.nan] * 7,
                [1.0, 2.0, 3.0, 4.0, 12.0, 8.8, 13.0],
            ]
        )
        crossed = detect_crossings(values)
        assert list(crossed) == [False, True]

    def test_no_false_positives_on_ties(self) -> None:
        from digiquant.strategies.sdca.quantile_rails import detect_crossings

        values = np.array([[1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0]])
        assert list(detect_crossings(values)) == [False]


class TestRearrangeNonCrossing:
    def test_no_crossing_is_a_no_op(self) -> None:
        from digiquant.strategies.sdca.quantile_rails import rearrange_non_crossing

        values = np.array([[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]])
        out = rearrange_non_crossing(values)
        np.testing.assert_array_equal(out, values)

    def test_clamps_toward_reconciled_neighbor_not_a_different_quantiles_value(self) -> None:
        """The real bug: np.sort silently relabels a *different* quantile's raw
        curve under a stale column label once ranks invert. rearrange_non_crossing
        must clamp each column to its own value, never swap in a neighbor's."""
        from digiquant.strategies.sdca.quantile_rails import rearrange_non_crossing

        raw = np.array([[6.0, 7.0, 8.0, 9.0, 12.0, 8.8, 13.0]])
        out = rearrange_non_crossing(raw)

        # Non-crossing invariant holds.
        assert (np.diff(out, axis=1) >= 0).all()
        # Column 5 (q95) is genuinely raw q95 clamped up to reconciled q75 --
        # not the raw q50 (9.0) a plain ascending sort would put in that slot.
        assert out[0, 5] == pytest.approx(max(raw[0, 5], out[0, 4]))
        assert out[0, 5] != pytest.approx(raw[0, 3])
        # Median column (index 3) is never touched by reconciliation.
        assert out[0, 3] == raw[0, 3]
        # A plain np.sort would have put 8.8 into the median slot; confirm
        # the fix does NOT reproduce that relabeling.
        assert out[0, 3] != np.sort(raw[0])[3]

    def test_clamps_below_median_too(self) -> None:
        from digiquant.strategies.sdca.quantile_rails import rearrange_non_crossing

        # q10 (idx 1) crosses below q01 (idx 0) on the low side.
        raw = np.array([[5.0, 3.0, 6.0, 7.0, 8.0, 9.0, 10.0]])
        out = rearrange_non_crossing(raw)

        assert (np.diff(out, axis=1) >= 0).all()
        # q10's own value (3.0) stays, clamped down to q25's already-
        # reconciled value on the walk toward q01 -- i.e. q01 clamps down to
        # q10's value, not the reverse.
        assert out[0, 0] == pytest.approx(min(raw[0, 0], out[0, 1]))
        assert out[0, 3] == raw[0, 3]

    def test_nan_rows_pass_through_unchanged(self) -> None:
        from digiquant.strategies.sdca.quantile_rails import rearrange_non_crossing

        values = np.array([[np.nan] * 7])
        out = rearrange_non_crossing(values)
        assert np.isnan(out).all()

    def test_mixed_finite_and_nan_rows(self) -> None:
        from digiquant.strategies.sdca.quantile_rails import rearrange_non_crossing

        values = np.array(
            [
                [np.nan] * 7,
                [6.0, 7.0, 8.0, 9.0, 12.0, 8.8, 13.0],
            ]
        )
        out = rearrange_non_crossing(values)
        assert np.isnan(out[0]).all()
        assert (np.diff(out[1]) >= 0).all()


class TestEvaluateQuadraticLog10:
    def _coeffs(self, values: dict[str, tuple[float, float]]):
        from digiquant.strategies.sdca.quantile_rails import QuantileCoefficients

        return {label: QuantileCoefficients(c=c, a=a, b=0.0) for label, (c, a) in values.items()}

    def test_warns_when_a_row_crosses(self, caplog) -> None:
        from digiquant.strategies.sdca.quantile_rails import evaluate_quadratic_log10

        # q95's shallow slope is overtaken by q75's steep slope at large x.
        coeffs = self._coeffs(
            {
                "q01": (1.0, 0.5),
                "q10": (1.5, 0.55),
                "q25": (2.0, 0.6),
                "q50": (2.5, 0.65),
                "q75": (3.0, 0.9),
                "q95": (3.3, 0.55),
                "q99": (3.5, 0.95),
            }
        )
        with caplog.at_level("WARNING"):
            values = evaluate_quadratic_log10(coeffs, np.array([0.0, 10.0]))
        assert any("crossing" in rec.message.lower() for rec in caplog.records)
        assert (np.diff(values, axis=1) >= 0).all()

    def test_no_warning_when_nothing_crosses(self, caplog) -> None:
        from digiquant.strategies.sdca.quantile_rails import evaluate_quadratic_log10

        coeffs = self._coeffs(
            {
                "q01": (1.0, 0.1),
                "q10": (1.5, 0.1),
                "q25": (2.0, 0.1),
                "q50": (2.5, 0.1),
                "q75": (3.0, 0.1),
                "q95": (3.3, 0.1),
                "q99": (3.5, 0.1),
            }
        )
        with caplog.at_level("WARNING"):
            evaluate_quadratic_log10(coeffs, np.array([0.0, 5.0, 10.0]))
        assert not any("crossing" in rec.message.lower() for rec in caplog.records)

    def test_nan_x_produces_nan_row_without_crashing(self) -> None:
        from digiquant.strategies.sdca.quantile_rails import evaluate_quadratic_log10

        coeffs = self._coeffs(
            {
                "q01": (1.0, 0.1),
                "q10": (1.5, 0.1),
                "q25": (2.0, 0.1),
                "q50": (2.5, 0.1),
                "q75": (3.0, 0.1),
                "q95": (3.3, 0.1),
                "q99": (3.5, 0.1),
            }
        )
        values = evaluate_quadratic_log10(coeffs, np.array([np.nan, 1.0]))
        assert np.isnan(values[0]).all()
        assert np.isfinite(values[1]).all()
