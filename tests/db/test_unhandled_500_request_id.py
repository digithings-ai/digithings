"""REM-066: X-Request-ID on unhandled 500 responses."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from digibase.errors import register_fastapi_error_handlers
from digibase.http import install_request_id_middleware


@pytest.mark.unit
def test_unhandled_exception_includes_request_id_header() -> None:
    app = FastAPI()
    install_request_id_middleware(app)
    register_fastapi_error_handlers(app, service="test")

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/boom", headers={"X-Request-ID": "rid-500"})
    assert r.status_code == 500
    assert r.headers.get("X-Request-ID") == "rid-500"
    body = r.json()
    assert body["error"]["request_id"] == "rid-500"
