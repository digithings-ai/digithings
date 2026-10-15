"""POST /v1/orchestrator_invoke dispatch for the digifetch_* family (#4097).

The endpoint routes the family through the shared in-process dispatcher
(``build_digifetch_tool_dispatcher``) so hub callers get the same §7
attribution envelope as the MCP and pipeline-agent surfaces. Offline: a
``httpx.MockTransport``-backed ``GloomberbClient`` is patched over the factory
seam in ``data.gloomberb.agent_tools``; the live API is never hit.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    GLOOMBERB_ATTRIBUTION,
    GLOOMBERB_DELAY_NOTICE,
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    GloomberbClient,
    agent_tools,
)
from digiquant.server import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from digifetch import HttpFetcher, RateLimiter, RetryPolicy  # noqa: E402
from tests.digi_test_jwt import auth_headers  # noqa: E402

AAPL_QUOTE: dict[str, Any] = {
    "symbol": "AAPL",
    "currency": "USD",
    "price": 200.0,
    "change": 1.0,
    "changePercent": 0.5,
    "lastUpdated": 1773000000000,
    "marketState": "CLOSED",
    "listingExchangeName": "NASDAQ",
    "dataSource": "delayed",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GLOOMBERB_ENABLED_ENV, raising=False)
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


def _patch_client(monkeypatch: pytest.MonkeyPatch, handler: Any, **kwargs: Any) -> None:
    fetcher = HttpFetcher(
        transport=httpx.MockTransport(handler),
        allowed_hosts=["api.gloom.sh"],
    )
    kwargs.setdefault("rate_limiter", RateLimiter(0))
    kwargs.setdefault("retry_policy", RetryPolicy(attempts=1))
    # Don't set enabled=True by default; let the client read from GLOOMBERB_ENABLED
    # unless the test explicitly passes enabled=True/False.
    gloomberb = GloomberbClient(fetcher=fetcher, **kwargs)
    monkeypatch.setattr(agent_tools, "build_gloomberb_client", lambda: gloomberb)


def _quote_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/market/quote"
    return httpx.Response(200, json={"status": "success", "data": AAPL_QUOTE})


def _fail_handler(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"no request expected, got {request.url}")


def test_digifetch_quote_returns_the_attributed_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, _quote_handler, enabled=True)
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digifetch_quote", "arguments": {"symbol": "AAPL"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["service"] == "digiquant"
    assert body["tool"] == "digifetch_quote"
    envelope = body["data"]
    assert envelope["data"]["quote"]["price"] == 200.0
    assert envelope["attribution"] == GLOOMBERB_ATTRIBUTION
    assert envelope["delay_notice"] == GLOOMBERB_DELAY_NOTICE
    assert envelope["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


@pytest.mark.parametrize("tool", ["digifetch_not_a_tool", "not_a_tool"])
def test_unknown_tools_still_400(client: TestClient, tool: str) -> None:
    r = client.post("/v1/orchestrator_invoke", json={"tool": tool, "arguments": {}})
    assert r.status_code == 400
    error = r.json()["error"]
    assert error["code"] == "http_400"
    assert tool in error["message"]


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("digifetch_holders", {"symbol": "AAPL"}),
        ("digifetch_transcripts", {"ticker": "AAPL"}),
    ],
)
def test_gated_tool_without_cookie_is_typed_auth_required(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: dict[str, Any]
) -> None:
    # Both session- and pro-gated names answer the typed envelope (the cookie
    # gate runs first), never a 400 and never a wire request.
    _patch_client(monkeypatch, _fail_handler, enabled=True)
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": tool, "arguments": arguments},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]
    assert body["data"]["data"]["code"] == "auth_required"


def test_pro_tool_with_free_session_is_typed_pro_required(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Pro plan required")

    _patch_client(monkeypatch, handler, session_cookie="test-session=test", enabled=True)
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digifetch_transcripts", "arguments": {"ticker": "AAPL"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["data"]["data"]["code"] == "pro_required"
    assert "Pro plan" in body["data"]["data"]["message"]


def test_invalid_args_are_typed_invalid_input_not_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, _fail_handler)
    # `resolution` is required for price_history — the input model rejects it.
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digifetch_price_history", "arguments": {"symbol": "AAPL"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["data"]["data"]["code"] == "invalid_input"


def test_price_history_date_window_dispatches_through_the_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": [{"date": "2015-01-05T00:00:00.000Z", "close": 100.0}],
                "currency": "USD",
                "providerMeta": {"provider": "yahoo"},
            },
        )

    _patch_client(monkeypatch, handler, enabled=True)
    r = client.post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digifetch_price_history",
            "arguments": {
                "symbol": "AAPL",
                "resolution": "1wk",
                "start_date": "2015-01-01",
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "rangeKey=ALL" in seen["url"]
    assert "startDate=2015-01-01" in seen["url"]
    assert body["data"]["data"]["bars"][0]["close"] == 100.0


def test_family_kill_switch_disables_the_tool_not_the_name(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "0")
    _patch_client(monkeypatch, _fail_handler)
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digifetch_quote", "arguments": {"symbol": "AAPL"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["data"]["data"]["code"] == "upstream_error"


def test_client_fault_returns_error_not_an_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The dispatcher's non-envelope path (agent_tools.py: the client call raised)
    # answers {"error": "<Type>: <msg>"} — the endpoint must surface it as
    # ok:false with the message preserved under `data`.
    class _Boom:
        def quote(self, request: Any) -> Any:
            raise RuntimeError("boom")

    monkeypatch.setattr(agent_tools, "build_gloomberb_client", lambda: _Boom())
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digifetch_quote", "arguments": {"symbol": "AAPL"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"].startswith("RuntimeError")
    assert body["data"] == {"error": "RuntimeError: boom"}


def test_section12_hosted_surface_tripwire_gated_tools_unreachable_without_a_cookie(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§12 tripwire, re-pinned after the DIG-2752 rescope (decision d4922299).

    The family no longer needs an opt-in, so the property is no longer "the kill
    switch blocks everything". It is narrower and still zero-HTTP: from the
    hosted /v1/orchestrator_invoke surface with NOTHING configured - no flag, no
    cookie, exactly what a deployed environment looks like - a cookie-gated tool
    MUST fail (now with the typed ``auth_required`` envelope instead of a
    disabled ``upstream_error``) and MUST make no network request, while the
    keyless ``free`` tools are reachable. The sibling tests above pin the same
    ``auth_required`` envelope with the flag set explicitly; this one pins the
    default, hosted, end-to-end shape that they do not cover.
    """
    monkeypatch.delenv(GLOOMBERB_ENABLED_ENV, raising=False)
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)

    # Any handler would fail if called, proving no request is made.
    _patch_client(monkeypatch, _fail_handler)

    # A session-gated tool (holders) must not be reachable.
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digifetch_holders", "arguments": {"symbol": "AAPL"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False, "Cookie-gated tool must not succeed without a cookie"
    assert body["data"]["data"]["code"] == "auth_required"

    # A pro-gated tool (transcripts) must not be reachable either.
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digifetch_transcripts", "arguments": {"ticker": "AAPL"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False, "Pro-gated tool must not succeed without a cookie"
    assert body["data"]["data"]["code"] == "auth_required"

    # The keyless surface IS reachable now, and that is the decision: it must
    # actually reach the transport, which a recording handler proves.
    reached: list[str] = []

    def _recording_handler(request: httpx.Request) -> httpx.Response:
        reached.append(str(request.url))
        return httpx.Response(200, json={"symbol": "AAPL", "price": 1.0})

    _patch_client(monkeypatch, _recording_handler)
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digifetch_quote", "arguments": {"symbol": "AAPL"}},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True, "A free tool must succeed with no credential"
    assert reached, "the free tool must actually reach the transport"
