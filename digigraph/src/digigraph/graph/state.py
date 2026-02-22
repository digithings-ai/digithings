"""Shared state for the Phase 1 workflow graph. TypedDict for LangGraph."""

from __future__ import annotations

from typing import TypedDict


class WorkflowState(TypedDict, total=False):
    """State passed between supervisor, research, and backtest nodes."""

    prompt: str
    session_id: str | None
    strategy_name: str
    symbols: list[str]
    research_note: str
    backtest_result: dict | None
    error: str | None
