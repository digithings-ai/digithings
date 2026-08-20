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
