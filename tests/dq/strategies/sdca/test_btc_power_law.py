"""Tests for the BTC power-law (RAQQR) RiskModel provider (#1082)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

pytestmark = pytest.mark.unit


def _synthetic_series(
    n: int = 1500,
    *,
    start: date = date(2015, 1, 1),
    median_log10: tuple[float, float, float] = (3.5, 2.0, 0.3),
    noise_std: float = 0.05,
    seed: int = 0,
) -> tuple[pl.Series, pl.Series]:
    """A power-law-shaped synthetic close series with known truth coefficients."""
    from digiquant.strategies.sdca.btc_power_law import BTC_GENESIS_DATE

    rng = np.random.default_rng(seed)
    dates = [start + timedelta(days=i) for i in range(n)]
    days_since_genesis = np.array([(d - BTC_GENESIS_DATE).days for d in dates], dtype=float)
    raw_x = np.log(days_since_genesis)
    mu = float(raw_x.mean())
    x = raw_x - mu
    c, a, b = median_log10
    log10_price = c + a * x + b * x**2 + rng.normal(0.0, noise_std, size=n)
    price = 10.0**log10_price
    return pl.Series("date", dates, dtype=pl.Date), pl.Series("close", price)


class TestFitBtcPowerLaw:
    def test_fit_recovers_known_median_coefficients_within_tolerance(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import fit_btc_power_law

        truth = (3.5, 2.0, 0.3)
        dates, price = _synthetic_series(median_log10=truth, noise_std=0.02)
        coefficients = fit_btc_power_law(dates, price)

        q50 = coefficients.quantiles["q50"]
        assert q50.c == pytest.approx(truth[0], abs=0.1)
        assert q50.a == pytest.approx(truth[1], abs=0.1)
        assert q50.b == pytest.approx(truth[2], abs=0.1)

    def test_fit_records_provenance(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import fit_btc_power_law

        dates, price = _synthetic_series()
        coefficients = fit_btc_power_law(dates, price, notes="synthetic")
        assert coefficients.fit_start == dates.to_list()[0]
        assert coefficients.fit_end == dates.to_list()[-1]
        assert coefficients.fit_rows == dates.len()
        assert coefficients.notes == "synthetic"

    def test_rejects_insufficient_history(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import MIN_FIT_HISTORY_DAYS, fit_btc_power_law

        dates, price = _synthetic_series(n=MIN_FIT_HISTORY_DAYS - 1)
        with pytest.raises(ValueError, match="at least"):
            fit_btc_power_law(dates, price)

    def test_rejects_non_date_dtype(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import fit_btc_power_law

        dates = pl.Series("date", ["2020-01-01", "2020-01-02"])
        price = pl.Series("close", [1.0, 2.0])
        with pytest.raises(ValueError, match="pl.Date"):
            fit_btc_power_law(dates, price)

    def test_rejects_non_increasing_dates(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import BTC_GENESIS_DATE, fit_btc_power_law

        n = 800
        start = BTC_GENESIS_DATE + timedelta(days=2000)
        dates = pl.Series("date", [start + timedelta(days=i) for i in range(n)], dtype=pl.Date)
        dates_list = dates.to_list()
        dates_list[1], dates_list[2] = dates_list[2], dates_list[1]
        dates = pl.Series("date", dates_list, dtype=pl.Date)
        price = pl.Series("close", list(range(1, n + 1)), dtype=pl.Float64)
        with pytest.raises(ValueError, match="strictly increasing"):
            fit_btc_power_law(dates, price)

    def test_rejects_non_positive_price(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import fit_btc_power_law

        dates, price = _synthetic_series()
        bad_price = price.scatter(0, -1.0)
        with pytest.raises(ValueError, match="positive"):
            fit_btc_power_law(dates, bad_price)

    def test_rejects_dates_on_or_before_genesis(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import BTC_GENESIS_DATE, fit_btc_power_law

        n = 800
        dates = pl.Series(
            "date", [BTC_GENESIS_DATE + timedelta(days=i) for i in range(n)], dtype=pl.Date
        )
        price = pl.Series("close", list(range(1, n + 1)), dtype=pl.Float64)
        with pytest.raises(ValueError, match="after genesis"):
            fit_btc_power_law(dates, price)

    def test_rejects_mismatched_lengths(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import fit_btc_power_law

        dates, price = _synthetic_series()
        with pytest.raises(ValueError, match="same length"):
            fit_btc_power_law(dates, price.head(price.len() - 1))


class TestBtcPowerLawCoefficientsModel:
    def test_rejects_incomplete_quantile_set(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            BtcPowerLawCoefficients,
            QuantileCoefficients,
        )

        with pytest.raises(ValueError, match="quantiles must cover exactly"):
            BtcPowerLawCoefficients(
                genesis=date(2009, 1, 3),
                mu=0.0,
                fit_start=date(2020, 1, 1),
                fit_end=date(2020, 1, 2),
                fit_rows=2,
                notes="",
                quantiles={"q50": QuantileCoefficients(c=0.0, a=0.0, b=0.0)},
            )

    def test_is_frozen(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import QuantileCoefficients

        coeff = QuantileCoefficients(c=1.0, a=2.0, b=3.0)
        with pytest.raises(ValueError):
            coeff.c = 5.0


class TestPersistence:
    def test_save_and_load_round_trip(self, tmp_path) -> None:
        from digiquant.strategies.sdca.btc_power_law import fit_btc_power_law, save_coefficients

        dates, price = _synthetic_series()
        coefficients = fit_btc_power_law(dates, price, notes="round-trip test")
        path = tmp_path / "coeffs.json"
        save_coefficients(coefficients, path)

        from digiquant.strategies.sdca.btc_power_law import load_coefficients

        loaded = load_coefficients(path)
        assert loaded == coefficients

    def test_load_missing_path_raises(self, tmp_path) -> None:
        from digiquant.strategies.sdca.btc_power_law import load_coefficients

        with pytest.raises(FileNotFoundError):
            load_coefficients(tmp_path / "does_not_exist.json")

    def test_load_example_placeholder_warns(self, caplog) -> None:
        from digiquant.strategies.sdca.btc_power_law import load_coefficients

        with caplog.at_level("WARNING"):
            coefficients = load_coefficients()
        assert coefficients.fit_rows > 0
        assert any("synthetic" in rec.message.lower() for rec in caplog.records) or any(
            "placeholder" in rec.message.lower() for rec in caplog.records
        )


class TestBtcPowerLawRiskModel:
    def test_satisfies_risk_model_protocol(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
        from digiquant.strategies.sdca.risk_model import RiskModel

        model = BtcPowerLawRiskModel(load_coefficients())
        assert isinstance(model, RiskModel)

    def test_rails_returns_low_median_high_non_crossing(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            BTC_GENESIS_DATE,
            BtcPowerLawRiskModel,
            load_coefficients,
        )

        model = BtcPowerLawRiskModel(load_coefficients())
        dates = pl.Series(
            "date",
            [BTC_GENESIS_DATE + timedelta(days=2000 + 30 * i) for i in range(20)],
            dtype=pl.Date,
        )
        rails = model.rails(dates)
        assert set(rails.columns) == {"low", "median", "high"}
        assert rails.height == dates.len()
        assert (rails["low"] < rails["median"]).all()
        assert (rails["median"] < rails["high"]).all()

    def test_rails_full_is_non_crossing_across_all_seven_quantiles(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            BTC_GENESIS_DATE,
            QUANTILE_LABELS,
            BtcPowerLawRiskModel,
            load_coefficients,
        )

        model = BtcPowerLawRiskModel(load_coefficients())
        dates = pl.Series(
            "date",
            [BTC_GENESIS_DATE + timedelta(days=2000 + 30 * i) for i in range(20)],
            dtype=pl.Date,
        )
        full = model.rails_full(dates)
        values = full.select(list(QUANTILE_LABELS)).to_numpy()
        assert (np.diff(values, axis=1) >= 0).all()

    def test_rails_null_on_or_before_genesis(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            BTC_GENESIS_DATE,
            BtcPowerLawRiskModel,
            load_coefficients,
        )

        model = BtcPowerLawRiskModel(load_coefficients())
        dates = pl.Series("date", [BTC_GENESIS_DATE, BTC_GENESIS_DATE + timedelta(days=1000)])
        rails = model.rails(dates)
        assert rails["low"][0] is None
        assert rails["median"][0] is None
        assert rails["high"][0] is None
        assert rails["median"][1] is not None

    def test_rejects_quantile_not_in_fitted_set(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients

        with pytest.raises(ValueError, match="low/high quantile"):
            BtcPowerLawRiskModel(load_coefficients(), low_quantile=0.05)

    def test_rejects_low_quantile_not_below_median(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients

        with pytest.raises(ValueError, match="low_quantile must be"):
            BtcPowerLawRiskModel(load_coefficients(), low_quantile=0.75, high_quantile=0.25)
