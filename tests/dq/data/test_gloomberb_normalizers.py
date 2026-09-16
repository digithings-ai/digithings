"""Unit tests for digiquant.data.gloomberb.normalizers (#4069).

Golden fixtures: a GBp (LSE) listing and an intraday series, plus the §5.4
unit/interval/date/malformed-intraday/day-range rules and the §5.3 freshness
union. No network.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb.normalizers import (  # noqa: E402
    DELAYED_NOTE,
    STALE_NOTE,
    CurrencyUnit,
    derive_freshness,
    is_intraday_interval,
    is_intraday_resolution,
    is_malformed_intraday_history,
    normalize_analyst_research,
    normalize_bars,
    normalize_cds_trades,
    normalize_congress_trades,
    normalize_corporate_actions,
    normalize_econ_calendar,
    normalize_econ_series,
    normalize_equity_diagnostic,
    normalize_exchange_rate,
    normalize_filing_events,
    normalize_funds_13f,
    normalize_holders,
    normalize_holdings_13f,
    normalize_news_list,
    normalize_options_chain,
    normalize_price_value_by_divisor,
    normalize_proxy_statements,
    normalize_quote,
    normalize_quotes_batch_items,
    normalize_research_hits,
    normalize_research_search,
    normalize_risk_reports,
    normalize_screener,
    normalize_search_results,
    normalize_sec_documents,
    normalize_sec_filings,
    normalize_shiller,
    normalize_short_interest,
    normalize_statements,
    normalize_transcript_detail,
    normalize_transcripts,
    normalize_tweets,
    normalize_venues,
    normalize_yield_curve,
    parse_cloud_price_point_date,
    resolve_currency_unit,
    resolve_exchange_timezone,
    to_cloud_interval,
)

# Golden fixture 1: an LSE listing quoted in pence (GBp), as the wire sends it.
GBP_QUOTE = {
    "symbol": "VOD.L",
    "currency": "GBp",
    "price": 12345.0,
    "change": 10.0,
    "changePercent": 0.081,
    "previousClose": 12300.0,
    "high52w": 15000.0,
    "low52w": 8000.0,
    "open": 12350.0,
    "high": 12400.0,
    "low": 12300.0,
    "volume": 1_000_000,
    "lastUpdated": 1773000000000,
    "marketState": "CLOSED",
    "listingExchangeName": "LSE",
    "dataSource": "delayed",
    "providerId": "gloomberb-cloud",
}

# Golden fixture 2: an intraday series with an ISO-datetime wire date.
INTRADAY_POINTS = [
    {"date": "2026-02-23T14:30:00.000Z", "open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5},
    {
        "date": "2026-02-23T14:35:00.000Z",
        "open": 100.5,
        "high": 101.5,
        "low": 100.0,
        "close": 101.0,
    },
    {
        "date": "2026-02-23T14:40:00.000Z",
        "open": 101.0,
        "high": 101.8,
        "low": 100.9,
        "close": 101.5,
    },
]


@pytest.mark.parametrize(
    ("wire", "expected"),
    [
        ("GBp", CurrencyUnit("GBP", 100)),
        ("GBX", CurrencyUnit("GBP", 100)),
        ("ILA", CurrencyUnit("ILS", 100)),
        ("ZAc", CurrencyUnit("ZAR", 100)),
        ("USD", CurrencyUnit("USD", 1)),
        ("gbp", CurrencyUnit("GBP", 1)),
        ("", CurrencyUnit("", 1)),
        (None, CurrencyUnit("", 1)),
    ],
)
def test_resolve_currency_unit(wire: str | None, expected: CurrencyUnit) -> None:
    assert resolve_currency_unit(wire) == expected


def test_normalize_price_value_by_divisor() -> None:
    assert normalize_price_value_by_divisor(12345.0, 100) == pytest.approx(123.45)
    assert normalize_price_value_by_divisor(100.0, 1) == 100.0
    assert normalize_price_value_by_divisor(None, 100) is None
    assert normalize_price_value_by_divisor(math.inf, 100) == math.inf


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("1m", "1min"),
        ("5m", "5min"),
        ("15m", "15min"),
        ("30m", "30min"),
        ("45m", "45min"),
        ("1d", "1day"),
        ("1wk", "1week"),
        ("1mo", "1month"),
        ("1h", "1h"),
        ("1Y", "1Y"),
    ],
)
def test_to_cloud_interval(token: str, expected: str) -> None:
    assert to_cloud_interval(token) == expected


def test_is_intraday_interval() -> None:
    assert is_intraday_interval("5min")
    assert is_intraday_interval("1h")
    assert not is_intraday_interval("1day")
    assert not is_intraday_interval("1week")


def test_is_intraday_resolution() -> None:
    assert is_intraday_resolution("5m")
    assert is_intraday_resolution("1h")
    assert not is_intraday_resolution("1d")


def test_resolve_exchange_timezone() -> None:
    assert resolve_exchange_timezone("LSE") == "Europe/London"
    assert resolve_exchange_timezone("lse") == "Europe/London"
    assert resolve_exchange_timezone("NASDAQ") == "America/New_York"
    assert resolve_exchange_timezone("UNKNOWN") is None
    assert resolve_exchange_timezone(None) is None


def test_parse_explicit_utc_datetime() -> None:
    parsed = parse_cloud_price_point_date("2026-09-07T00:00:00.000Z")
    assert parsed.isoformat() == "2026-09-07T00:00:00+00:00"


def test_parse_date_only_becomes_midnight_utc() -> None:
    parsed = parse_cloud_price_point_date("2026-09-07")
    assert parsed.isoformat() == "2026-09-07T00:00:00+00:00"


def test_parse_exchange_local_wall_time_uses_exchange_zone() -> None:
    # 08:00 London in June is BST (UTC+1) -> 07:00Z.
    parsed = parse_cloud_price_point_date("2026-06-10 08:00:00", exchange="LSE")
    assert parsed.isoformat() == "2026-06-10T07:00:00+00:00"


def test_parse_unknown_exchange_falls_back_to_utc() -> None:
    parsed = parse_cloud_price_point_date("2026-06-10 08:00:00", exchange="NOWHERE")
    assert parsed.isoformat() == "2026-06-10T08:00:00+00:00"


def test_parse_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_cloud_price_point_date("not-a-date")
    with pytest.raises(ValueError):
        parse_cloud_price_point_date(None)


def test_normalize_quote_gbp_listing_fixture() -> None:
    quote = normalize_quote(GBP_QUOTE)
    assert quote.currency == "GBP"
    assert quote.price == pytest.approx(123.45)
    assert quote.change == pytest.approx(0.1)
    assert quote.previous_close == pytest.approx(123.0)
    assert quote.high52w == pytest.approx(150.0)
    assert quote.low52w == pytest.approx(80.0)
    assert quote.open == pytest.approx(123.5)
    # changePercent and volume are never divided.
    assert quote.change_percent == pytest.approx(0.081)
    assert quote.volume == 1_000_000


def test_normalize_intraday_series_fixture() -> None:
    bars = normalize_bars(INTRADAY_POINTS, resolution="5m")
    assert [bar.date for bar in bars] == [
        "2026-02-23T14:30:00Z",
        "2026-02-23T14:35:00Z",
        "2026-02-23T14:40:00Z",
    ]
    assert bars[1].close == pytest.approx(101.0)
    assert bars[1].open == pytest.approx(100.5)


def test_normalize_bars_sorts_and_collapses_single_timestamp() -> None:
    out_of_order = [
        {"date": "2026-02-23T14:35:00Z", "close": 2.0},
        {"date": "2026-02-23T14:30:00Z", "close": 1.0},
    ]
    bars = normalize_bars(out_of_order, resolution="5m")
    assert [bar.close for bar in bars] == [1.0, 2.0]
    collapsed = normalize_bars(
        [{"date": "2026-02-23T14:30:00Z", "close": 1.0}] * 3, resolution="5m"
    )
    assert collapsed == []


def test_normalize_bars_daily_keeps_date_only_and_applies_divisor() -> None:
    bars = normalize_bars(
        [{"date": "2026-02-23T00:00:00.000Z", "open": 150.0, "close": 200.0}],
        resolution="1d",
        divisor=100,
    )
    assert bars[0].date == "2026-02-23"
    assert bars[0].close == pytest.approx(2.0)
    assert bars[0].open == pytest.approx(1.5)


def test_normalize_bars_skips_unparseable_dates_and_missing_closes() -> None:
    bars = normalize_bars(
        [
            {"date": "nope", "close": 1.0},
            {"date": "2026-02-23T14:30:00Z"},
            {"date": "2026-02-23T14:30:00Z", "close": 3.0},
        ],
        resolution="5m",
    )
    assert [bar.close for bar in bars] == [3.0]


def test_malformed_intraday_rejects_isolated_outlier() -> None:
    points = [
        {"date": "2026-02-23T14:30:00Z", "open": 100.0, "high": 100.5, "low": 99.8, "close": 100.0},
        {
            "date": "2026-02-23T14:35:00Z",
            "open": 400.0,
            "high": 401.0,
            "low": 399.0,
            "close": 100.2,
        },
        {
            "date": "2026-02-23T14:40:00Z",
            "open": 100.2,
            "high": 100.4,
            "low": 100.0,
            "close": 100.1,
        },
    ]
    bars = normalize_bars(points, resolution="5m")
    assert is_malformed_intraday_history(bars) is True


def test_malformed_intraday_accepts_stable_series() -> None:
    bars = normalize_bars(INTRADAY_POINTS, resolution="5m")
    assert is_malformed_intraday_history(bars) is False


def test_malformed_intraday_ignores_daily_gaps() -> None:
    points = [
        {"date": "2026-02-23", "open": 100.0, "high": 100.5, "low": 99.8, "close": 100.0},
        {"date": "2026-02-24", "open": 400.0, "high": 401.0, "low": 399.0, "close": 100.2},
        {"date": "2026-02-25", "open": 100.2, "high": 100.4, "low": 100.0, "close": 100.1},
    ]
    bars = normalize_bars(points, resolution="1d")
    assert is_malformed_intraday_history(bars) is False


def test_consolidate_day_range_regular_session_keeps_price_inside_range() -> None:
    quote = normalize_quote(
        {
            "symbol": "AAPL",
            "currency": "USD",
            "price": 200.0,
            "change": 1.0,
            "changePercent": 0.5,
            "high": 199.0,
            "low": 201.0,
            "lastUpdated": 1773000000000,
            "marketState": "REGULAR",
            "sessionConfidence": "high",
            "listingExchangeName": "NASDAQ",
        }
    )
    assert quote.high == pytest.approx(200.0)
    assert quote.low == pytest.approx(200.0)


def test_consolidate_day_range_closed_session_is_untouched() -> None:
    quote = normalize_quote(
        {
            "symbol": "AAPL",
            "currency": "USD",
            "price": 200.0,
            "change": 1.0,
            "changePercent": 0.5,
            "lastUpdated": 1773000000000,
            "marketState": "CLOSED",
            "listingExchangeName": "NASDAQ",
        }
    )
    assert quote.high is None
    assert quote.low is None


def test_freshness_stale_wire_flag_wins() -> None:
    fresh = derive_freshness(stale=True)
    assert fresh.stale is True
    assert fresh.delay_note == STALE_NOTE


def test_freshness_delayed_data_source_is_not_stale() -> None:
    fresh = derive_freshness(data_source="delayed")
    assert fresh.stale is False
    assert fresh.delay_note == DELAYED_NOTE


def test_freshness_delay_minutes_is_a_delay_not_stale() -> None:
    fresh = derive_freshness(delay_minutes=15)
    assert fresh.stale is False
    assert fresh.delay_note == DELAYED_NOTE
    assert derive_freshness(delay_minutes=0, data_source="live").delay_note is None
    assert derive_freshness().delay_note is None


def test_freshness_both_signals_keep_stale_note_and_stale_flag() -> None:
    fresh = derive_freshness(stale=True, data_source="delayed", delay_minutes=15)
    assert fresh.stale is True
    assert fresh.delay_note == STALE_NOTE


def test_normalize_quotes_batch_items_null_stale_entries() -> None:
    items = normalize_quotes_batch_items(
        [
            {
                "symbol": "AAPL",
                "exchange": "NASDAQ",
                "status": "success",
                "data": {
                    "symbol": "AAPL",
                    "currency": "USD",
                    "price": 1.0,
                    "change": 0,
                    "changePercent": 0,
                },
            },
            {
                "symbol": "VOD.L",
                "exchange": "LSE",
                "status": "success",
                "stale": True,
                "data": {"symbol": "VOD.L", "currency": "GBp", "price": 12345.0},
            },
            {"symbol": "MSFT", "exchange": "NASDAQ", "status": "empty", "reasonCode": "no data"},
        ]
    )
    assert len(items) == 3
    assert items[0].quote is not None
    assert items[1].quote is None and items[1].reason_code == "stale"
    assert items[2].quote is None and items[2].reason_code == "no data"


def test_normalize_holders_filters_owner_type_client_side() -> None:
    payload = {
        "holders": [
            {"ownerType": "institution", "name": "Big Fund", "shares": 10},
            {"ownerType": "insider", "name": "Jane Doe", "shares": 1},
        ]
    }
    assert [h.name for h in normalize_holders(payload, "all")] == ["Big Fund", "Jane Doe"]
    assert [h.name for h in normalize_holders(payload, "institution")] == ["Big Fund"]
    assert normalize_holders(payload, "fund") == []


def test_normalize_analyst_research_limits_actions() -> None:
    payload = {
        "recommendationRating": 2.1,
        "priceTarget": {"average": 250.0, "currency": "USD"},
        "ratings": [
            {"date": "2026-09-01", "firm": "A", "action": "up"},
            {"date": "2026-09-02", "firm": "B", "action": "down"},
        ],
    }
    result = normalize_analyst_research(payload, limit=1)
    assert result.recommendation == pytest.approx(2.1)
    assert result.price_target is not None and result.price_target.average == pytest.approx(250.0)
    assert [action.firm for action in result.actions] == ["A"]


def test_normalize_corporate_actions_flattens_kinds() -> None:
    payload = {
        "dividends": [{"exDate": "2026-08-01", "amount": 0.25}],
        "splits": [{"date": "2026-06-01", "ratio": 4.0, "fromFactor": 1.0, "toFactor": 4.0}],
        "earnings": [{"date": "2026-07-30", "epsEstimate": 1.5, "epsActual": 1.6}],
    }
    actions = normalize_corporate_actions(payload)
    assert [action.kind for action in actions] == ["dividend", "split", "earnings"]
    assert actions[1].ratio == pytest.approx(4.0)
    assert actions[2].eps_actual == pytest.approx(1.6)


def test_normalize_options_chain_normalizes_calls_and_puts() -> None:
    payload = {
        "underlyingSymbol": "AAPL",
        "expirationDates": [1780000000],
        "calls": [{"contractSymbol": "AAPL260101C00100000", "strike": 100.0}],
        "puts": [{"contractSymbol": "AAPL260101P00100000", "strike": 100.0}],
        "dataSource": "delayed",
        "delayMinutes": 15,
    }
    chain = normalize_options_chain(payload)
    assert chain.calls[0].side == "call"
    assert chain.puts[0].side == "put"
    assert chain.delay_minutes == pytest.approx(15)


def test_normalize_news_list_maps_headline_and_story_items() -> None:
    payload = {
        "items": [
            {
                "id": "n1",
                "headline": "Chips rally",
                "summary": "Semis lead",
                "sentiment": "positive",
                "sectors": ["Technology"],
                "primaryUrl": "https://example.test/n1",
                "primarySource": "Reuters",
                "lastPublishedAt": "2026-09-15T10:00:00Z",
                "tickerLinks": [{"symbol": "NVDA", "relationType": "primary"}],
                "items": [{"id": "s1", "title": "Wire", "url": "https://example.test/s1"}],
            }
        ]
    }
    items = normalize_news_list(payload)
    assert items[0].headline == "Chips rally"
    assert items[0].ticker_links[0].symbol == "NVDA"
    assert items[0].items[0].title == "Wire"


def test_normalize_search_results_maps_listings() -> None:
    results = normalize_search_results(
        [
            {
                "providerId": "gloomberb-cloud",
                "symbol": "VOD.L",
                "name": "Vodafone",
                "exchange": "LSE",
                "type": "equity",
                "currency": "GBP",
            }
        ]
    )
    assert results[0].symbol == "VOD.L"
    assert results[0].exchange == "LSE"


def test_normalize_exchange_rate_keeps_asof_and_stale_distinct() -> None:
    payload = {"rate": 1.2, "source": "yahoo", "delayMinutes": 15, "stale": False}
    result = normalize_exchange_rate(payload, response_as_of="2026-09-15T00:00:00Z")
    assert result.rate == pytest.approx(1.2)
    assert result.as_of == "2026-09-15T00:00:00Z"
    assert result.stale is False
    assert result.delay_note == DELAYED_NOTE
    stale = normalize_exchange_rate({"rate": 1.2, "stale": True})
    assert stale.stale is True
    assert stale.delay_note == STALE_NOTE


def test_normalize_sec_filings_and_documents() -> None:
    filings = normalize_sec_filings(
        {
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
        }
    )
    assert filings[0].accession_number == "0001-26-1"
    documents = normalize_sec_documents(
        {
            "documents": [
                {
                    "type": "10-Q",
                    "document": "a.htm",
                    "url": "https://sec.example/a",
                    "isPrimary": True,
                }
            ]
        }
    )
    assert documents[0].is_primary is True


# ── coverage-expansion mappers (#4110 phase 1) ──────────────────────────────


def test_normalize_econ_calendar_accepts_bare_and_wrapped_rows() -> None:
    rows = [
        {
            "id": "e1",
            "date": "2026-09-15",
            "time": "08:30",
            "country": "US",
            "event": "CPI YoY",
            "actual": 3.2,
            "forecast": "3.1",
            "prior": None,
            "impact": "high",
        }
    ]
    bare = normalize_econ_calendar(rows)
    wrapped = normalize_econ_calendar({"events": rows})
    assert bare == wrapped
    assert bare[0].actual == pytest.approx(3.2)
    assert bare[0].forecast == "3.1"
    assert normalize_econ_calendar("not-a-list") == []


def test_normalize_econ_series_maps_fred_missing_values() -> None:
    result = normalize_econ_series(
        {
            "observations": [
                {"date": "2026-07-01", "value": "2.9"},
                {"date": "2026-08-01", "value": "."},
                {"date": "2026-09-01", "value": None},
                {"date": "2026-10-01", "value": math.nan},
            ],
            "info": {"id": "CPIAUCSL", "title": "CPI", "units": "Percent", "frequency": "Monthly"},
        }
    )
    assert [row.value for row in result.observations] == [pytest.approx(2.9), None, None, None]
    assert result.info is not None and result.info.frequency == "Monthly"


def test_normalize_econ_series_without_info_maps_to_none() -> None:
    result = normalize_econ_series({"observations": [{"date": "2026-07-01", "value": 2.9}]})
    assert result.info is None
    assert result.observations[0].value == pytest.approx(2.9)
    assert normalize_econ_series({"observations": [], "info": None}).info is None


def test_normalize_yield_curve_reads_the_yield_alias() -> None:
    points = normalize_yield_curve(
        [{"maturity": "10Y", "maturityYears": 10, "yield": 4.2, "stale": False}]
    )
    assert points[0].yield_ == pytest.approx(4.2)
    assert points[0].maturity_years == pytest.approx(10.0)


def test_normalize_cds_and_research_hits() -> None:
    trades = normalize_cds_trades(
        {
            "trades": [
                {
                    "disseminationId": 1,
                    "issuerName": "Acme",
                    "notionalAmount": 1_000_000,
                    "notionalCapped": True,
                }
            ]
        }
    )
    assert trades[0].dissemination_id == 1
    assert trades[0].notional_capped is True
    hits = normalize_research_hits(
        {"hits": [{"id": "h1", "docType": "filing", "chunkIndex": 3, "ticker": "MSFT"}]}
    )
    assert hits[0].doc_type == "filing"
    assert hits[0].chunk_index == 3


def test_normalize_research_search_maps_the_pagination_block() -> None:
    result = normalize_research_search(
        {
            "hits": [{"id": "h1"}],
            "total": 120,
            "hasMore": True,
            "nextOffset": 10,
            "countCapped": False,
        }
    )
    assert result.hits[0].id == "h1"
    assert result.pagination is not None
    assert result.pagination.total == 120
    assert result.pagination.has_more is True
    assert result.pagination.next_offset == 10
    assert result.pagination.count_capped is False
    assert normalize_research_search({"hits": []}).pagination is None


def test_normalize_congress_trades_and_transcripts_accept_both_shapes() -> None:
    trade_rows = [
        {
            "id": "c1",
            "memberName": "Jane",
            "assetName": "Apple Inc.",
            "sourceUrl": "https://disclosures.test/c1",
            "transactionDate": "2026-08-01",
        }
    ]
    bare_trades = normalize_congress_trades(trade_rows)
    assert bare_trades == normalize_congress_trades({"trades": trade_rows})
    assert bare_trades[0].member_name == "Jane"
    assert bare_trades[0].asset_name == "Apple Inc."
    assert bare_trades[0].source_url == "https://disclosures.test/c1"

    transcript_rows = [
        {
            "id": "t1",
            "ticker": "AAPL",
            "companyName": "Apple Inc.",
            "callAt": "2026-08-01T16:30:00Z",
            "webcastUrl": "https://example.test/call/t1",
        }
    ]
    bare = normalize_transcripts(transcript_rows)
    assert bare == normalize_transcripts({"calls": transcript_rows})
    assert bare == normalize_transcripts({"transcripts": transcript_rows})
    assert bare[0].company_name == "Apple Inc."
    assert bare[0].call_at == "2026-08-01T16:30:00Z"
    assert bare[0].webcast_url == "https://example.test/call/t1"


# ── coverage-expansion mappers (#4110 phase 2) ──────────────────────────────


def test_normalize_statements_maps_annual_and_quarterly_rows() -> None:
    result = normalize_statements(
        {
            "annualStatements": [
                {"date": "2021-09-30", "currency": "USD", "purchaseOfBusiness": -33_000_000}
            ],
            "quarterlyStatements": [
                {"date": "2025-03-31", "currency": "USD", "shortTermDebtPayments": 1}
            ],
        }
    )
    assert result.annual_statements[0].purchase_of_business == pytest.approx(-33_000_000.0)
    assert result.quarterly_statements[0].date == "2025-03-31"
    # The long tail is preserved as extras.
    assert result.quarterly_statements[0].model_extra["shortTermDebtPayments"] == 1


def test_normalize_tweets_slices_and_flags_truncation() -> None:
    result = normalize_tweets(
        {
            "query": "$AAPL -filter:replies",
            "queryType": "Latest",
            "hours": 336,
            "cached": False,
            "asOf": "2026-09-15T17:49:13.531Z",
            "ticker": "AAPL",
            "cashtag": "$AAPL",
            "includeReplies": False,
            "tweets": [
                {
                    "id": str(i),
                    "url": f"https://x.test/{i}",
                    "text": f"t{i}",
                    "author": {"id": "a", "name": "N", "userName": "u"},
                    "metrics": {"likes": i, "views": i * 10},
                }
                for i in range(5)
            ],
        },
        limit=2,
    )
    assert result.query_type == "Latest"
    assert result.hours == 336
    assert result.cached is False
    assert result.include_replies is False
    assert len(result.tweets) == 2
    assert result.total_available == 5
    assert result.truncated is True
    assert result.tweets[0].author is not None and result.tweets[0].author.user_name == "u"
    assert result.tweets[1].metrics is not None and result.tweets[1].metrics.likes == 1


def test_normalize_tweets_without_truncation() -> None:
    result = normalize_tweets({"query": "q", "tweets": [{"id": "1"}]}, limit=50)
    assert result.total_available == 1
    assert result.truncated is False
    assert result.tweets[0].text == ""


def test_normalize_tweets_applies_the_hours_window() -> None:
    result = normalize_tweets(
        {
            "query": "q",
            "tweets": [
                {"id": "recent", "createdAt": "2026-09-15T16:00:00.000Z"},
                {"id": "old", "createdAt": "2026-09-01T00:00:00.000Z"},
                {"id": "unparseable", "createdAt": "not-a-date"},
                {"id": "missing"},
            ],
        },
        limit=50,
        min_created_at=datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc),
    )
    assert [tweet.id for tweet in result.tweets] == ["recent"]
    assert result.total_available == 4
    assert result.truncated is True


def test_normalize_venues_maps_the_list_and_clocks() -> None:
    result = normalize_venues(
        {
            "providerId": "gloomberb-cloud",
            "checkedAt": 1789494522591,
            "refreshAt": 1789494582591,
            "venues": [{"mic": "XADS", "name": "ADX", "timeToOpenSeconds": 43816}],
        }
    )
    assert result.provider_id == "gloomberb-cloud"
    assert result.checked_at == 1789494522591
    assert result.venues[0].name == "ADX"
    assert result.venues[0].time_to_open_seconds == 43816


def test_normalize_screener_accepts_list_and_wrapped_shapes() -> None:
    rows = [{"symbol": "AAPL", "price": 200.0}]
    bare = normalize_screener(rows, "gainers")
    wrapped = normalize_screener({"results": rows}, "gainers")
    assert bare.rows == wrapped.rows
    assert bare.category == "gainers"
    assert bare.rows[0].symbol == "AAPL"
    assert normalize_screener(None, "losers").rows == []


def test_normalize_screener_maps_the_ts_payload_envelope() -> None:
    result = normalize_screener(
        {
            "providerId": "gloomberb-cloud",
            "category": "gainers",
            "asOf": "2026-09-15T00:00:00Z",
            "stale": False,
            "items": [
                {
                    "symbol": "AAPL",
                    "rank": 1,
                    "tradeCount": 1000,
                    "high52w": 260.0,
                    "low52w": 160.0,
                    "dayHigh": 205.0,
                    "dayLow": 199.0,
                    "lastUpdated": 1,
                    "dataSource": "delayed",
                }
            ],
        },
        "gainers",
    )
    assert result.provider_id == "gloomberb-cloud"
    assert result.category == "gainers"
    assert result.as_of == "2026-09-15T00:00:00Z"
    assert result.stale is False
    row = result.rows[0]
    assert row.rank == 1
    assert row.trade_count == 1000
    assert row.high52w == pytest.approx(260.0)
    assert row.low52w == pytest.approx(160.0)
    assert row.day_high == pytest.approx(205.0)
    assert row.day_low == pytest.approx(199.0)
    assert row.data_source == "delayed"


def test_normalize_funds_13f_maps_each_what() -> None:
    funds = normalize_funds_13f([{"name": "BERKSHIRE", "CIK": "0000949012"}], "search")
    assert funds.what == "search"
    assert funds.funds is not None and funds.funds[0].cik == "0000949012"
    top = normalize_funds_13f(
        [{"cik": "0001907544", "name": "Magma", "period_of_report": "2026-06-30", "pnl": 624.41}],
        "top",
    )
    assert top.top_funds is not None and top.top_funds[0].period_of_report == "2026-06-30"
    tickers = normalize_funds_13f(
        [{"cusip": "037833100", "ticker": "AAPL", "company_name": "Apple"}], "tickers"
    )
    assert tickers.tickers is not None and tickers.tickers[0].company_name == "Apple"
    holders = normalize_funds_13f(
        {"cusip": "037833100", "periodOfReport": "2026-06-30", "ciks": ["1"]}, "holders"
    )
    assert holders.holders is not None
    assert holders.holders.period_of_report == "2026-06-30"
    assert holders.holders.ciks == ["1"]


def test_normalize_holdings_13f_maps_filings_and_forms() -> None:
    rows = [{"accession_number": "a1", "cik": "0001022837", "table_value_total": 5}]
    filings = normalize_holdings_13f(rows, "filings", 50)
    assert filings.what == "filings"
    assert filings.filings is not None and filings.filings[0].table_value_total == pytest.approx(
        5.0
    )
    forms = normalize_holdings_13f(rows, "forms", 50)
    assert forms.what == "forms"
    assert forms.forms is not None and forms.forms[0].accession_number == "a1"


def test_normalize_holdings_13f_form_maps_aliases_and_computes_has_more() -> None:
    rows = [
        {
            "accession_number": "a1",
            "name_of_issuer": "ALLY FINL INC",
            "title_of_class": "COM",
            "ssh_prnamt": 12_561_737,
            "ssh_prnamt_type": "SH",
            "voting_authority_sole": 12_561_737,
        }
    ]
    result = normalize_holdings_13f(rows, "form", 1)
    assert result.what == "form"
    assert result.has_more is True
    holding = result.holdings[0]  # type: ignore[index]
    assert holding.issuer == "ALLY FINL INC"
    assert holding.title_of_class == "COM"
    assert holding.shares == pytest.approx(12_561_737.0)
    assert holding.share_type == "SH"
    assert holding.voting_authority_sole == pytest.approx(12_561_737.0)
    assert normalize_holdings_13f(rows, "form", 50).has_more is False


# ── coverage-expansion mappers (#4110 phase 3) ──────────────────────────────


def test_normalize_shiller_keeps_the_most_recent_rows() -> None:
    raw = {
        "observations": [
            {"date": f"1871-{month:02d}-01", "price": float(month), "cape": None}
            for month in range(1, 13)
        ],
        "sourceUrl": "https://example.test/shiller.csv",
        "fetchedAt": "2026-09-15T06:20:06.110Z",
    }
    result = normalize_shiller(raw, limit=3)
    assert [row.date for row in result.observations] == [
        "1871-10-01",
        "1871-11-01",
        "1871-12-01",
    ]
    assert result.total_available == 12
    assert result.truncated is True
    assert result.source_url == "https://example.test/shiller.csv"
    assert result.dataset_fetched_at == "2026-09-15T06:20:06.110Z"
    full = normalize_shiller(raw, limit=50)
    assert len(full.observations) == 12
    assert full.truncated is False


def test_normalize_proxy_statements_list_and_statement() -> None:
    company = {
        "ticker": "AAPL",
        "cik": "0000320193",
        "name": "Apple Inc.",
        "shortName": "Apple",
    }
    listed = normalize_proxy_statements(
        {
            "company": company,
            "proxies": [{"id": "p1", "ticker": "AAPL", "company": company, "proxyYear": 2026}],
        },
        "list",
    )
    assert listed.what == "list"
    assert listed.company is not None and listed.company.short_name == "Apple"
    assert listed.proxies is not None and listed.proxies[0].proxy_year == 2026

    statement = normalize_proxy_statements(
        {
            "id": "p1",
            "ticker": "AAPL",
            "company": company,
            "proxyYear": 2026,
            "namedExecutives": [{"name": "Tim Cook", "total": 74_294_811}],
            "keyFigures": [{"label": "FY2025 Revenue", "value": "$416.2B", "note": "record"}],
            "otherYears": [],
        },
        "statement",
    )
    assert statement.what == "statement"
    assert statement.statement is not None
    assert statement.statement.named_executives[0].total == pytest.approx(74_294_811.0)
    assert statement.statement.key_figures[0].note == "record"


def test_normalize_filing_events_maps_rows() -> None:
    result = normalize_filing_events(
        {
            "ticker": "AAPL",
            "events": [
                {
                    "id": "e1",
                    "ticker": "AAPL",
                    "items": ["2.02"],
                    "material": False,
                    "read": False,
                    "people": [{"name": "Jane", "role": "CFO", "action": "appointed"}],
                }
            ],
        }
    )
    assert result.ticker == "AAPL"
    assert result.events[0].people[0].role == "CFO"


def test_normalize_risk_reports_list_and_report() -> None:
    company = {"ticker": "AAPL", "name": "Apple Inc."}
    listed = normalize_risk_reports(
        {
            "company": company,
            "reports": [
                {
                    "id": "r1",
                    "ticker": "AAPL",
                    "company": company,
                    "reportYear": 2025,
                    "riskCount": 31,
                }
            ],
        },
        "list",
    )
    assert listed.what == "list"
    assert listed.reports is not None and listed.reports[0].risk_count == 31

    report = normalize_risk_reports(
        {
            "id": "r1",
            "ticker": "AAPL",
            "company": company,
            "reportYear": 2025,
            "groups": ["Macro"],
            "risks": [{"heading": "H", "group": "Macro", "excerpt": "E", "words": 3}],
            "diff": {
                "added": [1],
                "removed": [{"heading": "Gone", "excerpt": "x"}],
                "reworded": [
                    {
                        "index": 2,
                        "similarity": 0.9,
                        "headingChanged": True,
                        "priorHeading": "Old",
                    }
                ],
                "matched": 30,
                "priorRiskCount": 34,
            },
            "notes": {
                "added": [{"index": 1, "text": "n"}],
                "removed": [],
                "reworded": [],
                "top": [],
            },
            "otherYears": [],
        },
        "report",
    )
    assert report.what == "report"
    assert report.report is not None
    assert report.report.diff is not None and report.report.diff.prior_risk_count == 34
    assert report.report.notes is not None and report.report.notes.added[0].text == "n"


def test_normalize_short_interest_maps_points() -> None:
    result = normalize_short_interest(
        {
            "symbol": "AAPL",
            "issueName": "Apple Inc.",
            "points": [
                {
                    "settlementDate": "2026-08-31",
                    "sharesShort": 1.5,
                    "previousSharesShort": 1.0,
                    "averageDailyVolume": 2.0,
                    "daysToCover": 0.75,
                    "changePercent": 50.0,
                    "revised": True,
                }
            ],
        }
    )
    assert result.issue_name == "Apple Inc."
    point = result.points[0]
    assert point.settlement_date == "2026-08-31"
    assert point.shares_short == pytest.approx(1.5)
    assert point.days_to_cover == pytest.approx(0.75)
    assert point.revised is True


def test_normalize_equity_diagnostic_pending_and_report() -> None:
    pending = normalize_equity_diagnostic({"status": "generating", "retryAfterMs": 2000})
    assert pending.pending is not None and pending.pending.retry_after_ms == 2000
    assert pending.report is None

    report = normalize_equity_diagnostic(
        {
            "schemaVersion": 1,
            "access": "preview",
            "symbol": "AAPL",
            "status": "partial",
            "verdict": "unclear",
            "findings": [{"id": "F1", "kind": "anomaly", "severity": 1, "evidenceIds": ["E1"]}],
            "coverage": [{"dataset": "statements", "status": "available"}],
            "evidence": [
                {"id": "E1", "dataset": "statements", "label": "10-K", "url": "https://x.test/e1"}
            ],
        }
    )
    assert report.pending is None
    assert report.report is not None
    assert report.report.access == "preview"
    assert report.report.findings[0].evidence_ids == ["E1"]
    assert report.report.evidence[0].url == "https://x.test/e1"

    with pytest.raises(ValueError, match="not an object"):
        normalize_equity_diagnostic("nope")


def test_normalize_proxy_statements_rejects_malformed_payloads() -> None:
    with pytest.raises(ValueError, match="not an object"):
        normalize_proxy_statements("nope", "list")
    with pytest.raises(ValueError, match="no company block"):
        normalize_proxy_statements({"proxies": []}, "list")
    with pytest.raises(ValueError, match="no proxies list"):
        normalize_proxy_statements({"company": {"ticker": "AAPL"}}, "list")
    with pytest.raises(ValueError, match="not an object"):
        normalize_proxy_statements("nope", "statement")
    # A detail payload missing its required company block is malformed too
    # (pydantic ValidationError is a ValueError).
    with pytest.raises(ValueError):
        normalize_proxy_statements({"id": "p1", "ticker": "AAPL"}, "statement")


def test_normalize_risk_reports_rejects_malformed_payloads() -> None:
    with pytest.raises(ValueError, match="not an object"):
        normalize_risk_reports("nope", "list")
    with pytest.raises(ValueError, match="no company block"):
        normalize_risk_reports({"reports": []}, "list")
    with pytest.raises(ValueError, match="no reports list"):
        normalize_risk_reports({"company": {"ticker": "AAPL"}}, "list")
    with pytest.raises(ValueError, match="not an object"):
        normalize_risk_reports(None, "report")
    with pytest.raises(ValueError):
        normalize_risk_reports({"id": "r1", "ticker": "AAPL"}, "report")


def test_normalize_transcript_detail_accepts_wrapped_bare_and_fallback_id() -> None:
    wrapped = {
        "transcript": {"id": "t1", "companyName": "Apple Inc.", "callAt": "2026-08-01T16:30:00Z"}
    }
    row = normalize_transcript_detail(wrapped, "t1")
    assert row.id == "t1"
    assert row.company_name == "Apple Inc."
    assert row.call_at == "2026-08-01T16:30:00Z"

    bare = normalize_transcript_detail({"companyName": "Apple Inc."}, "t9")
    assert bare.id == "t9"

    assert normalize_transcript_detail("not-a-mapping", "t2").id == "t2"

    extra = normalize_transcript_detail({"id": "t3", "segments": [{"speaker": "Tim"}]}, "t3")
    assert extra.model_dump()["segments"] == [{"speaker": "Tim"}]
