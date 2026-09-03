"""Tool-round budget for digiquant research-agent calls (#3299).

Cheap-model JSON needs room for data-tool grounding before Pydantic
validation. Default 24; override via ``OLYMPUS_MAX_TOOL_ROUNDS`` (also set in
``.github/digiquant-pipeline.yml``). digigraph chat keeps its own
``max_tool_rounds=4`` — do not reuse this there.
"""

from __future__ import annotations

import logging
import os
from typing import (  # score:allow untyped any — heterogeneous LLM message/tool-arg dicts
    Any,
    Callable,
    TypeVar,
)

from pydantic import BaseModel

logger = logging.getLogger(__name__)

OLYMPUS_MAX_TOOL_ROUNDS_ENV = "OLYMPUS_MAX_TOOL_ROUNDS"
_DEFAULT_MAX_TOOL_ROUNDS = 24

T = TypeVar("T", bound=BaseModel)


def olympus_max_tool_rounds() -> int:
    """Return the digiquant tool-round cap (default 24, minimum 1)."""
    raw = os.environ.get(OLYMPUS_MAX_TOOL_ROUNDS_ENV, "").strip()
    if not raw:
        return _DEFAULT_MAX_TOOL_ROUNDS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "invalid %s=%r; using default %d",
            OLYMPUS_MAX_TOOL_ROUNDS_ENV,
            raw,
            _DEFAULT_MAX_TOOL_ROUNDS,
        )
        return _DEFAULT_MAX_TOOL_ROUNDS
    return max(value, 1)


def run_olympus_research_agent(
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
    """Thin digiquant wrapper around digigraph's ``run_research_agent``.

    Injects ``OLYMPUS_MAX_TOOL_ROUNDS`` (default 24) unless the caller passes
    an explicit ``max_tool_rounds``. Digigraph chat stays at ``max_tool_rounds=4``.
    """
    from digigraph.graph.research_agent import run_research_agent

    return run_research_agent(
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
        max_tool_rounds=max_tool_rounds
        if max_tool_rounds is not None
        else olympus_max_tool_rounds(),
    )


__all__ = [
    "OLYMPUS_MAX_TOOL_ROUNDS_ENV",
    "olympus_max_tool_rounds",
    "run_olympus_research_agent",
]
