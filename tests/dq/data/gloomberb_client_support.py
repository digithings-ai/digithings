"""Shared support code for the digiquant gloomberb client tests.

The client test suite is split per upstream domain. The constants and the
three helpers every domain needs live here, so each domain module holds only
its own tests.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from digiquant.data.gloomberb import (
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    GloomberbClient,
)

from digifetch import HttpFetcher, RateLimiter, RetryPolicy

GBP_QUOTE = {
    "symbol": "VOD.L",
    "currency": "GBp",
    "price": 12345.0,
    "change": 10.0,
    "changePercent": 0.081,
    "lastUpdated": 1773000000000,
    "marketState": "CLOSED",
    "listingExchangeName": "LSE",
    "dataSource": "delayed",
}

AAPL_QUOTE = {
    "symbol": "AAPL",
    "currency": "USD",
    "price": 200.0,
    "change": 1.0,
    "changePercent": 0.5,
    "lastUpdated": 1773000000000,
    "marketState": "CLOSED",
    "listingExchangeName": "NASDAQ",
    "dataSource": "live",
}

INTRADAY_OUTLIER_POINTS = [
    {"date": "2026-02-23T14:30:00Z", "open": 100.0, "high": 100.5, "low": 99.8, "close": 100.0},
    {"date": "2026-02-23T14:35:00Z", "open": 400.0, "high": 401.0, "low": 399.0, "close": 100.2},
    {"date": "2026-02-23T14:40:00Z", "open": 100.2, "high": 100.4, "low": 100.0, "close": 100.1},
]


def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop the gloomberb env flags so a test starts from the same state."""
    monkeypatch.delenv(GLOOMBERB_ENABLED_ENV, raising=False)
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)


def make_client(handler: Any, **kwargs: Any) -> GloomberbClient:
    """Create a test client with the family enabled by default.

    Tests that need to exercise the kill switch via env var should pass
    ``enabled=None`` to force reading from ``GLOOMBERB_ENABLED``.
    """
    allowed_hosts = kwargs.pop("allowed_hosts", ["api.gloom.sh"])
    fetcher = HttpFetcher(
        transport=httpx.MockTransport(handler),
        allowed_hosts=allowed_hosts,
    )
    kwargs.setdefault("rate_limiter", RateLimiter(0))
    kwargs.setdefault("retry_policy", RetryPolicy(attempts=1))
    kwargs.setdefault("enabled", True)
    return GloomberbClient(fetcher=fetcher, **kwargs)


def envelope(data: Any, status: str = "success", **extra: Any) -> httpx.Response:
    payload = {"status": status, "data": data, **extra}
    return httpx.Response(200, json=payload)
