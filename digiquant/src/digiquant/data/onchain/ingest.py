"""Bitview → digiquant store ingest (#1086).

Fetches BRK/Bitview ``day1`` series into parquet under ``data/onchain/bitview/``
and optionally upserts ``macro_series_observations`` rows with
``source='bitview'``. Fail-soft: per-series errors stay on the result; a
total transport failure sets top-level ``error``. Unit tests inject a
session and never hit the network.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.data.onchain.bitview import (
    DEFAULT_CACHE_DIR,
    DEFAULT_SERIES,
    LICENSE_NOTE,
    BitviewFetchResult,
    fetch_bitview_series,
)

logger = logging.getLogger(__name__)

BITVIEW_SOURCE = "bitview"


class BitviewIngestResult(BaseModel):
    """Outcome of one scheduled / CLI Bitview ingest."""

    model_config = ConfigDict(frozen=True, strict=True)

    source: str = BITVIEW_SOURCE
    cache_dir: str
    fetch: BitviewFetchResult
    macro_rows: int = Field(0, ge=0)
    upserted: int = Field(0, ge=0)
    license: str = LICENSE_NOTE
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and any(s.has_data for s in self.fetch.series.values())


def frame_to_macro_rows(
    frame: pl.DataFrame,
    *,
    series_id: str,
    source: str = BITVIEW_SOURCE,
    unit: str | None = None,
) -> list[dict[str, Any]]:
    """Convert a ``date``/``value`` frame into ``macro_series_observations`` rows."""
    if "date" not in frame.columns or "value" not in frame.columns:
        raise ValueError(f"frame needs date/value columns, got {frame.columns}")
    rows: list[dict[str, Any]] = []
    for row in frame.select(
        pl.col("date").cast(pl.Date),
        pl.col("value").cast(pl.Float64),
    ).iter_rows(named=True):
        obs: date | None = row["date"]
        val = row["value"]
        if obs is None or val is None:
            continue
        try:
            numeric = float(val)
        except (TypeError, ValueError):
            continue
        if numeric != numeric:  # NaN
            continue
        rows.append(
            {
                "source": source,
                "series_id": series_id,
                "obs_date": obs.isoformat(),
                "value": numeric,
                "unit": unit,
                "meta": {"index": "day1", "provider": "bitview"},
            }
        )
    return rows


def series_frames_from_fetch(
    fetch: BitviewFetchResult,
    *,
    cache_dir: Path,
) -> dict[str, pl.DataFrame]:
    """Load parquet written during fetch (or empty if no path)."""
    out: dict[str, pl.DataFrame] = {}
    for series_id, result in fetch.series.items():
        if not result.has_data:
            continue
        path = Path(result.path) if result.path else cache_dir / f"{series_id}.parquet"
        if not path.is_file():
            continue
        out[series_id] = pl.read_parquet(path)
    return out


def ingest_bitview(
    series_ids: list[str] | None = None,
    *,
    cache_dir: Path | str | None = None,
    session: Any | None = None,
    supabase_client: Any | None = None,
    start: int | None = None,
    end: int | None = None,
) -> BitviewIngestResult:
    """Fetch Bitview series → parquet; optionally upsert macro store.

    ``session`` is injected in unit tests (no network). ``supabase_client``
    when provided upserts rows; when ``None``, only parquet is written.
    """
    dest = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    dest.mkdir(parents=True, exist_ok=True)
    ids = series_ids if series_ids else list(DEFAULT_SERIES)
    fetch = fetch_bitview_series(
        ids,
        cache_dir=dest,
        session=session,
        start=start,
        end=end,
    )
    frames = series_frames_from_fetch(fetch, cache_dir=dest)
    rows: list[dict[str, Any]] = []
    for series_id, frame in frames.items():
        rows.extend(frame_to_macro_rows(frame, series_id=series_id))

    upserted = 0
    error = fetch.error
    if supabase_client is not None and rows:
        try:
            from digiquant.data.prices.supabase_writer import upsert_macro_observations

            result = upsert_macro_observations(supabase_client, rows)
            upserted = result.rows
        except Exception as exc:  # fail-soft store write
            logger.warning("Bitview macro upsert failed: %s", exc)
            error = f"{type(exc).__name__}: {exc}"

    return BitviewIngestResult(
        cache_dir=str(dest),
        fetch=fetch,
        macro_rows=len(rows),
        upserted=upserted,
        error=error,
    )


__all__ = [
    "BITVIEW_SOURCE",
    "BitviewIngestResult",
    "frame_to_macro_rows",
    "ingest_bitview",
    "series_frames_from_fetch",
]
