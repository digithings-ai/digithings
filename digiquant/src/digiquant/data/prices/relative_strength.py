"""Sector relative-strength vs a benchmark, derived from raw closes (Pillar 1D).

Relative strength answers "which sectors are *leading* the index?" — the read a
PM needs to rotate. It is the excess return of each sector ETF over SPY across
several lookback windows, plus a cross-sectional rank. Derived from
``price_history`` closes already stored; no new data source. Polars only.

``compute_relative_strength`` is pure (frame in, dict out). The reader that
fetches closes lives in ``olympus/atlas/data/queries.py``.
"""

from __future__ import annotations

from datetime import date
from typing import Any  # noqa  # scored-lint suppression: heterogeneous signal-dict values

import polars as pl


def _window_return(closes: pl.Series, window: int) -> float | None:
    """Total return over ``window`` trading rows: ``close[-1] / close[-1-window] - 1``."""
    n = closes.len()
    if n <= window:
        return None
    last = closes[-1]
    ref = closes[-1 - window]
    if last is None or ref in (None, 0):
        return None
    return last / ref - 1.0


def compute_relative_strength(
    history: pl.DataFrame,
    *,
    benchmark: str = "SPY",
    windows: tuple[int, ...] = (21, 63, 126),
    as_of: date,
) -> dict[str, dict[str, Any]]:
    """Per-ETF excess return vs ``benchmark`` over each window + a rank.

    Args:
        history: long frame with ``date``, ``ticker``, ``close``.
        benchmark: ticker excluded from the output and used as the baseline.
        windows: trailing-trading-day windows for the excess-return calc.
        as_of: only rows ``<= as_of`` are used (look-ahead guard).

    Returns:
        ``{ticker: {rs_<w>d: excess_pct, rs_rank: 0-1 (1=strongest), trend}}``.
        Empty when there is no data or the benchmark is missing.
    """
    if history.is_empty():
        return {}

    # Supabase hands dates back as ISO strings; tests may pass real dates.
    if history.schema.get("date") == pl.Utf8:
        history = history.with_columns(pl.col("date").str.to_date())

    df = (
        history.select(
            pl.col("date").cast(pl.Date),
            pl.col("ticker").cast(pl.Utf8),
            pl.col("close").cast(pl.Float64),
        )
        .drop_nulls(subset=["close"])
        .filter(pl.col("date") <= as_of)
        .sort(["ticker", "date"])
    )
    if df.is_empty():
        return {}

    parts = df.partition_by("ticker", as_dict=True)

    def _ticker_of(key: Any) -> str:
        return key[0] if isinstance(key, tuple) else key

    bench_frame = next((g for k, g in parts.items() if _ticker_of(k) == benchmark), None)
    if bench_frame is None:
        return {}
    bench_ret = {w: _window_return(bench_frame["close"], w) for w in windows}

    mid_window = windows[len(windows) // 2]
    out: dict[str, dict[str, Any]] = {}
    for key, g in parts.items():
        ticker = _ticker_of(key)
        if ticker == benchmark:
            continue
        rec: dict[str, Any] = {}
        for w in windows:
            r = _window_return(g["close"], w)
            b = bench_ret.get(w)
            rec[f"rs_{w}d"] = round((r - b) * 100, 2) if (r is not None and b is not None) else None
        out[ticker] = rec

    # Cross-sectional rank on the mid window (1.0 = strongest). Tickers without a
    # mid-window reading are left unranked.
    ranked = sorted(
        (t for t, v in out.items() if v.get(f"rs_{mid_window}d") is not None),
        key=lambda t: out[t][f"rs_{mid_window}d"],
        reverse=True,
    )
    m = len(ranked)
    for i, t in enumerate(ranked):
        out[t]["rs_rank"] = round((m - i) / m, 2)
        out[t]["trend"] = "leading" if out[t][f"rs_{mid_window}d"] > 0 else "lagging"
    return out


__all__ = ["compute_relative_strength"]
