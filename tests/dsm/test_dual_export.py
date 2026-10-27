"""Unit tests for the digitrace trace wrapper and backend resolution.

Acceptance for the ADR-0036 amendment: the in-house OTLP leg is the default and
the remaining vendor integration (LangSmith) is only ever selected by its own
env vars — supported, never the default digitrace solution.
"""

from __future__ import annotations

import sys
import types
from typing import Any, get_args

import pytest
from digitrace.config import ExportBackend

from digitrace import config as config_mod
from digitrace import trace as trace_mod

_TELEMETRY_ENVS = (
    "LANGSMITH_API_KEY",
    "LANGSMITH_ENDPOINT",
    "DIGI_OTEL_ENDPOINT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "DIGI_OTEL_HEADERS",
    "OTEL_EXPORTER_OTLP_HEADERS",
)

_VENDOR_BACKENDS = {"dual", "langsmith"}


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _TELEMETRY_ENVS:
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


# --- 1. every backend value parses and is accepted when configured ----------


@pytest.mark.unit
def test_backend_enum_has_the_four_documented_values() -> None:
    assert set(get_args(ExportBackend)) == {"dual", "langsmith", "otel", "none"}


@pytest.mark.unit
@pytest.mark.parametrize("backend", ["dual", "langsmith", "otel", "none"])
def test_status_model_accepts_every_backend_value(backend: str) -> None:
    status = config_mod.TraceStatus(
        version="0.1.0",
        tracing_configured=backend != "none",
        langsmith_sdk_installed=False,
        export_backend=backend,
    )
    assert status.export_backend == backend


@pytest.mark.unit
def test_langsmith_backend_selected_when_key_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")
    assert config_mod.export_backend() == "langsmith"
    assert config_mod.tracing_enabled() is True
    assert config_mod.langsmith_host_sanitized() == "api.smith.langchain.com"


@pytest.mark.unit
def test_langsmith_backend_uses_configured_endpoint_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://eu.api.smith.langchain.com/extra?q=1")
    assert config_mod.export_backend() == "langsmith"
    assert config_mod.langsmith_host_sanitized() == "eu.api.smith.langchain.com"


@pytest.mark.unit
def test_dual_backend_when_both_legs_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://collector:4318")
    assert config_mod.export_backend() == "dual"
    # The dual flag additionally requires the SDK to be importable.
    monkeypatch.setattr(config_mod, "langsmith_sdk_importable", lambda: True)
    assert config_mod.dual_export_enabled() is True


# --- 2. the default is in-house and never a vendor -------------------------


@pytest.mark.unit
def test_default_backend_is_none_without_any_env() -> None:
    assert config_mod.export_backend() == "none"
    assert config_mod.otel_export_configured() is False
    assert config_mod.tracing_enabled() is False
    assert config_mod.langsmith_host_sanitized() is None

    def fn() -> int:
        return 1

    assert trace_mod.traceable("x")(fn) is fn
    assert trace_mod.otel_leg_enabled() is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "env_var",
    ["DIGI_OTEL_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"],
)
def test_plain_otlp_endpoint_resolves_to_in_house_otel_never_a_vendor(
    monkeypatch: pytest.MonkeyPatch, env_var: str
) -> None:
    """The regression test: a generic endpoint must not drift to a vendor default."""
    monkeypatch.setenv(env_var, "http://digitrace:8003/v1/otlp")
    assert config_mod.export_backend() == "otel"
    assert config_mod.export_backend() not in _VENDOR_BACKENDS


@pytest.mark.unit
def test_langsmith_endpoint_alone_is_not_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the key opts in; an endpoint with no key keeps the in-house default."""
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    assert config_mod.export_backend() == "none"
    assert config_mod.export_backend() not in _VENDOR_BACKENDS


@pytest.mark.unit
def test_unrelated_vendor_keys_never_select_a_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for vendor_env, value in (
        ("HELICONE_API_KEY", "sk-helicone-fake"),
        ("BRAINTRUST_API_KEY", "sk-braintrust-fake"),
        ("ARIZE_API_KEY", "sk-arize-fake"),
        ("DATADOG_API_KEY", "dd-fake"),
    ):
        monkeypatch.setenv(vendor_env, value)
    assert config_mod.export_backend() == "none"


# --- 3. status exposes vendor state, never a secret ------------------------


@pytest.mark.unit
def test_status_exposes_vendor_host_and_flags_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from digitrace import server as server_mod

    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_super_secret_token_do_not_leak")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://eu.api.smith.langchain.com")
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://collector:4318")
    monkeypatch.setattr(server_mod, "langsmith_sdk_importable", lambda: True)

    r = TestClient(server_mod.app).get("/v1/status")
    assert r.status_code == 200
    body = r.json()
    assert body["export_backend"] == "dual"
    assert body["dual_export"] is True
    assert body["otel_export_configured"] is True
    assert body["langsmith_sdk_installed"] is True
    assert body["langsmith_host"] == "eu.api.smith.langchain.com"
    assert "lsv2_" not in r.text
    assert "sk-lf" not in r.text


# --- OTel leg behaviour ----------------------------------------------------


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


# --- optional LangSmith SDK leg -------------------------------------------


@pytest.mark.unit
def test_langsmith_leg_is_noop_when_sdk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")
    monkeypatch.setattr(trace_mod, "LANGSMITH_SDK_AVAILABLE", False)
    monkeypatch.setattr(trace_mod, "_langsmith", None, raising=False)

    def fn() -> int:
        return 3

    assert trace_mod.traceable("x")(fn) is fn


@pytest.mark.unit
def test_langsmith_leg_wraps_with_redaction_when_sdk_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}
    fake = types.ModuleType("langsmith")

    def _traceable(**kwargs: Any) -> Any:
        calls.update(kwargs)

        def _outer(inner: Any) -> Any:
            calls["inner"] = inner
            return inner

        return _outer

    fake.traceable = _traceable  # type: ignore[attr-defined]
    monkeypatch.setattr(trace_mod, "LANGSMITH_SDK_AVAILABLE", True)
    monkeypatch.setattr(trace_mod, "_langsmith", fake, raising=False)
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")

    def fn() -> int:
        return 7

    wrapped = trace_mod.traceable("x")(fn)
    assert wrapped is fn  # no OTLP endpoint -> OTel leg stays a no-op
    assert calls["name"] == "x"
    assert callable(calls["process_inputs"])
    assert callable(calls["process_outputs"])
