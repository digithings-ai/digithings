"""Phase-2 MCP wiring for the 13 digifetch x Gloomberb tools (#4069).

Wrappers are exercised through FastMCP's tool manager with a
MockTransport-backed GloomberbClient patched over the env-seam builder. No
network, no session cookie required (gated tools are exercised both ways).
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from typing import Any

import httpx
import pytest

pytest.importorskip("mcp.server.fastmcp")

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    GLOOMBERB_ATTRIBUTION,
    GLOOMBERB_DELAY_NOTICE,
    EarningsEvent,
    GloomberbClient,
)
from digiquant.mcp_server import create_mcp_server  # noqa: E402
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest  # noqa: E402

from digifetch import HttpFetcher, RateLimiter, RetryPolicy  # noqa: E402
from digiquant import mcp_server  # noqa: E402

DIGIFETCH_TOOLS = {
    "digifetch_quote",
    "digifetch_quotes_batch",
    "digifetch_price_history",
    "digifetch_ticker_financials",
    "digifetch_options_chain",
    "digifetch_sec_filings",
    "digifetch_holders",
    "digifetch_analyst_research",
    "digifetch_corporate_actions",
    "digifetch_earnings_calendar",
    "digifetch_exchange_rate",
    "digifetch_search",
    "digifetch_news",
}

#: Tools whose payload carries a term.gloom.sh deep link (one listing).
LINKED_TOOLS = {
    "digifetch_quote",
    "digifetch_price_history",
    "digifetch_ticker_financials",
    "digifetch_options_chain",
    "digifetch_sec_filings",
    "digifetch_holders",
    "digifetch_analyst_research",
    "digifetch_corporate_actions",
}

AAPL_QUOTE = {
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
    monkeypatch.delenv("GLOOMBERB_ENABLED", raising=False)
    monkeypatch.delenv("GLOOMBERB_SESSION_COOKIE", raising=False)


def _mcp(name: str):
    return create_mcp_server()._tool_manager.get_tool(name).fn


def _names(scope: str = "full") -> set[str]:
    server = create_mcp_server(scope=scope)
    return {t.name for t in server._tool_manager.list_tools()}


def _envelope(data: Any, status: str = "success", **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"status": status, "data": data, **extra})


def _patch_client(monkeypatch: pytest.MonkeyPatch, handler: Any, **kwargs: Any) -> GloomberbClient:
    fetcher = HttpFetcher(
        transport=httpx.MockTransport(handler),
        allowed_hosts=["api.gloom.sh"],
    )
    kwargs.setdefault("rate_limiter", RateLimiter(0))
    kwargs.setdefault("retry_policy", RetryPolicy(attempts=1))
    client = GloomberbClient(fetcher=fetcher, **kwargs)
    monkeypatch.setattr(mcp_server, "_build_gloomberb_client", lambda: client)
    return client


def _sweep_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/market/quote":
        return _envelope(AAPL_QUOTE)
    if path == "/market/quotes/batch":
        return _envelope(
            {
                "items": [
                    {
                        "symbol": "AAPL",
                        "exchange": "NASDAQ",
                        "status": "success",
                        "data": AAPL_QUOTE,
                    }
                ]
            }
        )
    if path == "/market/history":
        return _envelope([], currency="USD", providerMeta={"provider": "yahoo"})
    if path == "/market/financials":
        return _envelope({"quote": AAPL_QUOTE})
    if path == "/market/options":
        return _envelope(
            {"underlyingSymbol": "AAPL", "expirationDates": [], "calls": [], "puts": []}
        )
    if path == "/cloud/sec/filings":
        return httpx.Response(200, json={"filings": [], "hasMore": False, "nextOffset": 0})
    if path == "/market/holders":
        return _envelope({"symbol": "AAPL", "holders": []})
    if path == "/market/analyst":
        return _envelope({"symbol": "AAPL", "recommendationRating": 2.0, "ratings": []})
    if path == "/market/corporate-actions":
        return _envelope({"symbol": "AAPL", "dividends": [], "splits": [], "earnings": []})
    if path == "/market/exchange-rate":
        return _envelope({"rate": 1.1, "source": "yahoo"})
    if path == "/market/search":
        return _envelope([])
    if path == "/news":
        return httpx.Response(
            200, json={"items": [{"id": "n1", "headline": "Headline"}], "nextCursor": None}
        )
    raise AssertionError(f"unexpected Gloomberb path {path!r}")


def test_all_13_tools_registered_in_full_and_read_scope() -> None:
    assert len(DIGIFETCH_TOOLS) == 13
    assert DIGIFETCH_TOOLS <= _names()
    assert DIGIFETCH_TOOLS <= _names(scope="read")


def test_orchestrator_manifest_lists_each_tool_with_attribution() -> None:
    rows = {row["function"]["name"]: row for row in build_orchestrator_tool_manifest()}
    missing = DIGIFETCH_TOOLS - set(rows)
    assert not missing, f"missing orchestrator tools: {sorted(missing)}"
    for name in sorted(DIGIFETCH_TOOLS - {"digifetch_earnings_calendar"}):
        description = rows[name]["function"]["description"]
        assert "Gloomberb" in description, f"{name} description must name the source"
    # The earnings calendar is Yahoo-backed; it must not claim Gloomberb.
    earnings_description = rows["digifetch_earnings_calendar"]["function"]["description"]
    assert "Yahoo" in earnings_description
    assert "Gloomberb" not in earnings_description


def test_anon_quote_returns_attributed_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return _envelope(AAPL_QUOTE)

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_quote")("AAPL"))
    assert payload["data"]["quote"]["price"] == 200.0
    assert payload["stale"] is False
    assert payload["delay_note"] == "Free-tier data delayed up to 15 minutes"
    assert payload["attribution"] == GLOOMBERB_ATTRIBUTION
    assert payload["delay_notice"] == GLOOMBERB_DELAY_NOTICE
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"
    assert "symbol=AAPL" in seen["url"]


def test_holders_without_cookie_is_auth_required_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _envelope({"symbol": "AAPL", "holders": []})

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_holders")("AAPL"))
    assert payload["data"]["code"] == "auth_required"
    assert "GLOOMBERB_SESSION_COOKIE" in payload["data"]["message"]
    assert calls == []


def test_kill_switch_disabled_returns_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # No builder patch: the env-seam path builds a real client, and the kill
    # switch short-circuits before any request, so this stays offline.
    monkeypatch.setenv("GLOOMBERB_ENABLED", "0")
    payload = json.loads(_mcp("digifetch_quote")("AAPL"))
    assert payload["data"]["code"] == "upstream_error"
    assert "kill switch" in payload["data"]["message"]


def test_session_cookie_is_never_echoed_in_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _envelope({"symbol": "AAPL", "holders": []})

    _patch_client(monkeypatch, handler, session_cookie="super-secret-token")
    result = _mcp("digifetch_holders")("AAPL")
    assert "super-secret-token" not in result
    assert json.loads(result)["data"]["holders"] == []


def test_earnings_calendar_reports_missing_yfinance(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the earnings path must not touch the Cloud transport")

    _patch_client(monkeypatch, handler)
    monkeypatch.setitem(sys.modules, "yfinance", None)
    payload = json.loads(_mcp("digifetch_earnings_calendar")(["AAPL"]))
    assert payload["data"]["code"] == "upstream_error"
    assert "yfinance" in payload["data"]["message"]


def test_earnings_calendar_returns_events(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the earnings path must not touch the Cloud transport")

    _patch_client(
        monkeypatch,
        handler,
        now=lambda: datetime(2026, 9, 15, tzinfo=timezone.utc),
        earnings_provider=lambda symbol: [
            EarningsEvent(symbol=symbol, earnings_date=date(2026, 9, 20), eps_estimate=1.2)
        ],
    )
    payload = json.loads(_mcp("digifetch_earnings_calendar")(["AAPL"], 90))
    assert payload["data"]["events"][0]["earnings_date"] == "2026-09-20"


def test_price_history_rejects_out_of_contract_request_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _envelope([])

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_price_history")("AAPL", "5m", "5Y"))
    assert payload["data"]["code"] == "invalid_input"
    assert calls == []


def test_news_with_ticker_carries_deep_link(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"items": [{"id": "n1", "headline": "Headline"}], "nextCursor": None}
        )

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_news")("ticker", "AAPL"))
    assert payload["data"]["items"][0]["headline"] == "Headline"
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"
    assert payload["attribution"] == GLOOMBERB_ATTRIBUTION


def test_env_seam_builder_caches_per_env_pair_and_defaults_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = mcp_server._build_gloomberb_client()
    assert first.enabled is True
    assert mcp_server._build_gloomberb_client() is first

    monkeypatch.setenv("GLOOMBERB_SESSION_COOKIE", "token-value")
    second = mcp_server._build_gloomberb_client()
    assert second is not first
    assert second.enabled is True


TOOL_CALLS: dict[str, tuple[Any, ...]] = {
    "digifetch_quote": ("AAPL",),
    "digifetch_quotes_batch": (["AAPL"],),
    "digifetch_price_history": ("AAPL", "1wk", "5Y"),
    "digifetch_ticker_financials": ("AAPL",),
    "digifetch_options_chain": ("AAPL",),
    "digifetch_sec_filings": ("MSFT",),
    "digifetch_holders": ("AAPL",),
    "digifetch_analyst_research": ("AAPL",),
    "digifetch_corporate_actions": ("AAPL",),
    "digifetch_earnings_calendar": (["AAPL"],),
    "digifetch_exchange_rate": ("EUR",),
    "digifetch_search": ("apple",),
    "digifetch_news": ("latest",),
}


@pytest.mark.parametrize(("name", "args"), sorted(TOOL_CALLS.items()))
def test_every_tool_returns_attributed_json(
    monkeypatch: pytest.MonkeyPatch, name: str, args: tuple[Any, ...]
) -> None:
    _patch_client(
        monkeypatch,
        _sweep_handler,
        session_cookie="gloomberb.session_token=test",
        earnings_provider=lambda symbol: [],
    )
    payload = json.loads(_mcp(name)(*args))
    assert "data" in payload, f"{name} returned no data slot"
    attributed = name != "digifetch_earnings_calendar"
    if attributed:
        assert payload["attribution"] == GLOOMBERB_ATTRIBUTION
        assert payload["delay_notice"] == GLOOMBERB_DELAY_NOTICE
        assert ("source_url" in payload) is (name in LINKED_TOOLS), f"{name} deep-link mismatch"
    else:
        # Yahoo-backed: must not claim Gloomberb attribution.
        assert "attribution" not in payload
        assert "source_url" not in payload


def test_env_seam_builder_closes_the_replaced_client(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeClient:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    import digiquant.data.gloomberb as gloomberb_pkg

    monkeypatch.setattr(mcp_server, "_gloomberb_clients", {})
    monkeypatch.setattr(gloomberb_pkg, "GloomberbClient", _FakeClient)
    first = mcp_server._build_gloomberb_client()
    assert mcp_server._build_gloomberb_client() is first

    monkeypatch.setenv("GLOOMBERB_SESSION_COOKIE", "token-value")
    second = mcp_server._build_gloomberb_client()
    assert second is not first
    assert first.closed is True


def test_sec_filings_documents_via_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "documents": [
                    {
                        "type": "10-Q",
                        "document": "a.htm",
                        "url": "https://sec.example/a",
                        "isPrimary": True,
                    }
                ]
            },
        )

    _patch_client(monkeypatch, handler)
    payload = json.loads(
        _mcp("digifetch_sec_filings")("MSFT", "documents", 15, "789019", "0001-26-1")
    )
    assert "/cloud/sec/filing/documents" in seen["url"]
    assert payload["data"]["documents"][0]["type"] == "10-Q"


def test_sec_filings_content_via_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": "<html/>", "form4": None})

    _patch_client(monkeypatch, handler)
    payload = json.loads(
        _mcp("digifetch_sec_filings")("MSFT", "content", 15, "789019", "0001-26-1")
    )
    assert payload["data"]["content"] == "<html/>"
