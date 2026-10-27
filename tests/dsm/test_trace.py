"""Unit tests for digitrace.trace (OTLP-only wrapper)."""

from __future__ import annotations

import pytest

from digitrace import trace as trace_mod


@pytest.mark.unit
def test_traceable_no_op_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DIGI_OTEL_ENDPOINT",
        "DIGITRACE_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")

    @trace_mod.traceable("demo")
    def fn() -> int:
        return 42

    assert fn() == 42
    assert fn.__name__ == "fn"


@pytest.mark.unit
def test_traceable_no_op_without_otel_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://digitrace:8003/v1/otlp")
    monkeypatch.setitem(__import__("sys").modules, "opentelemetry", None)
    monkeypatch.setitem(__import__("sys").modules, "opentelemetry.trace", None)

    @trace_mod.traceable("demo2")
    def fn2() -> str:
        return "x"

    assert fn2() == "x"


@pytest.mark.unit
def test_otel_leg_enabled_reports_endpoint_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_OTEL_ENDPOINT", raising=False)
    monkeypatch.delenv("DIGITRACE_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert trace_mod.otel_leg_enabled() is False

    monkeypatch.setenv("DIGITRACE_OTLP_ENDPOINT", "http://digitrace:8003/v1/otlp")
    # Endpoint alone is not enough without the SDK installed in this environment.
    assert trace_mod.otel_leg_enabled() == _sdk_present()


def _sdk_present() -> bool:
    try:
        import opentelemetry.trace  # noqa: F401
    except ImportError:
        return False
    return True
