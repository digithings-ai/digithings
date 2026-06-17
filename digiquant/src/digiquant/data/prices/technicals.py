"""Pure-Polars technical indicator computation.

Ported from ``digiquant/scripts/atlas/compute-technicals.py``. The original
implementation delegated to ``pandas_ta``; this module reimplements every
indicator using Polars expressions so we can keep the CLAUDE.md "Polars only"
invariant.

Indicator reference (matches first-principles Wilder / EMA / SMA references
within 1e-6 on a deterministic 60-row fixture — see
``tests/dq/data/test_technicals.py``). The implementation follows the same
formulas pandas_ta 0.3.x uses, but we do not run a live pandas_ta parity
check; callers needing bit-for-bit parity with a specific pandas_ta release
should add a dedicated comparison fixture.

* **Trend** — SMA(20, 50, 200), EMA(12, 26, 50), pct vs each SMA.
* **Trend strength** — ADX(14), +DI/-DI via Wilder smoothing.
* **Momentum** — RSI(7, 14, 21) via Wilder smoothing, MACD(12, 26, 9), ROC(5, 10, 21).
* **Volatility** — ATR(14) Wilder, ATR %, Bollinger(20, 2), 21-day log-return vol.
* **Mean reversion** — Stochastic %K(14, 3)/%D(3), Z-score vs SMA50 and SMA200.

The public entry point is :func:`compute_indicators`. Input is any Polars
DataFrame with columns ``open / high / low / close / volume`` (case-insensitive)
sorted ascending by date. Output has one row per input row with the full
indicator column set defined in :data:`digiquant.data.prices.TECHNICAL_COLUMNS`.
"""

from __future__ import annotations

import logging
import math

import polars as pl

from digiquant.data.prices import TECHNICAL_COLUMNS
from digiquant.data.prices._utils import filter_rows_by_trading_days

MIN_BARS = 30
_TRADING_DAYS_YEAR = 252

_logger = logging.getLogger(__name__)


# ─── Low-level primitives ───────────────────────────────────────────────────


def _sma(col: str, length: int) -> pl.Expr:
    return pl.col(col).rolling_mean(window_size=length, min_periods=length)


def _ema(col: str, length: int, adjust: bool = False) -> pl.Expr:
    # pandas_ta uses pandas' `ewm(span=length, adjust=False)` — Polars matches
    # via ewm_mean with `alpha = 2/(length+1)` and `adjust=False`.
    return pl.col(col).ewm_mean(span=length, adjust=adjust, min_periods=length)


def _wilder_ema(expr: pl.Expr, length: int) -> pl.Expr:
    """Wilder (RMA) smoothing: alpha = 1/length, adjust=False."""
    return expr.ewm_mean(alpha=1.0 / length, adjust=False, min_periods=length)


def _rsi(col: str, length: int) -> pl.Expr:
    delta = pl.col(col).diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
    avg_gain = _wilder_ema(gain, length)
    avg_loss = _wilder_ema(loss, length)
    rs = avg_gain / avg_loss
    return (100.0 - (100.0 / (1.0 + rs))).alias(f"rsi_{length}")


def _true_range() -> pl.Expr:
    prev_close = pl.col("close").shift(1)
    hl = pl.col("high") - pl.col("low")
    hc = (pl.col("high") - prev_close).abs()
    lc = (pl.col("low") - prev_close).abs()
    return pl.max_horizontal(hl, hc, lc)


def _atr(length: int) -> pl.Expr:
    return _wilder_ema(_true_range(), length).alias(f"atr_{length}")


def _rolling_std(col: str, length: int, ddof: int = 0) -> pl.Expr:
    return pl.col(col).rolling_std(window_size=length, min_periods=length, ddof=ddof)


# ─── Full indicator pipeline ────────────────────────────────────────────────


def _normalize(df: pl.DataFrame) -> pl.DataFrame:
    """Lowercase column names and ensure required OHLC columns are Float64."""
    rename = {c: c.lower() for c in df.columns if c != c.lower()}
    if rename:
        df = df.rename(rename)
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"OHLC columns missing: {missing}. Got: {df.columns}")
    # Cast to Float64 for safe arithmetic; volume may be Int.
    casts = {c: pl.Float64 for c in ("open", "high", "low", "close") if df.schema[c] != pl.Float64}
    if casts:
        df = df.with_columns([pl.col(c).cast(t) for c, t in casts.items()])
    return df


