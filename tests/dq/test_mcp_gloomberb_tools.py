"""MCP wiring for the digifetch x Gloomberb tools (#4069, #4110 phase 1).

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
    # coverage expansion (#4110 phase 1)
    "digifetch_econ_calendar",
    "digifetch_econ_series",
    "digifetch_yield_curve",
    "digifetch_cds",
    "digifetch_research_search",
    "digifetch_congress_trades",
    "digifetch_transcripts",
    # coverage expansion (#4110 phase 2)
    "digifetch_statements",
    "digifetch_ticker_tweets",
    "digifetch_tweet_search",
    "digifetch_venues",
    "digifetch_screener",
    "digifetch_13f_funds",
    "digifetch_13f_holdings",
    # coverage expansion (#4110 phase 3)
    "digifetch_shiller",
    "digifetch_proxy_statements",
    "digifetch_filing_events",
    "digifetch_risk_reports",
    "digifetch_short_interest",
    "digifetch_equity_diagnostic",
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
    "digifetch_transcripts",
    "digifetch_statements",
    "digifetch_ticker_tweets",
    "digifetch_proxy_statements",
    "digifetch_filing_events",
    "digifetch_risk_reports",
    "digifetch_short_interest",
    "digifetch_equity_diagnostic",
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
    if path == "/cloud/econ/calendar":
        return httpx.Response(
            200,
            json=[
                {
                    "id": "e1",
                    "date": "2026-09-15",
                    "time": "08:30",
                    "country": "US",
                    "event": "CPI YoY",
                    "actual": 3.2,
                    "forecast": 3.1,
                    "prior": 3.0,
                    "impact": "high",
                }
            ],
        )
    if path.startswith("/cloud/econ/series/"):
        return httpx.Response(
            200,
            json={
                "observations": [{"date": "2026-07-01", "value": 2.9}],
                "info": {"id": "CPIAUCSL", "title": "CPI", "units": "Percent"},
            },
        )
    if path == "/cloud/econ/yield-curve":
        return httpx.Response(
            200,
            json=[
                {
                    "maturity": "10Y",
                    "maturityYears": 10,
                    "yield": 4.2,
                    "asOf": "2026-09-15",
                    "stale": False,
                }
            ],
        )
    if path == "/cloud/credit/cds":
        return httpx.Response(
            200,
            json={
                "source": "DTCC PPD",
                "asOf": "2026-09-15",
                "trades": [{"disseminationId": 1, "issuerName": "Acme"}],
            },
        )
    if path == "/cloud/search":
        return httpx.Response(
            200,
            json={
                "hits": [{"id": "h1", "docType": "transcript", "ticker": "AAPL"}],
                "total": 120,
                "hasMore": True,
                "nextOffset": 10,
                "countCapped": False,
            },
        )
    if path == "/cloud/congress/house":
        return httpx.Response(
            200,
            json={"trades": [{"id": "c1", "memberName": "Jane", "ticker": "AAPL"}]},
        )
    if path == "/cloud/transcripts":
        return httpx.Response(
            200,
            json={
                "calls": [
                    {
                        "id": "t1",
                        "ticker": "AAPL",
                        "companyName": "Apple Inc.",
                        "callAt": "2026-08-01T16:30:00Z",
                        "webcastUrl": "https://example.test/call/t1",
                    }
                ]
            },
        )
    if path == "/market/statements":
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "annualStatements": [{"date": "2021-09-30", "currency": "USD"}],
                    "quarterlyStatements": [],
                },
            },
        )
    if path == "/news/tweets":
        return httpx.Response(200, json={"query": "$AAPL", "tweets": [{"id": "tw1", "text": "hi"}]})
    if path == "/news/tweets/search":
        return httpx.Response(
            200, json={"query": "tariffs", "tweets": [{"id": "tw2", "text": "hi"}]}
        )
    if path == "/market/venues":
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "providerId": "gloomberb-cloud",
                    "venues": [{"mic": "XADS", "name": "ADX"}],
                },
            },
        )
    if path == "/market/screener":
        return httpx.Response(
            200,
            json={"status": "success", "data": [{"symbol": "AAPL", "price": 200.0}]},
        )
    if path == "/cloud/sec/13f/funds":
        return httpx.Response(200, json=[{"name": "BERKSHIRE", "CIK": "0000949012"}])
    if path == "/cloud/sec/13f/topfunds":
        return httpx.Response(
            200,
            json=[
                {
                    "cik": "0001907544",
                    "name": "Magma",
                    "period_of_report": "2026-06-30",
                    "pnl": 624.41,
                }
            ],
        )
    if path == "/cloud/sec/13f/tickers":
        return httpx.Response(
            200, json=[{"cusip": "037833100", "ticker": "AAPL", "company_name": "Apple"}]
        )
    if path == "/cloud/sec/13f/holders":
        return httpx.Response(
            200,
            json={
                "cusip": "037833100",
                "periodOfReport": "2026-06-30",
                "ciks": ["0001067983"],
            },
        )
    if path == "/cloud/sec/13f/filings":
        return httpx.Response(
            200,
            json=[{"accession_number": "a1", "cik": "0001022837", "company_name": "Sumitomo"}],
        )
    if path == "/cloud/sec/13f/forms":
        return httpx.Response(
            200,
            json=[{"accession_number": "a1", "cik": "0001067983", "company_name": "Berkshire"}],
        )
    if path == "/cloud/sec/13f/form":
        return httpx.Response(
            200,
            json=[
                {
                    "accession_number": "a1",
                    "cik": "0001067983",
                    "name_of_issuer": "ALLY",
                    "ticker": "ALLY",
                    "value": 1.0,
                    "ssh_prnamt": 2.0,
                    "ssh_prnamt_type": "SH",
                }
            ],
        )
    if path == "/cloud/econ/shiller":
        return httpx.Response(
            200,
            json={
                "observations": [{"date": "2026-08-01", "price": 6000.0, "cape": 35.0}],
                "sourceUrl": "https://example.test/shiller.csv",
                "fetchedAt": "2026-09-15T06:20:06.110Z",
            },
        )
    if path == "/public/proxies/AAPL":
        company = {
            "ticker": "AAPL",
            "cik": "0000320193",
            "name": "Apple Inc.",
            "shortName": "Apple",
        }
        return httpx.Response(
            200,
            json={
                "company": company,
                "proxies": [
                    {
                        "id": "p1",
                        "ticker": "AAPL",
                        "company": company,
                        "proxyYear": 2026,
                        "ceoName": "Tim Cook",
                    }
                ],
            },
        )
    if path == "/public/proxies/AAPL/2026":
        return httpx.Response(
            200,
            json={
                "id": "p1",
                "ticker": "AAPL",
                "company": {"ticker": "AAPL", "name": "Apple Inc."},
                "proxyYear": 2026,
                "docUrl": "https://sec.test/p",
                "namedExecutives": [],
                "keyFigures": [],
                "otherYears": [],
            },
        )
    if path == "/public/events/AAPL":
        return httpx.Response(
            200,
            json={
                "ticker": "AAPL",
                "events": [{"id": "e1", "ticker": "AAPL", "headline": "Results of operations"}],
            },
        )
    if path == "/public/risks/AAPL":
        return httpx.Response(
            200,
            json={
                "company": {"ticker": "AAPL", "name": "Apple Inc."},
                "reports": [
                    {
                        "id": "r1",
                        "ticker": "AAPL",
                        "company": {"ticker": "AAPL", "name": "Apple Inc."},
                        "reportYear": 2025,
                    }
                ],
            },
        )
    if path == "/public/risks/AAPL/2025":
        return httpx.Response(
            200,
            json={
                "id": "r1",
                "ticker": "AAPL",
                "company": {"ticker": "AAPL", "name": "Apple Inc."},
                "reportYear": 2025,
                "risks": [{"heading": "H", "excerpt": "E"}],
                "groups": ["Macro"],
                "otherYears": [],
            },
        )
    if path == "/market/short-interest":
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "symbol": "AAPL",
                    "issueName": "Apple Inc.",
                    "points": [{"settlementDate": "2026-08-31", "sharesShort": 1.0}],
                },
            },
        )
    if path == "/research/equity-diagnostic":
        return httpx.Response(
            200,
            json={
                "schemaVersion": 1,
                "access": "preview",
                "symbol": "AAPL",
                "status": "partial",
                "verdict": "unclear",
                "findings": [],
                "coverage": [],
                "evidence": [],
            },
        )
    raise AssertionError(f"unexpected Gloomberb path {path!r}")


def test_all_33_tools_registered_in_full_and_read_scope() -> None:
    assert len(DIGIFETCH_TOOLS) == 33
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
    "digifetch_econ_calendar": (),
    "digifetch_econ_series": ("CPIAUCSL",),
    "digifetch_yield_curve": (),
    "digifetch_cds": (),
    "digifetch_research_search": ("inflation",),
    "digifetch_congress_trades": (),
    "digifetch_transcripts": ("AAPL",),
    "digifetch_statements": ("AAPL",),
    "digifetch_ticker_tweets": ("AAPL",),
    "digifetch_tweet_search": ("tariffs",),
    "digifetch_venues": (),
    "digifetch_screener": ("gainers",),
    "digifetch_13f_funds": ("search", "berkshire"),
    "digifetch_13f_holdings": ("forms", "1067983"),
    "digifetch_shiller": (),
    "digifetch_proxy_statements": ("AAPL",),
    "digifetch_filing_events": ("AAPL",),
    "digifetch_risk_reports": ("AAPL",),
    "digifetch_short_interest": ("AAPL",),
    "digifetch_equity_diagnostic": ("AAPL",),
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


# ── coverage expansion (#4110 phase 1) ──────────────────────────────────────


def test_research_search_without_cookie_is_auth_required_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _envelope({"hits": []})

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_research_search")("inflation"))
    assert payload["data"]["code"] == "auth_required"
    assert calls == []


def test_cds_out_of_range_days_is_invalid_input_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _envelope({"trades": []})

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_cds")(None, 91))
    assert payload["data"]["code"] == "invalid_input"
    assert calls == []


def test_transcripts_plan_required_maps_to_auth_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Pro plan required")

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_transcripts")("AAPL"))
    assert payload["data"]["code"] == "auth_required"
    assert "Pro plan" in payload["data"]["message"]
    assert payload["attribution"] == GLOOMBERB_ATTRIBUTION
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


@pytest.mark.parametrize("status", [200, 402])
def test_transcripts_402_plan_required_maps_to_auth_required(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="Pro plan required")

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_transcripts")("AAPL"))
    assert payload["data"]["code"] == "auth_required"
    assert "Pro plan" in payload["data"]["message"]


def test_research_search_402_maps_to_auth_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"message": "Payment Required"})

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_research_search")("inflation"))
    assert payload["data"]["code"] == "auth_required"


def test_transcripts_wrapper_maps_the_upstream_calls_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "calls": [
                    {
                        "id": "t1",
                        "ticker": "AAPL",
                        "companyName": "Apple Inc.",
                        "callAt": "2026-08-01T16:30:00Z",
                        "webcastUrl": "https://example.test/call/t1",
                    }
                ]
            },
        )

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_transcripts")("AAPL"))
    row = payload["data"]["transcripts"][0]
    assert row["company_name"] == "Apple Inc."
    assert row["call_at"] == "2026-08-01T16:30:00Z"
    assert row["webcast_url"] == "https://example.test/call/t1"


def test_congress_trades_upstream_500_maps_to_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500, text="Mistral OCR failed: 402 Customer monthly spending limit reached"
        )

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_congress_trades")())
    assert payload["data"]["code"] == "upstream_error"


def test_yield_curve_tool_returns_points_without_a_deep_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"maturity": "10Y", "maturityYears": 10, "yield": 4.2, "stale": False}],
        )

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_yield_curve")())
    assert payload["data"]["points"][0]["yield_"] == 4.2
    assert "source_url" not in payload


# ── coverage expansion (#4110 phase 2) ──────────────────────────────────────


def test_statements_without_cookie_is_auth_required_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"status": "success", "data": {}})

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_statements")("AAPL"))
    assert payload["data"]["code"] == "auth_required"
    assert calls == []


def test_statements_wrapper_maps_rows_and_deep_link(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "annualStatements": [
                        {"date": "2021-09-30", "currency": "USD", "purchaseOfBusiness": -1}
                    ],
                    "quarterlyStatements": [],
                },
            },
        )

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_statements")("AAPL", "annual"))
    assert payload["data"]["annual_statements"][0]["date"] == "2021-09-30"
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


def test_ticker_tweets_wrapper_slices_to_the_requested_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"query": "$AAPL", "tweets": [{"id": str(i), "text": "t"} for i in range(5)]},
        )

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_ticker_tweets")("AAPL", 2))
    assert len(payload["data"]["tweets"]) == 2
    assert payload["data"]["total_available"] == 5
    assert payload["data"]["truncated"] is True
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


def test_tweet_search_without_cookie_is_auth_required_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"query": "tariffs", "tweets": []})

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_tweet_search")("tariffs"))
    assert payload["data"]["code"] == "auth_required"
    assert calls == []


def test_screener_pro_required_envelope_maps_to_auth_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live free-session shape: 200 status=unsupported + PRO_REQUIRED."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "unsupported", "data": None, "reasonCode": "PRO_REQUIRED"},
        )

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_screener")("gainers"))
    assert payload["data"]["code"] == "auth_required"
    assert "Pro plan" in payload["data"]["message"]
    assert payload["data"]["retryable"] is False


def test_screener_402_text_body_maps_to_the_same_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, text="Pro plan required")

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_screener")("gainers"))
    assert payload["data"]["code"] == "auth_required"
    assert "Pro plan" in payload["data"]["message"]


def test_screener_without_cookie_is_auth_required_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"status": "success", "data": []})

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_screener")("gainers"))
    assert payload["data"]["code"] == "auth_required"
    assert calls == []


def test_13f_holdings_forms_normalizes_cik_and_sends_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json=[{"accession_number": "a1", "cik": "0001067983", "company_name": "Berkshire"}],
        )

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_13f_holdings")("forms", "1067983"))
    assert "cik=0001067983" in seen["url"]
    assert payload["data"]["forms"][0]["company_name"] == "Berkshire"


def test_13f_holdings_missing_required_field_is_invalid_input_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=[])

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_13f_holdings")("forms"))
    assert payload["data"]["code"] == "invalid_input"
    assert calls == []


def test_13f_funds_topfunds_wrapper_sends_the_quarter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"cik": "0001907544", "name": "Magma"}])

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_13f_funds")("top", None, "2026Q2"))
    assert "quarter=2026Q2" in seen["url"]
    assert payload["data"]["top_funds"][0]["name"] == "Magma"


def test_13f_funds_holders_wrapper_maps_the_ciks(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"cusip": "037833100", "periodOfReport": "2026-06-30", "ciks": ["1", "2"]},
        )

    _patch_client(monkeypatch, handler)
    payload = json.loads(
        _mcp("digifetch_13f_funds")("holders", None, None, None, "037833100", "2026-06-30")
    )
    holders = payload["data"]["holders"]
    assert holders["period_of_report"] == "2026-06-30"
    assert holders["ciks"] == ["1", "2"]


def test_13f_holders_proxied_4xx_maps_to_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Forms13F 400 for /holders")

    _patch_client(monkeypatch, handler)
    payload = json.loads(
        _mcp("digifetch_13f_funds")("holders", None, None, None, "037833100", "2026-06-30")
    )
    assert payload["data"]["code"] == "invalid_input"
    assert payload["data"]["retryable"] is False
    assert "Forms13F 400" in payload["data"]["message"]


def test_ticker_tweets_wrapper_applies_the_hours_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "query": "$AAPL",
                "tweets": [
                    {"id": "recent", "createdAt": "2026-09-15T16:00:00.000Z"},
                    {"id": "old", "createdAt": "2026-09-01T00:00:00.000Z"},
                ],
            },
        )

    _patch_client(
        monkeypatch,
        handler,
        session_cookie="gloomberb.session_token=test",
        now=lambda: datetime(2026, 9, 15, 17, 0, tzinfo=timezone.utc),
    )
    payload = json.loads(_mcp("digifetch_ticker_tweets")("AAPL", 50, 24))
    data = payload["data"]
    assert [tweet["id"] for tweet in data["tweets"]] == ["recent"]
    assert data["total_available"] == 2
    assert data["truncated"] is True


# ── coverage expansion (#4110 phase 3) ──────────────────────────────────────


def test_shiller_wrapper_slices_the_series(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "observations": [
                    {"date": f"2026-0{i}-01", "price": 100.0 + i, "cape": 30.0 + i}
                    for i in range(1, 6)
                ],
                "sourceUrl": "https://example.test/shiller.csv",
                "fetchedAt": "2026-09-15T06:20:06.110Z",
            },
        )

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_shiller")(2))
    data = payload["data"]
    assert [row["date"] for row in data["observations"]] == ["2026-04-01", "2026-05-01"]
    assert data["total_available"] == 5
    assert data["truncated"] is True
    assert data["source_url"] == "https://example.test/shiller.csv"


def test_proxy_statements_wrapper_lists_and_fetches_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        if request.url.path.endswith("/2026"):
            return httpx.Response(
                200,
                json={
                    "id": "p1",
                    "ticker": "AAPL",
                    "company": {"ticker": "AAPL", "name": "Apple Inc."},
                    "proxyYear": 2026,
                    "ceo": {"name": "Tim Cook", "total": 1.0},
                    "docUrl": "https://sec.test/p",
                    "namedExecutives": [],
                    "keyFigures": [],
                    "otherYears": [],
                },
            )
        return httpx.Response(
            200,
            json={
                "company": {"ticker": "AAPL", "name": "Apple Inc."},
                "proxies": [
                    {
                        "id": "p1",
                        "ticker": "AAPL",
                        "company": {"ticker": "AAPL", "name": "Apple Inc."},
                        "proxyYear": 2026,
                    }
                ],
            },
        )

    _patch_client(monkeypatch, handler)
    listed = json.loads(_mcp("digifetch_proxy_statements")("AAPL"))
    assert listed["data"]["proxies"][0]["proxy_year"] == 2026
    assert listed["source_url"] == "https://term.gloom.sh/?ticker=AAPL"

    one = json.loads(_mcp("digifetch_proxy_statements")("AAPL", "statement", 2026))
    assert one["data"]["statement"]["ceo"]["name"] == "Tim Cook"
    assert "/public/proxies/AAPL/2026" in seen["url"]


def test_proxy_statement_without_year_is_invalid_input_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={})

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_proxy_statements")("AAPL", "statement"))
    assert payload["data"]["code"] == "invalid_input"
    assert calls == []


def test_risk_report_without_year_is_invalid_input_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={})

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_risk_reports")("AAPL", "report"))
    assert payload["data"]["code"] == "invalid_input"
    assert calls == []


def test_filing_events_wrapper_maps_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ticker": "AAPL",
                "events": [
                    {
                        "id": "e1",
                        "ticker": "AAPL",
                        "items": ["2.02"],
                        "labels": ["Results of operations"],
                        "material": False,
                        "read": False,
                    }
                ],
            },
        )

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_filing_events")("AAPL", 5))
    event = payload["data"]["events"][0]
    assert event["items"] == ["2.02"]
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


def test_short_interest_without_cookie_is_auth_required_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _envelope({"symbol": "AAPL", "points": []})

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_short_interest")("AAPL"))
    assert payload["data"]["code"] == "auth_required"
    assert calls == []


def test_short_interest_out_of_range_years_is_invalid_input_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _envelope({"symbol": "AAPL", "points": []})

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_short_interest")("AAPL", 11))
    assert payload["data"]["code"] == "invalid_input"
    assert calls == []


def test_short_interest_wrapper_maps_points(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _envelope(
            {
                "symbol": "AAPL",
                "issueName": "Apple Inc.",
                "points": [{"settlementDate": "2026-08-31", "sharesShort": 1.0, "revised": False}],
            }
        )

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_short_interest")("AAPL", 1))
    point = payload["data"]["points"][0]
    assert point["settlement_date"] == "2026-08-31"
    assert point["shares_short"] == 1.0
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


def test_equity_diagnostic_pending_is_mapped_and_not_client_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(202, json={"status": "generating", "retryAfterMs": 2000})

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    first = json.loads(_mcp("digifetch_equity_diagnostic")("AAPL"))
    assert first["data"]["pending"]["retry_after_ms"] == 2000
    assert first["data"]["report"] is None
    # A pending payload must not enter the 900s client cache: the retry hits
    # the wire again.
    second = json.loads(_mcp("digifetch_equity_diagnostic")("AAPL"))
    assert second["data"]["pending"]["status"] == "generating"
    assert calls == [1, 1]


def test_equity_diagnostic_report_is_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "schemaVersion": 1,
                "access": "preview",
                "symbol": "AAPL",
                "status": "partial",
                "verdict": "risk_skewed",
                "summary": "Two flags found",
                "findings": [
                    {
                        "id": "F1",
                        "kind": "red_flag",
                        "severity": 3,
                        "title": "Margin compression",
                        "observation": "Gross margin fell",
                        "interpretation": "Pricing pressure",
                        "evidenceIds": ["E1"],
                    }
                ],
                "coverage": [{"dataset": "statements", "status": "available"}],
                "evidence": [{"id": "E1", "dataset": "statements", "label": "10-K"}],
            },
        )

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_equity_diagnostic")("AAPL"))
    report = payload["data"]["report"]
    assert report["access"] == "preview"
    assert report["verdict"] == "risk_skewed"
    assert report["findings"][0]["kind"] == "red_flag"
    assert report["findings"][0]["evidence_ids"] == ["E1"]
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


def test_equity_diagnostic_without_cookie_is_auth_required_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"status": "generating", "retryAfterMs": 1})

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_equity_diagnostic")("AAPL"))
    assert payload["data"]["code"] == "auth_required"
    assert calls == []
