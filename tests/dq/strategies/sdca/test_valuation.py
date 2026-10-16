"""Tests for the valuation z-score indicator (mirrors the artifact's eqmZScoreAtIndex)."""

from __future__ import annotations

import polars as pl
import pytest
from digiquant.strategies.sdca.valuation import valuation_z_score

pytestmark = pytest.mark.unit


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
