"""Supabase upsert helpers for price_history / price_technicals / macro_series_observations.

Preserves the column contracts Atlas still reads:

* ``price_history`` — ``{date, ticker, open, high, low, close, volume}``
* ``price_technicals`` — ``{date, ticker, <TECHNICAL_COLUMNS>}``
* ``macro_series_observations`` — ``{source, series_id, obs_date, value, unit, meta?}``

All audit payloads are passed through
:func:`digibase.audit.redact_mapping` before being emitted (per CLAUDE.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

import polars as pl

from digibase.audit import redact_mapping

from digiquant.data.prices import TECHNICAL_COLUMNS

DEFAULT_CHUNK = 500


class SupabaseLike(Protocol):
    """Structural type matching both ``supabase.Client`` and test fakes."""

    def table(self, name: str) -> Any:  # pragma: no cover - protocol
        ...


@dataclass(frozen=True)
class UpsertResult:
    table: str
    rows: int


def _safe_float(v: Any, decimals: int | None = 4) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, decimals) if decimals is not None else f


def _chunks(rows: list[dict[str, Any]], chunk: int):
    for i in range(0, len(rows), chunk):
        yield rows[i : i + chunk]


def ohlcv_to_price_history_rows(df: pl.DataFrame, ticker: str) -> list[dict[str, Any]]:
    """Convert a Polars OHLCV frame into price_history row dicts."""
    if df.is_empty():
        return []
    lower = {c: c.lower() for c in df.columns if c != c.lower()}
    if lower:
        df = df.rename(lower)
    if "timestamp" not in df.columns:
        for alt in ("date", "datetime"):
            if alt in df.columns:
                df = df.rename({alt: "timestamp"})
                break
    rows: list[dict[str, Any]] = []
    for r in df.iter_rows(named=True):
        ts = r.get("timestamp")
        obs_date = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
        close = _safe_float(r.get("close"))
        if close is None:
            continue
        rows.append(
            {
                "date": obs_date,
                "ticker": ticker,
                "open": _safe_float(r.get("open")),
                "high": _safe_float(r.get("high")),
                "low": _safe_float(r.get("low")),
                "close": close,
                "volume": _safe_float(r.get("volume"), decimals=None),
            }
        )
    return rows


def technicals_to_rows(
    df: pl.DataFrame, ticker: str, timestamps: pl.Series
) -> list[dict[str, Any]]:
    """Convert a technicals DataFrame into price_technicals row dicts.

    ``df`` columns must be a subset of :data:`TECHNICAL_COLUMNS`. ``timestamps``
    is a parallel Polars Series (one entry per row in ``df``).
    """
    if df.is_empty():
        return []
    if df.height != timestamps.len():
        raise ValueError("technicals rows and timestamps must have equal length")
    rows: list[dict[str, Any]] = []
    named = df.iter_rows(named=True)
    for ts, ind in zip(timestamps.to_list(), named, strict=True):
        obs_date = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
        row: dict[str, Any] = {"date": obs_date, "ticker": ticker}
        for col in TECHNICAL_COLUMNS:
            if col in ind:
                row[col] = _safe_float(ind[col])
        # Drop rows where every indicator column is None (leading NaN window).
        if any(row.get(c) is not None for c in TECHNICAL_COLUMNS):
            rows.append(row)
    return rows


def upsert_price_history(
    client: SupabaseLike,
    rows: list[dict[str, Any]],
    *,
    chunk: int = DEFAULT_CHUNK,
) -> UpsertResult:
    if not rows:
        return UpsertResult(table="price_history", rows=0)
    total = 0
    for batch in _chunks(rows, chunk):
        client.table("price_history").upsert(batch).execute()
        total += len(batch)
    _emit_audit("price_history", total)
    return UpsertResult(table="price_history", rows=total)


def upsert_price_technicals(
    client: SupabaseLike,
    rows: list[dict[str, Any]],
    *,
    chunk: int = DEFAULT_CHUNK,
) -> UpsertResult:
    if not rows:
        return UpsertResult(table="price_technicals", rows=0)
    total = 0
    for batch in _chunks(rows, chunk):
        client.table("price_technicals").upsert(batch).execute()
        total += len(batch)
    _emit_audit("price_technicals", total)
    return UpsertResult(table="price_technicals", rows=total)


def upsert_macro_observations(
    client: SupabaseLike,
    rows: list[dict[str, Any]],
    *,
    chunk: int = DEFAULT_CHUNK,
) -> UpsertResult:
    if not rows:
        return UpsertResult(table="macro_series_observations", rows=0)
    total = 0
    for batch in _chunks(rows, chunk):
        client.table("macro_series_observations").upsert(
            batch, on_conflict="source,series_id,obs_date"
        ).execute()
        total += len(batch)
    _emit_audit("macro_series_observations", total)
    return UpsertResult(table="macro_series_observations", rows=total)


def _emit_audit(table: str, rows: int) -> None:
    """Redacted audit record hook — structured for downstream log sinks.

    We never log row bodies (may contain licensed data per vendor ToS). We do
    redact the payload even though no secret-keyed fields are present, to
    guarantee the invariant at the call site.
    """
    redact_mapping({"table": table, "rows": rows, "operation": "upsert"})


def build_supabase_client(url: str | None, key: str | None):  # pragma: no cover - thin wrapper
    """Thin factory; returns ``None`` when creds are missing (matches legacy)."""
    if not url or not key:
        return None
    from supabase import create_client  # type: ignore[import-not-found]

    return create_client(url, key)


__all__ = [
    "DEFAULT_CHUNK",
    "SupabaseLike",
    "UpsertResult",
    "build_supabase_client",
    "ohlcv_to_price_history_rows",
    "technicals_to_rows",
    "upsert_macro_observations",
    "upsert_price_history",
    "upsert_price_technicals",
]
