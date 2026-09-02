"""Tests for the valuation z-score indicator (mirrors the artifact's eqmZScoreAtIndex)."""

from __future__ import annotations

import datetime as _dt
import math
from datetime import date

import numpy as np
import polars as pl
import pytest
from digiquant.strategies.sdca.valuation import (
    valuation_confluence_z,
    valuation_trend_z,
    valuation_z_score,
)

pytestmark = pytest.mark.unit


def _dates(n: int, start: date = date(2020, 1, 1)) -> pl.Series:
    return pl.Series("date", [start + _dt.timedelta(days=i) for i in range(n)], dtype=pl.Date)


class TestValuationZScore:
    def test_price_at_median_is_zero(self) -> None:
        price = pl.Series("price", [100.0])
        low = pl.Series("low", [50.0])
        median = pl.Series("median", [100.0])
        high = pl.Series("high", [200.0])
        z = valuation_z_score(price, low, median, high)
        assert z[0] == pytest.approx(0.0)

    def test_price_at_low_rail_is_plus_3(self) -> None:
        price = pl.Series("price", [50.0])
        low = pl.Series("low", [50.0])
        median = pl.Series("median", [100.0])
        high = pl.Series("high", [200.0])
        z = valuation_z_score(price, low, median, high)
        assert z[0] == pytest.approx(3.0)

    def test_price_at_high_rail_is_minus_3(self) -> None:
        price = pl.Series("price", [200.0])
        low = pl.Series("low", [50.0])
        median = pl.Series("median", [100.0])
        high = pl.Series("high", [200.0])
        z = valuation_z_score(price, low, median, high)
        assert z[0] == pytest.approx(-3.0)

    def test_price_below_low_rail_clamps_to_plus_3(self) -> None:
        price = pl.Series("price", [10.0])
        low = pl.Series("low", [50.0])
        median = pl.Series("median", [100.0])
        high = pl.Series("high", [200.0])
        z = valuation_z_score(price, low, median, high)
        assert z[0] == pytest.approx(3.0)

    def test_price_above_high_rail_clamps_to_minus_3(self) -> None:
        price = pl.Series("price", [1000.0])
        low = pl.Series("low", [50.0])
        median = pl.Series("median", [100.0])
        high = pl.Series("high", [200.0])
        z = valuation_z_score(price, low, median, high)
        assert z[0] == pytest.approx(-3.0)

    def test_vectorized_over_multiple_rows(self) -> None:
        price = pl.Series("price", [100.0, 50.0, 200.0])
        low = pl.Series("low", [50.0, 50.0, 50.0])
        median = pl.Series("median", [100.0, 100.0, 100.0])
        high = pl.Series("high", [200.0, 200.0, 200.0])
        z = valuation_z_score(price, low, median, high)
        assert z.to_list() == pytest.approx([0.0, 3.0, -3.0])

    def test_interior_prices_interpolate_in_log_space_not_linear_space(self) -> None:
        """Pin the module's headline guarantee: the interpolation is logarithmic.

        Only an interior price discriminates -- log and linear agree exactly at each
        rail and both saturate beyond them. Expected values are derived from the
        docstring formula, not from this implementation:
        ``3*ln(100/75)/ln(100/50)`` and ``-3*ln(150/100)/ln(200/100)``.
        A linear rewrite would give 1.5 and -1.5 here.
        """
        price = pl.Series("price", [75.0, 150.0])
        low = pl.Series("low", [50.0, 50.0])
        median = pl.Series("median", [100.0, 100.0])
        high = pl.Series("high", [200.0, 200.0])
        z = valuation_z_score(price, low, median, high)
        assert z[0] == pytest.approx(1.2451125, abs=1e-7)
        assert z[1] == pytest.approx(-1.7548875, abs=1e-7)

    def test_rows_with_any_null_rail_pass_through_as_null(self) -> None:
        price = pl.Series("price", [100.0, 100.0])
        low = pl.Series("low", [50.0, None])
        median = pl.Series("median", [100.0, 100.0])
        high = pl.Series("high", [200.0, 200.0])
        z = valuation_z_score(price, low, median, high)
        assert z[0] == pytest.approx(0.0)
        assert z[1] is None

    def test_non_positive_price_raises(self) -> None:
        price = pl.Series("price", [-5.0])
        low = pl.Series("low", [50.0])
        median = pl.Series("median", [100.0])
        high = pl.Series("high", [200.0])
        with pytest.raises(ValueError, match="positive"):
            valuation_z_score(price, low, median, high)

    def test_non_finite_price_raises(self) -> None:
        price = pl.Series("price", [float("inf")])
        low = pl.Series("low", [50.0])
        median = pl.Series("median", [100.0])
        high = pl.Series("high", [200.0])
        with pytest.raises(ValueError, match="finite"):
            valuation_z_score(price, low, median, high)

    def test_low_not_less_than_median_raises(self) -> None:
        price = pl.Series("price", [100.0])
        low = pl.Series("low", [100.0])
        median = pl.Series("median", [100.0])
        high = pl.Series("high", [200.0])
        with pytest.raises(ValueError, match="low < median < high"):
            valuation_z_score(price, low, median, high)

    def test_median_not_less_than_high_raises(self) -> None:
        price = pl.Series("price", [100.0])
        low = pl.Series("low", [50.0])
        median = pl.Series("median", [200.0])
        high = pl.Series("high", [200.0])
        with pytest.raises(ValueError, match="low < median < high"):
            valuation_z_score(price, low, median, high)

    def test_null_high_is_null_even_when_the_below_branch_is_taken(self) -> None:
        """A null rail must null the row even when the taken branch does not read it.

        ``below`` reads only ``low``, so a row with ``price < median`` and a null
        ``high`` used to return a real z-score — turning a no-data day into a
        max-buy signal (z=3 -> risk=0 -> the most aggressive curve node).
        """
        price = pl.Series("price", [100.0, 50.0])
        low = pl.Series("low", [50.0, 50.0])
        median = pl.Series("median", [100.0, 100.0])
        high = pl.Series("high", [200.0, None])
        z = valuation_z_score(price, low, median, high)
        assert z[0] == pytest.approx(0.0)
        assert z[1] is None

    def test_null_low_is_null_even_when_the_above_branch_is_taken(self) -> None:
        """Mirror of the above: ``above`` reads only ``high``."""
        price = pl.Series("price", [100.0, 150.0])
        low = pl.Series("low", [50.0, None])
        median = pl.Series("median", [100.0, 100.0])
        high = pl.Series("high", [200.0, 200.0])
        z = valuation_z_score(price, low, median, high)
        assert z[0] == pytest.approx(0.0)
        assert z[1] is None

    def test_partial_row_is_null_rather_than_validated(self) -> None:
        """A row with any null is a no-data day, so its other rails are not judged.

        Per the contract, validation covers only fully-populated rows -- ``median <
        high`` is not even checkable when ``high`` is null. What matters is that the
        row yields null: because ``price == median`` the below branch's numerator is
        exactly zero, so this input used to return a clean-looking ``-0.0`` without
        ever reading the null ``high`` at all.
        """
        price = pl.Series("price", [100.0])
        low = pl.Series("low", [999.0])
        median = pl.Series("median", [100.0])
        high = pl.Series("high", [None])
        assert valuation_z_score(price, low, median, high)[0] is None


