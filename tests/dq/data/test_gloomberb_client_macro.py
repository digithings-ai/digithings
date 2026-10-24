"""Unit tests for the digiquant gloomberb macro and risk endpoints.

The economic calendar and series, the yield curve, credit default swaps, the
Shiller tail, short interest, risk reports and the equity diagnostic.
Deterministic and offline: an ``httpx.MockTransport`` drives the real
``digifetch.HttpFetcher``.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    PREVIEW_ACCESS_WARNING,
    RETRYABLE_EXCEPTIONS,
    STALE_NOTE,
)

from digifetch import RetryPolicy  # noqa: E402
from tests.dq.data.gloomberb_client_support import (  # noqa: E402
    clean_env,
    envelope,
    make_client,
)

ECON_CALENDAR_ROWS = [
    {
        "id": "e1",
        "date": "2026-09-15",
        "time": "08:30",
        "country": "US",
        "event": "CPI YoY",
        "actual": 3.2,
        "forecast": 3.1,
        "prior": 3.0,
        "impact": "high",
    }
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    clean_env(monkeypatch)


def test_econ_calendar_maps_rows_without_a_limit_param() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=ECON_CALENDAR_ROWS)

    result = make_client(handler).econ_calendar()
    # The upstream ignores `limit` (fixed-size window), so the client sends none.
    assert "/cloud/econ/calendar" in seen["url"]
    assert "limit" not in seen["url"]
    events = result.data.events  # type: ignore[union-attr]
    assert events[0].event == "CPI YoY"
    assert events[0].actual == pytest.approx(3.2)
    assert events[0].impact == "high"
    assert result.delay_note is None


def test_econ_series_builds_path_and_maps_missing_values() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "observations": [
                    {"date": "2026-07-01", "value": 2.9},
                    {"date": "2026-08-01", "value": "."},
                ],
                "info": {"id": "CPIAUCSL", "title": "CPI", "units": "Percent"},
            },
        )

    result = make_client(handler).econ_series({"series_id": "CPIAUCSL", "limit": 12})
    assert "/cloud/econ/series/CPIAUCSL" in seen["url"]
    assert "limit=12" in seen["url"]
    assert "sortOrder=desc" in seen["url"]
    observations = result.data.observations  # type: ignore[union-attr]
    assert observations[0].value == pytest.approx(2.9)
    assert observations[1].value is None
    assert result.data.info.title == "CPI"


def test_econ_series_without_info_block_maps_to_null_info() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": [{"date": "2026-07-01", "value": 2.9}]})

    result = make_client(handler).econ_series({"series_id": "CPIAUCSL"})
    assert result.data.info is None  # type: ignore[union-attr]
    assert result.data.observations[0].value == pytest.approx(2.9)


def test_yield_curve_maps_the_yield_alias_and_row_staleness() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "maturity": "10Y",
                    "maturityYears": 10,
                    "yield": 4.2,
                    "asOf": "2026-09-15",
                    "fetchedAt": "2026-09-15T00:00:00Z",
                    "stale": True,
                }
            ],
        )

    result = make_client(handler).yield_curve()
    point = result.data.points[0]  # type: ignore[union-attr]
    assert point.maturity_years == pytest.approx(10.0)
    assert point.yield_ == pytest.approx(4.2)
    assert point.as_of == "2026-09-15"
    assert result.stale is True
    assert result.delay_note == STALE_NOTE


def test_cds_maps_the_trade_tape_and_sends_filters() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "source": "DTCC PPD",
                "asOf": "2026-09-15",
                "trades": [
                    {
                        "disseminationId": 1,
                        "actionType": "NEW",
                        "issuerName": "Acme",
                        "notionalAmount": 5_000_000,
                        "notionalCapped": False,
                        "notionalCurrency": "USD",
                        "fixedRate": 1.25,
                        "reportedSpread": 120.0,
                    }
                ],
            },
        )

    result = make_client(handler).cds({"issuer": "Acme", "days": 7, "limit": 20})
    assert "issuer=Acme" in seen["url"]
    assert "days=7" in seen["url"]
    assert "limit=20" in seen["url"]
    data = result.data  # type: ignore[union-attr]
    assert data.source == "DTCC PPD"
    assert data.as_of == "2026-09-15"
    assert data.trades[0].notional_amount == pytest.approx(5_000_000.0)
    assert data.trades[0].notional_capped is False


@pytest.mark.parametrize("days", [0, 91])
def test_cds_days_outside_1_90_is_invalid_input_without_request(days: int) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={})

    result = make_client(handler).cds({"days": days})
    assert result.data.code == "invalid_input"  # type: ignore[union-attr]
    assert "days" in result.data.message  # type: ignore[union-attr]
    assert calls == []


def test_shiller_is_anonymous_and_slices_the_tail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "observations": [
                    {"date": f"1871-{month:02d}-01", "price": float(month), "cape": None}
                    for month in range(1, 5)
                ],
                "sourceUrl": "https://example.test/shiller.csv",
                "fetchedAt": "2026-09-15T06:20:06.110Z",
            },
        )

    result = make_client(handler).shiller({"limit": 2})
    data = result.data  # type: ignore[union-attr]
    assert [row.date for row in data.observations] == ["1871-03-01", "1871-04-01"]
    assert data.total_available == 4
    assert data.truncated is True
    assert data.dataset_fetched_at == "2026-09-15T06:20:06.110Z"


def test_short_interest_is_session_gated_and_sends_years() -> None:
    calls: list[int] = []
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        seen["url"] = str(request.url)
        return envelope(
            {"symbol": "AAPL", "issueName": "Apple Inc.", "points": []},
        )

    denied = make_client(handler).short_interest({"symbol": "AAPL"})
    assert denied.data.code == "auth_required"  # type: ignore[union-attr]
    assert calls == []

    allowed = make_client(handler, session_cookie="token").short_interest(
        {"symbol": "AAPL", "years": 1}
    )
    assert "symbol=AAPL" in seen["url"]
    assert "years=1" in seen["url"]
    assert allowed.data.symbol == "AAPL"


def test_risk_reports_list_and_report_shapes() -> None:
    company = {"ticker": "AAPL", "name": "Apple Inc."}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/2025"):
            return httpx.Response(
                200,
                json={
                    "id": "r1",
                    "ticker": "AAPL",
                    "company": company,
                    "reportYear": 2025,
                    "risks": [{"heading": "H", "excerpt": "E"}],
                    "diff": {"added": [1], "removed": [], "reworded": [], "matched": 30},
                    "notes": {"added": [], "removed": [], "reworded": [], "top": []},
                    "otherYears": [],
                },
            )
        return httpx.Response(
            200,
            json={
                "company": company,
                "reports": [{"id": "r1", "ticker": "AAPL", "company": company, "reportYear": 2025}],
            },
        )

    client = make_client(handler)
    listed = client.risk_reports({"ticker": "AAPL"})
    assert listed.data.reports[0].report_year == 2025  # type: ignore[union-attr]
    report = client.risk_reports({"what": "report", "ticker": "AAPL", "year": 2025})
    assert report.data.report.diff.matched == 30


def test_risk_reports_malformed_payload_is_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"company": {"ticker": "AAPL"}})  # no reports

    result = make_client(handler).risk_reports({"ticker": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "reports list" in result.data.message


def test_equity_diagnostic_is_session_gated_and_caches_reports_not_pending() -> None:
    calls: list[int] = []
    state = {"mode": "pending"}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if state["mode"] == "pending":
            return httpx.Response(202, json={"status": "generating", "retryAfterMs": 2000})
        return httpx.Response(
            200,
            json={
                "schemaVersion": 1,
                "access": "preview",
                "symbol": "AAPL",
                "status": "partial",
                "verdict": "unclear",
                "findings": [],
                "coverage": [],
                "evidence": [],
            },
        )

    denied = make_client(handler).equity_diagnostic({"symbol": "AAPL"})
    assert denied.data.code == "auth_required"  # type: ignore[union-attr]
    assert calls == []

    client = make_client(handler, session_cookie="token")
    first = client.equity_diagnostic({"symbol": "AAPL"})
    # The payload's own `status=generating` must not read as an envelope error.
    assert first.data.pending is not None  # type: ignore[union-attr]
    assert first.data.pending.retry_after_ms == 2000  # type: ignore[union-attr]
    client.equity_diagnostic({"symbol": "AAPL"})
    assert len(calls) == 2  # pending payloads are never client-cached

    state["mode"] = "complete"
    assert client.equity_diagnostic({"symbol": "AAPL"}).data.report is not None  # type: ignore[union-attr]
    client.equity_diagnostic({"symbol": "AAPL"})
    assert len(calls) == 3


def test_equity_diagnostic_does_not_retry_generation_requests() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, json={"message": "unavailable"})

    policy = RetryPolicy(attempts=3, base_delay=0.0, jitter=False, retry_on=RETRYABLE_EXCEPTIONS)
    client = make_client(handler, session_cookie="token", retry_policy=policy)
    result = client.equity_diagnostic({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert result.data.retryable is True  # type: ignore[union-attr]
    # One attempt: the generation POST has no idempotency key and must not be
    # silently re-requested, even though the client's shared policy allows 3.
    assert len(calls) == 1


def test_equity_diagnostic_marks_preview_reports() -> None:
    def preview_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "schemaVersion": 1,
                "access": "preview",
                "symbol": "AAPL",
                "status": "partial",
                "verdict": "unclear",
                "findings": [],
                "coverage": [],
                "evidence": [],
            },
        )

    preview = make_client(preview_handler, session_cookie="token").equity_diagnostic(
        {"symbol": "AAPL"}
    )
    assert preview.data.report.access == "preview"  # type: ignore[union-attr]
    assert preview.warnings == [PREVIEW_ACCESS_WARNING]

    def full_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "schemaVersion": 1,
                "access": "full",
                "symbol": "AAPL",
                "status": "complete",
                "verdict": "balanced",
                "findings": [],
                "coverage": [],
                "evidence": [],
            },
        )

    full = make_client(full_handler, session_cookie="token").equity_diagnostic({"symbol": "AAPL"})
    assert full.data.report.access == "full"  # type: ignore[union-attr]
    assert full.warnings == []


def test_equity_diagnostic_pending_payload_has_no_preview_marker() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"status": "generating", "retryAfterMs": 2000})

    pending = make_client(handler, session_cookie="token").equity_diagnostic({"symbol": "AAPL"})
    assert pending.data.pending is not None  # type: ignore[union-attr]
    assert pending.warnings == []
