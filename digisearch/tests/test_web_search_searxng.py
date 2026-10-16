import logging

import httpx

from digisearch.web_search.models import WebSearchRequest
from digisearch.web_search.searxng_provider import (
    SearXNGWebSearchProvider,
    _normalize_unresponsive_engines,
)

_SEARXNG_LOGGER = "digisearch.web_search.searxng_provider"


def _provider_for(payload: dict) -> SearXNGWebSearchProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SearXNGWebSearchProvider(base_url="http://127.0.0.1:8080", client=client)


def test_normalize_unresponsive_engines_tolerates_malformed_shapes():
    assert _normalize_unresponsive_engines(None) == []
    assert _normalize_unresponsive_engines("not-a-list") == []
    assert _normalize_unresponsive_engines([]) == []
    assert _normalize_unresponsive_engines([["duckduckgo", "access denied"]]) == [
        "duckduckgo: access denied"
    ]
    assert _normalize_unresponsive_engines([["wikidata"], "brave", None]) == ["wikidata", "brave"]


def test_searxng_unresponsive_engines_logged_without_changing_results(caplog):
    payload = {
        "results": [
            {"url": "https://a.com/1", "title": "A", "content": "c1", "score": 1.0},
        ],
        "unresponsive_engines": [["duckduckgo", "access denied"], ["wikidata", "timeout"]],
    }
    p = _provider_for(payload)
    with caplog.at_level(logging.WARNING, logger=_SEARXNG_LOGGER):
        resp = p.search(WebSearchRequest(query="etf flows"))
    assert [r.url for r in resp.results] == ["https://a.com/1"]
    # Non-empty responses keep the bare provider name (response shape unchanged).
    assert resp.provider == "searxng"
    message = "\n".join(record.getMessage() for record in caplog.records)
    assert "duckduckgo: access denied" in message
    assert "wikidata: timeout" in message


def test_searxng_empty_with_unresponsive_engines_is_visible_empty_success(caplog):
    payload = {
        "results": [],
        "unresponsive_engines": [["duckduckgo", "access denied"], ["wikidata", "timeout"]],
    }
    p = _provider_for(payload)
    with caplog.at_level(logging.WARNING, logger=_SEARXNG_LOGGER):
        resp = p.search(WebSearchRequest(query="etf flows"))
    # Still a successful empty response — no raise, no failover.
    assert resp.results == []
    assert resp.provider == (
        "searxng(none; unresponsive=duckduckgo:access denied,wikidata:timeout)"
    )
    message = "\n".join(record.getMessage() for record in caplog.records)
    assert "duckduckgo: access denied" in message
    assert "0 result" in message


def test_searxng_empty_without_unresponsive_engines_behaves_as_before(caplog):
    p = _provider_for({"results": []})
    with caplog.at_level(logging.WARNING, logger=_SEARXNG_LOGGER):
        resp = p.search(WebSearchRequest(query="etf flows"))
    assert resp.results == []
    assert resp.provider == "searxng"
    # The formerly-silent empty case leaves a warning.
    assert any("empty" in record.getMessage() for record in caplog.records)


def test_searxng_malformed_unresponsive_field_is_ignored(caplog):
    p = _provider_for({"results": [], "unresponsive_engines": "not-a-list"})
    with caplog.at_level(logging.WARNING, logger=_SEARXNG_LOGGER):
        resp = p.search(WebSearchRequest(query="etf flows"))
    assert resp.results == []
    assert resp.provider == "searxng"


def test_searxng_json_mapping():
    payload = {
        "results": [
            {"url": "https://a.com/1", "title": "A", "content": "c1", "score": 2.0},
            {"url": "https://b.com/2", "title": "B", "content": "c2", "score": 1.0},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["format"] == "json"
        assert request.url.params["q"] == "etf flows"
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = SearXNGWebSearchProvider(base_url="http://127.0.0.1:8080", client=client)
    resp = p.search(WebSearchRequest(query="etf flows"))
    assert resp.provider == "searxng"
    assert resp.results[0].url == "https://a.com/1"


def _search_with_time_range_capture(recency_days):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        for key, value in request.url.params.items():
            seen[key] = value
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = SearXNGWebSearchProvider(base_url="http://127.0.0.1:8080", client=client)
    p.search(WebSearchRequest(query="etf flows", recency_days=recency_days))
    return seen


def test_searxng_sends_time_range_from_recency_days():
    assert _search_with_time_range_capture(1)["time_range"] == "day"
    # searxng documents only day/month/year: a week maps to month.
    assert _search_with_time_range_capture(7)["time_range"] == "month"
    assert _search_with_time_range_capture(31)["time_range"] == "month"
    assert _search_with_time_range_capture(90)["time_range"] == "year"


def test_searxng_omits_time_range_when_recency_none():
    assert "time_range" not in _search_with_time_range_capture(None)
