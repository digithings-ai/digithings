"""WP10.4/WP16.4 — one-account shared-cash Nautilus portfolio replay (#2784, #2991).

Builds a single ``BacktestEngine`` with one cash account, all instruments, and
global event ordering. Target deltas execute on the next synchronized bar.
Worker-local imports only — never call the independent per-symbol average runner.

WP16.4 adds :func:`reconcile_portfolio_replay_result` so every successful arm
reconciles NAV, cash, positions, fills, and commission totals in one engine.
"""

# score:allow pandas
# score:allow pd.
# score:allow untyped any

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Any

from digiquant.olympus.replay.models import (
    FillRecord,
    HoldingSnapshot,
    InstrumentBarSeries,
    NavPoint,
    PortfolioReplayRequest,
    PortfolioReplayResult,
    PortfolioReplayStatus,
    inconclusive_result,
    portfolio_replay_result_content_hash,
)

_logger = logging.getLogger(__name__)

_MONEY_QUANTUM = Decimal("0.01")


def run_shared_cash_portfolio_replay(request: PortfolioReplayRequest) -> PortfolioReplayResult:
    """Run one fresh shared-cash multi-instrument Nautilus engine for ``request``.

    Must be called from a spawned worker process (one engine per process).
    """
    try:
        return _run_engine(request)
    except Exception as exc:
        _logger.exception("shared-cash portfolio replay failed")
        return inconclusive_result(
            request_id=request.request_id,
            request_content_hash=request.content_hash(),
            status=PortfolioReplayStatus.ERROR,
            message=f"{type(exc).__name__}: {exc}",
            starting_cash=request.starting_cash,
        )


