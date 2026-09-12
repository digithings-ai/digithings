"""Unit tests for digibase service-to-service digikey auth."""

from __future__ import annotations

import time

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
    # No ``timeout=`` override: the bounded default from the factory applies.
    assert seen == [{}]
