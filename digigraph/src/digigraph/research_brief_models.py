"""Structured research brief: themes, citations, and quant hand-off hints (Pydantic v2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Theme(BaseModel):
    label: str = Field(..., min_length=1)
    summary: str = ""
    source_ids: list[str] = Field(default_factory=list)


class CitationRef(BaseModel):
    source_id: str
    title_hint: str | None = None


class ResearchBrief(BaseModel):
    """Synthesis grounded in RAG source_ids; no live performance claims."""

    themes: list[Theme] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    corpus_gaps: list[str] = Field(default_factory=list)
    profiling_questions: list[str] = Field(default_factory=list)
    suggested_catalog_strategies: list[str] = Field(default_factory=list)
    strategy_out_of_catalog: bool = False
    suggested_symbols: list[str] = Field(default_factory=list)
    suggested_strategy_params: dict[str, Any] = Field(default_factory=dict)