def _run_engine(request: PortfolioReplayRequest) -> PortfolioReplayResult:
    # Nautilus imports stay function-local so parent/test collection never loads
    # the Rust runtime.
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.backtest.models import FillModel, MakerTakerFeeModel
    from nautilus_trader.config import BacktestEngineConfig, LoggingConfig, StrategyConfig
    from nautilus_trader.model.currencies import USD
    from nautilus_trader.model.data import BarType
    from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, TimeInForce
    from nautilus_trader.model.identifiers import Venue
    from nautilus_trader.model.instruments import Equity
    from nautilus_trader.model.objects import Money, Quantity
    from nautilus_trader.persistence.wranglers import BarDataWrangler
    from nautilus_trader.test_kit.providers import TestInstrumentProvider
    from nautilus_trader.trading.strategy import Strategy

    venue_name = request.execution.venue
    venue = Venue(venue_name)
    commission = request.execution.commission_rate
    fill_fraction = request.execution.fill_fraction
    next_bar = request.execution.next_bar_execution
    unit_lot = Quantity.from_int(1)

    instruments: dict[str, Any] = {}
    bar_types: dict[str, Any] = {}
    prepared_bars: dict[str, list[Any]] = {}
    for series in request.series:
        base = TestInstrumentProvider.equity(symbol=series.ticker, venue=venue_name)
        inst = Equity(
            instrument_id=base.id,
            raw_symbol=base.raw_symbol,
            currency=base.quote_currency,
            price_precision=base.price_precision,
            price_increment=base.price_increment,
            lot_size=unit_lot,
            isin=base.isin,
            ts_event=base.ts_event,
            ts_init=base.ts_init,
            maker_fee=commission,
            taker_fee=commission,
        )
        instruments[series.ticker] = inst
        bar_type = BarType.from_str(f"{series.ticker}.{venue_name}-1-DAY-LAST-EXTERNAL")
        bar_types[series.ticker] = bar_type
        pd_df = _bars_to_pandas(series)
        wrangler = BarDataWrangler(bar_type=bar_type, instrument=inst)
        bars = wrangler.process(pd_df)
        if not bars:
            return inconclusive_result(
                request_id=request.request_id,
                request_content_hash=request.content_hash(),
                status=PortfolioReplayStatus.ERROR,
                message=f"no bars produced for {series.ticker}",
                starting_cash=request.starting_cash,
            )
        prepared_bars[series.ticker] = bars

    targets = {t.ticker: t.weight for t in request.target_weights}
    initial = {h.ticker: h.quantity for h in request.initial_holdings}
    tickers = [s.ticker for s in request.series]
    needs_seed = any(q > 0 for q in initial.values())

    class PortfolioReplayConfig(StrategyConfig, frozen=True):
        pass

    class SharedCashPortfolioStrategy(Strategy):
        def __init__(self, config: PortfolioReplayConfig) -> None:
            super().__init__(config)
            self._bar_index: dict[str, int] = {t: 0 for t in tickers}
            self._sync_count = 0
            self._seeded = not needs_seed
            self._rebalanced = False
            self._fills: list[FillRecord] = []
            self._nav_path: list[NavPoint] = []

        def on_start(self) -> None:
            for bt in bar_types.values():
                self.subscribe_bars(bt)

        def on_bar(self, bar: Any) -> None:
            ticker = bar.bar_type.instrument_id.symbol.value
            self._bar_index[ticker] = self._bar_index.get(ticker, 0) + 1
            if min(self._bar_index.values()) < self._sync_count + 1:
                return
            self._sync_count += 1

            # Mark-to-market at every synchronized close for drawdown evidence (#2831).
            nav, _qty, _last = self._nav_and_qty()
            ts = datetime.fromtimestamp(bar.ts_event / 1e9, tz=timezone.utc)
            self._nav_path.append(NavPoint(ts=ts, nav=nav.quantize(_MONEY_QUANTUM)))

            if not self._seeded:
                self._submit_quantity_orders(initial, tag="seed")
                self._seeded = True
                return

            if self._rebalanced:
                return

            # After optional seed: decide on sync N, execute on N+1 when next_bar.
            # needs_seed → seed at sync 1; decision at sync 2; exec at sync 3 (next_bar).
            # flat start → decision at sync 1; exec at sync 2 (next_bar).
            decision_sync = 2 if needs_seed else 1
            exec_sync = decision_sync + (1 if next_bar else 0)
            if self._sync_count < exec_sync:
                return
            self._submit_rebalance_orders()
            self._rebalanced = True

        def _nav_and_qty(self) -> tuple[Decimal, dict[str, Decimal], dict[str, Decimal]]:
            account = self.portfolio.account(venue)
            cash = Decimal(str(account.balance_total(USD)).split()[0])
            qty: dict[str, Decimal] = {}
            last: dict[str, Decimal] = {}
            positions_value = Decimal("0")
            for ticker, inst in instruments.items():
                net = self.portfolio.net_position(inst.id)
                q = Decimal(str(net)) if net is not None else Decimal("0")
                qty[ticker] = q
                last_bar = self.cache.bar(bar_types[ticker])
                px = Decimal(str(last_bar.close)) if last_bar is not None else Decimal("0")
                last[ticker] = px
                positions_value += q * px
            return cash + positions_value, qty, last

        def _submit_quantity_orders(self, quantities: dict[str, Decimal], *, tag: str) -> None:
            for ticker, want in quantities.items():
                if want <= 0:
                    continue
                units = int(want)
                if units <= 0:
                    continue
                order = self.order_factory.market(
                    instrument_id=instruments[ticker].id,
                    order_side=OrderSide.BUY,
                    quantity=Quantity.from_int(units),
                    time_in_force=TimeInForce.GTC,
                    tags=[tag],
                )
                self.submit_order(order)

        def _submit_rebalance_orders(self) -> None:
            nav, qty, last = self._nav_and_qty()
            if nav <= 0:
                return
            for ticker in tickers:
                weight = targets.get(ticker, Decimal("0"))
                px = last[ticker]
                if px <= 0:
                    continue
                target_qty = (weight * nav / px).to_integral_value(rounding=ROUND_DOWN)
                delta = target_qty - qty[ticker]
                if fill_fraction < 1:
                    delta = (delta * fill_fraction).to_integral_value(rounding=ROUND_DOWN)
                if delta == 0:
                    continue
                side = OrderSide.BUY if delta > 0 else OrderSide.SELL
                units = abs(int(delta))
                if side == OrderSide.SELL:
                    units = min(units, int(qty[ticker]))
                if units <= 0:
                    continue
                order = self.order_factory.market(
                    instrument_id=instruments[ticker].id,
                    order_side=side,
                    quantity=Quantity.from_int(units),
                    time_in_force=TimeInForce.GTC,
                    tags=["rebalance"],
                )
                self.submit_order(order)

        def on_order_filled(self, event: Any) -> None:
            ticker = event.instrument_id.symbol.value
            is_seed = False
            order = self.cache.order(event.client_order_id)
            if order is not None and order.tags:
                is_seed = "seed" in list(order.tags)
            commission_amt = Decimal("0")
            if event.commission is not None:
                commission_amt = Decimal(str(event.commission.as_double()))
            ts = datetime.fromtimestamp(event.ts_event / 1e9, tz=timezone.utc)
            side_enum = event.order_side
            if side_enum == OrderSide.BUY:
                side = "BUY"
            elif side_enum == OrderSide.SELL:
                side = "SELL"
            else:
                side = str(side_enum).split(".")[-1].upper()
            self._fills.append(
                FillRecord(
                    ticker=ticker,
                    side=side,
                    quantity=Decimal(str(event.last_qty)),
                    price=Decimal(str(event.last_px)),
                    commission=commission_amt,
                    ts=ts,
                    is_seed=is_seed,
                )
            )

    engine = BacktestEngine(
        config=BacktestEngineConfig(
            logging=LoggingConfig(log_level="ERROR"),
        )
    )
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=USD,
        starting_balances=[Money(float(request.starting_cash), USD)],
        fill_model=FillModel(
            prob_fill_on_limit=1.0,
            prob_slippage=0.0,
            random_seed=request.execution.random_seed,
        ),
        fee_model=MakerTakerFeeModel(),
    )
    for ticker in tickers:
        engine.add_instrument(instruments[ticker])
        engine.add_data(prepared_bars[ticker])

    strategy = SharedCashPortfolioStrategy(PortfolioReplayConfig())
    engine.add_strategy(strategy)
    engine.run()

    account = engine.portfolio.account(venue)
    ending_cash = _money_to_decimal(account.balance_total(USD))
    holdings: list[HoldingSnapshot] = []
    nav = ending_cash
    for ticker, inst in instruments.items():
        net = engine.portfolio.net_position(inst.id)
        qty = Decimal(str(net)) if net is not None else Decimal("0")
        last_bar = engine.cache.bar(bar_types[ticker])
        px = Decimal(str(last_bar.close)) if last_bar is not None else Decimal("0")
        mv = (qty * px).quantize(_MONEY_QUANTUM)
        holdings.append(
            HoldingSnapshot(
                ticker=ticker,
                quantity=qty,
                last_price=px,
                market_value=mv,
            )
        )
        nav += mv
    holdings_t = tuple(sorted(holdings, key=lambda h: h.ticker))
    fills = tuple(strategy._fills)
    nav_path = tuple(strategy._nav_path)
    total_commission = sum((f.commission for f in fills), Decimal("0")).quantize(_MONEY_QUANTUM)
    rebalance_commission = sum(
        (f.commission for f in fills if not f.is_seed),
        Decimal("0"),
    ).quantize(_MONEY_QUANTUM)

    draft = PortfolioReplayResult.model_construct(
        schema_version="1.0",
        request_id=request.request_id,
        request_content_hash=request.content_hash(),
        status=PortfolioReplayStatus.OK,
        starting_cash=request.starting_cash,
        ending_cash=ending_cash.quantize(_MONEY_QUANTUM),
        ending_nav=nav.quantize(_MONEY_QUANTUM),
        total_commission=total_commission,
        rebalance_commission=rebalance_commission,
        holdings=holdings_t,
        fills=fills,
        nav_path=nav_path,
        message="shared-cash portfolio replay ok",
        result_content_hash="0" * 64,
    )
    digest = portfolio_replay_result_content_hash(draft)
    return PortfolioReplayResult(
        request_id=request.request_id,
        request_content_hash=request.content_hash(),
        status=PortfolioReplayStatus.OK,
        starting_cash=request.starting_cash,
        ending_cash=ending_cash.quantize(_MONEY_QUANTUM),
        ending_nav=nav.quantize(_MONEY_QUANTUM),
        total_commission=total_commission,
        rebalance_commission=rebalance_commission,
        holdings=holdings_t,
        fills=fills,
        nav_path=nav_path,
        message="shared-cash portfolio replay ok",
        result_content_hash=digest,
    )


