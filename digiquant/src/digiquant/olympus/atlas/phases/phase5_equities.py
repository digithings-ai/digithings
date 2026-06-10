"""Phase 5 — US equities top-down, 11-sector swarm, deterministic scorecard.

Sector nodes share ``sector-research`` skill + ``config/sectors.yaml`` injection.
"""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for dict shape typing below

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant.olympus.atlas.phases._node_factory import _shared_context
from digiquant.olympus.atlas.sectors_config import SectorConfig, load_sectors
from digiquant.olympus.atlas.segments import Bias, SegmentReport
from digiquant.olympus.atlas.state import AtlasResearchState, SegmentPayload, SegmentSlot


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


class SectorScorecardEntry(SegmentReport):
    """One scorecard row (digest-reader compatible)."""

    etf: str = Field()
    stance: Literal["overweight", "underweight", "neutral"]
    key_driver: str = Field()


class SectorScorecard(SegmentReport):
    """Phase 5M — orchestrator synthesis after the 11 sector swarm."""

    rows: list[SectorScorecardEntry] = Field(default_factory=list)


# ─── Equity top-down node ───────────────────────────────────────────────────


def _equity_node(state: AtlasResearchState) -> dict[str, Any]:
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.olympus.atlas.phases._node_factory import build_grounding
    from digiquant.olympus.atlas.skills import load_skill

    skill_text = load_skill("equity")
    phase_inputs: dict[str, Any] = {
        "segment": "equity",
        "macro_regime": _macro_body(state),
        "phase1_signals": _phase1_bodies(state),
        "phase4_asset_classes": _phase4_bodies(state),
    }
    tools, execute_tool, _ = build_grounding(
        use_data_tools=True, live_search=False, run_date=state.run_date
    )
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=_shared_context(state),
        output_model=EquityOverviewReport,
        phase_slug="equity",
        tools=tools,
        execute_tool=execute_tool,
    )
    payload = SegmentPayload(
        segment="equity",
        body=result.model_dump(mode="json"),
        as_of=state.run_date,
    )
    # Equity is a single slot — same pattern as macro.
    return {"phase5_outputs": {"equity": SegmentSlot(payload=payload)}}


# ─── Sector node factory ────────────────────────────────────────────────────


def _sector_node_factory(sector: SectorConfig):
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.olympus.atlas.phases._node_factory import build_grounding
    from digiquant.olympus.atlas.skills import load_skill

    def _node(state: AtlasResearchState) -> dict[str, Any]:
        skill_text = load_skill("sector-research")
        # Equity top-down output is in phase5_outputs["equity"] after phase 5A.
        equity_body: dict[str, Any] = {}
        equity_slot = state.phase5_outputs.get("equity")
        if equity_slot is not None and equity_slot.payload.source == "today":
            equity_body = equity_slot.payload.body  # type: ignore[union-attr]
        phase_inputs: dict[str, Any] = {
            "segment": sector.slug,
            "sector_config": {
                "slug": sector.slug,
                "name": sector.name,
                "etfs": sector.etfs,
                "subsegments": sector.subsegments,
                "top_tickers": sector.top_tickers,
                "key_drivers": sector.key_drivers,
                "nuance_notes": sector.nuance_notes,
            },
            "macro_regime": _macro_body(state),
            "phase1_signals": _phase1_bodies(state),
            "equity_overview": equity_body,
        }
        tools, execute_tool, _ = build_grounding(
            use_data_tools=True, live_search=False, run_date=state.run_date
        )
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=_shared_context(state),
            output_model=SectorReport,
            phase_slug=sector.slug,
            tools=tools,
            execute_tool=execute_tool,
        )
        payload = SegmentPayload(
            segment=sector.slug,
            body=result.model_dump(mode="json"),
            as_of=state.run_date,
        )
        return {"phase5_outputs": {sector.slug: SegmentSlot(payload=payload)}}

    return _node


# ─── Scorecard synthesis node ───────────────────────────────────────────────


