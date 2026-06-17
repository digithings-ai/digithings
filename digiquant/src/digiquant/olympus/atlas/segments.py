"""Shared segment output-model primitives.

Every phase 1–5 segment produces a structured report; the shape has a common
core (segment, date, bias, headline, findings, sources, notes) plus
segment-specific extensions. Those extensions live with their phase modules;
this file defines the reusable core.

Kept minimal on purpose — the legacy Atlas system does not have strict
per-segment schemas beyond the overall digest/delta contracts in
``templates/schemas/``. We pick a clean Pydantic shape that makes the LLM's
output deterministic, covers everything the Phase 7 digest synthesis needs
to read, and leaves room for richer per-segment fields in sub-classes.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# Narrow stance vocabulary shared across asset classes / sectors.
# Phase 7 synthesis maps these to the digest's bias row.
Bias = Literal[
    "strong_bullish",
    "bullish",
    "neutral",
    "bearish",
    "strong_bearish",
    "mixed",
]

# Honest grade of the evidence behind a segment read (Pillar 1E). "absent" means no
# material data was available — the analyst should set it (with bias "neutral") instead of
# writing a confident "no data" brief; publish suppresses an absent + finding-free segment,
# and Phase 7 synthesis / the PM can discount thin ones.
DataQuality = Literal["high", "medium", "low", "absent"]


# LLM synonym → canonical Bias value. Applied before Pydantic validates the
# Literal so models never hard-fail on reasonable paraphrases (e.g. Gemini
# Flash returning "positive" instead of "bullish").
_BIAS_SYNONYMS: dict[str, str] = {
    "positive": "bullish",
    "negative": "bearish",
    "very_positive": "strong_bullish",
    "strongly_bullish": "strong_bullish",
    "strongly_positive": "strong_bullish",
    "very_negative": "strong_bearish",
    "strongly_bearish": "strong_bearish",
    "strongly_negative": "strong_bearish",
}


class Finding(BaseModel):
    """One material finding produced by a segment analyst."""

    label: str = Field(
        description="Short noun phrase labeling the finding (e.g. 'Breakout above 200-DMA')",
    )
    summary: str = Field(
        description="1-3 sentence description in analyst voice. Quantified where possible.",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Source IDs from the sources list this finding cites.",
    )


class Source(BaseModel):
    """One source cited by the segment's findings."""

    id: str = Field(description="Stable identifier used by Finding.source_ids")
    title: str | None = Field(default=None)
    url: str | None = Field(default=None)


class SegmentReport(BaseModel):
    """Common shape for Phase 1–5 segment reports.

    Phase-specific sub-classes add structured metrics (sentiment scores,
    flow direction, yield curve shape, etc.). Phase 7 synthesis reads only
    the fields here when assembling the master digest, so downstream
    consumers never depend on segment-specific extensions.
    """

    segment: str = Field(
        description="Stable segment slug, e.g. 'alt-sentiment-news', 'macro'.",
    )
    date: _date
    bias: Bias
    headline: str = Field(
        description="One-sentence executive summary; the strongest single signal today.",
    )
    material_findings: list[Finding] = Field(
        default_factory=list,
        description="Material findings, ordered by importance.",
    )
    sources: list[Source] = Field(
        default_factory=list,
        description="Every source referenced by findings.source_ids.",
    )
    notes: str = Field(
        default="",
        description="Free-form analyst notes — uncertainty, contradictions, regime caveats.",
    )
    data_quality: DataQuality | None = Field(
        default=None,
        description=(
            "Honest grade of the evidence behind this read: 'high'/'medium'/'low' when real "
            "data (prices, technicals, macro, retrieved sources) backs it; 'absent' when no "
            "material data was available — set 'absent' with bias 'neutral' rather than "
            "writing a confident brief on nothing."
        ),
    )
    confidence: float | None = Field(
        default=None,
        description="Optional self-rated confidence in the bias/findings, 0.0–1.0.",
    )

    @field_validator("bias", mode="before")
    @classmethod
    def _normalize_bias(cls, v: object) -> object:
        if isinstance(v, str):
            return _BIAS_SYNONYMS.get(v.lower(), v)
        return v

    @field_validator("data_quality", mode="before")
    @classmethod
    def _normalize_data_quality(cls, v: object) -> object:
        """Lower/strip the LLM's grade; an unrecognized value degrades to None so a
        malformed grade never hard-fails the run (it just publishes ungraded). This is
        fully fail-soft — unlike ``bias`` normalization, which only maps known synonyms and
        still rejects truly unknown values."""
        if isinstance(v, str):
            cleaned = v.strip().lower()
            return cleaned if cleaned in ("high", "medium", "low", "absent") else None
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: object) -> object:
        """Clamp to [0, 1]; a non-numeric value degrades to None (never hard-fail a run)."""
        if v is None:
            return None
        try:
            return max(0.0, min(1.0, float(v)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
