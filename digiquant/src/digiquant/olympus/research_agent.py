"""Olympus-bound research agent: injects the tool-round budget (#3299)."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar  # score:allow untyped any — matches digigraph run_research_agent

from digigraph.graph import research_agent as _research_agent_mod
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_MAX_TOOL_ROUNDS = 24


def olympus_max_tool_rounds() -> int:
    """Hard cap on tool-calling rounds per Olympus LLM turn.

    Default 24 — high enough that a 30-analyst roster can finish
    ``get_macro_series`` / ``get_etf_flows_proxy``; still finite so a stuck
    loop cannot unbounded-bill. Override with ``OLYMPUS_MAX_TOOL_ROUNDS``
    (positive int). Invalid or empty values fall back to the default.
    """
    raw = os.environ.get("OLYMPUS_MAX_TOOL_ROUNDS", "").strip()
    if not raw:
        return DEFAULT_MAX_TOOL_ROUNDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_TOOL_ROUNDS
    return value if value > 0 else DEFAULT_MAX_TOOL_ROUNDS


def run_research_agent(
    *,
    skill_text: str,
    phase_inputs: dict[str, Any],
    shared_context: dict[str, Any],
    output_model: type[T],
    model: str | None = None,
    phase_slug: str | None = None,
    temperature: float = 0.1,
    max_retries: int = 1,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    execute_tool: Callable[[str, dict[str, Any]], str] | None = None,
    search_parameters: dict[str, Any] | None = None,
    max_tool_rounds: int | None = None,
) -> T:
    """Call digigraph's research agent with Olympus's tool-round budget."""
    rounds = olympus_max_tool_rounds() if max_tool_rounds is None else max_tool_rounds
    return _research_agent_mod.run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=shared_context,
        output_model=output_model,
        model=model,
        phase_slug=phase_slug,
        temperature=temperature,
        max_retries=max_retries,
        max_tokens=max_tokens,
        tools=tools,
        execute_tool=execute_tool,
        search_parameters=search_parameters,
        max_tool_rounds=rounds,
    )
