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

from pydantic import BaseModel, Field


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


class Finding(BaseModel):
    """One material finding produced by a segment analyst."""

    label: str = Field(
        description="Short noun phrase labeling the finding (e.g. 'Breakout above 200-DMA')",
        max_length=120,
    )
    summary: str = Field(
        description="1-3 sentence description in analyst voice. Quantified where possible.",
        max_length=800,
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Source IDs from the sources list this finding cites.",
    )


class Source(BaseModel):
    """One source cited by the segment's findings."""

    id: str = Field(max_length=64, description="Stable identifier used by Finding.source_ids")
    title: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=1000)


class SegmentReport(BaseModel):
    """Common shape for Phase 1–5 segment reports.

    Phase-specific sub-classes add structured metrics (sentiment scores,
    flow direction, yield curve shape, etc.). Phase 7 synthesis reads only
    the fields here when assembling the master digest, so downstream
    consumers never depend on segment-specific extensions.
    """

    segment: str = Field(
        description="Stable segment slug, e.g. 'alt-sentiment-news', 'macro'.",
        max_length=64,
    )
    date: _date
    bias: Bias
    headline: str = Field(
        description="One-sentence executive summary; the strongest single signal today.",
        max_length=280,
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
        max_length=2000,
    )
