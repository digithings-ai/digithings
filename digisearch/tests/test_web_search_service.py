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
    # Retryable failures now loop over `_SEARCH_ATTEMPTS`; skip the backoff so
    # the #4192 classification tests stay fast (the retry itself is pinned below).
    monkeypatch.setattr(svc, "_SEARCH_RETRY_BACKOFF_S", 0.0)


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
    """Pin the installed ddgs exception the 2026-09-15 incident raised (#4192).

    ddgs carries no HTTP response, so the classifier keys off the exception
    *name*. A ddgs bump that renames ``RatelimitException`` must fail this test
    instead of silently downgrading a rate limit to a hard failure.
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


def test_ddgs_empty_scrape_is_classified_retryable():
    """A ddgs ``DDGSException`` is a transient scrape blip, not a hard failure (#4297).

    The hosted stack container runs ddgs-only (no in-container searxng sidecar),
    and ddgs raises ``DDGSException("No results found.")`` for a valid query
    roughly half the time; the same request returns rows on the next attempt.
    Classifying it non-retryable is what turned a blip into an aborted segment.
    """
    import pytest

    from digisearch.web_search import service as svc

    ddgs_exc = pytest.importorskip("ddgs.exceptions").DDGSException
    status, retryable = svc._provider_failure_fields(ddgs_exc("No results found."))
    assert status is None
    assert retryable is True


def test_search_only_retries_transient_ddgs_failure_then_succeeds(monkeypatch):
    """A transient ddgs empty-scrape is retried instead of failing the caller (#4297)."""
    import pytest

    from digisearch.web_search import service as svc
    from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult

    ddgs_exc = pytest.importorskip("ddgs.exceptions").DDGSException
    calls = {"n": 0}

    class _Flaky:
        name = "ddgs"

        def search(self, req):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ddgs_exc("No results found.")
            return WebSearchResponse(
                query=req.query,
                provider="ddgs",
                results=[WebSearchResult(url="https://a.com/1", title="A", snippet="s")],
            )

    class _Down:
        name = "searxng"

        def search(self, req):
            raise RuntimeError("searxng down")

    monkeypatch.setattr(svc, "SearXNGWebSearchProvider", lambda **k: _Down())
    monkeypatch.setattr(svc, "DdgsWebSearchProvider", lambda *a, **k: _Flaky())
    monkeypatch.setattr(svc, "_SEARCH_RETRY_BACKOFF_S", 0.0)
    resp = svc._search_only(WebSearchRequest(query="etf"), WebSearchConfig(backend="auto"))
    assert resp.provider == "ddgs"
    assert calls["n"] == 2


def test_search_only_exhausts_transient_retries_and_still_raises(monkeypatch):
    """An exhausted failover still raises — the retry is bounded, never a swallow (#4297)."""
    import pytest

    from digisearch.web_search import service as svc
    from digisearch.web_search.models import WebSearchProviderError, WebSearchRequest

    ddgs_exc = pytest.importorskip("ddgs.exceptions").DDGSException
    calls = {"n": 0}

    class _Down:
        name = "ddgs"

        def search(self, req):
            calls["n"] += 1
            raise ddgs_exc("No results found.")

    monkeypatch.setattr(svc, "DdgsWebSearchProvider", lambda *a, **k: _Down())
    monkeypatch.setattr(svc, "_SEARCH_RETRY_BACKOFF_S", 0.0)
    with pytest.raises(WebSearchProviderError) as excinfo:
        svc._search_only(WebSearchRequest(query="etf"), WebSearchConfig(backend="ddgs"))
    assert excinfo.value.retryable is True
    assert calls["n"] == svc._SEARCH_ATTEMPTS


def test_search_only_does_not_retry_hard_failure(monkeypatch):
    """A non-retryable provider error is reported on the first attempt (#4297)."""
    import pytest

    from digisearch.web_search import service as svc
    from digisearch.web_search.models import WebSearchProviderError, WebSearchRequest

    calls = {"n": 0}

    class _Hard:
        name = "ddgs"

        def search(self, req):
            calls["n"] += 1
            raise ValueError("provider exploded")

    monkeypatch.setattr(svc, "DdgsWebSearchProvider", lambda *a, **k: _Hard())
    monkeypatch.setattr(svc, "_SEARCH_RETRY_BACKOFF_S", 0.0)
    with pytest.raises(WebSearchProviderError) as excinfo:
        svc._search_only(WebSearchRequest(query="etf"), WebSearchConfig(backend="ddgs"))
    assert excinfo.value.retryable is False
    assert calls["n"] == 1
