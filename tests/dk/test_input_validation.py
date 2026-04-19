"""Pydantic v2 HTTP input-validation tests for DigiKey request bodies."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    os.environ.setdefault("DIGIKEY_DATABASE_URL", "sqlite:///:memory:")
    from digikey.server import app  # imported after env gate

    return TestClient(app)


@pytest.mark.unit
class TestTokenValidation:
    """POST /v1/oauth/token → TokenRequest (extra='forbid')."""

    def test_missing_grant_type_returns_422(self, client: TestClient) -> None:
        r = client.post("/v1/oauth/token", json={"api_key": "xxx"})
        assert r.status_code == 422
        assert r.json().get("error", {}).get("code") == "validation_error"

    def test_invalid_grant_type_returns_422(self, client: TestClient) -> None:
        r = client.post("/v1/oauth/token", json={"grant_type": "bogus"})
        assert r.status_code == 422

    def test_extra_field_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/v1/oauth/token",
            json={"grant_type": "api_key", "rogue": "x"},
        )
        assert r.status_code == 422


@pytest.mark.unit
class TestAdminKeysValidation:
    """POST /v1/admin/keys → AdminIssueBody (extra='forbid')."""

    def test_missing_tenant_slug_returns_422(self, client: TestClient) -> None:
        r = client.post(
            "/v1/admin/keys",
            json={"label": "x"},
            headers={"Authorization": "Bearer wrong"},
        )
        # missing tenant_slug should fail validation before auth check
        assert r.status_code == 422

    def test_extra_field_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/v1/admin/keys",
            json={"tenant_slug": "t1", "hack": 1},
            headers={"Authorization": "Bearer wrong"},
        )
        assert r.status_code == 422
