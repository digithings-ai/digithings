"""Unit tests for digibase.otel optional wiring (#222)."""

from __future__ import annotations

import pytest
from digibase.http import outbound_service_headers
from digibase.otel import inject_trace_context, resolve_otel_endpoint, setup_otel_fastapi
from fastapi import FastAPI

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_otel_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DIGI_OTEL_ENDPOINT",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_SERVICE_VERSION",
        "DIGI_SERVICE_VERSION",
    ):
        monkeypatch.delenv(key, raising=False)


def test_resolve_otel_endpoint_empty_when_unset() -> None:
    assert resolve_otel_endpoint() == ""


def test_resolve_otel_endpoint_prefers_digi_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://otel:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://other:4318")
    assert resolve_otel_endpoint() == "http://otel:4318"


def test_resolve_otel_endpoint_falls_back_to_standard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://std:4318")
    assert resolve_otel_endpoint() == "http://std:4318"


def test_setup_otel_fastapi_noop_without_endpoint() -> None:
    app = FastAPI()
    # Must not raise when tracing is disabled (no OTel packages required).
    setup_otel_fastapi(app, service_name="digitest", service_version="9.9.9")
    assert app.title == "FastAPI"


def test_inject_trace_context_noop_without_endpoint() -> None:
    headers: dict[str, str] = {"X-Request-ID": "abc"}
    inject_trace_context(headers)
    assert headers == {"X-Request-ID": "abc"}


def test_outbound_headers_still_work_without_otel() -> None:
    h = outbound_service_headers("req-1", "tok", extra={"X-Extra": "1"})
    assert h["X-Request-ID"] == "req-1"
    assert h["Authorization"] == "Bearer tok"
    assert h["X-Extra"] == "1"
    # No trace headers when tracing disabled.
    assert "traceparent" not in h


def test_setup_otel_fastapi_warns_when_packages_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://otel:4318")

    import builtins

    real_import = builtins.__import__

    def _block_otel(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name.startswith("opentelemetry"):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_otel)
    app = FastAPI()
    with caplog.at_level("WARNING"):
        setup_otel_fastapi(app, service_name="digitest")
    assert any("OpenTelemetry packages are missing" in r.message for r in caplog.records)
