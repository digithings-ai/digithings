"""NautilusTrader wrapper for the SDCA engine (#1081).

Follows the same precompute-then-drive pattern as ``m2_liquidity.py``: the
composite-risk index (produced upstream via ``compute_composite_risk()`` and
``valuation_z_score()``) is written to a parquet of ``date``/``risk`` columns
and passed in by path, since neither a Polars DataFrame nor a ``RiskModel``
can live in a frozen Nautilus ``StrategyConfig`` (msgspec struct). On each
bar, the strategy looks up that day's risk, converts it to a trade rate via
``AccumDistCurve.value_at_risk()``, and applies the exact buy/sell sizing
loop from ``sdca/backtest.py::run_backtest`` so the two never diverge into
separate sources of truth for the allocation decision.

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
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

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

    Reuses ``AccumDistCurve.value_at_risk()`` directly and mirrors the exact
    buy/sell sizing loop in ``sdca/backtest.py::run_backtest`` so the
    standalone parity harness and this live/backtest strategy never diverge.
    """

    def __init__(self, config: SdcaStrategyConfig) -> None:
        super().__init__(config)
        self._curve = AccumDistCurve(config.curve_nodes)
        self._risk_index: dict[date, float | None] = {}
        self._cash: float = config.initial_cash
        self._asset_units: float = 0.0
        self._instrument: Instrument | None = None

    def _load_risk_index(self) -> dict[date, float | None]:
        """Load the pre-computed risk parquet into a date -> risk map."""
        df = pl.read_parquet(self.config.risk_path)
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
        bar_date = unix_nanos_to_dt(bar.ts_event).date()
        risk = self._risk_index.get(bar_date)
        if risk is None:
            return  # no risk data for this date, or an explicit no-data day

        rate = self._curve.value_at_risk(risk)
        if self.config.long_only:
            rate = max(rate, 0.0)

        close = bar.close.as_double()

        if rate > 0:
            buy_usd = min(max(self._cash * rate / 100.0, 0.0), self._cash)
            if buy_usd <= 0:
                return
            self._cash -= buy_usd
            self._asset_units += buy_usd / close
            self._submit_market(OrderSide.BUY, buy_usd / close)
        elif rate < 0:
            sell_units = min(max(self._asset_units * (-rate) / 100.0, 0.0), self._asset_units)
            if sell_units <= 0:
                return
            self._cash += sell_units * close
            self._asset_units -= sell_units
            self._submit_market(OrderSide.SELL, sell_units)

    def _submit_market(self, side: OrderSide, quantity: float) -> None:
        """Submit a market order sized from the sdca allocation loop."""
        assert self._instrument is not None
        qty = self._instrument.make_qty(Decimal(str(quantity)))
        if qty.as_double() <= 0:
            return
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            quantity=qty,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)

    def on_reset(self) -> None:
        self._cash = self.config.initial_cash
        self._asset_units = 0.0


# ─── Registry ────────────────────────────────────────────────────────────────
# Note: risk_path must be injected at runtime (computed upstream from a live
# RiskModel + indicators) — no default registry entry, same as m2_liquidity.
# Use the registry for discovery only; instantiate SdcaStrategyConfig directly.


__all__ = ["SdcaStrategyConfig", "SdcaStrategy"]
