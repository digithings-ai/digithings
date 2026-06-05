"""Structured research brief: themes, citations, and quant hand-off hints (Pydantic v2)."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

BRIEF_SYSTEM = """You write a machine-readable research brief as a single JSON object (no markdown).
Rules:
- Do not state backtest results, Sharpe ratios, returns, win rates, or any performance metrics unless the user prompt explicitly quotes them from a source. The corpus is literature and notes, not live DigiQuant output.
- Every theme.summary must only restate ideas that are supported by Retrieved sources. Each theme MUST include source_ids: a non-empty array of ids from ALLOWED_SOURCE_IDS. If you lack evidence for a theme, put the idea in corpus_gaps instead.
- If sources disagree, add short strings to contradictions.
- assumptions: operational facts the literature often leaves implicit (e.g. futures roll policy, fee model) — not invented statistics.
- profiling_questions: concrete questions the user should answer before running serious backtests (instrument, horizon, leverage, roll rules).
- suggested_catalog_strategies: snake_case strategy family names that might exist in a systematic catalog; use [] and set strategy_out_of_catalog true if none fit.
- suggested_symbols: uppercase tickers or continuous symbols only when justified by the user prompt or sources; otherwise [].
- suggested_strategy_params: flat string/number map only when clearly implied; else {}.

JSON shape (all keys required; use [] or {} for empty collections):
{
  "themes": [{"label": "", "summary": "", "source_ids": []}],
  "contradictions": [],
  "assumptions": [],
  "corpus_gaps": [],
  "profiling_questions": [],
  "suggested_catalog_strategies": [],
  "strategy_out_of_catalog": false,
  "suggested_symbols": [],
  "suggested_strategy_params": {}
}
"""


def strip_json_fence(raw: str) -> str:
    """Remove optional markdown code fences from an LLM JSON payload."""
    s = re.sub(r"^```(?:json)?\s*", "", (raw or "").strip()).strip()
    return re.sub(r"\s*```$", "", s).strip()


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


def parse_brief_from_llm(raw: str) -> ResearchBrief:
    """Parse and validate a :class:`ResearchBrief` from raw LLM output (SIMP-034)."""
    return ResearchBrief.model_validate(json.loads(strip_json_fence(raw)))
