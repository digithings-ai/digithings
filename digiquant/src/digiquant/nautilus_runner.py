"""
Run a real NautilusTrader backtest when nautilus_trader is installed.
Requires user OHLCV data via data_path or data_dir. No fallback; backtest fails if data unavailable.
"""

from __future__ import annotations

import math

# Cache dir for tearsheets; relative paths resolve here. Add to .gitignore.
BACKTEST_RESULTS_DIR = "backtest_results"
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import polars as pl

from digiquant.models import BacktestResult


def _infer_bar_period_nautilus(ts_series: pl.Series) -> str:
    """Infer Nautilus bar period string from timestamp deltas. Returns e.g. 1-MINUTE, 1-HOUR, 1-DAY."""
    if ts_series.len() < 2:
        return "1-DAY"
    sorted_ts = ts_series.sort()
    diffs = sorted_ts.diff().drop_nulls()
    if diffs.len() == 0:
        return "1-DAY"
    try:
        median_us = diffs.dt.total_microseconds().median()
    except Exception:
        return "1-DAY"
    if median_us is None:
        return "1-DAY"
    median_sec = float(median_us) / 1e6
    if median_sec <= 90:
        return "1-MINUTE"
    if median_sec <= 3600:
        return "1-HOUR"
    return "1-DAY"


def _load_ohlcv_for_backtest(
    data_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    symbols: list[str] | None = None,
) -> tuple[pl.DataFrame, str] | None:
    """
    Load OHLCV data for backtest. Returns (df, symbol) for single-instrument run.
    - data_path: single CSV path -> load it, symbol from filename
    - data_dir + symbols: load first symbol's CSV from data_dir
    """
    from digiquant.data.loader import load_ohlcv_csv

    if data_path is not None:
        path = Path(data_path)
        if not path.exists():
            return None
        df = load_ohlcv_csv(path)
        symbol = df["symbol"][0] if "symbol" in df.columns else path.stem.split("_")[0]
        return df, str(symbol)

    if data_dir is not None and symbols:
        data_dir = Path(data_dir)
        if not data_dir.is_dir():
            return None
        for sym in symbols:
            for candidate in (data_dir / f"{sym}.csv", data_dir / f"{sym}_ohlcv.csv"):
                if candidate.exists():
                    df = load_ohlcv_csv(candidate)
                    return df, sym
    return None


