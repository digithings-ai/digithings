"""Tests for the RiskModel protocol — structural typing, no BTC-specific constants."""

from __future__ import annotations

import polars as pl
import pytest
from digiquant.strategies.sdca.risk_model import RiskModel

pytestmark = pytest.mark.unit


class StaticRiskModel:
    """Minimal RiskModel-shaped stub for protocol conformance testing."""

    def rails(self, dates: pl.Series) -> pl.DataFrame:
        n = len(dates)
        return pl.DataFrame(
            {
                "low": pl.Series([50.0] * n),
                "median": pl.Series([100.0] * n),
                "high": pl.Series([200.0] * n),
            }
        )


class TestRiskModelProtocol:
    def test_conforming_class_satisfies_protocol(self) -> None:
        model: RiskModel = StaticRiskModel()
        assert isinstance(model, RiskModel)

    def test_rails_returns_low_median_high_columns(self) -> None:
        model = StaticRiskModel()
        dates = pl.Series(["2024-01-01", "2024-01-02"])
        rails = model.rails(dates)
        assert set(rails.columns) == {"low", "median", "high"}
        assert rails.height == 2

    def test_non_conforming_object_fails_isinstance_check(self) -> None:
        class NotARiskModel:
            pass

        assert not isinstance(NotARiskModel(), RiskModel)
