"""Bitview / Bitcoin Research Kit (BRK) on-chain series — Polars-only, fail-soft.

Read-only client for hosted Bitview (``https://bitview.space``) or a self-hosted
BRK. JSON API only — no HTML scrape. Network is opt-in: the MCP tool is the
operator opt-in; tests inject a session and never hit the network.

v1 catalog (#1086 / research PR #3246): ``mvrv``, ``asopr_24h``,
``puell_multiple``, ``rhodl_ratio``. Do **not** dual-count ``nupl`` (monotone
of MVRV). Coin Metrics community series are CC BY-NC — this client does not
fetch them and they must not be republished commercially.

HTTP is split from parsing: ``series_data_to_frame`` is HTTP-free (unit-tested
against a captured SeriesData shape); ``BitviewClient.fetch`` adds timeout +
fail-soft. Mirrors ``data/onchain/hyperdash.py``.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Protocol  # score:allow untyped any — Bitview SeriesData JSON payloads

import httpx
import polars as pl
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

BITVIEW_BASE_URL = "https://bitview.space"
# BRK ``day1`` index 0 is Bitcoin genesis (same convention as ``btc_power_law``).
DAY1_EPOCH: date = date(2009, 1, 3)
DEFAULT_INDEX = "day1"
DEFAULT_SERIES: tuple[str, ...] = (
    "mvrv",
    "asopr_24h",
    "puell_multiple",
    "rhodl_ratio",
)
# NUPL = 1 − 1/MVRV. Fetching it as a second vote double-counts realized cap.
FORBIDDEN_SERIES: frozenset[str] = frozenset({"nupl"})
DEFAULT_CACHE_DIR = Path("data/onchain/bitview")
DEFAULT_TIMEOUT = 30.0
_USER_AGENT = "digiquant-research/1.0 (+https://digiquant.io)"
_ENV_FLAG = "DIGIQUANT_BITVIEW_FETCH"
LICENSE_NOTE = (
    "BRK MIT. Hosted bitview.space has no SLA; self-host BRK for production. "
    "Coin Metrics community data is CC BY-NC — research-only, do not publish "
    "derived CM series commercially."
)


class BitviewSeriesResult(BaseModel):
    """One series fetch: parquet path + coverage, or a fail-soft error."""

    model_config = ConfigDict(frozen=True, strict=True)

    series_id: str = Field(min_length=1)
    index: str = DEFAULT_INDEX
    row_count: int = Field(0, ge=0)
    date_start: date | None = None
    date_end: date | None = None
    null_days: int = Field(0, ge=0)
    path: str | None = None
    error: str | None = None
    source: str = "bitview"

    @property
    def has_data(self) -> bool:
        return self.error is None and self.row_count > 0


class BitviewFetchResult(BaseModel):
    """Multi-series fetch. Per-series errors stay in ``series``; transport
    failure also sets top-level ``error``.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    source: str = "bitview"
    index: str = DEFAULT_INDEX
    series: dict[str, BitviewSeriesResult]
    license: str = LICENSE_NOTE
    error: str | None = None


def day1_index_to_date(index: int) -> date:
    """Map a BRK ``day1`` offset to a calendar date (genesis = 0)."""
    if index < 0:
        raise ValueError(f"day1 index must be >= 0, got {index}")
    return DAY1_EPOCH + timedelta(days=index)


def _empty_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": pl.Series("date", [], dtype=pl.Date),
            "value": pl.Series("value", [], dtype=pl.Float64),
        }
    )


