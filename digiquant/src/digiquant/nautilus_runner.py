"""
Run a real NautilusTrader backtest when nautilus_trader is installed.
Uses bundled test data (e.g. ETHUSDT trades). Returns BacktestResult or None.
"""

from __future__ import annotations

import math
import uuid
from decimal import Decimal

import polars as pl

from digiquant.models import BacktestResult


def run_nautilus_backtest(
    strategy_name: str,
    symbols: list[str],
) -> BacktestResult | None:
    """
    Run NautilusTrader backtest with bundled test data. Returns None if
    nautilus_trader is not installed or backtest fails.
    """
    try:
        from nautilus_trader.backtest.engine import BacktestEngine
        from nautilus_trader.model import BarType
        from nautilus_trader.model import Venue
        from nautilus_trader.model.currencies import USDT
        from nautilus_trader.model.enums import AccountType
        from nautilus_trader.model.enums import OmsType
        from nautilus_trader.model.objects import Money
        from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
        from nautilus_trader.test_kit.providers import TestDataProvider
        from nautilus_trader.test_kit.providers import TestInstrumentProvider
    except ImportError:
        return None

    try:
        provider = TestDataProvider()
        # Bundled CSV: binance/ethusdt-trades.csv
        trades_df = provider.read_csv_ticks("binance/ethusdt-trades.csv")
    except Exception:
        return None

    instrument = TestInstrumentProvider.ethusdt_binance()
    wrangler = TradeTickDataWrangler(instrument=instrument)
    ticks = wrangler.process(trades_df)
    if not ticks:
        return None

    config = None  # use default BacktestEngineConfig
    engine = BacktestEngine(config=config)
    venue = Venue("BINANCE")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=None,
        starting_balances=[Money(1_000_000.0, USDT), Money(10.0, instrument.quote_currency)],
    )
    engine.add_instrument(instrument)
    engine.add_data(ticks, sort=False)
    engine.sort_data()

    # EMACross from examples (bar type must match; we have trade ticks -> use TICK bar)
    bar_type = BarType.from_str("ETHUSDT.BINANCE-250-TICK-LAST-INTERNAL")
    from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAP
    from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAPConfig

    strategy_config = EMACrossTWAPConfig(
        instrument_id=instrument.id,
        bar_type=bar_type,
        trade_size=Decimal("0.10"),
        fast_ema_period=10,
        slow_ema_period=20,
        twap_horizon_secs=10.0,
        twap_interval_secs=2.5,
    )
    strategy = EMACrossTWAP(config=strategy_config)
    engine.add_strategy(strategy)

    from nautilus_trader.examples.algorithms.twap import TWAPExecAlgorithm
    engine.add_exec_algorithm(TWAPExecAlgorithm())

    engine.run()

    # Extract results
    run_id = f"nautilus-{uuid.uuid4().hex[:8]}"
    fills = engine.trader.generate_order_fills_report()
    num_trades = len(fills) if fills is not None else 0
    account_report = engine.trader.generate_account_report(venue)
    start_ts = ticks[0].ts_init
    end_ts = ticks[-1].ts_init

    # Total PnL: last balance - initial (1M USDT)
    total_pnl = 0.0
    total_return_pct = 0.0
    if account_report is not None:
        try:
            df = pl.from_pandas(account_report)
            if df.height > 0:
                last_row = df.row(-1, named=True)
                total_str = last_row.get("total", "1000000")
                initial = 1_000_000.0
                if isinstance(total_str, str) and " " in total_str:
                    amount, curr = total_str.split()
                    final_balance = float(amount)
                else:
                    final_balance = float(total_str)
                total_pnl = final_balance - initial
                total_return_pct = (total_pnl / initial) * 100.0
        except Exception:
            pass

    sharpe: float | None = None
    max_dd: float | None = None
    try:
        stats_returns = engine.portfolio.analyzer.get_performance_stats_returns()
        if stats_returns:
            raw = stats_returns.get("Sharpe Ratio (252 days)", 0) or 0
            v = float(raw)
            sharpe = v if not math.isnan(v) else None
        stats_pnls = engine.portfolio.analyzer.get_performance_stats_pnls()
        if stats_pnls:
            dd = stats_pnls.get("Max Drawdown %") or stats_pnls.get("Max Drawdown")
            if dd is not None:
                v = float(dd)
                max_dd = v if not math.isnan(v) else None
    except Exception:
        pass

    def _ns_to_iso(ns: int) -> str:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    engine.dispose()

    # Ensure JSON-serializable: no nan
    def _safe_float(x: float | None) -> float | None:
        if x is None or math.isnan(x):
            return None
        return x

    return BacktestResult(
        run_id=run_id,
        strategy_name=strategy_name,
        symbols=symbols or [instrument.id.value],
        start_time=_ns_to_iso(start_ts),
        end_time=_ns_to_iso(end_ts),
        total_pnl=_safe_float(total_pnl) or 0.0,
        total_return_pct=_safe_float(total_return_pct) or 0.0,
        sharpe_ratio=sharpe,
        max_drawdown_pct=max_dd,
        num_trades=num_trades,
        status="ok",
        message="Backtest uses bundled ETHUSDT data (v0.1). User symbols echoed for workflow; per-symbol backtest in Phase 2.",
    )
