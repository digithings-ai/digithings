import httpx

from digisearch.web_search.models import WebSearchRequest
from digisearch.web_search.searxng_provider import SearXNGWebSearchProvider


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
