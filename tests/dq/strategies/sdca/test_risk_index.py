"""Tests for the SDCA risk-index builder (#3168)."""

from __future__ import annotations

import datetime as _dt
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from digiquant.strategies.sdca.composite_risk import IndicatorWeight
from digiquant.strategies.sdca.risk_index import (
    build_risk_index,
    write_risk_index,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_z_score

pytestmark = pytest.mark.unit

_DIAGNOSTIC_COLUMNS = {
    "date",
    "risk",
    "price",
    "low",
    "median",
    "high",
    "power_law_z",
    "composite_z",
}


class StaticRiskModel:
    """Minimal RiskModel stub: constant rails, optional null on a given row."""

    def __init__(
        self,
        *,
        low: float = 50.0,
        median: float = 100.0,
        high: float = 200.0,
        null_row: int | None = None,
    ) -> None:
        self.low = low
        self.median = median
        self.high = high
        self.null_row = null_row

    def rails(self, dates: pl.Series) -> pl.DataFrame:
        n = len(dates)
        lows: list[float | None] = [self.low] * n
        medians: list[float | None] = [self.median] * n
        highs: list[float | None] = [self.high] * n
        if self.null_row is not None:
            lows[self.null_row] = None
            medians[self.null_row] = None
            highs[self.null_row] = None
        return pl.DataFrame({"low": lows, "median": medians, "high": highs})


def _dates_and_price(n: int = 5, *, price: float = 100.0) -> tuple[pl.Series, pl.Series]:
    start = date(2020, 1, 1)
    dates = pl.Series("date", [start + _dt.timedelta(days=i) for i in range(n)], dtype=pl.Date)
    prices = pl.Series("price", [price] * n, dtype=pl.Float64)
    return dates, prices


class TestBuildRiskIndex:
    def test_produces_risk_and_diagnostic_columns(self) -> None:
        dates, price = _dates_and_price()
        frame = build_risk_index(dates, price, StaticRiskModel())
        assert set(frame.columns) == _DIAGNOSTIC_COLUMNS
        assert frame.height == dates.len()
        assert frame["date"].dtype == pl.Date
        assert frame["risk"].dtype.is_numeric()

    def test_price_at_median_is_risk_50(self) -> None:
        dates, price = _dates_and_price(n=1, price=100.0)
        frame = build_risk_index(dates, price, StaticRiskModel())
        assert frame["power_law_z"][0] == pytest.approx(0.0)
        assert frame["risk"][0] == pytest.approx(50.0)
        assert frame["composite_z"][0] == pytest.approx(0.0)

    def test_price_at_low_rail_is_risk_0(self) -> None:
        dates, price = _dates_and_price(n=1, price=50.0)
        frame = build_risk_index(dates, price, StaticRiskModel())
        assert frame["power_law_z"][0] == pytest.approx(3.0)
        assert frame["risk"][0] == pytest.approx(0.0)

    def test_matches_power_law_z_then_composite_pipeline(self) -> None:
        dates, price = _dates_and_price(n=3, price=80.0)
        model = StaticRiskModel()
        frame = build_risk_index(dates, price, model)
        rails = model.rails(dates)
        expected_z = power_law_z_score(price, rails["low"], rails["median"], rails["high"])
        assert frame["power_law_z"].to_list() == pytest.approx(expected_z.to_list())

    def test_null_rail_day_survives_as_null_risk_not_zero(self) -> None:
        dates, price = _dates_and_price(n=3)
        frame = build_risk_index(dates, price, StaticRiskModel(null_row=1))
        assert frame["risk"][0] is not None
        assert frame["risk"][1] is None
        assert frame["risk"][2] is not None
        assert frame["composite_z"][1] is None
        assert frame["power_law_z"][1] is None

    def test_extra_indicators_blend_into_composite(self) -> None:
        dates, price = _dates_and_price(n=1, price=100.0)
        extra = [
            IndicatorWeight(name="macro", z=pl.Series([3.0]), weight=1.0),
        ]
        frame = build_risk_index(dates, price, StaticRiskModel(), extra_indicators=extra)
        # power_law z=0 (price at median) + macro z=3, equal weights → composite 1.5
        assert frame["composite_z"][0] == pytest.approx(1.5)

    def test_rejects_length_mismatch(self) -> None:
        dates, price = _dates_and_price(n=3)
        with pytest.raises(ValueError, match="same length"):
            build_risk_index(dates, price.head(1), StaticRiskModel())

    def test_rejects_non_date_dtype(self) -> None:
        dates = pl.Series("date", ["2020-01-01", "2020-01-02"])
        price = pl.Series("price", [100.0, 100.0])
        with pytest.raises(ValueError, match="pl.Date"):
            build_risk_index(dates, price, StaticRiskModel())

    def test_two_thousand_day_series_keeps_every_date(self) -> None:
        dates, price = _dates_and_price(n=2000)
        frame = build_risk_index(dates, price, StaticRiskModel())
        assert frame.height == 2000
        assert frame["date"][0] == dates[0]
        assert frame["date"][-1] == dates[-1]
        assert frame["risk"].null_count() == 0


class TestWriteRiskIndex:
    def test_round_trips_through_sdca_strategy_load(self, tmp_path: Path) -> None:
        pytest.importorskip("nautilus_trader")
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig
        from nautilus_trader.model.data import BarSpecification, BarType
        from nautilus_trader.model.enums import BarAggregation, PriceType
        from nautilus_trader.test_kit.providers import TestInstrumentProvider

        dates, price = _dates_and_price(n=10)
        frame = build_risk_index(dates, price, StaticRiskModel(null_row=2))
        path = write_risk_index(frame, tmp_path / "risk.parquet")

        instrument = TestInstrumentProvider.btcusdt_binance()
        bar_type = BarType(instrument.id, BarSpecification(1, BarAggregation.DAY, PriceType.LAST))
        strategy = SdcaStrategy(
            SdcaStrategyConfig(
                instrument_id=instrument.id,
                bar_type=bar_type,
                initial_cash=100_000.0,
                risk_path=str(path),
            )
        )
        index = strategy._load_risk_index()
        assert len(index) == frame.height
        assert index[date(2020, 1, 3)] is None
        assert index[date(2020, 1, 1)] == pytest.approx(frame["risk"][0])

    def test_null_risk_survives_parquet_round_trip_not_dropped_or_zero(
        self, tmp_path: Path
    ) -> None:
        dates, price = _dates_and_price(n=4)
        frame = build_risk_index(dates, price, StaticRiskModel(null_row=0))
        path = write_risk_index(frame, tmp_path / "risk.parquet")
        loaded = pl.read_parquet(path)
        assert loaded.columns == ["date", "risk"]
        assert loaded["risk"][0] is None
        assert loaded["risk"][1] is not None
        assert loaded["risk"][1] == pytest.approx(frame["risk"][1])

    def test_rejects_duplicate_dates(self, tmp_path: Path) -> None:
        df = pl.DataFrame(
            {
                "date": [date(2020, 1, 1), date(2020, 1, 1)],
                "risk": [10.0, 20.0],
            }
        )
        with pytest.raises(ValueError, match="duplicate"):
            write_risk_index(df, tmp_path / "risk.parquet")

    def test_rejects_non_finite_risk(self, tmp_path: Path) -> None:
        df = pl.DataFrame(
            {
                "date": [date(2020, 1, 1), date(2020, 1, 2)],
                "risk": pl.Series([10.0, float("nan")], dtype=pl.Float64),
            }
        )
        with pytest.raises(ValueError, match="non-finite"):
            write_risk_index(df, tmp_path / "risk.parquet")

    def test_rejects_null_dates(self, tmp_path: Path) -> None:
        df = pl.DataFrame(
            {
                "date": pl.Series([date(2020, 1, 1), None], dtype=pl.Date),
                "risk": [10.0, 20.0],
            }
        )
        with pytest.raises(ValueError, match="null date"):
            write_risk_index(df, tmp_path / "risk.parquet")


class TestBtcPowerLawChain:
    def test_synthetic_fixture_builds_non_empty_index(self) -> None:
        from digiquant.strategies.sdca.btc_power_law import (
            BtcPowerLawRiskModel,
            load_coefficients,
        )

        dates, price = _dates_and_price(n=20, price=10_000.0)
        model = BtcPowerLawRiskModel(load_coefficients())
        frame = build_risk_index(dates, price, model)
        assert frame.height == 20
        assert frame["risk"].null_count() < frame.height
        assert frame["low"].null_count() == 0
        assert (frame["low"] < frame["median"]).all()
        assert (frame["median"] < frame["high"]).all()


class TestNullRiskProducesNoTrade:
    def test_loaded_null_day_skips_on_bar_submit(self, tmp_path: Path) -> None:
        pytest.importorskip("nautilus_trader")
        from unittest.mock import Mock

        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig
        from nautilus_trader.core.datetime import dt_to_unix_nanos
        from nautilus_trader.model.data import Bar, BarSpecification, BarType
        from nautilus_trader.model.enums import BarAggregation, PriceType
        from nautilus_trader.test_kit.providers import TestInstrumentProvider

        dates, price = _dates_and_price(n=3, price=50.0)  # cheap → buy on non-null days
        frame = build_risk_index(dates, price, StaticRiskModel(null_row=1))
        path = write_risk_index(frame, tmp_path / "risk.parquet")

        instrument = TestInstrumentProvider.btcusdt_binance()
        bar_type = BarType(instrument.id, BarSpecification(1, BarAggregation.DAY, PriceType.LAST))
        strategy = SdcaStrategy(
            SdcaStrategyConfig(
                instrument_id=instrument.id,
                bar_type=bar_type,
                initial_cash=100_000.0,
                risk_path=str(path),
            )
        )
        strategy._instrument = instrument
        strategy._risk_index = strategy._load_risk_index()
        strategy._submit_market = Mock()  # type: ignore[method-assign]

        def _bar(day: date) -> Bar:
            ts = dt_to_unix_nanos(_dt.datetime.combine(day, _dt.time.min, tzinfo=_dt.timezone.utc))
            p = instrument.make_price(50.0)
            q = instrument.make_qty(1.0)
            return Bar(bar_type, p, p, p, p, q, ts, ts)

        strategy.on_bar(_bar(date(2020, 1, 2)))  # null-risk day
        strategy._submit_market.assert_not_called()

        strategy.on_bar(_bar(date(2020, 1, 1)))  # cheap, risk 0 → buy
        strategy._submit_market.assert_called()
