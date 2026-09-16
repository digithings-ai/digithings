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


def test_search_web_delegates_to_search_only(monkeypatch):
    from digisearch.web_search import service as mod
    from digisearch.web_search.models import WebSearchRequest, WebSearchResponse

    seen: dict[str, object] = {}

    def fake_search_only(req, config):
        seen["query"] = req.query
        return WebSearchResponse(query=req.query, provider="searxng")

    monkeypatch.setattr(mod, "_search_only", fake_search_only)
    resp = mod.search_web(WebSearchRequest(query="q"))
    assert resp.provider == "searxng" and seen["query"] == "q"


def _provider_raising(monkeypatch, exc):
    """Point every failover provider at a fake raising ``exc()`` (#4192)."""
    from digisearch.web_search import service as svc

    class _Down:
        name = "down"

        def search(self, req):
            raise exc()

    monkeypatch.setattr(svc, "SearXNGWebSearchProvider", lambda **k: _Down())
    monkeypatch.setattr(svc, "DdgsWebSearchProvider", lambda *a, **k: _Down())


def test_search_only_wraps_provider_429_with_status_and_retryable(monkeypatch):
    import httpx
    import pytest

    from digisearch.web_search.models import WebSearchProviderError, WebSearchRequest

    request = httpx.Request("GET", "https://searxng.invalid/search")
    response = httpx.Response(429, request=request, text="Too Many Requests")
    _provider_raising(
        monkeypatch,
        lambda: httpx.HTTPStatusError(
            "Client error '429 Too Many Requests'", request=request, response=response
        ),
    )
    with pytest.raises(WebSearchProviderError) as excinfo:
        run_web_search(WebSearchRequest(query="etf"), config=WebSearchConfig(backend="auto"))
    assert excinfo.value.status_code == 429
    assert excinfo.value.retryable is True
    assert "all web-search backends failed" in str(excinfo.value)
    assert "429" in str(excinfo.value)


def test_search_only_wraps_connection_error_as_retryable(monkeypatch):
    import httpx
    import pytest

    from digisearch.web_search.models import WebSearchProviderError, WebSearchRequest

    _provider_raising(monkeypatch, lambda: httpx.ConnectError("connection refused"))
    with pytest.raises(WebSearchProviderError) as excinfo:
        run_web_search(WebSearchRequest(query="etf"), config=WebSearchConfig(backend="auto"))
    assert excinfo.value.status_code is None
    assert excinfo.value.retryable is True


def test_search_only_wraps_hard_provider_error_as_not_retryable(monkeypatch):
    import pytest

    from digisearch.web_search.models import WebSearchProviderError, WebSearchRequest

    _provider_raising(monkeypatch, lambda: ValueError("provider exploded"))
    with pytest.raises(WebSearchProviderError) as excinfo:
        run_web_search(WebSearchRequest(query="etf"), config=WebSearchConfig(backend="auto"))
    assert excinfo.value.status_code is None
    assert excinfo.value.retryable is False
    assert isinstance(excinfo.value, RuntimeError)


def test_search_only_wraps_ddgs_ratelimit_as_429_retryable(monkeypatch):
    """Pin ddgs 9.0.x ``RatelimitException`` -> 429/retryable (#4192).

    ddgs carries no HTTP response, so the classifier keys off the exception
    *name*. ddgs >=9.1 no longer raises this class (failed searches surface as
    ``DDGSException``, pinned below), so this covers the legacy deployed pin.
    """
    import pytest

    from digisearch.web_search.models import WebSearchProviderError, WebSearchRequest

    ratelimit = pytest.importorskip("ddgs.exceptions").RatelimitException
    _provider_raising(monkeypatch, ratelimit)
    with pytest.raises(WebSearchProviderError) as excinfo:
        run_web_search(WebSearchRequest(query="etf"), config=WebSearchConfig(backend="auto"))
    assert excinfo.value.status_code == 429
    assert excinfo.value.retryable is True
    assert "429" in str(excinfo.value)


def test_search_only_wraps_ddgs_timeout_as_retryable(monkeypatch):
    """Pin ddgs ``TimeoutException`` -> retryable, with no status hint (#4192)."""
    import pytest

    from digisearch.web_search.models import WebSearchProviderError, WebSearchRequest

    timeout = pytest.importorskip("ddgs.exceptions").TimeoutException
    _provider_raising(monkeypatch, timeout)
    with pytest.raises(WebSearchProviderError) as excinfo:
        run_web_search(WebSearchRequest(query="etf"), config=WebSearchConfig(backend="auto"))
    assert excinfo.value.status_code is None
    assert excinfo.value.retryable is True


def test_search_only_wraps_ddgs_hard_failure_as_not_retryable(monkeypatch):
    """ddgs >=9.1 collapses failed searches (even provider 429s) into this."""
    import pytest

    from digisearch.web_search.models import WebSearchProviderError, WebSearchRequest

    ddgs_error = pytest.importorskip("ddgs.exceptions").DDGSException
    _provider_raising(monkeypatch, lambda: ddgs_error("No results found."))
    with pytest.raises(WebSearchProviderError) as excinfo:
        run_web_search(WebSearchRequest(query="etf"), config=WebSearchConfig(backend="auto"))
    assert excinfo.value.status_code is None
    assert excinfo.value.retryable is False
    assert "No results found." in str(excinfo.value)


def test_search_only_scrubs_provider_url_credentials(monkeypatch):
    """Provider URL userinfo and query tokens must not leak into the error."""
    import pytest

    from digisearch.web_search.models import WebSearchProviderError, WebSearchRequest

    secret_url = (
        "Client error '429 Too Many Requests' for url "
        "'http://user:s3cr3t@searxng.internal:8080/search?q=etf&token=abc123'"
    )
    _provider_raising(monkeypatch, lambda: RuntimeError(secret_url))
    with pytest.raises(WebSearchProviderError) as excinfo:
        run_web_search(WebSearchRequest(query="etf"), config=WebSearchConfig(backend="auto"))
    message = str(excinfo.value)
    assert "s3cr3t" not in message
    assert "token=abc123" not in message
    assert "429 Too Many Requests" in message
    assert "***@searxng.internal" in message
