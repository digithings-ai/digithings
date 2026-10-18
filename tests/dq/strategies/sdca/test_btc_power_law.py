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

    def test_raises_on_quantreg_non_convergence_instead_of_persisting_garbage(self) -> None:
        """QuantReg's IRLS solver never raises on non-convergence — it silently
        returns whatever ``beta`` it was on at ``max_iter``, with only a
        ``warnings.warn(IterationLimitWarning)`` as the signal (see
        ``statsmodels.regression.quantile_regression.QuantReg.fit``). A price
        series that alternates between astronomically large and tiny (but still
        positive, finite, strictly-increasing-date) values every day is a
        genuinely pathological design for the IRLS reweighting to solve, and
        empirically drives it to hit ``max_iter=2000`` without converging.
        ``fit_btc_power_law`` must raise rather than silently persist the
        resulting garbage coefficients.
        """
        from digiquant.strategies.sdca.btc_power_law import fit_btc_power_law

        n = 1500
        start = date(2015, 1, 1)
        dates = pl.Series("date", [start + timedelta(days=i) for i in range(n)], dtype=pl.Date)
        alternating = np.where(np.arange(n) % 2 == 0, 1e12, 1e-6).astype(float)
        price = pl.Series("close", alternating)

        with pytest.raises(ValueError, match="converge"):
            fit_btc_power_law(dates, price)

    def test_rejects_row_count_at_floor_with_insufficient_calendar_span(self) -> None:
        """``MIN_FIT_HISTORY_DAYS`` consecutive daily rows is the previous check's
        exact acceptance boundary, and it spans only ``MIN_FIT_HISTORY_DAYS - 1``
        calendar days (N strictly-increasing dates span at least N-1 days) — one
        day short of what the name/docstring promise. The old row-count-only check
        wrongly accepted this; the calendar-span check must now reject it.
        """
        from digiquant.strategies.sdca.btc_power_law import MIN_FIT_HISTORY_DAYS, fit_btc_power_law

        dates, price = _synthetic_series(n=MIN_FIT_HISTORY_DAYS)
        assert (dates.to_list()[-1] - dates.to_list()[0]).days == MIN_FIT_HISTORY_DAYS - 1
        with pytest.raises(ValueError, match="calendar"):
            fit_btc_power_law(dates, price)

    def test_accepts_gappy_series_at_same_row_count_once_span_is_sufficient(self) -> None:
        """Same total row count as the rejected floor case above (so row count
        alone cannot explain the difference), but with one extra day of gap
        inserted so the calendar span reaches ``MIN_FIT_HISTORY_DAYS`` — this must
        now pass, showing the guard is keyed on calendar coverage, not density.
        """
        from digiquant.strategies.sdca.btc_power_law import (
            BTC_GENESIS_DATE,
            MIN_FIT_HISTORY_DAYS,
            fit_btc_power_law,
        )

        n = MIN_FIT_HISTORY_DAYS
        start = BTC_GENESIS_DATE + timedelta(days=2000)
        # n-1 consecutive rows, then one row pushed one extra day out — same row
        # count as the fully-dense floor case, but a gap widens the span by 1 day.
        gappy_dates = [start + timedelta(days=i) for i in range(n - 1)]
        gappy_dates.append(gappy_dates[-1] + timedelta(days=2))
        dates = pl.Series("date", gappy_dates, dtype=pl.Date)
        assert dates.len() == n
        assert (gappy_dates[-1] - gappy_dates[0]).days == MIN_FIT_HISTORY_DAYS

        days_since_genesis = np.array(
            [(d - BTC_GENESIS_DATE).days for d in gappy_dates], dtype=float
        )
        raw_x = np.log(days_since_genesis)
        mu = float(raw_x.mean())
        x = raw_x - mu
        c, a, b = (3.5, 2.0, 0.3)
        rng = np.random.default_rng(0)
        log10_price = c + a * x + b * x**2 + rng.normal(0.0, 0.02, size=n)
        price = pl.Series("close", 10.0**log10_price)

        coefficients = fit_btc_power_law(dates, price)
        assert coefficients.fit_rows == n


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
        from digiquant.strategies.sdca.btc_power_law import (
            _COEFFICIENTS_EXAMPLE_PATH,
            load_coefficients,
        )

        with caplog.at_level("WARNING"):
            coefficients = load_coefficients(_COEFFICIENTS_EXAMPLE_PATH)
        assert coefficients.fit_rows > 0
        assert any("synthetic" in rec.message.lower() for rec in caplog.records) or any(
            "placeholder" in rec.message.lower() for rec in caplog.records
        )

    def test_load_default_uses_committed_real_fit_without_placeholder_warning(self, caplog) -> None:
        """#3173: normal path is the committed Coinbase fit, not the synthetic example.

        Does not assert coefficient values — those are the fitted artifact, not a
        unit fixture. Pins provenance so a silent revert to the placeholder fails.
        """
        from datetime import date

        from digiquant.strategies.sdca.btc_power_law import (
            _COEFFICIENTS_PATH,
            load_coefficients,
        )

        if not _COEFFICIENTS_PATH.exists():
            pytest.skip("real coefficients file not present")
        with caplog.at_level("WARNING"):
            coefficients = load_coefficients()
        assert coefficients.fit_start == date(2015, 7, 20)
        assert coefficients.fit_rows >= 4000
        assert coefficients.notes.startswith("Real Coinbase")
        assert not any("placeholder" in rec.message.lower() for rec in caplog.records)
        assert not any("synthetic" in rec.message.lower() for rec in caplog.records)


