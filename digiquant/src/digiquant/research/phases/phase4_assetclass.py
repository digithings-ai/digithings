"""Phase 4 — asset-class analysis (5 parallel nodes; macro + phase-1 inputs)."""

from __future__ import annotations

from typing import Any  # score:allow untyped any — used for dict shape typing below

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.research.phases._node_factory import (
    SegmentNodeSpec,
    build_segment_node,
)
from digiquant.research.segments import ResearchMemo
from digiquant.research.state import AtlasResearchState


class BondsReport(ResearchMemo):
    """Phase 4A — yield curve + credit."""


class CommoditiesReport(ResearchMemo):
    """Phase 4B — energy / metals / ags."""


class ForexReport(ResearchMemo):
    """Phase 4C — DXY + major pairs."""


class CryptoReport(ResearchMemo):
    """Phase 4D — BTC/ETH + on-chain."""


class InternationalReport(ResearchMemo):
    """Phase 4E — Asia / Europe / EM."""


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
