"""
Run a real NautilusTrader backtest when nautilus_trader is installed.
Requires user OHLCV data via data_path or data_dir. No fallback; backtest fails if data unavailable.

Internal structure
------------------
_prepare_bar_data      — Polars OHLCV -> pandas + Nautilus BarType + bars list
_build_engine          — configure BacktestEngine with venue/instrument/data/strategy
_account_balance_path  — whole account report -> (balance series, timestamps)
_balance_path_metrics  — Sharpe + max drawdown from that balance series
_extract_pnl           — parse account report -> (total_pnl, total_return_pct)
_extract_perf_stats    — balance-path Sharpe/drawdown + verified returns series
_build_result          — assemble BacktestResult from raw engine outputs
_run_backtest_ohlcv    — orchestrates the above; writes tearsheet if requested

Sharpe and max drawdown come from the account-report balance path, NOT from the
portfolio analyzer: ``analyzer.returns()`` holds one observation per *closed
position*, so annualising it by 252 trading days produced numbers like -76 Sharpe
and -76% drawdown next to a -3.1% total return. The balance path already in hand
is the equity curve, and deriving all three metrics from it makes them mutually
consistent by construction.

The returns *series* the tearsheet charts are read from that same alias, so it is
verified rather than trusted: ``_verified_returns_series`` only publishes it when it
matches ``analyzer.portfolio_returns()``, and withholds it otherwise. See that
function for why the alias cannot be believed on its own.
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

# Balance columns in precedence order: first column present with a non-null cell wins.
BALANCE_COLUMNS = ("total", "balance", "equity")

# Timestamp column names to look for after pl.from_pandas() has folded a *named*
# pandas index into a column. The Nautilus account report index is unnamed, so this
# is a runtime fallback, never an assumption.
_ACCOUNT_TIMESTAMP_COLUMNS = ("ts_event", "timestamp", "index")

# 365.25 days in seconds — the year length used to annualise the balance path.
_YEAR_SECONDS = 365.25 * 86400.0

# Marker appended to ``missing`` when ``analyzer.returns()`` cannot be confirmed to be
# the portfolio return series. Tracked separately from the metric markers because a
# missing *chart* series must not cost a symbol its place in a multi-symbol aggregate
# (see _degraded_symbol_reason): the aggregates use no series at all.
RETURNS_SERIES_MISSING = "returns_series"

# Marker prefix for the per-symbol accounting inside a multi-symbol aggregate, matching
# the existing "sharpe_ratio (k/n symbols)" wording already emitted by that function.
RETURNS_SERIES_MISSING_SYMBOLS = f"{RETURNS_SERIES_MISSING} ("

# Elementwise tolerance for the alias-vs-portfolio comparison. The two series are the
# same objects when the alias is in sync, so the only differences seen in practice are
# float round-trips; anything larger than this is a genuinely different series.
_SERIES_MATCH_TOLERANCE = 1e-12

# Default position size, as a fraction of starting balance, expressed in notional.
# trade_size (units) = floor(STARTING_BALANCE_USD * fraction / first_price), min 1.
# Notional-based so a fixed unit count doesn't over-leverage high-priced instruments
# (e.g. 1000 BTC units on a $1M account is ~10-100x leverage and halts the run with
# AccountBalanceNegative after a handful of bars). 2% of $1M ≈ 1 BTC at ~$13.6k, a
# size known to complete the full BTC-USD run.
DEFAULT_NOTIONAL_FRACTION = 0.02

# Drawdown invariant, stated for tests and reviewers. Given a balance path that
# starts at STARTING_BALANCE_USD, the worst peak-to-trough fall can never be milder
# than the end-state loss: |dd| <= |total_return_pct| whenever the peak IS the
# starting balance (the path never rose above its start), and in the general case
# the weaker but unconditional bound is dd <= total_return_pct.
#
# The CTO brief proposed |dd| <= |total_return_pct| unconditionally. That is false
# for its own golden AAPL row (max_dd -5.11 against total_return_pct -3.10): once the
# account trades up, the peak exceeds the start and the trough-to-peak fall is
# legitimately larger than the start-to-end loss. The unconditional bound used in
# the regression tests is dd <= total_return_pct, which still forbids the original
# -76.53% drawdown beside a -3.10% return.
DRAWDOWN_NOT_MILDER_THAN_END_LOSS = "dd <= total_return_pct"


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


def _to_float(value: Any) -> float | None:
    """Parse one account-report cell into a float, or ``None`` when unusable.

    Nautilus emits the account total either as a number or as ``"1000000.00 USD"``;
    a leading ``1.05e6 USD`` form is also accepted.
    """
    if value is None:
        return None
    if isinstance(value, str):
        parts = value.strip().split()
        if not parts:
            return None
        try:
            return float(parts[0])
        except ValueError:
            return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def _account_timestamps(account_report: Any, df: pl.DataFrame) -> list[float] | None:
    """Epoch seconds for each report row, or ``None`` when no usable index exists.

    ``pl.from_pandas`` keeps a *named* pandas index as a column and drops an unnamed
    one. The Nautilus account report index is unnamed, so the fallback reads the
    pandas index directly rather than guessing a column name.
    """
    index = getattr(account_report, "index", None)
    index_name = getattr(index, "name", None)
    values: list[Any] | None = None
    if isinstance(index_name, str) and index_name in df.columns:
        values = df.get_column(index_name).to_list()
    elif index is not None and len(index) == df.height:
        values = list(index)
    else:
        for candidate in _ACCOUNT_TIMESTAMP_COLUMNS:
            if candidate in df.columns:
                values = df.get_column(candidate).to_list()
                break
    if values is None:
        return None
    seconds: list[float] = []
    for value in values:
        if isinstance(value, datetime):
            # Naive timestamps are read as UTC; only differences are used downstream.
            seconds.append(
                (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
            )
        elif isinstance(value, bool):
            return None
        elif isinstance(value, int | float) and not math.isnan(float(value)):
            # A bare RangeIndex carries no elapsed time: annualising on it is wrong.
            return None
        else:
            return None
    return seconds


def _account_balance_path(account_report: Any) -> tuple[list[float], list[float] | None]:
    """Read the *whole* account-report balance path: ``(balances, epoch_seconds)``.

    ``epoch_seconds`` is ``None`` when the report carries no usable timestamps, which
    leaves the annualised Sharpe ``None`` while still allowing max drawdown. Rows
    whose balance cell cannot be parsed are dropped from both lists.
    """
    if account_report is None:
        return [], None
    try:
        df = pl.from_pandas(account_report)
    except _PNL_PARSE_ERRORS:
        return [], None
    column = next((name for name in BALANCE_COLUMNS if name in df.columns), None)
    if column is None:
        return [], None
    stamps = _account_timestamps(account_report, df)
    balances: list[float] = []
    seconds: list[float] = []
    for row, cell in enumerate(df.get_column(column).to_list()):
        value = _to_float(cell)
        if value is None:
            continue
        balances.append(value)
        if stamps is not None and row < len(stamps):
            seconds.append(stamps[row])
    if not balances:
        return [], None
    if stamps is None or len(seconds) != len(balances):
        return balances, None
    return balances, seconds


def _sharpe_from_balance_path(balances: list[float], seconds: list[float] | None) -> float | None:
    """Annualised Sharpe of the balance path, risk-free rate 0.

    ``mean(returns) / stdev(returns) * sqrt(n_returns / years)``. The scaler is the
    observation count over elapsed years and deliberately *not* ``sqrt(252)``: the
    balance path has one observation per fill, so it is irregular in time and a
    trading-day scaler would misstate it by an order of magnitude.

    Returns ``None`` whenever the value is undefined — fewer than two returns, no
    timestamps, non-positive elapsed time, or zero dispersion — instead of a
    fabricated 0.0.
    """
    if seconds is None or len(balances) < 3:
        return None
    returns: list[float] = []
    for previous, current in zip(balances, balances[1:]):
        if previous == 0:
            return None
        returns.append((current - previous) / previous)
    years = (seconds[-1] - seconds[0]) / _YEAR_SECONDS
    if years <= 0:
        return None
    mean = sum(returns) / len(returns)
    # Sample standard deviation (ddof=1), matching the convention the golden values
    # were measured with.
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    if variance <= 0:
        return None
    return mean / math.sqrt(variance) * math.sqrt(len(returns) / years)


def _max_drawdown_from_balance_path(balances: list[float]) -> float | None:
    """Worst peak-to-trough fall of the balance path as a negative percent.

    ``min((bal - cummax(bal)) / cummax(bal)) * 100``. ``None`` only when there is no
    balance path at all; a flat or single-row path legitimately draws down 0.0.
    """
    if not balances:
        return None
    peak = balances[0]
    worst = 0.0
    for value in balances:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value - peak) / peak)
    return normalize_drawdown_pct(worst * 100.0)


def _balance_path_metrics(account_report: Any) -> dict[str, float | None]:
    """Sharpe and max drawdown derived from the account-report balance path.

    The single source of truth for both metrics, so ``total_return_pct`` (the change
    of the final balance), ``max_drawdown_pct`` and ``sharpe_ratio`` cannot disagree.
    """
    balances, seconds = _account_balance_path(account_report)
    return {
        "sharpe": _sharpe_from_balance_path(balances, seconds),
        "max_dd": _max_drawdown_from_balance_path(balances),
    }


def _extract_pnl(account_report: Any, errors: list[str] | None = None) -> tuple[float, float]:
    """Parse Nautilus account report -> (total_pnl, total_return_pct).

    Reads the final balance only; ``_balance_path_metrics`` derives Sharpe and max
    drawdown from the same series. Returns (0.0, 0.0) when the report cannot be
    parsed. Any failure message is appended to ``errors`` so callers can surface an
    error status rather than a fabricated zero-PnL success.
    """

    def _fail(msg: str) -> tuple[float, float]:
        logger.warning(msg)
        if errors is not None:
            errors.append(msg)
        return 0.0, 0.0

    if account_report is None:
        return _fail("PnL extraction failed: account report unavailable")
    try:
        df = pl.from_pandas(account_report)
        if df.height == 0:
            return _fail("PnL extraction failed: account report is empty")
        last_row = df.row(-1, named=True)
        initial = STARTING_BALANCE_USD
        final_balance = None
        for col_name in BALANCE_COLUMNS:
            if col_name in last_row and last_row[col_name] is not None:
                final_balance = _to_float(last_row[col_name])
                break
        if final_balance is None:
            return _fail(
                "PnL extraction failed: no usable balance column in %s" % list(last_row.keys())
            )
        total_pnl = final_balance - initial
        return total_pnl, (total_pnl / initial) * 100.0
    except _PNL_PARSE_ERRORS as e:
        return _fail(f"PnL extraction failed: {e}")


def _series_is_portfolio_returns(alias: Any, portfolio: Any) -> bool:
    """True only when ``alias`` *is* the portfolio series, value for value.

    Length alone proves nothing: a per-position series can match the portfolio one
    in length by coincidence. Index and dtype are ignored on purpose — only the
    ordered values decide what the charts would draw.
    """
    if alias is None or portfolio is None:
        return False
    try:
        if len(alias) == 0 or len(alias) != len(portfolio):
            return False
        left = [float(v) for v in alias]
        right = [float(v) for v in portfolio]
    except (TypeError, ValueError):
        return False
    for a, b in zip(left, right):
        if math.isnan(a) and math.isnan(b):
            continue
        if abs(a - b) > _SERIES_MATCH_TOLERANCE:
            return False
    return True


def _verified_returns_series(analyzer: Any) -> tuple[Any, str | None]:
    """The analyzer returns series worth publishing, and why it was withheld.

    ``analyzer.returns()`` is an *alias*, not the portfolio series. Where Nautilus
    exposes ``_sync_returns_alias``, it repoints ``_returns`` at the portfolio
    returns when those are non-empty and otherwise at the per-position returns —
    silently, with no warning. DigiQuant never calls ``analyze_statistics``, so the
    portfolio series is populated only by Nautilus' own post-run venue loop, and it
    is empty whenever ``_calculate_portfolio_returns`` sees fewer than two account
    state events, more than one balance currency on any event, a currency change
    between events, or fewer than two distinct calendar days of balance data.

    Publishing the fallback is how ``charts/equity.py`` came to compound a
    per-position series as ``(1 + r).cum_prod() * initial_balance`` under a
    ``Daily Equity`` label: roughly -78% compounded next to a real final balance of
    968,989.60 on 1,000,000. So the alias is compared against
    ``portfolio_returns()`` and anything that cannot be confirmed is withheld.

    Three separate ways to fail, all refused, because all three leave the alias
    indistinguishable from a per-position series: no ``portfolio_returns`` to
    compare against (nautilus_trader below the release that added it — including
    the 1.223.0 pin), an empty portfolio series (the silent fallback), or values
    that differ. Building a correct daily series instead is DIG-1834's job; here a
    blank chart is honest and a wrong curve is not.
    """
    if not hasattr(analyzer, "portfolio_returns"):
        return None, (
            f"analyzer has no portfolio_returns() to confirm the alias against "
            f"(nautilus_trader {getattr(analyzer, '__class__', type(analyzer)).__module__})"
        )
    try:
        portfolio = analyzer.portfolio_returns()
    except _ANALYZER_ERRORS as e:
        return None, f"portfolio_returns() failed: {e}"
    if portfolio is None or len(portfolio) == 0:
        return None, "portfolio_returns() is empty, so returns() is the per-position fallback"
    alias = analyzer.returns()
    if not _series_is_portfolio_returns(alias, portfolio):
        return None, (
            f"returns() has {0 if alias is None else len(alias)} values against "
            f"{len(portfolio)} in portfolio_returns() and does not match them"
        )
    return alias, None


def _extract_perf_stats(
    engine: Any,
    USD: Any,
    account_report: Any = None,
) -> dict[str, Any]:
    """Sharpe and max drawdown from the balance path, series only when verified.

    ``sharpe`` and ``max_dd`` are derived from ``account_report``'s balance path by
    ``_balance_path_metrics``. The analyzer is read for the series the tearsheet
    renders, but never for a metric: its returns are per closed position, not an
    equity curve.

    ``returns_series`` is published only when ``_verified_returns_series`` can
    confirm it against ``analyzer.portfolio_returns()``. An alias that cannot be
    confirmed is withheld rather than drawn, and ``RETURNS_SERIES_MISSING`` is
    appended to ``missing`` so the result lands ``partial`` instead of advertising a
    chart it cannot stand behind.

    ``errors`` records analyzer/parse failures and ``missing`` names metrics that
    remained ``None``, so callers can mark a result ``partial`` instead of
    presenting fabricated ``ok`` metrics.
    """
    result: dict[str, Any] = {
        "sharpe": None,
        "max_dd": None,
        "stats_returns": None,
        "stats_pnls": None,
        "stats_general": None,
        "returns_series": None,
        "realized_pnls_series": None,
        "errors": [],
        "missing": [],
    }
    result.update(_balance_path_metrics(account_report))
    try:
        analyzer = engine.portfolio.analyzer
        result["stats_returns"] = analyzer.get_performance_stats_returns()
        result["stats_pnls"] = analyzer.get_performance_stats_pnls()
        if hasattr(analyzer, "get_performance_stats_general"):
            result["stats_general"] = analyzer.get_performance_stats_general()
        if hasattr(analyzer, "returns"):
            series, refusal = _verified_returns_series(analyzer)
            if series is None:
                logger.warning("Withholding returns series: %s", refusal)
                result["missing"].append(RETURNS_SERIES_MISSING)
            else:
                result["returns_series"] = series
        if hasattr(analyzer, "realized_pnls"):
            rp = analyzer.realized_pnls(USD)
            result["realized_pnls_series"] = rp if rp is not None and len(rp) > 0 else None
    except _ANALYZER_ERRORS as e:
        logger.warning("Failed to extract performance stats from Nautilus analyzer: %s", e)
        result["errors"].append(f"performance stats unavailable: {e}")

    if result["sharpe"] is None:
        result["missing"].append("sharpe_ratio")
    if result["max_dd"] is None:
        result["missing"].append("max_drawdown_pct")
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
    *,
    errors: list[str] | None = None,
    missing: list[str] | None = None,
    warnings: list[str] | None = None,
) -> BacktestResult:
    """Assemble BacktestResult from extracted metrics.

    ``errors`` are fatal extraction failures (``status="error"``); ``missing``
    names absent metrics and ``warnings`` records non-fatal analyzer errors
    (``status="partial"``). A result is only ``ok`` when every metric was
    extracted cleanly.
    """

    def _ns_to_iso(ns: int) -> str:
        return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _safe_float(x: float | None) -> float | None:
        return None if (x is None or math.isnan(x)) else x

    errors = list(errors or [])
    missing = list(missing if missing is not None else perf.get("missing") or [])
    warnings = list(warnings if warnings is not None else perf.get("errors") or [])
    if errors:
        status = "error"
        detail = "; ".join(errors)
        if warnings:
            detail += f"; analyzer warnings: {'; '.join(warnings)}"
        message = f"Backtest on user OHLCV data ({symbol}) — metric extraction failed: {detail}."
    elif missing or warnings:
        status = "partial"
        parts = []
        if warnings:
            parts.append(f"analyzer warnings: {'; '.join(warnings)}")
        if missing:
            parts.append(f"missing metrics: {', '.join(missing)}")
        message = f"Backtest on user OHLCV data ({symbol}) — {'; '.join(parts)}."
    else:
        status = "ok"
        message = f"Backtest on user OHLCV data ({symbol})."

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
        missing=missing,
        status=status,
        message=message,
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
        from nautilus_trader.model import BarType, Venue
        from nautilus_trader.model.currencies import USD
        from nautilus_trader.model.enums import AccountType, OmsType
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

    pnl_errors: list[str] = []
    total_pnl, total_return_pct = _extract_pnl(account_report, errors=pnl_errors)
    perf = _extract_perf_stats(engine, USD, account_report)

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
        errors=pnl_errors,
        missing=perf["missing"],
        warnings=perf["errors"],
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


def _degraded_symbol_reason(result: BacktestResult) -> str | None:
    """Why this symbol cannot be averaged in, or ``None`` when it can be.

    The aggregates use PnL, total return, Sharpe, drawdown and the trade count. A
    withheld returns series is none of those, so a symbol that is ``partial``
    *only* because ``RETURNS_SERIES_MISSING`` is present still has honest numbers to
    contribute and stays in. Excluding it would drop real trades from every average
    to avoid a chart that is not drawn here anyway (multi-symbol tearsheets are
    skipped), and because the refusal fires on every run under the pinned
    nautilus_trader, excluding on it would empty the aggregate entirely.

    Every other reason still excludes: a partial missing a real metric, or any
    error. That is unchanged behaviour.
    """
    if result.status == "ok":
        return None
    if result.status == "partial" and set(result.missing) == {RETURNS_SERIES_MISSING}:
        return None
    return result.status


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
    - sharpe_ratio as the *average* Sharpe (labelled as such in the message)
    - max_drawdown_pct as the worst per-symbol drawdown (never silently nil)
    - per_symbol_pnl dict keyed by symbol

    Symbols whose backtest failed (``None`` or ``status="error"``) are never
    silently averaged in as fabricated zeros; they are named and the result is
    marked ``partial``. A symbol ``partial`` only because its returns series was
    withheld is still averaged in — see ``_degraded_symbol_reason`` — and counted
    under ``missing`` so the reader can see the charts were not drawn.
    """
    per_symbol_pnl: dict[str, float] = {}
    per_symbol_return: dict[str, float] = {}
    per_symbol_sharpe: dict[str, float] = {}
    per_symbol_max_dd: dict[str, float] = {}
    skipped_symbols: list[str] = [s for s in symbols if s not in symbol_dfs]
    degraded_symbols: list[str] = []
    withheld_series_symbols: list[str] = []
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
            skipped_symbols.append(sym)
            continue
        degraded = _degraded_symbol_reason(result)
        if degraded is not None:
            logger.warning(
                "Multi-symbol: backtest status=%s for symbol %s — excluding from aggregates",
                degraded,
                sym,
            )
            degraded_symbols.append(f"{sym} ({degraded})")
            continue
        if RETURNS_SERIES_MISSING in result.missing:
            withheld_series_symbols.append(sym)
        per_symbol_pnl[sym] = result.total_pnl
        per_symbol_return[sym] = result.total_return_pct
        if result.sharpe_ratio is not None:
            per_symbol_sharpe[sym] = result.sharpe_ratio
        if result.max_drawdown_pct is not None:
            per_symbol_max_dd[sym] = result.max_drawdown_pct
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
    worst_dd = min(per_symbol_max_dd.values()) if per_symbol_max_dd else None

    missing: list[str] = []
    if avg_sharpe is None:
        missing.append("sharpe_ratio")
    elif len(per_symbol_sharpe) < n:
        missing.append(f"sharpe_ratio ({len(per_symbol_sharpe)}/{n} symbols)")
    if worst_dd is None:
        missing.append("max_drawdown_pct")
    elif len(per_symbol_max_dd) < n:
        missing.append(f"max_drawdown_pct ({len(per_symbol_max_dd)}/{n} symbols)")
    if withheld_series_symbols:
        missing.append(
            f"{RETURNS_SERIES_MISSING_SYMBOLS}{len(withheld_series_symbols)}/{n} symbols)"
        )

    status = "partial" if (skipped_symbols or degraded_symbols or missing) else "ok"

    message_bits = [f"Multi-symbol backtest across {n} symbol(s): {', '.join(per_symbol_pnl)}."]
    if avg_sharpe is not None:
        message_bits.append(
            f"sharpe_ratio is the average Sharpe across "
            f"{len(per_symbol_sharpe)}/{n} symbols, not a portfolio Sharpe."
        )
    if worst_dd is not None:
        message_bits.append(
            f"max_drawdown_pct is the worst per-symbol drawdown across "
            f"{len(per_symbol_max_dd)}/{n} symbols."
        )
    if missing:
        message_bits.append(f"Missing metrics: {', '.join(missing)}.")
    if skipped_symbols:
        message_bits.append(f"Symbols skipped: {', '.join(skipped_symbols)}.")
    if degraded_symbols:
        message_bits.append(f"Degraded symbols excluded: {', '.join(degraded_symbols)}.")

    bt_result = BacktestResult(
        run_id=combined_run_id,
        strategy_name=strategy_name,
        symbols=symbols,
        start_time=start_time or "",
        end_time=end_time or "",
        total_pnl=round(avg_pnl, 4),
        total_return_pct=round(avg_return, 4),
        sharpe_ratio=round(avg_sharpe, 4) if avg_sharpe is not None else None,
        max_drawdown_pct=normalize_drawdown_pct(worst_dd),
        num_trades=num_trades_total,
        per_symbol_pnl={k: round(v, 4) for k, v in per_symbol_pnl.items()},
        missing=missing,
        status=status,
        message=" ".join(message_bits),
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
