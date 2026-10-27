"""Unit tests for the OTLP-only digitrace trace wrapper.

The vendor SDK leg is gone (#4929): the only export path is the generic OTLP
endpoint/headers pair, which an operator may point at any collector.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from digitrace import config as config_mod
from digitrace import trace as trace_mod

_OTLP_ENVS = (
    "LANGSMITH_API_KEY",
    "LANGSMITH_ENDPOINT",
    "DIGI_OTEL_ENDPOINT",
    "DIGITRACE_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "DIGI_OTEL_HEADERS",
    "OTEL_EXPORTER_OTLP_HEADERS",
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _OTLP_ENVS:
        monkeypatch.delenv(key, raising=False)


def _install_fake_otel(monkeypatch: pytest.MonkeyPatch, spans: list[dict[str, Any]]) -> None:
    pkg = types.ModuleType("opentelemetry")
    trace_api = types.ModuleType("opentelemetry.trace")

    class _StatusCode:
        UNSET = "UNSET"
        OK = "OK"
        ERROR = "ERROR"

    class _FakeSpan:
        def __init__(self, name: str, attributes: dict[str, str] | None) -> None:
            self.name = name
            self.attributes = dict(attributes or {})
            self.status: str = _StatusCode.UNSET

        def set_status(self, status: str) -> None:
            self.status = status

    class _FakeSpanCM:
        def __init__(self, span: _FakeSpan) -> None:
            self._span = span

        def __enter__(self) -> _FakeSpan:
            return self._span

        def __exit__(self, *args: object) -> bool:
            spans.append(
                {
                    "name": self._span.name,
                    "attributes": self._span.attributes,
                    "status": self._span.status,
                }
            )
            return False

    class _FakeTracer:
        def start_as_current_span(self, name: str, attributes: dict[str, str]) -> _FakeSpanCM:
            return _FakeSpanCM(_FakeSpan(name, attributes))

    class _FakeTrace:
        StatusCode = _StatusCode

        @staticmethod
        def get_tracer(_name: str) -> _FakeTracer:
            return _FakeTracer()

    trace_api.StatusCode = _StatusCode
    trace_api.get_tracer = _FakeTrace.get_tracer
    pkg.trace = trace_api
    monkeypatch.setitem(sys.modules, "opentelemetry", pkg)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace_api)


def _block_otel_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", None)


@pytest.mark.unit
def test_default_backend_none_and_noop_identity() -> None:
    assert config_mod.export_backend() == "none"
    assert config_mod.otel_export_configured() is False
    assert config_mod.tracing_enabled() is False

    def fn() -> int:
        return 1

    assert trace_mod.traceable("x")(fn) is fn
    assert trace_mod.otel_leg_enabled() is False


@pytest.mark.unit
def test_otlp_backend_opens_span(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://otel:4318")
    spans: list[dict[str, Any]] = []
    _install_fake_otel(monkeypatch, spans)
    assert config_mod.export_backend() == "otel"
    assert config_mod.tracing_enabled() is True
    assert trace_mod.otel_leg_enabled() is True

    @trace_mod.traceable("completion")
    def fn(workflow_id: str = "") -> str:
        return f"ok:{workflow_id}"

    assert fn.__name__ == "fn"
    assert fn(workflow_id="wf-1") == "ok:wf-1"
    assert len(spans) == 1
    assert spans[0]["name"] == "digitrace.completion"
    assert spans[0]["attributes"]["digi.run_name"] == "completion"
    assert spans[0]["attributes"]["digi.workflow_id"] == "wf-1"


@pytest.mark.unit
def test_otel_leg_exception_propagates_and_marks_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel:4318")
    spans: list[dict[str, Any]] = []
    _install_fake_otel(monkeypatch, spans)

    @trace_mod.traceable("boom")
    def fn() -> None:
        raise ValueError("inner failure")

    with pytest.raises(ValueError, match="inner failure"):
        fn()
    assert len(spans) == 1
    assert spans[0]["status"] == "ERROR"


@pytest.mark.unit
def test_correlation_attrs_from_state_mapping_and_safety() -> None:
    assert trace_mod._correlation_attrs((), {"workflow_id": "wf-9"}) == {"digi.workflow_id": "wf-9"}
    # First positional mapping (LangGraph state dict) is honored.
    attrs = trace_mod._correlation_attrs(({"request_id": "req-7"},), {})
    assert attrs == {"digi.request_id": "req-7"}
    # Over-long values are dropped, never truncated into a leak.
    assert trace_mod._correlation_attrs((), {"session_id": "x" * 129}) == {}
    # Non-strings and blanks are dropped.
    assert trace_mod._correlation_attrs((), {"workflow_id": 123}) == {}
    assert trace_mod._correlation_attrs((), {"workflow_id": "  "}) == {}
    # Unknown keys (prompts, secrets) never become attributes.
    assert trace_mod._correlation_attrs((), {"prompt": "hello", "api_key": "sk-x"}) == {}


@pytest.mark.unit
def test_otel_noop_without_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://otel:4318")
    _block_otel_import(monkeypatch)
    assert trace_mod.otel_leg_enabled() is False

    def fn() -> int:
        return 5

    assert trace_mod.traceable("x")(fn) is fn


@pytest.mark.unit
def test_no_vendor_backend_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the generic OTLP pair selects a backend; no vendor env is read."""
    for vendor_env, value in (
        ("LANGSMITH_API_KEY", "lsv2_fake"),
        ("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        ("LANGFUSE_SECRET_KEY", "sk-lf-fake"),
        ("LANGFUSE_HOST", "trace.example.com"),
        ("HELICONE_API_KEY", "sk-helicone-fake"),
        ("BRAINTRUST_API_KEY", "sk-braintrust-fake"),
        ("ARIZE_API_KEY", "sk-arize-fake"),
        ("DATADOG_API_KEY", "dd-fake"),
    ):
        monkeypatch.setenv(vendor_env, value)
    assert config_mod.export_backend() == "none"
    assert config_mod.otel_export_configured() is False
    for removed in ("langsmith_sdk_importable", "langsmith_host_sanitized", "dual_export_enabled"):
        assert not hasattr(config_mod, removed)

    monkeypatch.setenv("DIGITRACE_OTLP_ENDPOINT", "http://digitrace:8003/v1/otlp")
    assert config_mod.export_backend() == "otel"


@pytest.mark.unit
def test_status_fields_secret_free(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from digitrace import server as server_mod

    monkeypatch.setattr(server_mod, "tracing_enabled", lambda: True)
    monkeypatch.setattr(server_mod, "otel_export_configured", lambda: True)
    monkeypatch.setattr(server_mod, "export_backend", lambda: "otel")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_super_secret_token_do_not_leak")
    client = TestClient(server_mod.app)
    r = client.get("/v1/status")
    assert r.status_code == 200
    body = r.json()
    assert body["export_backend"] == "otel"
    assert body["otel_export_configured"] is True
    assert "langsmith_sdk_installed" not in body
    assert "langsmith_host" not in body
    assert "dual_export" not in body
    assert "lsv2_" not in r.text
    assert "pass123" not in r.text
