"""Unit tests for digibase service-to-service digikey auth."""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx
import pytest
from digibase.service_auth import ServiceAuthError, clear_service_jwt_cache, get_service_jwt

pytestmark = pytest.mark.unit


def test_exchange_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        assert request.url.path == "/v1/oauth/token"
        return httpx.Response(
            200, json={"access_token": "jwt-1", "token_type": "Bearer", "expires_in": 900}
        )

    def _fake_post(url: str, payload: dict) -> dict:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return client.post(url, json=payload).json()

    monkeypatch.setattr("digibase.service_auth._http_post", _fake_post)
    clear_service_jwt_cache()
    assert get_service_jwt() == "jwt-1"
    assert get_service_jwt() == "jwt-1"
    assert len(calls) == 1


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIQUANT_DIGIKEY_API_KEY", raising=False)
    clear_service_jwt_cache()
    try:
        get_service_jwt()
    except ServiceAuthError:
        return
    raise AssertionError("expected ServiceAuthError")


def test_distinct_keys_sharing_prefix_get_distinct_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_a = "dgk_live_abc1234_suffix_A_0001"
    key_b = "dgk_live_abc1234_suffix_B_0002"
    assert key_a[:16] == key_b[:16]
    assert key_a != key_b
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")
    calls = []
    tokens = ["jwt-a", "jwt-b"]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        assert request.url.path == "/v1/oauth/token"
        return httpx.Response(
            200,
            json={
                "access_token": tokens[len(calls) - 1],
                "token_type": "Bearer",
                "expires_in": 900,
            },
        )

    def _fake_post(url: str, payload: dict) -> dict:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return client.post(url, json=payload).json()

    monkeypatch.setattr("digibase.service_auth._http_post", _fake_post)
    clear_service_jwt_cache()
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", key_a)
    assert get_service_jwt() == "jwt-a"
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", key_b)
    assert get_service_jwt() == "jwt-b"
    assert len(calls) == 2


def test_missing_digikey_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.delenv("DIGIKEY_URL", raising=False)
    clear_service_jwt_cache()
    with pytest.raises(ServiceAuthError):
        get_service_jwt()


def test_empty_access_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/oauth/token"
        return httpx.Response(
            200, json={"access_token": "", "token_type": "Bearer", "expires_in": 900}
        )

    def _fake_post(url: str, payload: dict) -> dict:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return client.post(url, json=payload).json()

    monkeypatch.setattr("digibase.service_auth._http_post", _fake_post)
    clear_service_jwt_cache()
    with pytest.raises(ServiceAuthError, match="empty token"):
        get_service_jwt()


def test_exchange_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")

    def _fake_post(url: str, payload: dict) -> dict:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("digibase.service_auth._http_post", _fake_post)
    clear_service_jwt_cache()
    with pytest.raises(ServiceAuthError, match="exchange failed"):
        get_service_jwt()


def test_expired_entry_reexchanges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        assert request.url.path == "/v1/oauth/token"
        return httpx.Response(
            200,
            json={
                "access_token": f"jwt-{len(calls)}",
                "token_type": "Bearer",
                "expires_in": 900,
            },
        )

    def _fake_post(url: str, payload: dict) -> dict:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return client.post(url, json=payload).json()

    monkeypatch.setattr("digibase.service_auth._http_post", _fake_post)
    clear_service_jwt_cache()
    t0 = time.monotonic()
    assert get_service_jwt() == "jwt-1"
    assert len(calls) == 1

    def _later() -> float:
        return t0 + 1000.0

    monkeypatch.setattr(time, "monotonic", _later)
    assert get_service_jwt() == "jwt-2"
    assert len(calls) == 2


def test_null_access_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/oauth/token"
        return httpx.Response(
            200, json={"access_token": None, "token_type": "Bearer", "expires_in": 900}
        )

    def _fake_post(url: str, payload: dict) -> dict:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return client.post(url, json=payload).json()

    monkeypatch.setattr("digibase.service_auth._http_post", _fake_post)
    clear_service_jwt_cache()
    with pytest.raises(ServiceAuthError, match="empty token"):
        get_service_jwt()


def test_distinct_digikey_bases_get_distinct_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey-a:8005")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url.host))
        return httpx.Response(
            200,
            json={
                "access_token": f"jwt-{len(calls)}",
                "token_type": "Bearer",
                "expires_in": 900,
            },
        )

    def _fake_post(url: str, payload: dict) -> dict:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return client.post(url, json=payload).json()

    monkeypatch.setattr("digibase.service_auth._http_post", _fake_post)
    clear_service_jwt_cache()
    assert get_service_jwt() == "jwt-1"
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey-b:8005")
    assert get_service_jwt() == "jwt-2"
    assert calls == ["digikey-a", "digikey-b"]


