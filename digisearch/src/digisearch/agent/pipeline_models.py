"""Pydantic models for the DigiSearch research-turn LangGraph (SIMP-019/020)."""

from __future__ import annotations

from operator import add
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class ResearchTurnTraceStep(BaseModel):
    """One research-turn trace entry."""

    model_config = ConfigDict(extra="forbid")

    step: str
    status: str
    service: str | None = None
    detail: str | None = None
    total: int | None = None


class ResearchTurnState(BaseModel):
    """LangGraph state for plan → retrieve → aggregate (SIMP-019)."""

    model_config = ConfigDict(extra="forbid")

    user_message: str = ""
    index_name: str = "default"
    top_k: int = 10
    mode: str = "hybrid"
    filter: str | None = None
    filters: list[dict[str, Any]] | None = None
    session_id: str | None = None
    service: str = "digisearch"
    trace: Annotated[list[ResearchTurnTraceStep], add] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    backend: str | None = None
    rag_sources: list[dict[str, Any]] = Field(default_factory=list)
    formatted_context: str = ""
    error: str | None = None


class ResearchTurnOutput(BaseModel):
    """HTTP/MCP payload for one research turn (SIMP-019/020)."""

    service: str = "digisearch"
    error: str | None = None
    trace: list[ResearchTurnTraceStep] = Field(default_factory=list)
    query: str | None = None
    index_name: str | None = None
    total: int = 0
    backend: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    rag_sources: list[dict[str, Any]] = Field(default_factory=list)
    formatted_context: str = ""
