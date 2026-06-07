"""
Run a real NautilusTrader backtest when nautilus_trader is installed.
Requires user OHLCV data via data_path or data_dir. No fallback; backtest fails if data unavailable.

Internal structure
------------------
_prepare_bar_data      — Polars OHLCV -> pandas + Nautilus BarType + bars list
_build_engine          — configure BacktestEngine with venue/instrument/data/strategy
_extract_pnl           — parse account report -> (total_pnl, total_return_pct)
_extract_perf_stats    — pull Sharpe, max-drawdown, series from portfolio analyzer
_build_result          — assemble BacktestResult from raw engine outputs
_run_backtest_ohlcv    — orchestrates the above; writes tearsheet if requested
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import polars as pl

from digiquant.constraints import normalize_drawdown_pct
from digiquant.models import BacktestResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_POLARS_DT_ERRORS = (
    AttributeError,
    TypeError,
    pl.exceptions.ComputeError,
    pl.exceptions.InvalidOperationError,
)
_OHLCV_LOAD_ERRORS = (OSError, ValueError, pl.exceptions.ComputeError, pl.exceptions.SchemaError)
_PNL_PARSE_ERRORS = (ValueError, TypeError, KeyError, IndexError)
_ANALYZER_ERRORS = (AttributeError, TypeError, ValueError)
_TEARSHEET_ERRORS = (ImportError, OSError, ValueError, TypeError, RuntimeError)

# Cache dir for tearsheets; relative paths resolve here. Add to .gitignore.
BACKTEST_RESULTS_DIR = "backtest_results"

# Venue starting cash. Single source of truth for sizing + PnL baseline.
STARTING_BALANCE_USD = 1_000_000.0

# Default position size, as a fraction of starting balance, expressed in notional.
# trade_size (units) = floor(STARTING_BALANCE_USD * fraction / first_price), min 1.
# Notional-based so a fixed unit count doesn't over-leverage high-priced instruments
# (e.g. 1000 BTC units on a $1M account is ~10-100x leverage and halts the run with
# AccountBalanceNegative after a handful of bars). 2% of $1M ≈ 1 BTC at ~$13.6k, a
# size known to complete the full BTC-USD run.
DEFAULT_NOTIONAL_FRACTION = 0.02


def _default_trade_size(first_price: float, balance: float, fraction: float) -> Decimal:
    """Notional-based default position size in instrument units (floored, min 1).

    Keeps per-trade notional at ``fraction`` of account balance regardless of unit
    price, so the run does not over-leverage and halt on high-priced instruments.
    """
    if first_price <= 0:
        return Decimal(1)
    units = int((balance * fraction) // first_price)
    return Decimal(max(units, 1))


def _resolve_tearsheet_output(path: str | Path) -> Path:
    """Resolve tearsheet path under BACKTEST_RESULTS_DIR (reject path traversal)."""
    out = Path(path)
    if not out.is_absolute():
        out = Path(BACKTEST_RESULTS_DIR) / out
    base = Path(BACKTEST_RESULTS_DIR).resolve()
    resolved = out.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"tearsheet_path must resolve under {BACKTEST_RESULTS_DIR!r}") from exc
    return resolved


# ---------------------------------------------------------------------------
# Bar period inference
# ---------------------------------------------------------------------------


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
    except _POLARS_DT_ERRORS:
        return "1-DAY"
    if median_us is None:
        return "1-DAY"
    median_sec = float(median_us) / 1e6
    if median_sec <= 90:
        return "1-MINUTE"
    if median_sec <= 3600:
        return "1-HOUR"
    return "1-DAY"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_ohlcv_for_backtest(
    data_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    symbols: list[str] | None = None,
) -> tuple[pl.DataFrame, str] | None:
    """
    Load OHLCV data for backtest. Returns (df, symbol) for single-instrument run.
    - data_path: single CSV path -> load it, symbol from filename
    - data_dir + symbols: load first symbol's CSV from data_dir

    For multi-symbol runs use _load_all_ohlcv_for_backtest().
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
        data_dir_resolved = data_dir.resolve()
        for sym in symbols:
            for candidate in (data_dir / f"{sym}.csv", data_dir / f"{sym}_ohlcv.csv"):
                resolved_candidate = candidate.resolve()
                if not resolved_candidate.is_relative_to(data_dir_resolved):
                    logger.warning("Symbol path escapes data_dir, skipping: %s", candidate)
                    continue
                if resolved_candidate.exists():
                    df = load_ohlcv_csv(resolved_candidate)
                    return df, sym
    return None