def _bars_to_pandas(series: InstrumentBarSeries) -> Any:
    """Convert instrument bar series via Polars → pandas (Nautilus wrangler boundary).

    Matches ``nautilus_runner._prepare_bar_data``: pandas 3 CoW frames built from
    plain Python lists are rejected by ``BarDataWrangler`` (read-only buffers);
    Polars ``to_pandas()`` yields a layout the wrangler accepts.
    """
    import pandas as pd
    import polars as pl

    volumes = [float(b.volume) for b in series.bars]
    pl_df = pl.DataFrame(
        {
            "timestamp": [b.ts for b in series.bars],
            "open": [float(b.open) for b in series.bars],
            "high": [float(b.high) for b in series.bars],
            "low": [float(b.low) for b in series.bars],
            "close": [float(b.close) for b in series.bars],
            "volume": volumes,
        }
    )
    pd_df = pl_df.select(["open", "high", "low", "close"]).to_pandas()
    pd_df.index = pd.to_datetime(pl_df["timestamp"].to_pandas(), utc=True)
    pd_df.index.name = "timestamp"
    # Assign volume as a plain float64 Series — Polars→pandas can null volume on
    # some dtype paths; never pass NaN into BarDataWrangler Quantity.
    pd_df["volume"] = pd.Series(volumes, index=pd_df.index, dtype="float64")
    return pd_df


