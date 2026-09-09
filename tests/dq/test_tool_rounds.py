"""OLYMPUS_MAX_TOOL_ROUNDS wiring: default 24, env override, thin wrapper (#3299)."""

from __future__ import annotations

import sys
import types
from typing import Any  # score:allow untyped any — captured mock kwargs dict

import pytest
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


def _install_stub_agent(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub ``digigraph.graph.research_agent`` in sys.modules.

    The wrapper imports it lazily per call; stubbing keeps this test hermetic
    in lanes whose venv lacks the full digigraph import chain (e.g. no
    ``openai`` in the digiquant lane). ``monkeypatch`` reverts everything.
    """
    seen: dict[str, Any] = {}
    pkg = types.ModuleType("digigraph")
    pkg.__path__ = []  # type: ignore[attr-defined]
    sub = types.ModuleType("digigraph.graph")
    sub.__path__ = []  # type: ignore[attr-defined]
    mod = types.ModuleType("digigraph.graph.research_agent")

    def _fake(**kwargs: Any) -> _Out:
        seen.update(kwargs)
        return _Out(headline="ok")

    mod.run_research_agent = _fake  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "digigraph", pkg)
    monkeypatch.setitem(sys.modules, "digigraph.graph", sub)
    monkeypatch.setitem(sys.modules, "digigraph.graph.research_agent", mod)
    return seen


def test_wrapper_injects_default_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _install_stub_agent(monkeypatch)
    out = run_olympus_research_agent(
        skill_text="s",
        phase_inputs={},
        shared_context={},
        output_model=_Out,
    )
    assert out.headline == "ok"
    assert seen["max_tool_rounds"] == 24


def test_wrapper_respects_explicit_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _install_stub_agent(monkeypatch)
    run_olympus_research_agent(
        skill_text="s",
        phase_inputs={},
        shared_context={},
        output_model=_Out,
        max_tool_rounds=4,
    )
    assert seen["max_tool_rounds"] == 4
