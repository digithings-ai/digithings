"""DigiQuant ``/healthz`` liveness contract.

Contract (see AGENTS.md "Liveness vs status"):
* returns HTTP 200 with ``{"ok": true}``
* requires no ``Authorization`` header
* is rate-limit-exempt (burst of requests all succeed)
"""

from __future__ import annotations

import pytest

pytest.importorskip("nautilus_trader")

from fastapi.testclient import TestClient  # noqa: E402

from digiquant.server import app  # noqa: E402


@pytest.fixture
def unauth_client() -> TestClient:
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
        for _ in range(100):
            r = unauth_client.get("/healthz")
            assert r.status_code == 200
