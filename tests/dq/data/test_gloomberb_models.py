"""Unit tests for digiquant.data.gloomberb.models (#4069).

Pins the §5.2 resolution x range caps (reject, never clamp), the §5.1 input
bounds, and the shared envelope/error contract.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb.models import (  # noqa: E402
    AnalystResearchInput,
    CdsInput,
    CongressTradesInput,
    DigifetchEnvelope,
    DigifetchError,
    EconCalendarEvent,
    EconCalendarInput,
    EconSeriesInput,
    EquityDiagnosticInput,
    ExchangeRateInput,
    FilingEventsInput,
    HoldersInput,
    NewsInput,
    OptionsChainInput,
    PriceHistoryInput,
    ProxyStatementsInput,
    QuoteEnvelope,
    QuoteInput,
    QuoteResult,
    QuotesBatchInput,
    ResearchSearchInput,
    RiskReportsInput,
    ScreenerInput,
    ScreenerRow,
    SearchInput,
    SecFilingsInput,
    ShillerInput,
    ShortInterestInput,
    StatementsInput,
    ThirteenFFundsInput,
    ThirteenFHoldingsInput,
    TickerTweetsInput,
    TranscriptsInput,
    TweetSearchInput,
    VenuesInput,
    YieldCurveInput,
    envelope_error,
)

VALID_CAP_PAIRS = [
    ("1m", "1W"),
    ("5m", "1W"),
    ("15m", "1M"),
    ("30m", "6M"),
    ("1h", "3M"),
    ("1d", "5Y"),
    ("1wk", "5Y"),
    ("1mo", "5Y"),
    ("1mo", "ALL"),
]

INVALID_CAP_PAIRS = [
    ("1m", "1M"),
    ("5m", "1M"),
    ("5m", "1Y"),
    ("15m", "3M"),
    ("1h", "1Y"),
    ("1d", "ALL"),
    ("1wk", "ALL"),
    ("30m", "1Y"),
]


@pytest.mark.parametrize(("resolution", "range_key"), VALID_CAP_PAIRS)
def test_price_history_caps_accept_contract_combinations(resolution: str, range_key: str) -> None:
    request = PriceHistoryInput(symbol="AAPL", resolution=resolution, range=range_key)
    assert request.range == range_key


@pytest.mark.parametrize(("resolution", "range_key"), INVALID_CAP_PAIRS)
def test_price_history_caps_reject_out_of_contract_requests(
    resolution: str, range_key: str
) -> None:
    with pytest.raises(ValidationError, match="outside the contract"):
        PriceHistoryInput(symbol="AAPL", resolution=resolution, range=range_key)


def test_price_history_range_defaults_to_five_years_for_daily() -> None:
    request = PriceHistoryInput(symbol="AAPL", resolution="1d")
    assert request.range == "5Y"


def test_price_history_requires_explicit_range_for_non_daily() -> None:
    with pytest.raises(ValidationError, match="range is required"):
        PriceHistoryInput(symbol="AAPL", resolution="5m")


def test_price_history_rejects_unknown_resolution() -> None:
    with pytest.raises(ValidationError):
        PriceHistoryInput(symbol="AAPL", resolution="2h", range="1M")  # type: ignore[arg-type]


def test_price_history_date_window_bypasses_the_range_cap() -> None:
    # #4100: an explicit window replaces the range dimension, so the §5.2
    # resolution x range caps do not apply (the client sends rangeKey=ALL).
    request = PriceHistoryInput(
        symbol="AAPL", resolution="1wk", start_date="2015-01-01", end_date="2026-01-01"
    )
    assert request.range is None
    assert request.start_date is not None and request.start_date.isoformat() == "2015-01-01"
    assert request.end_date is not None and request.end_date.isoformat() == "2026-01-01"
    # An open-ended window is legal on either side.
    start_only = PriceHistoryInput(symbol="AAPL", resolution="1wk", start_date="2015-01-01")
    assert start_only.range is None and start_only.end_date is None
    end_only = PriceHistoryInput(symbol="AAPL", resolution="1d", end_date="2020-01-02")
    assert end_only.range is None and end_only.start_date is None
    # The 1d no-range default is untouched when no window is given.
    assert PriceHistoryInput(symbol="AAPL", resolution="1d").range == "5Y"


def test_price_history_date_window_and_range_are_mutually_exclusive() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        PriceHistoryInput(symbol="AAPL", resolution="1wk", range="5Y", start_date="2015-01-01")
    with pytest.raises(ValidationError, match="mutually exclusive"):
        PriceHistoryInput(symbol="AAPL", resolution="1d", range="6M", end_date="2015-01-01")


def test_price_history_date_window_rejects_reversed_and_malformed_dates() -> None:
    with pytest.raises(ValidationError, match="on or before"):
        PriceHistoryInput(
            symbol="AAPL", resolution="1wk", start_date="2026-01-01", end_date="2015-01-01"
        )
    with pytest.raises(ValidationError):
        PriceHistoryInput(symbol="AAPL", resolution="1wk", start_date="2015-1-1")
    with pytest.raises(ValidationError):
        PriceHistoryInput(symbol="AAPL", resolution="1wk", start_date="2015-13-01")


def test_quotes_batch_bounds() -> None:
    assert len(QuotesBatchInput(symbols=["AAPL"]).symbols) == 1
    assert len(QuotesBatchInput(symbols=[f"S{i}" for i in range(20)]).symbols) == 20
    with pytest.raises(ValidationError):
        QuotesBatchInput(symbols=[])
    with pytest.raises(ValidationError):
        QuotesBatchInput(symbols=[f"S{i}" for i in range(21)])


def test_search_limit_accepts_above_cap_for_client_side_clamping() -> None:
    assert SearchInput(query="apple", limit=10).limit == 10
    # Spec §5.1: >10 is accepted, clamped client-side, and flagged.
    assert SearchInput(query="apple", limit=25).limit == 25
    with pytest.raises(ValidationError):
        SearchInput(query="apple", limit=0)


def test_sec_filings_count_is_bounded() -> None:
    assert SecFilingsInput(ticker="MSFT", count=40).count == 40
    with pytest.raises(ValidationError):
        SecFilingsInput(ticker="MSFT", count=41)


def test_analyst_and_news_limits_are_bounded() -> None:
    assert AnalystResearchInput(symbol="AAPL", limit=100).limit == 100
    with pytest.raises(ValidationError):
        AnalystResearchInput(symbol="AAPL", limit=101)
    assert NewsInput(limit=100).limit == 100
    with pytest.raises(ValidationError):
        NewsInput(limit=101)


def test_options_expiration_rejects_milliseconds() -> None:
    assert OptionsChainInput(symbol="AAPL", expiration=1_780_000_000).expiration == 1_780_000_000
    with pytest.raises(ValidationError, match="milliseconds"):
        OptionsChainInput(symbol="AAPL", expiration=1_780_000_000_000)


def test_exchange_rate_uppercases_and_rejects_non_usd_target() -> None:
    request = ExchangeRateInput(from_currency="eur")
    assert request.from_currency == "EUR"
    assert request.to_currency == "USD"
    with pytest.raises(ValidationError, match="USD-based only"):
        ExchangeRateInput(from_currency="EUR", to_currency="GBP")
    with pytest.raises(ValidationError):
        ExchangeRateInput(from_currency="EURO")


def test_sec_filings_documents_require_identity() -> None:
    with pytest.raises(ValidationError, match="requires both cik and accession"):
        SecFilingsInput(ticker="MSFT", what="documents")
    request = SecFilingsInput(ticker="MSFT", what="content", cik="789019", accession="0001-22")
    assert request.what == "content"


def test_inputs_forbid_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        QuoteInput(symbol="AAPL", bogus=True)  # type: ignore[call-arg]


def test_option_expiration_defaults_to_none() -> None:
    assert OptionsChainInput(symbol="AAPL").expiration is None


def test_holders_owner_type_vocabulary() -> None:
    assert HoldersInput(symbol="AAPL", owner_type="fund").owner_type == "fund"
    with pytest.raises(ValidationError):
        HoldersInput(symbol="AAPL", owner_type="pension")  # type: ignore[arg-type]


def test_news_story_id_is_accepted() -> None:
    request = NewsInput(feed="ticker", ticker="AAPL", story_id="n-1", limit=5)
    assert request.story_id == "n-1"


def test_envelope_discriminates_success_from_typed_error() -> None:
    success = QuoteEnvelope(data=QuoteResult(quote=None))
    assert envelope_error(success) is None
    assert success.source == "gloomberb"
    assert success.provider_id == "gloomberb-cloud"
    failure = QuoteEnvelope(data=DigifetchError(code="not_found", message="missing"))
    error = envelope_error(failure)
    assert error is not None and error.code == "not_found" and error.retryable is False


def test_envelope_defaults_are_documented() -> None:
    envelope = QuoteEnvelope(data=QuoteResult(quote=None))
    assert envelope.stale is False
    assert envelope.delay_note is None
    assert envelope.warnings == []
    assert envelope.fetched_at.tzinfo is not None


def test_error_codes_are_closed_vocabulary() -> None:
    with pytest.raises(ValidationError):
        DigifetchError(code="teapot", message="nope")  # type: ignore[arg-type]


def test_generic_envelope_preserves_declared_envelope_alias() -> None:
    envelope: DigifetchEnvelope[QuoteResult] = QuoteEnvelope(
        data=QuoteResult(quote=None), delay_note="Free-tier data delayed up to 15 minutes"
    )
    assert envelope.delay_note == "Free-tier data delayed up to 15 minutes"


# ── coverage-expansion input bounds (#4110 phase 1) ─────────────────────────


def test_cds_days_bounds_are_validated_in_the_input_model() -> None:
    assert CdsInput(days=1).days == 1
    assert CdsInput(days=90).days == 90
    with pytest.raises(ValidationError):
        CdsInput(days=0)
    with pytest.raises(ValidationError):
        CdsInput(days=91)


def test_cds_issuer_is_bounded() -> None:
    assert CdsInput(issuer="  Acme  ").issuer == "Acme"
    with pytest.raises(ValidationError):
        CdsInput(issuer="x" * 201)


def test_new_tool_limits_are_bounded() -> None:
    assert EconSeriesInput(series_id="CPIAUCSL", limit=1000).limit == 1000
    with pytest.raises(ValidationError):
        EconSeriesInput(series_id="CPIAUCSL", limit=1001)
    assert ResearchSearchInput(query="inflation", limit=100).limit == 100
    with pytest.raises(ValidationError):
        ResearchSearchInput(query="inflation", limit=101)
    assert CongressTradesInput(limit=200).limit == 200
    with pytest.raises(ValidationError):
        CongressTradesInput(limit=201)
    assert TranscriptsInput(ticker="aapl", limit=100).limit == 100
    with pytest.raises(ValidationError):
        TranscriptsInput(ticker="aapl", limit=101)


def test_research_search_offset_is_bounded() -> None:
    assert ResearchSearchInput(query="inflation").offset == 0
    assert ResearchSearchInput(query="inflation", offset=10_000).offset == 10_000
    with pytest.raises(ValidationError):
        ResearchSearchInput(query="inflation", offset=-1)
    with pytest.raises(ValidationError):
        ResearchSearchInput(query="inflation", offset=10_001)


def test_econ_series_sort_order_vocabulary() -> None:
    assert EconSeriesInput(series_id="CPIAUCSL", sort_order="asc").sort_order == "asc"
    with pytest.raises(ValidationError):
        EconSeriesInput(series_id="CPIAUCSL", sort_order="sideways")  # type: ignore[arg-type]


def test_parameterless_inputs_forbid_unknown_fields() -> None:
    assert YieldCurveInput().model_dump() == {}
    assert EconCalendarInput().model_dump() == {}
    with pytest.raises(ValidationError):
        YieldCurveInput(maturities="all")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        EconCalendarInput(limit=2)  # type: ignore[call-arg]


def test_econ_calendar_event_keeps_textual_prints() -> None:
    event = EconCalendarEvent(
        id="e1", date="2026-09-15", event="CPI", actual="3.2%", forecast=3.1, prior=None
    )
    assert event.actual == "3.2%"
    assert event.forecast == pytest.approx(3.1)
    assert event.prior is None


# ── coverage-expansion input bounds (#4110 phase 2) ─────────────────────────


def test_statements_and_screener_vocabularies() -> None:
    assert StatementsInput(symbol="AAPL", period="both").period == "both"
    with pytest.raises(ValidationError):
        StatementsInput(symbol="AAPL", period="ttm")  # type: ignore[arg-type]
    assert ScreenerInput(category="most-active", count=50).count == 50
    with pytest.raises(ValidationError):
        ScreenerInput(category="movers")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ScreenerInput(category="gainers", count=51)
    with pytest.raises(ValidationError):
        ScreenerInput(category="gainers", mode="fast")  # type: ignore[arg-type]


def test_tweet_inputs_bound_limits_and_query_type() -> None:
    assert TickerTweetsInput(ticker="AAPL", limit=200, hours=720).limit == 200
    with pytest.raises(ValidationError):
        TickerTweetsInput(ticker="AAPL", limit=201)
    with pytest.raises(ValidationError):
        TickerTweetsInput(ticker="AAPL", hours=0)
    assert TweetSearchInput(query="tariffs", query_type="Top").query_type == "Top"
    with pytest.raises(ValidationError):
        TweetSearchInput(query="tariffs", query_type="LATEST")  # type: ignore[arg-type]


def test_venues_input_takes_no_parameters_and_forbids_unknown_fields() -> None:
    assert VenuesInput().model_dump() == {}
    with pytest.raises(ValidationError):
        VenuesInput(mic="XADS")  # type: ignore[call-arg]


def test_13f_funds_requires_fields_per_what() -> None:
    with pytest.raises(ValidationError, match="requires query"):
        ThirteenFFundsInput(what="search")
    with pytest.raises(ValidationError, match="requires quarter"):
        ThirteenFFundsInput(what="top")
    with pytest.raises(ValidationError, match="requires 1-50 tickers"):
        ThirteenFFundsInput(what="tickers")
    with pytest.raises(ValidationError, match="cusip and period_of_report"):
        ThirteenFFundsInput(what="holders")
    assert ThirteenFFundsInput(what="search", query="berkshire").query == "berkshire"
    assert ThirteenFFundsInput(what="top", quarter="2026Q2").quarter == "2026Q2"
    assert ThirteenFFundsInput(what="tickers", tickers=["AAPL"]).tickers == ["AAPL"]
    assert (
        ThirteenFFundsInput(what="holders", cusip="037833100", period_of_report="2026-06-30").cusip
        == "037833100"
    )


def test_13f_funds_rejects_dashed_quarters_and_oversized_ticker_lists() -> None:
    # The upstream answers 400 for 2026-Q2; the contract rejects it first.
    with pytest.raises(ValidationError):
        ThirteenFFundsInput(what="top", quarter="2026-Q2")
    with pytest.raises(ValidationError):
        ThirteenFFundsInput(what="tickers", tickers=[f"S{i}" for i in range(51)])


def test_13f_holdings_requires_fields_per_what_and_normalizes_cik() -> None:
    with pytest.raises(ValidationError, match="from_date and to_date"):
        ThirteenFHoldingsInput(what="filings")
    with pytest.raises(ValidationError, match="requires cik"):
        ThirteenFHoldingsInput(what="forms")
    with pytest.raises(ValidationError, match="requires accession_number"):
        ThirteenFHoldingsInput(what="form", cik="1067983")
    assert ThirteenFHoldingsInput(what="forms", cik="1067983").cik == "0001067983"
    assert ThirteenFHoldingsInput(what="forms", cik="0001067983").cik == "0001067983"
    with pytest.raises(ValidationError, match="digits only"):
        ThirteenFHoldingsInput(what="forms", cik="abc")
    request = ThirteenFHoldingsInput(
        what="filings", from_date="2026-07-01", to_date="2026-08-31", limit=2
    )
    assert request.from_date == "2026-07-01"


def test_tweet_search_hours_bounds_are_validated() -> None:
    assert TweetSearchInput(query="tariffs", hours=1).hours == 1
    assert TweetSearchInput(query="tariffs", hours=720).hours == 720
    with pytest.raises(ValidationError):
        TweetSearchInput(query="tariffs", hours=0)
    with pytest.raises(ValidationError):
        TweetSearchInput(query="tariffs", hours=721)


def test_13f_holdings_normalizes_accession_and_validates_dates() -> None:
    undashed = ThirteenFHoldingsInput(
        what="form", cik="1067983", accession_number="000119312526352200"
    )
    assert undashed.accession_number == "0001193125-26-352200"
    dashed = ThirteenFHoldingsInput(
        what="form", cik="1067983", accession_number="0001193125-26-352200"
    )
    assert dashed.accession_number == "0001193125-26-352200"
    with pytest.raises(ValidationError, match="18 digits"):
        ThirteenFHoldingsInput(what="form", cik="1067983", accession_number="0001")
    with pytest.raises(ValidationError):
        ThirteenFHoldingsInput(what="filings", from_date="2026-6-1", to_date="2026-08-31")
    with pytest.raises(ValidationError):
        ThirteenFHoldingsInput(what="filings", from_date="2026-07-01", to_date="01/08/2026")


def test_screener_row_follows_the_ts_item_shape() -> None:
    # Shape source: CloudMarketScreenerItem; marketCap is not part of it.
    assert "market_cap" not in ScreenerRow.model_fields
    assert {
        "symbol",
        "rank",
        "currency",
        "trade_count",
        "high52w",
        "low52w",
        "day_high",
        "day_low",
        "last_updated",
        "data_source",
    } <= set(ScreenerRow.model_fields)


# ── coverage-expansion input bounds (#4110 phase 3) ─────────────────────────


def test_shiller_limit_is_bounded() -> None:
    assert ShillerInput().limit == 240
    assert ShillerInput(limit=2000).limit == 2000
    with pytest.raises(ValidationError):
        ShillerInput(limit=0)
    with pytest.raises(ValidationError):
        ShillerInput(limit=2001)


def test_proxy_statements_what_and_year_rules() -> None:
    assert ProxyStatementsInput(ticker="AAPL").what == "list"
    with pytest.raises(ValidationError, match="requires year"):
        ProxyStatementsInput(ticker="AAPL", what="statement")
    statement = ProxyStatementsInput(ticker="AAPL", what="statement", year=2026)
    assert statement.year == 2026
    with pytest.raises(ValidationError):
        ProxyStatementsInput(ticker="AAPL", what="filing")  # type: ignore[arg-type]


def test_filing_events_limit_is_bounded() -> None:
    assert FilingEventsInput(ticker="AAPL", limit=200).limit == 200
    with pytest.raises(ValidationError):
        FilingEventsInput(ticker="AAPL", limit=201)


def test_risk_reports_what_and_year_rules() -> None:
    assert RiskReportsInput(ticker="AAPL").what == "list"
    with pytest.raises(ValidationError, match="requires year"):
        RiskReportsInput(ticker="AAPL", what="report")
    assert RiskReportsInput(ticker="AAPL", what="report", year=2025).year == 2025
    with pytest.raises(ValidationError):
        RiskReportsInput(ticker="AAPL", what="summary")  # type: ignore[arg-type]


def test_short_interest_years_is_bounded() -> None:
    assert ShortInterestInput(symbol="AAPL").years == 3
    assert ShortInterestInput(symbol="AAPL", years=10).years == 10
    with pytest.raises(ValidationError):
        ShortInterestInput(symbol="AAPL", years=0)
    with pytest.raises(ValidationError):
        ShortInterestInput(symbol="AAPL", years=11)


def test_equity_diagnostic_mode_vocabulary() -> None:
    assert EquityDiagnosticInput(symbol="AAPL").mode == "cache-first"
    assert EquityDiagnosticInput(symbol="AAPL", mode="refresh").mode == "refresh"
    with pytest.raises(ValidationError):
        EquityDiagnosticInput(symbol="AAPL", mode="force")  # type: ignore[arg-type]


def test_package_exports_resolve() -> None:
    # Every advertised name must actually exist on the package (a name in
    # __all__ without an import breaks `from digiquant.data.gloomberb import X`).
    import digiquant.data.gloomberb as gloomberb_pkg

    missing = [name for name in gloomberb_pkg.__all__ if not hasattr(gloomberb_pkg, name)]
    assert missing == []


def test_error_code_vocabulary_includes_pro_required() -> None:
    error = DigifetchError(code="pro_required", message="This endpoint requires a Pro plan")
    assert error.code == "pro_required"
    assert error.retryable is False
    with pytest.raises(ValidationError):
        DigifetchError(code="payment_required", message="nope")  # type: ignore[arg-type]


def test_preview_access_warning_marker_is_exported() -> None:
    from digiquant.data.gloomberb import PREVIEW_ACCESS_WARNING

    assert (
        PREVIEW_ACCESS_WARNING == "preview access: report is a free-tier preview (access=preview)"
    )
