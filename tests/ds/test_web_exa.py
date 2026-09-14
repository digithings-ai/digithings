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