def _scorecard_node(state: AtlasResearchState) -> dict[str, Any]:
    """Deterministic scorecard from fresh sector slots (no LLM)."""
    rows: list[SectorScorecardEntry] = []
    for sector in load_sectors():
        slot = state.phase5_outputs.get(sector.slug)
        if slot is None or slot.payload.source != "today":
            continue
        body = slot.payload.body  # type: ignore[union-attr]
        rows.append(
            SectorScorecardEntry(
                segment=sector.slug,
                date=state.run_date,
                bias=_bias_from_body(body),
                headline=str(body.get("headline") or ""),
                etf=(sector.etfs[0] if sector.etfs else ""),
                stance=_stance_from_bias(_bias_from_body(body)),
                key_driver=(sector.key_drivers[0] if sector.key_drivers else ""),
                material_findings=[],
                sources=[],
                notes="",
            )
        )
    scorecard = SectorScorecard(
        segment="sector-scorecard",
        date=state.run_date,
        bias=_aggregate_bias(rows),
        headline=f"{len(rows)} sectors scored",
        rows=rows,
        material_findings=[],
        sources=[],
        notes="",
    )
    payload = SegmentPayload(
        segment="sector-scorecard",
        body=scorecard.model_dump(mode="json"),
        as_of=state.run_date,
    )
    return {"phase5_outputs": {"sector-scorecard": SegmentSlot(payload=payload)}}


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


def _bias_from_body(body: dict[str, Any]) -> Bias:
    raw = str(body.get("bias") or "neutral")
    if raw in {"strong_bullish", "bullish", "neutral", "bearish", "strong_bearish", "mixed"}:
        return raw  # type: ignore[return-value]
    return "neutral"


def _stance_from_bias(bias: Bias) -> Literal["overweight", "underweight", "neutral"]:
    if bias in {"strong_bullish", "bullish"}:
        return "overweight"
    if bias in {"strong_bearish", "bearish"}:
        return "underweight"
    return "neutral"


def _aggregate_bias(rows: list[SectorScorecardEntry]) -> Bias:
    """Reduce 11 sector stances to one portfolio-level bias.

    Thresholds (deliberate, document here so readers don't reverse-engineer):
    - ``bullish`` when overweight sectors are more than 2× underweight (≥67% OW-tilt).
    - ``bearish`` the symmetric case.
    - ``mixed`` when OW and UW are nearly balanced and together cover at least
      half the sectors — genuine tug-of-war between directional bets.
    - ``neutral`` otherwise (mostly neutral stances, or no meaningful directional tilt).
    - Empty input is treated as ``mixed`` (no information, don't fake a stance).
    """
    if not rows:
        return "mixed"
    ow = sum(1 for r in rows if r.stance == "overweight")
    uw = sum(1 for r in rows if r.stance == "underweight")
    if ow > uw * 2:
        return "bullish"
    if uw > ow * 2:
        return "bearish"
    if abs(ow - uw) <= 1 and ow + uw >= len(rows) // 2:
        return "mixed"
    return "neutral"


# ─── Phase assembly ─────────────────────────────────────────────────────────


def build_phase5_equity() -> PipelinePhase:
    """Phase 5A: single equity top-down node."""
    return PipelinePhase(
        name="phase5_equity",
        nodes=[NodeSpec(name="equity", run=_equity_node)],
    )


def build_phase5_sectors() -> PipelinePhase:
    """Phase 5B–L: 11 parallel sector nodes driven by sectors.yaml."""
    return PipelinePhase(
        name="phase5_sectors",
        nodes=[
            NodeSpec(name=sector.slug, run=_sector_node_factory(sector))
            for sector in load_sectors()
        ],
    )


def build_phase5_scorecard() -> PipelinePhase:
    """Phase 5M: deterministic scorecard synthesis (no LLM)."""
    return PipelinePhase(
        name="phase5_scorecard",
        nodes=[NodeSpec(name="sector-scorecard", run=_scorecard_node)],
    )


def build_phase5() -> list[PipelinePhase]:
    """Return equity → sectors → scorecard sub-phases in order."""
    return [build_phase5_equity(), build_phase5_sectors(), build_phase5_scorecard()]


__all__ = [
    "EquityOverviewReport",
    "SectorReport",
    "SectorScorecard",
    "SectorScorecardEntry",
    "build_phase5",
    "build_phase5_equity",
    "build_phase5_scorecard",
    "build_phase5_sectors",
]
