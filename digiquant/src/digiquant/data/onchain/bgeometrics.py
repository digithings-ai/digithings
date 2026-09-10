"""BGeometrics / bitcoin-data.com on-chain valuation series — fail-soft, HTTP-free parser.

Free public REST API for Bitcoin valuation and on-chain metrics (MVRV, NUPL,
SOPR, realized cap/price, HODL waves, Mayer multiple, NVT, Pi-cycle, rainbow
chart, power-law model, and more — 700+ endpoints as of 2026-09; docs at
https://api.bgeometrics.com/scalar.html). Investigated as the free
alternative to BlockHorizon's undocumented endpoint (issue #3694): it covers
nearly the same metric catalog with a documented, no-signup API.

Free-tier constraints:
- **Treat an API key as required, not optional.** This module originally
  documented anonymous access as working, but bitcoin-data.com now markets
  registration as required for even the free tier, and an unauthenticated
  call observed in a later session returned HTTP 200 with an empty body
  instead of data — anonymous access may be gone or degraded. Pass ``token``
  (or set ``BGEOMETRICS_API_TOKEN``); the exact header name bitcoin-data.com
  expects wasn't independently confirmed, so ``_get_json`` sends the token
  under both ``Authorization: Bearer`` and ``X-Bgapi-Token`` (the latter is
  what bitcoin-data.com's own MCP server docs describe) as a hedge.
- **10 requests/hour, 15 requests/day**, shared across every metric from one
  IP/token. Fetch **one metric per call**; do not loop over a catalog.
- **History capped at roughly the last 4 years.** Range queries further back
  return an empty list, not an error (verified: 2014-01 and 2018-01 both
  returned ``[]`` while 2025-01 returned real values). Multi-cycle
  backtesting (2014/2018 cycles) needs a different source — see
  ``coinmetrics.py``, whose free MVRV series covers full history back to
  2010.

HTTP is split from parsing, mirroring ``data/onchain/bitview.py``:
``bgeometrics_rows_to_frame`` is HTTP-free; ``BgeometricsClient.fetch`` adds
timeout + fail-soft handling, including surfacing the API's own rate-limit
error message instead of a bare HTTP status.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from typing import Any, Protocol  # score:allow untyped any — bitcoin-data.com JSON rows

import httpx
import polars as pl
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

BGEOMETRICS_BASE_URL = "https://api.bitcoin-data.com"
DEFAULT_TIMEOUT = 30.0
DEFAULT_CACHE_DIR = Path("data/onchain/bgeometrics")
_USER_AGENT = "digiquant-research/1.0 (+https://digiquant.io)"
_ENV_FLAG = "DIGIQUANT_BGEOMETRICS_FETCH"
_ENV_TOKEN = "BGEOMETRICS_API_TOKEN"

# A curated subset of the ~700-endpoint catalog covering the BlockHorizon-style
# valuation composites from issue #3694. Any other bitcoin-data.com metric slug
# also works against this client — this is a menu, not a whitelist.
KNOWN_METRICS: tuple[str, ...] = (
    "mvrv",
    "mvrv-zscore",
    "nupl",
    "sopr",
    "realized-price",
    "realized-cap",
    "thermocap-multiple",
    "mayer-multiple",
    "pi-cycle",
    "rainbow-chart",
    "power-law-model-price",
    "nvt-ratio",
    "hodl-waves-supply",
)

FREE_TIER_NOTE = (
    "bitcoin-data.com free plan: 10 req/hour, 15 req/day, shared across all "
    "metrics from one IP/token. History is limited to roughly the last 4 "
    "years. Fetch one metric per call. For full-history MVRV back to 2010, "
    "use digiquant.data.onchain.coinmetrics instead."
)


class BgeometricsSeriesResult(BaseModel):
    """One metric fetch: parquet path + coverage, or a fail-soft error."""

    model_config = ConfigDict(frozen=True, strict=True)

    metric: str = Field(min_length=1)
    row_count: int = Field(0, ge=0)
    date_start: date | None = None
    date_end: date | None = None
    null_days: int = Field(0, ge=0)
    path: str | None = None
    error: str | None = None
    source: str = "bgeometrics"
    note: str = FREE_TIER_NOTE

    @property
    def has_data(self) -> bool:
        return self.error is None and self.row_count > 0


def _empty_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": pl.Series("date", [], dtype=pl.Date),
            "value": pl.Series("value", [], dtype=pl.Float64),
        }
    )


def _row_value(row: dict[str, Any]) -> float | None:
    """Pick the metric's value out of a ``{"d", "unixTs", "<metric>": v}`` row.

    bitcoin-data.com names the value field after the metric slug (e.g.
    ``mvrv``, ``sopr``) in a casing we don't know ahead of time for every one
    of the ~700 endpoints, so take whichever single numeric field isn't the
    date/timestamp/paging metadata.
    """
    skip = {"d", "unixTs", "page", "totalPages", "totalElements"}
    candidates = [
        v
        for k, v in row.items()
        if k not in skip and isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    if len(candidates) != 1:
        return None
    return float(candidates[0])


def bgeometrics_rows_to_frame(payload: object) -> pl.DataFrame:
    """Pure parser: bitcoin-data.com JSON (single row or list of rows) -> Polars.

    Captured shapes (2026-09-10, live)::

        {"d": "2026-09-09", "unixTs": 1788912000, "mvrv": 1.4808}
        [{"d": "2025-01-01", "unixTs": 1735689600, "mvrv": 2.3579}, ...]

    Unrecognized payloads return an empty frame; rows missing a parseable
    date or exactly one numeric value are dropped rather than raising.
    """
    if isinstance(payload, dict):
        rows: list[Any] = [payload]
    elif isinstance(payload, list):
        rows = payload
    else:
        return _empty_frame()
    dates: list[date] = []
    values: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_date = row.get("d")
        if not isinstance(raw_date, str):
            continue
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError:
            continue
        value = _row_value(row)
        if value is None:
            continue
        dates.append(parsed)
        values.append(value)
    if not dates:
        return _empty_frame()
    return pl.DataFrame({"date": dates, "value": values}).sort("date")


def write_series_parquet(frame: pl.DataFrame, path: Path | str) -> Path:
    """Persist ``date``/``value`` parquet under ``data/onchain/bgeometrics/``."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if "date" not in frame.columns or "value" not in frame.columns:
        raise ValueError(f"bgeometrics frame needs date/value columns, got {frame.columns}")
    out = frame.select(
        pl.col("date").cast(pl.Date),
        pl.col("value").cast(pl.Float64),
    )
    out.write_parquet(dest)
    return dest


