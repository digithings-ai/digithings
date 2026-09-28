"""External provider adapters for the unified ``web_search`` tool (#4711).

Every vendor call goes through ``digisearch.web_providers.base.request_json``
(httpx only — no vendor SDKs), so these tests fake ``httpx.request`` and pin
the wire contract each adapter builds: URL, auth header, payload keys, and the
result mapping back onto ``WebSearchResponse``. No live API verification.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from digisearch.server import app
from digisearch.web_providers import base as providers_base
from digisearch.web_providers import get_provider
from digisearch.web_providers.base import WebProviderError, request_json, require_dict
from digisearch.web_search.models import WebSearchRequest
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, payload: Any, status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _patch_request(
    monkeypatch: pytest.MonkeyPatch,
    payload: Any,
    seen: dict,
    *,
    status_code: int = 200,
    text: str = "",
) -> None:
    """Route every provider HTTP call into ``seen`` instead of the network."""

    def fake_request(
        method: str,
        url: str,
        headers: dict | None = None,
        json: dict | None = None,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> _Resp:
        seen.update(
            method=method,
            url=url,
            headers=headers or {},
            json=json,
            params=params,
            timeout=timeout,
        )
        return _Resp(payload, status_code=status_code, text=text)

    monkeypatch.setattr(providers_base.httpx, "request", fake_request)


# --- tavily -------------------------------------------------------------------


def test_tavily_payload_and_result_mapping(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-key")
    seen: dict = {}
    _patch_request(
        monkeypatch,
        {
            "results": [
                {
                    "url": "https://a.com/1",
                    "title": "A",
                    "content": "body text",
                    "score": 0.87,
                    "published_date": "Tue, 11 Mar 2025 17:00:00 GMT",
                    "author": "Jane Doe",
                }
            ],
            "usage": {"credits": 3},
            "response_time": 1.2,
            "answer": "because reasons",
        },
        seen,
    )
    resp = get_provider("tavily").search(
        WebSearchRequest(
            query="q",
            max_results=3,
            include_domains=["a.com"],
            recency_days=7,
            effort="thorough",
        )
    )
    assert seen["method"] == "POST"
    assert seen["url"] == "https://api.tavily.com/search"
    assert seen["headers"]["Authorization"] == "Bearer tvly-key"
    body = seen["json"]
    assert body["query"] == "q"
    assert body["max_results"] == 3
    assert body["include_domains"] == ["a.com"]
    assert body["time_range"] == "week"
    assert body["search_depth"] == "advanced"  # thorough -> advanced
    assert body["include_usage"] is True

    assert resp.provider == "tavily"
    row = resp.results[0]
    assert row.url == "https://a.com/1"
    assert row.snippet == "body text"
    assert row.score == 0.87 and row.engine == "tavily"
    assert row.published_date == "Tue, 11 Mar 2025 17:00:00 GMT"
    assert row.author == "Jane Doe"
    # Credits are not dollars: they live in `output` so `cost_dollars` stays honest.
    assert resp.cost_dollars is None
    assert resp.output == {"credits": 3, "response_time": 1.2, "answer": "because reasons"}


def test_tavily_fast_effort_maps_to_fast_depth(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-key")
    seen: dict = {}
    _patch_request(monkeypatch, {"results": []}, seen)
    get_provider("tavily").search(WebSearchRequest(query="q", effort="fast", recency_days=None))
    assert seen["json"]["search_depth"] == "fast"
    assert "time_range" not in seen["json"]  # recency_days=None omits it


# --- parallel -----------------------------------------------------------------


def test_parallel_payload_and_result_mapping(monkeypatch):
    monkeypatch.setenv("PARALLEL_API_KEY", "par-key")
    seen: dict = {}
    _patch_request(
        monkeypatch,
        {
            "results": [
                {
                    "url": "https://a.com/1",
                    "title": "A",
                    "excerpts": ["first excerpt", "second excerpt"],
                    "publish_date": "2026-01-02",
                }
            ],
            "search_id": "s-1",
        },
        seen,
    )
    resp = get_provider("parallel").search(
        WebSearchRequest(
            query="q",
            purpose="find funding rounds",
            effort="fast",
            include_domains=["a.com"],
            recency_days=7,
        )
    )
    assert seen["method"] == "POST"
    assert seen["url"] == "https://api.parallel.ai/v1/search"
    assert seen["headers"]["x-api-key"] == "par-key"
    body = seen["json"]
    assert body["search_queries"] == ["q"]
    assert body["mode"] == "fast"
    assert body["objective"] == "find funding rounds"
    policy = body["advanced_settings"]["source_policy"]
    assert policy["include_domains"] == ["a.com"]
    assert "after_date" in policy

    assert resp.provider == "parallel"
    row = resp.results[0]
    assert row.snippet == "first excerpt second excerpt"
    assert row.score == 1.0 and row.engine == "parallel"
    assert row.published_date == "2026-01-02"
    assert resp.output == {"search_id": "s-1"}


def test_parallel_results_truncated_to_max_results(monkeypatch):
    monkeypatch.setenv("PARALLEL_API_KEY", "par-key")
    seen: dict = {}
    rows = [{"url": f"https://a.com/{i}", "title": f"t{i}"} for i in range(5)]
    _patch_request(monkeypatch, {"results": rows}, seen)
    resp = get_provider("parallel").search(WebSearchRequest(query="q", max_results=2))
    assert len(resp.results) == 2


# --- firecrawl ----------------------------------------------------------------


def test_firecrawl_payload_and_result_mapping(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-key")
    seen: dict = {}
    _patch_request(
        monkeypatch,
        {
            "data": {
                "web": [
                    {
                        "url": "https://a.com/1",
                        "title": "Web hit",
                        "description": "web description",
                        "date": "2026-09-01",
                    }
                ],
                "news": [
                    {
                        "url": "https://b.com/2",
                        "title": "News hit",
                        "snippet": "news snippet",
                        "date": "1 week ago",
                    }
                ],
            },
            "success": True,
        },
        seen,
    )
    resp = get_provider("firecrawl").search(
        WebSearchRequest(query="q", max_results=5, exclude_domains=["bad.com"], recency_days=7)
    )
    assert seen["method"] == "POST"
    assert seen["url"] == "https://api.firecrawl.dev/v2/search"
    assert seen["headers"]["Authorization"] == "Bearer fc-key"
    body = seen["json"]
    assert body["query"] == "q"
    assert body["limit"] == 5
    assert body["excludeDomains"] == ["bad.com"]
    assert body["tbs"] == "qdr:w"
    assert "includeDomains" not in body  # mutually exclusive upstream

    assert resp.provider == "firecrawl"
    # web rows first, then news; both normalised onto one ranked list.
    assert [r.url for r in resp.results] == ["https://a.com/1", "https://b.com/2"]
    assert resp.results[0].snippet == "web description"
    assert resp.results[1].snippet == "news snippet"
    assert resp.results[0].engine == "firecrawl"
    assert resp.results[1].published_date == "1 week ago"
    assert resp.output == {"success": True}


# --- tinyfish (tinyfish.ai) ---------------------------------------------------


def test_tinyfish_payload_and_result_mapping(monkeypatch):
    monkeypatch.setenv("TINYFISH_API_KEY", "tf-key")
    seen: dict = {}
    _patch_request(
        monkeypatch,
        {
            "results": [
                {
                    "url": "https://a.com/1",
                    "title": "A",
                    "snippet": "from publisher",
                    "publisher": "FishCo",
                    "date": "2026-09-01",
                },
                {
                    "url": "https://b.com/2",
                    "title": "B",
                    "snippet": "from authors",
                    "authors": ["Ann", "Bob"],
                    "year": 2024,
                },
            ],
            "total_results": 2,
            "request_id": "r-1",
        },
        seen,
    )
    resp = get_provider("tinyfish").search(
        WebSearchRequest(
            query="q",
            purpose="latest funding news",
            include_domains=["a.com", "b.com"],
            recency_days=2,
        )
    )
    assert seen["method"] == "GET"
    assert seen["url"] == "https://api.search.tinyfish.ai/"
    assert seen["headers"]["X-API-Key"] == "tf-key"
    params = seen["params"]
    assert params["query"] == "q"
    assert params["purpose"] == "latest funding news"
    assert params["include_domains"] == "a.com,b.com"
    assert params["recency_minutes"] == 2 * 1440  # minute-granular upstream

    assert resp.provider == "tinyfish"
    assert resp.results[0].author == "FishCo"
    assert resp.results[0].published_date == "2026-09-01"
    assert resp.results[1].author == "Ann, Bob"
    assert resp.results[1].published_date == "2024"  # year fallback
    assert resp.results[0].score == 1.0 and resp.results[1].score == 0.99
    assert resp.output == {"total_results": 2, "request_id": "r-1"}


# --- shared transport mapping (base.request_json) -----------------------------


def test_transport_timeout_is_retryable(monkeypatch):
    def _raise(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(providers_base.httpx, "request", _raise)
    with pytest.raises(WebProviderError) as excinfo:
        request_json("tavily", method="POST", url="https://example.com")
    assert excinfo.value.retryable is True


def test_429_is_retryable_and_401_is_not(monkeypatch):
    seen: dict = {}

    def _status(status_code: int):
        def _call(*args, **kwargs):
            seen["called"] = True
            return _Resp({}, status_code=status_code, text="upstream said no")

        return _call

    monkeypatch.setattr(providers_base.httpx, "request", _status(429))
    with pytest.raises(WebProviderError) as rate:
        request_json("tavily", method="POST", url="https://example.com")
    assert rate.value.retryable is True and rate.value.status_code == 429

    monkeypatch.setattr(providers_base.httpx, "request", _status(401))
    with pytest.raises(WebProviderError) as auth:
        request_json("tavily", method="POST", url="https://example.com")
    assert auth.value.retryable is False and auth.value.status_code == 401


def test_require_dict_rejects_non_object_payloads():
    with pytest.raises(WebProviderError) as excinfo:
        require_dict("tavily", ["not", "a", "dict"])
    assert excinfo.value.retryable is False


# --- route: provider failures stay the #4192 soft envelope --------------------


def test_route_external_provider_failure_is_soft_envelope(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-key")
    seen: dict = {}
    _patch_request(monkeypatch, {}, seen, status_code=500, text="boom")
    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/web_search", json={"query": "q", "provider": "tavily"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["retryable"] is True
    assert body["status_code"] == 500
    assert "boom" in body["error"]


def test_route_missing_key_stays_503_not_a_soft_envelope(monkeypatch):
    """A missing key is a config error (503), never the 200 outage envelope."""
    from digisearch.web_providers import EXTERNAL_PROVIDER_ENV

    for env in EXTERNAL_PROVIDER_ENV.values():
        monkeypatch.delenv(env, raising=False)
    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/web_search", json={"query": "q", "provider": "parallel"})
    assert resp.status_code == 503, resp.text
    assert "PARALLEL_API_KEY" in resp.text
