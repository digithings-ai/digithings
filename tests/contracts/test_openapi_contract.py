"""Contract-style tests: OpenAPI presence and error envelope shape (no live stack)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digigraph.server import app as dg_app
from tests.digi_test_jwt import auth_headers


@pytest.mark.unit
def test_digigraph_openapi_has_health_and_workflow() -> None:
    schema = dg_app.openapi()
    paths = schema.get("paths", {})
    assert "/health" in paths
    assert "/workflow" in paths
    assert "/v1/chat/completions" in paths


@pytest.mark.unit
def test_digiquant_openapi_has_strategies() -> None:
    from digiquant.server import app as dq_app

    schema = dq_app.openapi()
    assert "/strategies" in schema.get("paths", {})


@pytest.mark.unit
def test_digigraph_validation_error_envelope() -> None:
    client = TestClient(dg_app, headers=auth_headers())
    r = client.post("/workflow", json={})
    assert r.status_code == 422
    data = r.json()
    assert "error" in data
    assert "code" in data["error"]
    assert data["error"]["code"] == "validation_error"
