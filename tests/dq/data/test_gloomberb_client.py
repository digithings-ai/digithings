"""Unit tests for the digiquant gloomberb client transport contract.

The cross-cutting half of the client: the error mapping, the cache, the
circuit breaker, the kill switch and the session cookie that gates the pro
endpoints. Deterministic and offline: an ``httpx.MockTransport`` drives the
real ``digifetch.HttpFetcher`` (with ``allowed_hosts`` skipping DNS so the
SSRF guard is exercised without a socket).
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    RETRYABLE_EXCEPTIONS,
    QuoteResult,
    session_cache_fingerprint,
)

from digifetch import RetryPolicy, SsrfBlockedError  # noqa: E402
from tests.dq.data.gloomberb_client_support import (  # noqa: E402
    AAPL_QUOTE,
    clean_env,
    envelope,
    make_client,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    clean_env(monkeypatch)


def test_gated_endpoint_401_maps_to_auth_required() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})

    client = make_client(handler, session_cookie="token-value")
    result = client.holders({"symbol": "AAPL"})
    assert result.data.code == "auth_required"  # type: ignore[union-attr]
    assert GLOOMBERB_SESSION_COOKIE_ENV in result.data.message


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
    assert result.data.retryable is True


@pytest.mark.parametrize("status", ["empty", "unsupported"])
def test_empty_and_unsupported_statuses_map_to_not_found(status: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": status, "data": None, "reasonCode": "no data"})

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "not_found"  # type: ignore[union-attr]
    assert "no data" in result.data.message


def test_retryable_error_status_maps_to_retryable_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "retryable_error", "data": None})

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert result.data.retryable is True


def test_fatal_error_status_maps_to_non_retryable_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "fatal_error", "data": None})

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert result.data.retryable is False


def test_non_json_body_maps_to_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "non-JSON" in result.data.message


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
    disabled = make_client(handler, enabled=None)
    assert disabled.enabled is False
    assert disabled.quote({"symbol": "AAPL"}).data.code == "upstream_error"  # type: ignore[union-attr]

    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    enabled = make_client(handler, enabled=None)
    assert enabled.enabled is True
    assert isinstance(enabled.quote({"symbol": "AAPL"}).data, QuoteResult)
    assert len(calls) == 1


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
    client = make_client(handler, enabled=None)
    assert client.enabled is expected
    if not expected:
        result = client.quote({"symbol": "AAPL"})
        assert result.data.code == "upstream_error"  # type: ignore[union-attr]
        assert calls == []


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


def test_429_retry_after_within_bound_is_slept() -> None:
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "2"}, json={"message": "slow down"})

    result = make_client(handler, sleep=slept.append).quote({"symbol": "AAPL"})
    assert result.data.code == "rate_limited"  # type: ignore[union-attr]
    assert slept == [2.0]
    assert "waited 2s" in result.data.message


def test_429_retry_after_above_bound_is_not_slept() -> None:
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "999"}, json={"message": "slow down"})

    result = make_client(handler, sleep=slept.append).quote({"symbol": "AAPL"})
    assert result.data.code == "rate_limited"  # type: ignore[union-attr]
    assert slept == []
    assert "999" in result.data.message  # type: ignore[union-attr]
    assert "not slept" in result.data.message


def test_too_many_redirects_maps_to_typed_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TooManyRedirects("exceeded redirects")

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "exceeded redirects" in result.data.message


def test_ssrf_blocked_maps_to_typed_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise SsrfBlockedError("host is blocked")

    result = make_client(handler).quote({"symbol": "AAPL"})
    assert result.data.code == "upstream_error"  # type: ignore[union-attr]
    assert "SSRF" in result.data.message


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


def test_session_cache_fingerprint_separates_sessions_without_storing_the_cookie() -> None:
    assert session_cache_fingerprint(None) == "anon"
    assert session_cache_fingerprint("") == "anon"
    first = session_cache_fingerprint("gloomberb.session_token=aaa")
    assert first == session_cache_fingerprint("gloomberb.session_token=aaa")
    assert first != session_cache_fingerprint("gloomberb.session_token=bbb")
    assert len(first) == 16
    assert "aaa" not in first


def test_cache_key_follows_the_session_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cached entitlement-sensitive response never crosses sessions."""

    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return envelope({"symbol": "AAPL", "issueName": "Apple Inc.", "points": []})

    client = make_client(handler, session_cookie="session-a")
    client.short_interest({"symbol": "AAPL"})
    client.short_interest({"symbol": "AAPL"})
    assert len(calls) == 1  # same session: cache hit

    monkeypatch.setattr(client, "_session_cookie", "session-b")
    client.short_interest({"symbol": "AAPL"})
    assert len(calls) == 2  # a session switch never serves the other entry

    monkeypatch.setattr(client, "_session_cookie", "session-a")
    client.short_interest({"symbol": "AAPL"})
    assert len(calls) == 2


