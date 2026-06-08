"""Phase 1 — alternative data & positioning (4 parallel segment nodes).

Per-skill Pydantic models extend :class:`digiquant.olympus.atlas.segments.SegmentReport`.
"""

from __future__ import annotations

from typing import Literal

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant.olympus.atlas.phases._node_factory import (
    SegmentNodeSpec,
    build_segment_node,
)
from digiquant.olympus.atlas.segments import SegmentReport


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
        live_search=True,  # soft signals come from web/news/X
    ),
    SegmentNodeSpec(
        segment_slug="alt-cta-positioning",
        skill_slug="alt-cta-positioning",
        output_model=CtaPositioningReport,
        phase_outputs_field=_PHASE_FIELD,
        live_search=True,
    ),
    SegmentNodeSpec(
        segment_slug="alt-options-derivatives",
        skill_slug="alt-options-derivatives",
        output_model=OptionsDerivativesReport,
        phase_outputs_field=_PHASE_FIELD,
        live_search=True,
    ),
    SegmentNodeSpec(
        segment_slug="alt-politician-signals",
        skill_slug="alt-politician-signals",
        output_model=PoliticianSignalsReport,
        phase_outputs_field=_PHASE_FIELD,
        live_search=True,
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
