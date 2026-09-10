from digisearch.web_search.ddgs_provider import DdgsWebSearchProvider
from digisearch.web_search.models import WebSearchRequest


class FakeDDGS:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def text(self, query, max_results=4, **kw):
        return [
            {"href": "https://a.com/1", "title": "A1", "body": "snippet one"},
            {"href": "https://evil.com/2", "title": "E", "body": "bad"},
        ]


def test_ddgs_maps_and_filters(monkeypatch):
    import digisearch.web_search.ddgs_provider as mod

    monkeypatch.setattr(mod, "DDGS", FakeDDGS)
    p = DdgsWebSearchProvider()
    resp = p.search(WebSearchRequest(query="etf flows", include_domains=["a.com"]))
    assert resp.provider == "ddgs"
    assert [r.url for r in resp.results] == ["https://a.com/1"]
