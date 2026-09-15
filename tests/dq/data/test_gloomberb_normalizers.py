"""Unit tests for digiquant.data.gloomberb.normalizers (#4069).

Golden fixtures: a GBp (LSE) listing and an intraday series, plus the §5.4
unit/interval/date/malformed-intraday/day-range rules and the §5.3 freshness
union. No network.
"""

from __future__ import annotations

import math

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
    normalize_exchange_rate,
    normalize_holders,
    normalize_news_list,
    normalize_options_chain,
    normalize_price_value_by_divisor,
    normalize_quote,
    normalize_quotes_batch_items,
    normalize_research_hits,
    normalize_research_search,
    normalize_search_results,
    normalize_sec_documents,
    normalize_sec_filings,
    normalize_transcripts,
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
