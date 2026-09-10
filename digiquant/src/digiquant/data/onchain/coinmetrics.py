"""CoinMetrics Community API on-chain series — fail-soft, HTTP-free parser.

Free, no-signup REST API (``https://community-api.coinmetrics.io/v4``).
Investigated as a full-history cross-check / complement to
``digiquant.data.onchain.bgeometrics`` (issue #3694): the community tier
exposes only a narrow metric set per asset (31 metrics for BTC, confirmed
live 2026-09-10) — of the valuation-composite family, only ``CapMVRVCur``
(MVRV) is included — but that one metric carries genuine full history back
to BTC's early years (2010-07-18 through today), unlike bgeometrics' ~4-year
free-tier cap. Coin Metrics community series are CC BY-NC — research-only,
do not republish derived series commercially (same restriction ``bitview.py``
already documents for its own CM-sourced data).

Confirmed live (2026-09-10):
- No auth required; rate limit is generous (``x-ratelimit-limit: 6000,
  6000;w=20`` — a sliding 20s window), so unlike bgeometrics this client can
  be called freely.
- A single request with a large ``page_size`` returns full history in one
  shot (5890 daily rows for BTC MVRV, no ``next_page_url`` needed) — no
  pagination handling required for a single asset/metric pull.

HTTP is split from parsing, mirroring ``data/onchain/bitview.py``:
``asset_metrics_rows_to_frame`` is HTTP-free; ``CoinMetricsClient.fetch``
adds timeout + fail-soft handling.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol  # score:allow untyped any — CoinMetrics JSON rows

import httpx
import polars as pl
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

COINMETRICS_BASE_URL = "https://community-api.coinmetrics.io/v4"
DEFAULT_TIMEOUT = 30.0
DEFAULT_PAGE_SIZE = 10_000
DEFAULT_CACHE_DIR = Path("data/onchain/coinmetrics")
_USER_AGENT = "digiquant-research/1.0 (+https://digiquant.io)"
_ENV_FLAG = "DIGIQUANT_COINMETRICS_FETCH"

# All 31 metrics available for BTC on the free community tier as of 2026-09-10
# (``GET /v4/catalog/assets?assets=btc``). Only CapMVRVCur is a valuation
# composite; the rest are supply/flow/fee/price primitives.
KNOWN_COMMUNITY_METRICS: tuple[str, ...] = (
    "CapMVRVCur",
    "CapMrktCurUSD",
    "CapMrktEstUSD",
    "PriceUSD",
    "PriceBTC",
    "SplyCur",
    "AdrActCnt",
    "AdrBalCnt",
    "HashRate",
    "TxCnt",
    "TxTfrCnt",
    "ROI30d",
    "ROI1yr",
)

LICENSE_NOTE = (
    "CoinMetrics community data is CC BY-NC — research-only, do not "
    "republish derived series commercially. Free community tier exposes "
    "only 31 metrics for BTC; CapMVRVCur (MVRV) is the only valuation "
    "composite among them, but it has full history back to 2010-07-18."
)


class CoinMetricsSeriesResult(BaseModel):
    """One metric fetch: parquet path + coverage, or a fail-soft error."""

    model_config = ConfigDict(frozen=True, strict=True)

    asset: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    row_count: int = Field(0, ge=0)
    date_start: date | None = None
    date_end: date | None = None
    null_days: int = Field(0, ge=0)
    path: str | None = None
    error: str | None = None
    source: str = "coinmetrics"
    license: str = LICENSE_NOTE

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


def asset_metrics_rows_to_frame(payload: object, *, metric: str) -> pl.DataFrame:
    """Pure parser: CoinMetrics ``asset-metrics`` JSON -> Polars ``date``/``value``.

    Captured shape (2026-09-10, live ``GET /v4/timeseries/asset-metrics``)::

        {"data": [
            {"asset": "btc", "time": "2018-01-01T00:00:00.000000000Z",
             "CapMVRVCur": "2.69423548"},
            ...
        ]}

    Values arrive as strings (CoinMetrics' convention for numeric precision);
    rows with a missing/non-numeric value or unparseable timestamp are
    dropped rather than raising. Unrecognized payloads return an empty frame.
    """
    if not isinstance(payload, dict):
        return _empty_frame()
    rows = payload.get("data")
    if not isinstance(rows, list):
        return _empty_frame()
    dates: list[date] = []
    values: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_time = row.get("time")
        raw_value = row.get(metric)
        if not isinstance(raw_time, str) or raw_value is None:
            continue
        try:
            parsed_date = datetime.fromisoformat(raw_time.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        dates.append(parsed_date)
        values.append(value)
    if not dates:
        return _empty_frame()
    return pl.DataFrame({"date": dates, "value": values}).sort("date")


def write_series_parquet(frame: pl.DataFrame, path: Path | str) -> Path:
    """Persist ``date``/``value`` parquet under ``data/onchain/coinmetrics/``."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if "date" not in frame.columns or "value" not in frame.columns:
        raise ValueError(f"coinmetrics frame needs date/value columns, got {frame.columns}")
    out = frame.select(
        pl.col("date").cast(pl.Date),
        pl.col("value").cast(pl.Float64),
    )
    out.write_parquet(dest)
    return dest


def _result_from_frame(
    asset: str,
    metric: str,
    frame: pl.DataFrame,
    *,
    cache_dir: Path | None,
    error: str | None = None,
) -> CoinMetricsSeriesResult:
    path: str | None = None
    if error is None and cache_dir is not None and frame.height > 0:
        path = str(write_series_parquet(frame, Path(cache_dir) / f"{asset}_{metric}.parquet"))
    return CoinMetricsSeriesResult(
        asset=asset,
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


def _get_json(
    url: str,
    *,
    timeout: float,
    session: _HttpGet | None,
    params: dict[str, str | int],
) -> object:
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    caller = session if session is not None else httpx
    resp = caller.get(url, headers=headers, timeout=timeout, params=params)
    resp.raise_for_status()
    return resp.json()


class CoinMetricsClient:
    """GET a CoinMetrics community ``asset-metrics`` series. Fail-soft; injectable session."""

    def __init__(
        self,
        *,
        base_url: str = COINMETRICS_BASE_URL,
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
        metric: str,
        *,
        asset: str = "btc",
        start_time: str | None = None,
        end_time: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> CoinMetricsSeriesResult:
        metric = metric.strip()
        asset = asset.strip().lower()
        if not metric or not asset:
            return CoinMetricsSeriesResult(
                asset=asset or "?", metric=metric or "?", error="asset and metric are required"
            )
        url = f"{self.base_url}/timeseries/asset-metrics"
        params: dict[str, str | int] = {
            "assets": asset,
            "metrics": metric,
            "frequency": "1d",
            "page_size": page_size,
        }
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        try:
            payload = _get_json(url, timeout=self.timeout, session=self.session, params=params)
        except Exception as exc:  # transport/HTTP — never crash the caller
            logger.warning("coinmetrics fetch of %s/%s failed: %s", asset, metric, exc)
            return CoinMetricsSeriesResult(
                asset=asset, metric=metric, error=f"{type(exc).__name__}: {exc}"
            )
        frame = asset_metrics_rows_to_frame(payload, metric=metric)
        if frame.height == 0:
            return CoinMetricsSeriesResult(
                asset=asset,
                metric=metric,
                error="no data (unknown asset/metric, or not on the community tier)",
            )
        return _result_from_frame(asset, metric, frame, cache_dir=self.cache_dir)


def _fetch_enabled() -> bool:
    """Kill-switch for *library* auto-fetch. MCP invocation is itself opt-in."""
    raw = os.environ.get(_ENV_FLAG, "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def fetch_coinmetrics_series(
    metric: str,
    *,
    asset: str = "btc",
    start_time: str | None = None,
    end_time: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    cache_dir: Path | str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    session: _HttpGet | None = None,
    base_url: str = COINMETRICS_BASE_URL,
) -> CoinMetricsSeriesResult:
    """Fetch one CoinMetrics community metric. Always fail-soft. Inject ``session`` in tests (no network)."""
    if session is None and not _fetch_enabled():
        return CoinMetricsSeriesResult(
            asset=asset, metric=metric, error=f"{_ENV_FLAG} disabled (no network)"
        )
    client = CoinMetricsClient(base_url=base_url, timeout=timeout, session=session, cache_dir=cache_dir)
    return client.fetch(metric, asset=asset, start_time=start_time, end_time=end_time, page_size=page_size)


__all__ = [
    "COINMETRICS_BASE_URL",
    "DEFAULT_CACHE_DIR",
    "DEFAULT_PAGE_SIZE",
    "KNOWN_COMMUNITY_METRICS",
    "LICENSE_NOTE",
    "CoinMetricsClient",
    "CoinMetricsSeriesResult",
    "asset_metrics_rows_to_frame",
    "fetch_coinmetrics_series",
    "write_series_parquet",
]
