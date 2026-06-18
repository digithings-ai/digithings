"""Custom Bollinger Bands mean reversion strategy."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from nautilus_trader.config import PositiveFloat
from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators import BollingerBands
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from digiquant.strategies.registry import register


class BollingerMRConfig(StrategyConfig, frozen=True):
    """Configuration for BollingerMR mean reversion strategy."""

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    period: PositiveInt = 20
    std_dev: PositiveFloat = 2.0
    request_bars: bool = True


class BollingerMR(Strategy):
    """
    Bollinger Bands mean reversion.
    Long when price touches lower band, short when price touches upper band.
    """

    def __init__(self, config: BollingerMRConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument | None = None
        self.bb = BollingerBands(config.period, config.std_dev)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.register_indicator_for_bars(self.config.bar_type, self.bb)
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

        close = bar.close.as_double()
        lower = self.bb.lower
        upper = self.bb.upper
        if lower is None or upper is None:
            return

        qty = self.instrument.make_qty(self.config.trade_size)

        if close <= lower:
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
        elif close >= upper:
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
        self.bb.reset()


register(
    "bollinger_mr",
    BollingerMR,
    BollingerMRConfig,
    {
        "trade_size": Decimal(1000),
        "period": 20,
        "std_dev": 2.0,
    },
    aliases=["mean_reversion_stat_arb"],
    description="Bollinger Bands mean reversion strategy",
)
