"""NautilusTrader long-only relative-strength rotator (#1084 Phase 1).

Precompute → drive pattern (same as ``m2_liquidity`` / SDCA):

1. ``RsRanker.rank`` + ``build_allocation_frame`` write a parquet of
   ``date, symbol, weight`` (empty date ⇒ cash on that rebalance).
2. This strategy loads that path in ``on_start`` and rebalances on the
   clock bar every ``rebalance_every`` calendar days (default 7), holding
   the prior target between scheduled rebalances.

Optional macro regime gating belongs in the *allocation* parquet (set all
weights to cash when ``risk_on`` is false) — see ``build_allocation_frame``.
No live-trading / broker path.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, PriceType, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from digiquant.strategies.registry import register


class RsRotationConfig(StrategyConfig, frozen=True):
    """Configuration for the Phase-1 RS rotation strategy."""

    # Clock instrument drives rebalance checks; other sleeves are still subscribed.
    instrument_id: InstrumentId
    bar_type: BarType
    # Comma-separated InstrumentId / BarType strings for the full sleeve universe.
    instrument_ids_csv: str
    bar_types_csv: str
    allocation_path: str
    # Notional quote currency allocated when fully invested (split by weight).
    portfolio_notional: Decimal
    # Ignore tiny residual diffs when deciding whether to trade.
    rebalance_tolerance: float = 0.02
    # Calendar days between rebalances (matches CI harness default).
    rebalance_every: int = 7


class RsRotationStrategy(Strategy):
    """Long-only top-N rotator driven by a precomputed allocation parquet."""

    def __init__(self, config: RsRotationConfig) -> None:
        super().__init__(config)
        self._allocations: dict[date, dict[str, float]] = {}
        self._instruments: dict[InstrumentId, Instrument] = {}
        self._bar_types: list[BarType] = []
        self._instrument_ids: list[InstrumentId] = []
        self._last_rebalance_date: date | None = None
        self._active_targets: dict[str, float] = {}

    def _parse_universe(self) -> None:
        id_tokens = [t.strip() for t in self.config.instrument_ids_csv.split(",") if t.strip()]
        bt_tokens = [t.strip() for t in self.config.bar_types_csv.split(",") if t.strip()]
        if not id_tokens or len(id_tokens) != len(bt_tokens):
            raise ValueError(
                "instrument_ids_csv and bar_types_csv must be non-empty and equal length"
            )
        self._instrument_ids = [InstrumentId.from_str(t) for t in id_tokens]
        self._bar_types = [BarType.from_str(t) for t in bt_tokens]

    def _load_allocations(self) -> dict[date, dict[str, float]]:
        df = pl.read_parquet(self.config.allocation_path)
        required = {"date", "symbol", "weight"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"allocation parquet missing columns: {sorted(missing)}")
        out: dict[date, dict[str, float]] = {}
        for row in df.select(["date", "symbol", "weight"]).to_dicts():
            d = row["date"]
            key = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
            out.setdefault(key, {})[str(row["symbol"])] = float(row["weight"])
        return out

    def _weight_for(self, iid: InstrumentId, targets: dict[str, float]) -> float:
        """Resolve allocation weight for an instrument (full id or bare symbol)."""
        symbol_key = str(iid).split(".")[0]
        if str(iid) in targets:
            return float(targets[str(iid)])
        if symbol_key in targets:
            return float(targets[symbol_key])
        # Also allow InstrumentId.symbol when present.
        sym = getattr(iid, "symbol", None)
        if sym is not None and str(sym) in targets:
            return float(targets[str(sym)])
        return 0.0

    def _last_price(self, iid: InstrumentId, *, clock_close: float | None) -> float | None:
        if iid == self.config.instrument_id and clock_close is not None and clock_close > 0:
            return float(clock_close)
        last = self.cache.price(iid, PriceType.LAST)
        if last is None:
            tick = self.cache.trade_tick(iid)
            if tick is not None:
                return float(tick.price)
            return None
        return float(last)

    def on_start(self) -> None:
        if int(self.config.rebalance_every) < 1:
            self.log.error("rebalance_every must be >= 1")
            self.stop()
            return
        self._parse_universe()
        for iid in self._instrument_ids:
            inst = self.cache.instrument(iid)
            if inst is None:
                self.log.error(f"Could not find instrument for {iid}")
                self.stop()
                return
            self._instruments[iid] = inst
        try:
            self._allocations = self._load_allocations()
        except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
            self.log.error(f"Failed to load allocations: {exc}")
            self.stop()
            return
        for bt in self._bar_types:
            self.subscribe_bars(bt)

    def on_bar(self, bar: Bar) -> None:
        # Clock on the configured primary bar_type only.
        if bar.bar_type != self.config.bar_type:
            return
        bar_date = unix_nanos_to_dt(bar.ts_event).date()
        if self._last_rebalance_date is not None:
            elapsed = (bar_date - self._last_rebalance_date).days
            if elapsed < int(self.config.rebalance_every):
                return
        self._last_rebalance_date = bar_date
        # Missing date ⇒ cash target for this rebalance (absolute / regime gate).
        self._active_targets = dict(self._allocations.get(bar_date, {}))
        self._rebalance_to(self._active_targets, clock_close=bar.close.as_double())

    def _rebalance_to(self, targets: dict[str, float], *, clock_close: float) -> None:
        """Flatten to cash when targets empty; else size sleeves by weight."""
        notional = float(self.config.portfolio_notional)
        tol = float(self.config.rebalance_tolerance)

        for iid, inst in self._instruments.items():
            weight = self._weight_for(iid, targets)
            pos = self.portfolio.net_position(iid)
            pos_qty = float(pos) if pos is not None else 0.0
            px = self._last_price(iid, clock_close=clock_close)
            if weight <= 0 or px is None or px <= 0:
                if abs(pos_qty) > 0:
                    self.close_all_positions(iid)
                continue
            desired = (notional * weight) / px
            if abs(desired - pos_qty) / max(abs(desired), 1.0) < tol:
                continue
            delta = desired - pos_qty
            side = OrderSide.BUY if delta > 0 else OrderSide.SELL
            qty = abs(delta)
            order = self.order_factory.market(
                instrument_id=iid,
                order_side=side,
                quantity=inst.make_qty(Decimal(str(round(qty, 8)))),
                time_in_force=TimeInForce.GTC,
            )
            self.submit_order(order)

    def on_stop(self) -> None:
        for iid in self._instrument_ids:
            self.cancel_all_orders(iid)
            self.close_all_positions(iid)


register(
    "rs_rotation",
    RsRotationStrategy,
    RsRotationConfig,
    default_params={
        "portfolio_notional": Decimal("10000"),
        "rebalance_tolerance": 0.02,
        "rebalance_every": 7,
        # Runtime paths / universe CSVs injected by caller (like m2 signal_path).
    },
    aliases=["relative_strength_rotation", "asset_rotation"],
    description="Long-only relative-strength asset rotator (Phase 1, #1084)",
)