def series_data_to_frame(payload: object, *, series_id: str = "") -> pl.DataFrame:
    """Pure parser: Bitview ``SeriesData`` JSON → ``date``/``value`` Polars.

    Captured shape (2026-08-30)::

        {"version": …, "index": "day1", "type": "StoredF32",
         "start": 800, "end": 805, "stamp": "…Z",
         "data": [3.214286, 3.214286, 3.178571, 3.142857, 2.931034]}

    ``start`` inclusive, ``end`` exclusive. Null values are kept as null
    (warmup / pre-history). Unrecognized payloads return an empty frame.
    """
    del series_id  # reserved for diagnostics; shape is index/data only
    if not isinstance(payload, dict):
        return _empty_frame()
    data = payload.get("data")
    if not isinstance(data, list):
        return _empty_frame()
    try:
        start = int(payload.get("start", 0))
    except (TypeError, ValueError):
        return _empty_frame()
    index_name = payload.get("index")
    if index_name not in (None, DEFAULT_INDEX, "day1"):
        logger.warning("Bitview series index %r is not day1; refusing", index_name)
        return _empty_frame()
    dates: list[date] = []
    values: list[float | None] = []
    for offset, raw in enumerate(data):
        dates.append(day1_index_to_date(start + offset))
        if raw is None:
            values.append(None)
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            values.append(None)
    if not dates:
        return _empty_frame()
    return pl.DataFrame({"date": dates, "value": values}).sort("date")


