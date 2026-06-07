"""M2 Liquidity strategy — 5-indicator voting system on global M2 money supply.

The strategy pre-loads a pre-computed signal DataFrame at instantiation time.
On each bar, it looks up the signal for that bar's date and fires entries/exits.

Usage:
    from digiquant.data.m2 import M2DataFetcher
    from digiquant.indicators.m2_signals import M2SignalComputer

    m2_df = M2DataFetcher().fetch(offset_days=86)
    ohlcv_df = ...  # your daily BTC OHLCV Polars DataFrame with 'close' column
    m2_df = m2_df.join(ohlcv_df.select(["date", "close"]), on="date", how="inner")
    signal_df = M2SignalComputer().compute(m2_df)
    signal_df.write_parquet("/tmp/m2_signals.parquet")

    config = M2LiquidityConfig(
        instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
        bar_type=...,
        trade_size=Decimal("1000"),
        signal_path="/tmp/m2_signals.parquet",
    )
    strategy = M2LiquidityStrategy(config)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy


class M2LiquidityConfig(StrategyConfig, frozen=True):
    """Configuration for M2 Liquidity strategy."""

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    # Path to a parquet of the pre-computed signal frame (columns:
    # date, buy_signal, sell_signal). A Polars DataFrame cannot live in a
    # frozen Nautilus StrategyConfig (msgspec struct) — we pass a path and
    # load it in on_start().
    signal_path: str

    # Risk management
    use_sl: bool = True
    sl_pct: float = 10.0

    # Strategy control
    enable_long: bool = True
    enable_short: bool = False  # PineScript default has short disabled


class M2LiquidityStrategy(Strategy):
    """Enters on M2 aggregate signal crossover; exits on reversal or stop loss."""

    def __init__(self, config: M2LiquidityConfig) -> None:
        super().__init__(config)
        self._signal_index: dict[date, tuple[bool, bool]] = {}
        self._long_sl_price: float | None = None
        self._short_sl_price: float | None = None
        self._instrument: Instrument | None = None

    def _load_signal_index(self) -> dict[date, tuple[bool, bool]]:
        """Load the pre-computed signal parquet into a date → (buy, sell) map."""
        df = pl.read_parquet(self.config.signal_path)
        return {
            row["date"]: (bool(row["buy_signal"]), bool(row["sell_signal"]))
            for row in df.select(["date", "buy_signal", "sell_signal"]).to_dicts()
        }

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    def on_start(self) -> None:
        self._instrument = self.cache.instrument(self.config.instrument_id)
        self._signal_index = self._load_signal_index()
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        close = bar.close.as_double()
        bar_date = unix_nanos_to_dt(bar.ts_event).date()

        signals = self._signal_index.get(bar_date)
        if signals is None:
            return  # no M2 data for this date (weekends, M2 gap)

        buy_signal, sell_signal = signals
        pos = self.portfolio.net_position(self.config.instrument_id)

        # ── Stop loss check ──────────────────────────────────────────────────
        if self.config.use_sl:
            if pos > 0 and self._long_sl_price is not None and close <= self._long_sl_price:
                self.close_all_positions(self.config.instrument_id)
                self._long_sl_price = None
                return
            if pos < 0 and self._short_sl_price is not None and close >= self._short_sl_price:
                self.close_all_positions(self.config.instrument_id)
                self._short_sl_price = None
                return

        # ── Entries ──────────────────────────────────────────────────────────
        if buy_signal and self.config.enable_long and pos == 0:
            self._long_sl_price = close * (1 - self.config.sl_pct / 100)
            self._submit_market(OrderSide.BUY)

        if sell_signal:
            if self.config.enable_short and pos == 0:
                self._short_sl_price = close * (1 + self.config.sl_pct / 100)
                self._submit_market(OrderSide.SELL)
            elif pos > 0:
                self.close_all_positions(self.config.instrument_id)
                self._long_sl_price = None

    def _submit_market(self, side: OrderSide) -> None:
        """Submit a fixed-size market order. No explicit client_order_id."""
        assert self._instrument is not None
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            quantity=self._instrument.make_qty(self.config.trade_size),
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)

    def on_reset(self) -> None:
        self._long_sl_price = None
        self._short_sl_price = None


# ─── Registry ────────────────────────────────────────────────────────────────
# Note: signal_df must be injected at runtime — no default registry entry.
# Use the registry for discovery only; instantiate M2LiquidityConfig directly.
