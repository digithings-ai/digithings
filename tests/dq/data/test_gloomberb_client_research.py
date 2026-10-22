"""Unit tests for the digiquant gloomberb research endpoints.

Analyst research, transcripts, the tweet feeds, the screener and the saved
searches. Deterministic and offline: an ``httpx.MockTransport`` drives the
real ``digifetch.HttpFetcher``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import QuoteResult  # noqa: E402

from tests.dq.data.gloomberb_client_support import (  # noqa: E402
    AAPL_QUOTE,
    clean_env,
    envelope,
    make_client,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    clean_env(monkeypatch)


def test_research_search_is_session_gated_and_maps_hits_and_pagination() -> None:
    calls: list[int] = []
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "id": "h1",
                        "docType": "transcript",
                        "chunkIndex": 2,
                        "ticker": "AAPL",
                        "title": "Q3 call",
                        "url": "https://example.test/h1",
                        "snippet": "...",
                    }
                ],
                "total": 120,
                "hasMore": True,
                "nextOffset": 10,
                "countCapped": False,
            },
        )

    denied = make_client(handler).research_search({"query": "inflation"})
    assert denied.data.code == "auth_required"  # type: ignore[union-attr]
    assert calls == []

    allowed = make_client(handler, session_cookie="token").research_search(
        {"query": "inflation", "offset": 5}
    )
    assert "offset=5" in seen["url"]
    hit = allowed.data.hits[0]  # type: ignore[union-attr]
    assert hit.id == "h1"
    assert hit.doc_type == "transcript"
    assert hit.chunk_index == 2
    pagination = allowed.data.pagination  # type: ignore[union-attr]
    assert pagination is not None
    assert pagination.total == 120
    assert pagination.has_more is True
    assert pagination.next_offset == 10
    assert pagination.count_capped is False
    assert calls == [1]


def test_research_search_without_pagination_metadata_has_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hits": [{"id": "h1"}]})

    result = make_client(handler, session_cookie="token").research_search({"query": "x"})
    assert result.data.pagination is None


@pytest.mark.parametrize("status", [401, 402])
def test_research_search_auth_codes_map_to_auth_required(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "Unauthorized"})

    result = make_client(handler, session_cookie="token").research_search({"query": "x"})
    assert result.data.code == "auth_required"  # type: ignore[union-attr]
    assert result.data.retryable is False


def test_transcripts_map_upstream_calls_rows_and_require_a_session_cookie() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            200,
            json={
                "calls": [
                    {
                        "id": "t1",
                        "ticker": "AAPL",
                        "companyName": "Apple Inc.",
                        "callAt": "2026-08-01T16:30:00Z",
                        "webcastUrl": "https://example.test/call/t1",
                    }
                ]
            },
        )

    denied = make_client(handler).transcripts({"ticker": "AAPL"})
    assert denied.data.code == "auth_required"  # type: ignore[union-attr]
    assert calls == []

    allowed = make_client(handler, session_cookie="token").transcripts({"ticker": "AAPL"})
    row = allowed.data.transcripts[0]  # type: ignore[union-attr]
    assert row.company_name == "Apple Inc."
    assert row.call_at == "2026-08-01T16:30:00Z"
    assert row.webcast_url == "https://example.test/call/t1"


@pytest.mark.parametrize("status", [200, 402, 403])
def test_transcripts_plan_required_body_maps_to_pro_required(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="Pro plan required")

    result = make_client(handler, session_cookie="token").transcripts({"ticker": "AAPL"})
    assert result.data.code == "pro_required"  # type: ignore[union-attr]
    assert "Pro plan" in result.data.message  # type: ignore[union-attr]
    assert result.data.retryable is False


@pytest.mark.parametrize("status", [200, 402])
def test_transcripts_json_plan_error_does_not_read_as_an_empty_success(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "Pro plan required"})

    result = make_client(handler, session_cookie="token").transcripts({"ticker": "AAPL"})
    assert result.data.code == "pro_required"


def test_transcripts_plan_required_does_not_open_the_breaker() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/cloud/transcripts":
            return httpx.Response(200, text="Pro plan required")
        return envelope(AAPL_QUOTE)

    client = make_client(handler, session_cookie="token", circuit_failure_threshold=2)
    for _ in range(3):
        assert client.transcripts({"ticker": "AAPL"}).data.code == "pro_required"  # type: ignore[union-attr]
    # A plan gate is deterministic, not upstream degradation: the breaker stays closed.
    assert isinstance(client.quote({"symbol": "AAPL"}).data, QuoteResult)
    assert calls == ["/cloud/transcripts"] * 3 + ["/market/quote"]


def test_transcripts_detail_mode_fetches_by_id_and_requires_pro() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "transcript": {
                    "companyName": "Apple Inc.",
                    "callAt": "2026-08-01T16:30:00Z",
                }
            },
        )

    denied = make_client(handler).transcripts({"transcript_id": "t1"})
    assert denied.data.code == "auth_required"  # type: ignore[union-attr]
    assert seen == {}

    allowed = make_client(handler, session_cookie="token").transcripts({"transcript_id": "t1"})
    assert seen["path"] == "/cloud/transcripts/t1"
    row = allowed.data.transcripts[0]  # type: ignore[union-attr]
    assert row.id == "t1"
    assert row.company_name == "Apple Inc."


def test_transcripts_rejects_two_targets_before_any_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"calls": []})

    result = make_client(handler, session_cookie="token").transcripts(
        {"ticker": "AAPL", "transcript_id": "t1"}
    )
    assert result.data.code == "invalid_input"  # type: ignore[union-attr]
    assert calls == []


def test_ticker_tweets_maps_metadata_and_slices_to_limit() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            200,
            json={
                "query": "$AAPL -filter:replies",
                "queryType": "Latest",
                "limit": 1,
                "hours": 336,
                "cached": False,
                "asOf": "2026-09-15T17:49:13.531Z",
                "tweets": [{"id": str(i), "text": f"t{i}"} for i in range(5)],
                "ticker": "AAPL",
                "cashtag": "$AAPL",
                "includeReplies": False,
            },
        )

    denied = make_client(handler).ticker_tweets({"ticker": "AAPL"})
    assert denied.data.code == "auth_required"  # type: ignore[union-attr]
    assert calls == []

    allowed = make_client(handler, session_cookie="token").ticker_tweets(
        {"ticker": "AAPL", "limit": 2}
    )
    data = allowed.data  # type: ignore[union-attr]
    assert data.query == "$AAPL -filter:replies"
    assert data.hours == 336
    assert data.ticker == "AAPL"
    assert len(data.tweets) == 2
    assert data.total_available == 5
    assert data.truncated is True


def test_tweet_search_sends_query_type_and_slices() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"query": "tariffs", "tweets": [{"id": "1", "text": "t"}]},
        )

    result = make_client(handler, session_cookie="token").tweet_search(
        {"query": "tariffs", "query_type": "Top", "limit": 5}
    )
    assert "query=tariffs" in seen["url"]
    assert "queryType=Top" in seen["url"]
    assert result.data.tweets[0].id == "1"  # type: ignore[union-attr]
    assert result.data.truncated is False


def test_ticker_tweets_hours_window_drops_old_and_unparseable_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "query": "$AAPL",
                "tweets": [
                    {"id": "recent", "text": "r", "createdAt": "2026-09-15T16:00:00.000Z"},
                    {"id": "old", "text": "o", "createdAt": "2026-09-01T00:00:00.000Z"},
                    {"id": "unparseable", "text": "u", "createdAt": "not-a-date"},
                    {"id": "missing"},
                ],
            },
        )

    client = make_client(
        handler,
        session_cookie="token",
        now=lambda: datetime(2026, 9, 15, 17, 0, tzinfo=timezone.utc),
    )
    result = client.ticker_tweets({"ticker": "AAPL", "hours": 24, "limit": 50})
    data = result.data  # type: ignore[union-attr]
    assert [tweet.id for tweet in data.tweets] == ["recent"]
    assert data.total_available == 4
    assert data.truncated is True


def test_tweet_search_hours_window_is_applied() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "query": "tariffs",
                "tweets": [
                    {"id": "recent", "createdAt": "2026-09-15T16:00:00Z"},
                    {"id": "old", "createdAt": "2026-09-14T00:00:00Z"},
                ],
            },
        )

    client = make_client(
        handler,
        session_cookie="token",
        now=lambda: datetime(2026, 9, 15, 17, 0, tzinfo=timezone.utc),
    )
    result = client.tweet_search({"query": "tariffs", "hours": 6, "limit": 50})
    data = result.data  # type: ignore[union-attr]
    assert [tweet.id for tweet in data.tweets] == ["recent"]
    assert data.total_available == 2
    assert data.truncated is True


def test_screener_maps_both_pro_gate_shapes_without_a_request_when_cookieless() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            200,
            json={"status": "unsupported", "data": None, "reasonCode": "PRO_REQUIRED"},
        )

    denied = make_client(handler).screener({"category": "gainers"})
    assert denied.data.code == "auth_required"  # type: ignore[union-attr]
    assert calls == []

    by_reason = make_client(handler, session_cookie="token").screener({"category": "gainers"})
    assert by_reason.data.code == "pro_required"  # type: ignore[union-attr]
    assert "Pro plan" in by_reason.data.message  # type: ignore[union-attr]
    assert "PRO_REQUIRED" in by_reason.data.message


def test_screener_402_text_body_maps_to_pro_required() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, text="Pro plan required")

    result = make_client(handler, session_cookie="token").screener({"category": "gainers"})
    assert result.data.code == "pro_required"  # type: ignore[union-attr]
    assert result.data.retryable is False


def test_screener_pro_gate_does_not_open_the_breaker() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/market/screener":
            return httpx.Response(
                200,
                json={"status": "unsupported", "data": None, "reasonCode": "PRO_REQUIRED"},
            )
        return envelope(AAPL_QUOTE)

    client = make_client(handler, session_cookie="token", circuit_failure_threshold=2)
    for _ in range(3):
        assert client.screener({"category": "gainers"}).data.code == "pro_required"  # type: ignore[union-attr]
    assert isinstance(client.quote({"symbol": "AAPL"}).data, QuoteResult)
    assert calls == ["/market/screener"] * 3 + ["/market/quote"]


def test_screener_success_payload_maps_rows_when_pro() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"status": "success", "data": [{"symbol": "AAPL", "price": 200.0}]},
        )

    result = make_client(handler, session_cookie="token").screener(
        {"category": "gainers", "count": 5, "mode": "cache-first"}
    )
    assert "category=gainers" in seen["url"]
    assert "count=5" in seen["url"]
    assert "mode=cache-first" in seen["url"]
    assert result.data.category == "gainers"  # type: ignore[union-attr]
    assert result.data.rows[0].symbol == "AAPL"


def test_saved_searches_is_session_gated_and_maps_rows() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        assert request.url.path == "/cloud/search/saved"
        return httpx.Response(200, json={"searches": [{"id": "s1", "name": "AI capex"}]})

    denied = make_client(handler).saved_searches()
    assert denied.data.code == "auth_required"  # type: ignore[union-attr]
    assert calls == []

    allowed = make_client(handler, session_cookie="token").saved_searches()
    assert allowed.data.searches[0].name == "AI capex"  # type: ignore[union-attr]
    assert calls == [1]


def test_saved_searches_401_maps_to_auth_required() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})

    result = make_client(handler, session_cookie="token").saved_searches()
    assert result.data.code == "auth_required"  # type: ignore[union-attr]
    assert result.data.retryable is False
