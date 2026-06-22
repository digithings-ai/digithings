"""Phase 5 — US equities top-down, 11-sector swarm, deterministic scorecard.

Sector nodes share ``sector-research`` skill + ``config/sectors.yaml`` injection.
"""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for dict shape typing below

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant.olympus.atlas.phases._node_factory import (
    InputsBuilder,
    SegmentNodeSpec,
    build_segment_node,
)
from digiquant.olympus.atlas.sectors_config import SectorConfig, load_sectors
from digiquant.olympus.atlas.segments import Bias, DataQuality, SegmentReport, Source
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
                # #953: propagate the quality signals from the sector report instead of
                # dropping them — the scorecard is the artifact Hermes/PM weight on, so a
                # sector graded data_quality="low" must not look identical to a "high" one.
                confidence=body.get("confidence"),
                data_quality=body.get("data_quality"),
                material_findings=body.get("material_findings") or [],
                sources=body.get("sources") or [],
                notes=str(body.get("notes") or ""),
            )
        )
    scorecard = SectorScorecard(
        segment="sector-scorecard",
        date=state.run_date,
        bias=_aggregate_bias(rows),
        headline=f"{len(rows)} sectors scored",
        rows=rows,
        # #953: roll the per-sector quality up so the scorecard envelope itself carries a
        # confidence / data-quality / provenance signal (was hardcoded empty).
        confidence=_aggregate_confidence(rows),
        data_quality=_worst_data_quality(rows),
        material_findings=[f for r in rows for f in r.material_findings][:8],
        sources=_dedup_sources(rows),
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


# Worst-to-best ordering for rolling the per-sector data-quality grade up to the scorecard.
_DATA_QUALITY_RANK: dict[str, int] = {"absent": 0, "low": 1, "medium": 2, "high": 3}


def _aggregate_confidence(rows: list[SectorScorecardEntry]) -> float | None:
    """Mean of the present per-sector confidences (None when no sector reported one)."""
    vals = [r.confidence for r in rows if r.confidence is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _worst_data_quality(rows: list[SectorScorecardEntry]) -> DataQuality | None:
    """Lowest per-sector data-quality grade — the scorecard is only as trustworthy as its
    weakest sector read (absent < low < medium < high). None when none reported one."""
    grades = [r.data_quality for r in rows if r.data_quality is not None]
    if not grades:
        return None
    return min(grades, key=lambda g: _DATA_QUALITY_RANK.get(str(g), 0))


def _dedup_sources(rows: list[SectorScorecardEntry], *, cap: int = 20) -> list[Source]:
    """Deduplicated union of per-sector sources (by id), capped — a provenance trail for the
    scorecard envelope (was hardcoded empty)."""
    seen: set[str] = set()
    out: list[Source] = []
    for row in rows:
        for src in row.sources:
            if src.id and src.id not in seen:
                seen.add(src.id)
                out.append(src)
                if len(out) >= cap:
                    return out
    return out


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
