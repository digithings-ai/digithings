"""Unit tests for Phase 2 dual-export (#4931): LangSmith + OTLP (Langfuse) fan-out."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from digitrace import config as config_mod
from digitrace import trace as trace_mod

_DUAL_ENVS = (
    "LANGSMITH_API_KEY",
    "LANGSMITH_ENDPOINT",
    "DIGITRACE_LANGFUSE_OTLP_ENDPOINT",
    "LANGFUSE_OTLP_ENDPOINT",
    "LANGFUSE_HOST",
    "LANGFUSE_URL",
    "DIGI_OTEL_ENDPOINT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "DIGI_OTEL_HEADERS",
    "OTEL_EXPORTER_OTLP_HEADERS",
)


@pytest.fixture(autouse=True)
def _clear_dual_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _DUAL_ENVS:
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
        def start_as_current_span(
            self, name: str, attributes: dict[str, str] | None = None
        ) -> _FakeSpanCM:
            return _FakeSpanCM(_FakeSpan(name, attributes))

    trace_api.StatusCode = _StatusCode  # type: ignore[attr-defined]
    trace_api.get_tracer = lambda name: _FakeTracer()  # type: ignore[attr-defined]
    pkg.trace = trace_api  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry", pkg)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace_api)


def _block_otel_import(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _blocked(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    for mod in ("opentelemetry", "opentelemetry.trace"):
        monkeypatch.delitem(sys.modules, mod, raising=False)


class _FakeLangSmith:
    captured: dict[str, Any] = {}

    @staticmethod
    def traceable(**kwargs: Any):  # type: ignore[no-untyped-def]
        _FakeLangSmith.captured.update(kwargs)

        def wrap(fn):  # type: ignore[no-untyped-def]
            return fn

        return wrap


def _enable_fake_langsmith(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeLangSmith.captured = {}
    monkeypatch.setattr(trace_mod, "LANGSMITH_SDK_AVAILABLE", True)
    monkeypatch.setattr(trace_mod, "_langsmith", _FakeLangSmith)
    monkeypatch.setattr(config_mod, "langsmith_sdk_importable", lambda: True)
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")


@pytest.mark.unit
def test_default_backend_none_and_noop_identity() -> None:
    assert config_mod.export_backend() == "none"
    assert config_mod.dual_export_enabled() is False
    assert config_mod.otel_export_configured() is False
    assert config_mod.langfuse_configured() is False

    def fn() -> int:
        return 1

    assert trace_mod.traceable("x")(fn) is fn
    assert trace_mod.otel_leg_enabled() is False


@pytest.mark.unit
def test_langsmith_only_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_fake_langsmith(monkeypatch)
    _block_otel_import(monkeypatch)
    assert config_mod.export_backend() == "langsmith"
    assert config_mod.dual_export_enabled() is False

    @trace_mod.traceable("ls_only")
    def fn() -> int:
        return 2

    assert fn() == 2
    assert _FakeLangSmith.captured["name"] == "ls_only"
    assert callable(_FakeLangSmith.captured["process_inputs"])


@pytest.mark.unit
def test_otlp_only_backend_opens_span(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trace_mod, "LANGSMITH_SDK_AVAILABLE", False)
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://otel:4318")
    spans: list[dict[str, Any]] = []
    _install_fake_otel(monkeypatch, spans)
    assert config_mod.export_backend() == "otel"
    assert config_mod.dual_export_enabled() is False
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
def test_dual_export_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    """One call reaches both legs with the same correlation context."""
    _enable_fake_langsmith(monkeypatch)
    monkeypatch.setenv(
        "DIGITRACE_LANGFUSE_OTLP_ENDPOINT", "https://trace.example.com/api/public/otel"
    )
    spans: list[dict[str, Any]] = []
    _install_fake_otel(monkeypatch, spans)
    assert config_mod.export_backend() == "dual"
    assert config_mod.dual_export_enabled() is True

    @trace_mod.traceable("run_tools")
    def fn(*, request_id: str = "", session_id: str = "") -> str:
        return f"{request_id}/{session_id}"

    assert fn(request_id="r-1", session_id="s-1") == "r-1/s-1"
    # LangSmith leg saw the call (redaction hooks attached).
    assert _FakeLangSmith.captured["name"] == "run_tools"
    assert callable(_FakeLangSmith.captured["process_inputs"])
    # OTel leg saw the same call with the same correlation ids.
    assert len(spans) == 1
    assert spans[0]["name"] == "digitrace.run_tools"
    assert spans[0]["attributes"]["digi.request_id"] == "r-1"
    assert spans[0]["attributes"]["digi.session_id"] == "s-1"


@pytest.mark.unit
def test_otel_leg_exception_propagates_and_marks_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trace_mod, "LANGSMITH_SDK_AVAILABLE", False)
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
    monkeypatch.setattr(trace_mod, "LANGSMITH_SDK_AVAILABLE", False)
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://otel:4318")
    _block_otel_import(monkeypatch)
    assert trace_mod.otel_leg_enabled() is False

    def fn() -> int:
        return 5

    assert trace_mod.traceable("x")(fn) is fn


@pytest.mark.unit
def test_langfuse_specific_backend_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_OTLP_ENDPOINT", "https://trace.example.com/api/public/otel")
    assert config_mod.langfuse_configured() is True
    assert config_mod.export_backend() == "langfuse-otlp"
    assert config_mod.langfuse_host_sanitized() == "trace.example.com"


@pytest.mark.unit
def test_langfuse_host_does_not_relabel_generic_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    """LANGFUSE_HOST is display-only. A generic OTEL endpoint stays ``otel``."""
    monkeypatch.setenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel:4318")
    assert config_mod.langfuse_configured() is True
    assert config_mod.export_backend() == "otel"


@pytest.mark.unit
def test_langfuse_otlp_endpoint_installs_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Langfuse-only endpoint must build an OTLP exporter, not only a local span."""
    monkeypatch.setattr(trace_mod, "LANGSMITH_SDK_AVAILABLE", False)
    endpoint = "https://cloud.langfuse.com/api/public/otel"
    monkeypatch.setenv("DIGITRACE_LANGFUSE_OTLP_ENDPOINT", endpoint)
    monkeypatch.setenv("DIGI_OTEL_HEADERS", "Authorization=Basic%20abc")
    constructed: dict[str, Any] = {}
    spans: list[dict[str, Any]] = []

    def _pkg(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        mod.__path__ = []  # type: ignore[attr-defined]
        mod.__package__ = name
        return mod

    otel = _pkg("opentelemetry")
    trace_api = _pkg("opentelemetry.trace")
    sdk_trace = _pkg("opentelemetry.sdk.trace")
    sdk_export = _pkg("opentelemetry.sdk.trace.export")
    exporter_mod = _pkg("opentelemetry.exporter.otlp.proto.http.trace_exporter")

    class _StatusCode:
        UNSET = "UNSET"
        ERROR = "ERROR"

    class ProxyTracerProvider:
        """Name must match the SDK proxy so the installer treats it as unset."""

    class _FakeTracer:
        def start_as_current_span(self, name: str, attributes: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
            class _CM:
                def __enter__(self_cm):  # type: ignore[no-untyped-def]
                    return self

                def __exit__(self_cm, *_args: object) -> bool:
                    spans.append({"name": name})
                    return False

                def set_status(self_cm, _status: object) -> None:
                    return None

            return _CM()

    class _Exporter:
        def __init__(self, *, endpoint: str, headers: dict[str, str] | None = None) -> None:
            constructed["endpoint"] = endpoint
            constructed["headers"] = headers

    class _Processor:
        def __init__(self, exporter: _Exporter) -> None:
            constructed["processor"] = exporter

    class _Provider:
        def add_span_processor(self, processor: _Processor) -> None:
            constructed["added"] = processor

    trace_api.StatusCode = _StatusCode  # type: ignore[attr-defined]
    trace_api.get_tracer = lambda _name: _FakeTracer()  # type: ignore[attr-defined]
    trace_api.get_tracer_provider = lambda: ProxyTracerProvider()  # type: ignore[attr-defined]
    trace_api.set_tracer_provider = lambda provider: constructed.setdefault("provider", provider)  # type: ignore[attr-defined]
    sdk_trace.TracerProvider = _Provider  # type: ignore[attr-defined]
    sdk_export.BatchSpanProcessor = _Processor  # type: ignore[attr-defined]
    exporter_mod.OTLPSpanExporter = _Exporter  # type: ignore[attr-defined]
    otel.trace = trace_api  # type: ignore[attr-defined]

    for name, mod in (
        ("opentelemetry", otel),
        ("opentelemetry.trace", trace_api),
        ("opentelemetry.sdk", _pkg("opentelemetry.sdk")),
        ("opentelemetry.sdk.trace", sdk_trace),
        ("opentelemetry.sdk.trace.export", sdk_export),
        ("opentelemetry.exporter", _pkg("opentelemetry.exporter")),
        ("opentelemetry.exporter.otlp", _pkg("opentelemetry.exporter.otlp")),
        ("opentelemetry.exporter.otlp.proto", _pkg("opentelemetry.exporter.otlp.proto")),
        ("opentelemetry.exporter.otlp.proto.http", _pkg("opentelemetry.exporter.otlp.proto.http")),
        ("opentelemetry.exporter.otlp.proto.http.trace_exporter", exporter_mod),
    ):
        monkeypatch.setitem(sys.modules, name, mod)

    @trace_mod.traceable("langfuse-span")
    def fn() -> str:
        return "ok"

    assert fn() == "ok"
    assert constructed["endpoint"] == endpoint
    assert constructed["headers"] == {"Authorization": "Basic abc"}
    assert "provider" in constructed
    assert spans[0]["name"] == "digitrace.langfuse-span"


@pytest.mark.unit
def test_langfuse_host_sanitized_strips_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DIGITRACE_LANGFUSE_OTLP_ENDPOINT",
        "https://user:pass123@trace.example.com:443/api/public/otel?tok=abc",
    )
    host = config_mod.langfuse_host_sanitized()
    assert host == "trace.example.com"
    assert "pass123" not in (host or "")
    monkeypatch.delenv("DIGITRACE_LANGFUSE_OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("LANGFUSE_HOST", "trace.example.com")
    assert config_mod.langfuse_host_sanitized() == "trace.example.com"


@pytest.mark.unit
def test_status_dual_fields_secret_free(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from digitrace import server as server_mod

    monkeypatch.setattr(server_mod, "tracing_enabled", lambda: True)
    monkeypatch.setattr(server_mod, "langsmith_sdk_importable", lambda: True)
    monkeypatch.setattr(server_mod, "langsmith_host_sanitized", lambda: "api.smith.langchain.com")
    monkeypatch.setattr(server_mod, "langfuse_configured", lambda: True)
    monkeypatch.setattr(server_mod, "otel_export_configured", lambda: True)
    monkeypatch.setattr(server_mod, "dual_export_enabled", lambda: True)
    monkeypatch.setattr(server_mod, "export_backend", lambda: "dual")
    monkeypatch.setattr(server_mod, "langfuse_host_sanitized", lambda: "trace.example.com")
    client = TestClient(server_mod.app)
    r = client.get("/v1/status")
    assert r.status_code == 200
    body = r.json()
    assert body["dual_export"] is True
    assert body["export_backend"] == "dual"
    assert body["langfuse_configured"] is True
    assert body["otel_export_configured"] is True
    assert body["langfuse_host"] == "trace.example.com"
    assert "lsv2_" not in r.text
    assert "pass123" not in r.text
