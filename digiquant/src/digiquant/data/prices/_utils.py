"""Internal helpers shared across the prices package.

Kept deliberately small — anything exported from here is a private helper
with no external callers.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from datetime import date as dt_date
from typing import Any, TypeVar  # score:allow untyped any — TypeVar bound for call_with_retry

import polars as pl

T = TypeVar("T")

_logger = logging.getLogger(__name__)

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
    ``digiquant/scripts/research/compute-technicals.py`` shim.
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


def fetch_trading_days(client: Any, venue: str, *, page_size: int = 1000) -> pl.Series | None:
    """Fetch all trading days for ``venue`` from the ``trading_calendar`` table.

    Returns a :class:`polars.Series` of :class:`datetime.date` values for rows
    where ``is_trading_day=True``, or ``None`` on error.  Paginates automatically
    so callers are not limited by Supabase's default 1 000-row cap.

    ``page_size`` must be <= PostgREST's max-rows cap (1 000). A larger value
    silently returns only the first 1 000 rows, so ``len(batch) < page_size``
    is true on page 1 and pagination stops after one page — which previously
    yielded only the *oldest* 1 000 days and dropped every recent session from
    the technicals trading-day filter. ``.order("date")`` makes paging
    deterministic.

    Lives here rather than in ``cli/prices.py`` (its original home) because
    :mod:`digiquant.data.prices.refresh` needs the same calendar to avoid
    computing indicators on non-session bars (#1752).
    """
    all_dates: list[dt_date] = []
    offset = 0
    try:
        while True:
            resp = (
                client.table("trading_calendar")
                .select("date")
                .eq("venue", venue)
                .eq("is_trading_day", True)
                .order("date")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = resp.data or []
            for row in batch:
                raw = row.get("date")
                if raw:
                    all_dates.append(dt_date.fromisoformat(str(raw)[:10]))
            if len(batch) < page_size:
                break
            offset += page_size
    except Exception as exc:
        _logger.warning("trading_calendar query failed for venue %s: %s", venue, exc)
        return None
    if not all_dates:
        return None
    return pl.Series("trading_days", all_dates)


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
    "fetch_trading_days",
    "filter_rows_by_trading_days",
    "safe_float",
    "safe_int",
]
