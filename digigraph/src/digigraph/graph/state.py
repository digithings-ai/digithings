"""Shared LangGraph state for the Phase 1 workflow graph."""

from __future__ import annotations

from typing import Any, TypedDict


class WorkflowState(TypedDict, total=False):
    """LangGraph state; input keys from :class:`digigraph.models.WorkflowRequest` via ``workflow._initial_graph_state``.

    N/A (wave 7i / SIMP-001): LangGraph checkpoints require JSON-serializable ``dict`` slots;
    Pydantic workflow I/O lives in ``models.py`` — TypedDict overlap is intentional.
    """

    prompt: str
    session_id: str | None
    request_id: str | None
    workflow_id: str | None
    # Forward digikey JWT (or legacy API key) to digiquant / digisearch HTTP clients.
    digi_bearer: str | None
    # Sorted list of allowed orchestrator tool names; None = unrestricted.
    allowed_tool_names: list[str] | None
    strategy_name: str
    symbols: list[str]
    # Optional parameters passed to digiquant run_backtest (from research extraction or user).
    strategy_params: dict[str, Any]
    # Optional user/tenant trading profile (Phase F); merged into optimization_constraints when set.
    trading_profile: dict[str, Any]
    research_note: str
    research_response: str  # Freeform LLM response (document-search mode)
    # Aggregated digisearch citations + structured brief (research / ideation tier).
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
    # Opaque URI from digiquant/export (Phase 2 artifact contract); workflow stores refs not blobs.
    quant_artifact_uri: str | None
    error: str | None
    # Stable digichat contract code (e.g. free_quota_exceeded); set with error.
    error_code: str | None
    # Session datasets: ref -> { ref, profile }. No reducer; last writer wins per key.
    stored_datasets: dict[str, dict[str, Any]]
    # Workflow profile: full_stack | research_rag | quant_backtest | plan_execute (set at invoke).
    workflow_profile: str
    # Per-request corpus routing (X-Digi-Corpus-Index / X-Digi-Vault-Prefix / DIGI_TENANT_CORPUS_MAP).
    # Must be declared here — LangGraph StateGraph(WorkflowState) drops undeclared keys, which
    # silently ignored OCC occ_help overrides and left digisearch on digiproject default index.
    digisearch_index: str | None
    vault_path_prefix: str | None
    research_system_prompt_override: str | None
    # Per-request response language (X-Digi-Language). Must be declared here — see the
    # digisearch_index/vault_path_prefix comment above; same LangGraph pitfall (#2097).
    response_language: str | None
    # Optional supervisor / routing (when DIGI_SUPERVISOR=1).
    supervisor_depth_remaining: int
    supervisor_route: str | None
    # Subject (JWT sub / digikey identity, when auth supplies one) for cross-thread
    # Store lookups (see graph.get_store()). Falsy (None/empty) skips store lookups
    # entirely rather than keying on a placeholder -- but this is a client-writable
    # field (models.py's WorkflowRequest.digi_subject), only overridden server-side
    # when request auth carries a subject; an unauthenticated/dev request's own value
    # is not verified. See ARCHITECTURE.md §6.10.
    digi_subject: str | None