def test_comma_scope_tuple_collision_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            200,
            json={
                "access_token": f"jwt-{len(calls)}",
                "token_type": "Bearer",
                "expires_in": 900,
            },
        )

    def _fake_post(url: str, payload: dict) -> dict:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return client.post(url, json=payload).json()

    monkeypatch.setattr("digibase.service_auth._http_post", _fake_post)
    clear_service_jwt_cache()
    # ``",".join(("a,b",)) == ",".join(("a", "b")) == "a,b"`` — these must not share.
    assert get_service_jwt(scopes=("a,b",)) == "jwt-1"
    assert get_service_jwt(scopes=("a", "b")) == "jwt-2"
    assert len(calls) == 2


def test_http_post_uses_shared_sync_client_factory() -> None:
    import digibase.service_auth as service_auth

    from digibase import http_client

    assert service_auth.sync_client is http_client.sync_client


def test_http_post_routes_through_sync_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import digibase.service_auth as service_auth

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "jwt-x", "expires_in": 900})

    def fake_sync_client(**kwargs: object) -> httpx.Client:
        seen.append(kwargs)
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr("digibase.service_auth.sync_client", fake_sync_client)
    payload = service_auth._http_post("http://digikey:8005/v1/oauth/token", {"a": 1})
    assert payload["access_token"] == "jwt-x"
    # #4050: the exchange passes a cold-start envelope through the shared factory —
    # read is 60 s, twice the generic 30 s default; the other phases stay put.
    assert len(seen) == 1
    timeout = seen[0]["timeout"]
    assert timeout.connect == 5.0
    assert timeout.read == 60.0
    assert timeout.write == 10.0
    assert timeout.pool == 5.0


def _patch_mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Route ``service_auth`` HTTP through ``handler`` without touching the network.

    Replaces the ``sync_client`` factory on the ``service_auth`` module (not the
    shared ``http_client`` module) so each attempt builds a client backed by an
    ``httpx.MockTransport``.
    """
    import digibase.service_auth as service_auth

    def fake_sync_client(**kwargs: object) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(service_auth, "sync_client", fake_sync_client)


def test_first_call_read_timeout_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cold digikey must not fail the exchange on one read timeout (#4050)."""
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")
    # Keep the backoff instant; count the sleeps so the retry pacing is pinned.
    sleeps: list[float] = []
    monkeypatch.setattr("digibase.service_auth.time.sleep", lambda seconds: sleeps.append(seconds))
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("cold container", request=request)
        assert request.url.path == "/v1/oauth/token"
        return httpx.Response(
            200,
            json={"access_token": "jwt-1", "token_type": "Bearer", "expires_in": 900},
        )

    _patch_mock_transport(monkeypatch, handler)
    clear_service_jwt_cache()

    assert get_service_jwt() == "jwt-1"
    assert len(calls) == 2
    assert len(sleeps) == 1

    # The token won by a retry is cached exactly like a first-try success.
    assert get_service_jwt() == "jwt-1"
    assert len(calls) == 2


def test_401_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rejected key stays rejected — 4xx auth failures fail fast (#4050)."""
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")
    sleeps: list[float] = []
    monkeypatch.setattr("digibase.service_auth.time.sleep", lambda seconds: sleeps.append(seconds))
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"detail": "invalid api key"})

    _patch_mock_transport(monkeypatch, handler)
    clear_service_jwt_cache()

    with pytest.raises(ServiceAuthError, match="exchange failed"):
        get_service_jwt()
    assert len(calls) == 1
    assert sleeps == []


def test_persistent_read_timeout_raises_after_bounded_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A permanently cold digikey still bounds the retry budget at 3 attempts (#4050)."""
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")
    sleeps: list[float] = []
    monkeypatch.setattr("digibase.service_auth.time.sleep", lambda seconds: sleeps.append(seconds))
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ReadTimeout("still cold", request=request)

    _patch_mock_transport(monkeypatch, handler)
    clear_service_jwt_cache()

    with pytest.raises(ServiceAuthError, match="exchange failed"):
        get_service_jwt()
    # 1 initial attempt + 2 retries.
    assert len(calls) == 3
    assert len(sleeps) == 2


def test_server_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries are for transport failures only — an HTTP error response is terminal (#4050)."""
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")
    sleeps: list[float] = []
    monkeypatch.setattr("digibase.service_auth.time.sleep", lambda seconds: sleeps.append(seconds))
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, json={"detail": "unavailable"})

    _patch_mock_transport(monkeypatch, handler)
    clear_service_jwt_cache()

    with pytest.raises(ServiceAuthError, match="exchange failed"):
        get_service_jwt()
    assert len(calls) == 1
    assert sleeps == []
