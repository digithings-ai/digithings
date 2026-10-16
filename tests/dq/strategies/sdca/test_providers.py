"""Tests for the SDCA RiskModel selector (#3175)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from digiquant.strategies.sdca.btc_power_law import (
    _COEFFICIENTS_EXAMPLE_PATH,
    BtcPowerLawRiskModel,
)
from digiquant.strategies.sdca.generic_valuation import GenericValuationRiskModel
from digiquant.strategies.sdca.providers import (
    KNOWN_SDCA_RISK_MODELS,
    resolve_sdca_risk_model,
)
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.rolling_z import RollingZRiskModel

pytestmark = pytest.mark.unit


def _series(
    n: int, *, start: date = date(2018, 1, 1), seed: int = 0
) -> tuple[pl.Series, pl.Series]:
    rng = np.random.default_rng(seed)
    dates = [start + timedelta(days=i) for i in range(n)]
    t = np.arange(n, dtype=float)
    log10_p = 2.0 + 0.0003 * t + rng.normal(0.0, 0.03, size=n)
    return (
        pl.Series("date", dates, dtype=pl.Date),
        pl.Series("close", 10.0**log10_p),
    )


class TestResolveSdcaRiskModel:
    def test_unknown_name_raises(self) -> None:
        dates, price = _series(n=10)
        with pytest.raises(ValueError, match="unknown risk_model 'not_a_provider'"):
            resolve_sdca_risk_model("not_a_provider", dates=dates, price=price)

    def test_btc_power_law_loads_coefficients(self) -> None:
        dates, price = _series(n=20)
        model = resolve_sdca_risk_model(
            "btc_power_law",
            dates=dates,
            price=price,
            coefficients_path=Path(_COEFFICIENTS_EXAMPLE_PATH),
        )
        assert isinstance(model, BtcPowerLawRiskModel)

    def test_generic_valuation_fits_from_series(self) -> None:
        dates, price = _series(n=900)
        model = resolve_sdca_risk_model("generic_valuation", dates=dates, price=price)
        assert isinstance(model, GenericValuationRiskModel)

    def test_rolling_z_from_short_series(self) -> None:
        dates, price = _series(n=60)
        model = resolve_sdca_risk_model("rolling_z", dates=dates, price=price, rolling_window=20)
        assert isinstance(model, RollingZRiskModel)

    def test_known_names_cover_the_ladder(self) -> None:
        assert KNOWN_SDCA_RISK_MODELS == (
            "btc_power_law",
            "generic_valuation",
            "rolling_z",
        )


class TestBuildRiskIndexViaSelector:
    def test_each_provider_builds_a_risk_index(self) -> None:
        btc_dates, btc_price = _series(n=30, start=date(2020, 1, 1))
        btc_model = resolve_sdca_risk_model(
            "btc_power_law",
            dates=btc_dates,
            price=btc_price,
            coefficients_path=Path(_COEFFICIENTS_EXAMPLE_PATH),
        )
        btc_frame = build_risk_index(btc_dates, btc_price, btc_model)
        assert btc_frame.height == 30
        assert btc_frame["risk"].null_count() == 0

        gen_dates, gen_price = _series(n=900, start=date(2018, 1, 1), seed=1)
        gen_model = resolve_sdca_risk_model("generic_valuation", dates=gen_dates, price=gen_price)
        gen_frame = build_risk_index(gen_dates, gen_price, gen_model)
        assert gen_frame.height == 900
        assert gen_frame["risk"].null_count() == 0
        assert (gen_frame["low"] < gen_frame["median"]).all()

        z_dates, z_price = _series(n=80, start=date(2024, 1, 1), seed=2)
        z_model = resolve_sdca_risk_model(
            "rolling_z", dates=z_dates, price=z_price, rolling_window=20
        )
        z_frame = build_risk_index(z_dates, z_price, z_model)
        assert z_frame.height == 80
        assert z_frame["risk"].null_count() >= 1  # first day has no lookback
        complete = z_frame.filter(pl.col("risk").is_not_null())
        assert complete.height > 0
        assert complete["risk"].is_finite().all()

    def test_generic_valuation_2000_day_index_is_not_capped_at_900(self) -> None:
        dates, price = _series(n=2000, start=date(2015, 7, 20), seed=3)
        model = resolve_sdca_risk_model(
            "generic_valuation",
            dates=dates,
            price=price,
            form="log_linear",
            max_fit_rows=400,
        )
        frame = build_risk_index(dates, price, model)
        assert frame.height == 2000
        assert frame["date"][0] == dates[0]
        assert frame["date"][-1] == dates[-1]
        assert frame["risk"].null_count() == 0
