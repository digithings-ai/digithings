"""Tests for SlapperConfig and SlapperStrategy instantiation.

Full backtest integration is covered by make test-unit once Nautilus is
installed. These tests verify config correctness and indicator wiring
without spinning up the backtest engine.
"""

from __future__ import annotations

import pytest

try:
    from nautilus_trader.model.identifiers import InstrumentId
    from nautilus_trader.model.data import BarType, BarSpecification
    from nautilus_trader.model.enums import BarAggregation, PriceType

    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")


@pytest.fixture()
def btc_instrument_id() -> "InstrumentId":
    return InstrumentId.from_str("BTCUSDT.BINANCE")


@pytest.fixture()
def bar_type(btc_instrument_id: "InstrumentId") -> "BarType":
    spec = BarSpecification(1, BarAggregation.DAY, PriceType.LAST)
    return BarType(btc_instrument_id, spec)


class TestSlapperConfig:
    def test_btc_defaults(self, btc_instrument_id, bar_type) -> None:
        from decimal import Decimal
        from digiquant.strategies.slapper import SlapperConfig

        cfg = SlapperConfig(
            instrument_id=btc_instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
        )
        assert cfg.rsi_length == 14
        assert cfg.adf_lookback == 44
        assert cfg.adf_upper_entry == pytest.approx(-1.25)
        assert cfg.dpsd_dema_length == 4
        assert cfg.dpsd_dema_src == "hlcc4"
        assert cfg.use_reversal_stop is False

    def test_all_fields_are_frozen(self, btc_instrument_id, bar_type) -> None:
        from decimal import Decimal
        from digiquant.strategies.slapper import SlapperConfig

        cfg = SlapperConfig(
            instrument_id=btc_instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
        )
        with pytest.raises(Exception):  # frozen Pydantic raises ValidationError or TypeError
            cfg.rsi_length = 99  # type: ignore[misc]


class TestSlapperStrategyInstantiation:
    def test_can_instantiate(self, btc_instrument_id, bar_type) -> None:
        from decimal import Decimal
        from digiquant.strategies.slapper import SlapperConfig, SlapperStrategy

        cfg = SlapperConfig(
            instrument_id=btc_instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
        )
        strategy = SlapperStrategy(cfg)
        assert strategy is not None

    def test_indicator_instances_created(self, btc_instrument_id, bar_type) -> None:
        from decimal import Decimal
        from digiquant.strategies.slapper import SlapperConfig, SlapperStrategy
        from digiquant.indicators import RSI, RollingADF, BollingerBands, DPSDTrend

        cfg = SlapperConfig(
            instrument_id=btc_instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
        )
        strategy = SlapperStrategy(cfg)
        assert isinstance(strategy._rsi, RSI)
        assert isinstance(strategy._adf, RollingADF)
        assert isinstance(strategy._bb, BollingerBands)
        assert isinstance(strategy._dpsd, DPSDTrend)
