"""Stack image ships [web-search] so hosted :8765 web_search stays available (refs #3854)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digisearch import mcp_server

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_stack_dockerfile_installs_web_search_extra():
    text = (ROOT / "Dockerfile.digithings-stack-cloudflare").read_text()
    line = next(
        line for line in text.splitlines() if "digisearch[" in line and "uv pip install" in line
    )
    assert "web-search" in line


@pytest.mark.unit
def test_web_search_registered_on_mcp_singleton():
    sync_names = {tool.name for tool in mcp_server.mcp._tool_manager.list_tools()}
    assert "web_search" in sync_names
    async_tools = asyncio.run(mcp_server.mcp.list_tools())
    assert any(tool.name == "web_search" for tool in async_tools)


@pytest.mark.unit
def test_run_web_search_prefers_searxng_falls_back_to_ddgs_no_network(
    monkeypatch: pytest.MonkeyPatch,
):
    from digisearch.web_search import service as svc
    from digisearch.web_search.models import (
        WebSearchRequest,
        WebSearchResponse,
        WebSearchResult,
    )

    attempted: list[str] = []

    def boom(req):
        attempted.append("searxng")
        raise RuntimeError("searxng down")

    class Ok:
        name = "ddgs"

        def search(self, req):
            attempted.append("ddgs")
            return WebSearchResponse(
                query=req.query,
                provider="ddgs",
                results=[WebSearchResult(url="https://a.com/1", title="A", snippet="s")],
            )

    class _Fetcher:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def fetch(self, url):
            raise RuntimeError("no network in unit")

    monkeypatch.setattr(
        svc,
        "SearXNGWebSearchProvider",
        lambda **k: type("S", (), {"search": staticmethod(boom), "name": "searxng"})(),
    )
    monkeypatch.setattr(svc, "DdgsWebSearchProvider", Ok)
    monkeypatch.setattr(svc, "HttpFetcher", _Fetcher)
    resp = svc.run_web_search(WebSearchRequest(query="etf"), config=svc.WebSearchConfig())
    assert attempted[0] == "searxng"
    assert resp.provider == "ddgs"
    assert resp.results and resp.results[0].url == "https://a.com/1"
