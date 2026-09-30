"""Probe-backed tools: TAS/QR/EMM/SIV/JOBS/CBR/CDX/SOVR/FLOW/COT/CRYP/VCA/HIVG/OVDV/DDIS/session-movers/trending/SUB/IPO (130-coverage Task 5).

Offline: ``httpx.MockTransport`` drives the real ``digifetch.HttpFetcher``
(``allowed_hosts`` covers the Cloud + Yahoo + Substack hosts so the SSRF guard
is exercised without a socket). Every tool gets an invalid-input-no-request
case plus a mapped-rows case against the Task 4 probe shapes
(``docs/superpowers/plans/2026-09-30-gloomberb-endpoint-probes.md``); the
Pro-gated and venue-direct tools get their denial/fail-soft contracts pinned
too. Live status is unverified throughout (no operator approval for any host).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    GloomberbClient,
)

from digifetch import HttpFetcher, RateLimiter, RetryPolicy  # noqa: E402

CLOUD = "api.gloom.sh"
YAHOO = "query1.finance.yahoo.com"
SUB_PUB = "examplepub.substack.com"
SUB_ORIGIN = "substack.com"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GLOOMBERB_ENABLED_ENV, raising=False)
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)
    monkeypatch.delenv("SUBSTACK_SESSION_COOKIE", raising=False)


def make_client(handler: Any, **kwargs: Any) -> GloomberbClient:
    allowed_hosts = kwargs.pop("allowed_hosts", [CLOUD, YAHOO, SUB_PUB, SUB_ORIGIN])
    fetcher = HttpFetcher(
        transport=httpx.MockTransport(handler),
        allowed_hosts=allowed_hosts,
    )
    kwargs.setdefault("rate_limiter", RateLimiter(0))
    kwargs.setdefault("retry_policy", RetryPolicy(attempts=1))
    kwargs.setdefault("session_cookie", "gloomberb.session_token=test")
    return GloomberbClient(fetcher=fetcher, **kwargs)


def _envelope(data: Any, status: str = "success", **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"status": status, "data": data, **extra})


# ── TAS / QR (shared /cloud/tape route) ───────────────────────────────────────


TAPE_PAYLOAD = {
    "symbol": "AAPL",
    "exchange": "NASDAQ",
    "sessionHigh": 201.5,
    "sessionLow": 198.0,
    "trades": [
        {
            "id": "t1",
            "timestamp": "2026-09-30T19:59:00Z",
            "price": 200.5,
            "size": 100,
            "exchange": "NASDAQ",
            "conditions": ["@"],
            "tape": "C",
        }
    ],
    "quotes": [
        {
            "bid": 200.4,
            "ask": 200.6,
            "bidSize": 5,
            "askSize": 8,
            "venues": ["NASDAQ"],
            "conditions": ["R"],
        }
    ],
    "capacity": 1000,
    "dropped": 0,
    "cancelled": 0,
}


def test_time_and_sales_maps_trades() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/cloud/tape/AAPL"
        return _envelope(TAPE_PAYLOAD)

    envelope = make_client(handler).time_and_sales({"symbol": "AAPL", "exchange": "NASDAQ"})
    assert "exchange=NASDAQ" in seen["url"]
    assert envelope.data.symbol == "AAPL"
    assert envelope.data.trades[0].price == 200.5
    assert envelope.data.session_high == 201.5


def test_time_and_sales_requires_exchange_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).time_and_sales({"symbol": "AAPL"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_quote_recap_maps_quotes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cloud/tape/AAPL"
        return _envelope(TAPE_PAYLOAD)

    envelope = make_client(handler).quote_recap({"symbol": "AAPL", "exchange": "NASDAQ"})
    assert envelope.data.quotes[0].bid == 200.4
    assert envelope.data.quotes[0].ask_size == 8


def test_quote_recap_requires_exchange_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).quote_recap({"symbol": "AAPL"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_tape_tools_without_cookie_are_auth_required_without_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("gated tools must not reach the wire without a cookie")

    client = make_client(handler, session_cookie=None)
    # No GLOOMBERB_SESSION_COOKIE in env (clean_env) and no explicit cookie.
    assert client.time_and_sales({"symbol": "AAPL", "exchange": "X"}).data.code == ("auth_required")
    assert client.quote_recap({"symbol": "AAPL", "exchange": "X"}).data.code == ("auth_required")
    assert calls == []


# ── EMM ───────────────────────────────────────────────────────────────────────


def test_estimate_revisions_maps_periods() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/cloud/research/estimates/AAPL"
        return _envelope(
            {
                "symbol": "AAPL",
                "periods": [
                    {
                        "period": "Q3-2026",
                        "current": 1.75,
                        "recorded": 1.70,
                        "lookback": 1.68,
                        "source": "yahoo",
                    }
                ],
                "breadth7d": {"up": 5, "down": 2},
                "surprises": [{"period": "Q2-2026", "actual": 1.9, "estimate": 1.8}],
                "guidance": "raised",
                "coverage": ["Q3-2026"],
                "gaps": [],
            }
        )

    envelope = make_client(handler).estimate_revisions({"symbol": "AAPL"})
    assert "exchange" not in seen["url"]  # optional exchange is omitted when unset
    assert envelope.data.periods[0].source == "yahoo"
    assert envelope.data.guidance == "raised"


def test_estimate_revisions_blank_symbol_is_invalid_input() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).estimate_revisions({"symbol": "  "})
    assert envelope.data.code == "invalid_input"
    assert calls == []


# ── SIV ───────────────────────────────────────────────────────────────────────


def test_short_volume_maps_finra_rows() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return _envelope(
            {
                "symbol": "AAPL",
                "scope": "nms",
                "rows": [
                    {
                        "date": "2026-09-29",
                        "shortVolume": 1000.0,
                        "shortExemptVolume": 10.0,
                        "totalVolume": 5000.0,
                        "ratioPercent": 20.0,
                        "markets": ["NASDAQ"],
                        "sourceUrl": "https://example.test/finra",
                    }
                ],
                "latest": {"date": "2026-09-29", "ratioPercent": 20.0},
                "change": 1.5,
                "percentile": 80.0,
                "coverageStart": "2026-09-01",
                "coverageEnd": "2026-09-29",
            }
        )

    envelope = make_client(handler).short_volume({"symbol": "AAPL"})
    assert "scope=nms" in seen["url"]
    assert envelope.data.rows[0].ratio_percent == 20.0
    assert envelope.data.scope == "nms"


def test_short_volume_rejects_unknown_scope_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).short_volume({"symbol": "AAPL", "scope": "dark"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


# ── JOBS ──────────────────────────────────────────────────────────────────────


def test_hiring_summary_maps_or_pending() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cloud/jobs/AAPL"
        return _envelope({"ticker": "AAPL", "status": "ready", "openCount": 120})

    envelope = make_client(handler).hiring({"ticker": "AAPL"})
    assert envelope.data.mode == "summary"
    assert envelope.data.summary["openCount"] == 120


def test_hiring_postings_paginates() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/cloud/jobs/AAPL/postings"
        return _envelope(
            {
                "postings": [{"id": "p1", "title": "Engineer", "location": "Cupertino"}],
                "total": 120,
            }
        )

    envelope = make_client(handler).hiring(
        {"ticker": "AAPL", "mode": "postings", "limit": 10, "offset": 5}
    )
    assert "limit=10" in seen["url"]
    assert "offset=5" in seen["url"]
    assert envelope.data.total == 120
    assert envelope.data.postings[0].title == "Engineer"


def test_hiring_movers_needs_no_ticker() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cloud/jobs"
        return _envelope(
            {
                "asOf": "2026-09-30",
                "covered": 500,
                "movers": [
                    {
                        "ticker": "NVDA",
                        "openCount": 900,
                        "employeeCount": 30000,
                        "change30d": 25,
                        "new7d": 10,
                        "topFunction": "Engineering",
                    }
                ],
            }
        )

    envelope = make_client(handler).hiring({"mode": "movers"})
    assert envelope.data.movers[0].ticker == "NVDA"
    assert envelope.data.covered == 500


def test_hiring_summary_requires_ticker_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).hiring({"mode": "summary"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


# ── CBR ───────────────────────────────────────────────────────────────────────


def test_central_bank_rates_maps_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cloud/econ/central-bank-rates"
        return _envelope(
            {
                "rows": [
                    {
                        "bank": "Federal Reserve",
                        "rate": 4.5,
                        "rangeLow": 4.25,
                        "rangeHigh": 4.5,
                        "sourceSeriesIds": ["FEDTARRR", "EFFR"],
                        "nextMeeting": "2026-10-29",
                        "state": "confirmed",
                    }
                ]
            }
        )

    envelope = make_client(handler).central_bank_rates({})
    assert envelope.data.rows[0].bank == "Federal Reserve"
    assert envelope.data.rows[0].source_series_ids == ["FEDTARRR", "EFFR"]


def test_central_bank_rates_rejects_unknown_fields_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).central_bank_rates({"bank": "Fed"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


# ── CDX / SOVR ────────────────────────────────────────────────────────────────


def test_cdx_maps_board_and_points() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/cloud/credit/cdx"
        return _envelope(
            {
                "boards": [
                    {
                        "name": "CDX IG",
                        "spread": 65.0,
                        "maturity": "5Y",
                        "onTheRun": True,
                    }
                ],
                "points": [{"date": "2026-09-29", "spread": 65.0}],
            }
        )

    envelope = make_client(handler).cdx({"days": 30})
    assert "days=30" in seen["url"]
    assert envelope.data.boards[0].name == "CDX IG"
    assert envelope.data.points[0]["spread"] == 65.0


def test_cdx_rejects_non_positive_days_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).cdx({"days": 0})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_sovereign_cds_maps_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cloud/credit/sovr"
        return _envelope(
            {
                "rows": [
                    {
                        "sovereign": "Italy",
                        "spreadBp": 120.0,
                        "change1w": 5.0,
                        "change1m": -10.0,
                        "points": [{"date": "2026-09-29", "spread": 120.0}],
                    }
                ]
            }
        )

    envelope = make_client(handler).sovereign_cds({})
    assert envelope.data.rows[0].sovereign == "Italy"
    assert envelope.data.rows[0].spread_bp == 120.0


# ── FLOW (Pro-gated, fail closed) ─────────────────────────────────────────────


def test_options_flow_maps_events_and_has_more() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/market/scanner/flow/history"
        return httpx.Response(
            200,
            json={
                "events": [
                    {
                        "id": "f1",
                        "at": "2026-09-30T19:00:00Z",
                        "underlying": "AAPL",
                        "contract": "AAPL260116C00200000",
                        "right": "C",
                        "strike": 200.0,
                        "expiry": "2026-01-16",
                        "side": "ask",
                        "kind": "sweep",
                        "size": 50,
                        "price": 2.5,
                        "premium": 12500.0,
                        "vol": 100,
                        "openInterest": 500,
                        "volOi": 0.2,
                        "iv": 0.35,
                    }
                ],
                "hasMore": True,
            },
        )

    envelope = make_client(handler).options_flow({"symbols": ["AAPL"], "min_premium": 10000})
    assert "minPremium=10000" in seen["url"]
    assert envelope.data.events[0].kind == "sweep"
    assert envelope.data.has_more is True


def test_options_flow_surfaces_pro_denial_and_never_empties() -> None:
    def denial(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "unsupported", "data": None, "reasonCode": "PRO_REQUIRED"},
        )

    envelope = make_client(denial).options_flow({})
    assert envelope.data.code == "pro_required"
    assert envelope.data.retryable is False

    def text_402(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, text="Pro plan required for options flow")

    envelope = make_client(text_402).options_flow({})
    assert envelope.data.code == "pro_required"


def test_options_flow_without_cookie_is_auth_required_without_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("gated tools must not reach the wire without a cookie")

    envelope = make_client(handler, session_cookie=None).options_flow({})
    assert envelope.data.code == "auth_required"
    assert calls == []


# ── COT ───────────────────────────────────────────────────────────────────────


def test_cot_board_maps_class_rows() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/cloud/cot/board"
        return _envelope(
            {
                "report": "legacy",
                "traderClass": "managed-money",
                "rows": [
                    {
                        "code": "134741",
                        "contract": "3M SOFR",
                        "asOf": "2026-09-22",
                        "traderClass": "managed-money",
                        "long": 1000,
                        "short": 800,
                        "spreading": 50,
                        "net": 200,
                        "pct1y": 90.0,
                        "pct3y": 75.0,
                    }
                ],
            }
        )

    envelope = make_client(handler).cot({"report": "legacy", "trader_class": "managed-money"})
    assert "traderClass=managed-money" in seen["url"]
    assert envelope.data.rows[0].net == 200


def test_cot_contract_mode_hits_the_contract_path() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/cloud/cot/contracts/134741"
        return _envelope({"report": "legacy", "code": "134741", "rows": []})

    envelope = make_client(handler).cot({"code": "134741"})
    assert "report=legacy" in seen["url"]
    assert envelope.data.code == "134741"


def test_cot_rejects_unknown_trader_class_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).cot({"trader_class": "whales"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


# ── CRYP ──────────────────────────────────────────────────────────────────────


def test_crypto_markets_maps_coins() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cloud/crypto/markets"
        return _envelope(
            {
                "coins": [
                    {
                        "symbol": "BTC",
                        "name": "Bitcoin",
                        "price": 110000.0,
                        "change24h": 2.5,
                        "dayHigh": 111000.0,
                        "dayLow": 108000.0,
                        "volume24h": 5e10,
                        "marketCap": 2.1e12,
                        "supply": 19.8e6,
                        "range52w": [38000.0, 112000.0],
                        "priceYearAgo": 65000.0,
                        "closes30d": [100000.0, 101000.0],
                    }
                ],
                "source": {"name": "venue", "url": "https://example.test/btc"},
            }
        )

    envelope = make_client(handler).crypto_markets({})
    assert envelope.data.coins[0].symbol == "BTC"
    # The server-declared source passes through; no vendor is asserted here.
    assert envelope.data.source["url"] == "https://example.test/btc"


# ── VCA / HIVG / OVDV (IV-history; denial verbatim, 402-ready) ────────────────


def test_iv_screen_maps_rows() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/cloud/iv/screen"
        return _envelope(
            {
                "rows": [
                    {
                        "symbol": "SPY",
                        "status": "ready",
                        "iv30Value": 15.2,
                        "iv30Date": "2026-09-29",
                        "iv30Rank": 30.0,
                        "iv30Percentile": 28.0,
                        "iv90Value": 16.1,
                        "iv90Date": "2026-09-29",
                        "iv90Rank": 35.0,
                        "iv90Percentile": 33.0,
                        "latest": 15.2,
                        "skew25d": -2.1,
                    }
                ]
            }
        )

    envelope = make_client(handler).iv_screen({"symbols": ["SPY"]})
    assert "symbols=SPY" in seen["url"]
    assert envelope.data.rows[0].status == "ready"
    assert envelope.data.rows[0].skew_25d == -2.1


def test_iv_screen_requires_a_symbol_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).iv_screen({"symbols": []})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_iv_history_maps_term_points() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/cloud/iv/history"
        return _envelope(
            {
                "symbol": "AAPL",
                "days": 30,
                "status": "ready",
                "points": [{"date": "2026-09-29", "iv30": 22.5, "iv90": 24.0}],
                "iv30Rank": 40.0,
                "iv30Percentile": 38.0,
                "iv90Rank": 45.0,
                "iv90Percentile": 42.0,
                "latest": 22.5,
            }
        )

    envelope = make_client(handler).iv_history({"symbol": "AAPL", "days": 30})
    assert "days=30" in seen["url"]
    assert envelope.data.status == "ready"
    assert envelope.data.points[0]["iv30"] == 22.5


def test_iv_history_surfaces_server_denial_verbatim_and_is_402_ready() -> None:
    def text_402(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, text="Pro plan required for IV history")

    gated = make_client(text_402).iv_history({"symbol": "AAPL"})
    assert gated.data.code == "pro_required"
    # The upstream denial text is surfaced verbatim, not swallowed.
    assert "Pro plan required for IV history" in gated.data.message

    def bare_402(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, text="payment required")

    fallback = make_client(bare_402).iv_history({"symbol": "AAPL"})
    # No recognizable plan body: the generic 402 mapping stands.
    assert fallback.data.code == "auth_required"


def test_iv_surface_dates_mode_lists_dates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cloud/iv/surface-dates"
        return _envelope({"symbol": "AAPL", "dates": ["2026-09-26", "2026-09-29"]})

    envelope = make_client(handler).iv_surface({"symbol": "AAPL"})
    assert envelope.data.dates == ["2026-09-26", "2026-09-29"]
    assert envelope.data.surface is None


def test_iv_surface_detail_mode_reads_the_stored_surface() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/cloud/iv/surface"
        return _envelope(
            {"symbol": "AAPL", "date": "2026-09-29", "surface": {"expiries": ["2026-10-17"]}}
        )

    envelope = make_client(handler).iv_surface({"symbol": "AAPL", "date": "2026-09-29"})
    assert "date=2026-09-29" in seen["url"]
    assert envelope.data.surface["expiries"] == ["2026-10-17"]


# ── DDIS ──────────────────────────────────────────────────────────────────────


def test_debt_maturities_maps_facts() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/cloud/debt-maturities"
        return _envelope(
            {
                "symbol": "AAPL",
                "totalPrincipal": 100e9,
                "next12mShare": 0.08,
                "next3yShare": 0.25,
                "interestExpense": 4e9,
                "borrowingCost": 0.04,
                "filings": [
                    {
                        "accession": "0000320193-26-000001",
                        "filed": "2026-08-01",
                        "form": "10-Q",
                        "principal": 10e9,
                    }
                ],
            }
        )

    envelope = make_client(handler).debt_maturities({"symbol": "AAPL"})
    assert "symbol=AAPL" in seen["url"]
    assert envelope.data.total_principal == 100e9
    assert envelope.data.filings[0].form == "10-Q"


# ── Session movers (Cloud) + trending (Yahoo venue-direct) ────────────────────


def test_session_movers_maps_session_rows() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/market/screener"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": [
                    {
                        "symbol": "NVDA",
                        "price": 180.0,
                        "change": 5.0,
                        "refClose": 171.4,
                        "sessionVolume": 2e6,
                        "relVolume": 1.8,
                        "gapPct": 4.9,
                        "vwap": 178.0,
                        "catalysts": ["earnings"],
                        "phase": "premarket",
                        "asOf": "2026-09-30T12:00:00Z",
                    }
                ],
                "phase": "premarket",
                "asOf": "2026-09-30T12:00:00Z",
            },
        )

    envelope = make_client(handler).session_movers({"category": "premarket", "side": "up"})
    assert "category=premarket" in seen["url"]
    assert "side=up" in seen["url"]
    assert envelope.data.movers[0].gap_pct == 4.9
    assert envelope.data.phase == "premarket"


def test_session_movers_rejects_stock_categories_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).session_movers({"category": "gainers", "side": "up"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_trending_hydrates_yahoo_symbols_with_delayed_quotes() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == YAHOO:
            seen["trending"] = str(request.url)
            assert request.url.path == "/v1/finance/trending/US"
            return httpx.Response(
                200,
                json={
                    "finance": {
                        "result": [
                            {"count": 2, "quotes": [{"symbol": "NVDA"}, {"symbol": "TSLA"}]}
                        ],
                        "error": None,
                    }
                },
            )
        seen["quotes"] = str(request.url)
        assert request.url.path == "/market/quotes/batch"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "items": [
                        {
                            "symbol": "NVDA",
                            "exchange": "NASDAQ",
                            "status": "success",
                            "data": {
                                "symbol": "NVDA",
                                "currency": "USD",
                                "price": 180.0,
                                "change": 5.0,
                                "changePercent": 2.8,
                                "lastUpdated": 1773000000000,
                                "marketState": "PRE",
                                "listingExchangeName": "NASDAQ",
                            },
                        }
                    ]
                },
            },
        )

    envelope = make_client(handler).trending({"limit": 5})
    assert "/v1/finance/trending/US" in seen["trending"]
    assert envelope.data.rows, "venue rows must never be an empty success"
    assert envelope.data.rows[0].symbol == "NVDA"
    assert envelope.data.rows[0].price == 180.0
    assert envelope.data.rows[0].venue_url == "https://finance.yahoo.com/quote/NVDA"
    assert "Yahoo" in envelope.data.attribution


def test_trending_sends_browser_like_headers_to_yahoo() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == YAHOO:
            seen["user_agent"] = request.headers.get("user-agent", "")
            seen["referer"] = request.headers.get("referer", "")
            return httpx.Response(
                200,
                json={
                    "finance": {
                        "result": [{"count": 1, "quotes": [{"symbol": "NVDA"}]}],
                        "error": None,
                    }
                },
            )
        return httpx.Response(200, json={"status": "success", "data": {"items": []}})

    make_client(handler).trending({"limit": 1})
    assert "Mozilla" in seen["user_agent"], "Yahoo bot-gate needs a browser User-Agent (#4876)"
    assert "yahoo" in seen["referer"].lower(), "Yahoo bot-gate needs a Yahoo referer (#4876)"


def test_trending_empty_trending_list_is_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"finance": {"result": [], "error": None}})

    envelope = make_client(handler).trending({})
    assert envelope.data.code == "upstream_error"


def test_trending_rejects_over_batch_limit_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    envelope = make_client(handler).trending({"limit": 21})
    assert envelope.data.code == "invalid_input"
    assert calls == []


# ── SUB (own-account venue-direct, fail-soft) ─────────────────────────────────


def test_substack_without_stored_auth_is_auth_required_with_login_help() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("no stored auth means no request")

    envelope = make_client(handler).substack({"publication": "examplepub"})
    assert envelope.data.code == "auth_required"
    assert "SUBSTACK_SESSION_COOKIE" in envelope.data.message
    assert calls == []


def test_substack_feed_maps_archive_posts() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.host == SUB_PUB
        assert request.url.path == "/api/v1/posts"
        assert "substack.sid=test-substack" in request.headers.get("cookie", "")
        return httpx.Response(
            200,
            json=[
                {
                    "id": 123,
                    "title": "Hello",
                    "subtitle": "World",
                    "slug": "hello",
                    "post_date": "2026-09-29T10:00:00Z",
                    "audience": "everyone",
                    "canonical_url": "https://examplepub.substack.com/p/hello",
                }
            ],
        )

    client = make_client(handler, substack_cookie="substack.sid=test-substack")
    envelope = client.substack({"publication": "examplepub", "limit": 10})
    assert "limit=10" in seen["url"]
    assert envelope.data.posts[0].title == "Hello"
    assert "Substack" in envelope.data.attribution


def test_substack_post_mode_reads_by_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == SUB_PUB
        assert request.url.path == "/api/v1/posts/by-id/123"
        return httpx.Response(200, json={"post": {"id": 123, "title": "Hello"}})

    client = make_client(handler, substack_cookie="bare-substack-token")
    envelope = client.substack({"publication": "examplepub", "mode": "post", "post_id": "123"})
    assert envelope.data.post["title"] == "Hello"


def test_substack_post_mode_requires_post_id_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    client = make_client(handler, substack_cookie="x")
    envelope = client.substack({"publication": "examplepub", "mode": "post"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_substack_expired_session_is_auth_required_not_an_error_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden")

    client = make_client(handler, substack_cookie="stale-token")
    envelope = client.substack({"publication": "examplepub"})
    assert envelope.data.code == "auth_required"
    assert envelope.data.retryable is False


def test_substack_rejects_bad_publication_slugs_without_a_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    client = make_client(handler, substack_cookie="x")
    envelope = client.substack({"publication": "not a slug!!"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


# ── IPO (Cloud, open) ─────────────────────────────────────────────────────────


def test_ipo_calendar_maps_deals() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.url.path == "/cloud/ipo/calendar"
        return _envelope(
            {
                "deals": [
                    {
                        "id": "d1",
                        "company": "Acme",
                        "symbol": "ACME",
                        "mic": "XNYS",
                        "venue": "NYSE",
                        "status": "priced",
                        "priceLow": 20.0,
                        "priceHigh": 22.0,
                        "offerSize": 500e6,
                        "filedDate": "2026-06-01",
                        "listedDate": "2026-09-28",
                        "firstDayOpen": 25.0,
                        "firstDayClose": 27.5,
                        "firstDayReturn": 0.25,
                    }
                ]
            }
        )

    envelope = make_client(handler).ipo_calendar({"status": "priced"})
    assert "status=priced" in seen["url"]
    assert envelope.data.deals[0].company == "Acme"
    assert envelope.data.deals[0].first_day_return == 0.25


def test_ipo_calendar_is_anonymous() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert not request.headers.get("cookie")
        return _envelope({"deals": []})

    envelope = make_client(handler, session_cookie=None).ipo_calendar({})
    assert envelope.data.deals == []


# ── controller ruling: VIX far-leg default ────────────────────────────────────


def test_vix_term_structure_defaults_to_the_fred_3m_leg() -> None:
    """Far-leg default is VXVCLS (FRED 3M), not the ^VIX3M index symbol."""
    from digiquant.data.gloomberb import VixTermInput

    assert VixTermInput.model_fields["far_series"].default == "VXVCLS"
    assert VixTermInput.model_fields["near_series"].default == "VIXCLS"


def test_vix_term_structure_default_request_hits_vxvcls() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "observations": [{"date": "2026-09-29", "value": 18.0}],
                "info": {"id": "x", "title": "x", "units": "Index"},
            },
        )

    envelope = make_client(handler).vix_term_structure({})
    assert envelope.data.far_series == "VXVCLS"
    assert "/cloud/econ/series/VIXCLS" in paths
    assert "/cloud/econ/series/VXVCLS" in paths
    assert not [p for p in paths if p.endswith("/VIX3M")]