def _result_from_frame(
    metric: str,
    frame: pl.DataFrame,
    *,
    cache_dir: Path | None,
    error: str | None = None,
) -> BgeometricsSeriesResult:
    path: str | None = None
    if error is None and cache_dir is not None and frame.height > 0:
        path = str(write_series_parquet(frame, Path(cache_dir) / f"{metric}.parquet"))
    return BgeometricsSeriesResult(
        metric=metric,
        row_count=frame.height,
        date_start=frame["date"][0] if frame.height else None,
        date_end=frame["date"][-1] if frame.height else None,
        null_days=int(frame["value"].null_count()) if frame.height else 0,
        path=path,
        error=error,
    )


class _HttpGet(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        params: dict[str, str | int] | None = None,
    ) -> Any: ...


def _error_from_response(exc: httpx.HTTPStatusError) -> str:
    """Surface bitcoin-data.com's own error message (e.g. rate-limit detail)
    instead of a bare HTTP status when the response body is JSON.
    """
    try:
        body = exc.response.json()
    except Exception:
        return f"HTTPStatusError: {exc}"
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            message = err.get("message") or err.get("code")
            if message:
                return str(message)
    return f"HTTPStatusError: {exc}"


def _get_json(
    url: str,
    *,
    timeout: float,
    session: _HttpGet | None,
    params: dict[str, str | int] | None,
    token: str | None,
) -> object:
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if token:
        # bitcoin-data.com's own MCP docs (mcp.bitcoin-data.com) document
        # ``x-bgapi-token`` as the header name, while this client historically
        # sent ``Authorization: Bearer``. Send both — harmless if only one is
        # actually read, and avoids silently breaking whichever scheme is real.
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Bgapi-Token"] = token
    caller = session if session is not None else httpx
    resp = caller.get(url, headers=headers, timeout=timeout, params=params)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(_error_from_response(exc)) from exc
    return resp.json()


