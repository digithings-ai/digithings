"""Offline grokipedia MCP client + tools (spike). No live network."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.unit

_SEARCH_JSON = {
    "results": [
        {
            "slug": "Bitcoin",
            "title": "Bitcoin",
            "snippet": "A peer-to-peer electronic cash system.",
            "viewCount": 123,
        }
    ],
    "totalCount": 1,
}

_PAGE_JSON = {
    "found": True,
    "page": {
        "slug": "Bitcoin",
        "title": "Bitcoin",
        "content": "Bitcoin is a cryptocurrency.",
    },
}


class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


def _client(
    handler: Any,
    *,
    content_cap: int | None = None,
    min_interval: float = 0.0,
) -> Any:
    from digisearch.grokipedia.client import GrokipediaClient
    from digisearch.grokipedia.rate_limit import PoliteLimiter

    clock = _FakeClock()
    limiter = PoliteLimiter(
        min_interval=min_interval,
        capacity=10.0,
        refill_per_s=100.0,
        clock=clock.now,
        sleep=clock.sleep,
    )
    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://grokipedia.com",
    )
    kwargs: dict[str, Any] = {"http_client": http, "limiter": limiter}
    if content_cap is not None:
        kwargs["content_cap"] = content_cap
    client = GrokipediaClient(**kwargs)
    client._clock = clock  # type: ignore[attr-defined]
    return client


def test_search_hits_full_text_search_and_parses_results() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_SEARCH_JSON)

    client = _client(handler)
    out = client.search("bitcoin", limit=5)
    assert out.ok is True
    assert out.query == "bitcoin"
    assert len(out.results) == 1
    assert out.results[0].slug == "Bitcoin"
    assert out.results[0].title == "Bitcoin"
    assert "peer-to-peer" in out.results[0].snippet
    assert out.total_count == 1
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/full-text-search"
    assert seen[0].url.params["query"] == "bitcoin"
    assert seen[0].url.params["limit"] == "5"


def test_get_page_uses_page_preview_not_api_page() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=_PAGE_JSON)

    client = _client(handler)
    out = client.get_page("Bitcoin", include_content=True)
    assert out.ok is True
    assert out.found is True
    assert out.page is not None
    assert out.page.slug == "Bitcoin"
    assert out.page.content.startswith("Bitcoin is")
    assert seen == ["/api/page-preview"]
    assert "/api/page" not in seen
    assert not any(p.startswith("/page/") for p in seen)


def test_get_page_include_content_false_sends_site_preview_flag() -> None:
    params: list[httpx.QueryParams] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params.append(request.url.params)
        return httpx.Response(200, json=_PAGE_JSON)

    client = _client(handler)
    client.get_page("Bitcoin", include_content=False)
    assert params[0]["slug"] == "Bitcoin"
    assert params[0].get("content") == "0"


def test_get_page_include_content_true_sends_include_content() -> None:
    params: list[httpx.QueryParams] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params.append(request.url.params)
        return httpx.Response(200, json=_PAGE_JSON)

    client = _client(handler)
    client.get_page("Bitcoin", include_content=True)
    assert params[0]["slug"] == "Bitcoin"
    assert params[0].get("includeContent") == "true"


def test_get_page_truncates_content_with_marker() -> None:
    body = {
        "found": True,
        "page": {"slug": "Long", "title": "Long", "content": "x" * 200},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    client = _client(handler, content_cap=50)
    out = client.get_page("Long")
    assert out.ok is True
    assert out.page is not None
    assert out.page.truncated is True
    assert out.page.content.startswith("x" * 50)
    assert "[truncated: 150 chars omitted]" in out.page.content
    assert len(out.page.content) < 200 + 40


def test_http_errors_are_json_envelopes_not_exceptions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    client = _client(handler)
    search = client.search("bitcoin")
    page = client.get_page("Bitcoin")
    assert search.ok is False
    assert page.ok is False
    assert search.status_code == 503
    assert page.status_code == 503
    assert search.retryable is True
    assert "503" in search.error


def test_timeout_is_json_envelope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    client = _client(handler)
    out = client.search("bitcoin")
    assert out.ok is False
    assert out.retryable is True
    assert "timeout" in out.error.lower() or "timed out" in out.error.lower()


def test_empty_query_and_slug_do_not_hit_network() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_SEARCH_JSON)

    client = _client(handler)
    q = client.search("   ")
    s = client.get_page("")
    assert q.ok is False
    assert s.ok is False
    assert "required" in q.error.lower()
    assert "required" in s.error.lower()
    assert calls == 0


def test_url_slug_is_rejected_without_html_fetch() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="<html>nope</html>")

    client = _client(handler)
    out = client.get_page("https://grokipedia.com/page/Bitcoin")
    assert out.ok is False
    assert calls == []


def test_request_headers_set_user_agent_and_accept() -> None:
    from digisearch.grokipedia.client import USER_AGENT

    headers_seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        headers_seen.append(request.headers)
        return httpx.Response(200, json=_SEARCH_JSON)

    client = _client(handler)
    client.search("bitcoin")
    assert headers_seen[0]["user-agent"] == USER_AGENT
    assert headers_seen[0]["accept"] == "application/json"
    assert USER_AGENT.startswith("digithings-digisearch-grokipedia/0.1")


def test_polite_limiter_enforces_min_interval() -> None:
    from digisearch.grokipedia.rate_limit import PoliteLimiter

    clock = _FakeClock()
    limiter = PoliteLimiter(
        min_interval=0.3,
        capacity=10.0,
        refill_per_s=100.0,
        clock=clock.now,
        sleep=clock.sleep,
    )
    assert limiter.acquire() == 0.0
    waited = limiter.acquire()
    assert waited == pytest.approx(0.3)
    assert clock.slept == [0.3]


def test_polite_limiter_token_bucket_blocks_when_empty() -> None:
    from digisearch.grokipedia.rate_limit import PoliteLimiter

    clock = _FakeClock()
    limiter = PoliteLimiter(
        min_interval=0.0,
        capacity=1.0,
        refill_per_s=2.0,
        clock=clock.now,
        sleep=clock.sleep,
    )
    assert limiter.acquire() == 0.0
    waited = limiter.acquire()
    assert waited == pytest.approx(0.5)
    assert clock.slept == [0.5]


def test_client_acquires_limiter_before_each_call() -> None:
    acquires: list[str] = []

    class _Spy:
        def acquire(self) -> float:
            acquires.append("acquire")
            return 0.0

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SEARCH_JSON)

    from digisearch.grokipedia.client import GrokipediaClient

    client = GrokipediaClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://grokipedia.com",
        ),
        limiter=_Spy(),  # type: ignore[arg-type]
    )
    client.search("a")
    client.search("b")
    assert acquires == ["acquire", "acquire"]


def test_tools_return_json_and_never_raise_on_http_error() -> None:
    from digisearch.grokipedia import tools

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    client = _client(handler)
    tools.set_client(client)
    try:
        raw = tools.grokipedia_search("bitcoin")
        payload = json.loads(raw)
        assert payload["ok"] is False
        assert payload["status_code"] == 429
        assert payload["retryable"] is True
        raw_page = tools.grokipedia_get_page("Bitcoin")
        page = json.loads(raw_page)
        assert page["ok"] is False
    finally:
        tools.set_client(None)


def test_module_notes_robots_disallow() -> None:
    import digisearch.grokipedia as pkg

    doc = (pkg.__doc__ or "").lower()
    assert "disallow: /api/" in doc
    assert "unofficial" in doc
    assert "spike" in doc


def test_mcp_tools_registered() -> None:
    pytest.importorskip("mcp.server.fastmcp")
    from digisearch import mcp_server

    names = {tool.name for tool in mcp_server.mcp._tool_manager.list_tools()}
    assert "grokipedia_search" in names
    assert "grokipedia_get_page" in names
