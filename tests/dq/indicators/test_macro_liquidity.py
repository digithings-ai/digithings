"""Unit tests for MacroLiquidityModel (#1085)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from digiquant.indicators.macro_liquidity import (
    DEFAULT_MACRO_SPECS,
    MacroLiquidityConfig,
    MacroLiquidityModel,
    MacroSeriesSpec,
    RegimeState,
    backtest_regime_gate,
    load_regime_series,
    regime_index_by_date,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def _dates(n: int, start: date = date(2018, 1, 1)) -> pl.Series:
    return pl.Series("date", [start + timedelta(days=i) for i in range(n)])


def _series_frame(
    dates: pl.Series,
    values: np.ndarray | list[float],
    *,
    every: int = 1,
) -> pl.DataFrame:
    """Sparse observation frame (macro cadence) on a subset of calendar days."""
    idxs = list(range(0, len(dates), every))
    return pl.DataFrame(
        {
            "date": [dates[i] for i in idxs],
            "value": [float(values[i]) for i in idxs],
        }
    )


def _synthetic_bundle(n: int = 400) -> tuple[pl.Series, dict[str, pl.DataFrame]]:
    """Four rising/falling series so z-signs are deterministic after warmup."""
    rng = np.random.default_rng(7)
    dates = _dates(n)
    t = np.arange(n, dtype=float)
    # Expanding liquidity, weak dollar, falling unemployment, rising mfg employment.
    m2 = 15_000.0 + t * 3.0 + rng.normal(0, 5, n)
    dxy = 120.0 - t * 0.02 + rng.normal(0, 0.3, n)
    unrate = 8.0 - t * 0.005 + rng.normal(0, 0.05, n)
    manemp = 11_000.0 + t * 1.5 + rng.normal(0, 8, n)
    series = {
        "m2": _series_frame(dates, m2, every=7),
        "dxy": _series_frame(dates, dxy, every=1),
        "unrate": _series_frame(dates, unrate, every=30),
        "pmi": _series_frame(dates, manemp, every=30),
    }
    return dates, series


class TestMacroSeriesSpec:
    def test_default_specs_include_m2_and_two_new(self) -> None:
        names = {s.name for s in DEFAULT_MACRO_SPECS if s.enabled}
        assert "m2" in names
        assert {"dxy", "unrate"} <= names
        assert len(names) >= 3

    def test_rejects_bad_weight(self) -> None:
        with pytest.raises(ValidationError):
            MacroSeriesSpec(name="m2", series_id="M2SL", weight=0.0)


class TestMacroLiquidityModel:
    def test_blends_m2_plus_macros_into_regime_columns(self) -> None:
        dates, series = _synthetic_bundle()
        model = MacroLiquidityModel()
        out = model.compute(dates, series)
        for col in (
            "m2_z",
            "dxy_z",
            "unrate_z",
            "pmi_z",
            "composite_z",
            "regime_score",
            "avg_vote",
            "regime_state",
            "risk_on",
        ):
            assert col in out.columns
        assert len(out) == len(dates)
        valid = out.drop_nulls(subset=["regime_score"])
        assert len(valid) > 0
        assert valid["regime_score"].min() >= 0.0
        assert valid["regime_score"].max() <= 100.0
        states = set(valid["regime_state"].unique().to_list())
        assert states <= {
            RegimeState.EXPANSION.value,
            RegimeState.NEUTRAL.value,
            RegimeState.CONTRACTION.value,
        }

    def test_dxy_sign_flips_strong_dollar_to_negative_z(self) -> None:
        n = 200
        dates = _dates(n)
        # Flat M2/UNRATE/MANEMP; rising dollar only.
        flat = np.full(n, 100.0)
        rising_dxy = 90.0 + np.linspace(0, 20, n)
        series = {
            "m2": _series_frame(dates, flat),
            "dxy": _series_frame(dates, rising_dxy),
            "unrate": _series_frame(dates, flat),
            "pmi": _series_frame(dates, flat),
        }
        # Isolate DXY vote.
        cfg = MacroLiquidityConfig(
            specs=(MacroSeriesSpec(name="dxy", series_id="DTWEXBGS", transform="level", sign=-1),),
            window=60,
            min_samples=20,
        )
        out = MacroLiquidityModel(cfg).compute(dates, series)
        tail = out.drop_nulls(subset=["dxy_z"]).tail(30)
        assert (tail["dxy_z"] < 0).mean() > 0.7

    def test_missing_enabled_series_raises(self) -> None:
        dates, series = _synthetic_bundle(120)
        del series["dxy"]
        with pytest.raises(KeyError, match="dxy"):
            MacroLiquidityModel().compute(dates, series)

    def test_write_and_load_regime_series(self, tmp_path: Path) -> None:
        dates, series = _synthetic_bundle(250)
        model = MacroLiquidityModel()
        out = model.compute(dates, series)
        path = model.write_regime_series(out, tmp_path / "regime.parquet")
        loaded = load_regime_series(path)
        assert loaded.columns == [
            "date",
            "regime_score",
            "regime_state",
            "risk_on",
            "composite_z",
            "avg_vote",
        ]
        index = regime_index_by_date(loaded)
        assert len(index) == len(loaded)
        sample_date = loaded["date"][0]
        state, risk = index[sample_date]
        assert state in (
            None,
            RegimeState.EXPANSION.value,
            RegimeState.NEUTRAL.value,
            RegimeState.CONTRACTION.value,
        )
        assert risk in (None, True, False)

    def test_config_rejects_inverted_thresholds(self) -> None:
        with pytest.raises(ValidationError):
            MacroLiquidityConfig(expansion_threshold=40.0, contraction_threshold=60.0)


class TestRegimeGateBacktest:
    def test_gate_raises_cash_in_contraction_vs_always_in(self) -> None:
        # Price rises then crashes. Gate is risk-on only in the rising half.
        n = 100
        dates = [date(2020, 1, 1) + timedelta(days=i) for i in range(n)]
        price = [100.0 + i for i in range(50)] + [150.0 - (i - 49) * 2 for i in range(50, n)]
        risk_on = [True] * 50 + [False] * 50
        report = backtest_regime_gate(dates, price, risk_on, initial_cash=10_000.0)
        assert report.days_total == n
        assert report.days_invested == 50
        assert report.days_cash == 50
        # Always-in rides the crash; gated exits at the top → gated beats always-in.
        assert report.gated_return_pct > report.always_in_return_pct
        assert report.gated_minus_always_pct > 0.0

    def test_always_on_matches_buy_and_hold(self) -> None:
        dates = [date(2021, 1, 1) + timedelta(days=i) for i in range(10)]
        price = [10.0 * (1.01**i) for i in range(10)]
        report = backtest_regime_gate(dates, price, [True] * 10, initial_cash=1_000.0)
        expected = (price[-1] / price[0] - 1.0) * 100.0
        assert report.always_in_return_pct == pytest.approx(expected, rel=1e-9)
        assert report.gated_return_pct == pytest.approx(expected, rel=1e-9)
        assert report.gated_minus_always_pct == pytest.approx(0.0, abs=1e-9)
