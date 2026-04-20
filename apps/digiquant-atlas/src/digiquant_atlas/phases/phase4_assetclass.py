"""Phase 4 — Asset class analysis (5-way parallel fan-out).

Five dedicated asset-class agents: bonds, commodities, forex, crypto,
international. Each references the Phase 3 macro regime and checks for
alignment. Output models are lightweight wrappers over SegmentReport with
asset-class-specific fields.
"""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for dict shape typing below

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant_atlas.phases._node_factory import (
    SegmentNodeSpec,
    _shared_context,
)
from digiquant_atlas.segments import SegmentReport
from digiquant_atlas.state import AtlasResearchState, SegmentPayload, SegmentSlot


class BondsReport(SegmentReport):
    """Phase 4A — yield curve + credit."""

    yield_curve_shape: Literal["steepening", "flattening", "inverted", "normal"] | None = None
    two_ten_spread_bps: float | None = None
    credit_ig_spread_bps: float | None = None
    credit_hy_spread_bps: float | None = None


class CommoditiesReport(SegmentReport):
    """Phase 4B — energy / metals / ags."""

    oil_trend: Literal["bullish", "bearish", "neutral"] | None = None
    gold_trend: Literal["bullish", "bearish", "neutral"] | None = None
    industrial_metals_trend: Literal["bullish", "bearish", "neutral"] | None = None


class ForexReport(SegmentReport):
    """Phase 4C — DXY + major pairs."""

    dxy_trend: Literal["stronger", "weaker", "range"] | None = None
    policy_divergence: str | None = Field(default=None, max_length=280)


class CryptoReport(SegmentReport):
    """Phase 4D — BTC/ETH + on-chain."""

    btc_trend: Literal["bullish", "bearish", "neutral"] | None = None
    btc_dominance: float | None = Field(default=None, ge=0, le=100)
    funding_rate_bias: Literal["long_skew", "short_skew", "balanced"] | None = None


class InternationalReport(SegmentReport):
    """Phase 4E — Asia / Europe / EM."""

    asia_stance: Literal["bullish", "bearish", "neutral"] | None = None
    europe_stance: Literal["bullish", "bearish", "neutral"] | None = None
    em_stance: Literal["bullish", "bearish", "neutral"] | None = None


# ─── Phase assembly ─────────────────────────────────────────────────────────

_PHASE_FIELD = "phase4_outputs"

_SPECS = (
    SegmentNodeSpec("bonds", "bonds", BondsReport, _PHASE_FIELD),
    SegmentNodeSpec("commodities", "commodities", CommoditiesReport, _PHASE_FIELD),
    SegmentNodeSpec("forex", "forex", ForexReport, _PHASE_FIELD),
    SegmentNodeSpec("crypto", "crypto", CryptoReport, _PHASE_FIELD),
    SegmentNodeSpec("international", "international", InternationalReport, _PHASE_FIELD),
)


def _asset_class_node_factory(spec: SegmentNodeSpec):
    """Build an asset-class node that reads Phase 3 macro output as input.

    The generic build_segment_node does not include upstream phase outputs
    in phase_inputs. Asset-class analysts need the macro regime — so we
    compose a specialized node here rather than bending the generic factory.
    """
    from digigraph.graph.research_agent import run_research_agent

    from digiquant_atlas.skills import load_skill

    def _node(state: AtlasResearchState) -> dict[str, Any]:
        skill_text = load_skill(spec.skill_slug)
        macro_body: dict[str, Any] = {}
        if state.phase3_output is not None and state.phase3_output.payload.source == "today":
            macro_body = state.phase3_output.payload.body  # type: ignore[union-attr]
        phase_inputs: dict[str, Any] = {
            "segment": spec.segment_slug,
            "macro_regime": macro_body,
            "phase1_signals": {
                slug: slot.payload.model_dump(mode="json")
                for slug, slot in state.phase1_outputs.items()
            },
        }
        shared = _shared_context(state)
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=shared,
            output_model=spec.output_model,
        )
        payload = SegmentPayload(
            segment=spec.segment_slug,
            body=result.model_dump(mode="json"),
            as_of=state.run_date,
        )
        return {spec.phase_outputs_field: {spec.segment_slug: SegmentSlot(payload=payload)}}

    return _node


def build_phase4() -> PipelinePhase:
    return PipelinePhase(
        name="phase4_assetclass",
        nodes=[
            NodeSpec(name=spec.segment_slug, run=_asset_class_node_factory(spec)) for spec in _SPECS
        ],
    )


__all__ = [
    "BondsReport",
    "CommoditiesReport",
    "CryptoReport",
    "ForexReport",
    "InternationalReport",
    "build_phase4",
]
