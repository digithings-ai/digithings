"""Tests for M2LiquidityConfig and M2LiquidityStrategy instantiation."""

from __future__ import annotations

import pytest
from datetime import date
import polars as pl
import numpy as np

try:
    from nautilus_trader.model.identifiers import InstrumentId
    from nautilus_trader.model.data import BarType, BarSpecification
    from nautilus_trader.model.enums import BarAggregation, PriceType

    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")


def _write_signal_parquet(tmp_path, n: int = 400) -> tuple[str, int]:
    """Write a synthetic signal parquet, returning (path, row_count)."""
    import datetime as _dt

    rng = np.random.default_rng(0)
    dates = [date(2020, 1, 1) + _dt.timedelta(days=i) for i in range(n)]
    avg = pl.Series("avg_score", rng.uniform(0, 1, n))
    buy = (avg.shift(1) < 0.5) & (avg >= 0.5)
    sell = (avg.shift(1) > 0.5) & (avg <= 0.5)
    df = pl.DataFrame(
        {
            "date": dates,
            "avg_score": avg,
            "buy_signal": buy.fill_null(False),
            "sell_signal": sell.fill_null(False),
        }
    )
    path = tmp_path / "signals.parquet"
    df.write_parquet(path)
    return str(path), n


@pytest.fixture()
def instrument_id():
    return InstrumentId.from_str("BTCUSDT.BINANCE")


@pytest.fixture()
def bar_type(instrument_id):
    spec = BarSpecification(1, BarAggregation.DAY, PriceType.LAST)
    return BarType(instrument_id, spec)


class TestM2LiquidityConfig:
    def test_defaults(self, instrument_id, bar_type, tmp_path) -> None:
        from decimal import Decimal
        from digiquant.strategies.m2_liquidity import M2LiquidityConfig

        path, _ = _write_signal_parquet(tmp_path)
        cfg = M2LiquidityConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
            signal_path=path,
        )
        assert cfg.use_sl is True
        assert cfg.sl_pct == pytest.approx(10.0)
        assert cfg.enable_long is True
        assert cfg.enable_short is False


class TestM2LiquidityStrategyInstantiation:
    def test_can_instantiate(self, instrument_id, bar_type, tmp_path) -> None:
        from decimal import Decimal
        from digiquant.strategies.m2_liquidity import M2LiquidityConfig, M2LiquidityStrategy

        path, _ = _write_signal_parquet(tmp_path)
        cfg = M2LiquidityConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
            signal_path=path,
        )
        strategy = M2LiquidityStrategy(cfg)
        assert strategy is not None

    def test_signal_index_loaded_on_start(self, instrument_id, bar_type, tmp_path) -> None:
        from decimal import Decimal
        from digiquant.strategies.m2_liquidity import M2LiquidityConfig, M2LiquidityStrategy

        path, n = _write_signal_parquet(tmp_path, 200)
        cfg = M2LiquidityConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
            signal_path=path,
        )
        strategy = M2LiquidityStrategy(cfg)
        # Index is loaded in on_start(); call the loader directly to verify mapping.
        index = strategy._load_signal_index()
        assert len(index) == n
