"""Optional agentic layer: composite research turns (install ``digisearch[agent]``)."""

from __future__ import annotations

from typing import Any

__all__ = ["run_research_turn"]


def run_research_turn(initial: dict[str, Any]) -> dict[str, Any]:
    from digisearch.agent.pipeline import run_research_turn as _run

    return _run(initial)
