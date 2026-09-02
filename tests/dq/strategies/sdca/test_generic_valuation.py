"""Tests for the generic per-asset valuation-z RiskModel (#3175)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from digiquant.strategies.sdca.generic_valuation import (
    GenericValuationRiskModel,
    fit_generic_valuation,
    load_coefficients,
    save_coefficients,
)
from digiquant.strategies.sdca.quantile_rails import (
    MIN_FIT_HISTORY_DAYS,
    QUANTILE_LABELS,
    REFERENCE_SPAN_DAYS,
    evenly_spaced_fit_indices,
)
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.risk_model import RiskModel

pytestmark = pytest.mark.unit


def _log_trend_series(
    n: int,
    *,
    start: date,
    intercept: float = 2.0,
    slope: float = 0.0004,
    noise_std: float = 0.04,
    seed: int = 1,
) -> tuple[pl.Series, pl.Series]:
    """Synthetic cyclical-crypto log-price series (no genesis, calendar time)."""
    rng = np.random.default_rng(seed)
    dates = [start + timedelta(days=i) for i in range(n)]
    t = np.arange(n, dtype=float)
    cycle = 0.08 * np.sin(2.0 * np.pi * t / 365.25)
    log10_p = intercept + slope * t + cycle + rng.normal(0.0, noise_std, size=n)
    return (
        pl.Series("date", dates, dtype=pl.Date),
        pl.Series("close", 10.0**log10_p),
    )


class TestFitGenericValuation:
    def test_records_origin_as_first_bar_and_form(self) -> None:
        dates, price = _log_trend_series(n=900, start=date(2018, 1, 1))
        coefficients = fit_generic_valuation(dates, price, form="log_linear", notes="eth-like")
        assert coefficients.origin == dates[0]
        assert coefficients.form == "log_linear"
        assert coefficients.fit_rows == 900
        assert coefficients.notes == "eth-like"
        assert all(q.b == 0.0 for q in coefficients.quantiles.values())

    def test_rejects_insufficient_history(self) -> None:
        dates, price = _log_trend_series(n=MIN_FIT_HISTORY_DAYS - 1, start=date(2020, 1, 1))
        with pytest.raises(ValueError, match="at least"):
            fit_generic_valuation(dates, price)

    def test_quadratic_nonconvergence_falls_back_to_log_linear(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.strategies.sdca import generic_valuation as gv

        real = gv.fit_quantile_regression
        calls = {"n": 0}

        def flaky(design, log_prices, *, caller: str, max_iter: int = 2000):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError(
                    f"{caller}: QuantReg failed to converge for quantile 0.95 (q95): "
                    "Maximum number of iterations (2000) reached."
                )
            return real(design, log_prices, caller=caller, max_iter=max_iter)

        monkeypatch.setattr(gv, "fit_quantile_regression", flaky)
        dates, price = _log_trend_series(n=900, start=date(2018, 1, 1))
        coefficients = fit_generic_valuation(dates, price, form="log_quadratic")
        assert coefficients.form == "log_linear"
        assert "did not converge" in coefficients.notes
        assert all(q.b == 0.0 for q in coefficients.quantiles.values())

    def test_widen_factor_is_one_on_long_history(self) -> None:
        n = REFERENCE_SPAN_DAYS + 2
        dates, price = _log_trend_series(n=n, start=date(2015, 1, 1), noise_std=0.02)
        coefficients = fit_generic_valuation(dates, price, form="log_linear")
        assert coefficients.widen_factor == pytest.approx(1.0)

    def test_save_and_load_round_trip(self, tmp_path) -> None:
        dates, price = _log_trend_series(n=900, start=date(2018, 1, 1))
        coefficients = fit_generic_valuation(dates, price, notes="round-trip")
        path = tmp_path / "generic.json"
        save_coefficients(coefficients, path)
        assert load_coefficients(path) == coefficients


class TestGenericValuationRiskModel:
    def test_satisfies_risk_model_protocol(self) -> None:
        dates, price = _log_trend_series(n=900, start=date(2018, 1, 1))
        model = GenericValuationRiskModel(fit_generic_valuation(dates, price, form="log_linear"))
        assert isinstance(model, RiskModel)

    def test_eth_length_rails_non_crossing(self) -> None:
        # ETH-era start (2017-08), synthetic daily history — no network.
        dates, price = _log_trend_series(n=1500, start=date(2017, 8, 1), seed=2)
        model = GenericValuationRiskModel(fit_generic_valuation(dates, price))
        rails = model.rails(dates)
        assert set(rails.columns) == {"low", "median", "high"}
        complete = rails.drop_nulls()
        assert complete.height == dates.len()
        assert (complete["low"] < complete["median"]).all()
        assert (complete["median"] < complete["high"]).all()
        full = model.rails_full(dates).select(list(QUANTILE_LABELS)).to_numpy()
        assert (np.diff(full, axis=1) >= 0).all()

    def test_sol_length_rails_non_crossing(self) -> None:
        # SOL-era start (2020-04), shorter than ETH — still above the fit floor.
        dates, price = _log_trend_series(n=1200, start=date(2020, 4, 10), seed=3)
        model = GenericValuationRiskModel(fit_generic_valuation(dates, price, form="log_linear"))
        rails = model.rails(dates)
        complete = rails.drop_nulls()
        assert (complete["low"] < complete["median"]).all()
        assert (complete["median"] < complete["high"]).all()

    def test_truncated_history_widens_rails(self) -> None:
        """A 2-year fit must emit wider rails than a 12-year fit on the overlap.

        Pins the short-history widen mechanism on truncated history, not just
        a widen_factor field check.
        """
        n_long = 12 * 365 + 5
        dates, price = _log_trend_series(n=n_long, start=date(2014, 1, 1), noise_std=0.03, seed=4)
        long_fit = fit_generic_valuation(dates, price, form="log_linear")
        assert long_fit.widen_factor == pytest.approx(1.0)

        n_short = MIN_FIT_HISTORY_DAYS + 1
        short_dates = dates.tail(n_short)
        short_price = price.tail(n_short)
        short_fit = fit_generic_valuation(short_dates, short_price, form="log_linear")
        short_span = (short_dates[-1] - short_dates[0]).days
        assert short_fit.widen_factor == pytest.approx(REFERENCE_SPAN_DAYS / short_span)
        assert short_fit.widen_factor > long_fit.widen_factor

        probe = pl.Series("date", [dates[-1]], dtype=pl.Date)
        long_rails = GenericValuationRiskModel(long_fit).rails(probe)
        short_rails = GenericValuationRiskModel(short_fit).rails(probe)
        long_width = float(np.log(long_rails["high"][0] / long_rails["low"][0]))
        short_width = float(np.log(short_rails["high"][0] / short_rails["low"][0]))
        assert short_width > long_width

    def test_same_coefficients_widen_in_isolation(self) -> None:
        dates, price = _log_trend_series(n=900, start=date(2018, 1, 1), noise_std=0.03)
        coefficients = fit_generic_valuation(dates, price, form="log_linear")
        narrow = GenericValuationRiskModel(coefficients.model_copy(update={"widen_factor": 1.0}))
        wide = GenericValuationRiskModel(coefficients.model_copy(update={"widen_factor": 4.0}))
        probe = pl.Series("date", [dates[-1]], dtype=pl.Date)
        n_w = np.log(narrow.rails(probe)["high"][0] / narrow.rails(probe)["low"][0])
        w_w = np.log(wide.rails(probe)["high"][0] / wide.rails(probe)["low"][0])
        assert w_w == pytest.approx(4.0 * n_w, rel=1e-6)


class TestEvenlySpacedFitIndices:
    def test_none_or_cap_above_n_returns_every_row(self) -> None:
        assert evenly_spaced_fit_indices(5, None) == [0, 1, 2, 3, 4]
        assert evenly_spaced_fit_indices(5, 5) == [0, 1, 2, 3, 4]
        assert evenly_spaced_fit_indices(5, 50) == [0, 1, 2, 3, 4]

    def test_subsample_covers_full_span_not_a_900_prefix(self) -> None:
        idx = evenly_spaced_fit_indices(2000, 400)
        assert idx[0] == 0
        assert idx[-1] == 1999
        assert len(idx) <= 400
        assert len(idx) >= 390
        assert idx != list(range(400))
        assert 900 not in {len(idx), idx[-1] + 1}


class TestFullHistoryGenericRails:
    def test_2000_day_series_scores_every_day_not_900(self) -> None:
        """Prefix-clipping QuantReg at 900 days ended BTC charts in Jan 2018."""
        dates, price = _log_trend_series(n=2000, start=date(2015, 7, 20), seed=7)
        coefficients = fit_generic_valuation(dates, price, form="log_linear", max_fit_rows=400)
        assert coefficients.fit_start == dates[0]
        assert coefficients.fit_end == dates[-1]
        assert 390 <= coefficients.fit_rows <= 400
        assert coefficients.fit_rows != 900
        model = GenericValuationRiskModel(coefficients)
        rails = model.rails(dates)
        assert rails.height == 2000
        frame = build_risk_index(dates, price, model)
        assert frame.height == 2000
        assert frame["date"][0] == dates[0]
        assert frame["date"][-1] == dates[-1]
        assert frame["risk"].null_count() == 0
        complete = frame.filter(pl.col("risk").is_not_null())
        assert complete.height == 2000
        assert complete["risk"].is_finite().all()
