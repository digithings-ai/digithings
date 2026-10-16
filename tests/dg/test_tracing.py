"""Unit tests for digigraph Phase 2 tracing wiring (#4931)."""

from __future__ import annotations

import pytest

from digigraph import tracing as tracing_mod

_TRACING_ENVS = (
    "LANGSMITH_API_KEY",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING_V2",
    "DIGITRACE_LANGFUSE_OTLP_ENDPOINT",
    "LANGFUSE_OTLP_ENDPOINT",
    "DIGI_OTEL_ENDPOINT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
)


@pytest.fixture(autouse=True)
def _clear_tracing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _TRACING_ENVS:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.unit
def test_run_span_name_shared() -> None:
    assert tracing_mod.RUN_SPAN_NAME == "digigraph_workflow_run"
    assert tracing_mod.NODE_SPAN_PREFIX == "digigraph_node"


@pytest.mark.unit
def test_trace_helpers_noop_when_disabled() -> None:
    def fn(state: dict) -> dict:
        return state

    assert tracing_mod.trace_node("backtest")(fn) is fn
    assert tracing_mod.trace_run(fn) is fn


@pytest.mark.unit
def test_configure_sets_langsmith_defaults_when_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")
    status = tracing_mod.configure_langgraph_tracing()
    import os

    assert os.environ.get("LANGSMITH_TRACING") == "true"
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    assert status["otel"] is False


@pytest.mark.unit
def test_configure_respects_explicit_operator_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    tracing_mod.configure_langgraph_tracing()
    import os

    assert os.environ.get("LANGSMITH_TRACING") == "false"


@pytest.mark.unit
def test_configure_noop_without_key() -> None:
    import os

    status = tracing_mod.configure_langgraph_tracing()
    assert "LANGSMITH_TRACING" not in os.environ
    assert status["langsmith"] is False
    assert status["otel"] is False


@pytest.mark.unit
def test_configure_reports_otel_when_endpoint_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DIGITRACE_LANGFUSE_OTLP_ENDPOINT", "https://trace.example.com/api/public/otel"
    )
    status = tracing_mod.configure_langgraph_tracing()
    assert status["otel"] is True


@pytest.mark.unit
def test_workflow_entry_points_wired() -> None:
    """Run decorators + configure calls are present on all three entry points."""
    from pathlib import Path

    from digigraph import workflow as workflow_mod

    text = Path(workflow_mod.__file__).read_text()
    # One @trace_run decorator per entry point (invoke / via-stream / streaming).
    assert text.count("@trace_run") == 3
    assert text.count("configure_langgraph_tracing()") >= 3
    for fn_name in (
        "run_digigraph_workflow",
        "run_digigraph_workflow_via_stream",
        "run_digigraph_workflow_streaming",
    ):
        fn = getattr(workflow_mod, fn_name)
        assert fn.__name__ == fn_name
