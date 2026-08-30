"""Weekly RSI / MACD and SMA-band z — causal, ISO-week, no lookahead."""

from __future__ import annotations

import datetime as _dt
from datetime import date

import polars as pl
import pytest
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    PRICE_OSCILLATOR_NAMES,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    build_extra_indicators,
    composite_weights_from_params,
)
from digiquant.strategies.sdca.price_oscillators import (
    completed_weekly_closes,
    sma_band_z,
    weekly_macd_z,
    weekly_rsi_z,
)

pytestmark = pytest.mark.unit


def _dates(n: int, start: date = date(2020, 1, 6)) -> pl.Series:
    """Default start is a Monday so ISO weeks line up."""
    return pl.Series("date", [start + _dt.timedelta(days=i) for i in range(n)], dtype=pl.Date)


class TestCompletedWeeklyCloses:
    def test_drops_in_progress_iso_week(self) -> None:
        # Mon 6 Jan 2020 … Wed 22 Jan 2020 (week of 20 Jan is incomplete).
        dates = _dates(17)
        close = pl.Series([float(i + 1) for i in range(17)])
        weekly = completed_weekly_closes(dates, close)
        week_ends = weekly["week_end"].to_list()
        assert date(2020, 1, 12) in week_ends  # first full week Sun
        assert date(2020, 1, 19) in week_ends  # second full week Sun
        assert date(2020, 1, 22) not in week_ends  # incomplete Wed

    def test_weekly_close_is_last_daily_of_completed_week(self) -> None:
        dates = _dates(14)
        close = pl.Series([10.0 + i for i in range(14)])
        weekly = completed_weekly_closes(dates, close)
        # Week Mon 6–Sun 12 Jan: last close is day index 6 (value 16.0).
        first = weekly.filter(pl.col("week_end") == date(2020, 1, 12))
        assert first.height == 1
        assert first["close"][0] == pytest.approx(16.0)


class TestWeeklyRsiZ:
    def test_oversold_weekly_rsi_is_positive_z(self) -> None:
        n = 280  # ~40 weeks
        dates = _dates(n)
        # Steady grind down so weekly RSI sits well below 50.
        close = pl.Series([1000.0 - 2.0 * i for i in range(n)])
        z = weekly_rsi_z(dates, close)
        tail = [v for v in z.to_list()[-60:] if v is not None]
        assert tail, "expected weekly RSI z after warmup"
        assert sum(tail) / len(tail) > 0.5

    def test_overbought_weekly_rsi_is_negative_z(self) -> None:
        n = 280
        dates = _dates(n)
        close = pl.Series([100.0 + 2.0 * i for i in range(n)])
        z = weekly_rsi_z(dates, close)
        tail = [v for v in z.to_list()[-60:] if v is not None]
        assert tail
        assert sum(tail) / len(tail) < -0.5

    def test_wednesday_does_not_see_same_week_friday_spike(self) -> None:
        n = 250
        dates = _dates(n)
        # Oscillate so weekly RSI is not already clipped at ±3.
        base = [100.0 + 8.0 * ((i % 20) - 10) for i in range(n)]
        z1 = weekly_rsi_z(dates, pl.Series(base))
        spiked = base.copy()
        # Spike the ISO week-end (Sunday). Wednesday of that week must not see it;
        # the following Monday must.
        sunday = date(2020, 5, 17)
        idx = dates.to_list().index(sunday)
        spiked[idx] = 10_000.0
        z2 = weekly_rsi_z(dates, pl.Series(spiked))
        wednesday = date(2020, 5, 13)
        w_idx = dates.to_list().index(wednesday)
        assert z1[w_idx] is not None
        assert z1[w_idx] == pytest.approx(z2[w_idx])
        next_monday = date(2020, 5, 18)
        m_idx = dates.to_list().index(next_monday)
        assert z1[m_idx] != pytest.approx(z2[m_idx])

    def test_clipped_to_unit_interval(self) -> None:
        n = 200
        dates = _dates(n)
        close = pl.Series([50.0 + i for i in range(n)])
        z = weekly_rsi_z(dates, close)
        finite = [v for v in z.to_list() if v is not None]
        assert finite
        assert max(finite) <= 3.0 + 1e-9
        assert min(finite) >= -3.0 - 1e-9