def _load_all_ohlcv_for_backtest(
    data_dir: str | Path,
    symbols: list[str],
) -> dict[str, pl.DataFrame]:
    """Load all available symbol CSVs from data_dir. Returns {symbol: df} for found symbols."""
    from digiquant.data.loader import load_ohlcv_csv

    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        return {}
    data_dir_resolved = data_dir.resolve()
    loaded: dict[str, pl.DataFrame] = {}
    for sym in symbols:
        for candidate in (data_dir / f"{sym}.csv", data_dir / f"{sym}_ohlcv.csv"):
            resolved_candidate = candidate.resolve()
            if not resolved_candidate.is_relative_to(data_dir_resolved):
                logger.warning("Symbol path escapes data_dir, skipping: %s", candidate)
                continue
            if resolved_candidate.exists():
                try:
                    loaded[sym] = load_ohlcv_csv(resolved_candidate)
                    logger.debug("Loaded OHLCV for %s from %s", sym, resolved_candidate)
                except _OHLCV_LOAD_ERRORS as e:
                    logger.warning("Failed to load OHLCV for %s: %s", sym, e)
                break
    return loaded


# ---------------------------------------------------------------------------
# Engine setup helpers
# ---------------------------------------------------------------------------


def _prepare_bar_data(
    ohlcv_df: pl.DataFrame,
    symbol: str,
    venue_name: str,
    BarType: Any,
    BarDataWrangler: Any,
    TestInstrumentProvider: Any,
) -> tuple[Any, Any, Any, Any] | None:
    """Convert Polars OHLCV DataFrame to Nautilus bars.

    Returns (inst, bar_type, bars, pd_df) or None if conversion yields no bars.
    """
    ts_col = "timestamp" if "timestamp" in ohlcv_df.columns else ohlcv_df.columns[0]
    bar_period = _infer_bar_period_nautilus(ohlcv_df[ts_col])

    # Polars -> pandas (Nautilus API boundary; expects 'timestamp' index)
    pd_df = ohlcv_df.select(["open", "high", "low", "close"]).to_pandas()
    idx = pd.to_datetime(ohlcv_df[ts_col].to_pandas(), utc=True)
    pd_df.index = idx
    pd_df.index.name = "timestamp"
    if "volume" in ohlcv_df.columns:
        pd_df["volume"] = ohlcv_df["volume"].fill_null(1_000_000.0).to_pandas().astype("float64")
    else:
        pd_df["volume"] = 1_000_000.0
    pd_df["volume"] = pd_df["volume"].fillna(1_000_000.0)

    inst = TestInstrumentProvider.equity(symbol=symbol, venue=venue_name)
    bar_type_str = f"{symbol}.{venue_name}-{bar_period}-LAST-EXTERNAL"
    bar_type = BarType.from_str(bar_type_str)
    wrangler = BarDataWrangler(bar_type=bar_type, instrument=inst)
    bars = wrangler.process(pd_df)
    if not bars:
        return None
    return inst, bar_type, bars, pd_df


def _build_engine(
    inst: Any,
    bars: Any,
    bar_type: Any,
    strategy_name: str,
    strategy_params: dict | None,
    venue_name: str,
    BacktestEngine: Any,
    Venue: Any,
    OmsType: Any,
    AccountType: Any,
    USD: Any,
    Money: Any,
    get_strategy: Any,
) -> Any:
    """Configure and run a BacktestEngine. Returns the completed engine."""
    engine = BacktestEngine()
    venue = Venue(venue_name)
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=USD,
        starting_balances=[Money(STARTING_BALANCE_USD, USD)],
    )
    engine.add_instrument(inst)
    engine.add_data(bars)

    # Instrument-aware default: size from the first bar price so notional stays a
    # small fraction of equity rather than a fixed unit count. An explicit caller
    # trade_size always wins.
    first_price = float(bars[0].close) if bars else 0.0
    default_size = _default_trade_size(first_price, STARTING_BALANCE_USD, DEFAULT_NOTIONAL_FRACTION)
    params: dict = {"trade_size": default_size}
    if strategy_params:
        params.update(strategy_params)
        if "trade_size" in strategy_params:
            params["trade_size"] = Decimal(str(strategy_params["trade_size"]))
    strategy, _config = get_strategy(
        strategy_name=strategy_name,
        instrument_id=inst.id,
        bar_type=bar_type,
        **params,
    )
    engine.add_strategy(strategy)
    engine.run()
    return engine


