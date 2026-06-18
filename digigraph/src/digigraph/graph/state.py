"""Shared LangGraph state for the Phase 1 workflow graph."""

from __future__ import annotations

from typing import Any, Callable, TypedDict


class WorkflowState(TypedDict, total=False):
    """LangGraph state; input keys from :class:`digigraph.models.WorkflowRequest` via ``workflow._initial_graph_state``.

    N/A (wave 7i / SIMP-001): LangGraph checkpoints require JSON-serializable ``dict`` slots;
    Pydantic workflow I/O lives in ``models.py`` — TypedDict overlap is intentional.
    """

    prompt: str
    session_id: str | None
    request_id: str | None
    workflow_id: str | None
    # Forward DigiKey JWT (or legacy API key) to DigiQuant / DigiSearch HTTP clients.
    digi_bearer: str | None
    # Sorted list of allowed orchestrator tool names; None = unrestricted.
    allowed_tool_names: list[str] | None
    strategy_name: str
    symbols: list[str]
    # Optional parameters passed to DigiQuant run_backtest (from research extraction or user).
    strategy_params: dict[str, Any]
    # Optional user/tenant trading profile (Phase F); merged into optimization_constraints when set.
    trading_profile: dict[str, Any]
    research_note: str
    research_response: str  # Freeform LLM response (document-search mode)
    # Aggregated DigiSearch citations + structured brief (research / ideation tier).
    rag_sources: list[dict[str, Any]]
    research_brief: dict[str, Any]
    profiling_questions: list[str]
    research_filters: list[dict[str, Any]]
    evidence_tier_preference: list[str]
    backtest_result: dict | None
    backtest_job_id: str | None
    optimize_result: dict | None
    optimize_error: str | None
    optimization_constraints: dict[str, Any]
    # Opaque URI from DigiQuant/export (Phase 2 artifact contract); workflow stores refs not blobs.
    quant_artifact_uri: str | None
    error: str | None
    # Session datasets: ref -> { ref, profile }. No reducer; last writer wins per key.
    stored_datasets: dict[str, dict[str, Any]]
    # Streaming only: callback(event_type, data). Not serialized; request-scoped.
    stream_callback: Callable[[str, Any], None]
    # Workflow profile: full_stack | research_rag | quant_backtest | plan_execute (set at invoke).
    workflow_profile: str
    # Optional supervisor / routing (when DIGI_SUPERVISOR=1).
    supervisor_depth_remaining: int
    supervisor_route: str | None