class TestWeeklyMacdZ:
    def test_default_macd_weight_is_zero(self) -> None:
        w = SdcaCompositeWeights()
        assert w.weekly_macd == pytest.approx(0.0)
        assert "weekly_macd" not in w.enabled_extras()

    def test_macd_is_causal_asof_like_rsi(self) -> None:
        n = 800
        dates = _dates(n)
        base = [100.0 + 4.0 * ((i % 30) - 15) for i in range(n)]
        z1 = weekly_macd_z(dates, pl.Series(base))
        spiked = base.copy()
        sunday = date(2021, 6, 13)
        idx = dates.to_list().index(sunday)
        spiked[idx] = 50_000.0
        z2 = weekly_macd_z(dates, pl.Series(spiked))
        wednesday = date(2021, 6, 9)
        w_idx = dates.to_list().index(wednesday)
        assert z1[w_idx] is not None
        assert z1[w_idx] == pytest.approx(z2[w_idx])
        next_monday = date(2021, 6, 14)
        m_idx = dates.to_list().index(next_monday)
        assert z1[m_idx] is not None
        assert z1[m_idx] != pytest.approx(z2[m_idx])


class TestSmaBandZ:
    def test_below_slow_sma_is_positive_z(self) -> None:
        n = 150
        dates = _dates(n)
        # Flat then a crash: close sits below the 90d SMA.
        close = pl.Series([100.0] * 90 + [60.0] * 60)
        z = sma_band_z(dates, close, window=90, min_samples=30)
        # Right after the crash the SMA has not yet followed; the tail has.
        after = [v for v in z.to_list()[90:110] if v is not None]
        assert after
        assert sum(after) / len(after) > 1.0

    def test_above_slow_sma_is_negative_z(self) -> None:
        n = 150
        dates = _dates(n)
        close = pl.Series([100.0] * 90 + [160.0] * 60)
        z = sma_band_z(dates, close, window=90, min_samples=30)
        after = [v for v in z.to_list()[90:110] if v is not None]
        assert after
        assert sum(after) / len(after) < -1.0

    def test_is_causal(self) -> None:
        n = 120
        dates = _dates(n)
        base = [100.0] * n
        z1 = sma_band_z(dates, pl.Series(base), window=90, min_samples=30)
        spiked = base.copy()
        spiked[-1] = 400.0
        z2 = sma_band_z(dates, pl.Series(spiked), window=90, min_samples=30)
        assert z1[100] == pytest.approx(z2[100])


class TestCatalogWiring:
    def test_price_oscillators_listed_and_default_off(self) -> None:
        assert PRICE_OSCILLATOR_NAMES == ("weekly_rsi", "weekly_macd", "sma_band")
        assert set(PRICE_OSCILLATOR_NAMES).issubset(set(EXTRA_INDICATOR_NAMES))
        w = SdcaCompositeWeights()
        assert w.valuation == pytest.approx(1.0)
        assert w.enabled_extras() == {}

    def test_zero_weight_skips_oscillators(self) -> None:
        dates = _dates(30)
        extras = build_extra_indicators(
            dates,
            pl.Series([100.0] * 30),
            SdcaCompositeWeights(),
            ExtraIndicatorSources(),
        )
        assert extras == []

    def test_positive_weekly_rsi_weight_emits_series(self) -> None:
        n = 200
        dates = _dates(n)
        extras = build_extra_indicators(
            dates,
            pl.Series([100.0 + 0.2 * i for i in range(n)]),
            SdcaCompositeWeights(valuation=1.0, weekly_rsi=0.4),
            ExtraIndicatorSources(),
            window=20,
            min_samples=10,
        )
        names = [e.name for e in extras]
        assert names == ["weekly_rsi"]
        assert extras[0].z.len() == n

    def test_from_params_defaults_keep_btc_charts(self) -> None:
        w = composite_weights_from_params({"buy_max_rate": 10.0})
        assert w.weekly_rsi == pytest.approx(0.0)
        assert w.weekly_macd == pytest.approx(0.0)
        assert w.sma_band == pytest.approx(0.0)
        assert w.enabled_extras() == {}
