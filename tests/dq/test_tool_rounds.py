"""OLYMPUS_MAX_TOOL_ROUNDS wiring: default 24, env override, thin wrapper (#3299)."""

from __future__ import annotations

from typing import Any  # score:allow untyped any — captured mock kwargs dict
from unittest.mock import patch

import pytest
from digigraph.graph import research_agent as _research_agent_module
from digiquant.tool_rounds import (
    OLYMPUS_MAX_TOOL_ROUNDS_ENV,
    olympus_max_tool_rounds,
    run_olympus_research_agent,
)
from pydantic import BaseModel

pytestmark = pytest.mark.unit


class _Out(BaseModel):
    headline: str = ""


def test_default_is_24(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(OLYMPUS_MAX_TOOL_ROUNDS_ENV, raising=False)
    assert olympus_max_tool_rounds() == 24


def test_env_override_and_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_MAX_TOOL_ROUNDS_ENV, "8")
    assert olympus_max_tool_rounds() == 8
    monkeypatch.setenv(OLYMPUS_MAX_TOOL_ROUNDS_ENV, "0")
    assert olympus_max_tool_rounds() == 1


def test_invalid_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_MAX_TOOL_ROUNDS_ENV, "lots")
    assert olympus_max_tool_rounds() == 24


def test_wrapper_injects_default_rounds() -> None:
    seen: dict[str, Any] = {}

    def _fake(**kwargs: Any) -> _Out:
        seen.update(kwargs)
        return _Out(headline="ok")

    with patch.object(_research_agent_module, "run_research_agent", _fake):
        out = run_olympus_research_agent(
            skill_text="s",
            phase_inputs={},
            shared_context={},
            output_model=_Out,
        )
    assert out.headline == "ok"
    assert seen["max_tool_rounds"] == 24


def test_wrapper_respects_explicit_rounds() -> None:
    seen: dict[str, Any] = {}

    def _fake(**kwargs: Any) -> _Out:
        seen.update(kwargs)
        return _Out(headline="ok")

    with patch.object(_research_agent_module, "run_research_agent", _fake):
        run_olympus_research_agent(
            skill_text="s",
            phase_inputs={},
            shared_context={},
            output_model=_Out,
            max_tool_rounds=4,
        )
    assert seen["max_tool_rounds"] == 4