class TestValuationTrendZ:
    def test_values_before_full_window_are_null(self) -> None:
        n, window = 40, 20
        dates = _dates(n)
        price = pl.Series("price", [100.0 * math.exp(0.01 * i) for i in range(n)])
        z = valuation_trend_z(dates, price, window=window)
        assert z[: window - 1].null_count() == window - 1
        assert z[window - 1] is not None

    def test_perfectly_linear_trend_has_near_zero_residual(self) -> None:
        """A synthetic series exactly on its own trend line should read ~0 (neutral).

        With a noiseless line, the true RSS sits at the ``_SIGMA_FLOOR`` clip, so the
        z-score is a ratio of two near-zero floating-point quantities -- exact zero
        isn't guaranteed, only smallness (observed noise floor is ~1e-2, well below
        any reading this indicator would treat as a real signal).
        """
        n, window = 60, 20
        dates = _dates(n)
        price = pl.Series("price", [100.0 * math.exp(0.01 * i) for i in range(n)])
        z = valuation_trend_z(dates, price, window=window)
        for i in range(window - 1, n):
            assert abs(z[i]) < 0.1

    def test_upward_jump_reads_negative_rich(self) -> None:
        n, window = 60, 20
        dates = _dates(n)
        values = [100.0 * math.exp(0.01 * i) for i in range(n)]
        values[-1] *= 1.05
        z = valuation_trend_z(dates, pl.Series("price", values), window=window)
        assert z[-1] < 0.0

    def test_downward_jump_reads_positive_cheap(self) -> None:
        n, window = 60, 20
        dates = _dates(n)
        values = [100.0 * math.exp(0.01 * i) for i in range(n)]
        values[-1] /= 1.05
        z = valuation_trend_z(dates, pl.Series("price", values), window=window)
        assert z[-1] > 0.0

    def test_extreme_jumps_clip_to_plus_minus_3(self) -> None:
        n, window = 60, 20
        dates = _dates(n)
        base = [100.0 * math.exp(0.01 * i) for i in range(n)]

        up = list(base)
        up[-1] *= math.exp(10.0)
        z_up = valuation_trend_z(dates, pl.Series("price", up), window=window)
        assert z_up[-1] == pytest.approx(-3.0)

        down = list(base)
        down[-1] *= math.exp(-10.0)
        z_down = valuation_trend_z(dates, pl.Series("price", down), window=window)
        assert z_down[-1] == pytest.approx(3.0)

    def test_matches_numpy_polyfit_per_window(self) -> None:
        """Regression guard for the closed-form derivation against a naive per-window fit."""
        rng = np.random.default_rng(42)
        n, window = 80, 20
        dates = _dates(n)
        log_returns = rng.normal(0.0, 0.02, size=n)
        log_price = np.cumsum(log_returns) + math.log(100.0)
        price = pl.Series("price", np.exp(log_price).tolist())

        z = valuation_trend_z(dates, price, window=window)

        xs = np.arange(window, dtype=np.float64)
        for i in range(window - 1, n):
            ys = log_price[i - window + 1 : i + 1]
            slope, intercept = np.polyfit(xs, ys, 1)
            residuals = ys - (intercept + slope * xs)
            rss = float(np.sum(residuals**2))
            dof = max(window - 2, 1)
            resid_std = max(math.sqrt(rss / dof), 1e-12)
            expected = max(-3.0, min(3.0, -(residuals[-1] / resid_std)))
            assert z[i] == pytest.approx(expected, abs=1e-6)