def write_series_parquet(frame: pl.DataFrame, path: Path | str) -> Path:
    """Persist ``date``/``value`` parquet under ``data/onchain/bitview/``."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if "date" not in frame.columns or "value" not in frame.columns:
        raise ValueError(f"bitview frame needs date/value columns, got {frame.columns}")
    out = frame.select(
        pl.col("date").cast(pl.Date),
        pl.col("value").cast(pl.Float64),
    )
    out.write_parquet(dest)
    return dest


def _result_from_frame(
    series_id: str,
    frame: pl.DataFrame,
    *,
    cache_dir: Path | None,
    error: str | None = None,
) -> BitviewSeriesResult:
    path: str | None = None
    if error is None and cache_dir is not None and frame.height > 0:
        path = str(write_series_parquet(frame, Path(cache_dir) / f"{series_id}.parquet"))
    dated = frame.filter(pl.col("value").is_not_null()) if frame.height else frame
    return BitviewSeriesResult(
        series_id=series_id,
        row_count=frame.height,
        date_start=dated["date"][0] if dated.height else None,
        date_end=dated["date"][-1] if dated.height else None,
        null_days=int(frame["value"].null_count()) if frame.height else 0,
        path=path,
        error=error,
    )


def _forbidden_result(series_id: str) -> BitviewSeriesResult:
    return BitviewSeriesResult(
        series_id=series_id,
        error=(
            f"{series_id} is a monotone of mvrv (NUPL = 1 − 1/MVRV); do not dual-count (Refs #1086)"
        ),
    )


def _normalize_ids(series_ids: list[str] | None) -> list[str]:
    if not series_ids:
        return list(DEFAULT_SERIES)
    out: list[str] = []
    seen: set[str] = set()
    for raw in series_ids:
        name = str(raw).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out or list(DEFAULT_SERIES)


class _HttpGet(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        params: dict[str, str | int] | None = None,
    ) -> Any: ...


def _get_json(
    url: str,
    *,
    timeout: float,
    session: _HttpGet | None,
    params: dict[str, str | int] | None = None,
) -> object:
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    caller = session if session is not None else httpx
    resp = caller.get(url, headers=headers, timeout=timeout, params=params)
    resp.raise_for_status()
    return resp.json()


class BitviewClient:
    """GET Bitview/BRK ``day1`` series. Fail-soft; injectable session for tests."""

    def __init__(
        self,
        *,
        base_url: str = BITVIEW_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        session: _HttpGet | None = None,
        cache_dir: Path | str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None

    def fetch(
        self,
        series_ids: list[str] | None = None,
        *,
        start: int | None = None,
        end: int | None = None,
    ) -> BitviewFetchResult:
        ids = _normalize_ids(series_ids)
        results: dict[str, BitviewSeriesResult] = {}
        allowed: list[str] = []
        for series_id in ids:
            if series_id.lower() in FORBIDDEN_SERIES:
                results[series_id] = _forbidden_result(series_id)
            else:
                allowed.append(series_id)
        if not allowed:
            return BitviewFetchResult(series=results)
        try:
            fetched = self._fetch_allowed(allowed, start=start, end=end)
        except Exception as exc:  # transport/HTTP — never crash the caller
            logger.warning("Bitview fetch failed: %s", exc)
            err = f"{type(exc).__name__}: {exc}"
            for series_id in allowed:
                results[series_id] = BitviewSeriesResult(series_id=series_id, error=err)
            return BitviewFetchResult(series=results, error=err)
        results.update(fetched)
        allowed_hits = [results[sid] for sid in allowed]
        if allowed_hits and not any(row.has_data for row in allowed_hits):
            first_err = next(
                (row.error for row in allowed_hits if row.error),
                "no series returned data",
            )
            return BitviewFetchResult(series=results, error=first_err)
        return BitviewFetchResult(series=results)

    def _fetch_allowed(
        self,
        allowed: list[str],
        *,
        start: int | None,
        end: int | None,
    ) -> dict[str, BitviewSeriesResult]:
        params: dict[str, str | int] = {}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        bulk_url = f"{self.base_url}/api/series/bulk"
        bulk_params = {"series": ",".join(allowed), "index": DEFAULT_INDEX, **params}
        try:
            body = _get_json(
                bulk_url, timeout=self.timeout, session=self.session, params=bulk_params
            )
        except Exception:
            return {sid: self._fetch_one(sid, params=params) for sid in allowed}
        if not isinstance(body, list) or len(body) != len(allowed):
            return {sid: self._fetch_one(sid, params=params) for sid in allowed}
        out: dict[str, BitviewSeriesResult] = {}
        for series_id, payload in zip(allowed, body, strict=True):
            out[series_id] = self._result_from_payload(series_id, payload)
        return out

    def _fetch_one(self, series_id: str, *, params: dict[str, str | int]) -> BitviewSeriesResult:
        url = f"{self.base_url}/api/series/{series_id}/{DEFAULT_INDEX}"
        try:
            payload = _get_json(url, timeout=self.timeout, session=self.session, params=params)
        except Exception as exc:
            logger.warning("Bitview series %s failed: %s", series_id, exc)
            return BitviewSeriesResult(series_id=series_id, error=f"{type(exc).__name__}: {exc}")
        return self._result_from_payload(series_id, payload)

    def _result_from_payload(self, series_id: str, payload: object) -> BitviewSeriesResult:
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            message = payload["error"].get("message") or payload["error"].get("code") or "error"
            return BitviewSeriesResult(series_id=series_id, error=str(message))
        frame = series_data_to_frame(payload, series_id=series_id)
        if frame.height == 0:
            return BitviewSeriesResult(series_id=series_id, error="no data")
        return _result_from_frame(series_id, frame, cache_dir=self.cache_dir)


def _fetch_enabled() -> bool:
    """Kill-switch for *library* auto-fetch. MCP invocation is itself opt-in."""
    raw = os.environ.get(_ENV_FLAG, "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def fetch_bitview_series(
    series_ids: list[str] | None = None,
    *,
    cache_dir: Path | str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    session: _HttpGet | None = None,
    start: int | None = None,
    end: int | None = None,
    base_url: str = BITVIEW_BASE_URL,
) -> BitviewFetchResult:
    """Fetch v1 series. Always fail-soft. Inject ``session`` in tests (no network)."""
    if session is None and not _fetch_enabled():
        ids = _normalize_ids(series_ids)
        return BitviewFetchResult(
            series={
                sid: BitviewSeriesResult(series_id=sid, error=f"{_ENV_FLAG} disabled (no network)")
                for sid in ids
            },
            error=f"{_ENV_FLAG} disabled",
        )
    client = BitviewClient(base_url=base_url, timeout=timeout, session=session, cache_dir=cache_dir)
    return client.fetch(series_ids, start=start, end=end)


__all__ = [
    "BITVIEW_BASE_URL",
    "DAY1_EPOCH",
    "DEFAULT_CACHE_DIR",
    "DEFAULT_SERIES",
    "FORBIDDEN_SERIES",
    "LICENSE_NOTE",
    "BitviewClient",
    "BitviewFetchResult",
    "BitviewSeriesResult",
    "day1_index_to_date",
    "fetch_bitview_series",
    "series_data_to_frame",
    "write_series_parquet",
]
