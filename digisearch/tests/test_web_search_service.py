from digisearch.web_search.models import WebSearchRequest
from digisearch.web_search.service import WebSearchConfig, run_web_search


def test_service_prefers_searxng_falls_back_to_ddgs(monkeypatch):
    from digisearch.web_search import service as svc

    def boom(req):
        raise RuntimeError("searxng down")

    class Ok:
        name = "ddgs"

        def search(self, req):
            from digisearch.web_search.models import WebSearchResponse, WebSearchResult

            return WebSearchResponse(
                query=req.query,
                provider="ddgs",
                results=[WebSearchResult(url="https://a.com/1", title="A", snippet="s")],
            )

    monkeypatch.setattr(
        svc,
        "SearXNGWebSearchProvider",
        lambda **k: type("S", (), {"search": staticmethod(boom), "name": "searxng"})(),
    )
    monkeypatch.setattr(svc, "DdgsWebSearchProvider", Ok)
    resp = run_web_search(WebSearchRequest(query="etf"), config=WebSearchConfig(backend="auto"))
    assert resp.provider == "ddgs"