class TestValuationConfluenceZ:
    def test_matches_agreement_scaled_formula_across_history(self) -> None:
        n = 500
        dates = _dates(n)
        price = pl.Series(
            "price",
            [
                100.0 + 40.0 * math.sin(2 * math.pi * i / 140) + 15.0 * math.sin(2 * math.pi * i / 33)
                for i in range(n)
            ],
        )
        low = pl.Series("low", [50.0] * n)
        median = pl.Series("median", [100.0] * n)
        high = pl.Series("high", [200.0] * n)

        long_term_weight = 0.5
        agreement_boost = 0.5
        disagreement_damp = 0.5
        trend_window = 60

        blended = valuation_confluence_z(
            dates,
            price,
            low,
            median,
            high,
            trend_window=trend_window,
            long_term_weight=long_term_weight,
            agreement_boost=agreement_boost,
            disagreement_damp=disagreement_damp,
        )
        long_term = valuation_z_score(price, low, median, high)
        medium_term = valuation_trend_z(dates, price, window=trend_window)

        saw_agreement = False
        saw_disagreement = False
        for i in range(n):
            long_val = long_term[i]
            med_val = medium_term[i]
            if long_val is None and med_val is None:
                assert blended[i] is None
                continue
            if med_val is None:
                # Below the trend window: null-passthrough falls back to the raw
                # long-term leg untouched, not a null and not a blended value.
                assert blended[i] == pytest.approx(long_val, abs=1e-9)
                continue
            if long_val is None:
                assert blended[i] == pytest.approx(med_val, abs=1e-9)
                continue
            base = long_term_weight * long_val + (1.0 - long_term_weight) * med_val
            if long_val == 0.0 or med_val == 0.0:
                multiplier = 1.0
            elif (long_val > 0) == (med_val > 0):
                saw_agreement = True
                multiplier = 1.0 + agreement_boost * (
                    min(abs(long_val), abs(med_val)) / max(abs(long_val), abs(med_val))
                )
            else:
                saw_disagreement = True
                multiplier = disagreement_damp
            expected = max(-3.0, min(3.0, base * multiplier))
            assert blended[i] == pytest.approx(expected, abs=1e-9)

        assert saw_agreement, "fixture must exercise the agreement branch"
        assert saw_disagreement, "fixture must exercise the disagreement branch"

    def test_short_history_falls_back_to_long_term_leg_only(self) -> None:
        """Below the trend window, the medium-term leg is null throughout and the
        blend's null-passthrough rule means the output is exactly the raw
        power-law leg -- not null, and not some degenerate blended value."""
        n = 10
        dates = _dates(n)
        price = pl.Series("price", [100.0 + i for i in range(n)])
        low = pl.Series("low", [50.0] * n)
        median = pl.Series("median", [100.0] * n)
        high = pl.Series("high", [200.0] * n)

        blended = valuation_confluence_z(dates, price, low, median, high, trend_window=180)
        long_term = valuation_z_score(price, low, median, high)

        assert blended.to_list() == pytest.approx(long_term.to_list())
