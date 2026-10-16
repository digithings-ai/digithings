"""Fear & Greed Index (alternative.me) — Polars-only, fail-soft.

Read-only client for the free, no-auth alternative.me Crypto Fear & Greed
Index (``https://api.alternative.me/fng/``). A sentiment-class daily series,
structurally distinct from every price/on-chain valuation transform already
in ``indicator_catalog.py`` — not a derivative of ``power_law``, ``m2``,
``dxy``, or any Bitview on-chain ratio. Network is opt-in via an env flag;
tests inject a session and never hit the network.

Index convention: 0 = Extreme Fear, 100 = Extreme Greed. Historically read
as a *contrarian* signal — extreme fear has coincided with local bottoms,
extreme greed with local tops — so a valuation-style indicator built on top
of this raw series should sign-flip it (high raw value → low "buy opportunity"
z-score), matching the existing on-chain ratio indicators' sign convention.
That transform belongs in ``indicator_catalog.py``, not here: this module
only fetches and parses the raw 0-100 series.

HTTP is split from parsing: ``fng_payload_to_frame`` is HTTP-free (unit-tested
against a captured payload shape); ``FearGreedClient.fetch`` adds timeout +
fail-soft. Mirrors ``data/onchain/bitview.py``.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol  # score:allow untyped any — raw FNG JSON payload

import httpx
import polars as pl
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

FNG_BASE_URL = "https://api.alternative.me"
DEFAULT_CACHE_DIR = Path("data/onchain/fear_greed")
DEFAULT_TIMEOUT = 30.0
_USER_AGENT = "digiquant-research/1.0 (+https://digiquant.io)"
_ENV_FLAG = "DIGIQUANT_FNG_FETCH"
LICENSE_NOTE = (
    "alternative.me Crypto Fear & Greed Index. Free, no-auth public API. "
    "No published SLA -- fail-soft, do not block a run on this fetch failing."
)


class FearGreedResult(BaseModel):
    """One fetch attempt: parquet path + coverage, or a fail-soft error."""

    model_config = ConfigDict(frozen=True, strict=True)

    row_count: int = Field(0, ge=0)
    date_start: date | None = None
    date_end: date | None = None
    path: str | None = None
    error: str | None = None
    source: str = "alternative.me"
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


def fng_payload_to_frame(payload: object) -> pl.DataFrame:
    """Pure parser: alternative.me FNG JSON -> ``date``/``value`` Polars.

    Captured shape (2026-09-17)::

        {"name": "Fear and Greed Index",
         "data": [{"value": "50", "value_classification": "Neutral",
                    "timestamp": "1789603200", "time_until_update": "35586"}, ...],
         "metadata": {"error": null}}

    ``value`` is 0-100 (string in the payload). ``timestamp`` is Unix
    seconds, UTC, one row per calendar day. Unrecognized payloads or rows
    return an empty frame / are skipped rather than raising.
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
        raw_value = row.get("value")
        raw_ts = row.get("timestamp")
        if raw_value is None or raw_ts is None:
            continue
        try:
            value = float(raw_value)
            ts = int(raw_ts)
        except (TypeError, ValueError):
            continue
        dates.append(datetime.fromtimestamp(ts, tz=timezone.utc).date())
        values.append(value)
    if not dates:
        return _empty_frame()
    return (
        pl.DataFrame({"date": dates, "value": values})
        .unique(subset=["date"], keep="first")
        .sort("date")
    )


def write_fng_parquet(frame: pl.DataFrame, path: Path | str) -> Path:
    """Persist ``date``/``value`` parquet under ``data/onchain/fear_greed/``."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if "date" not in frame.columns or "value" not in frame.columns:
        raise ValueError(f"fear_greed frame needs date/value columns, got {frame.columns}")
    out = frame.select(
        pl.col("date").cast(pl.Date),
        pl.col("value").cast(pl.Float64),
    )
    out.write_parquet(dest)
    return dest


def _result_from_frame(
    frame: pl.DataFrame,
    *,
    cache_dir: Path | None,
    error: str | None = None,
) -> FearGreedResult:
    path: str | None = None
    if error is None and cache_dir is not None and frame.height > 0:
        path = str(write_fng_parquet(frame, Path(cache_dir) / "fear_greed.parquet"))
    return FearGreedResult(
        row_count=frame.height,
        date_start=frame["date"][0] if frame.height else None,
        date_end=frame["date"][-1] if frame.height else None,
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
    params: dict[str, str | int] | None = None,
) -> object:
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    caller = session if session is not None else httpx
    resp = caller.get(url, headers=headers, timeout=timeout, params=params)
    resp.raise_for_status()
    return resp.json()


class FearGreedClient:
    """GET alternative.me FNG series. Fail-soft; injectable session for tests."""

    def __init__(
        self,
        *,
        base_url: str = FNG_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        session: _HttpGet | None = None,
        cache_dir: Path | str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None

    def fetch(self, *, limit: int = 0) -> FearGreedResult:
        """Fetch the full history by default (``limit=0``, alternative.me convention)."""
        url = f"{self.base_url}/fng/"
        params: dict[str, str | int] = {"limit": limit, "format": "json"}
        try:
            payload = _get_json(url, timeout=self.timeout, session=self.session, params=params)
        except Exception as exc:  # transport/HTTP -- never crash the caller
            logger.warning("Fear & Greed fetch failed: %s", exc)
            return FearGreedResult(error=f"{type(exc).__name__}: {exc}")
        frame = fng_payload_to_frame(payload)
        if frame.height == 0:
            return FearGreedResult(error="no data")
        return _result_from_frame(frame, cache_dir=self.cache_dir)


def _fetch_enabled() -> bool:
    """Kill-switch for *library* auto-fetch."""
    raw = os.environ.get(_ENV_FLAG, "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def fetch_fear_greed(
    *,
    cache_dir: Path | str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    session: _HttpGet | None = None,
    limit: int = 0,
    base_url: str = FNG_BASE_URL,
) -> FearGreedResult:
    """Fetch the FNG series. Always fail-soft. Inject ``session`` in tests (no network)."""
    if session is None and not _fetch_enabled():
        return FearGreedResult(error=f"{_ENV_FLAG} disabled (no network)")
    client = FearGreedClient(base_url=base_url, timeout=timeout, session=session, cache_dir=cache_dir)
    return client.fetch(limit=limit)


__all__ = [
    "DEFAULT_CACHE_DIR",
    "FNG_BASE_URL",
    "LICENSE_NOTE",
    "FearGreedClient",
    "FearGreedResult",
    "fetch_fear_greed",
    "fng_payload_to_frame",
    "write_fng_parquet",
]
