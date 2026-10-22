"""Unit tests for the digiquant gloomberb quote and reference endpoints.

Quotes, the batch quote, ticker financials, options, FX, search, news, the
earnings calendar and the venue list. Deterministic and offline: an
``httpx.MockTransport`` drives the real ``digifetch.HttpFetcher``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    DELAYED_NOTE,
    STALE_NOTE,
    EarningsEvent,
    QuoteInput,
    QuoteResult,
)

from tests.dq.data.gloomberb_client_support import (  # noqa: E402
    AAPL_QUOTE,
    GBP_QUOTE,
    clean_env,
    envelope,
    make_client,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    clean_env(monkeypatch)


def test_quote_success_normalizes_gbp_and_reports_delayed() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["origin"] = request.headers.get("origin", "")
        return envelope(GBP_QUOTE, asOf="2026-09-15T00:00:00Z")

    result = make_client(handler).quote(QuoteInput(symbol="VOD.L", exchange="LSE"))
    assert isinstance(result.data, QuoteResult)
    quote = result.data.quote
    assert quote is not None
    assert quote.price == pytest.approx(123.45)
    assert quote.currency == "GBP"
    assert quote.change == pytest.approx(0.1)
    assert result.stale is False
    assert result.delay_note == DELAYED_NOTE
    assert "symbol=VOD.L" in seen["url"]
    assert "exchange=LSE" in seen["url"]
    assert result.fetched_at.tzinfo is not None


def test_quote_wire_stale_maps_to_the_stale_note() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope(AAPL_QUOTE, stale=True)

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.stale is True
    assert result.delay_note == STALE_NOTE


def test_quote_schema_validation_error_is_invalid_input_without_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return envelope(None)

    result = make_client(handler).quote({"symbol": "", "bogus": 1})  # type: ignore[arg-type]
    assert result.data.code == "invalid_input"  # type: ignore[union-attr]
    assert calls == []


def test_quotes_batch_maps_items_and_stale_envelope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope(
            {
                "items": [
                    {
                        "symbol": "AAPL",
                        "exchange": "NASDAQ",
                        "status": "success",
                        "data": AAPL_QUOTE,
                    },
                    {
                        "symbol": "VOD.L",
                        "exchange": "LSE",
                        "status": "success",
                        "stale": True,
                        "data": GBP_QUOTE,
                    },
                ]
            }
        )

    result = make_client(handler).quotes_batch({"symbols": ["AAPL", "VOD.L"]})
    assert result.stale is True
    quotes = result.data.quotes  # type: ignore[union-attr]
    assert quotes[0].quote is not None and quotes[0].quote.currency == "USD"
    assert quotes[1].quote is None and quotes[1].reason_code == "stale"


def test_ticker_financials_normalizes_quote_and_price_history() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope(
            {
                "quote": GBP_QUOTE,
                "annualStatements": [{"date": "2026-03-31", "totalRevenue": 1.0}],
                "priceHistory": [{"date": "2026-02-23", "close": 100.0}],
            },
            currency="GBp",
        )

    result = make_client(handler).ticker_financials({"symbol": "VOD.L"})
    financials = result.data.financials  # type: ignore[union-attr]
    assert financials.quote is not None
    assert financials.quote.price == pytest.approx(123.45)
    assert financials.price_history[0].date == "2026-02-23"
    assert financials.annual_statements[0].total_revenue == pytest.approx(1.0)


def test_options_chain_sends_epoch_seconds_and_normalizes_sides() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return envelope(
            {
                "underlyingSymbol": "AAPL",
                "expirationDates": [1780000000],
                "calls": [{"contractSymbol": "AAPL260101C00100000", "strike": 100.0}],
                "puts": [{"contractSymbol": "AAPL260101P00100000", "strike": 100.0}],
                "delayMinutes": 15,
            }
        )

    result = make_client(handler).options_chain({"symbol": "AAPL", "expiration": 1780000000})
    assert "expirationDate=1780000000" in seen["url"]
    assert result.delay_note == DELAYED_NOTE
    chain = result.data.chain  # type: ignore[union-attr]
    assert chain.calls[0].side == "call"
    assert chain.puts[0].side == "put"


def test_exchange_rate_keeps_asof_and_delay_distinct() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope(
            {"rate": 0.85, "source": "yahoo", "delayMinutes": 15, "stale": False},
            asOf="2026-09-15T00:00:00Z",
        )

    result = make_client(handler).exchange_rate({"from_currency": "EUR"})
    assert result.data.rate == pytest.approx(0.85)  # type: ignore[union-attr]
    assert result.data.as_of == "2026-09-15T00:00:00Z"  # type: ignore[union-attr]
    assert result.stale is False
    assert result.delay_note == DELAYED_NOTE


def test_search_maps_listings_and_sends_limit() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return envelope(
            [
                {
                    "providerId": "gloomberb-cloud",
                    "symbol": "VOD.L",
                    "name": "Vodafone",
                    "exchange": "LSE",
                    "type": "equity",
                }
            ]
        )

    result = make_client(handler).search({"query": "vodafone", "limit": 5})
    assert "limit=5" in seen["url"]
    assert result.data.results[0].symbol == "VOD.L"  # type: ignore[union-attr]
    assert result.data.limit_clamped is False


def test_search_clamps_above_cap_and_flags_the_clamp() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return envelope([])

    result = make_client(handler).search({"query": "vodafone", "limit": 25})
    assert "limit=10" in seen["url"]
    assert result.data.limit_clamped is True


def test_news_list_payload_is_direct_not_enveloped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "n1",
                        "headline": "Chips rally",
                        "summary": "Semis lead",
                        "primaryUrl": "https://example.test/n1",
                        "primarySource": "Reuters",
                    }
                ],
                "nextCursor": None,
            },
        )

    result = make_client(handler).news({"feed": "latest", "limit": 5})
    assert result.data.items[0].headline == "Chips rally"


def test_news_story_path_encodes_the_story_id() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"id": "a/b", "headline": "Story"})

    result = make_client(handler).news({"story_id": "a/b"})
    assert "/news/a%2Fb" in seen["url"]
    assert result.data.items[0].headline == "Story"


def test_earnings_calendar_uses_injected_provider_and_horizon() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the Yahoo path must not touch the Cloud transport")

    events = [
        EarningsEvent(symbol="AAPL", earnings_date=date(2026, 9, 20), eps_estimate=1.2),
        EarningsEvent(symbol="AAPL", earnings_date=date(2027, 1, 1), eps_estimate=1.5),
    ]
    client = make_client(
        handler,
        now=lambda: datetime(2026, 9, 15, tzinfo=timezone.utc),
        earnings_provider=lambda symbol: events,
    )
    result = client.earnings_calendar({"symbols": ["AAPL"], "horizon_days": 90})
    assert [event.earnings_date for event in result.data.events] == [date(2026, 9, 20)]


def test_earnings_calendar_fails_soft_per_symbol() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no Cloud transport on the Yahoo path")

    def provider(symbol: str) -> list[EarningsEvent]:
        if symbol == "BAD":
            raise RuntimeError("yahoo throttled")
        return [EarningsEvent(symbol=symbol, earnings_date=date(2026, 9, 20))]

    client = make_client(
        handler,
        now=lambda: datetime(2026, 9, 15, tzinfo=timezone.utc),
        earnings_provider=provider,
    )
    result = client.earnings_calendar({"symbols": ["BAD", "AAPL"]})
    assert [event.symbol for event in result.data.events] == ["AAPL"]  # type: ignore[union-attr]
    assert result.warnings and "yahoo throttled" in result.warnings[0]


def test_quote_payload_stale_folds_into_the_envelope() -> None:
    """Spec §3.2/§5.3: payload-level `stale` is part of the freshness union."""

    def handler(request: httpx.Request) -> httpx.Response:
        return envelope({**AAPL_QUOTE, "stale": True, "dataSource": "live"})

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.stale is True
    assert result.delay_note == STALE_NOTE


def test_exchange_rate_payload_stale_folds_into_the_envelope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope({"rate": 0.85, "stale": True, "dataSource": "live"})

    result = make_client(handler).exchange_rate({"from_currency": "EUR"})
    assert result.stale is True
    assert result.data.stale is True  # type: ignore[union-attr]
    assert result.delay_note == STALE_NOTE


def test_malformed_exchange_rate_payload_maps_to_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope({"source": "yahoo"})  # no finite rate

    result = make_client(handler).exchange_rate({"from_currency": "EUR"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "no finite rate" in result.data.message


def test_venues_is_anonymous_and_maps_the_venue_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "providerId": "gloomberb-cloud",
                    "checkedAt": 1789494522591,
                    "refreshAt": 1789494582591,
                    "venues": [
                        {
                            "mic": "XADS",
                            "name": "ADX",
                            "countryCode": "AE",
                            "isOpen": False,
                            "timeToOpenSeconds": 43816,
                        }
                    ],
                },
                "asOf": "2026-09-15T17:48:42.591Z",
            },
        )

    result = make_client(handler).venues()
    data = result.data  # type: ignore[union-attr]
    assert data.provider_id == "gloomberb-cloud"
    assert data.checked_at == 1789494522591
    venue = data.venues[0]
    assert venue.mic == "XADS"
    assert venue.country_code == "AE"
    assert venue.is_open is False
    assert venue.time_to_open_seconds == 43816


def test_venues_payload_level_stale_folds_into_the_envelope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"providerId": "gloomberb-cloud", "stale": True, "venues": []},
            },
        )

    result = make_client(handler).venues()
    assert result.stale is True
    assert result.delay_note == STALE_NOTE
