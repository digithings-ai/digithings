"""Phase 6 — deterministic ``daily_snapshots`` bias row (no LLM)."""

from __future__ import annotations

from typing import Any  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import AtlasResearchState, Phase6BiasRow


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


def _fed_odds_compact(state: AtlasResearchState) -> dict[str, Any] | None:
    """Extract a compact fed_odds summary from the preflight market_context.

    The full ``get_fed_rate_probabilities`` payload (meeting_date, kalshi distribution,
    polymarket list) is richer than the bias row needs. We surface the most actionable
    slice: meeting date, most-likely bucket, and p(cut)/p(hold)/p(hike) when available.
    Returns None when preflight did not populate fed_odds (outage or no ingested rows).
    """
    full = state.data_layer.market_context.get("fed_odds")
    if not isinstance(full, dict) or not full:
        return None
    out: dict[str, Any] = {"meeting_date": full.get("meeting_date")}
    kalshi = full.get("kalshi") or {}
    dist = kalshi.get("distribution") or {}
    if dist:
        out["most_likely"] = kalshi.get("most_likely")
        # Aggregate into the three coarse buckets the bias row uses.
        # bucket keys look like "<=3.25", "3.5", ">4.25"; a cut = key < current fed funds.
        # We surface the raw distribution so downstream consumers can re-aggregate.
        out["distribution"] = dist
    polymarket = full.get("polymarket")
    if polymarket:
        out["polymarket_top"] = polymarket[0] if polymarket else None
    out["sources"] = full.get("sources", [])
    return out


def _onchain_positioning_compact(state: AtlasResearchState) -> dict[str, Any] | None:
    """Surface the on-chain cohort-positioning summary preflight injected into market_context.

    The provider already stores a compact dict (overall divergence + the top divergent markets),
    so this is a guarded pass-through. Returns None when preflight did not populate it (Hyperdash
    outage or no cohort data) — fail-soft, mirroring fed_odds (#801)."""
    compact = state.data_layer.market_context.get("onchain_positioning")
    return compact if isinstance(compact, dict) and compact else None


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
        # Populated by preflight from prediction-market data (Kalshi + Polymarket).
        # Fail-soft: None when no ingested rows or preflight encountered an outage.
        "fed_odds": _fed_odds_compact(state),
        # On-chain smart-money vs rekt cohort divergence (Hyperdash). Fail-soft to None (#801).
        "onchain_positioning": _onchain_positioning_compact(state),
        "notes": "",  # filled by Phase 7 master synthesis
    }
    return {"phase6_bias_row": bias_row}


def build_phase6() -> PipelinePhase:
    return PipelinePhase(
        name="phase6_consolidate",
        nodes=[NodeSpec(name="consolidate", run=_phase6_node)],
    )


__all__ = ["build_phase6"]
