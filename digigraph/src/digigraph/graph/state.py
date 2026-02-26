"""Shared state for the Phase 1 workflow graph. TypedDict for LangGraph."""

from __future__ import annotations

from typing import Any, Callable, TypedDict


class WorkflowState(TypedDict, total=False):
    """State passed between supervisor, research, and backtest nodes."""

    prompt: str
    session_id: str | None
    strategy_name: str
    symbols: list[str]
    research_note: str
    research_response: str  # Freeform LLM response (document-search mode)
    backtest_result: dict | None
    error: str | None
    # Streaming only: callback(event_type, data) for tool_call/tool_result. Not serialized.
    stream_callback: Callable[[str, Any], None]
