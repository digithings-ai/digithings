"""Unit tests for the grokipedia JSON spike (mocked HTTP, no network)."""

from __future__ import annotations

import json
from collections.abc import Generator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from digisearch.cli import app
from digisearch.grokipedia.client import (
    USER_AGENT,
    GrokipediaClient,
    GrokipediaError,
    GrokipediaNotFoundError,
    GrokipediaRateLimitError,
    GrokipediaRobotsError,
    SlidingWindowLimiter,
    allow_api_from_env,
    reset_shared_client,
)
from digisearch.grokipedia.tools import (
    CONTENT_PREVIEW_CHARS,
    grokipedia_get_page,
    grokipedia_search,
    grokipedia_typeahead,
)
from typer.testing import CliRunner

pytestmark = pytest.mark.unit


class _Clock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _client(
    handler: object,
    *,
    limiter: SlidingWindowLimiter | None = None,
) -> GrokipediaClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, follow_redirects=False)
    return GrokipediaClient(http_client=http, allow_api=True, limiter=limiter)


@pytest.fixture(autouse=True)
def _reset_shared() -> Generator[None]:
    reset_shared_client()
    yield
    reset_shared_client()


def test_allow_api_from_env_is_opt_in() -> None:
    assert allow_api_from_env({}) is False
    assert allow_api_from_env({"DIGISEARCH_GROKIPEDIA_ALLOW_API": "1"}) is True
    assert allow_api_from_env({"DIGISEARCH_GROKIPEDIA_ALLOW_API": "true"}) is True
    assert allow_api_from_env({"DIGISEARCH_GROKIPEDIA_ALLOW_API": "0"}) is False


def test_search_hits_json_endpoint_with_identifying_user_agent() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "slug": "Python",
                        "title": "Python",
                        "snippet": "A <em>language</em>.\n",
                        "viewCount": 12,
                    }
                ],
                "totalCount": 1,
            },
        )

    client = _client(handler)
    out = client.search("  python  ", limit=5)
    assert len(seen) == 1
    request = seen[0]
    parsed = urlparse(str(request.url))
    assert parsed.scheme == "https"
    assert parsed.netloc == "grokipedia.com"
    assert parsed.path == "/api/full-text-search"
    qs = parse_qs(parsed.query)
    assert qs["query"] == ["python"]
    assert qs["limit"] == ["5"]
    assert request.headers["user-agent"] == USER_AGENT
    assert "digithings" in USER_AGENT
    assert "digisearch" in USER_AGENT
    assert request.headers["accept"] == "application/json"
    assert len(out.results) == 1
    hit = out.results[0]
    assert hit.slug == "Python"
    assert hit.snippet == "A language."
    assert hit.view_count == 12
    assert hit.url == "https://grokipedia.com/page/Python"
    assert out.total_count == 1
    assert out.query == "python"


def test_search_clamps_limit_and_skips_malformed_hits() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200,
            json={"results": [{"title": "no slug"}, {"slug": "Ok", "title": "Ok"}]},
        )

    out = _client(handler).search("q", limit=999)
    assert "limit=50" in seen[0]
    assert [h.slug for h in out.results] == ["Ok"]


def test_get_page_uses_include_content_and_nested_page_object() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "page": {
                    "title": "Python",
                    "content": "Python is a language.",
                    "description": "A language",
                    "citations": [{"title": "Docs", "url": "https://docs.python.org"}],
                    "extraFieldIgnored": True,
                }
            },
        )

    page = _client(handler).get_page("Python")
    qs = parse_qs(urlparse(str(seen[0].url)).query)
    assert urlparse(str(seen[0].url)).path == "/api/page"
    assert qs["slug"] == ["Python"]
    assert qs["includeContent"] == ["true"]
    assert seen[0].headers["user-agent"] == USER_AGENT
    assert page.title == "Python"
    assert page.slug == "Python"
    assert page.content == "Python is a language."
    assert page.citations[0].url == "https://docs.python.org"
    assert page.url == "https://grokipedia.com/page/Python"


def test_typeahead_hits_json_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        assert parsed.path == "/api/typeahead"
        qs = parse_qs(parsed.query)
        assert qs["query"] == ["Py"]
        assert qs["limit"] == ["3"]
        return httpx.Response(
            200,
            json={"results": [{"slug": "Python", "title": "Python", "snippet": "lang"}]},
        )

    out = _client(handler).typeahead("Py", limit=3)
    assert [h.slug for h in out.results] == ["Python"]


