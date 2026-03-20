"""Structured I/O for DigiGraph (Pydantic). All outputs are Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, Field


# OpenAI-compatible chat (for model exposure in Open WebUI)
class ChatMessage(BaseModel):
    """OpenAI-style message."""

    role: str = Field(..., description="user, assistant, or system")
    content: str = Field("", description="Message content")


class ChatCompletionRequest(BaseModel):
    """OpenAI POST /v1/chat/completions request."""

    model_config = {"extra": "ignore"}

    model: str = Field("sitaas-rag", description="Model id (ignored; we use project config)")
    messages: list[ChatMessage] = Field(..., description="Conversation messages")
    stream: bool = Field(False, description="If true, return SSE stream")
    openwebui_format: bool = Field(
        False,
        description="If true, format tool blocks for Open WebUI (<details type=\"tool_calls\">, summary + Input/Output). Optional; also enabled when model is sitaas-rag.",
    )
    session_id: str | None = Field(
        None,
        description="Optional conversation/session id. Isolates digistore and checkpoint state per conversation. Also set via X-Session-Id or X-Thread-Id header.",
    )


class WorkflowRequest(BaseModel):
    """Input for run_digigraph_workflow (e.g. user idea or backtest request)."""

    prompt: str = Field(..., description="User idea, e.g. 'Build me a mean-reversion stat-arb on tech'")
    session_id: str | None = Field(None, description="Optional session for checkpointing (Phase 1)")


class WorkflowResult(BaseModel):
    """Result of run_digigraph_workflow. Phase 0: backtest result only."""

    success: bool = Field(..., description="Whether the workflow completed successfully")
    message: str = Field("", description="Human-readable summary")
    backtest_result: dict | None = Field(None, description="DigiQuant BacktestResult when workflow ran a backtest")


class LLMResult(BaseModel):
    """Typed result from an LLM completion call. Replaces bare str | tuple return types."""

    content: str = Field("", description="Text content returned by the model")
    tool_calls: list[dict] | None = Field(None, description="Tool calls requested by the model, if any")

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)
