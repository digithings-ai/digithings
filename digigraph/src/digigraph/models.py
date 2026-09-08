"""Structured I/O for digigraph (Pydantic). All outputs are Pydantic models."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _coerce_openai_message_content(v: Any) -> str:
    """Normalize OpenAI-style message content (AI SDK sends list of {type,text} parts)."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        parts: list[str] = []
        for block in v:
            if isinstance(block, dict):
                t = block.get("type")
                if t == "text" and "text" in block:
                    parts.append(str(block.get("text") or ""))
                elif "text" in block:
                    parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    if isinstance(v, dict) and "text" in v:
        return str(v.get("text") or "")
    return str(v)


# OpenAI-compatible chat (for model exposure in Open WebUI)
class ChatMessage(BaseModel):
    """OpenAI-style message."""

    model_config = {"extra": "ignore"}

    role: str = Field(..., description="user, assistant, or system")
    content: Annotated[str, BeforeValidator(_coerce_openai_message_content)] = Field(
        "", description="Message content (string or OpenAI/AI SDK part list)"
    )


class ChatCompletionRequest(BaseModel):
    """OpenAI POST /v1/chat/completions request."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field("digigraph-rag", description="Model id (ignored; we use project config)")
    messages: list[ChatMessage] = Field(..., description="Conversation messages")
    stream: bool = Field(False, description="If true, return SSE stream")
    openwebui_format: bool = Field(
        False,
        description=(
            "If true, format tool blocks for Open WebUI (<details>, summary + tables). "
            "Also enabled by X-Response-Format: openwebui. model=digigraph-rag alone does "
            "not enable this; opt out anytime via X-Suppress-Tool-Stream or "
            "X-Response-Format: plain|neutral|none|digichat."
        ),
    )
    session_id: str | None = Field(
        None,
        description="Optional conversation/session id. Isolates digistore and checkpoint state per conversation. Also set via X-Session-Id or X-Thread-Id header.",
    )
    allowed_tools: list[str] | None = Field(
        None,
        description="Optional tool allowlist for this completion. Overrides project/env when set. Also accepted via X-Allowed-Tools header (comma-separated).",
    )
    require_tool_calls: bool | None = Field(
        None,
        description=(
            "Optional per-request signal that this completion needs tool_choice='required'. "
            "Also accepted via X-Require-Tool-Calls header. Combined with project "
            "agents.require_tool_calls and env DIGI_REQUIRE_TOOL_CALLS as a FLOOR (any true "
            "value wins) — unlike allowed_tools, this can only raise the requirement, never "
            "lower one the deployment already mandates."
        ),
    )
    force_tool: str | None = Field(
        None,
        description=(
            "Optional per-request locate tool to run with the user string as its query. "
            "Also accepted via X-Digi-Force-Tool. Aliases: search/digisearch, "
            "docs/digivault. Injected — the model is not asked to write the query."
        ),
    )
    enable_web_search: bool = Field(
        False,
        description=(
            "Opt-in public web search via the digigraph ``web_search`` tool (digillm). "
            "Default off — corpus-only. Also accepted via X-Digi-Enable-Web-Search. "
            "When off, the model must not call web; when on, External cites supplement "
            "vault/search hits and never replace them (#3420)."
        ),
    )


class WorkflowRequest(BaseModel):
    """Input for run_digigraph_workflow (e.g. user idea or backtest request)."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(
        ..., description="User idea, e.g. 'Build me a mean-reversion stat-arb on tech'"
    )
    session_id: str | None = Field(None, description="Optional session for checkpointing (Phase 1)")
    request_id: str | None = Field(
        None,
        description=(
            "Correlates audit logs and outbound HTTP (X-Request-ID). "
            "Set from X-Request-ID on HTTP or generated for MCP."
        ),
    )
    allowed_tools: list[str] | None = Field(
        None,
        description=(
            "Optional allowlist of orchestrator tool names. When set (including []), overrides "
            "project agents.allowed_tools and DIGI_ALLOWED_TOOLS. Omit to use those sources."
        ),
    )
    require_tool_calls: bool | None = Field(
        None,
        description=(
            "Optional per-request signal that this workflow needs tool_choice='required'. "
            "Combined with project agents.require_tool_calls and env DIGI_REQUIRE_TOOL_CALLS "
            "as a FLOOR (any true value wins) — unlike allowed_tools, this can only raise the "
            "requirement, never lower one the deployment already mandates."
        ),
    )
    trading_profile: dict[str, Any] | None = Field(
        None,
        description="Optional digiclone profile dict (maps into optimization constraints in graph).",
    )
    strategy_params: dict[str, float | int | str] | None = Field(
        None,
        description="Optional digiquant strategy parameters when skipping LLM extraction.",
    )
    research_filters: list[dict[str, Any]] | None = Field(
        None,
        description="Optional structured digisearch filters merged into every digisearch tool call.",
    )
    digi_bearer: str | None = Field(
        None,
        description="digikey-issued JWT forwarded to digiquant/digisearch as Authorization Bearer.",
    )
    digi_trace_key_prefix: str | None = Field(
        None, description="digikey key prefix for audit (optional)."
    )
    digi_trace_tenant: str | None = Field(None, description="Tenant slug for audit (optional).")
    digi_trace_project_id: str | None = Field(None, description="Project id for audit (optional).")
    digi_trace_jti: str | None = Field(None, description="JWT jti for audit (optional).")
    digi_subject: str | None = Field(
        None,
        description=(
            "JWT subject for checkpoint thread scoping and Store namespace keying. "
            "Client-writable on this model but never trusted as-is: server.py's "
            "_with_digi_request_context/_digi_fields_from_request unconditionally "
            "overwrite this field with the verified auth.subject when request auth "
            "carries a non-empty subject, and clear it to None otherwise (no auth at "
            "all, or an auth object with an empty subject claim) — a client-supplied "
            "value never reaches graph state or the Store namespace key unverified. "
            "See ARCHITECTURE.md §6.10."
        ),
    )
    digisearch_index: str | None = Field(
        None,
        title="digisearch index",
        description=(
            "Per-request digisearch index. Client-writable on this model but, when "
            "DIGI_TENANT_CORPUS_MAP is set, overwritten server-side from the "
            "authenticated tenant's map entry (headers/body cannot select another "
            "tenant's corpus). When the map is unset, X-Digi-Corpus-Index may set it."
        ),
    )
    vault_path_prefix: str | None = Field(
        None,
        description=(
            "Per-request digivault path prefix. Same trust rule as digisearch_index: "
            "map is authoritative when configured; otherwise X-Digi-Vault-Prefix may "
            "set it. digivault also enforces tenant→prefix server-side."
        ),
    )
    research_system_prompt_override: str | None = Field(
        None,
        description="Optional research system prompt from DIGI_TENANT_CORPUS_MAP.",
    )
    response_language: str | None = Field(
        None,
        description=(
            "Per-request response language code (X-Digi-Language). One of the curated "
            "codes in digigraph.languages.LANGUAGE_NAMES; unrecognized values are ignored."
        ),
    )
    evidence_tier_preference: list[str] | None = Field(
        None,
        description="Preferred evidence_tier values (peer_reviewed, working_paper, …) added as a filter.",
    )
    force_tool: str | None = Field(
        None,
        description=(
            "Optional per-request locate tool to run with the user string as its query "
            "(X-Digi-Force-Tool). Aliases: search/digisearch, docs/digivault. The model "
            "is not hinted — the call is injected, then it synthesizes."
        ),
    )
    enable_web_search: bool = Field(
        False,
        description=(
            "Opt-in digigraph ``web_search`` tool (digillm). Default off. "
            "Also via X-Digi-Enable-Web-Search (#3420)."
        ),
    )


