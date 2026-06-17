"""Custom RSI momentum strategy: long when oversold, short when overbought."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators import RelativeStrengthIndex
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from digiquant.strategies.registry import register


class RSIMomentumConfig(StrategyConfig, frozen=True):
    """Configuration for RSIMomentum strategy."""

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    rsi_period: PositiveInt = 14
    oversold: float = 30.0
    overbought: float = 70.0
    request_bars: bool = True


class RSIMomentum(Strategy):
    """
    RSI oversold/overbought strategy.
    Long when RSI < oversold, short when RSI > overbought.
    """

    def __init__(self, config: RSIMomentumConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument | None = None
        self.rsi = RelativeStrengthIndex(config.rsi_period)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.register_indicator_for_bars(self.config.bar_type, self.rsi)
        if self.config.request_bars:
            self.request_bars(
                self.config.bar_type,
                start=self._clock.utc_now() - timedelta(days=1),
            )
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        if not self.indicators_initialized():
            return
        if bar.is_single_price():
            return
        if self.instrument is None:
            return

        rsi_val = self.rsi.value
        if rsi_val is None:
            return

        qty = self.instrument.make_qty(self.config.trade_size)

        if rsi_val < self.config.oversold:
            if self.portfolio.is_flat(self.config.instrument_id):
                order = self.order_factory.market(
                    instrument_id=self.config.instrument_id,
                    order_side=OrderSide.BUY,
                    quantity=qty,
                    time_in_force=TimeInForce.GTC,
                )
                self.submit_order(order)
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                order = self.order_factory.market(
                    instrument_id=self.config.instrument_id,
                    order_side=OrderSide.BUY,
                    quantity=qty,
                    time_in_force=TimeInForce.GTC,
                )
                self.submit_order(order)
        elif rsi_val > self.config.overbought:
            if self.portfolio.is_flat(self.config.instrument_id):
                order = self.order_factory.market(
                    instrument_id=self.config.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=qty,
                    time_in_force=TimeInForce.GTC,
                )
                self.submit_order(order)
            elif self.portfolio.is_net_long(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                order = self.order_factory.market(
                    instrument_id=self.config.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=qty,
                    time_in_force=TimeInForce.GTC,
                )
                self.submit_order(order)

    def on_reset(self) -> None:
        self.rsi.reset()


register(
    "rsi_momentum",
    RSIMomentum,
    RSIMomentumConfig,
    {
        "trade_size": Decimal(1000),
        "rsi_period": 14,
        "oversold": 30.0,
        "overbought": 70.0,
    },
    aliases=["momentum_energy"],
    description="RSI oversold/overbought momentum strategy",
)
