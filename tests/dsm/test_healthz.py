"""DigiSmith ``/healthz`` liveness contract.

Contract (see AGENTS.md "Liveness vs status"): ``/healthz`` is the minimal
liveness probe; ``/v1/status`` remains the richer diagnostic surface.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digismith.server import app

_client = TestClient(app)


@pytest.mark.unit
class TestHealthz:
    def test_returns_200_ok_true(self) -> None:
        r = _client.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_no_authorization_header_required(self) -> None:
        assert "Authorization" not in _client.headers
        r = _client.get("/healthz")
        assert r.status_code == 200

    def test_not_rate_limited_under_burst(self) -> None:
        for _ in range(100):
            r = _client.get("/healthz")
            assert r.status_code == 200

    def test_v1_status_still_available(self) -> None:
        """Contract: ``/healthz`` does not replace ``/v1/status`` — both must work."""
        r = _client.get("/v1/status")
        assert r.status_code == 200
