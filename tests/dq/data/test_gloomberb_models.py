"""Unit tests for digiquant.data.gloomberb.models (#4069).

Pins the §5.2 resolution x range caps (reject, never clamp), the §5.1 input
bounds, and the shared envelope/error contract.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb.models import (  # noqa: E402
    DigifetchEnvelope,
    DigifetchError,
    ExchangeRateInput,
    HoldersInput,
    NewsInput,
    OptionsChainInput,
    PriceHistoryInput,
    QuoteEnvelope,
    QuoteInput,
    QuoteResult,
    QuotesBatchInput,
    SearchInput,
    SecFilingsInput,
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


def test_quotes_batch_bounds() -> None:
    assert len(QuotesBatchInput(symbols=["AAPL"]).symbols) == 1
    assert len(QuotesBatchInput(symbols=[f"S{i}" for i in range(20)]).symbols) == 20
    with pytest.raises(ValidationError):
        QuotesBatchInput(symbols=[])
    with pytest.raises(ValidationError):
        QuotesBatchInput(symbols=[f"S{i}" for i in range(21)])


def test_search_limit_is_bounded_by_the_wrapper_cap() -> None:
    assert SearchInput(query="apple", limit=10).limit == 10
    with pytest.raises(ValidationError):
        SearchInput(query="apple", limit=11)
    with pytest.raises(ValidationError):
        SearchInput(query="apple", limit=0)


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
