"""Portfolio-math compositions: CMP/GR/CORR/RV/GFM/GE/G/VAL/BTMM/WIRP (Task 3).

All ten are compositions over existing reads (price_history, ticker_financials,
econ_series, shiller, and the Kalshi KXFED venue path). Derived numbers are
computed locally (rebased returns, date-aligned inner joins, Pearson math,
statement multiples, CAPE zones, SOFR/EFFR spreads, fed-prob ladders) and must
never claim Gloomberb sourcing (attributed=False, no deep link).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import GloomberbClient  # noqa: E402
from digiquant.data.gloomberb.agent_tools import (  # noqa: E402
    build_digifetch_tool_dispatcher,
)

from digifetch import HttpFetcher, RateLimiter, RetryPolicy  # noqa: E402


def make_client(handler: Any, **kwargs: Any) -> GloomberbClient:
    fetcher = HttpFetcher(
        transport=httpx.MockTransport(handler),
        allowed_hosts=["api.gloom.sh", "api.elections.kalshi.com"],
    )
    kwargs.setdefault("rate_limiter", RateLimiter(0))
    kwargs.setdefault("retry_policy", RetryPolicy(attempts=1))
    return GloomberbClient(fetcher=fetcher, **kwargs)


def _envelope(data: Any, status: str = "success", **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"status": status, "data": data, **extra})


def _bars(base: float, step: float = 1.0, n: int = 5) -> list[dict[str, Any]]:
    return [
        {"date": f"2026-09-{25 + i:02d}T00:00:00.000Z", "close": base + step * i} for i in range(n)
    ]


AAPL_FINANCIALS = {
    "quote": {
        "symbol": "AAPL",
        "currency": "USD",
        "price": 200.0,
        "change": 1.0,
        "changePercent": 0.5,
        "lastUpdated": 1773000000000,
        "marketState": "CLOSED",
        "listingExchangeName": "NASDAQ",
        "dataSource": "delayed",
    },
    "fundamentals": {
        "trailingPe": 30.0,
        "forwardPe": 25.0,
        "pegRatio": 1.5,
        "enterpriseToRevenue": 8.0,
        "dividendYield": 0.005,
    },
    "annualStatements": [
        {
            "date": "2025-09-27",
            "currency": "USD",
            "totalRevenue": 400.0,
            "netIncome": 100.0,
            "eps": 6.0,
        },
        {
            "date": "2024-09-28",
            "currency": "USD",
            "totalRevenue": 380.0,
            "netIncome": 95.0,
            "eps": 5.5,
        },
    ],
    "quarterlyStatements": [],
}

MSFT_FINANCIALS = {
    "quote": {
        "symbol": "MSFT",
        "currency": "USD",
        "price": 400.0,
        "change": 2.0,
        "changePercent": 0.5,
        "lastUpdated": 1773000000000,
        "marketState": "CLOSED",
        "listingExchangeName": "NASDAQ",
        "dataSource": "delayed",
    },
    "fundamentals": {
        "trailingPe": 35.0,
        "forwardPe": 30.0,
        "pegRatio": 2.0,
        "enterpriseToRevenue": 10.0,
        "dividendYield": 0.008,
    },
    "annualStatements": [
        {
            "date": "2025-06-30",
            "currency": "USD",
            "totalRevenue": 250.0,
            "netIncome": 90.0,
            "eps": 12.0,
        },
    ],
    "quarterlyStatements": [],
}


def _portfolio_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/market/history":
        symbol = request.url.params.get("symbol", "AAPL")
        base = 100.0 if symbol == "AAPL" else 200.0
        return _envelope(_bars(base), currency="USD", providerMeta={"provider": "yahoo"})
    if path == "/market/financials":
        symbol = request.url.params.get("symbol", "AAPL")
        return _envelope(MSFT_FINANCIALS if symbol == "MSFT" else AAPL_FINANCIALS)
    if path.startswith("/cloud/econ/series/"):
        series_id = path.rsplit("/", 1)[-1]
        value = {"SOFR": 4.3, "EFFR": 4.25, "WRESBAL": 3200.0}.get(series_id, 2.9)
        return httpx.Response(
            200,
            json={
                "observations": [
                    {"date": "2026-09-29", "value": value},
                    {"date": "2026-09-28", "value": value},
                ],
                "info": {"id": series_id, "title": series_id, "units": "Percent"},
            },
        )
    if path == "/cloud/econ/shiller":
        return httpx.Response(
            200,
            json={
                "observations": [
                    {"date": f"2026-0{i}-01", "price": 6000.0, "cape": 30.0 + i}
                    for i in range(1, 6)
                ],
                "sourceUrl": "https://example.test/shiller.csv",
                "fetchedAt": "2026-09-15T06:20:06.110Z",
            },
        )
    if path == "/markets" or path == "/trade-api/v2/markets":
        assert request.url.host == "api.elections.kalshi.com"
        return httpx.Response(
            200,
            json={
                "markets": [
                    {
                        "ticker": "KXFED-26DEC-450",
                        "event_ticker": "KXFED-26DEC",
                        "floor_strike": 4.5,
                        "strike_type": "greater",
                        "yes_bid": 90,
                        "yes_ask": 92,
                        "last_price": 91,
                        "close_time": "2026-12-16T00:00:00Z",
                        "status": "open",
                    },
                    {
                        "ticker": "KXFED-26DEC-475",
                        "event_ticker": "KXFED-26DEC",
                        "floor_strike": 4.75,
                        "strike_type": "greater",
                        "yes_bid": 40,
                        "yes_ask": 42,
                        "last_price": 41,
                        "close_time": "2026-12-16T00:00:00Z",
                        "status": "open",
                    },
                    {
                        "ticker": "KXFED-26DEC-500",
                        "event_ticker": "KXFED-26DEC",
                        "floor_strike": 5.0,
                        "strike_type": "greater",
                        "yes_bid": 9,
                        "yes_ask": 11,
                        "last_price": 10,
                        "close_time": "2026-12-16T00:00:00Z",
                        "status": "open",
                    },
                ],
                "cursor": "",
            },
        )
    raise AssertionError(f"unexpected request: {request.url}")


def test_correlation_matrix_is_one_for_identical_series() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/market/history"
        return _envelope(_bars(100.0), currency="USD", providerMeta={"provider": "yahoo"})

    client = make_client(handler)
    result = client.correlation_matrix({"tickers": ["AAPL", "MSFT"]}).data
    assert result.matrix["AAPL"]["MSFT"] == pytest.approx(1.0)
    assert result.matrix["MSFT"]["MSFT"] == pytest.approx(1.0)
    assert result.common_dates, "an aligned join must report its dates"


def test_correlation_matrix_dispatch_never_claims_sourcing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _envelope(_bars(100.0), currency="USD", providerMeta={"provider": "yahoo"})

    execute = build_digifetch_tool_dispatcher(client=make_client(handler))
    result = execute("digifetch_correlation_matrix", {"tickers": ["AAPL", "MSFT"]})
    assert isinstance(result, dict)
    assert result["ok"] is True
    payload = json.loads(str(result["content"]))
    assert payload["data"]["matrix"]["AAPL"]["MSFT"] == pytest.approx(1.0)
    assert "attribution" not in payload
    assert "source_url" not in payload


def test_compare_performance_rebases_to_100_at_first_common_date() -> None:
    client = make_client(_portfolio_handler)
    result = client.compare_performance({"tickers": ["AAPL", "MSFT"]}).data
    assert result.series["AAPL"][0] == pytest.approx(100.0)
    assert result.series["MSFT"][0] == pytest.approx(100.0)
    assert result.total_returns["AAPL"] == pytest.approx(0.04)
    assert result.dates[0] <= result.dates[-1]


def test_price_compositions_reject_a_single_ticker_without_a_request() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    client = make_client(_fail)
    for envelope in (
        client.compare_performance({"tickers": ["AAPL"]}),
        client.correlation_matrix({"tickers": ["AAPL"]}),
        client.relationship_graph({"base": "AAPL", "quote": "AAPL"}),
        client.relative_valuation({"tickers": ["AAPL"]}),
    ):
        assert envelope.data.code == "invalid_input"
    assert calls == []


def test_price_compositions_reject_an_empty_overlap_without_clamping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        symbol = request.url.params.get("symbol", "AAPL")
        bars = (
            _bars(100.0)
            if symbol == "AAPL"
            else [
                {"date": f"2020-01-{10 + i:02d}T00:00:00.000Z", "close": 50.0 + i} for i in range(5)
            ]
        )
        return _envelope(bars, currency="USD", providerMeta={"provider": "yahoo"})

    client = make_client(handler)
    envelope = client.compare_performance({"tickers": ["AAPL", "MSFT"]})
    assert envelope.data.code == "invalid_input"
    assert "overlap" in envelope.data.message


def test_relationship_graph_reports_ratio_beta_and_rolling_correlation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/market/history"
        return _envelope(_bars(100.0), currency="USD", providerMeta={"provider": "yahoo"})

    client = make_client(handler)
    result = client.relationship_graph({"base": "AAPL", "quote": "MSFT"}).data
    assert result.ratio[0] == pytest.approx(1.0)
    assert result.beta == pytest.approx(1.0)
    assert result.rolling_correlation[-1] == pytest.approx(1.0)


def test_relative_valuation_builds_the_peer_table() -> None:
    client = make_client(_portfolio_handler)
    result = client.relative_valuation({"tickers": ["AAPL", "MSFT"]}).data
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].trailing_pe == pytest.approx(30.0)
    assert result.rows[1].trailing_pe == pytest.approx(35.0)
    assert result.median_pe == pytest.approx(32.5)


def test_relative_valuation_upstream_error_when_a_leg_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("symbol") == "MSFT":
            return httpx.Response(500, text="boom")
        return _portfolio_handler(request)

    client = make_client(handler)
    envelope = client.relative_valuation({"tickers": ["AAPL", "MSFT"]})
    assert envelope.data.code == "upstream_error"
    assert "MSFT" in envelope.data.message


def test_fundamental_graph_reads_a_statement_field() -> None:
    client = make_client(_portfolio_handler)
    result = client.fundamental_graph({"symbol": "AAPL", "field": "total_revenue"}).data
    assert [point.value for point in result.points] == pytest.approx([380.0, 400.0])
    assert result.points[0].date == "2024-09-28"


def test_fundamental_graph_rejects_an_unknown_field_without_a_request() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    client = make_client(_fail)
    envelope = client.fundamental_graph({"symbol": "AAPL", "field": "nope"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_valuation_graph_reports_multiples_per_period() -> None:
    client = make_client(_portfolio_handler)
    result = client.valuation_graph({"symbol": "AAPL"}).data
    assert result.snapshot.trailing_pe == pytest.approx(30.0)
    assert result.snapshot.price == pytest.approx(200.0)
    assert result.rows[0].eps == pytest.approx(5.5)


def test_custom_chart_aligns_explicit_series_without_a_catalog() -> None:
    client = make_client(_portfolio_handler)
    result = client.custom_chart(
        {
            "series": [
                {"source": "price", "symbol": "AAPL"},
                {"source": "fred", "ref": "SOFR"},
            ]
        }
    ).data
    assert "AAPL" in result.columns
    assert "FRED:SOFR" in result.columns
    assert result.dates, "aligned columns must report their union of dates"


def test_custom_chart_rejects_an_empty_series_list_without_a_request() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    client = make_client(_fail)
    envelope = client.custom_chart({"series": []})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_market_valuation_reports_cape_against_history_zones() -> None:
    client = make_client(_portfolio_handler)
    result = client.market_valuation({}).data
    assert result.cape == pytest.approx(35.0)
    assert result.cape_percentile == pytest.approx(1.0)
    assert result.zone == "expensive"
    assert result.n_observations == 5


def test_money_markets_reports_sofr_effr_spread() -> None:
    client = make_client(_portfolio_handler)
    result = client.money_markets({}).data
    assert result.sofr == pytest.approx(4.3)
    assert result.effr == pytest.approx(4.25)
    assert result.spread == pytest.approx(0.05)
    assert result.reserves == pytest.approx(3200.0)


def test_money_markets_upstream_error_when_a_series_is_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/EFFR"):
            return httpx.Response(404, json={"status": "error", "message": "no series"})
        return _portfolio_handler(request)

    client = make_client(handler)
    envelope = client.money_markets({})
    assert envelope.data.code == "upstream_error"


def test_rate_path_differences_the_kalshi_ladder() -> None:
    client = make_client(_portfolio_handler)
    result = client.rate_path({}).data
    assert len(result.meetings) == 1
    meeting = result.meetings[0]
    assert meeting.meeting == "2026-12-16"
    distribution = meeting.distribution
    assert sum(distribution.values()) == pytest.approx(1.0)
    assert meeting.most_likely == "4.75"
    assert meeting.n_strikes == 3


def test_rate_path_dispatch_never_claims_sourcing() -> None:
    execute = build_digifetch_tool_dispatcher(client=make_client(_portfolio_handler))
    result = execute("digifetch_rate_path", {})
    assert isinstance(result, dict)
    assert result["ok"] is True
    payload = json.loads(str(result["content"]))
    assert payload["data"]["meetings"][0]["meeting"] == "2026-12-16"
    assert "attribution" not in payload
    assert "source_url" not in payload


def test_portfolio_math_tools_honor_the_kill_switch_without_a_request() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("a disabled family must not reach the wire")

    client = make_client(_fail, enabled=False)
    for envelope in (
        client.compare_performance({"tickers": ["AAPL", "MSFT"]}),
        client.correlation_matrix({"tickers": ["AAPL", "MSFT"]}),
        client.rate_path({}),
    ):
        assert envelope.data.code == "upstream_error"
        assert "disabled" in envelope.data.message
    assert calls == []


def test_portfolio_math_results_are_cached_for_900s() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _portfolio_handler(request)

    client = make_client(handler)
    first = client.money_markets({})
    second = client.money_markets({})
    assert first.data.sofr == pytest.approx(second.data.sofr)
    # SOFR + EFFR + reserves; the repeat serves the envelope cache.
    assert len(calls) == 3
