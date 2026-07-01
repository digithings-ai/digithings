"""Unit tests for the digibase X-Request-ID correlation primitives (task #213)."""

from __future__ import annotations

import logging
import re

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from digibase.http import (
    RequestIdLogFilter,
    current_request_id,
    install_request_id_logging,
    install_request_id_middleware,
    outbound_request_id_headers,
    outbound_service_headers,
)


pytestmark = pytest.mark.unit


_HEX_32 = re.compile(r"^[0-9a-f]{32}$")


def _build_app() -> FastAPI:
    app = FastAPI()
    install_request_id_middleware(app)

    @app.get("/echo")
    def echo(request: Request) -> dict[str, str | None]:
        return {
            "state": getattr(request.state, "request_id", None),
            "ctx": current_request_id(),
        }

    return app


def test_middleware_passes_through_inbound_header() -> None:
    client = TestClient(_build_app())
    resp = client.get("/echo", headers={"X-Request-ID": "trace-abc"})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == "trace-abc"
    body = resp.json()
    assert body == {"state": "trace-abc", "ctx": "trace-abc"}


def test_middleware_generates_hex_id_when_header_missing() -> None:
    client = TestClient(_build_app())
    resp = client.get("/echo")
    assert resp.status_code == 200
    generated = resp.headers["X-Request-ID"]
    assert _HEX_32.match(generated), generated
    body = resp.json()
    assert body["state"] == generated
    assert body["ctx"] == generated


def test_middleware_generates_hex_id_when_header_blank() -> None:
    client = TestClient(_build_app())
    resp = client.get("/echo", headers={"X-Request-ID": "   "})
    assert resp.status_code == 200
    assert _HEX_32.match(resp.headers["X-Request-ID"])


def test_context_var_resets_after_request() -> None:
    """Leaking the ctxvar between requests would cross-contaminate outbound calls."""
    client = TestClient(_build_app())
    client.get("/echo", headers={"X-Request-ID": "rid-1"})
    assert current_request_id() is None


def test_outbound_request_id_headers_trims_and_skips_empty() -> None:
    assert outbound_request_id_headers(None) is None
    assert outbound_request_id_headers("") is None
    assert outbound_request_id_headers("   ") is None
    assert outbound_request_id_headers("  abc  ") == {"X-Request-ID": "abc"}


def test_outbound_service_headers_merges_id_bearer_and_extra() -> None:
    out = outbound_service_headers("rid-7", "jwt.tok", extra={"X-Tenant": "acme", "empty": ""})
    assert out == {"X-Request-ID": "rid-7", "Authorization": "Bearer jwt.tok", "X-Tenant": "acme"}


def test_log_filter_defaults_request_id_when_no_request_active() -> None:
    """Records emitted at startup or in background tasks must not raise on %(request_id)s."""
    flt = RequestIdLogFilter()
    record = logging.LogRecord("x", logging.INFO, "x", 1, "hi", None, None)
    assert flt.filter(record) is True
    assert record.request_id == "-"


def test_install_request_id_logging_is_idempotent() -> None:
    target = logging.getLogger("digibase.test.idempotent_req_id")
    target.filters.clear()
    first = install_request_id_logging(target)
    second = install_request_id_logging(target)
    assert first is second
    assert sum(isinstance(f, RequestIdLogFilter) for f in target.filters) == 1


def test_log_filter_picks_up_in_flight_request_id() -> None:
    log = logging.getLogger("digibase.test.req_id_flow")
    log.setLevel(logging.INFO)
    install_request_id_logging(log)

    captured: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
            captured.append(getattr(record, "request_id", "MISSING"))

    log.addHandler(_Capture())

    app = FastAPI()
    install_request_id_middleware(app)

    @app.get("/log")
    def _log() -> dict[str, bool]:
        log.info("hello")
        return {"ok": True}

    client = TestClient(app)
    client.get("/log", headers={"X-Request-ID": "rid-log"})

    assert "rid-log" in captured