def test_cache_bounds_and_eviction_still_hold_with_the_session_key() -> None:
    now = {"t": 0.0}
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"status": "success", "data": AAPL_QUOTE})

    client = make_client(
        handler,
        session_cookie="session-a",
        monotonic=lambda: now["t"],
        cache_ttl=900.0,
        cache_max_entries=2,
    )
    for symbol in ("AAPL", "MSFT", "NVDA"):
        client.quote({"symbol": symbol})
    assert client.cache_size == 2  # size bound intact
    assert len(calls) == 3

    now["t"] += 901.0
    client.quote({"symbol": "AAPL"})
    assert len(calls) == 4  # the expired entry did not serve
    assert client.cache_size == 1


def test_pro_gate_shapes_are_pro_required_not_auth_required() -> None:
    """A valid free session is entitled-gated (pro_required), not session-gated."""

    def transcripts_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Pro plan required")

    transcripts = make_client(transcripts_handler, session_cookie="token").transcripts(
        {"ticker": "AAPL"}
    )
    assert transcripts.data.code == "pro_required"  # type: ignore[union-attr]
    assert transcripts.data.code != "auth_required"  # type: ignore[union-attr]

    def screener_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "unsupported", "data": None, "reasonCode": "PRO_REQUIRED"},
        )

    screener = make_client(screener_handler, session_cookie="token").screener(
        {"category": "gainers"}
    )
    assert screener.data.code == "pro_required"  # type: ignore[union-attr]
    assert screener.data.code != "auth_required"


def test_pro_required_is_non_retryable_and_breaker_safe_for_both_shapes() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/cloud/transcripts":
            return httpx.Response(200, text="Pro plan required")
        if request.url.path == "/market/screener":
            return httpx.Response(
                200,
                json={"status": "unsupported", "data": None, "reasonCode": "PRO_REQUIRED"},
            )
        return envelope(AAPL_QUOTE)

    policy = RetryPolicy(attempts=3, base_delay=0.0, jitter=False, retry_on=RETRYABLE_EXCEPTIONS)
    client = make_client(
        handler,
        session_cookie="token",
        retry_policy=policy,
        circuit_failure_threshold=2,
    )
    for _ in range(3):
        transcripts = client.transcripts({"ticker": "AAPL"})
        assert transcripts.data.code == "pro_required"  # type: ignore[union-attr]
        assert transcripts.data.retryable is False  # type: ignore[union-attr]
        screener = client.screener({"category": "gainers"})
        assert screener.data.code == "pro_required"  # type: ignore[union-attr]
        assert screener.data.retryable is False  # type: ignore[union-attr]
    # Six deterministic plan gates: no retries (one call each) and the shared
    # breaker stays closed for unrelated tools.
    assert calls.count("/cloud/transcripts") == 3
    assert calls.count("/market/screener") == 3
    assert isinstance(client.quote({"symbol": "AAPL"}).data, QuoteResult)
