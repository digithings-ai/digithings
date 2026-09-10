"""Unit tests for digibase service-to-service digikey auth."""

from __future__ import annotations

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
