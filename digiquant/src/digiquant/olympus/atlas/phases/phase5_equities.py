"""Phase 5 — US equities top-down and 11-sector swarm.

Sector nodes share ``sector-research`` skill + ``config/sectors.yaml`` injection.
There is no rolled-up sector-scorecard step: operators and digest/PM read the
sector memos themselves.
"""

from __future__ import annotations

from typing import Any, Literal  # score:allow untyped any — used for dict shape typing below

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant.olympus.atlas.phases._node_factory import (
    InputsBuilder,
    SegmentNodeSpec,
    build_segment_node,
)
from digiquant.olympus.atlas.sectors_config import SectorConfig, load_sectors
from digiquant.olympus.atlas.segments import SegmentReport
from digiquant.olympus.atlas.state import AtlasResearchState

# ─── Output models ──────────────────────────────────────────────────────────


class EquityOverviewReport(SegmentReport):
    """Phase 5A — top-down SPY/QQQ/IWM read."""

    spy_trend: Literal["bullish", "bearish", "neutral"] | None = None
    market_breadth: Literal["broad", "narrow", "mixed"] | None = None
    factor_leader: (
        Literal["value", "growth", "momentum", "quality", "small_cap", "mixed"] | None
    ) = None


class SectorReport(SegmentReport):
    """Phase 5B-L — per-sector deep-dive (one LLM call per sector)."""

    relative_strength_vs_spy: Literal["outperforming", "underperforming", "inline"] | None = None
    sub_segment_leader: str | None = Field(default=None)
    driver_confirmation_count: int = Field(default=0, ge=0)
    conviction: Literal["high", "medium", "low"] | None = None


# ─── Equity top-down node ───────────────────────────────────────────────────

_EQUITY_SPEC = SegmentNodeSpec(
    segment_slug="equity",
    skill_slug="equity",
    output_model=EquityOverviewReport,
    phase_outputs_field="phase5_outputs",
    use_data_tools=True,
    extra_context_keys=("macro",),
)


def _equity_inputs_builder(state: AtlasResearchState, spec: SegmentNodeSpec) -> dict[str, Any]:
    return {
        "segment": spec.segment_slug,
        "macro_regime": _macro_body(state),
        "phase1_signals": _phase1_bodies(state),
        "phase4_asset_classes": _phase4_bodies(state),
    }


# ─── Sector nodes (build_segment_node + sector-research edit skill) ───────────


def _sector_config_payload(sector: SectorConfig) -> dict[str, Any]:
    return {
        "slug": sector.slug,
        "name": sector.name,
        "etfs": sector.etfs,
        "subsegments": sector.subsegments,
        "top_tickers": sector.top_tickers,
        "key_drivers": sector.key_drivers,
        "nuance_notes": sector.nuance_notes,
    }


def _equity_overview_body(state: AtlasResearchState) -> dict[str, Any]:
    equity_slot = state.phase5_outputs.get("equity")
    if equity_slot is not None and equity_slot.payload.source == "today":
        return equity_slot.payload.body  # type: ignore[union-attr]
    return {}


def _sector_inputs_builder(sector: SectorConfig) -> InputsBuilder:
    def _builder(state: AtlasResearchState, spec: SegmentNodeSpec) -> dict[str, Any]:
        return {
            "segment": spec.segment_slug,
            "sector_config": _sector_config_payload(sector),
            "macro_regime": _macro_body(state),
            "phase1_signals": _phase1_bodies(state),
            "equity_overview": _equity_overview_body(state),
        }

    return _builder


def _sector_spec(sector: SectorConfig) -> SegmentNodeSpec:
    return SegmentNodeSpec(
        segment_slug=sector.slug,
        skill_slug="sector-research",
        output_model=SectorReport,
        phase_outputs_field="phase5_outputs",
        use_data_tools=True,
        extra_context_keys=("equity", "macro"),
    )


# ─── Helpers ────────────────────────────────────────────────────────────────


def _macro_body(state: AtlasResearchState) -> dict[str, Any]:
    if state.phase3_output is None or state.phase3_output.payload.source != "today":
        return {}
    return state.phase3_output.payload.body  # type: ignore[union-attr]


def _phase1_bodies(state: AtlasResearchState) -> dict[str, dict[str, Any]]:
    return {
        slug: slot.payload.model_dump(mode="json") for slug, slot in state.phase1_outputs.items()
    }


def _phase4_bodies(state: AtlasResearchState) -> dict[str, dict[str, Any]]:
    return {
        slug: slot.payload.model_dump(mode="json") for slug, slot in state.phase4_outputs.items()
    }


# ─── Phase assembly ─────────────────────────────────────────────────────────


def build_phase5_equity() -> PipelinePhase:
    """Phase 5A: single equity top-down node."""
    return PipelinePhase(
        name="phase5_equity",
        nodes=[
            NodeSpec(
                name="equity",
                run=build_segment_node(_EQUITY_SPEC, inputs_builder=_equity_inputs_builder),
            )
        ],
    )


def build_phase5_sectors() -> PipelinePhase:
    """Phase 5B–L: 11 parallel sector nodes driven by sectors.yaml."""
    return PipelinePhase(
        name="phase5_sectors",
        nodes=[
            NodeSpec(
                name=sector.slug,
                run=build_segment_node(
                    _sector_spec(sector),
                    inputs_builder=_sector_inputs_builder(sector),
                ),
            )
            for sector in load_sectors()
        ],
    )


def build_phase5() -> list[PipelinePhase]:
    """Return equity → sector-memo sub-phases in order."""
    return [build_phase5_equity(), build_phase5_sectors()]


__all__ = [
    "EquityOverviewReport",
    "SectorReport",
    "build_phase5",
    "build_phase5_equity",
    "build_phase5_sectors",
]
