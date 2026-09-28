"""Paging on the shallow recall path: ``exa_web_search`` (#4234, #4241).

EXA ``POST /search`` has no offset parameter and caps ``numResults`` upstream
(the 1-100 bound pinned by ``monitors/models.py`` / #4123), so paging is a
client-side slice of one enlarged window. These tests pin the MCP surface:
deterministic non-overlapping pages, the window cap enforced before any POST,
an explicit error for windows past the cap (never a silent truncated page),
an explicit empty page past the query's result count, a default call that
stays byte-identical to the unpaged output, and the HTTP-route parity of the
same paging math (#4241).
"""

from __future__ import annotations

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


def test_tool_is_registered_with_offset(_exa):
    pytest.importorskip("mcp.server.fastmcp")
    tool = next(
        t for t in mcp_server.mcp._tool_manager.list_tools() if t.name == "exa_web_search"
    )
    assert "offset" in tool.parameters["properties"]


def test_default_call_output_is_byte_identical(_exa, monkeypatch):
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(8), seen)
    output = mcp_server.exa_web_search("blog post about AI")
    expected = web_exa.format_web_results(web_exa.exa_search("blog post about AI"))
    assert output == expected
    assert seen["payloads"][0] == seen["payloads"][1]
    assert seen["payload"]["numResults"] == 8
    assert "offset" not in seen["payload"]


def test_page2_is_deterministic_and_non_overlapping(_exa, monkeypatch):
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(16), seen)
    page1 = mcp_server.exa_web_search("q", num_results=8)
    page2 = mcp_server.exa_web_search("q", num_results=8, offset=8)
    for i in range(1, 9):
        assert page1.count(f"https://example.com/{i}\n") == 1
        assert f"https://example.com/{i}\n" not in page2
    for i in range(9, 17):
        assert page2.count(f"https://example.com/{i}\n") == 1
    assert seen["payloads"][0]["numResults"] == 8
    assert seen["payloads"][1]["numResults"] == 16


def test_page_past_the_cap_is_an_explicit_error(_exa, monkeypatch):
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    out = mcp_server.exa_web_search("q", num_results=8, offset=100)
    assert out.startswith("[digisearch web search error:")
    assert "off" in out and "100" in out
    assert "payloads" not in seen


def test_window_clipped_by_the_cap_errors_before_any_post(_exa, monkeypatch):
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    out = mcp_server.exa_web_search("q", num_results=8, offset=95)
    assert out.startswith("[digisearch web search error:")
    assert "cap" in out
    assert "payloads" not in seen


def test_empty_page_past_the_result_count_is_explicit(_exa, monkeypatch):
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(3), seen)
    out = mcp_server.exa_web_search("q", num_results=8, offset=8)
    assert "offset 8" in out
    assert "No EXA results found" not in out  # generic message reserved for the unpaged call


def test_http_page2_matches_mcp_page2(_exa, monkeypatch):
    """The HTTP route slices the same window into the same page (#4241 parity)."""
    from digisearch.server import app
    from fastapi.testclient import TestClient

    from tests.digi_test_jwt import auth_headers

    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(16), seen)
    client = TestClient(app, headers=auth_headers())
    resp = client.post(
        "/v1/digisearch_web_search",
        json={"query": "q", "num_results": 8, "offset": 8},
    )
    assert resp.status_code == 200, resp.text
    http_urls = [r["url"] for r in resp.json()["results"]]
    out = mcp_server.exa_web_search("q", num_results=8, offset=8)
    assert http_urls == [f"https://example.com/{i}" for i in range(9, 17)]
    for url in http_urls:
        assert f"{url}\n" in out
    # Both surfaces enlarged the window to offset + num_results on the wire.
    assert [p["numResults"] for p in seen["payloads"]] == [16, 16]
