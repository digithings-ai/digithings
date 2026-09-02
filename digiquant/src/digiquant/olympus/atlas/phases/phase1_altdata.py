"""Phase 1 — alternative data & positioning (6 parallel segment nodes).

Per-skill Pydantic models extend :class:`digiquant.olympus.atlas.segments.ResearchMemo`.
"""

from __future__ import annotations

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.phases._node_factory import (
    SegmentNodeSpec,
    build_segment_node,
)
from digiquant.olympus.atlas.segments import ResearchMemo


class SentimentNewsReport(ResearchMemo):
    """Phase 1A — retail + pro sentiment + news catalysts."""


class CtaPositioningReport(ResearchMemo):
    """Phase 1B — systematic trend-follower positioning."""


class OnchainCohortPositioningReport(ResearchMemo):
    """Phase 1F — on-chain cohort positioning (smart-money vs rekt divergence, Hyperdash, #801)."""


class OptionsDerivativesReport(ResearchMemo):
    """Phase 1C — GEX, VIX, dealer positioning."""


class PoliticianSignalsReport(ResearchMemo):
    """Phase 1D — Congressional trades (STOCK Act) + policy signals."""


class AiPortfoliosReport(ResearchMemo):
    """Phase 1E — what other AI investment systems are picking (X proxy, #658)."""


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
        # Phase D PR-1 (#708): read the FRED-republished vol complex
        # (VIX/VIX3M/VXN/GVZ/OVX) via the Supabase data tools instead of a paid
        # web_search pre-pass — exact term-structure numbers, not paraphrased
        # prose, at zero per-run search cost.
        use_data_tools=True,
    ),
    SegmentNodeSpec(
        segment_slug="alt-politician-signals",
        skill_slug="alt-politician-signals",
        output_model=PoliticianSignalsReport,
        phase_outputs_field=_PHASE_FIELD,
        live_search=True,
    ),
    SegmentNodeSpec(
        segment_slug="alt-onchain-positioning",
        skill_slug="alt-onchain-positioning",
        output_model=OnchainCohortPositioningReport,
        phase_outputs_field=_PHASE_FIELD,
        # No live_search / data_tools: the deterministic Hyperdash divergence is injected into
        # shared_context.data_layer.market_context.onchain_positioning by preflight (#801). The
        # segment interprets that — zero per-run search cost.
    ),
    SegmentNodeSpec(
        segment_slug="alt-ai-portfolios",
        skill_slug="alt-ai-portfolios",
        output_model=AiPortfoliosReport,
        phase_outputs_field=_PHASE_FIELD,
        ai_portfolios=True,  # OpenRouter web search of tracked AI-portfolio accounts
    ),
)


def build_phase1() -> PipelinePhase:
    """Return the Phase-1 fan-out (6 parallel nodes)."""
    return PipelinePhase(
        name="phase1_altdata",
        nodes=[NodeSpec(name=spec.segment_slug, run=build_segment_node(spec)) for spec in _SPECS],
    )


__all__ = [
    "AiPortfoliosReport",
    "CtaPositioningReport",
    "OnchainCohortPositioningReport",
    "OptionsDerivativesReport",
    "PoliticianSignalsReport",
    "SentimentNewsReport",
    "build_phase1",
]
