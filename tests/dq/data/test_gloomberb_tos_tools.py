"""ToS/direct tools: FNG/POLL/AUCT/HALT/HN (130-coverage Task 6).

Offline: ``httpx.MockTransport`` drives the real ``digifetch.HttpFetcher``
(``allowed_hosts`` covers the five venue hosts so the SSRF guard is exercised
without a socket). Shapes come from the plugin sources (``gloom-fear-greed``,
``gloom-polls``, ``gloom-hackernews``, the Nasdaq Trader halt feed) and the
Treasury Fiscal Data API docs — coded defensively, no live HTTP (no operator
approval for any host). Every tool gets an invalid-input-no-request case plus
a mapped-rows case; the venue-direct contracts pin fail-soft behavior and the
locked caveats (FNG ToS grey area, POLL CC BY 4.0, AUCT public, HALT delayed,
HN public API). No description or payload anywhere may claim Gloomberb
sourcing for these venue reads.

GUID disposition: Task 4 probed 24 rows with no GUID verdict and Task 5 built
no guidance tool, so per the brief (GUID-via-transcripts ONLY on a Task 4
NO-ROUTE) no ``digifetch_company_guidance`` is built here; the matrix GUID row
stays COMP-over-transcripts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    GloomberbClient,
)
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest  # noqa: E402

from digifetch import HttpFetcher, RateLimiter, RetryPolicy  # noqa: E402

CNN = "production.dataviz.cnn.io"
VOTEHUB = "api.votehub.com"
FISCALDATA = "api.fiscaldata.treasury.gov"
NASDAQ_TRADER = "www.nasdaqtrader.com"
HN = "hacker-news.firebaseio.com"

TOS_TOOLS = {
    "digifetch_fear_greed",
    "digifetch_polls",
    "digifetch_treasury_auctions",
    "digifetch_market_halts",
    "digifetch_hacker_news",
}

CC_BY_MARKER = "VoteHub data © VoteHub contributors, CC BY 4.0"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GLOOMBERB_ENABLED_ENV, raising=False)
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)
    monkeypatch.delenv("SUBSTACK_SESSION_COOKIE", raising=False)


def make_client(handler: Any, **kwargs: Any) -> GloomberbClient:
    allowed_hosts = kwargs.pop("allowed_hosts", [CNN, VOTEHUB, FISCALDATA, NASDAQ_TRADER, HN])
    fetcher = HttpFetcher(
        transport=httpx.MockTransport(handler),
        allowed_hosts=allowed_hosts,
    )
    kwargs.setdefault("rate_limiter", RateLimiter(0))
    kwargs.setdefault("retry_policy", RetryPolicy(attempts=1))
    return GloomberbClient(fetcher=fetcher, **kwargs)


# ── FNG (unofficial CNN read) ───────────────────────────────────────────────


def _cnn_fixture(score: float = 42.0, rating: str = "Fear") -> dict[str, Any]:
    def series(extra: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "timestamp": "2026-09-29T16:00:00Z",
            "score": score,
            "rating": rating,
            "data": [
                {"x": 1789948800000, "y": score - 2.0, "rating": rating},
                {"x": 1790035200000, "y": score, "rating": rating},
            ],
        }
        if extra:
            payload.update(extra)
        return payload

    return {
        "fear_and_greed": series(
            {
                "previous_close": 44.0,
                "previous_1_week": 50.0,
                "previous_1_month": 60.0,
                "previous_1_year": 70.0,
            }
        ),
        "fear_and_greed_historical": {
            "data": [
                {"x": 1759104000000, "y": 55.0, "rating": "Greed"},
                {"x": 1790035200000, "y": score, "rating": rating},
            ]
        },
        "market_momentum_sp500": series(),
        "market_momentum_sp125": series(),
        "stock_price_strength": series(),
        "stock_price_breadth": series(),
        "put_call_options": series(),
        "market_volatility_vix": series(),
        "market_volatility_vix_50": series(),
        "safe_haven_demand": series(),
        "junk_bond_demand": series(),
    }


def _cnn_handler(payload: dict[str, Any]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == CNN
        assert request.url.path.startswith("/index/fearandgreed/graphdata")
        return httpx.Response(200, json=payload)

    return handler


def test_fear_greed_maps_index_and_seven_components() -> None:
    envelope = make_client(_cnn_handler(_cnn_fixture())).fear_greed({})
    result = envelope.data
    assert result.score == 42.0
    assert result.rating == "fear"
    assert result.previous.close == 44.0
    assert result.previous.week == 50.0
    assert result.previous.month == 60.0
    assert result.previous.year == 70.0
    assert len(result.history) == 2
    assert result.history[-1].score == 42.0
    assert {component.id for component in result.components} == {
        "market-momentum",
        "stock-price-strength",
        "stock-price-breadth",
        "put-call-options",
        "market-volatility",
        "safe-haven-demand",
        "junk-bond-demand",
    }
    for component in result.components:
        assert component.value == 42.0
        assert component.source_url == "https://www.cnn.com/markets/fear-and-greed"
    assert "CNN" in result.attribution
    assert "Gloomberb" not in result.attribution


def test_fear_greed_partial_shape_is_fail_soft() -> None:
    payload = _cnn_fixture()
    del payload["junk_bond_demand"]
    del payload["safe_haven_demand"]
    envelope = make_client(_cnn_handler(payload)).fear_greed({})
    assert len(envelope.data.components) == 5
    assert envelope.data.score == 42.0


def test_fear_greed_rating_falls_back_from_score() -> None:
    payload = _cnn_fixture()
    for series in payload.values():
        if isinstance(series, dict):
            series.pop("rating", None)
            for point in series.get("data", []) or []:
                if isinstance(point, dict):
                    point.pop("rating", None)
    payload["fear_and_greed"]["score"] = 70.0
    envelope = make_client(_cnn_handler(payload)).fear_greed({})
    assert envelope.data.rating == "greed"


def test_fear_greed_both_fetches_failing_is_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="cnn down")

    envelope = make_client(handler).fear_greed({})
    assert envelope.data.code == "upstream_error"


def test_fear_greed_sends_cnn_referer() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["referer"] = request.headers.get("referer", "")
        return httpx.Response(200, json=_cnn_fixture())

    make_client(handler).fear_greed({})
    assert "cnn.com" in seen["referer"]


# ── POLL (VoteHub, CC BY 4.0) ───────────────────────────────────────────────


def _poll_fixture() -> list[dict[str, Any]]:
    return [
        {
            "id": "p1",
            "poll_type": "approval",
            "sample_size": 1500,
            "population": "lv",
            "url": "https://votehub.com/p/p1",
            "created_at": "2026-09-06T00:00:00Z",
            "start_date": "2026-09-01",
            "end_date": "2026-09-05",
            "pollster": "Acme Polls",
            "answers": [
                {"choice": "Approve", "pct": 45.0},
                {"choice": "Disapprove", "pct": 52.0},
            ],
            "seat_name": None,
            "sponsors": [],
            "internal": False,
            "partisan": None,
            "subject": "Presidential approval",
        },
        {
            "id": "p2",
            "poll_type": "approval",
            "sample_size": "800",
            "population": "rv",
            "url": None,
            "created_at": None,
            "start_date": "2026-08-20",
            "end_date": "2026-08-24",
            "pollster": "Beta Research",
            "answers": [{"choice": "Approve", "pct": 48.5}],
            "seat_name": None,
            "sponsors": ["Sponsor A"],
            "internal": True,
            "partisan": "D",
            "subject": "Presidential approval",
        },
        # Not a poll (no subject): filtered, never a row.
        {"id": "junk", "pollster": "Nobody"},
    ]


def test_polls_maps_rows_with_cc_by_marker() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.host == VOTEHUB
        assert request.url.path == "/polls"
        return httpx.Response(200, json=_poll_fixture())

    envelope = make_client(handler).polls({"poll_type": "approval", "limit": 10})
    result = envelope.data
    assert "poll_type=approval" in seen["url"]
    assert len(result.rows) == 2
    first = result.rows[0]
    assert first.pollster == "Acme Polls"
    assert first.sample_size == 1500
    assert first.margin_of_error == 2.5
    assert first.lead == 7.0
    assert first.lead_choice == "Disapprove"
    assert first.url == "https://votehub.com/p/p1"
    assert result.total_available == 2
    assert result.truncated is False
    for row in result.rows:
        assert CC_BY_MARKER in (row.attribution or "")
    assert CC_BY_MARKER in result.attribution
    assert "Gloomberb" not in result.attribution


def test_polls_accepts_wrapped_polls_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"polls": _poll_fixture()})

    envelope = make_client(handler).polls({})
    assert len(envelope.data.rows) == 2


def test_polls_rejects_bad_limit_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).polls({"limit": 0})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_polls_sends_subject_filter() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[])

    envelope = make_client(handler).polls({"subject": "Senate"})
    assert "subject=Senate" in seen["url"]
    assert envelope.data.rows == []


# ── AUCT (Treasury Fiscal Data, public) ──────────────────────────────────────


def _auction_fixture() -> dict[str, Any]:
    return {
        "data": [
            {
                "record_date": "2026-09-24",
                "cusip": "912797AB1",
                "security_type": "Bill",
                "security_type_desc": "Treasury Bill",
                "auction_date": "2026-09-22",
                "issue_date": "2026-09-25",
                "maturity_date": "2026-12-24",
                "offering_amount": "80000000000",
                "total_accepted": "80000000000",
                "bid_to_cover_ratio": "2.85",
                "high_yield": "4.125",
                "price_per100": "98.950000",
                "pdf_url": "https://www.treasurydirect.gov/results.pdf",
            }
        ],
        "meta": {"count": 1, "labels": {}, "dataTypes": {}, "dataFormats": {}},
        "links": {},
    }


def test_treasury_auctions_maps_rows() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.host == FISCALDATA
        assert request.url.path.endswith("/auctions_query")
        return httpx.Response(200, json=_auction_fixture())

    envelope = make_client(handler).treasury_auctions({"limit": 20})
    result = envelope.data
    assert "sort=-record_date" in seen["url"].replace("%2D", "-").replace("%2d", "-")
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.cusip == "912797AB1"
    assert row.security_type == "Bill"
    assert row.auction_date == "2026-09-22"
    assert row.source_url == "https://www.treasurydirect.gov/results.pdf"
    assert "Fiscal Data" in result.attribution
    assert "Gloomberb" not in result.attribution


def test_treasury_auctions_sends_security_type_filter() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_auction_fixture())

    make_client(handler).treasury_auctions({"security_type": "Bill"})
    assert "security_type" in seen["url"]
    assert "Bill" in seen["url"]


def test_treasury_auctions_rejects_bad_limit_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).treasury_auctions({"limit": 0})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_treasury_auctions_rejects_bad_date_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).treasury_auctions({"from_date": "09/24/2026"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


# ── HALT (Nasdaq Trader, delayed) ────────────────────────────────────────────


def _halt_feed(items: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<rss version="2.0" xmlns:ndaq="http://www.nasdaqtrader.com/ndaq">'
        "<channel><title>NASDAQ Trade Halts</title>"
        f"{items}"
        "</channel></rss>"
    )


def _halt_item(
    symbol: str = "XYZ",
    code: str = "T1",
    halt_date: str = "09/29/2026",
    halt_time: str = "14:32:10",
) -> str:
    return (
        "<item>"
        f"<title>{symbol} halted</title>"
        f"<ndaq:IssueSymbol>{symbol}</ndaq:IssueSymbol>"
        "<ndaq:IssueName>XYZ Corp</ndaq:IssueName>"
        "<ndaq:Market>NASDAQ</ndaq:Market>"
        f"<ndaq:HaltDate>{halt_date}</ndaq:HaltDate>"
        f"<ndaq:HaltTime>{halt_time}</ndaq:HaltTime>"
        f"<ndaq:ReasonCode>{code}</ndaq:ReasonCode>"
        "<ndaq:ResumptionDate>09/29/2026</ndaq:ResumptionDate>"
        "<ndaq:ResumptionQuoteTime>14:37:10</ndaq:ResumptionQuoteTime>"
        "<ndaq:ResumptionTradeTime>14:37:15</ndaq:ResumptionTradeTime>"
        "</item>"
    )


def test_market_halts_maps_rss_items() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.host == NASDAQ_TRADER
        assert request.url.path == "/rss.aspx"
        assert request.url.params.get("feed") == "tradehalts"
        return httpx.Response(200, text=_halt_feed(_halt_item() + _halt_item("ABC", "LUDP")))

    envelope = make_client(handler).market_halts({})
    result = envelope.data
    assert "rss.aspx" in seen["url"]
    assert len(result.rows) == 2
    first = result.rows[0]
    assert first.symbol == "XYZ"
    assert first.company == "XYZ Corp"
    assert first.reason_code == "T1"
    assert first.reason == "News pending"
    assert first.halted_at == int(
        datetime(2026, 9, 29, 18, 32, 10, tzinfo=timezone.utc).timestamp() * 1000
    )
    assert first.status == "resumed"
    assert first.source_url == "https://www.nasdaqtrader.com/trader.aspx?id=TradeHalt"
    assert result.rows[1].reason == "Volatility pause"
    assert "Nasdaq Trader" in result.attribution
    assert "Gloomberb" not in result.attribution


def test_market_halts_empty_channel_is_quiet_day_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_halt_feed(""))

    envelope = make_client(handler).market_halts({})
    assert envelope.data.rows == []


def test_market_halts_non_rss_is_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not a feed</html>")

    envelope = make_client(handler).market_halts({})
    assert envelope.data.code == "upstream_error"


def test_market_halts_unparseable_items_are_format_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=_halt_feed("<item><title>no ndaq fields here</title></item>"),
        )

    envelope = make_client(handler).market_halts({})
    assert envelope.data.code == "upstream_error"
    assert "format" in envelope.data.message


def test_market_halts_symbol_filter_is_client_side() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, text=_halt_feed(_halt_item() + _halt_item("ABC", "LUDP")))

    envelope = make_client(handler).market_halts({"symbol": "abc"})
    assert calls == [1]
    assert [row.symbol for row in envelope.data.rows] == ["ABC"]


def test_market_halts_rejects_bad_limit_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).market_halts({"limit": 0})
    assert envelope.data.code == "invalid_input"
    assert calls == []


# ── HN (public API) ──────────────────────────────────────────────────────────


def _hn_handler() -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == HN
        path = request.url.path
        if path == "/v0/topstories.json":
            return httpx.Response(200, json=[111, 222, 333])
        if path == "/v0/item/111.json":
            return httpx.Response(
                200,
                json={
                    "id": 111,
                    "title": "Something interesting",
                    "by": "pg",
                    "time": 1790000000,
                    "score": 250,
                    "descendants": 120,
                    "url": "https://example.com/article",
                },
            )
        if path == "/v0/item/222.json":
            return httpx.Response(
                200,
                json={
                    "id": 222,
                    "title": "Ask HN: How do you test?",
                    "by": "someone",
                    "time": 1790000100,
                    "score": 30,
                    "text": "Discuss.",
                },
            )
        if path == "/v0/item/333.json":
            return httpx.Response(200, json={"id": 333, "deleted": True})
        raise AssertionError(f"unexpected HN path {path!r}")

    return handler


def test_hacker_news_maps_feed_stories() -> None:
    envelope = make_client(_hn_handler()).hacker_news({"feed": "top", "limit": 3})
    result = envelope.data
    assert result.feed == "top"
    assert len(result.rows) == 2
    first = result.rows[0]
    assert first.id == 111
    assert first.title == "Something interesting"
    assert first.by == "pg"
    assert first.score == 250
    assert first.comments == 120
    assert first.site == "example.com"
    assert first.source_url == "https://example.com/article"
    assert "Hacker News" in result.attribution
    assert "Gloomberb" not in result.attribution


def test_hacker_news_ask_post_links_discussion() -> None:
    envelope = make_client(_hn_handler()).hacker_news({"feed": "top", "limit": 3})
    ask = envelope.data.rows[1]
    assert ask.id == 222
    assert ask.url is None
    assert ask.source_url == "https://news.ycombinator.com/item?id=222"


def test_hacker_news_item_404_is_fail_soft() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v0/topstories.json":
            return httpx.Response(200, json=[111, 999])
        if request.url.path == "/v0/item/111.json":
            return httpx.Response(
                200,
                json={"id": 111, "title": "Kept", "by": "a", "time": 1, "score": 1},
            )
        return httpx.Response(404, text="no such item")

    envelope = make_client(handler).hacker_news({"feed": "top", "limit": 5})
    assert [row.id for row in envelope.data.rows] == [111]


def test_hacker_news_rejects_unknown_feed_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).hacker_news({"feed": "frontpage"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


# ── venue-direct contract (all five) ─────────────────────────────────────────


def test_tos_tools_are_free() -> None:
    from digiquant.data.gloomberb.entitlements import TOOL_ENTITLEMENTS

    for name in sorted(TOS_TOOLS):
        assert TOOL_ENTITLEMENTS[name] == "free", name


def test_tos_manifest_descriptions_name_the_venue_never_gloomberb() -> None:
    rows = {row["function"]["name"]: row for row in build_orchestrator_tool_manifest()}
    assert TOS_TOOLS <= set(rows)
    markers = {
        "digifetch_fear_greed": (
            "CNN",
            "unofficial CNN read, ToS grey area, cross-check before citing",
        ),
        "digifetch_polls": ("VoteHub", CC_BY_MARKER),
        "digifetch_treasury_auctions": ("Fiscal", "Treasury Fiscal Data, public"),
        "digifetch_market_halts": ("Nasdaq", "Nasdaq Trader, delayed"),
        "digifetch_hacker_news": ("Hacker", "public API"),
    }
    for name, (venue, caveat) in markers.items():
        description = rows[name]["function"]["description"]
        assert venue in description, name
        assert caveat in description, name
        assert "Gloomberb" not in description, name
