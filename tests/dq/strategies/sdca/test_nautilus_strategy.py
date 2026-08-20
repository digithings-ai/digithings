"""Tests for SdcaStrategyConfig and SdcaStrategy instantiation (#1081)."""

from __future__ import annotations

import datetime as _dt
from datetime import date

import polars as pl
import pytest

try:
    from nautilus_trader.model.data import BarSpecification, BarType
    from nautilus_trader.model.enums import BarAggregation, PriceType
    from nautilus_trader.test_kit.providers import TestInstrumentProvider

    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")


def _write_risk_parquet(tmp_path, n: int = 60, with_null: bool = False) -> tuple[str, int]:
    """Write a synthetic risk-index parquet (date, risk), returning (path, row_count)."""
    dates = [date(2020, 1, 1) + _dt.timedelta(days=i) for i in range(n)]
    risks: list[float | None] = [float(i % 101) for i in range(n)]
    if with_null:
        risks[0] = None
    df = pl.DataFrame({"date": dates, "risk": pl.Series(risks, dtype=pl.Float64)})
    path = tmp_path / "risk.parquet"
    df.write_parquet(path)
    return str(path), n


@pytest.fixture()
def instrument():
    return TestInstrumentProvider.btcusdt_binance()


@pytest.fixture()
def instrument_id(instrument):
    return instrument.id


@pytest.fixture()
def bar_type(instrument_id):
    spec = BarSpecification(1, BarAggregation.DAY, PriceType.LAST)
    return BarType(instrument_id, spec)


class TestSdcaStrategyConfig:
    def test_defaults(self, instrument_id, bar_type, tmp_path) -> None:
        from digiquant.strategies.sdca.curve import DEFAULT_BTC_NODES
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=path,
        )
        assert cfg.curve_nodes == DEFAULT_BTC_NODES
        assert cfg.long_only is False

    def test_custom_curve_nodes_and_long_only(self, instrument_id, bar_type, tmp_path) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path)
        nodes = tuple(5.0 for _ in range(21))
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=50_000.0,
            risk_path=path,
            curve_nodes=nodes,
            long_only=True,
        )
        assert cfg.curve_nodes == nodes
        assert cfg.long_only is True

    def test_rejects_wrong_node_count(self, instrument_id, bar_type, tmp_path) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path)
        with pytest.raises(ValueError, match="21"):
            SdcaStrategyConfig(
                instrument_id=instrument_id,
                bar_type=bar_type,
                initial_cash=100_000.0,
                risk_path=path,
                curve_nodes=(1.0, 2.0, 3.0),
            )


class TestSdcaStrategyInstantiation:
    def test_can_instantiate(self, instrument_id, bar_type, tmp_path) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=path,
        )
        strategy = SdcaStrategy(cfg)
        assert strategy is not None

    def test_risk_index_loaded_matches_row_count(self, instrument_id, bar_type, tmp_path) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        path, n = _write_risk_parquet(tmp_path, n=200)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=path,
        )
        strategy = SdcaStrategy(cfg)
        index = strategy._load_risk_index()
        assert len(index) == n

    def test_risk_index_preserves_null(self, instrument_id, bar_type, tmp_path) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path, n=10, with_null=True)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=path,
        )
        strategy = SdcaStrategy(cfg)
        index = strategy._load_risk_index()
        assert index[date(2020, 1, 1)] is None

    def test_initial_state_matches_config(self, instrument_id, bar_type, tmp_path) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=77_000.0,
            risk_path=path,
        )
        strategy = SdcaStrategy(cfg)
        assert strategy._cash == pytest.approx(77_000.0)
        assert strategy._asset_units == pytest.approx(0.0)
