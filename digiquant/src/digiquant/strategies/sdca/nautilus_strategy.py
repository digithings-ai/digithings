"""NautilusTrader wrapper for the SDCA engine (#1081).

Follows the same precompute-then-drive pattern as ``m2_liquidity.py``: the
composite-risk index (produced upstream via ``compute_composite_risk()`` and
``valuation_z_score()``) is written to a parquet of ``date``/``risk`` columns
and passed in by path, since neither a Polars DataFrame nor a ``RiskModel``
can live in a frozen Nautilus ``StrategyConfig`` (msgspec struct). On each
bar, the strategy looks up that day's risk, converts it to a trade rate via
``AccumDistCurve.value_at_risk()``, and sizes the trade via
``sdca/backtest.py::size_trade`` so the two never diverge into separate
sources of truth for the allocation decision. Shadow ``_cash``/
``_asset_units`` are updated from real ``OrderFilled`` events, not the
pre-submission estimate, so they track Nautilus's actual (quantized)
execution state. ``on_bar()`` skips sizing a new order while a prior one is
still open (terminal-state guard, see ``_order_pending``), so two bars can
never size off the same unreserved capacity.

Usage:
    import polars as pl
    from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategyConfig, SdcaStrategy

    pl.DataFrame({"date": dates, "risk": risk}).write_parquet("/tmp/sdca_risk.parquet")

    config = SdcaStrategyConfig(
        instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
        bar_type=...,
        initial_cash=100_000.0,
        risk_path="/tmp/sdca_risk.parquet",
    )
    strategy = SdcaStrategy(config)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl
from nautilus_trader.config import PositiveFloat, StrategyConfig
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import (
    OrderCanceled,
    OrderDenied,
    OrderExpired,
    OrderFilled,
    OrderRejected,
)
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from digiquant.strategies.registry import register
from digiquant.strategies.sdca.backtest import size_trade
from digiquant.strategies.sdca.curve import DEFAULT_BTC_NODES, RISK_NODES, AccumDistCurve


class SdcaStrategyConfig(StrategyConfig, frozen=True):
    """Configuration for the SDCA strategy."""

    instrument_id: InstrumentId
    bar_type: BarType
    initial_cash: PositiveFloat
    # Path to a parquet of the pre-computed risk-index frame (columns:
    # date, risk). A Polars DataFrame and a RiskModel cannot live in a
    # frozen Nautilus StrategyConfig (msgspec struct) — we pass a path and
    # load it in on_start().
    risk_path: str

    # 21-node (risk 0, 5, ..., 100) piecewise-linear accumulation/distribution
    # curve. All-positive = long-only accumulation; signed = accumulation +
    # distribution. See sdca/curve.py.
    curve_nodes: tuple[float, ...] = DEFAULT_BTC_NODES

    # Safety override: clamp the curve's rate to >= 0 so the strategy never
    # sells, regardless of curve_nodes' own sign.
    long_only: bool = False

    def __post_init__(self) -> None:
        if len(self.curve_nodes) != len(RISK_NODES):
            raise ValueError(
                f"curve_nodes must have {len(RISK_NODES)} nodes, got {len(self.curve_nodes)}"
            )


class SdcaStrategy(Strategy):
    """Drives the SDCA curve/composite-risk allocation decision bar-by-bar.

    Reuses ``AccumDistCurve.value_at_risk()`` and ``sdca/backtest.py::size_trade``
    directly so the standalone parity harness and this live/backtest strategy
    never diverge.
    """

    def __init__(self, config: SdcaStrategyConfig) -> None:
        super().__init__(config)
        self._curve = AccumDistCurve(config.curve_nodes)
        self._risk_index: dict[date, float | None] = {}
        self._cash: float = config.initial_cash
        self._asset_units: float = 0.0
        self._instrument: Instrument | None = None
        # Guards on_bar() against sizing a new order off unreserved capacity
        # while a prior order is still open — see _submit_market()/on_order_filled().
        self._order_pending: bool = False
        self._pending_qty: float = 0.0

    def _load_risk_index(self) -> dict[date, float | None]:
        """Load the pre-computed risk parquet into a date -> risk map."""
        df = pl.read_parquet(self.config.risk_path)
        missing = {"date", "risk"} - set(df.columns)
        if missing:
            raise ValueError(f"risk_path parquet is missing required columns: {sorted(missing)}")
        date_dtype = df.schema["date"]
        if date_dtype != pl.Date:
            # iter_rows() yields datetime.datetime for pl.Datetime, which never
            # equals the datetime.date keys on_bar() looks up with — cast rather
            # than silently dropping every matching day's trade decision.
            if isinstance(date_dtype, pl.Datetime):
                df = df.with_columns(pl.col("date").cast(pl.Date))
            else:
                raise ValueError(
                    f"risk_path parquet 'date' column must be pl.Date, got {date_dtype}"
                )
        risk_dtype = df.schema["risk"]
        if not risk_dtype.is_numeric():
            # A string/object risk column loads without error and reaches
            # AccumDistCurve.value_at_risk() as a str, which raises TypeError deep
            # in the curve math on the first matching bar — fail fast here instead.
            raise ValueError(f"risk_path parquet 'risk' column must be numeric, got {risk_dtype}")
        if df["date"].null_count() > 0:
            # A null date becomes a None dict key, which on_bar()'s datetime.date
            # lookups can never match — a silently dead row rather than an error.
            raise ValueError("risk_path parquet has null date value(s)")
        non_finite = df.filter(pl.col("risk").is_not_null() & ~pl.col("risk").is_finite())
        if non_finite.height > 0:
            # NaN/±inf pass is_numeric() but reach AccumDistCurve.value_at_risk()
            # as a non-finite float; null risk is kept as an explicit no-data day.
            bad_dates = non_finite["date"].to_list()
            raise ValueError(f"risk_path parquet has non-finite risk value(s) on: {bad_dates}")
        dupes = df.filter(df["date"].is_duplicated())["date"].unique().sort().to_list()
        if dupes:
            raise ValueError(f"risk_path parquet has duplicate date(s): {dupes}")
        return dict(df.select(["date", "risk"]).iter_rows())

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    def on_start(self) -> None:
        self._instrument = self.cache.instrument(self.config.instrument_id)
        if self._instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self._risk_index = self._load_risk_index()
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        if self._order_pending:
            # A prior order hasn't reached a terminal state yet — sizing off
            # _cash/_asset_units now would double-spend capacity already
            # committed to that order.
            return

        bar_date = unix_nanos_to_dt(bar.ts_event).date()
        risk = self._risk_index.get(bar_date)
        if risk is None:
            return  # no risk data for this date, or an explicit no-data day

        rate = self._curve.value_at_risk(risk)
        if self.config.long_only:
            rate = max(rate, 0.0)

        close = bar.close.as_double()
        # Remaining cash / remaining holdings from the fill-synced shadow book.
        buy_usd, sell_units = size_trade(rate, self._cash, self._asset_units)

        if rate > 0:
            if buy_usd <= 0:
                return
            self._submit_market(OrderSide.BUY, buy_usd / close)
        elif rate < 0:
            if sell_units <= 0:
                return
            self._submit_market(OrderSide.SELL, sell_units)

    def _submit_market(self, side: OrderSide, quantity: float) -> None:
        """Submit a market order sized from the sdca allocation loop.

        Remaining-book compounding can size below the instrument increment
        (balanced ``buy_max_rate`` drains cash toward dust). ``make_qty``
        raises if the value rounds to zero — skip those bars instead.
        """
        assert self._instrument is not None
        if quantity <= 0:
            return
        increment = self._instrument.size_increment.as_double()
        if increment > 0 and quantity < increment:
            return
        qty = self._instrument.make_qty(Decimal(str(quantity)))
        if qty.as_double() <= 0:
            return
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            quantity=qty,
            time_in_force=TimeInForce.GTC,
        )
        self._order_pending = True
        self._pending_qty = qty.as_double()
        self.submit_order(order)

    def on_order_filled(self, event: OrderFilled) -> None:
        """Sync shadow cash/asset_units from a real fill (post-quantization).

        ``on_bar()`` deliberately does not update ``_cash``/``_asset_units``
        itself — ``_submit_market()`` quantizes the requested quantity to the
        instrument's ``size_precision`` before submission, so the pre-submit
        estimate can diverge from what actually fills. Using ``last_qty``/
        ``last_px`` (not cumulative) keeps this correct across partial fills.

        Also decrements ``_pending_qty`` by this fill and clears
        ``_order_pending`` once the whole requested quantity has filled —
        tracked from our own submitted quantity rather than querying order
        state, since ``OrderFilled`` carries no ``leaves_qty``.
        """
        filled_units = event.last_qty.as_double()
        filled_price = event.last_px.as_double()
        if event.is_buy:
            self._cash -= filled_units * filled_price
            self._asset_units += filled_units
        else:
            self._cash += filled_units * filled_price
            self._asset_units -= filled_units

        # Commission is a real cash outflow on either side. Only subtract it
        # when denominated in the instrument's quote currency (the currency
        # _cash tracks) — a fee paid in a different currency (e.g. the base
        # asset, or a separate fee token) can't be folded into a
        # single-currency cash figure without a conversion rate this
        # shadow-accounting strategy doesn't have.
        if (
            self._instrument is not None
            and event.commission.currency == self._instrument.quote_currency
        ):
            self._cash -= event.commission.as_double()

        self._pending_qty -= filled_units
        if self._pending_qty <= 1e-9:
            self._order_pending = False

    def on_order_canceled(self, event: OrderCanceled) -> None:
        self._order_pending = False
        self._pending_qty = 0.0

    def on_order_rejected(self, event: OrderRejected) -> None:
        self._order_pending = False
        self._pending_qty = 0.0

    def on_order_expired(self, event: OrderExpired) -> None:
        self._order_pending = False
        self._pending_qty = 0.0

    def on_order_denied(self, event: OrderDenied) -> None:
        self._order_pending = False
        self._pending_qty = 0.0

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)

    def on_reset(self) -> None:
        self._cash = self.config.initial_cash
        self._asset_units = 0.0
        self._order_pending = False
        self._pending_qty = 0.0


# ─── Registry (#3170) ────────────────────────────────────────────────────────
# risk_path has no static default (it is materialized per run from the
# signal-delayed OHLCV frame). default_params omit it; generate_tearsheets
# injects the path via get_strategy(..., **overrides).

register(
    "btc_sdca",
    SdcaStrategy,
    SdcaStrategyConfig,
    {
        "initial_cash": 1000.0,
        "long_only": True,
        "curve_nodes": DEFAULT_BTC_NODES,
    },
    aliases=["sdca"],
    description="BTC Strategic DCA: composite risk → accumulation/distribution curve",
)


__all__ = ["SdcaStrategyConfig", "SdcaStrategy"]
