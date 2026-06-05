"""Phase 6 — Daily-snapshot bias row consolidation.

A deterministic reduction over the first five phases — extracts the bias
signals the dashboard cares about into the row shape of ``daily_snapshots``.
No LLM call; this is pure aggregation.

The 14-column bias row is described in ARCHITECTURE.md §Phase 6. Fields
we can determine deterministically from prior phases are set; narrative
fields (like ``notes``) are left empty and populated in Phase 7.
"""

from __future__ import annotations

from typing import Any  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.atlas.state import AtlasResearchState, Phase6BiasRow


def _bias_of(state: AtlasResearchState, field: str, key: str) -> str:
    container = getattr(state, field, None)
    if not container:
        return ""
    slot = container.get(key) if isinstance(container, dict) else container
    if slot is None or slot.payload.source != "today":
        return ""
    body = slot.payload.body  # type: ignore[union-attr]
    return str(body.get("bias") or "")


def _macro_regime_label(state: AtlasResearchState) -> str:
    if state.phase3_output is None or state.phase3_output.payload.source != "today":
        return ""
    return str(state.phase3_output.payload.body.get("regime_label") or "")  # type: ignore[union-attr]


def _vix_level(state: AtlasResearchState) -> float | None:
    options = state.phase1_outputs.get("alt-options-derivatives")
    if options is None or options.payload.source != "today":
        return None
    val = options.payload.body.get("vix_level")  # type: ignore[union-attr]
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _phase6_node(state: AtlasResearchState) -> dict[str, Any]:
    """Assemble the daily_snapshots bias row from phases 1–5."""
    bias_row: Phase6BiasRow = {
        "date": state.run_date.isoformat(),
        "run_type": state.run_type,
        "macro_regime": _macro_regime_label(state),
        "equity_bias": _bias_of(state, "phase5_outputs", "equity"),
        "crypto_bias": _bias_of(state, "phase4_outputs", "crypto"),
        "bond_bias": _bias_of(state, "phase4_outputs", "bonds"),
        "commodity_bias": _bias_of(state, "phase4_outputs", "commodities"),
        "forex_bias": _bias_of(state, "phase4_outputs", "forex"),
        "vix_level": _vix_level(state),
        "inst_flow": _bias_of(state, "phase2_outputs", "inst-institutional-flows"),
        "options_sentiment": _bias_of(state, "phase1_outputs", "alt-options-derivatives"),
        "cta_direction": _bias_of(state, "phase1_outputs", "alt-cta-positioning"),
        "hf_consensus": _bias_of(state, "phase2_outputs", "inst-hedge-fund-intel"),
        "fed_odds": None,  # populated by Phase 7 synthesis via rate-futures lookup
        "notes": "",  # filled by Phase 7 master synthesis
    }
    return {"phase6_bias_row": bias_row}


def build_phase6() -> PipelinePhase:
    return PipelinePhase(
        name="phase6_consolidate",
        nodes=[NodeSpec(name="consolidate", run=_phase6_node)],
    )


__all__ = ["build_phase6"]
