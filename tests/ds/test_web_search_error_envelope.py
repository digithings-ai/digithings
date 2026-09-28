"""Provider failures on web_search are soft envelopes, never HTTP 500 (#4192).

On 2026-09-15 a provider failure (the deployed free ``ddgs`` engine, likely
rate-limited) escaped ``POST /v1/orchestrator_invoke`` as an HTTP 500 and
cancelled digiquant's daily book run; a 429 the same night was masked. The
direct route ``POST /v1/web_search`` shares ``run_web_search`` with the
orchestrator ``web_search`` tool, so both must convert provider failures
(429 / 5xx / connection / timeout) into an HTTP 200 envelope
``{"ok": false, "error": ..., "retryable": ..., "status_code": ...}``.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from digisearch.server import app
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers


@pytest.fixture
def client() -> TestClient:
    # raise_server_exceptions=False: a pre-fix escaping provider exception must
    # surface as the HTTP 500 the contract forbids instead of aborting the test.
    return TestClient(app, headers=auth_headers(), raise_server_exceptions=False)


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://searxng.invalid/search")
    response = httpx.Response(status, request=request, text="upstream boom")
    return httpx.HTTPStatusError(
        f"Client error '{status}' for url '{request.url}'", request=request, response=response
    )


def _down_every_provider(monkeypatch: pytest.MonkeyPatch, exc: Callable[[], Exception]) -> None:
    """Make both failover providers raise ``exc()`` — the real service runs."""
    import digisearch.web_search.service as svc

    class _Down:
        name = "down"

        def search(self, req: object) -> object:
            raise exc()

    monkeypatch.delenv("DIGISEARCH_WEB_SEARCH_BACKEND", raising=False)
    monkeypatch.setattr(svc, "SearXNGWebSearchProvider", lambda **k: _Down())
    monkeypatch.setattr(svc, "DdgsWebSearchProvider", lambda *a, **k: _Down())


@pytest.mark.unit
@pytest.mark.parametrize(
    ("exc", "status_code", "retryable"),
    [
        (lambda: _http_status_error(429), 429, True),
        (lambda: _http_status_error(503), 503, True),
        (lambda: httpx.ConnectError("connection refused"), None, True),
        (lambda: httpx.ReadTimeout("timed out"), None, True),
        (lambda: _http_status_error(400), 400, False),
        (lambda: ValueError("provider exploded"), None, False),
    ],
    ids=["429", "503", "connect-error", "timeout", "hard-400", "hard-value-error"],
)
def test_v1_web_search_provider_failure_is_soft_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    exc: Callable[[], Exception],
    status_code: int | None,
    retryable: bool,
) -> None:
    _down_every_provider(monkeypatch, exc)
    r = client.post("/v1/web_search", json={"query": "etf flows"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error")
    assert body.get("retryable") is retryable
    assert body.get("status_code") == status_code
    if status_code is not None:
        assert str(status_code) in body["error"]


@pytest.mark.unit
def test_v1_web_search_error_scrubs_provider_url_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provider URL userinfo and query tokens must not reach the envelope."""
    secret_url = (
        "Client error '429 Too Many Requests' for url "
        "'http://user:s3cr3t@searxng.internal:8080/search?q=etf&token=abc123'"
    )
    _down_every_provider(monkeypatch, lambda: RuntimeError(secret_url))
    r = client.post("/v1/web_search", json={"query": "etf flows"})
    body = r.json()
    assert body["ok"] is False
    assert "s3cr3t" not in body["error"]
    assert "token=abc123" not in body["error"]


