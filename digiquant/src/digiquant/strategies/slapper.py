"""Slapper strategy — ADF + RSI + Bollinger Bands mean reversion combined with DPSD trend.

Converted from BTC/ETH/SOL Slapper PineScript (v6). One class covers all three
coins; parameter differences are captured in the registry configs.

Signal logic:
  mr_long  = (adf_crossover OR rsi_crossover) AND rsi_over_under AND close < bb_lower
  mr_short = (adf_crossunder OR rsi_crossunder) AND close > bb_upper
  buy      = mr_long OR dpsd_crossed_up
  sell     = mr_short OR dpsd_crossed_down

Reversal stop (BTC only, use_reversal_stop=True):
  If MR-only entry AND DPSD trend opposes AND drawdown > threshold → close and reverse.
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from digiquant.indicators import BollingerBands, DPSDTrend, RollingADF, RSI, make_ma
from digiquant.indicators.ma import VWMA


class SlapperConfig(StrategyConfig, frozen=True):
    """All parameters for the Slapper strategy family."""

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    # When set (e.g. 100.0), size each entry as this percent of account equity,
    # replicating Pine's percent_of_equity compounding. None → fixed trade_size.
    size_pct_equity: float | None = None

    # ── RSI ──────────────────────────────────────────────────────────────────
    rsi_length: PositiveInt = 14
    rsi_use_ma: bool = True
    rsi_ma_length: PositiveInt = 14
    rsi_ma_type: str = "EMA"  # SMA/EMA/RMA/WMA/HMA/VWMA
    rsi_upper_band: float = 44.0
    rsi_lower_band: float = 37.0

    # ── ADF ──────────────────────────────────────────────────────────────────
    adf_lookback: int = 44
    adf_nlag: int = 0
    adf_use_ma: bool = True
    adf_ma_length: PositiveInt = 45
    adf_ma_type: str = "EMA"
    adf_upper_entry: float = -1.25
    adf_use_lower_entry: bool = True
    adf_lower_entry: float = -1.65

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb_length: PositiveInt = 37
    bb_ma_type: str = "EMA"
    bb_mult: float = 0.3

    # ── DPSD ─────────────────────────────────────────────────────────────────
    dpsd_dema_length: PositiveInt = 4
    dpsd_dema_src: str = "hlcc4"  # "hl2" or "hlcc4"
    dpsd_percentile_length: PositiveInt = 69
    dpsd_percentile_type: str = "55/45"
    dpsd_sd_length: PositiveInt = 25
    dpsd_ema_length: PositiveInt = 41
    dpsd_include_ema: bool = True

    # ── Reversal stop (BTC only) ──────────────────────────────────────────────
    use_reversal_stop: bool = False
    stop_drawdown_threshold: float = 20.0

    # ── Strategy control ─────────────────────────────────────────────────────
    enable_long: bool = True
    enable_short: bool = True


class SlapperStrategy(Strategy):
    """ADF + RSI + BB mean reversion combined with DPSD trend-following."""

    def __init__(self, config: SlapperConfig) -> None:
        super().__init__(config)

        self._rsi = RSI(config.rsi_length)
        # RSI MA: VWMA needs special handling (requires volume); others via make_ma
        if config.rsi_ma_type == "VWMA":
            self._rsi_ma: VWMA | object = VWMA(config.rsi_ma_length)
            self._rsi_ma_is_vwma = True
        else:
            self._rsi_ma = make_ma(config.rsi_ma_type, config.rsi_ma_length)
            self._rsi_ma_is_vwma = False

        self._adf = RollingADF(
            lookback=config.adf_lookback,
            nlag=config.adf_nlag,
            use_ma=config.adf_use_ma,
            ma_type=config.adf_ma_type,
            ma_length=config.adf_ma_length,
        )

        self._bb = BollingerBands(
            length=config.bb_length,
            mult=config.bb_mult,
            ma_type=config.bb_ma_type,
        )

        self._dpsd = DPSDTrend(
            dema_length=config.dpsd_dema_length,
            percentile_length=config.dpsd_percentile_length,
            percentile_type=config.dpsd_percentile_type,
            sd_length=config.dpsd_sd_length,
            ema_length=config.dpsd_ema_length,
            include_ema=config.dpsd_include_ema,
        )

        # Previous values for crossover detection
        self._prev_selected_rsi: float | None = None

        # Reversal stop state
        self._is_mr_only_entry: bool = False
        self._signal_close_price: float | None = None

        self._instrument: Instrument | None = None

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    def on_start(self) -> None:
        self._instrument = self.cache.instrument(self.config.instrument_id)
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        close = bar.close.as_double()
        high = bar.high.as_double()
        low = bar.low.as_double()
        volume = bar.volume.as_double()

        # ── Source for DPSD ──────────────────────────────────────────────────
        dpsd_src = (
            (high + low) / 2.0
            if self.config.dpsd_dema_src == "hl2"
            else (high + low + close * 2.0) / 4.0
        )

        # ── Update indicators ────────────────────────────────────────────────
        self._rsi.update(close)
        self._adf.update(close)
        self._bb.update(close)
        self._dpsd.update(src=dpsd_src, close=close)

        if not (self._rsi.initialized and self._adf.initialized and self._bb.initialized):
            return

        # ── RSI MA ───────────────────────────────────────────────────────────
        if self.config.rsi_use_ma:
            if self._rsi_ma_is_vwma:
                self._rsi_ma.update(price=self._rsi.value, volume=volume)  # type: ignore[union-attr]
            else:
                self._rsi_ma.update(self._rsi.value)  # type: ignore[union-attr]
            selected_rsi = self._rsi_ma.value if self._rsi_ma.initialized else None
        else:
            selected_rsi = self._rsi.value

        if selected_rsi is None:
            return

        # ── RSI crossover signals ────────────────────────────────────────────
        upper_b = self.config.rsi_upper_band
        lower_b = self.config.rsi_lower_band
        prev = self._prev_selected_rsi
        rsi_long = prev is not None and prev < upper_b and selected_rsi >= upper_b
        rsi_short = prev is not None and prev > upper_b and selected_rsi <= upper_b
        rsi_over_under = selected_rsi > upper_b or selected_rsi < lower_b
        self._prev_selected_rsi = selected_rsi

        # ── ADF crossover signals ────────────────────────────────────────────
        adf_long = self._adf.crossover(self.config.adf_upper_entry) or (
            self.config.adf_use_lower_entry and self._adf.crossover(self.config.adf_lower_entry)
        )
        adf_short = self._adf.crossunder(self.config.adf_upper_entry) or (
            self.config.adf_use_lower_entry and self._adf.crossunder(self.config.adf_lower_entry)
        )

        # ── BB ───────────────────────────────────────────────────────────────
        bb_long = close < self._bb.lower  # type: ignore[operator]
        bb_short = close > self._bb.upper  # type: ignore[operator]

        # ── Combined signals ──────────────────────────────────────────────────
        mr_long = (adf_long or rsi_long) and rsi_over_under and bb_long
        mr_short = (adf_short or rsi_short) and bb_short
        trend_long = self._dpsd.crossed_up() if self._dpsd.initialized else False
        trend_short = self._dpsd.crossed_down() if self._dpsd.initialized else False

        buy_signal = mr_long or trend_long
        sell_signal = mr_short or trend_short

        # ── Reversal stop (BTC Slapper only) ─────────────────────────────────
        if self.config.use_reversal_stop:
            self._check_reversal_stop(close)

        # ── Entries — close-then-open reversal, pyramiding=0 (Pine parity) ────
        # See rsi_momentum.py:73-108 for the established pattern.
        if buy_signal and self.config.enable_long:
            if self.portfolio.is_flat(self.config.instrument_id):
                self._enter(OrderSide.BUY, close)
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self._enter(OrderSide.BUY, close)
            # else already long → ignored (pyramiding=0)
            if self.config.use_reversal_stop and not self.portfolio.is_flat(
                self.config.instrument_id
            ):
                self._is_mr_only_entry = mr_long and not trend_long
                self._signal_close_price = close

        elif sell_signal and self.config.enable_short:
            if self.portfolio.is_flat(self.config.instrument_id):
                self._enter(OrderSide.SELL, close)
            elif self.portfolio.is_net_long(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self._enter(OrderSide.SELL, close)
            # else already short → ignored (pyramiding=0)
            if self.config.use_reversal_stop and not self.portfolio.is_flat(
                self.config.instrument_id
            ):
                self._is_mr_only_entry = mr_short and not trend_short
                self._signal_close_price = close

        # Reset mr_only flag when flat
        if self.portfolio.is_flat(self.config.instrument_id) and self.config.use_reversal_stop:
            self._is_mr_only_entry = False
            self._signal_close_price = None

    def _entry_qty(self, close: float):
        """Compute order quantity. Fixed trade_size unless size_pct_equity is set.

        When size_pct_equity is set, derive notional from account equity to
        replicate Pine's percent_of_equity sizing (compounding).
        VERIFY the equity-read API against the installed Nautilus version before
        trusting this branch — see the Pine-Parity Semantics note at the top.
        """
        assert self._instrument is not None
        if self.config.size_pct_equity is None:
            return self._instrument.make_qty(self.config.trade_size)
        venue = self.config.instrument_id.venue
        account = self.portfolio.account(venue)
        currency = self._instrument.quote_currency
        equity = account.balance_total(currency).as_double()
        notional = equity * (self.config.size_pct_equity / 100.0)
        qty_raw = notional / close
        return self._instrument.make_qty(qty_raw)

    def _enter(self, side: OrderSide, close: float) -> None:
        """Submit a market entry sized per config. No explicit client_order_id."""
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            quantity=self._entry_qty(close),
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

    def _check_reversal_stop(self, close: float) -> None:
        """Reverse position when MR-only entry exceeds drawdown threshold.

        Pine closes the losing MR position and immediately enters the opposite
        side (a reversal). We replicate: close, then open the opposite side.
        """
        if not self._is_mr_only_entry or self._signal_close_price is None:
            return
        threshold = self.config.stop_drawdown_threshold
        trend = self._dpsd.trend if self._dpsd.initialized else 0.0

        if self.portfolio.is_net_long(self.config.instrument_id) and trend == -1.0:
            dd_pct = (self._signal_close_price - close) / self._signal_close_price * 100
            if dd_pct > threshold and self.config.enable_short:
                self.close_all_positions(self.config.instrument_id)
                self._enter(OrderSide.SELL, close)
                self._is_mr_only_entry = False  # reversal aligns with trend

        elif self.portfolio.is_net_short(self.config.instrument_id) and trend == 1.0:
            dd_pct = (close - self._signal_close_price) / self._signal_close_price * 100
            if dd_pct > threshold and self.config.enable_long:
                self.close_all_positions(self.config.instrument_id)
                self._enter(OrderSide.BUY, close)
                self._is_mr_only_entry = False

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)

    def on_reset(self) -> None:
        cfg = self.config
        self._rsi = RSI(cfg.rsi_length)
        if cfg.rsi_ma_type == "VWMA":
            self._rsi_ma = VWMA(cfg.rsi_ma_length)
        else:
            self._rsi_ma = make_ma(cfg.rsi_ma_type, cfg.rsi_ma_length)
        self._adf = RollingADF(
            lookback=cfg.adf_lookback,
            nlag=cfg.adf_nlag,
            use_ma=cfg.adf_use_ma,
            ma_type=cfg.adf_ma_type,
            ma_length=cfg.adf_ma_length,
        )
        self._bb = BollingerBands(length=cfg.bb_length, mult=cfg.bb_mult, ma_type=cfg.bb_ma_type)
        self._dpsd = DPSDTrend(
            dema_length=cfg.dpsd_dema_length,
            percentile_length=cfg.dpsd_percentile_length,
            percentile_type=cfg.dpsd_percentile_type,
            sd_length=cfg.dpsd_sd_length,
            ema_length=cfg.dpsd_ema_length,
            include_ema=cfg.dpsd_include_ema,
        )
        self._prev_selected_rsi = None
        self._is_mr_only_entry = False
        self._signal_close_price = None