def _extract_pnl(account_report: Any) -> tuple[float, float]:
    """Parse Nautilus account report -> (total_pnl, total_return_pct). Returns (0, 0) on failure."""
    if account_report is None:
        return 0.0, 0.0
    try:
        df = pl.from_pandas(account_report)
        if df.height == 0:
            return 0.0, 0.0
        last_row = df.row(-1, named=True)
        initial = STARTING_BALANCE_USD
        raw_balance = None
        for col_name in ("total", "balance", "equity"):
            if col_name in last_row and last_row[col_name] is not None:
                raw_balance = last_row[col_name]
                break
        if raw_balance is None:
            logger.warning(
                "Account report has no recognised balance column. Columns: %s",
                list(last_row.keys()),
            )
            return 0.0, 0.0
        # Nautilus may return "1000000.00 USD" or a numeric value
        if isinstance(raw_balance, str):
            final_balance = float(raw_balance.strip().split()[0])
        else:
            final_balance = float(raw_balance)
        total_pnl = final_balance - initial
        return total_pnl, (total_pnl / initial) * 100.0
    except _PNL_PARSE_ERRORS as e:
        logger.warning("Failed to parse account report for PnL: %s", e)
        return 0.0, 0.0


def _extract_perf_stats(engine: Any, USD: Any) -> dict[str, Any]:
    """Extract Sharpe, max-drawdown and raw series from the portfolio analyzer."""
    result: dict[str, Any] = {
        "sharpe": None,
        "max_dd": None,
        "stats_returns": None,
        "stats_pnls": None,
        "stats_general": None,
        "returns_series": None,
        "realized_pnls_series": None,
    }
    try:
        analyzer = engine.portfolio.analyzer
        stats_returns = analyzer.get_performance_stats_returns()
        result["stats_returns"] = stats_returns
        if stats_returns:
            raw = stats_returns.get("Sharpe Ratio (252 days)", 0) or 0
            v = float(raw)
            result["sharpe"] = v if not math.isnan(v) else None

        stats_pnls = analyzer.get_performance_stats_pnls()
        result["stats_pnls"] = stats_pnls
        if stats_pnls:
            dd = stats_pnls.get("Max Drawdown %") or stats_pnls.get("Max Drawdown")
            if dd is not None:
                v = float(dd)
                normalized = normalize_drawdown_pct(v if not math.isnan(v) else None)
                result["max_dd"] = normalized

        if hasattr(analyzer, "get_performance_stats_general"):
            result["stats_general"] = analyzer.get_performance_stats_general()

        if hasattr(analyzer, "returns"):
            result["returns_series"] = analyzer.returns()

        if hasattr(analyzer, "realized_pnls"):
            rp = analyzer.realized_pnls(USD)
            result["realized_pnls_series"] = rp if rp is not None and len(rp) > 0 else None

        # Fallback max-drawdown from returns series
        if (
            result["max_dd"] is None
            and result["returns_series"] is not None
            and len(result["returns_series"]) > 0
        ):
            try:
                cum = (1 + result["returns_series"]).cumprod()
                peak = cum.cummax()
                dd_pct = (peak - cum) / peak.replace(0, 1) * 100
                result["max_dd"] = normalize_drawdown_pct(
                    float(dd_pct.max()) if not dd_pct.empty else None
                )
            except _PNL_PARSE_ERRORS as e:
                logger.debug("Failed to compute max drawdown from returns series: %s", e)
    except _ANALYZER_ERRORS as e:
        logger.warning("Failed to extract performance stats from Nautilus analyzer: %s", e)
    return result


