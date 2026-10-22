"""Unit tests for the digiquant gloomberb history and filings endpoints.

Price history, SEC filings, congressional trades, company statements, proxy
statements, filing events and the 13F holdings. Deterministic and offline: an
``httpx.MockTransport`` drives the real ``digifetch.HttpFetcher``.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    RETRYABLE_EXCEPTIONS,
    QuoteResult,
)

from digifetch import RetryPolicy  # noqa: E402
from tests.dq.data.gloomberb_client_support import (  # noqa: E402
    AAPL_QUOTE,
    INTRADAY_OUTLIER_POINTS,
    clean_env,
    envelope,
    make_client,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    clean_env(monkeypatch)


def test_price_history_sends_interval_and_range_key() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return envelope([], currency="USD", providerMeta={"provider": "yahoo"})

    make_client(handler).price_history({"symbol": "AAPL", "resolution": "1d", "range": "6M"})
    assert "interval=1day" in seen["url"]
    assert "rangeKey=6M" in seen["url"]


def test_price_history_date_window_sends_range_key_all_and_dates() -> None:
    # #4100: the live probe verified rangeKey=ALL + startDate serves >5Y of
    # weekly bars; a windowed request maps start/end onto those query params.
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return envelope([], currency="USD", providerMeta={"provider": "yahoo"})

    result = make_client(handler).price_history(
        {
            "symbol": "AAPL",
            "resolution": "1wk",
            "start_date": "2015-01-01",
            "end_date": "2026-09-01",
        }
    )
    assert "interval=1week" in seen["url"]
    assert "rangeKey=ALL" in seen["url"]
    assert "startDate=2015-01-01" in seen["url"]
    assert "endDate=2026-09-01" in seen["url"]
    # The windowed call is a normal success envelope (no range in metadata).
    assert result.data.metadata.range == ""


def test_price_history_start_only_window_omits_end_date() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return envelope([], currency="USD", providerMeta={"provider": "yahoo"})

    make_client(handler).price_history(
        {"symbol": "AAPL", "resolution": "1d", "startDate": "2015-01-01"}
    )
    assert "rangeKey=ALL" in seen["url"]
    assert "startDate=2015-01-01" in seen["url"]
    assert "endDate" not in seen["url"]


def test_price_history_end_only_window_omits_start_date() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return envelope([], currency="USD", providerMeta={"provider": "yahoo"})

    make_client(handler).price_history(
        {"symbol": "AAPL", "resolution": "1wk", "end_date": "2020-01-02"}
    )
    assert "rangeKey=ALL" in seen["url"]
    assert "endDate=2020-01-02" in seen["url"]
    assert "startDate" not in seen["url"]


def test_price_history_numeric_timestamp_window_is_invalid_input_without_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a numeric timestamp must not reach the wire")

    result = make_client(handler).price_history(
        {"symbol": "AAPL", "resolution": "1wk", "start_date": 1420070400.0}
    )
    assert result.data.code == "invalid_input"


def test_price_history_window_with_range_is_invalid_input_without_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a window + range request must not reach the wire")

    result = make_client(handler).price_history(
        {"symbol": "AAPL", "resolution": "1wk", "range": "5Y", "start_date": "2015-01-01"}
    )
    assert result.data.code == "invalid_input"


def test_price_history_rejects_malformed_intraday_from_non_yahoo_upstream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope(INTRADAY_OUTLIER_POINTS, providerMeta={"provider": "twelvedata"})

    result = make_client(handler).price_history(
        {"symbol": "AAPL", "resolution": "5m", "range": "1W"}
    )
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "OHLC validation" in result.data.message


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
    assert result.data.documents is None


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
    assert result.data.filings is None


def test_sec_filing_content_returns_the_content_string() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": "<html>10-Q</html>", "form4": None})

    result = make_client(handler).sec_filings(
        {"ticker": "MSFT", "what": "content", "cik": "789019", "accession": "0001-26-1"}
    )
    assert result.data.content == "<html>10-Q</html>"


def test_congress_trades_maps_a_success_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "trades": [
                    {
                        "id": "c1",
                        "memberName": "Jane Doe",
                        "ticker": "AAPL",
                        "transactionDate": "2026-08-01",
                        "transactionType": "buy",
                        "assetName": "Apple Inc.",
                        "sourceUrl": "https://disclosures.test/c1",
                        "filingDate": "2026-08-10",
                        "notificationDate": "2026-08-08",
                    }
                ]
            },
        )

    result = make_client(handler).congress_trades({"year": 2026, "limit": 10})
    trade = result.data.trades[0]  # type: ignore[union-attr]
    assert trade.member_name == "Jane Doe"
    assert trade.asset_name == "Apple Inc."
    assert trade.source_url == "https://disclosures.test/c1"
    assert trade.filing_date == "2026-08-10"
    assert trade.notification_date == "2026-08-08"
    assert trade.transaction_date == "2026-08-01"
    assert trade.transaction_type == "buy"


def test_congress_trades_upstream_500_maps_to_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500, text="Mistral OCR failed: 402 Customer monthly spending limit reached"
        )

    result = make_client(handler).congress_trades()
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert result.data.retryable is True


def test_statements_is_session_gated_and_maps_rows() -> None:
    calls: list[int] = []
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "annualStatements": [
                        {
                            "date": "2021-09-30",
                            "currency": "USD",
                            "dateSource": "provider",
                            "purchaseOfBusiness": -33_000_000,
                        }
                    ],
                    "quarterlyStatements": [],
                },
            },
        )

    denied = make_client(handler).statements({"symbol": "AAPL"})
    assert denied.data.code == "auth_required"  # type: ignore[union-attr]
    assert calls == []

    allowed = make_client(handler, session_cookie="token").statements(
        {"symbol": "AAPL", "period": "annual", "exchange": "NASDAQ"}
    )
    assert "symbol=AAPL" in seen["url"]
    assert "period=annual" in seen["url"]
    assert "exchange=NASDAQ" in seen["url"]
    row = allowed.data.annual_statements[0]  # type: ignore[union-attr]
    assert row.date == "2021-09-30"
    assert row.currency == "USD"
    assert row.date_source == "provider"
    assert row.purchase_of_business == pytest.approx(-33_000_000.0)
    assert allowed.data.quarterly_statements == []


def test_proxy_statements_uppercases_ticker_and_requires_year_for_statement() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
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

    client = make_client(handler)
    listed = client.proxy_statements({"ticker": "aapl"})
    assert "/public/proxies/AAPL" in seen["url"]
    assert listed.data.proxies[0].proxy_year == 2026  # type: ignore[union-attr]

    invalid = client.proxy_statements({"ticker": "AAPL", "what": "statement"})
    assert invalid.data.code == "invalid_input"


def test_proxy_statement_detail_maps_executives_and_unknown_is_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/2026"):
            return httpx.Response(
                200,
                json={
                    "id": "p1",
                    "ticker": "AAPL",
                    "company": {"ticker": "AAPL", "name": "Apple Inc."},
                    "proxyYear": 2026,
                    "ceo": {"name": "Tim Cook", "total": 74_294_811, "priorYearTotal": 74_609_802},
                    "namedExecutives": [{"name": "Tim Cook", "total": 74_294_811}],
                    "keyFigures": [],
                    "otherYears": [],
                },
            )
        return httpx.Response(404, json={"message": "No proxy statements for this ticker"})

    client = make_client(handler)
    statement = client.proxy_statements({"what": "statement", "ticker": "AAPL", "year": 2026})
    assert statement.data.statement.ceo.name == "Tim Cook"  # type: ignore[union-attr]
    missing = client.proxy_statements({"ticker": "ZZZZ"})
    assert missing.data.code == "not_found"


def test_proxy_statements_malformed_payload_is_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})  # no company/proxies block

    result = make_client(handler).proxy_statements({"ticker": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "company block" in result.data.message


def test_filing_events_sends_limit_and_maps_rows() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "ticker": "AAPL",
                "events": [{"id": "e1", "ticker": "AAPL", "items": ["2.02"], "read": False}],
            },
        )

    result = make_client(handler).filing_events({"ticker": "aapl", "limit": 5})
    assert "/public/events/AAPL" in seen["url"]
    assert "limit=5" in seen["url"]
    assert result.data.events[0].items == ["2.02"]


def test_13f_funds_each_what_sends_its_params() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"name": "BERKSHIRE", "CIK": "0000949012"}])

    result = make_client(handler).thirteen_f_funds({"what": "search", "query": "berkshire"})
    assert "/cloud/sec/13f/funds" in seen["url"]
    assert "name=berkshire" in seen["url"]
    assert result.data.funds[0].cik == "0000949012"


def test_13f_funds_top_tickers_and_holders_shapes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
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
        return httpx.Response(
            200,
            json={"cusip": "037833100", "periodOfReport": "2026-06-30", "ciks": ["0001067983"]},
        )

    seen: dict[str, str] = {}

    def recording_handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return handler(request)

    client = make_client(recording_handler)
    top = client.thirteen_f_funds({"what": "top", "quarter": "2026Q2"})
    assert "quarter=2026Q2" in seen["url"]
    assert top.data.top_funds[0].pnl == pytest.approx(624.41)  # type: ignore[union-attr]

    tickers = client.thirteen_f_funds({"what": "tickers", "tickers": ["AAPL", "MSFT"]})
    assert "tickers=AAPL%2CMSFT" in seen["url"] or "tickers=AAPL,MSFT" in seen["url"]
    assert tickers.data.tickers[0].company_name == "Apple"  # type: ignore[union-attr]

    holders = client.thirteen_f_funds(
        {"what": "holders", "cusip": "037833100", "period_of_report": "2026-06-30"}
    )
    assert "cusip=037833100" in seen["url"]
    assert holders.data.holders.period_of_report == "2026-06-30"  # type: ignore[union-attr]
    assert holders.data.holders.ciks == ["0001067983"]


def test_13f_holdings_filings_sends_the_date_range() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json=[
                {
                    "accession_number": "0000950123-25-003235",
                    "cik": "0001022837",
                    "company_name": "SUMITOMO",
                    "period_of_report": "2024-09-30",
                    "table_value_total": 569157836,
                }
            ],
        )

    result = make_client(handler).thirteen_f_holdings(
        {"what": "filings", "from_date": "2025-01-01", "to_date": "2025-03-31", "limit": 2}
    )
    assert "/cloud/sec/13f/filings" in seen["url"]
    assert "from=2025-01-01" in seen["url"]
    assert "to=2025-03-31" in seen["url"]
    filing = result.data.filings[0]  # type: ignore[union-attr]
    assert filing.accession_number == "0000950123-25-003235"
    assert filing.table_value_total == pytest.approx(569157836.0)


def test_13f_holdings_form_maps_holding_aliases_and_has_more() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json=[
                {
                    "accession_number": "0001193125-26-352200",
                    "cik": "0001067983",
                    "name_of_issuer": "ALLY FINL INC",
                    "title_of_class": "COM",
                    "cusip": "02005N100",
                    "ticker": "ALLY",
                    "value": 577211815,
                    "ssh_prnamt": 12561737,
                    "ssh_prnamt_type": "SH",
                    "investment_discretion": "DFND",
                    "voting_authority_sole": 12561737,
                    "voting_authority_shared": 0,
                    "voting_authority_none": 0,
                    "put_call": "",
                    "pnl": -6.84,
                }
            ],
        )

    result = make_client(handler).thirteen_f_holdings(
        {"what": "form", "cik": "1067983", "accession_number": "0001193125-26-352200", "limit": 1}
    )
    assert "cik=0001067983" in seen["url"]
    assert "accession_number=0001193125-26-352200" in seen["url"]
    holding = result.data.holdings[0]  # type: ignore[union-attr]
    assert holding.issuer == "ALLY FINL INC"
    assert holding.shares == pytest.approx(12561737.0)
    assert holding.share_type == "SH"
    assert holding.voting_authority_sole == pytest.approx(12561737.0)
    assert result.data.has_more is True


def test_13f_holdings_missing_required_params_is_invalid_input_without_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=[])

    for request in (
        {"what": "filings"},
        {"what": "forms"},
        {"what": "form", "cik": "1067983"},
    ):
        result = make_client(handler).thirteen_f_holdings(request)
        assert result.data.code == "invalid_input"  # type: ignore[union-attr]
    assert calls == []


def test_13f_holders_proxied_4xx_is_invalid_input_without_retry_or_breaker() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/cloud/sec/13f/holders":
            return httpx.Response(500, text="Forms13F 400 for /holders")
        return envelope(AAPL_QUOTE)

    policy = RetryPolicy(attempts=3, base_delay=0.0, jitter=False, retry_on=RETRYABLE_EXCEPTIONS)
    client = make_client(handler, retry_policy=policy, circuit_failure_threshold=2)
    for _ in range(3):
        result = client.thirteen_f_funds(
            {"what": "holders", "cusip": "037833100", "period_of_report": "2026-06-30"}
        )
        assert result.data.code == "invalid_input"  # type: ignore[union-attr]
        assert result.data.retryable is False  # type: ignore[union-attr]
    # One wire call per request (no retries), and the shared breaker stays closed.
    assert calls == ["/cloud/sec/13f/holders"] * 3
    assert isinstance(client.quote({"symbol": "AAPL"}).data, QuoteResult)


def test_forms13f_5xx_body_is_still_a_retryable_upstream_error() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500, text="Forms13F 500 for /form")

    policy = RetryPolicy(attempts=2, base_delay=0.0, jitter=False, retry_on=RETRYABLE_EXCEPTIONS)
    client = make_client(handler, retry_policy=policy)
    result = client.thirteen_f_holdings(
        {"what": "form", "cik": "1067983", "accession_number": "0001193125-26-352200"}
    )
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert result.data.retryable is True  # type: ignore[union-attr]
    assert len(calls) == 2


def test_13f_holdings_malformed_dates_are_invalid_input_without_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=[])

    result = make_client(handler).thirteen_f_holdings(
        {"what": "filings", "from_date": "2026-6-1", "to_date": "2026-08-31"}
    )
    assert result.data.code == "invalid_input"  # type: ignore[union-attr]
    assert calls == []


def test_13f_holdings_undashed_accession_is_normalized() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200, json=[{"accession_number": "0001193125-26-352200", "name_of_issuer": "ALLY"}]
        )

    result = make_client(handler).thirteen_f_holdings(
        {
            "what": "form",
            "cik": "1067983",
            "accession_number": "000119312526352200",
            "limit": 1,
        }
    )
    assert "accession_number=0001193125-26-352200" in seen["url"]
    assert result.data.holdings[0].issuer == "ALLY"


def test_13f_holdings_bad_accession_is_invalid_input_without_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=[])

    result = make_client(handler).thirteen_f_holdings(
        {"what": "form", "cik": "1067983", "accession_number": "0001"}
    )
    assert result.data.code == "invalid_input"  # type: ignore[union-attr]
    assert calls == []
