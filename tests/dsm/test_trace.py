"""Unit tests for digismith.trace."""

from __future__ import annotations

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
