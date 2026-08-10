"""Contract-style tests: OpenAPI presence and error envelope shape (no live stack)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

# digisearch startup gate
os.environ.setdefault("DIGISEARCH_ALLOW_STUB", "1")
os.environ.setdefault("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
os.environ.setdefault("DIGIKEY_DATABASE_URL", "sqlite:////tmp/digikey-openapi-contract.sqlite")


@pytest.mark.unit
def test_digigraph_openapi_has_health_and_workflow() -> None:
    from digigraph.server import app as dg_app

    schema = dg_app.openapi()
    paths = schema.get("paths", {})
    assert "/health" in paths
    assert "/workflow" in paths
    assert "/v1/chat/completions" in paths
    assert "digigraph" in (schema.get("info") or {}).get("title", "").lower()


@pytest.mark.unit
def test_digiquant_openapi_has_strategies() -> None:
    from digiquant.server import app as dq_app

    schema = dq_app.openapi()
    assert "/strategies" in schema.get("paths", {})
    assert "/run_backtest" in schema.get("paths", {})


@pytest.mark.unit
def test_digikey_openapi_has_jwks_and_token() -> None:
    from digikey.server import app as dk_app

    schema = dk_app.openapi()
    paths = schema.get("paths", {})
    assert "/healthz" in paths
    assert "/.well-known/jwks.json" in paths
    assert "/v1/oauth/token" in paths
    assert "/v1/admin/keys" in paths


@pytest.mark.unit
def test_digisearch_openapi_has_query_and_ingest() -> None:
    from digisearch.server import app as ds_app

    schema = ds_app.openapi()
    paths = schema.get("paths", {})
    assert "/query" in paths
    assert "/ingest" in paths
    assert "/healthz" in paths


@pytest.mark.unit
def test_digismith_openapi_has_status() -> None:
    from digismith.server import app as sm_app

    schema = sm_app.openapi()
    paths = schema.get("paths", {})
    assert "/healthz" in paths
    assert "/v1/status" in paths


@pytest.mark.unit
def test_digivault_openapi_has_notes() -> None:
    from digivault.server import app as dv_app

    schema = dv_app.openapi()
    paths = schema.get("paths", {})
    assert "/healthz" in paths
    assert "/v1/notes" in paths
    assert "/v1/orchestrator_tools" in paths


@pytest.mark.unit
@pytest.mark.parametrize(
    "import_path",
    [
        "digigraph.server:app",
        "digiquant.server:app",
        "digikey.server:app",
        "digisearch.server:app",
        "digismith.server:app",
        "digivault.server:app",
    ],
)
def test_openapi_json_and_docs_public(import_path: str) -> None:
    module_path, attr = import_path.split(":")
    mod = __import__(module_path, fromlist=[attr])
    app = getattr(mod, attr)
    client = TestClient(app)
    # No auth headers — docs and schema must be auth-exempt
    r_docs = client.get("/docs")
    assert r_docs.status_code == 200
    r_oa = client.get("/openapi.json")
    assert r_oa.status_code == 200
    body = r_oa.json()
    assert "paths" in body
    assert "openapi" in body


@pytest.mark.unit
def test_digigraph_validation_error_envelope() -> None:
    from digigraph.server import app as dg_app

    client = TestClient(dg_app, headers=auth_headers())
    r = client.post("/workflow", json={})
    assert r.status_code == 422
    data = r.json()
    assert "error" in data
    assert "code" in data["error"]
    assert data["error"]["code"] == "validation_error"
