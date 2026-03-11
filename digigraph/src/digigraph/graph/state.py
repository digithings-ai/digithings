"""Shared state for the Phase 1 workflow graph. TypedDict for LangGraph."""

from __future__ import annotations

from typing import Any, Callable, TypedDict


class WorkflowState(TypedDict, total=False):
    """State passed between supervisor, research, and backtest nodes.

    State keys have no reducers: last writer wins. When parallel or accumulating
    updates are added, use Annotated reducers for those keys (see LANGGRAPH_REVIEW.md).
    stream_callback is not serialized by the checkpointer; streaming is request-scoped only.
    """

    prompt: str
    session_id: str | None
    strategy_name: str
    symbols: list[str]
    research_note: str
    research_response: str  # Freeform LLM response (document-search mode)
    backtest_result: dict | None
    error: str | None
    # Session datasets: ref -> { ref, profile }. No reducer; last writer wins per key.
    stored_datasets: dict[str, dict[str, Any]]
    # Streaming only: callback(event_type, data). Not serialized; request-scoped.
    stream_callback: Callable[[str, Any], None]
