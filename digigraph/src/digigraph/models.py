"""Structured I/O for DigiGraph (Pydantic). All outputs are Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowRequest(BaseModel):
    """Input for run_digigraph_workflow (e.g. user idea or backtest request)."""

    prompt: str = Field(..., description="User idea, e.g. 'Build me a mean-reversion stat-arb on tech'")
    session_id: str | None = Field(None, description="Optional session for checkpointing (Phase 1)")


class WorkflowResult(BaseModel):
    """Result of run_digigraph_workflow. Phase 0: backtest result only."""

    success: bool = Field(..., description="Whether the workflow completed successfully")
    message: str = Field("", description="Human-readable summary")
    backtest_result: dict | None = Field(None, description="DigiQuant BacktestResult when workflow ran a backtest")
