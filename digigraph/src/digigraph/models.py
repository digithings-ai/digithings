"""Structured I/O for DigiGraph (Pydantic). All outputs are Pydantic models."""

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

    model_config = {"extra": "ignore"}

    model: str = Field("sitaas-rag", description="Model id (ignored; we use project config)")
    messages: list[ChatMessage] = Field(..., description="Conversation messages")
    stream: bool = Field(False, description="If true, return SSE stream")
    openwebui_format: bool = Field(
        False,
        description='If true, format tool blocks for Open WebUI (<details type="tool_calls">, summary + Input/Output). Optional; also enabled when model is sitaas-rag.',
    )
    session_id: str | None = Field(
        None,
        description="Optional conversation/session id. Isolates digistore and checkpoint state per conversation. Also set via X-Session-Id or X-Thread-Id header.",
    )
    allowed_tools: list[str] | None = Field(
        None,
        description="Optional tool allowlist for this completion. Overrides project/env when set. Also accepted via X-Allowed-Tools header (comma-separated).",
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
    trading_profile: dict[str, Any] | None = Field(
        None,
        description="Optional DigiClone profile dict (maps into optimization constraints in graph).",
    )
    strategy_params: dict[str, float | int | str] | None = Field(
        None,
        description="Optional DigiQuant strategy parameters when skipping LLM extraction.",
    )
    research_filters: list[dict[str, Any]] | None = Field(
        None,
        description="Optional structured DigiSearch filters merged into every digisearch tool call.",
    )
    digi_bearer: str | None = Field(
        None,
        description="DigiKey-issued JWT forwarded to DigiQuant/DigiSearch as Authorization Bearer.",
    )
    digi_trace_key_prefix: str | None = Field(
        None, description="DigiKey key prefix for audit (optional)."
    )
    digi_trace_tenant: str | None = Field(None, description="Tenant slug for audit (optional).")
    digi_trace_project_id: str | None = Field(None, description="Project id for audit (optional).")
    digi_trace_jti: str | None = Field(None, description="JWT jti for audit (optional).")
    evidence_tier_preference: list[str] | None = Field(
        None,
        description="Preferred evidence_tier values (peer_reviewed, working_paper, …) added as a filter.",
    )


class WorkflowResult(BaseModel):
    """Result of run_digigraph_workflow. Phase 0: backtest result only."""

    success: bool = Field(..., description="Whether the workflow completed successfully")
    message: str = Field("", description="Human-readable summary")
    backtest_result: dict | None = Field(
        None, description="DigiQuant BacktestResult when workflow ran a backtest"
    )
    optimize_result: dict | None = Field(
        default=None, description="DigiQuant OptimizeResult when optimize step ran"
    )
    optimize_error: str | None = Field(
        default=None, description="Error from optimize step without failing whole workflow"
    )
    research_brief: dict[str, Any] | None = Field(
        default=None, description="Structured research brief when research subgraph produced one"
    )
    rag_sources: list[dict[str, Any]] | None = Field(
        default=None, description="Aggregated DigiSearch citations from the research step"
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
