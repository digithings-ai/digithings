"""Paging on the MCP ``web_search`` tool with ``provider="exa"`` (#4234, #4241, #4711).

EXA ``POST /search`` has no offset parameter and caps ``numResults`` upstream
(the 1-100 bound pinned by ``monitors/models.py`` / #4123), so paging is a
client-side slice of one enlarged window. These tests pin the MCP surface of
the unified tool (the old ``exa_web_search`` was folded into
``web_search(provider="exa")`` by #4711): deterministic non-overlapping pages
as JSON, the window cap enforced before any POST, an explicit error for
windows past the cap (never a silent truncated page), an explicit empty page
past the query's result count, a default call that stays byte-identical to
the unpaged output, and the HTTP-route parity of the same paging math (#4241).
"""

from __future__ import annotations

import json

import pytest

from digisearch import mcp_server, web_exa

pytestmark = pytest.mark.unit


def _page_results(n: int) -> list[dict]:
    return [{"title": f"t{i}", "url": f"https://example.com/{i}"} for i in range(1, n + 1)]


def _patch_exa_post(monkeypatch, results: list[dict], seen: dict) -> None:
    """Fake EXA POST honoring ``numResults`` (returns at most that many results)."""

    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            return {"results": results[: seen["payload"]["numResults"]], "searchType": "auto"}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["payload"] = json
        seen.setdefault("payloads", []).append(json)
        return FakeResp()

    monkeypatch.setattr(web_exa.httpx, "post", fake_post)


@pytest.fixture
def _exa(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")


def test_tool_is_registered_with_provider_and_offset(_exa):
    pytest.importorskip("mcp.server.fastmcp")
    tool = next(t for t in mcp_server.mcp._tool_manager.list_tools() if t.name == "web_search")
    props = tool.parameters["properties"]
    assert "offset" in props
    assert "provider" in props
    assert "effort" in props


def test_default_call_output_is_byte_identical(_exa, monkeypatch):
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(8), seen)
    out = mcp_server.web_search("blog post about AI", provider="exa", max_results=8)
    explicit = mcp_server.web_search("blog post about AI", provider="exa", max_results=8, offset=0)
    assert out == explicit
    data = json.loads(out)
    assert data["provider"] == "exa"
    assert [r["url"] for r in data["results"]] == [f"https://example.com/{i}" for i in range(1, 9)]
    assert seen["payloads"][0] == seen["payloads"][1]
    assert seen["payload"]["numResults"] == 8
    assert "offset" not in seen["payload"]


def test_page2_is_deterministic_and_non_overlapping(_exa, monkeypatch):
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(16), seen)
    page1 = json.loads(mcp_server.web_search("q", provider="exa", max_results=8))
    page2 = json.loads(mcp_server.web_search("q", provider="exa", max_results=8, offset=8))
    urls1 = [r["url"] for r in page1["results"]]
    urls2 = [r["url"] for r in page2["results"]]
    assert urls1 == [f"https://example.com/{i}" for i in range(1, 9)]
    assert urls2 == [f"https://example.com/{i}" for i in range(9, 17)]
    assert not set(urls1) & set(urls2)
    assert seen["payloads"][0]["numResults"] == 8
    assert seen["payloads"][1]["numResults"] == 16


def test_page_past_the_cap_is_an_explicit_error(_exa, monkeypatch):
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    out = mcp_server.web_search("q", provider="exa", max_results=8, offset=100)
    assert out.startswith("[web_search error:")
    assert "100" in out
    assert "payloads" not in seen


def test_window_clipped_by_the_cap_errors_before_any_post(_exa, monkeypatch):
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    out = mcp_server.web_search("q", provider="exa", max_results=8, offset=95)
    assert out.startswith("[web_search error:")
    assert "cap" in out
    assert "payloads" not in seen


def test_empty_page_past_the_result_count_is_explicit(_exa, monkeypatch):
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(3), seen)
    out = mcp_server.web_search("q", provider="exa", max_results=8, offset=8)
    data = json.loads(out)
    assert data["results"] == []  # an explicit empty page, not a re-sliced page 1
    assert data["provider"] == "exa"


def test_offset_on_a_provider_without_paging_is_an_explicit_error(monkeypatch):
    """internal can't page: offset > 0 errors instead of silently returning page 1."""
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    out = mcp_server.web_search("q", offset=8)
    assert out.startswith("[web_search error:")
    assert "offset" in out


def test_http_page2_matches_mcp_page2(_exa, monkeypatch):
    """The HTTP route slices the same window into the same page (#4241 parity)."""
    from digisearch.server import app
    from fastapi.testclient import TestClient

    from tests.digi_test_jwt import auth_headers

    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(16), seen)
    client = TestClient(app, headers=auth_headers())
    resp = client.post(
        "/v1/web_search",
        json={"query": "q", "provider": "exa", "max_results": 8, "offset": 8},
    )
    assert resp.status_code == 200, resp.text
    http_urls = [r["url"] for r in resp.json()["results"]]
    mcp_data = json.loads(mcp_server.web_search("q", provider="exa", max_results=8, offset=8))
    assert http_urls == [f"https://example.com/{i}" for i in range(9, 17)]
    assert [r["url"] for r in mcp_data["results"]] == http_urls
    # Both surfaces enlarged the window to offset + max_results on the wire.
    assert [p["numResults"] for p in seen["payloads"]] == [16, 16]
