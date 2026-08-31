"""Olympus tool-round budget (#3299)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from digiquant.olympus.research_agent import (
    DEFAULT_MAX_TOOL_ROUNDS,
    olympus_max_tool_rounds,
    run_research_agent,
)
from pydantic import BaseModel

pytestmark = pytest.mark.unit


class _Out(BaseModel):
    ok: bool = True


def test_olympus_max_tool_rounds_defaults_to_24(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLYMPUS_MAX_TOOL_ROUNDS", raising=False)
    assert olympus_max_tool_rounds() == DEFAULT_MAX_TOOL_ROUNDS == 24


def test_olympus_max_tool_rounds_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MAX_TOOL_ROUNDS", "48")
    assert olympus_max_tool_rounds() == 48


@pytest.mark.parametrize("raw", ["", "nope", "0", "-3"])
def test_olympus_max_tool_rounds_invalid_falls_back(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    if raw == "":
        monkeypatch.delenv("OLYMPUS_MAX_TOOL_ROUNDS", raising=False)
    else:
        monkeypatch.setenv("OLYMPUS_MAX_TOOL_ROUNDS", raw)
    assert olympus_max_tool_rounds() == DEFAULT_MAX_TOOL_ROUNDS


def test_wrapper_forwards_budget_to_digigraph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MAX_TOOL_ROUNDS", "24")
    captured: dict[str, object] = {}

    def fake_run(**kwargs: object) -> _Out:
        captured.update(kwargs)
        return _Out()

    with patch("digigraph.graph.research_agent.run_research_agent", side_effect=fake_run):
        out = run_research_agent(
            skill_text="s",
            phase_inputs={},
            shared_context={},
            output_model=_Out,
            model="test-model",
        )
    assert out.ok is True
    assert captured["max_tool_rounds"] == 24