class WorkflowResult(BaseModel):
    """Result of run_digigraph_workflow. Phase 0: backtest result only."""

    success: bool = Field(..., description="Whether the workflow completed successfully")
    message: str = Field("", description="Human-readable summary")
    error_code: str | None = Field(
        default=None,
        description="Stable machine code for digichat (e.g. free_quota_exceeded); None on success",
    )
    backtest_result: dict | None = Field(
        None, description="digiquant BacktestResult when workflow ran a backtest"
    )
    optimize_result: dict | None = Field(
        default=None, description="digiquant OptimizeResult when optimize step ran"
    )
    optimize_error: str | None = Field(
        default=None, description="Error from optimize step without failing whole workflow"
    )
    research_brief: dict[str, Any] | None = Field(
        default=None, description="Structured research brief when research subgraph produced one"
    )
    rag_sources: list[dict[str, Any]] | None = Field(
        default=None, description="Aggregated digisearch citations from the research step"
    )
    profiling_questions: list[str] | None = Field(
        default=None, description="Merged profiling questions (brief + trading profile gaps)"
    )


class ResumeThreadRequest(BaseModel):
    """Body for POST /threads/{thread_id}/resume."""

    model_config = ConfigDict(extra="forbid")

    resume: Any | None = Field(
        default=None,
        description="Value passed to LangGraph Command(resume=...). Omit for a plain re-invoke.",
    )


class LLMResult(BaseModel):
    """Typed result from an LLM completion call. Replaces bare str | tuple return types."""

    content: str = Field("", description="Text content returned by the model")
    tool_calls: list[dict] | None = Field(
        None, description="Tool calls requested by the model, if any"
    )

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)
