"""Phase 4 — asset-class analysis (5 parallel nodes; macro + phase-1 inputs)."""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for dict shape typing below

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant.olympus.atlas.phases._node_factory import (
    SegmentNodeSpec,
    build_segment_node,
)
from digiquant.olympus.atlas.segments import SegmentReport
from digiquant.olympus.atlas.state import AtlasResearchState


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
    policy_divergence: str | None = Field(default=None)


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

# Every asset-class node keeps the macro prior in shared context (#696).
_MACRO_CTX = ("macro",)

_SPECS = (
    SegmentNodeSpec(
        "bonds",
        "bonds",
        BondsReport,
        _PHASE_FIELD,
        use_data_tools=True,
        extra_context_keys=_MACRO_CTX,
    ),
    SegmentNodeSpec(
        "commodities",
        "commodities",
        CommoditiesReport,
        _PHASE_FIELD,
        use_data_tools=True,
        extra_context_keys=_MACRO_CTX,
    ),
    SegmentNodeSpec(
        "forex",
        "forex",
        ForexReport,
        _PHASE_FIELD,
        use_data_tools=True,
        extra_context_keys=_MACRO_CTX,
    ),
    SegmentNodeSpec(
        "crypto",
        "crypto",
        CryptoReport,
        _PHASE_FIELD,
        use_data_tools=True,
        extra_context_keys=_MACRO_CTX,
    ),
    SegmentNodeSpec(
        "international",
        "international",
        InternationalReport,
        _PHASE_FIELD,
        use_data_tools=True,
        extra_context_keys=_MACRO_CTX,
        live_search=True,  # non-US markets / M2 freshness via web
    ),
)


def _asset_class_inputs_builder(state: AtlasResearchState, spec: SegmentNodeSpec) -> dict[str, Any]:
    """Inject macro regime and phase-1 signals into segment phase_inputs."""
    macro_body: dict[str, Any] = {}
    if state.phase3_output is not None and state.phase3_output.payload.source == "today":
        macro_body = state.phase3_output.payload.body  # type: ignore[union-attr]
    return {
        "segment": spec.segment_slug,
        "macro_regime": macro_body,
        "phase1_signals": {
            slug: slot.payload.model_dump(mode="json")
            for slug, slot in state.phase1_outputs.items()
        },
    }


def build_phase4() -> PipelinePhase:
    return PipelinePhase(
        name="phase4_assetclass",
        nodes=[
            NodeSpec(
                name=spec.segment_slug,
                run=build_segment_node(spec, inputs_builder=_asset_class_inputs_builder),
            )
            for spec in _SPECS
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