def _build_result(
    run_id: str,
    strategy_name: str,
    symbols_echo: list[str],
    symbol: str,
    start_ts: int,
    end_ts: int,
    total_pnl: float,
    total_return_pct: float,
    num_trades: int,
    perf: dict[str, Any],
) -> BacktestResult:
    """Assemble BacktestResult from extracted metrics."""

    def _ns_to_iso(ns: int) -> str:
        return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _safe_float(x: float | None) -> float | None:
        return None if (x is None or math.isnan(x)) else x

    return BacktestResult(
        run_id=run_id,
        strategy_name=strategy_name,
        symbols=symbols_echo or [symbol],
        start_time=_ns_to_iso(start_ts),
        end_time=_ns_to_iso(end_ts),
        total_pnl=_safe_float(total_pnl) or 0.0,
        total_return_pct=_safe_float(total_return_pct) or 0.0,
        sharpe_ratio=perf["sharpe"],
        max_drawdown_pct=normalize_drawdown_pct(perf["max_dd"]),
        num_trades=num_trades,
        status="ok",
        message=f"Backtest on user OHLCV data ({symbol}).",
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _run_backtest_ohlcv(
    ohlcv_df: pl.DataFrame,
    symbol: str,
    strategy_name: str,
    symbols_echo: list[str],
    tearsheet_path: str | Path | None = None,
    strategy_params: dict | None = None,
    full_tearsheet: bool = True,
) -> BacktestResult | None:
    """Run Nautilus backtest on OHLCV bar data."""
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

    venue_name = "SIM"
    prepared = _prepare_bar_data(
        ohlcv_df, symbol, venue_name, BarType, BarDataWrangler, TestInstrumentProvider
    )
    if prepared is None:
        return None
    inst, bar_type, bars, _pd_df = prepared

    engine = _build_engine(
        inst=inst,
        bars=bars,
        bar_type=bar_type,
        strategy_name=strategy_name,
        strategy_params=strategy_params,
        venue_name=venue_name,
        BacktestEngine=BacktestEngine,
        Venue=Venue,
        OmsType=OmsType,
        AccountType=AccountType,
        USD=USD,
        Money=Money,
        get_strategy=get_strategy,
    )

    run_id = f"nautilus-{uuid.uuid4().hex[:8]}"
    fills = engine.trader.generate_order_fills_report()
    num_trades = len(fills) if fills is not None else 0
    account_report = engine.trader.generate_account_report(Venue(venue_name))
    start_ts = bars[0].ts_init
    end_ts = bars[-1].ts_init

    total_pnl, total_return_pct = _extract_pnl(account_report)
    perf = _extract_perf_stats(engine, USD)

    engine.dispose()

    bt_result = _build_result(
        run_id=run_id,
        strategy_name=strategy_name,
        symbols_echo=symbols_echo,
        symbol=symbol,
        start_ts=start_ts,
        end_ts=end_ts,
        total_pnl=total_pnl,
        total_return_pct=total_return_pct,
        num_trades=num_trades,
        perf=perf,
    )

    if tearsheet_path is not None:
        try:
            from digiquant.tearsheet import create_tearsheet as create_digi_tearsheet

            out = _resolve_tearsheet_output(tearsheet_path)
            create_digi_tearsheet(
                result=bt_result,
                output_path=out,
                strategy_params=strategy_params,
                account_report=account_report,
                fills_report=fills,
                ohlcv_df=ohlcv_df,
                symbol=symbol,
                stats_returns=perf["stats_returns"],
                stats_pnls=perf["stats_pnls"],
                stats_general=perf["stats_general"],
                returns_series=perf["returns_series"],
                realized_pnls_series=perf["realized_pnls_series"],
                full=full_tearsheet,
            )
        except _TEARSHEET_ERRORS as exc:
            logger.warning("tearsheet skipped for %s: %s", tearsheet_path, exc)

    return bt_result


def _run_multi_symbol_backtest(
    symbol_dfs: dict[str, pl.DataFrame],
    strategy_name: str,
    symbols: list[str],
    tearsheet_path: str | Path | None = None,
    strategy_params: dict | None = None,
    full_tearsheet: bool = True,
) -> BacktestResult | None:
    """Run one backtest per symbol and aggregate results.

    Returns a combined BacktestResult with:
    - total_pnl / total_return_pct as averages across symbols
    - sharpe_ratio as the average Sharpe
    - per_symbol_pnl dict keyed by symbol
    """
    per_symbol_pnl: dict[str, float] = {}
    per_symbol_return: dict[str, float] = {}
    per_symbol_sharpe: dict[str, float] = {}
    num_trades_total = 0
    combined_run_id = f"multi-{uuid.uuid4().hex[:8]}"
    start_time: str | None = None
    end_time: str | None = None

    for sym, df in symbol_dfs.items():
        result = _run_backtest_ohlcv(
            ohlcv_df=df,
            symbol=sym,
            strategy_name=strategy_name,
            symbols_echo=[sym],
            tearsheet_path=None,  # Tearsheet written once after aggregation
            strategy_params=strategy_params,
            full_tearsheet=False,
        )
        if result is None:
            logger.warning("Multi-symbol: backtest returned None for symbol %s — skipping", sym)
            continue
        per_symbol_pnl[sym] = result.total_pnl
        per_symbol_return[sym] = result.total_return_pct
        if result.sharpe_ratio is not None:
            per_symbol_sharpe[sym] = result.sharpe_ratio
        num_trades_total += result.num_trades
        if start_time is None or result.start_time < start_time:
            start_time = result.start_time
        if end_time is None or result.end_time > end_time:
            end_time = result.end_time

    if not per_symbol_pnl:
        return None

    n = len(per_symbol_pnl)
    avg_pnl = sum(per_symbol_pnl.values()) / n
    avg_return = sum(per_symbol_return.values()) / n
    avg_sharpe = (
        (sum(per_symbol_sharpe.values()) / len(per_symbol_sharpe)) if per_symbol_sharpe else None
    )

    bt_result = BacktestResult(
        run_id=combined_run_id,
        strategy_name=strategy_name,
        symbols=symbols,
        start_time=start_time or "",
        end_time=end_time or "",
        total_pnl=round(avg_pnl, 4),
        total_return_pct=round(avg_return, 4),
        sharpe_ratio=round(avg_sharpe, 4) if avg_sharpe is not None else None,
        max_drawdown_pct=None,
        num_trades=num_trades_total,
        per_symbol_pnl={k: round(v, 4) for k, v in per_symbol_pnl.items()},
        status="ok",
        message=f"Multi-symbol backtest across {n} symbol(s): {', '.join(per_symbol_pnl)}.",
    )

    if tearsheet_path is not None:
        logger.info(
            "Multi-symbol tearsheet not yet supported — tearsheet skipped. "
            "Set tearsheet_path=None or run single-symbol to generate HTML."
        )

    return bt_result


def run_nautilus_backtest(
    strategy_name: str,
    symbols: list[str],
    data_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    tearsheet_path: str | Path | None = None,
    strategy_params: dict | None = None,
    full_tearsheet: bool = True,
) -> BacktestResult | None:
    """
    Run NautilusTrader backtest on user OHLCV data.
    Requires data_path (single CSV) or data_dir + symbols. Returns None if data unavailable
    or nautilus_trader not installed.

    Multi-symbol: when data_dir + multiple symbols are given and all CSVs are found,
    runs one backtest per symbol and aggregates results with per_symbol_pnl breakdown.
    """
    # Multi-symbol path: data_dir with more than one symbol
    if data_path is None and data_dir is not None and symbols and len(symbols) > 1:
        all_dfs = _load_all_ohlcv_for_backtest(data_dir, symbols)
        if len(all_dfs) > 1:
            return _run_multi_symbol_backtest(
                symbol_dfs=all_dfs,
                strategy_name=strategy_name,
                symbols=symbols,
                tearsheet_path=tearsheet_path,
                strategy_params=strategy_params,
                full_tearsheet=full_tearsheet,
            )

    # Single-symbol path (original behaviour)
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
        full_tearsheet=full_tearsheet,
    )
