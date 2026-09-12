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


def test_config_rejects_unknown_backend():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WebSearchConfig(backend="bing")


def test_config_clamps_fetch_bounds():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WebSearchConfig(fetch_max_pages=0)
    with pytest.raises(ValidationError):
        WebSearchConfig(fetch_max_pages=11)
    with pytest.raises(ValidationError):
        WebSearchConfig(fetch_timeout=0)
    with pytest.raises(ValidationError):
        WebSearchConfig(fetch_timeout=-1.0)
    assert WebSearchConfig(fetch_max_pages=10, fetch_timeout=0.5).fetch_max_pages == 10


def test_limiter_for_shares_default_and_caches_custom():
    from digisearch.web_search import service as svc

    assert svc._limiter_for(1.0) is svc._limiter
    assert svc._limiter_for(0.25) is svc._limiter_for(0.25)
    assert svc._limiter_for(0.25) is not svc._limiter


def test_run_uses_configured_min_interval(monkeypatch):
    from digisearch.web_search import service as svc
    from digisearch.web_search.models import WebSearchResponse, WebSearchResult

    acquired: list[float] = []

    class _RecordingLimiter:
        def acquire(self):
            acquired.append(1.0)

    class _Provider:
        name = "searxng"

        def search(self, req):
            return WebSearchResponse(
                query=req.query,
                provider="searxng",
                results=[WebSearchResult(url="https://a.com/1", title="A", snippet="s")],
            )

    class _Fetcher:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def fetch(self, url):
            raise RuntimeError("no network in unit")

    monkeypatch.setattr(svc, "SearXNGWebSearchProvider", lambda **k: _Provider())
    monkeypatch.setattr(svc, "DdgsWebSearchProvider", lambda *a, **k: _Provider())
    monkeypatch.setattr(svc, "HttpFetcher", _Fetcher)
    custom = svc._limiter_for(0.0)
    monkeypatch.setattr(custom, "acquire", _RecordingLimiter().acquire)
    resp = run_web_search(
        WebSearchRequest(query="etf"),
        config=WebSearchConfig(backend="searxng", fetch_max_pages=1, min_interval_s=0.0),
    )
    assert resp.results and acquired == [1.0]


def test_from_env_bad_backend_raises_config_error(monkeypatch):
    import pytest

    from digisearch.web_search.models import WebSearchConfigError

    monkeypatch.setenv("DIGISEARCH_WEB_SEARCH_BACKEND", "bogus")
    with pytest.raises(WebSearchConfigError, match="bogus"):
        WebSearchConfig.from_env()


def test_from_env_good_backend_unchanged(monkeypatch):
    monkeypatch.delenv("DIGISEARCH_WEB_SEARCH_BACKEND", raising=False)
    assert WebSearchConfig.from_env().backend == "auto"
    monkeypatch.setenv("DIGISEARCH_WEB_SEARCH_BACKEND", "ddgs")
    assert WebSearchConfig.from_env().backend == "ddgs"


def test_from_env_parses_fetch_allowed_hosts(monkeypatch):
    monkeypatch.delenv("DIGISEARCH_FETCH_ALLOWED_HOSTS", raising=False)
    assert WebSearchConfig.from_env().fetch_allowed_hosts == ()
    monkeypatch.setenv("DIGISEARCH_FETCH_ALLOWED_HOSTS", " Internal.Example.com , proxy.local ,")
    assert WebSearchConfig.from_env().fetch_allowed_hosts == (
        "internal.example.com",
        "proxy.local",
    )


def test_run_passes_fetch_allowed_hosts_to_fetcher(monkeypatch):
    from digisearch.web_search import service as svc
    from digisearch.web_search.models import WebSearchResponse, WebSearchResult

    seen: dict = {}

    class _Provider:
        name = "searxng"

        def search(self, req):
            return WebSearchResponse(
                query=req.query,
                provider="searxng",
                results=[WebSearchResult(url="https://a.com/1", title="A", snippet="s")],
            )

    class _Fetcher:
        def __init__(self, *a, **k):
            seen.update(k)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def fetch(self, url):
            raise RuntimeError("no network in unit")

    monkeypatch.setattr(svc, "SearXNGWebSearchProvider", lambda **k: _Provider())
    monkeypatch.setattr(svc, "HttpFetcher", _Fetcher)
    run_web_search(
        WebSearchRequest(query="etf"),
        config=WebSearchConfig(
            backend="searxng",
            fetch_max_pages=1,
            min_interval_s=0.0,
            fetch_allowed_hosts=("internal.example.com",),
        ),
    )
    assert seen.get("allowed_hosts") == ("internal.example.com",)


def test_run_web_search_lets_config_error_propagate(monkeypatch):
    import pytest

    from digisearch.web_search.models import WebSearchConfigError

    monkeypatch.setenv("DIGISEARCH_WEB_SEARCH_BACKEND", "bogus")
    with pytest.raises(WebSearchConfigError):
        run_web_search(WebSearchRequest(query="etf"))
