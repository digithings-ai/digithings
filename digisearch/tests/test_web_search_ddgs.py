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


def _search_with_call_capture(monkeypatch, req):
    import digisearch.web_search.ddgs_provider as mod

    seen: list[dict] = []

    class RecordingDDGS(FakeDDGS):
        def text(self, query, max_results=4, **kw):
            seen.append({"query": query, "max_results": max_results, **kw})
            return super().text(query, max_results=max_results, **kw)

    monkeypatch.setattr(mod, "DDGS", RecordingDDGS)
    resp = DdgsWebSearchProvider().search(req)
    assert len(seen) == 1
    return resp, seen[0]


def test_ddgs_sends_timelimit_from_recency_days(monkeypatch):
    _, call = _search_with_call_capture(
        monkeypatch, WebSearchRequest(query="etf flows", recency_days=1)
    )
    assert call["timelimit"] == "d"
    _, call = _search_with_call_capture(
        monkeypatch, WebSearchRequest(query="etf flows", recency_days=7)
    )
    assert call["timelimit"] == "w"
    _, call = _search_with_call_capture(
        monkeypatch, WebSearchRequest(query="etf flows", recency_days=90)
    )
    assert call["timelimit"] == "y"
    _, call = _search_with_call_capture(
        monkeypatch, WebSearchRequest(query="etf flows", recency_days=None)
    )
    assert call["timelimit"] is None


def test_ddgs_overfetches_before_filtering_then_caps(monkeypatch):
    resp, call = _search_with_call_capture(
        monkeypatch, WebSearchRequest(query="etf flows", max_results=1)
    )
    assert call["max_results"] == 2
    assert [r.url for r in resp.results] == ["https://a.com/1"]