class BgeometricsClient:
    """GET one bitcoin-data.com metric. Fail-soft; injectable session for tests."""

    def __init__(
        self,
        *,
        base_url: str = BGEOMETRICS_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        session: _HttpGet | None = None,
        cache_dir: Path | str | None = None,
        token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.token = token

    def fetch(
        self,
        metric: str,
        *,
        startday: str | None = None,
        endday: str | None = None,
        last: bool = False,
    ) -> BgeometricsSeriesResult:
        metric = metric.strip().lstrip("/")
        if not metric:
            return BgeometricsSeriesResult(metric=metric or "?", error="metric id is required")
        suffix = "/last" if last else ""
        url = f"{self.base_url}/v1/{metric}{suffix}"
        params: dict[str, str | int] = {}
        if not last:
            if startday:
                params["startday"] = startday
            if endday:
                params["endday"] = endday
        try:
            payload = _get_json(
                url,
                timeout=self.timeout,
                session=self.session,
                params=params or None,
                token=self.token,
            )
        except Exception as exc:  # transport/HTTP/rate-limit — never crash the caller
            logger.warning("bgeometrics fetch of %s failed: %s", metric, exc)
            return BgeometricsSeriesResult(metric=metric, error=str(exc))
        frame = bgeometrics_rows_to_frame(payload)
        if frame.height == 0:
            return BgeometricsSeriesResult(
                metric=metric,
                error="no data (unknown metric, or before the free-tier history window)",
            )
        return _result_from_frame(metric, frame, cache_dir=self.cache_dir)


def _fetch_enabled() -> bool:
    """Kill-switch for *library* auto-fetch. MCP invocation is itself opt-in."""
    raw = os.environ.get(_ENV_FLAG, "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def fetch_bgeometrics_series(
    metric: str,
    *,
    startday: str | None = None,
    endday: str | None = None,
    last: bool = False,
    cache_dir: Path | str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    session: _HttpGet | None = None,
    base_url: str = BGEOMETRICS_BASE_URL,
    token: str | None = None,
) -> BgeometricsSeriesResult:
    """Fetch one bitcoin-data.com metric. Always fail-soft. Inject ``session`` in tests (no network)."""
    if session is None and not _fetch_enabled():
        return BgeometricsSeriesResult(metric=metric, error=f"{_ENV_FLAG} disabled (no network)")
    resolved_token = token if token is not None else os.environ.get(_ENV_TOKEN, "").strip() or None
    client = BgeometricsClient(
        base_url=base_url,
        timeout=timeout,
        session=session,
        cache_dir=cache_dir,
        token=resolved_token,
    )
    return client.fetch(metric, startday=startday, endday=endday, last=last)


__all__ = [
    "BGEOMETRICS_BASE_URL",
    "DEFAULT_CACHE_DIR",
    "FREE_TIER_NOTE",
    "KNOWN_METRICS",
    "BgeometricsClient",
    "BgeometricsSeriesResult",
    "bgeometrics_rows_to_frame",
    "fetch_bgeometrics_series",
    "write_series_parquet",
]
