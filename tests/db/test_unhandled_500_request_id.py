"""REM-066: X-Request-ID on unhandled 500 responses."""

from __future__ import annotations

import logging

import pytest
from digibase.errors import register_fastapi_error_handlers
from digibase.http import install_request_id_middleware
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _boom_app() -> FastAPI:
    app = FastAPI()
    install_request_id_middleware(app)
    register_fastapi_error_handlers(app, service="test")

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    return app


@pytest.mark.unit
def test_unhandled_exception_includes_request_id_header() -> None:
    client = TestClient(_boom_app(), raise_server_exceptions=False)
    r = client.get("/boom", headers={"X-Request-ID": "rid-500"})
    assert r.status_code == 500
    assert r.headers.get("X-Request-ID") == "rid-500"
    body = r.json()
    assert body["error"]["request_id"] == "rid-500"


@pytest.mark.unit
def test_unhandled_exception_logs_correlated_record(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = TestClient(_boom_app(), raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="digibase.errors"):
        r = client.get("/boom", headers={"X-Request-ID": "rid-log-500"})

    assert r.status_code == 500

    records = [rec for rec in caplog.records if rec.name == "digibase.errors"]
    assert records, "expected digibase.errors to log the unhandled exception"
    record = records[-1]
    assert record.levelno == logging.ERROR
    message = record.getMessage()
    assert "rid-log-500" in message
    assert "RuntimeError" in message
    assert "kaboom" in message
    # The handler intentionally omits exc_info: Starlette's ServerErrorMiddleware
    # re-raises and uvicorn logs the full traceback on its own logger, which
    # TestClient does not capture. Asserting no exc_info here pins that this
    # record does not double-log the traceback.
    assert record.exc_info is None