def compute_indicators(
    df: pl.DataFrame,
    trading_days: pl.Series | None = None,
) -> pl.DataFrame:
    """Compute all technical indicators defined in :data:`TECHNICAL_COLUMNS`.

    Parameters
    ----------
    df : pl.DataFrame
        OHLC(V) Polars frame sorted by date ascending. Must contain
        ``open``, ``high``, ``low``, ``close`` (case-insensitive).
        The date column should be named ``timestamp``.
    trading_days : pl.Series | None
        Optional filter: a Series of :class:`datetime.date` values representing
        valid trading days. When provided, rows whose ``timestamp`` column value
        is not in ``trading_days`` are dropped *before* computation, so
        indicators are only computed on real market sessions.

        Graceful fallback: if ``trading_days`` is provided but empty, a warning
        is logged and all rows are retained unchanged.

    Returns
    -------
    pl.DataFrame
        Same length as (filtered) input; columns = ``TECHNICAL_COLUMNS``.
        NaN/null in leading rows where insufficient history exists.
    """
    if trading_days is not None:
        if len(trading_days) == 0:
            _logger.warning("trading_days filter is empty — computing technicals on all rows")
        elif "timestamp" in df.columns:
            df = filter_rows_by_trading_days(df, trading_days)
        else:
            _logger.warning(
                "trading_days provided but DataFrame has no 'timestamp' column — "
                "skipping filter and computing technicals on all rows"
            )

    if df.is_empty():
        return pl.DataFrame({c: pl.Series(c, [], dtype=pl.Float64) for c in TECHNICAL_COLUMNS})

    df = _normalize(df)

    # ── Moving averages & EMAs ──────────────────────────────────────────
    ma_exprs = [
        _sma("close", 20).alias("sma_20"),
        _sma("close", 50).alias("sma_50"),
        _sma("close", 200).alias("sma_200"),
        _ema("close", 12).alias("ema_12"),
        _ema("close", 26).alias("ema_26"),
        _ema("close", 50).alias("ema_50"),
    ]
    with_ma = df.with_columns(ma_exprs)

    pct_exprs = [
        ((pl.col("close") - pl.col("sma_20")) / pl.col("sma_20") * 100).alias("pct_vs_sma20"),
        ((pl.col("close") - pl.col("sma_50")) / pl.col("sma_50") * 100).alias("pct_vs_sma50"),
        ((pl.col("close") - pl.col("sma_200")) / pl.col("sma_200") * 100).alias("pct_vs_sma200"),
    ]

    # ── ADX / DMI (Wilder 14) ───────────────────────────────────────────
    # +DM = max(high - prev_high, 0) if (high - prev_high) > (prev_low - low), else 0
    # -DM = max(prev_low - low, 0) if (prev_low - low) > (high - prev_high), else 0
    up = pl.col("high") - pl.col("high").shift(1)
    down = pl.col("low").shift(1) - pl.col("low")
    plus_dm = pl.when((up > down) & (up > 0)).then(up).otherwise(0.0)
    minus_dm = pl.when((down > up) & (down > 0)).then(down).otherwise(0.0)

    # ── MACD ────────────────────────────────────────────────────────────
    macd = pl.col("ema_12") - pl.col("ema_26")
    # Signal line = EMA(MACD, 9) — needs to be computed sequentially.

    # ── RSI (3 lengths) ─────────────────────────────────────────────────
    rsi_exprs = [_rsi("close", n) for n in (7, 14, 21)]

    # ── ROC ─────────────────────────────────────────────────────────────
    roc_exprs = [
        ((pl.col("close") / pl.col("close").shift(n) - 1.0) * 100).alias(f"roc_{n}")
        for n in (5, 10, 21)
    ]

    # ── ATR(14) ─────────────────────────────────────────────────────────
    atr_expr = _atr(14)

    # ── Bollinger(20, 2) — ddof=0 matches pandas_ta default ─────────────
    bb_mid = _sma("close", 20)
    bb_std = _rolling_std("close", 20, ddof=0)

    # ── Historical vol: 21-day stdev of log returns, annualized ──────────
    log_ret = (pl.col("close") / pl.col("close").shift(1)).log()

    # ── Stochastic %K/%D(14, 3, 3) ─────────────────────────────────────
    lowest_low = pl.col("low").rolling_min(window_size=14, min_periods=14)
    highest_high = pl.col("high").rolling_max(window_size=14, min_periods=14)
    raw_k = (pl.col("close") - lowest_low) / (highest_high - lowest_low) * 100
    # pandas_ta.stoch smooths raw %K by 3-period SMA → STOCHk, then %D = SMA(STOCHk, 3).

    # ── Z-score vs SMA50 / SMA200 ─────────────────────────────────────
    std_50 = _rolling_std("close", 50, ddof=1)
    std_200 = _rolling_std("close", 200, ddof=1)

    # Assemble pass 1: independent columns.
    out = with_ma.with_columns(
        pct_exprs
        + [
            plus_dm.alias("_plus_dm"),
            minus_dm.alias("_minus_dm"),
            _true_range().alias("_tr"),
            macd.alias("macd"),
        ]
        + rsi_exprs
        + roc_exprs
        + [
            atr_expr,
            bb_mid.alias("_bb_mid"),
            bb_std.alias("_bb_std"),
            log_ret.alias("_log_ret"),
            raw_k.alias("_raw_k"),
            std_50.alias("_std_50"),
            std_200.alias("_std_200"),
        ]
    )

    # Pass 2: Wilder-smoothed DMI + ATR-for-DMI + MACD signal + stochastic %K/%D.
    out = out.with_columns(
        [
            _wilder_ema(pl.col("_plus_dm"), 14).alias("_plus_dm_smooth"),
            _wilder_ema(pl.col("_minus_dm"), 14).alias("_minus_dm_smooth"),
            _wilder_ema(pl.col("_tr"), 14).alias("_tr_smooth"),
            pl.col("macd").ewm_mean(span=9, adjust=False, min_periods=9).alias("macd_signal"),
            pl.col("_raw_k").rolling_mean(window_size=3, min_periods=3).alias("stoch_k"),
        ]
    )

    out = out.with_columns(
        [
            (pl.col("_plus_dm_smooth") / pl.col("_tr_smooth") * 100).alias("dmi_plus"),
            (pl.col("_minus_dm_smooth") / pl.col("_tr_smooth") * 100).alias("dmi_minus"),
            pl.col("stoch_k").rolling_mean(window_size=3, min_periods=3).alias("stoch_d"),
            (pl.col("macd") - pl.col("macd_signal")).alias("macd_hist"),
            (pl.col("atr_14") / pl.col("close") * 100).alias("atr_pct"),
            (pl.col("_bb_mid") + 2.0 * pl.col("_bb_std")).alias("bb_upper"),
            (pl.col("_bb_mid") - 2.0 * pl.col("_bb_std")).alias("bb_lower"),
            (
                pl.col("_log_ret").rolling_std(window_size=21, min_periods=21, ddof=1)
                * math.sqrt(_TRADING_DAYS_YEAR)
                * 100
            ).alias("hist_vol_21"),
            ((pl.col("close") - pl.col("sma_50")) / pl.col("_std_50")).alias("zscore_50"),
            ((pl.col("close") - pl.col("sma_200")) / pl.col("_std_200")).alias("zscore_200"),
        ]
    )

    # ADX: Wilder EMA of DX over 14 periods. DX = 100*|+DI - -DI|/(+DI + -DI).
    out = out.with_columns(
        (
            (pl.col("dmi_plus") - pl.col("dmi_minus")).abs()
            / (pl.col("dmi_plus") + pl.col("dmi_minus"))
            * 100.0
        ).alias("_dx")
    )
    out = out.with_columns(
        _wilder_ema(pl.col("_dx"), 14).alias("adx_14"),
    )

    # Bollinger %B and bandwidth.
    out = out.with_columns(
        [
            (
                (pl.col("close") - pl.col("bb_lower")) / (pl.col("bb_upper") - pl.col("bb_lower"))
            ).alias("bb_pct_b"),
            ((pl.col("bb_upper") - pl.col("bb_lower")) / pl.col("_bb_mid") * 100.0).alias(
                "bb_bandwidth"
            ),
        ]
    )

    # Project to just the indicator columns (preserving original ordering).
    # Defensive invariant: no intermediate ``_``-prefixed column may appear
    # in TECHNICAL_COLUMNS. If this ever fires, the contract between this
    # module and `digiquant.data.prices.TECHNICAL_COLUMNS` has drifted.
    assert not any(c.startswith("_") for c in TECHNICAL_COLUMNS), (
        "TECHNICAL_COLUMNS must not contain intermediate '_'-prefixed names"
    )
    return out.select([pl.col(c) for c in TECHNICAL_COLUMNS])


__all__ = [
    "MIN_BARS",
    "TECHNICAL_COLUMNS",
    "compute_indicators",
]