class TestBtcPowerLawRiskModel:
    def test_satisfies_risk_model_protocol(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            _COEFFICIENTS_EXAMPLE_PATH,
            BtcPowerLawRiskModel,
            load_coefficients,
        )
        from digiquant.strategies.sdca.risk_model import RiskModel

        model = BtcPowerLawRiskModel(load_coefficients(_COEFFICIENTS_EXAMPLE_PATH))
        assert isinstance(model, RiskModel)

    def test_rails_returns_low_median_high_non_crossing(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            _COEFFICIENTS_EXAMPLE_PATH,
            BTC_GENESIS_DATE,
            BtcPowerLawRiskModel,
            load_coefficients,
        )

        model = BtcPowerLawRiskModel(load_coefficients(_COEFFICIENTS_EXAMPLE_PATH))
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
            _COEFFICIENTS_EXAMPLE_PATH,
            BTC_GENESIS_DATE,
            QUANTILE_LABELS,
            BtcPowerLawRiskModel,
            load_coefficients,
        )

        model = BtcPowerLawRiskModel(load_coefficients(_COEFFICIENTS_EXAMPLE_PATH))
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
            _COEFFICIENTS_EXAMPLE_PATH,
            BTC_GENESIS_DATE,
            BtcPowerLawRiskModel,
            load_coefficients,
        )

        model = BtcPowerLawRiskModel(load_coefficients(_COEFFICIENTS_EXAMPLE_PATH))
        dates = pl.Series("date", [BTC_GENESIS_DATE, BTC_GENESIS_DATE + timedelta(days=1000)])
        rails = model.rails(dates)
        assert rails["low"][0] is None
        assert rails["median"][0] is None
        assert rails["high"][0] is None
        assert rails["median"][1] is not None

    def test_rejects_quantile_not_in_fitted_set(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            _COEFFICIENTS_EXAMPLE_PATH,
            BtcPowerLawRiskModel,
            load_coefficients,
        )

        with pytest.raises(ValueError, match="low/high quantile"):
            BtcPowerLawRiskModel(load_coefficients(_COEFFICIENTS_EXAMPLE_PATH), low_quantile=0.05)

    def test_rejects_low_quantile_not_below_median(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            _COEFFICIENTS_EXAMPLE_PATH,
            BtcPowerLawRiskModel,
            load_coefficients,
        )

        with pytest.raises(ValueError, match="low_quantile must be"):
            BtcPowerLawRiskModel(
                load_coefficients(_COEFFICIENTS_EXAMPLE_PATH), low_quantile=0.75, high_quantile=0.25
            )


