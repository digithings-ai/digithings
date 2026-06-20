"""Phase 2 — institutional intelligence (2 parallel segment nodes).

Carries a delta-only **circuit-breaker** (#928): institutional segments run
live web search + an LLM, but Jun 17–19 prod produced zero ``inst-*`` documents
(no ingest) while still paying for both. When pre-flight reports the
institutional layer has been absent for ``>= ABSENCE_BREAKER_THRESHOLD``
consecutive runs, a DELTA run skips the paid ``inst-*`` LLM/search nodes and
writes a deterministic "absent" stub slot instead (zero search spend). BASELINE
always runs Phase 2 fully — a baseline is the contract's full refresh and must
re-probe the layer rather than inherit a stale absence.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Literal  # noqa: F401 — used for node-update dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant.olympus.atlas.phases._node_factory import (
    SegmentNodeSpec,
    build_segment_node,
    dict_slot_write_adapter,
)
from digiquant.olympus.atlas.segments import SegmentReport
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    SegmentPayload,
    SegmentSlot,
)

logger = logging.getLogger(__name__)

# Consecutive institutional-absent runs that trip the delta circuit-breaker (#928).
ABSENCE_BREAKER_THRESHOLD = 3

# Reason stamped on the diagnostics-visible "absent" stub so the Phase 9
# post-mortem / cost audit can see exactly why inst-* skipped its paid nodes.
INST_ABSENT_REASON = "institutional_data_absent_circuit_breaker"


class InstitutionalFlowsReport(SegmentReport):
    """Phase 2A — ETF inflows / outflows, dark-pool prints, 13D/13G/Form 4."""

    flow_direction: Literal["inflow", "outflow", "mixed"] | None = None
    largest_sector_inflow: str | None = Field(default=None)
    largest_sector_outflow: str | None = Field(default=None)
    notable_filings: list[str] = Field(
        default_factory=list,
        description="≤5 short filing labels (e.g., '13D by Elliott on XYZ').",
    )


class HedgeFundIntelReport(SegmentReport):
    """Phase 2B — tracked-fund signals (13F, X posts, conference calls)."""

    tracked_funds_count: int = Field(default=0, ge=0)
    top_signals: list[str] = Field(
        default_factory=list,
        description="≤8 short signal labels; ordered by conviction.",
    )


# ─── Phase assembly ─────────────────────────────────────────────────────────

_PHASE_FIELD = "phase2_outputs"

_SPECS = (
    SegmentNodeSpec(
        segment_slug="inst-institutional-flows",
        skill_slug="inst-institutional-flows",
        output_model=InstitutionalFlowsReport,
        phase_outputs_field=_PHASE_FIELD,
        live_search=True,  # 13F / flows color from web
    ),
    SegmentNodeSpec(
        segment_slug="inst-hedge-fund-intel",
        skill_slug="inst-hedge-fund-intel",
        output_model=HedgeFundIntelReport,
        phase_outputs_field=_PHASE_FIELD,
        live_search=True,
    ),
)


def _breaker_tripped(state: AtlasResearchState) -> bool:
    """True only on a DELTA run whose institutional layer has been absent
    for ``>= ABSENCE_BREAKER_THRESHOLD`` consecutive runs.

    BASELINE (and any non-delta) always returns False so Phase 2 runs fully —
    a baseline must re-probe the layer rather than inherit a stale absence.
    """
    if state.run_type != "delta":
        return False
    return state.data_layer.institutional_absence_streak >= ABSENCE_BREAKER_THRESHOLD


def _absent_stub_slot(spec: SegmentNodeSpec, state: AtlasResearchState) -> SegmentSlot:
    """Deterministic, search-free 'absent' stub for a skipped institutional segment.

    Graded ``data_quality='absent'`` with bias ``neutral`` and no findings, so
    publish suppresses it (Pillar 1E ``_is_degenerate``) instead of surfacing a
    confident empty document. The breaker reason is stamped into ``notes`` and a
    machine-readable ``circuit_breaker`` marker so diagnostics can record the
    skip without a new column.
    """
    body: dict[str, Any] = {
        "segment": spec.segment_slug,
        "date": state.run_date.isoformat(),
        "bias": "neutral",
        "headline": "Institutional data absent — circuit-breaker engaged; segment skipped.",
        "material_findings": [],
        "sources": [],
        "notes": (
            f"{INST_ABSENT_REASON}: institutional ingest absent for "
            f"{state.data_layer.institutional_absence_streak} consecutive runs "
            f"(>= {ABSENCE_BREAKER_THRESHOLD}); skipped paid LLM/web-search nodes."
        ),
        "data_quality": "absent",
        "circuit_breaker": INST_ABSENT_REASON,
    }
    return SegmentSlot(
        payload=SegmentPayload(segment=spec.segment_slug, body=body, as_of=state.run_date)
    )


def _build_phase2_node(spec: SegmentNodeSpec) -> Callable[[AtlasResearchState], dict[str, Any]]:
    """Wrap the generic segment node with the delta circuit-breaker (#928)."""
    inner = build_segment_node(spec)

    def _node(state: AtlasResearchState) -> dict[str, Any]:
        if _breaker_tripped(state):
            logger.info(
                "phase2 circuit-breaker: skipping %s (institutional absent %d>=%d runs); "
                "emitting deterministic absent stub, zero search spend",
                spec.segment_slug,
                state.data_layer.institutional_absence_streak,
                ABSENCE_BREAKER_THRESHOLD,
            )
            return dict_slot_write_adapter(spec, _absent_stub_slot(spec, state))
        return inner(state)

    return _node


def build_phase2() -> PipelinePhase:
    """Return the Phase-2 fan-out (2 parallel nodes) with the delta circuit-breaker."""
    return PipelinePhase(
        name="phase2_institutional",
        nodes=[NodeSpec(name=spec.segment_slug, run=_build_phase2_node(spec)) for spec in _SPECS],
    )


__all__ = [
    "ABSENCE_BREAKER_THRESHOLD",
    "INST_ABSENT_REASON",
    "HedgeFundIntelReport",
    "InstitutionalFlowsReport",
    "build_phase2",
]
