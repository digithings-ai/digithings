"""Unit tests for digiquant.data.gloomberb.client (#4069).

Deterministic and offline: an ``httpx.MockTransport`` drives the real
``digifetch.HttpFetcher`` (with ``allowed_hosts`` skipping DNS so the SSRF
guard is exercised without a socket). Covers the §5.3 error mapping, the §5.3
freshness union, the §5.5 cache/breaker/kill switch, and the §5.4 normalizers
on the client path.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    DELAYED_NOTE,
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    RETRYABLE_EXCEPTIONS,
    STALE_NOTE,
    EarningsEvent,
    GloomberbClient,
    QuoteInput,
    QuoteResult,
)

from digifetch import HttpFetcher, RateLimiter, RetryPolicy, SsrfBlockedError  # noqa: E402

GBP_QUOTE = {
    "symbol": "VOD.L",
    "currency": "GBp",
    "price": 12345.0,
    "change": 10.0,
    "changePercent": 0.081,
    "lastUpdated": 1773000000000,
    "marketState": "CLOSED",
    "listingExchangeName": "LSE",
    "dataSource": "delayed",
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
    "dataSource": "live",
}

INTRADAY_OUTLIER_POINTS = [
    {"date": "2026-02-23T14:30:00Z", "open": 100.0, "high": 100.5, "low": 99.8, "close": 100.0},
    {"date": "2026-02-23T14:35:00Z", "open": 400.0, "high": 401.0, "low": 399.0, "close": 100.2},
    {"date": "2026-02-23T14:40:00Z", "open": 100.2, "high": 100.4, "low": 100.0, "close": 100.1},
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GLOOMBERB_ENABLED_ENV, raising=False)
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)


def make_client(handler: Any, **kwargs: Any) -> GloomberbClient:
    allowed_hosts = kwargs.pop("allowed_hosts", ["api.gloom.sh"])
    fetcher = HttpFetcher(
        transport=httpx.MockTransport(handler),
        allowed_hosts=allowed_hosts,
    )
    kwargs.setdefault("rate_limiter", RateLimiter(0))
    kwargs.setdefault("retry_policy", RetryPolicy(attempts=1))
    return GloomberbClient(fetcher=fetcher, **kwargs)


def envelope(data: Any, status: str = "success", **extra: Any) -> httpx.Response:
    payload = {"status": status, "data": data, **extra}
    return httpx.Response(200, json=payload)


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


def test_gated_endpoint_401_maps_to_auth_required() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})

    client = make_client(handler, session_cookie="token-value")
    result = client.holders({"symbol": "AAPL"})
    assert result.data.code == "auth_required"  # type: ignore[union-attr]
    assert GLOOMBERB_SESSION_COOKIE_ENV in result.data.message  # type: ignore[union-attr]


def test_gated_endpoint_without_cookie_fails_before_any_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return envelope({"symbol": "AAPL", "holders": []})

    result = make_client(handler).corporate_actions({"symbol": "AAPL"})
    assert result.data.code == "auth_required"  # type: ignore[union-attr]
    assert calls == []


def test_session_cookie_name_value_pair_is_attached_to_gated_endpoints() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cookie"] = request.headers.get("cookie", "")
        return envelope({"symbol": "AAPL", "holders": []})

    client = make_client(handler, session_cookie="gloomberb.session_token=abc")
    result = client.holders({"symbol": "AAPL"})
    assert result.data.holders == []  # type: ignore[union-attr]
    assert seen["cookie"] == "gloomberb.session_token=abc"


def test_bare_session_cookie_uses_both_upstream_cookie_names() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cookie"] = request.headers.get("cookie", "")
        return envelope({"symbol": "AAPL", "holders": []})

    make_client(handler, session_cookie="just-a-token").holders({"symbol": "AAPL"})
    assert "__Secure-gloomberb.session_token=just-a-token" in seen["cookie"]
    assert "gloomberb.session_token=just-a-token" in seen["cookie"]


def test_429_surfaces_retry_after_and_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "42"}, json={"message": "slow down"})

    policy = RetryPolicy(attempts=3, base_delay=0.0, jitter=False, retry_on=RETRYABLE_EXCEPTIONS)
    result = make_client(handler, retry_policy=policy).quote({"symbol": "AAPL"})
    assert result.data.code == "rate_limited"  # type: ignore[union-attr]
    assert "42" in result.data.message  # type: ignore[union-attr]
    assert result.data.retryable is False  # type: ignore[union-attr]
    assert len(calls) == 1


def test_404_maps_to_not_found_and_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(404, json={"message": "nope"})

    policy = RetryPolicy(attempts=3, base_delay=0.0, jitter=False, retry_on=RETRYABLE_EXCEPTIONS)
    result = make_client(handler, retry_policy=policy).quote({"symbol": "AAPL"})
    assert result.data.code == "not_found"  # type: ignore[union-attr]
    assert len(calls) == 1


def test_5xx_is_retried_then_surfaces_retryable_upstream_error() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, json={"message": "unavailable"})

    policy = RetryPolicy(attempts=2, base_delay=0.0, jitter=False, retry_on=RETRYABLE_EXCEPTIONS)
    result = make_client(handler, retry_policy=policy).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert result.data.retryable is True  # type: ignore[union-attr]
    assert len(calls) == 2


def test_timeout_maps_to_retryable_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert result.data.retryable is True  # type: ignore[union-attr]


@pytest.mark.parametrize("status", ["empty", "unsupported"])
def test_empty_and_unsupported_statuses_map_to_not_found(status: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": status, "data": None, "reasonCode": "no data"})

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "not_found"  # type: ignore[union-attr]
    assert "no data" in result.data.message  # type: ignore[union-attr]


def test_retryable_error_status_maps_to_retryable_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "retryable_error", "data": None})

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert result.data.retryable is True  # type: ignore[union-attr]


def test_fatal_error_status_maps_to_non_retryable_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "fatal_error", "data": None})

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert result.data.retryable is False  # type: ignore[union-attr]


def test_non_json_body_maps_to_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "non-JSON" in result.data.message  # type: ignore[union-attr]


def test_kill_switch_off_disables_calls_without_any_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return envelope(AAPL_QUOTE)

    result = make_client(handler, enabled=False).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "kill switch" in result.data.message  # type: ignore[union-attr]
    assert calls == []


def test_kill_switch_reads_the_env_flag_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return envelope(AAPL_QUOTE)

    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "0")
    disabled = make_client(handler)
    assert disabled.enabled is False
    assert disabled.quote({"symbol": "AAPL"}).data.code == "upstream_error"  # type: ignore[union-attr]

    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    enabled = make_client(handler)
    assert enabled.enabled is True
    assert isinstance(enabled.quote({"symbol": "AAPL"}).data, QuoteResult)
    assert len(calls) == 1


def test_ttl_cache_hit_avoids_a_second_fetch() -> None:
    now = {"t": 100.0}
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return envelope(AAPL_QUOTE)

    client = make_client(handler, monotonic=lambda: now["t"], cache_ttl=900.0)
    client.quote({"symbol": "AAPL"})
    client.quote({"symbol": "AAPL"})
    assert len(calls) == 1

    now["t"] += 901.0
    client.quote({"symbol": "AAPL"})
    assert len(calls) == 2

    client.quote({"symbol": "MSFT"})
    assert len(calls) == 3


def test_error_envelopes_are_not_cached() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, json={"message": "unavailable"})

    client = make_client(handler)
    for _ in range(2):
        assert client.quote({"symbol": "AAPL"}).data.code == "upstream_error"  # type: ignore[union-attr]
    assert len(calls) == 2


def test_circuit_breaker_opens_after_consecutive_failures_and_half_opens() -> None:
    now = {"t": 0.0}
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        symbol = request.url.params.get("symbol", "")
        calls.append(symbol)
        if symbol in ("FAIL1", "FAIL2"):
            return httpx.Response(500, json={"message": "boom"})
        return envelope({**AAPL_QUOTE, "symbol": symbol})

    client = make_client(
        handler,
        monotonic=lambda: now["t"],
        circuit_failure_threshold=2,
        circuit_reset_seconds=60.0,
    )
    assert client.quote({"symbol": "FAIL1"}).data.code == "upstream_error"  # type: ignore[union-attr]
    assert client.quote({"symbol": "FAIL2"}).data.code == "upstream_error"  # type: ignore[union-attr]
    assert calls == ["FAIL1", "FAIL2"]

    # Open: fail fast, no wire call.
    fast = client.quote({"symbol": "FAIL3"})
    assert fast.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "circuit breaker" in fast.data.message  # type: ignore[union-attr]
    assert calls == ["FAIL1", "FAIL2"]

    # Half-open after the reset window: one probe is allowed, success closes it.
    now["t"] += 61.0
    assert isinstance(client.quote({"symbol": "PROBE"}).data, QuoteResult)
    assert calls == ["FAIL1", "FAIL2", "PROBE"]
    assert isinstance(client.quote({"symbol": "AFTER"}).data, QuoteResult)
    assert calls == ["FAIL1", "FAIL2", "PROBE", "AFTER"]


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


def test_price_history_sends_interval_and_range_key() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return envelope([], currency="USD", providerMeta={"provider": "yahoo"})

    make_client(handler).price_history({"symbol": "AAPL", "resolution": "1d", "range": "6M"})
    assert "interval=1day" in seen["url"]
    assert "rangeKey=6M" in seen["url"]


def test_price_history_rejects_malformed_intraday_from_non_yahoo_upstream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope(INTRADAY_OUTLIER_POINTS, providerMeta={"provider": "twelvedata"})

    result = make_client(handler).price_history(
        {"symbol": "AAPL", "resolution": "5m", "range": "1W"}
    )
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "OHLC validation" in result.data.message  # type: ignore[union-attr]


def test_price_history_keeps_malformed_intraday_from_yahoo() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope(INTRADAY_OUTLIER_POINTS, providerMeta={"provider": "yahoo"})

    result = make_client(handler).price_history(
        {"symbol": "AAPL", "resolution": "5m", "range": "1W"}
    )
    bars = result.data.bars  # type: ignore[union-attr]
    assert len(bars) == 3
    assert bars[0].date == "2026-02-23T14:30:00Z"


def test_price_history_metadata_carries_bar_count_and_upstream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope(
            [{"date": "2026-02-23T00:00:00.000Z", "close": 200.0}],
            currency="GBp",
            providerMeta={"provider": "yahoo", "timezone": "Europe/London"},
        )

    result = make_client(handler).price_history(
        {"symbol": "SHEL.L", "resolution": "1d", "range": "5Y", "exchange": "LSE"}
    )
    metadata = result.data.metadata  # type: ignore[union-attr]
    assert metadata.bar_count == 1
    # Canonical unit: bars are divided to GBP, so metadata must not keep "GBp".
    assert metadata.currency == "GBP"
    assert metadata.upstream_provider == "yahoo"
    assert metadata.timezone == "Europe/London"


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
    assert result.data.limit_clamped is False  # type: ignore[union-attr]


def test_search_clamps_above_cap_and_flags_the_clamp() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return envelope([])

    result = make_client(handler).search({"query": "vodafone", "limit": 25})
    assert "limit=10" in seen["url"]
    assert result.data.limit_clamped is True  # type: ignore[union-attr]


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
    assert result.data.items[0].headline == "Chips rally"  # type: ignore[union-attr]


def test_news_story_path_encodes_the_story_id() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"id": "a/b", "headline": "Story"})

    result = make_client(handler).news({"story_id": "a/b"})
    assert "/news/a%2Fb" in seen["url"]
    assert result.data.items[0].headline == "Story"  # type: ignore[union-attr]


def test_sec_filings_direct_payload_maps_filings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "filings": [
                    {
                        "accessionNumber": "0001-26-1",
                        "form": "10-Q",
                        "filingDate": "2026-08-01",
                        "cik": "789019",
                        "filingUrl": "https://sec.example/1",
                    }
                ],
                "hasMore": False,
                "nextOffset": 1,
            },
        )

    result = make_client(handler).sec_filings({"ticker": "MSFT", "what": "filings", "count": 1})
    assert result.data.filings[0].form == "10-Q"  # type: ignore[union-attr]
    assert result.data.documents is None  # type: ignore[union-attr]


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
    assert [event.earnings_date for event in result.data.events] == [date(2026, 9, 20)]  # type: ignore[union-attr]


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


# ── review-fix regressions (#4069 follow-up) ─────────────────────────────────


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


def test_repeated_auth_required_does_not_open_the_breaker() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/market/holders":
            return httpx.Response(401, json={"message": "Unauthorized"})
        return envelope(AAPL_QUOTE)

    client = make_client(handler, session_cookie="token-value", circuit_failure_threshold=2)
    for _ in range(3):
        assert client.holders({"symbol": "AAPL"}).data.code == "auth_required"  # type: ignore[union-attr]

    # Deterministic 4xx outcomes must not trip the breaker for other tools.
    assert isinstance(client.quote({"symbol": "AAPL"}).data, QuoteResult)
    assert calls == ["/market/holders"] * 3 + ["/market/quote"]


def test_malformed_exchange_rate_payload_maps_to_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope({"source": "yahoo"})  # no finite rate

    result = make_client(handler).exchange_rate({"from_currency": "EUR"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "no finite rate" in result.data.message  # type: ignore[union-attr]


def test_too_many_redirects_maps_to_typed_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TooManyRedirects("exceeded redirects")

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "exceeded redirects" in result.data.message  # type: ignore[union-attr]


def test_ssrf_blocked_maps_to_typed_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise SsrfBlockedError("host is blocked")

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "SSRF" in result.data.message  # type: ignore[union-attr]


def test_gated_cookie_is_not_forwarded_to_a_cross_origin_redirect() -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("cookie")))
        if request.url.host == "api.gloom.sh":
            return httpx.Response(302, headers={"location": "https://cdn.other.example/steal"})
        return envelope({"symbol": "AAPL", "holders": []})

    result = make_client(
        handler,
        allowed_hosts=["api.gloom.sh", "cdn.other.example"],
        session_cookie="gloomberb.session_token=secret",
    ).holders({"symbol": "AAPL"})
    assert result.data.holders == []  # type: ignore[union-attr]
    assert seen[0][1] == "gloomberb.session_token=secret"
    assert seen[1][0] == "https://cdn.other.example/steal"
    assert seen[1][1] is None


def test_cookie_is_not_attached_to_ungated_endpoints() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cookie"] = request.headers.get("cookie")
        return envelope(AAPL_QUOTE)

    result = make_client(handler, session_cookie="gloomberb.session_token=secret").quote(
        {"symbol": "AAPL"}
    )
    assert isinstance(result.data, QuoteResult)
    assert seen["cookie"] is None


def test_cache_evicts_expired_entries_on_access() -> None:
    now = {"t": 0.0}
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return envelope(AAPL_QUOTE)

    client = make_client(handler, monotonic=lambda: now["t"], cache_ttl=900.0)
    client.quote({"symbol": "AAPL"})
    assert client.cache_size == 1

    now["t"] += 901.0
    client.quote({"symbol": "MSFT"})
    # The expired AAPL entry is evicted before the new put (no unbounded growth).
    assert client.cache_size == 1
    assert len(calls) == 2


def test_cache_is_size_bounded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope(AAPL_QUOTE)

    client = make_client(handler, monotonic=lambda: 0.0, cache_max_entries=2)
    for symbol in ("AAPL", "MSFT", "NVDA"):
        client.quote({"symbol": symbol})
    assert client.cache_size == 2


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("on", True),
        ("yes", True),
        ("0", False),
        ("false", False),
        ("ture", False),
        ("", False),
    ],
)
def test_kill_switch_env_allowlist_fails_closed(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return envelope(AAPL_QUOTE)

    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, value)
    client = make_client(handler)
    assert client.enabled is expected
    if not expected:
        result = client.quote({"symbol": "AAPL"})
        assert result.data.code == "upstream_error"  # type: ignore[union-attr]
        assert calls == []


def test_429_retry_after_within_bound_is_slept() -> None:
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "2"}, json={"message": "slow down"})

    result = make_client(handler, sleep=slept.append).quote({"symbol": "AAPL"})
    assert result.data.code == "rate_limited"  # type: ignore[union-attr]
    assert slept == [2.0]
    assert "waited 2s" in result.data.message  # type: ignore[union-attr]


def test_429_retry_after_above_bound_is_not_slept() -> None:
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "999"}, json={"message": "slow down"})

    result = make_client(handler, sleep=slept.append).quote({"symbol": "AAPL"})
    assert result.data.code == "rate_limited"  # type: ignore[union-attr]
    assert slept == []
    assert "999" in result.data.message  # type: ignore[union-attr]
    assert "not slept" in result.data.message  # type: ignore[union-attr]


def test_sec_filing_documents_requests_the_documents_path() -> None:
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

    result = make_client(handler).sec_filings(
        {"ticker": "MSFT", "what": "documents", "cik": "789019", "accession": "0001-26-1"}
    )
    assert "/cloud/sec/filing/documents" in seen["url"]
    assert "cik=789019" in seen["url"]
    assert "accession=0001-26-1" in seen["url"]
    assert result.data.documents[0].type == "10-Q"  # type: ignore[union-attr]
    assert result.data.filings is None  # type: ignore[union-attr]


def test_sec_filing_content_returns_the_content_string() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": "<html>10-Q</html>", "form4": None})

    result = make_client(handler).sec_filings(
        {"ticker": "MSFT", "what": "content", "cik": "789019", "accession": "0001-26-1"}
    )
    assert result.data.content == "<html>10-Q</html>"  # type: ignore[union-attr]