class TestRailsCrossingReconciliation:
    """Deliberately-crossing synthetic coefficients reproduce the real failure
    mode (a quantile's raw fitted curve falling out of rank order at some x),
    not just re-check ordering the old row-wise np.sort already passed."""

    def _crossing_coefficients(self):
        from digiquant.strategies.sdca.btc_power_law import (
            BtcPowerLawCoefficients,
            QuantileCoefficients,
        )

        # q75's slope (a=0.9) is steeper than q95's (a=0.55): independently
        # fit, they start in natural rank order at x=0 but q75 overtakes q95
        # once x grows past ~1.9 -- exactly the "independently-fit curves can
        # cross" scenario the module docstring describes. b=0 (linear) keeps
        # the arithmetic easy to hand-verify.
        coeffs = {
            "q01": QuantileCoefficients(c=1.0, a=0.5, b=0.0),
            "q10": QuantileCoefficients(c=1.5, a=0.55, b=0.0),
            "q25": QuantileCoefficients(c=2.0, a=0.6, b=0.0),
            "q50": QuantileCoefficients(c=2.5, a=0.65, b=0.0),
            "q75": QuantileCoefficients(c=3.0, a=0.9, b=0.0),
            "q95": QuantileCoefficients(c=3.3, a=0.55, b=0.0),
            "q99": QuantileCoefficients(c=3.5, a=0.95, b=0.0),
        }
        return BtcPowerLawCoefficients(
            genesis=date(1900, 1, 1),
            mu=0.0,
            fit_start=date(1900, 1, 1),
            fit_end=date(1900, 1, 11),
            fit_rows=10,
            notes="synthetic crossing fixture, not a real fit",
            quantiles=coeffs,
        )

    def _raw_values(self, coefficients, dates: list[date]):
        """Same formula as _evaluate_rails, without reconciliation -- what
        the pre-fix code path would have handed to np.sort."""
        from digiquant.strategies.sdca.btc_power_law import QUANTILE_LABELS

        days_since_genesis = np.array(
            [(d - coefficients.genesis).days for d in dates], dtype=float
        )
        x = np.log(days_since_genesis) - coefficients.mu
        raw = np.full((len(dates), len(QUANTILE_LABELS)), np.nan)
        for j, label in enumerate(QUANTILE_LABELS):
            coeff = coefficients.quantiles[label]
            raw[:, j] = 10.0 ** (coeff.c + coeff.a * x + coeff.b * x**2)
        return raw

    def test_reconciled_q95_is_its_own_value_clamped_not_a_swapped_quantile(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            QUANTILE_LABELS,
            BtcPowerLawRiskModel,
        )

        coefficients = self._crossing_coefficients()
        model = BtcPowerLawRiskModel(coefficients)
        # x=0 (day 1, no crossing) and x=ln(10) (day 10, q75 overtakes q95).
        dates = [date(1900, 1, 2), date(1900, 1, 11)]
        raw = self._raw_values(coefficients, dates)

        full = model.rails_full(pl.Series("date", dates, dtype=pl.Date))
        values = full.select(list(QUANTILE_LABELS)).to_numpy()

        q50_idx, q75_idx, q95_idx = 3, 4, 5

        # Row 1 (x=ln(10)) genuinely crossed in the raw fit: q75 > q95.
        assert raw[1, q75_idx] > raw[1, q95_idx]
        # Non-crossing invariant holds on the reconciled output.
        assert (np.diff(values, axis=1) >= 0).all()
        # Reconciled q95 is its OWN raw value clamped up to reconciled q75 --
        # not the raw q50 value that a plain ascending np.sort would relabel
        # into the q95 slot (np.sort(raw[1])[q95_idx] would equal raw q50).
        assert values[1, q95_idx] == pytest.approx(max(raw[1, q95_idx], values[1, q75_idx]))
        assert values[1, q95_idx] != pytest.approx(raw[1, q50_idx])
        assert values[1, q95_idx] != pytest.approx(np.sort(raw[1])[q50_idx])
        # Median is never touched by reconciliation.
        assert values[1, q50_idx] == pytest.approx(raw[1, q50_idx])
        # Row 0 had no raw crossing -- reconciliation is a no-op there.
        np.testing.assert_allclose(values[0], raw[0])

    def test_warns_when_a_raw_row_crosses(self, caplog) -> None:
        from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel

        coefficients = self._crossing_coefficients()
        model = BtcPowerLawRiskModel(coefficients)
        dates = pl.Series("date", [date(1900, 1, 2), date(1900, 1, 11)], dtype=pl.Date)
        with caplog.at_level("WARNING"):
            model.rails_full(dates)
        assert any("crossing" in rec.message.lower() for rec in caplog.records)

    def test_no_warning_when_nothing_crosses(self, caplog) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            _COEFFICIENTS_EXAMPLE_PATH,
            BTC_GENESIS_DATE,
            BtcPowerLawRiskModel,
            load_coefficients,
        )

        model = BtcPowerLawRiskModel(load_coefficients(_COEFFICIENTS_EXAMPLE_PATH))
        dates = pl.Series(
            "date",
            [BTC_GENESIS_DATE + timedelta(days=2000 + 30 * i) for i in range(20)],
            dtype=pl.Date,
        )
        caplog.clear()
        with caplog.at_level("WARNING"):
            model.rails_full(dates)
        assert not any("crossing" in rec.message.lower() for rec in caplog.records)

    def test_matches_np_sort_when_real_coefficients_never_cross(self) -> None:
        """Regression guard: where the real committed coefficients never cross
        today, rearrange_non_crossing must reproduce what row-wise np.sort
        produced before this fix -- a no-op until a rail actually crosses."""
        from digiquant.strategies.sdca.btc_power_law import (
            _COEFFICIENTS_EXAMPLE_PATH,
            BTC_GENESIS_DATE,
            load_coefficients,
        )
        from digiquant.strategies.sdca.quantile_rails import rearrange_non_crossing

        coefficients = load_coefficients(_COEFFICIENTS_EXAMPLE_PATH)
        dates = [BTC_GENESIS_DATE + timedelta(days=2000 + 15 * i) for i in range(200)]
        raw = self._raw_values(coefficients, dates)

        reconciled = rearrange_non_crossing(raw)
        np.testing.assert_allclose(reconciled, np.sort(raw, axis=1))


