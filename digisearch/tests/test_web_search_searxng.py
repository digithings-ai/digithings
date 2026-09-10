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
