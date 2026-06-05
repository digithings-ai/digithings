"""Internal helpers shared across the prices package.

Kept deliberately small — anything exported from here is a private helper
with no external callers.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any, TypeVar  # noqa: ANN401 — TypeVar bound for call_with_retry

import polars as pl

T = TypeVar("T")

# Transient postgrest / supabase-py / network failures during chunked upserts.
TRANSIENT_UPSERT_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ValueError,
    TypeError,
    KeyError,
    RuntimeError,
)


def safe_float(v: Any, decimals: int | None = 4) -> float | None:
    """Coerce a value to a finite Python float, or return ``None``.

    Returns ``None`` for ``NaN`` / ``±inf`` / non-numeric / coercion errors.
    If ``decimals`` is given, the result is rounded; pass ``None`` to skip
    rounding (e.g. for integer-typed volume columns).

    Single source of truth — previously duplicated in both
    ``supabase_writer.py`` and the legacy
    ``digiquant/scripts/atlas/compute-technicals.py`` shim.
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, decimals) if decimals is not None else f


def safe_int(v: Any) -> int | None:
    """Coerce a value to an int, or return ``None``.

    Volume columns in Supabase are ``bigint``; postgrest rejects float payloads
    (``"127844500.0"``) with ``22P02`` invalid-syntax errors. yfinance sometimes
    returns volume as float (NaN-coercion, unadjusted closes, pandas extension
    dtypes), so we must cast before serializing.
    """
    f = safe_float(v, decimals=None)
    return int(f) if f is not None else None


def filter_rows_by_trading_days(df: pl.DataFrame, trading_days: pl.Series) -> pl.DataFrame:
    """Keep rows whose ``timestamp`` falls on a day in ``trading_days``.

    ``trading_days`` is a Series of :class:`datetime.date` (``pl.Date``). Cached
    OHLCV often stores ``timestamp`` as ``pl.Datetime`` after ``read_csv``; Polars
    rejects ``is_in`` across Date vs Datetime, so we normalize to date first.
    """
    if "timestamp" not in df.columns:
        return df
    ts_dtype = df.schema["timestamp"]
    if ts_dtype == pl.Date:
        ts = pl.col("timestamp")
    elif isinstance(ts_dtype, pl.Datetime):
        ts = pl.col("timestamp").dt.date()
    else:
        ts = pl.col("timestamp").cast(pl.Date)
    return df.filter(ts.is_in(trading_days))


def call_with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 5,
    backoff_seconds: float = 0.75,
    transient: tuple[type[BaseException], ...] = TRANSIENT_UPSERT_ERRORS,
) -> T:
    """Invoke *fn* with linear backoff on transient errors."""
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except transient as exc:
            last = exc
            if attempt >= attempts:
                raise
            time.sleep(backoff_seconds * attempt)
    raise AssertionError("unreachable") from last


__all__ = [
    "TRANSIENT_UPSERT_ERRORS",
    "call_with_retry",
    "filter_rows_by_trading_days",
    "safe_float",
    "safe_int",
]