class TestMonotoneUpperRails:
    """Option (a): the ceiling must not fall. q75/q95/q99 are fit with b = 0.

    Measured before the fix: every one of the seven rails was a free quadratic in
    centred log-time with b < 0, so the q95 ceiling peaked 2025-11-08 and fell
    afterwards (113.4k -> 55.4k by 2032), sitting below the 2024-2025 all-time high.
    The constraint is opt-in so the historical all-quadratic fit stays reproducible.
    """

    @staticmethod
    def _horizon(start: date = date(2026, 10, 16), n: int = 44) -> pl.Series:
        return pl.Series(
            "date",
            [start + timedelta(days=90 * i) for i in range(n)],
            dtype=pl.Date,
        )

    def test_checked_in_coefficients_constrain_only_the_ceiling(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            MONOTONE_QUANTILE_LABELS,
            load_coefficients,
        )

        coeffs = load_coefficients()
        for label in MONOTONE_QUANTILE_LABELS:
            assert coeffs.quantiles[label].b == 0.0, label
        # Option (a) deliberately leaves the lower rails quadratic.
        for label in ("q01", "q10", "q25", "q50"):
            assert coeffs.quantiles[label].b != 0.0, label

    def test_upper_rails_never_fall_over_a_forward_horizon(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            MONOTONE_QUANTILE_LABELS,
            _evaluate_rails,
            load_coefficients,
        )

        frame = _evaluate_rails(load_coefficients(), self._horizon())
        for label in MONOTONE_QUANTILE_LABELS:
            values = frame[label].to_list()
            falls = [i for i in range(1, len(values)) if values[i] < values[i - 1]]
            assert not falls, f"{label} falls at rows {falls[:3]}"

    def test_reconciled_rails_stay_ordered_over_the_horizon(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            BtcPowerLawRiskModel,
            load_coefficients,
        )

        horizon = self._horizon()
        # ``rails()`` returns only low/median/high (no date column), so pair each row
        # with the horizon date we asked for — the frame is in the same row order.
        frame = BtcPowerLawRiskModel(load_coefficients()).rails(horizon)
        bad = [
            day
            for day, lo, med, hi in zip(
                horizon.to_list(),
                frame["low"].to_list(),
                frame["median"].to_list(),
                frame["high"].to_list(),
                strict=True,
            )
            if not (lo < med < hi)
        ]
        assert bad == []

    def test_fit_applies_the_constraint_to_the_named_quantiles_only(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            MONOTONE_QUANTILE_LABELS,
            fit_btc_power_law,
        )

        dates, price = _synthetic_series(median_log10=(3.5, 2.0, 0.3))
        coeffs = fit_btc_power_law(dates, price, linear_quantiles=MONOTONE_QUANTILE_LABELS)
        for label in MONOTONE_QUANTILE_LABELS:
            assert coeffs.quantiles[label].b == 0.0, label
        # Quadratic-truth data: the unconstrained median still fits a quadratic, so a
        # zero here would mean the constraint leaked onto a quantile it must not touch.
        assert coeffs.quantiles["q50"].b != 0.0

    def test_rejects_an_unknown_linear_quantile_label(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import fit_btc_power_law

        dates, price = _synthetic_series()
        with pytest.raises(ValueError, match="linear_quantiles"):
            fit_btc_power_law(dates, price, linear_quantiles=("q42",))
