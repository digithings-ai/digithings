"""Custom MACD trend-following strategy using Nautilus MovingAverageConvergenceDivergence."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.indicators import MovingAverageConvergenceDivergence
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from digiquant.strategies.registry import register


class MACDTrendConfig(StrategyConfig, frozen=True):
    """Configuration for MACDTrend strategy."""

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    fast_period: PositiveInt = 12
    slow_period: PositiveInt = 26
    signal_period: PositiveInt = 9
    request_bars: bool = True


class MACDTrend(Strategy):
    """
    MACD trend-following using Nautilus MovingAverageConvergenceDivergence.
    Long when MACD line crosses above signal line, short when below.
    Note: Nautilus MACD(fast, slow) only; signal line is EMA of MACD values (computed manually).
    """

    def __init__(self, config: MACDTrendConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument | None = None
        # Nautilus MACD takes (fast, slow) only - 3rd param would be ma_type, not signal_period
        self.macd = MovingAverageConvergenceDivergence(config.fast_period, config.slow_period)
        self.signal_ema = ExponentialMovingAverage(config.signal_period)
        self._prev_macd: float | None = None
        self._prev_signal: float | None = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.register_indicator_for_bars(self.config.bar_type, self.macd)
        if self.config.request_bars:
            self.request_bars(
                self.config.bar_type,
                start=self._clock.utc_now() - timedelta(days=1),
            )
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        if not self.macd.initialized:
            return
        if bar.is_single_price():
            return
        if self.instrument is None:
            return

        macd_val = self.macd.value
        if macd_val is None:
            return

        self.signal_ema.update_raw(macd_val)
        signal_val = self.signal_ema.value
        if signal_val is None:
            self._prev_macd = macd_val
            return

        prev_macd = self._prev_macd
        prev_signal = self._prev_signal
        self._prev_macd = macd_val
        self._prev_signal = signal_val

        if prev_macd is None or prev_signal is None:
            return

        qty = self.instrument.make_qty(self.config.trade_size)

        if prev_macd <= prev_signal and macd_val > signal_val:
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
        elif prev_macd >= prev_signal and macd_val < signal_val:
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
        self.macd.reset()
        self.signal_ema.reset()
        self._prev_macd = None
        self._prev_signal = None


register(
    "macd_trend",
    MACDTrend,
    MACDTrendConfig,
    {
        "trade_size": Decimal(1000),
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9,
    },
    description="MACD trend-following strategy",
)
