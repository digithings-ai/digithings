"""Unit tests for digibase.otel optional wiring (#222)."""

from __future__ import annotations

import pytest
from digibase.http import outbound_service_headers
from digibase.otel import (
    inject_trace_context,
    resolve_otel_endpoint,
    resolve_otel_headers,
    setup_otel_fastapi,
)
from fastapi import FastAPI

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_otel_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DIGI_OTEL_ENDPOINT",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "DIGI_OTEL_HEADERS",
        "OTEL_EXPORTER_OTLP_HEADERS",
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


def test_resolve_otel_headers_empty_when_unset() -> None:
    assert resolve_otel_headers() == {}


def test_resolve_otel_headers_prefers_digi_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGI_OTEL_HEADERS", "X-Foo=bar")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "X-Foo=other")
    assert resolve_otel_headers() == {"X-Foo": "bar"}


def test_resolve_otel_headers_falls_back_to_standard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "X-Foo=bar")
    assert resolve_otel_headers() == {"X-Foo": "bar"}


def test_resolve_otel_headers_parses_url_decoded_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGI_OTEL_HEADERS", "Authorization=Basic%20abc,X-Foo=bar")
    assert resolve_otel_headers() == {
        "Authorization": "Basic abc",
        "X-Foo": "bar",
    }


def test_resolve_otel_headers_skips_malformed_pairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DIGI_OTEL_HEADERS", "Authorization=Basic%20abc,,noequals,=novalue,X-Foo=bar"
    )
    assert resolve_otel_headers() == {
        "Authorization": "Basic abc",
        "X-Foo": "bar",
    }


def _install_fake_otel(monkeypatch: pytest.MonkeyPatch, captured: dict[str, object]) -> None:
    import sys
    import types

    def _mod(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    otel = _mod("opentelemetry")
    trace_mod = _mod("opentelemetry.trace")
    trace_mod.set_tracer_provider = lambda provider: None  # type: ignore[attr-defined]
    otel.trace = trace_mod  # type: ignore[attr-defined]

    exporter_mod = _mod("opentelemetry.exporter.otlp.proto.http.trace_exporter")

    class _FakeExporter:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured["args"] = args
            captured["kwargs"] = kwargs

    exporter_mod.OTLPSpanExporter = _FakeExporter  # type: ignore[attr-defined]

    fastapi_mod = _mod("opentelemetry.instrumentation.fastapi")

    class _FakeFastAPIInstrumentor:
        @staticmethod
        def instrument_app(app: object) -> None:
            return None

    fastapi_mod.FastAPIInstrumentor = _FakeFastAPIInstrumentor  # type: ignore[attr-defined]

    resources_mod = _mod("opentelemetry.sdk.resources")

    class _FakeResource:
        @staticmethod
        def create(attrs: dict[str, str]) -> dict[str, str]:
            return attrs

    resources_mod.Resource = _FakeResource  # type: ignore[attr-defined]

    trace_sdk_mod = _mod("opentelemetry.sdk.trace")

    class _FakeProvider:
        def __init__(self, resource: object = None) -> None:
            self.resource = resource

        def add_span_processor(self, processor: object) -> None:
            return None

    trace_sdk_mod.TracerProvider = _FakeProvider  # type: ignore[attr-defined]

    export_mod = _mod("opentelemetry.sdk.trace.export")

    class _FakeBatchSpanProcessor:
        def __init__(self, exporter: object) -> None:
            self.exporter = exporter

    export_mod.BatchSpanProcessor = _FakeBatchSpanProcessor  # type: ignore[attr-defined]


def test_setup_otel_fastapi_passes_headers_to_exporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://otel:4318")
    monkeypatch.setenv("DIGI_OTEL_HEADERS", "Authorization=Basic%20abc,X-Foo=bar")
    captured: dict[str, object] = {}
    _install_fake_otel(monkeypatch, captured)
    setup_otel_fastapi(FastAPI(), service_name="digitest")
    kwargs = captured.get("kwargs")
    assert isinstance(kwargs, dict)
    assert kwargs.get("endpoint") == "http://otel:4318"
    assert kwargs.get("headers") == {"Authorization": "Basic abc", "X-Foo": "bar"}


def test_setup_otel_fastapi_omits_headers_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://otel:4318")
    captured: dict[str, object] = {}
    _install_fake_otel(monkeypatch, captured)
    setup_otel_fastapi(FastAPI(), service_name="digitest")
    kwargs = captured.get("kwargs")
    assert isinstance(kwargs, dict)
    assert kwargs.get("endpoint") == "http://otel:4318"
    assert not kwargs.get("headers")