def test_robots_opt_in_blocks_http_by_default() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"results": []})

    client = GrokipediaClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        allow_api=False,
    )
    with pytest.raises(GrokipediaRobotsError, match="Disallow: /api/"):
        client.search("python")
    assert calls["n"] == 0


def test_local_rate_limit_caps_at_thirty_per_window() -> None:
    clock = _Clock()
    limiter = SlidingWindowLimiter(max_requests=2, window_seconds=60.0, clock=clock)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"results": []})

    client = _client(handler, limiter=limiter)
    client.search("a")
    client.search("b")
    with pytest.raises(GrokipediaRateLimitError, match="rate limit"):
        client.search("c")
    assert calls["n"] == 2
    clock.t = 61.0
    client.search("d")
    assert calls["n"] == 3


def test_upstream_429_is_retryable_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    with pytest.raises(GrokipediaRateLimitError) as excinfo:
        _client(handler).search("q")
    assert excinfo.value.retryable is True
    assert excinfo.value.status_code == 429


def test_html_body_is_rejected_no_scrape_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body>Python</body></html>",
        )

    with pytest.raises(GrokipediaError, match="HTML"):
        _client(handler).search("python")


def test_non_json_body_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="not json",
        )

    with pytest.raises(GrokipediaError, match="non-JSON"):
        _client(handler).get_page("Python")


def test_get_page_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "missing"})

    with pytest.raises(GrokipediaNotFoundError, match="Python"):
        _client(handler).get_page("Python")


def test_empty_query_and_bad_slug_rejected_without_http() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={})

    client = _client(handler)
    with pytest.raises(ValueError, match="query"):
        client.search("  ")
    with pytest.raises(ValueError, match="slug"):
        client.get_page("../etc/passwd")
    with pytest.raises(ValueError, match="slug"):
        client.get_page("a/b")
    assert calls["n"] == 0


def test_tools_return_json_via_shared_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if path.endswith("full-text-search"):
            return httpx.Response(
                200,
                json={"results": [{"slug": "Python", "title": "Python", "snippet": "lang"}]},
            )
        if path.endswith("typeahead"):
            return httpx.Response(200, json={"results": [{"slug": "Python", "title": "Python"}]})
        return httpx.Response(
            200,
            json={"page": {"title": "Python", "content": "x" * (CONTENT_PREVIEW_CHARS + 50)}},
        )

    client = _client(handler)
    monkeypatch.setattr("digisearch.grokipedia.tools.get_shared_client", lambda: client)
    search = json.loads(grokipedia_search("python", limit=2))
    assert search["results"][0]["slug"] == "Python"
    page = json.loads(grokipedia_get_page("Python"))
    assert page["truncated"] is True
    assert len(page["content"]) == CONTENT_PREVIEW_CHARS
    ahead = json.loads(grokipedia_typeahead("Py"))
    assert ahead["results"][0]["slug"] == "Python"


def test_tools_fail_closed_on_robots(monkeypatch: pytest.MonkeyPatch) -> None:
    client = GrokipediaClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": []}))
        ),
        allow_api=False,
    )
    monkeypatch.setattr("digisearch.grokipedia.tools.get_shared_client", lambda: client)
    out = grokipedia_search("python")
    assert out.startswith("[grokipedia disabled:")
    assert "Disallow: /api/" in out


def test_mcp_tools_registered() -> None:
    pytest.importorskip("mcp.server.fastmcp")
    from digisearch import mcp_server

    names = {tool.name for tool in mcp_server.mcp._tool_manager.list_tools()}
    assert {"grokipedia_search", "grokipedia_get_page", "grokipedia_typeahead"} <= names


def test_default_limiter_is_thirty_per_minute() -> None:
    limiter = SlidingWindowLimiter()
    assert limiter.max_requests == 30
    assert limiter.window_seconds == 60.0


def test_cli_grokipedia_help_lists_commands() -> None:
    result = CliRunner().invoke(app, ["grokipedia", "--help"])
    assert result.exit_code == 0
    assert "search" in result.stdout
    assert "page" in result.stdout
    assert "typeahead" in result.stdout
