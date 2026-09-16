"""Unit tests for the optional EXA web-search wrapper (no network, no key)."""

import pytest
from digisearch.orchestrator_tools import (
    TOOL_DIGISEARCH_WEB_SEARCH,
    build_orchestrator_tool_manifest,
    build_web_search_tool,
)
from digisearch.server import app
from fastapi.testclient import TestClient

from digisearch import web_exa
from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit


def test_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    assert web_exa.is_exa_configured() is False


def test_search_without_key_fails_closed(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with pytest.raises(web_exa.ExaNotConfiguredError):
        web_exa.exa_search("hello")


def test_search_rejects_empty_query(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    with pytest.raises(ValueError):
        web_exa.exa_search("  ")


def test_search_rejects_bad_type(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    with pytest.raises(ValueError):
        web_exa.exa_search("hello", search_type="neural")  # type: ignore[arg-type]


def test_manifest_excludes_web_by_default():
    names = [t["function"]["name"] for t in build_orchestrator_tool_manifest()]
    assert TOOL_DIGISEARCH_WEB_SEARCH not in names


def test_manifest_includes_web_when_asked():
    tools = build_orchestrator_tool_manifest(include_web_search=True)
    names = [t["function"]["name"] for t in tools]
    assert TOOL_DIGISEARCH_WEB_SEARCH in names
    assert build_web_search_tool()["function"]["name"] == TOOL_DIGISEARCH_WEB_SEARCH


def test_search_posts_expected_shape(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}

    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            return {
                "results": [{"title": "t", "url": "https://example.com"}],
                "searchType": "auto",
                "costDollars": {"total": 0.007},
            }

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["payload"] = json
        assert headers["x-api-key"] == "test-key"
        return FakeResp()

    monkeypatch.setattr(web_exa.httpx, "post", fake_post)
    data = web_exa.exa_search("blog post about AI", num_results=5)
    assert seen["url"] == "https://api.exa.ai/search"
    assert seen["payload"]["query"] == "blog post about AI"
    assert seen["payload"]["numResults"] == 5
    assert len(data.results) == 1
    assert web_exa.format_web_results(data).startswith("Title: t")


def test_format_empty_results():
    assert "No EXA results" in web_exa.format_web_results(web_exa.WebSearchData())


def test_route_dormant_without_key(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/digisearch_web_search", json={"query": "hello"})
    assert resp.status_code == 503, resp.text


def test_route_forwards_domains(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}

    def fake_exa_search(query, **kwargs):
        seen["query"] = query
        seen["kwargs"] = kwargs
        return web_exa.WebSearchData(results=[])

    monkeypatch.setattr(web_exa, "exa_search", fake_exa_search)
    client = TestClient(app, headers=auth_headers())
    resp = client.post(
        "/v1/digisearch_web_search",
        json={
            "query": "hello",
            "include_domains": ["example.com"],
            "exclude_domains": ["bad.example"],
        },
    )
    assert resp.status_code == 200, resp.text
    assert seen["query"] == "hello"
    assert seen["kwargs"]["include_domains"] == ["example.com"]
    assert seen["kwargs"]["exclude_domains"] == ["bad.example"]


# --- Paging (#4234): offset over one enlarged window, bounded by the EXA cap ----


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


def test_exa_max_results_is_the_pinned_cap():
    """The cap is the 1-100 EXA bound pinned by monitors models (#4065 / R6)."""
    assert web_exa.EXA_MAX_RESULTS == 100
    from digisearch.monitors.models import Watch

    bounds = Watch.model_fields["num_results"].metadata
    assert web_exa.EXA_MAX_RESULTS in [getattr(m, "le", None) for m in bounds]


def test_search_default_call_is_unchanged(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(8), seen)
    data = web_exa.exa_search("blog post about AI")
    assert seen["payload"] == {
        "query": "blog post about AI",
        "type": "auto",
        "numResults": 8,
        "contents": {"highlights": {"query": "blog post about AI", "maxCharacters": 4000}},
    }
    assert [r["url"] for r in data.results] == [f"https://example.com/{i}" for i in range(1, 9)]


def test_search_pages_offset_over_one_enlarged_window(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(20), seen)
    data = web_exa.exa_search("q", num_results=8, offset=8)
    # EXA POST /search has no offset: the window is enlarged on the wire...
    assert seen["payload"]["numResults"] == 16
    assert "offset" not in seen["payload"]
    # ...and the page is sliced client-side.
    assert [r["url"] for r in data.results] == [f"https://example.com/{i}" for i in range(9, 17)]


def test_search_page1_and_page2_are_deterministic_and_non_overlapping(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(16), seen)
    page1 = web_exa.exa_search("q", num_results=8, offset=0)
    page2 = web_exa.exa_search("q", num_results=8, offset=8)
    urls1 = [r["url"] for r in page1.results]
    urls2 = [r["url"] for r in page2.results]
    assert urls1 == [f"https://example.com/{i}" for i in range(1, 9)]
    assert urls2 == [f"https://example.com/{i}" for i in range(9, 17)]
    assert not set(urls1) & set(urls2)
    assert [p["numResults"] for p in seen["payloads"]] == [8, 16]


def test_search_window_clipped_by_cap_is_out_of_range(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    with pytest.raises(web_exa.ExaPageOutOfRangeError, match="cap"):
        web_exa.exa_search("q", num_results=8, offset=95)
    # Never a silent truncated page, and never an unbounded scan.
    assert "payloads" not in seen


def test_search_offset_beyond_cap_is_out_of_range(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    with pytest.raises(web_exa.ExaPageOutOfRangeError) as excinfo:
        web_exa.exa_search("q", num_results=8, offset=100)
    assert isinstance(excinfo.value, ValueError)  # existing callers catch ValueError
    assert "100" in str(excinfo.value)
    assert "payloads" not in seen


def test_search_last_page_at_the_cap_is_reachable(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    data = web_exa.exa_search("q", num_results=8, offset=92)
    assert seen["payload"]["numResults"] == 100
    assert [r["url"] for r in data.results] == [f"https://example.com/{i}" for i in range(93, 101)]


def test_search_negative_offset_rejected(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(8), seen)
    with pytest.raises(ValueError, match="offset"):
        web_exa.exa_search("q", offset=-1)
    assert "payloads" not in seen


# --- HTTP route (#4241): offset on POST /v1/digisearch_web_search ---------------


def test_route_default_offset_is_byte_identical(monkeypatch):
    """The default call and an explicit ``offset=0`` are the same request/response."""
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(16), seen)
    client = TestClient(app, headers=auth_headers())
    default = client.post("/v1/digisearch_web_search", json={"query": "q", "num_results": 8})
    explicit = client.post(
        "/v1/digisearch_web_search", json={"query": "q", "num_results": 8, "offset": 0}
    )
    assert default.status_code == 200, default.text
    assert default.content == explicit.content
    assert seen["payloads"][0] == seen["payloads"][1]
    assert seen["payload"]["numResults"] == 8
    assert "offset" not in seen["payload"]


def test_route_page2_is_deterministic_and_non_overlapping(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(16), seen)
    client = TestClient(app, headers=auth_headers())
    page1 = client.post("/v1/digisearch_web_search", json={"query": "q", "num_results": 8})
    page2 = client.post(
        "/v1/digisearch_web_search", json={"query": "q", "num_results": 8, "offset": 8}
    )
    assert page1.status_code == 200, page1.text
    assert page2.status_code == 200, page2.text
    urls1 = [r["url"] for r in page1.json()["results"]]
    urls2 = [r["url"] for r in page2.json()["results"]]
    assert urls1 == [f"https://example.com/{i}" for i in range(1, 9)]
    assert urls2 == [f"https://example.com/{i}" for i in range(9, 17)]
    # One enlarged window on the wire; the page is sliced client-side.
    assert [p["numResults"] for p in seen["payloads"]] == [8, 16]


def test_route_window_past_the_cap_is_400_explicit(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    client = TestClient(app, headers=auth_headers())
    resp = client.post(
        "/v1/digisearch_web_search", json={"query": "q", "num_results": 8, "offset": 95}
    )
    assert resp.status_code == 400, resp.text
    assert "cap" in resp.text
    assert "100" in resp.text
    # Refused before any EXA POST — never a silently truncated page.
    assert "payloads" not in seen


def test_route_offset_beyond_the_cap_is_400_explicit(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/digisearch_web_search", json={"query": "q", "offset": 100})
    assert resp.status_code == 400, resp.text
    assert "100" in resp.text
    assert "payloads" not in seen


def test_route_negative_offset_is_422(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/digisearch_web_search", json={"query": "q", "offset": -1})
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "validation_error"
    # The envelope flattens the field path; the ge=0 bound is still explicit.
    assert "greater than or equal to 0" in error["message"]


def test_route_last_page_at_the_cap_is_reachable(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    client = TestClient(app, headers=auth_headers())
    resp = client.post(
        "/v1/digisearch_web_search", json={"query": "q", "num_results": 8, "offset": 92}
    )
    assert resp.status_code == 200, resp.text
    assert seen["payload"]["numResults"] == 100
    urls = [r["url"] for r in resp.json()["results"]]
    assert urls == [f"https://example.com/{i}" for i in range(93, 101)]


# --- Orchestrator manifest (#4241): offset advertised in the invoke schema ------


def test_manifest_web_search_exposes_offset():
    tool = build_web_search_tool()
    props = tool["function"]["parameters"]["properties"]
    assert props["offset"]["type"] == "integer"
    assert "100" in props["offset"]["description"]
    # required stays query-only: offset is optional and defaults to the unpaged call.
    assert tool["function"]["parameters"]["required"] == ["query"]