def _money_to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    text = str(value).strip().split()[0]
    return Decimal(text)


def reconcile_portfolio_replay_result(result: PortfolioReplayResult) -> None:
    """Verify NAV, cash, holdings, fills, and commission reconcile for *result*.

    Raises ``ValueError`` when financially material fields disagree. Callers use
    this as the WP16.4 acceptance metric: one engine, one reconciled book.
    """
    if result.status is not PortfolioReplayStatus.OK:
        raise ValueError("reconcile requires status=ok")
    if result.ending_cash is None or result.ending_nav is None:
        raise ValueError("ok result missing ending_cash or ending_nav")
    if result.total_commission is None or result.rebalance_commission is None:
        raise ValueError("ok result missing commission totals")

    holdings_value = sum((h.market_value for h in result.holdings), Decimal("0"))
    expected_nav = (result.ending_cash + holdings_value).quantize(_MONEY_QUANTUM)
    if result.ending_nav != expected_nav:
        raise ValueError(
            f"ending_nav {result.ending_nav} != ending_cash + holdings ({expected_nav})"
        )

    for holding in result.holdings:
        expected_mv = (holding.quantity * holding.last_price).quantize(_MONEY_QUANTUM)
        if holding.market_value != expected_mv:
            raise ValueError(
                f"{holding.ticker} market_value {holding.market_value} != qty*price ({expected_mv})"
            )

    fill_commission = sum((f.commission for f in result.fills), Decimal("0")).quantize(
        _MONEY_QUANTUM
    )
    if fill_commission != result.total_commission:
        raise ValueError(
            f"total_commission {result.total_commission} != sum(fill commissions) "
            f"({fill_commission})"
        )

    rebalance_commission = sum(
        (f.commission for f in result.fills if not f.is_seed),
        Decimal("0"),
    ).quantize(_MONEY_QUANTUM)
    if rebalance_commission != result.rebalance_commission:
        raise ValueError(
            f"rebalance_commission {result.rebalance_commission} != non-seed fills "
            f"({rebalance_commission})"
        )


__all__ = ["reconcile_portfolio_replay_result", "run_shared_cash_portfolio_replay"]