@pytest.mark.unit
def test_v1_web_search_provider_failure_logs_warning(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The HTTP 200 soft envelope must still leave an operator-visible log."""
    import logging

    _down_every_provider(monkeypatch, lambda: _http_status_error(429))
    with caplog.at_level(logging.WARNING, logger="digisearch.server"):
        r = client.post("/v1/web_search", json={"query": "etf flows"})
    assert r.json()["ok"] is False
    assert any("web_search provider failure" in record.getMessage() for record in caplog.records)


@pytest.mark.unit
def test_v1_web_search_rate_limit_is_retryable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """429 must be distinguishable from a hard failure so callers can back off."""
    _down_every_provider(monkeypatch, lambda: _http_status_error(429))
    r = client.post("/v1/web_search", json={"query": "etf flows"})
    body = r.json()
    assert r.status_code == 200
    assert body["ok"] is False
    assert body["retryable"] is True
    assert body["status_code"] == 429
    assert "429" in body["error"]


@pytest.mark.unit
def test_v1_web_search_ddgs_ratelimit_is_soft_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin ddgs 9.0.x ``RatelimitException`` -> 200 soft envelope.

    The deployed free ``ddgs`` fallback raised this on 2026-09-15 and escaped as
    an HTTP 500. ddgs >=9.1 masks failed searches as ``DDGSException`` instead,
    so this pins the legacy class the incident actually raised.
    """
    ratelimit = pytest.importorskip("ddgs.exceptions").RatelimitException
    _down_every_provider(monkeypatch, ratelimit)
    r = client.post("/v1/web_search", json={"query": "etf flows"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"ok", "error", "retryable", "status_code"}
    assert body["ok"] is False
    assert body["retryable"] is True
    assert body["status_code"] == 429
    assert "429" in body["error"]
    assert "RatelimitException" in body["error"]


@pytest.mark.unit
def test_v1_web_search_success_shape_unchanged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The success body stays exactly ``{query, results, provider}``."""
    import digisearch.web_search.service as svc
    from digisearch.web_search.models import WebSearchResponse, WebSearchResult

    def _fake_run(req: object) -> WebSearchResponse:
        return WebSearchResponse(
            query="etf flows",
            results=[WebSearchResult(url="https://a.com/1", title="A", snippet="s")],
            provider="searxng",
        )

    monkeypatch.setattr(svc, "run_web_search", _fake_run)
    r = client.post("/v1/web_search", json={"query": "etf flows"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"query", "results", "provider"}
    assert body["query"] == "etf flows"
    assert body["provider"] == "searxng"
    assert [row["url"] for row in body["results"]] == ["https://a.com/1"]


@pytest.mark.unit
def test_orchestrator_invoke_web_search_provider_429_is_soft_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hub path digiquant uses must not 500 on a provider 429 either."""
    _down_every_provider(monkeypatch, lambda: _http_status_error(429))
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "web_search", "arguments": {"query": "etf flows"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert body.get("retryable") is True
    assert body.get("status_code") == 429
    assert "429" in (body.get("error") or "")


@pytest.mark.unit
def test_orchestrator_invoke_web_search_provider_connection_error_is_soft_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _down_every_provider(monkeypatch, lambda: httpx.ConnectError("connection refused"))
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "web_search", "arguments": {"query": "etf flows"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert body.get("retryable") is True
    assert body.get("status_code") is None


@pytest.mark.unit
def test_orchestrator_invoke_web_search_empty_query_envelope_unchanged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pinned: empty query is validated before any provider is reached."""
    _down_every_provider(monkeypatch, lambda: pytest.fail("provider must not be reached"))
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "web_search", "arguments": {"query": "   "}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error") == "query is required"


#: The real searxng provider, driven through the real service, returning a
#: successful empty body that names two blocked engines (#4297).
_UNRESPONSIVE_DIAGNOSTIC = "searxng(none; unresponsive=duckduckgo:access denied,wikidata:timeout)"


def _searxng_empty_with_unresponsive_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the real service against a MockTransport searxng (no network)."""
    import digisearch.web_search.service as svc
    from digisearch.web_search.searxng_provider import SearXNGWebSearchProvider

    payload = {
        "results": [],
        "unresponsive_engines": [["duckduckgo", "access denied"], ["wikidata", "timeout"]],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = SearXNGWebSearchProvider(
        base_url="http://127.0.0.1:8080",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    class _Fetcher:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def __enter__(self) -> _Fetcher:
            return self

        def __exit__(self, *a: object) -> bool:
            return False

        def fetch(self, url: str) -> object:
            raise RuntimeError("no network in unit")

    monkeypatch.setenv("DIGISEARCH_WEB_SEARCH_BACKEND", "searxng")
    monkeypatch.setattr(svc, "SearXNGWebSearchProvider", lambda **k: provider)
    monkeypatch.setattr(
        svc, "DdgsWebSearchProvider", lambda *a, **k: pytest.fail("ddgs must not run")
    )
    monkeypatch.setattr(svc, "HttpFetcher", _Fetcher)


@pytest.mark.unit
def test_v1_web_search_empty_unresponsive_engines_reaches_client(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An authenticated client can read which searxng engines failed (#4297).

    The hosted container's only observability channel is this HTTP response, so
    a successful empty body must name the blocked engines without changing the
    ``{query, results, provider}`` shape.
    """
    _searxng_empty_with_unresponsive_engines(monkeypatch)
    r = client.post("/v1/web_search", json={"query": "etf flows"})
    assert r.status_code == 200
    body = r.json()
    assert body["results"] == []
    assert body["provider"] == _UNRESPONSIVE_DIAGNOSTIC
    assert set(body) == {"query", "results", "provider"}


@pytest.mark.unit
def test_orchestrator_invoke_web_search_empty_unresponsive_engines_reaches_client(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hub path digiquant uses must carry the same diagnostic (#4297)."""
    _searxng_empty_with_unresponsive_engines(monkeypatch)
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "web_search", "arguments": {"query": "etf flows"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body["data"]["results"] == []
    assert body["data"]["provider"] == _UNRESPONSIVE_DIAGNOSTIC
