"""Grounding models for the Phase B web research branch (#4064).

``GroundingCitation`` is a re-export of the landed shared atom
``digisearch.web_search.citation.Citation`` (single shape, never a fork).
"""

# score:allow untyped any
# JSON-schema payload containers at the model boundary are dynamic; Any is the honest annotation.

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from digisearch.web_search.citation import Citation as GroundingCitation

__all__ = [
    "EFFORT_PRESETS",
    "Confidence",
    "EffortMode",
    "FieldGrounding",
    "GroundingCitation",
    "StructuredSynthesis",
    "TurnCost",
    "TurnUsage",
    "WebResearchConfig",
    "WebResearchError",
]


class Confidence(str, Enum):
    """Model-assigned confidence for one grounded field."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"


class EffortMode(str, Enum):
    """Web research budget preset selector."""

    FAST = "fast"
    THOROUGH = "thorough"


class FieldGrounding(BaseModel):
    """Citations supporting one field of a structured synthesis."""

    model_config = ConfigDict(extra="forbid")

    field: str
    citations: list[GroundingCitation] = Field(min_length=1)
    confidence: Confidence = Confidence.HIGH


class StructuredSynthesis(BaseModel):
    """Structured answer content plus per-field grounding."""

    model_config = ConfigDict(extra="forbid")

    content: dict[str, Any]
    text: str = ""
    grounding: list[FieldGrounding] = Field(default_factory=list)


class WebResearchConfig(BaseModel):
    """Resolved web research budget/effort configuration."""

    model_config = ConfigDict(extra="forbid")

    effort: EffortMode = EffortMode.FAST
    live_top_n: int = 8
    fetch_top_n: int = 5
    cited_top_n: int = 5
    synthesis_model: str = ""
    max_synthesis_chars: int = 12000


EFFORT_PRESETS: dict[EffortMode, WebResearchConfig] = {
    EffortMode.FAST: WebResearchConfig(
        effort=EffortMode.FAST, live_top_n=8, fetch_top_n=5, cited_top_n=5
    ),
    EffortMode.THOROUGH: WebResearchConfig(
        effort=EffortMode.THOROUGH, live_top_n=20, fetch_top_n=10, cited_top_n=8
    ),
}


class TurnUsage(BaseModel):
    """Per-turn web research usage counters (mirrors EXA usage shape)."""

    model_config = ConfigDict(extra="forbid")

    searches: int = 0
    pages_fetched: int = 0
    pages_cited: int = 0
    llm_calls: int = 0
    search_ms: int = 0
    fetch_ms: int = 0
    rerank_ms: int = 0
    synthesis_ms: int = 0
    total_ms: int = 0


class TurnCost(BaseModel):
    """Advisory per-turn web research cost (mirrors EXA costDollars shape).

    ``total`` is advisory-only: OSS web research has no metered dollar cost,
    so budget/routing gates MUST also consult stage-ms and, when
    ``breakdown["llm_calls"] > 0``, digillm telemetry.
    """

    model_config = ConfigDict(extra="forbid")

    total: float = 0.0
    provider: str = "web-oss"
    breakdown: dict[str, int] = Field(default_factory=dict)
    note: str = "oss-synthesis; llm spend metered in digillm telemetry, not here"


class WebResearchError(RuntimeError):
    """Any web research dependency failure (fail-hard, never uncited)."""