def _run_backtest_ohlcv(
    ohlcv_df: pl.DataFrame,
    symbol: str,
    strategy_name: str,
    symbols_echo: list[str],
    tearsheet_path: str | Path | None = None,
    strategy_params: dict | None = None,
) -> BacktestResult | None:
    """Run Nautilus backtest on OHLCV bar data. Uses EMACross strategy."""
    try:
        from nautilus_trader.backtest.engine import BacktestEngine
        from nautilus_trader.model import BarType
        from nautilus_trader.model import Venue
        from nautilus_trader.model.currencies import USD
        from nautilus_trader.model.enums import AccountType
        from nautilus_trader.model.enums import OmsType
        from nautilus_trader.model.objects import Money
        from nautilus_trader.persistence.wranglers import BarDataWrangler
        from nautilus_trader.test_kit.providers import TestInstrumentProvider

        from digiquant.strategies import get_strategy
    except ImportError:
        return None

    ts_col = "timestamp" if "timestamp" in ohlcv_df.columns else ohlcv_df.columns[0]
    bar_period = _infer_bar_period_nautilus(ohlcv_df[ts_col])

    # Polars -> pandas for BarDataWrangler (Nautilus API boundary; expects 'timestamp' index)
    pd_df = ohlcv_df.select(["open", "high", "low", "close"]).to_pandas()
    idx = pd.to_datetime(ohlcv_df[ts_col].to_pandas(), utc=True)
    pd_df.index = idx
    pd_df.index.name = "timestamp"
    if "volume" in ohlcv_df.columns:
        pd_df["volume"] = ohlcv_df["volume"].fill_null(1_000_000.0).to_pandas().astype("float64")
    else:
        pd_df["volume"] = 1_000_000.0
    pd_df["volume"] = pd_df["volume"].fillna(1_000_000.0)

    venue_name = "SIM"
    inst = TestInstrumentProvider.equity(symbol=symbol, venue=venue_name)
    bar_type_str = f"{symbol}.{venue_name}-{bar_period}-LAST-EXTERNAL"
    bar_type = BarType.from_str(bar_type_str)
    wrangler = BarDataWrangler(bar_type=bar_type, instrument=inst)
    bars = wrangler.process(pd_df)
    if not bars:
        return None

    engine = BacktestEngine()
    venue = Venue(venue_name)
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=USD,
        starting_balances=[Money(1_000_000.0, USD)],
    )
    engine.add_instrument(inst)
    engine.add_data(bars)

    params: dict = {"trade_size": Decimal(1000)}
    if strategy_params:
        for k, v in strategy_params.items():
            if k == "trade_size":
                params["trade_size"] = Decimal(str(v))
            else:
                params[k] = v
    strategy, _config = get_strategy(
        strategy_name=strategy_name,
        instrument_id=inst.id,
        bar_type=bar_type,
        **params,
    )
    engine.add_strategy(strategy)
    engine.run()

    run_id = f"nautilus-{uuid.uuid4().hex[:8]}"
    fills = engine.trader.generate_order_fills_report()
    num_trades = len(fills) if fills is not None else 0
    account_report = engine.trader.generate_account_report(venue)
    start_ts = bars[0].ts_init
    end_ts = bars[-1].ts_init

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
                    amount, _ = total_str.split()
                    final_balance = float(amount)
                else:
                    final_balance = float(total_str)
                total_pnl = final_balance - initial
                total_return_pct = (total_pnl / initial) * 100.0
        except Exception:
            pass

    sharpe: float | None = None
    max_dd: float | None = None
    stats_returns: dict | None = None
    stats_pnls: dict | None = None
    stats_general: dict | None = None
    returns_series = None
    realized_pnls_series = None
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
        if hasattr(engine.portfolio.analyzer, "get_performance_stats_general"):
            stats_general = engine.portfolio.analyzer.get_performance_stats_general()
        if hasattr(engine.portfolio.analyzer, "returns"):
            returns_series = engine.portfolio.analyzer.returns()
        if hasattr(engine.portfolio.analyzer, "realized_pnls"):
            rp = engine.portfolio.analyzer.realized_pnls(USD)
            realized_pnls_series = rp if rp is not None and len(rp) > 0 else None
        if max_dd is None and returns_series is not None and len(returns_series) > 0:
            try:
                cum = (1 + returns_series).cumprod()
                peak = cum.cummax()
                dd_pct = (peak - cum) / peak.replace(0, 1) * 100
                max_dd = float(dd_pct.max()) if not dd_pct.empty else None
            except Exception:
                pass
    except Exception:
        pass

    def _ns_to_iso(ns: int) -> str:
        dt = datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    engine.dispose()

    def _safe_float(x: float | None) -> float | None:
        if x is None or math.isnan(x):
            return None
        return x

    bt_result = BacktestResult(
        run_id=run_id,
        strategy_name=strategy_name,
        symbols=symbols_echo or [symbol],
        start_time=_ns_to_iso(start_ts),
        end_time=_ns_to_iso(end_ts),
        total_pnl=_safe_float(total_pnl) or 0.0,
        total_return_pct=_safe_float(total_return_pct) or 0.0,
        sharpe_ratio=sharpe,
        max_drawdown_pct=max_dd,
        num_trades=num_trades,
        status="ok",
        message=f"Backtest on user OHLCV data ({symbol}).",
    )

    if tearsheet_path is not None:
        try:
            from digiquant.tearsheet import create_tearsheet as create_digi_tearsheet

            out = Path(tearsheet_path)
            if not out.is_absolute():
                out = Path(BACKTEST_RESULTS_DIR) / out
            create_digi_tearsheet(
                result=bt_result,
                output_path=out,
                strategy_params=strategy_params,
                account_report=account_report,
                fills_report=fills,
                ohlcv_df=ohlcv_df,
                symbol=symbol,
                stats_returns=stats_returns,
                stats_pnls=stats_pnls,
                stats_general=stats_general,
                returns_series=returns_series,
                realized_pnls_series=realized_pnls_series,
            )
        except ImportError:
            pass  # plotly/visualization not installed

    return bt_result


def run_nautilus_backtest(
    strategy_name: str,
    symbols: list[str],
    data_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    tearsheet_path: str | Path | None = None,
    strategy_params: dict | None = None,
) -> BacktestResult | None:
    """
    Run NautilusTrader backtest on user OHLCV data.
    Requires data_path (single CSV) or data_dir + symbols. Returns None if data unavailable
    or nautilus_trader not installed.
    """
    loaded = _load_ohlcv_for_backtest(data_path=data_path, data_dir=data_dir, symbols=symbols)
    if loaded is None:
        return None
    ohlcv_df, symbol = loaded
    return _run_backtest_ohlcv(
        ohlcv_df=ohlcv_df,
        symbol=symbol,
        strategy_name=strategy_name,
        symbols_echo=symbols or [symbol],
        tearsheet_path=tearsheet_path,
        strategy_params=strategy_params,
    )
