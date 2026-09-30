"""Unit tests for digifetch_prediction_markets (#4813).

Deterministic and offline: an ``httpx.MockTransport`` drives the real
``digifetch.HttpFetcher`` (with ``allowed_hosts`` covering the venue hosts so
the SSRF guard is exercised without a socket). The Polymarket Gamma and Kalshi
trade fixtures below mirror the shapes the gloom prediction-markets plugin
reads; the client parses them defensively.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    GloomberbClient,
    PredictionMarketsInput,
)

from digifetch import HttpFetcher, RateLimiter, RetryPolicy  # noqa: E402

VENUE_HOSTS = ["gamma-api.polymarket.com", "api.elections.kalshi.com"]

GAMMA_EVENTS = [
    {
        "id": "1001",
        "title": "Fed December decision",
        "slug": "fed-december-decision",
        "volume": "9999.0",
        "tags": [{"label": "Macro"}],
        "markets": [
            {
                "question": "25bp hike in December?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.25", "0.75"]',
                "volume": "1234.5",
                "liquidity": "567.8",
                "endDate": "2026-12-16T00:00:00Z",
            }
        ],
    }
]

KALSHI_EVENTS = {
    "events": [
        {
            "event_ticker": "FED-26",
            "title": "Fed December decision",
            "category": "Economics",
            "markets": [
                {
                    "ticker": "FED-26-Y1",
                    "yes_bid": 24,
                    "yes_ask": 26,
                    "last_price": 25,
                    "volume": 1000,
                    "open_interest": 500,
                    "close_time": "2026-12-16T00:00:00Z",
                    "status": "open",
                }
            ],
        }
    ]
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GLOOMBERB_ENABLED_ENV, raising=False)
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)


def make_client(handler: Any, **kwargs: Any) -> GloomberbClient:
    allowed_hosts = kwargs.pop("allowed_hosts", VENUE_HOSTS)
    fetcher = HttpFetcher(
        transport=httpx.MockTransport(handler),
        allowed_hosts=allowed_hosts,
    )
    kwargs.setdefault("rate_limiter", RateLimiter(0))
    kwargs.setdefault("retry_policy", RetryPolicy(attempts=1))
    return GloomberbClient(fetcher=fetcher, **kwargs)


def venue_handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if host == "gamma-api.polymarket.com":
        return httpx.Response(200, json=GAMMA_EVENTS)
    if host == "api.elections.kalshi.com":
        return httpx.Response(200, json=KALSHI_EVENTS)
    return httpx.Response(404, json={"message": "unexpected host"})


def test_polymarket_catalog_maps_yes_prob_and_deep_link() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return venue_handler(request)

    result = make_client(handler).prediction_markets(PredictionMarketsInput(venue="polymarket"))
    assert "gamma-api.polymarket.com/events" in seen["url"]
    rows = result.data.markets  # type: ignore[union-attr]
    assert len(rows) == 1
    assert rows[0].venue == "polymarket"
    assert rows[0].yes_prob == pytest.approx(0.25)
    assert rows[0].volume_24h == pytest.approx(1234.5)
    assert "polymarket.com/event/fed-december-decision" in rows[0].venue_url
    assert result.data.warnings == []  # type: ignore[union-attr]
    assert "Polymarket" in result.data.attribution  # type: ignore[union-attr]
    assert "Gloomberb" not in result.data.attribution  # type: ignore[union-attr]


def test_kalshi_catalog_maps_cents_and_open_interest() -> None:
    result = make_client(venue_handler).prediction_markets(PredictionMarketsInput(venue="kalshi"))
    rows = result.data.markets  # type: ignore[union-attr]
    assert len(rows) == 1
    assert rows[0].venue == "kalshi"
    assert rows[0].yes_prob == pytest.approx(0.25)
    assert rows[0].spread == pytest.approx(0.02)
    assert rows[0].open_interest == pytest.approx(500.0)
    assert "kalshi.com/markets/FED-26-Y1" in rows[0].venue_url
    assert result.data.warnings == []  # type: ignore[union-attr]


def test_query_filters_rows_client_side() -> None:
    result = make_client(venue_handler).prediction_markets(
        PredictionMarketsInput(query="unrelated query text")
    )
    assert result.data.markets == []  # type: ignore[union-attr]


def test_invalid_venue_makes_no_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return venue_handler(request)

    result = make_client(handler).prediction_markets({"venue": "betfair"})  # type: ignore[arg-type]
    assert result.data.code == "invalid_input"  # type: ignore[union-attr]
    assert calls == []


def test_partial_venue_failure_warns_and_keeps_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gamma-api.polymarket.com":
            return httpx.Response(500, json={"message": "boom"})
        return venue_handler(request)

    result = make_client(handler).prediction_markets()
    rows = result.data.markets  # type: ignore[union-attr]
    assert len(rows) == 1
    assert rows[0].venue == "kalshi"
    warnings = result.data.warnings  # type: ignore[union-attr]
    assert len(warnings) == 1
    assert "Polymarket" in warnings[0]


def test_both_venues_failing_maps_to_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    result = make_client(handler).prediction_markets()
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
