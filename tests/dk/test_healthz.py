"""DigiKey ``/healthz`` liveness contract.

Contract (see AGENTS.md "Liveness vs status"):
* returns HTTP 200 with ``{"ok": true}``
* requires no ``Authorization`` header (admin scopes are NOT required)
* is rate-limit-exempt — the token-bucket dependency is NOT attached to the
  route, so a burst of requests must not trigger HTTP 429.
"""

from __future__ import annotations

import os

# Signing key loads at digikey.server import — allow ephemeral RS256 for unit tests.
if not (os.environ.get("DIGIKEY_PRIVATE_KEY_PEM") or "").strip():
    os.environ.setdefault("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")

import pytest
from fastapi.testclient import TestClient

from digikey.ratelimit import reset_limiter_for_tests
from digikey.server import app


@pytest.fixture
def unauth_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Tiny bucket: if /healthz were rate-limited the burst test would fail fast.
    monkeypatch.setenv("DIGIKEY_RL_PER_MIN", "1")
    monkeypatch.setenv("DIGIKEY_RL_BURST", "2")
    reset_limiter_for_tests()
    return TestClient(app)


@pytest.mark.unit
class TestHealthz:
    def test_returns_200_ok_true(self, unauth_client: TestClient) -> None:
        r = unauth_client.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_no_authorization_header_required(self, unauth_client: TestClient) -> None:
        assert "Authorization" not in unauth_client.headers
        r = unauth_client.get("/healthz")
        assert r.status_code == 200

    def test_not_rate_limited_under_burst(self, unauth_client: TestClient) -> None:
        # Burst of 100 — far above DIGIKEY_RL_BURST=2. All must return 200
        # because the rate-limit dependency is NOT attached to /healthz.
        for _ in range(100):
            r = unauth_client.get("/healthz")
            assert r.status_code == 200
