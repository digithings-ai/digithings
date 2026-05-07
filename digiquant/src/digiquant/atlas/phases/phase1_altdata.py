"""Phase 1 — Alternative data & positioning signals (4-way parallel fan-out).

Four sub-agents run in parallel: sentiment & news, CTA positioning, options
& derivatives, politician signals. Per the orchestrator skill they "inform
everything downstream" — macro and segment reads should be coloured by
positioning and sentiment before they're classified.

Design decision (commit 4): keep four separate Pydantic output models
rather than collapsing into a single discriminated-union model. The four
skills produce genuinely different structured metrics (sentiment scores vs
CTA positioning vs options GEX vs STOCK Act filings); a single model would
require a permissive body that would defeat the structured-output guarantee
we want from run_research_agent. Four small models are clearer and also
give each node its own validation error surface.

Common shape (headline, bias, findings, sources, notes) comes from the
shared :class:`digiquant.atlas.segments.SegmentReport` base.
"""

from __future__ import annotations

from typing import Literal

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant.atlas.phases._node_factory import (
    SegmentNodeSpec,
    build_segment_node,
)
from digiquant.atlas.segments import SegmentReport


class SentimentNewsReport(SegmentReport):
    """Phase 1A — retail + pro sentiment + news catalysts."""

    aaii_bull_bear_spread: float | None = Field(
        default=None,
        description="AAII bulls minus bears; None if not available in today's context.",
    )
    cnn_fear_greed_index: int | None = Field(default=None, ge=0, le=100)
    retail_sentiment_stance: Literal["risk_on", "risk_off", "mixed"] | None = None
    top_catalysts: list[str] = Field(
        default_factory=list,
        description="≤5 short catalyst labels; ordered by significance.",
    )


class CtaPositioningReport(SegmentReport):
    """Phase 1B — systematic trend-follower positioning."""

    systematic_stance: Literal["long", "short", "neutral", "mixed"] | None = None
    futures_oi_trend: Literal["expanding", "contracting", "flat"] | None = None
    cta_flow_bias: Literal["adding", "reducing", "neutral", "mixed"] | None = None


class OptionsDerivativesReport(SegmentReport):
    """Phase 1C — GEX, VIX, dealer positioning."""

    vix_level: float | None = Field(default=None, ge=0)
    vix_term_structure: Literal["contango", "backwardation", "flat"] | None = None
    dealer_gamma: Literal["long", "short", "neutral"] | None = None
    put_call_ratio: float | None = Field(default=None, ge=0)


class PoliticianSignalsReport(SegmentReport):
    """Phase 1D — Congressional trades (STOCK Act) + policy signals."""

    notable_buys: list[str] = Field(default_factory=list, description="≤5 short tickers")
    notable_sells: list[str] = Field(default_factory=list, description="≤5 short tickers")
    policy_signal: str | None = Field(
        default=None,
        description="Fed / Treasury / regulator signal worth flagging today.",
    )


# ─── Phase assembly ─────────────────────────────────────────────────────────

_PHASE_FIELD = "phase1_outputs"

_SPECS = (
    SegmentNodeSpec(
        segment_slug="alt-sentiment-news",
        skill_slug="alt-sentiment-news",
        output_model=SentimentNewsReport,
        phase_outputs_field=_PHASE_FIELD,
    ),
    SegmentNodeSpec(
        segment_slug="alt-cta-positioning",
        skill_slug="alt-cta-positioning",
        output_model=CtaPositioningReport,
        phase_outputs_field=_PHASE_FIELD,
    ),
    SegmentNodeSpec(
        segment_slug="alt-options-derivatives",
        skill_slug="alt-options-derivatives",
        output_model=OptionsDerivativesReport,
        phase_outputs_field=_PHASE_FIELD,
    ),
    SegmentNodeSpec(
        segment_slug="alt-politician-signals",
        skill_slug="alt-politician-signals",
        output_model=PoliticianSignalsReport,
        phase_outputs_field=_PHASE_FIELD,
    ),
)


def build_phase1() -> PipelinePhase:
    """Return the Phase-1 fan-out (4 parallel nodes)."""
    return PipelinePhase(
        name="phase1_altdata",
        nodes=[NodeSpec(name=spec.segment_slug, run=build_segment_node(spec)) for spec in _SPECS],
    )


__all__ = [
    "CtaPositioningReport",
    "OptionsDerivativesReport",
    "PoliticianSignalsReport",
    "SentimentNewsReport",
    "build_phase1",
]
