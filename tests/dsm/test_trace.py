"""Unit tests for digismith.trace."""

from __future__ import annotations

from typing import Any

import pytest

from digismith import trace as trace_mod


@pytest.mark.unit
def test_traceable_no_op_when_sdk_not_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trace_mod, "LANGSMITH_SDK_AVAILABLE", False)
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")

    @trace_mod.traceable("demo")
    def fn() -> int:
        return 42

    assert fn() == 42
    assert fn.__name__ == "fn"


@pytest.mark.unit
def test_traceable_no_op_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    @trace_mod.traceable("demo2")
    def fn2() -> str:
        return "x"

    assert fn2() == "x"


@pytest.mark.unit
def test_traceable_passes_redaction_hooks_to_langsmith(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When tracing is active, redactor hooks must reach langsmith.traceable."""
    captured: dict[str, Any] = {}

    def fake_traceable(**kwargs: Any):
        captured.update(kwargs)

        def wrap(fn):
            return fn

        return wrap

    class FakeLs:
        traceable = staticmethod(fake_traceable)

    monkeypatch.setattr(trace_mod, "LANGSMITH_SDK_AVAILABLE", True)
    monkeypatch.setattr(trace_mod, "_langsmith", FakeLs)
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")

    @trace_mod.traceable("demo3")
    def fn3(x: int) -> int:
        return x + 1

    assert fn3(1) == 2
    assert captured["name"] == "demo3"
    assert callable(captured["process_inputs"])
    assert callable(captured["process_outputs"])
    # Hooks must actually redact.
    assert captured["process_inputs"]({"email": "u@e.co"}) == {"email": "[REDACTED_EMAIL]"}
    assert captured["process_outputs"]("sk-abcdefghij1234567") == "[REDACTED_KEY]"


@pytest.mark.unit
def test_traceable_falls_back_when_process_kwargs_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older langsmith SDKs without process_inputs kwarg still decorate."""
    calls: list[dict[str, Any]] = []

    def fake_traceable(**kwargs: Any):
        calls.append(kwargs)
        if "process_inputs" in kwargs or "process_outputs" in kwargs:
            raise TypeError("unexpected kwarg")

        def wrap(fn):
            return fn

        return wrap

    class FakeLs:
        traceable = staticmethod(fake_traceable)

    monkeypatch.setattr(trace_mod, "LANGSMITH_SDK_AVAILABLE", True)
    monkeypatch.setattr(trace_mod, "_langsmith", FakeLs)
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")

    @trace_mod.traceable("demo4")
    def fn4() -> int:
        return 7

    assert fn4() == 7
    # Two attempts: first with process_* kwargs, then fallback without.
    assert len(calls) == 2
    assert "process_inputs" in calls[0]
    assert "process_inputs" not in calls[1]
