"""Phase 6 — deterministic ``daily_snapshots`` bias row (no LLM)."""

from __future__ import annotations

from datetime import date
from typing import Any  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    Phase6BiasRow,
    refresh_scope_forces_full,
)
from digiquant.olympus.edit_mode import DocumentPatch, PatchOp, merge_document_patch
from digiquant.olympus.edit_mode.models import TriageSignal
from digiquant.olympus.edit_mode.prior import PriorPublished
from digiquant.olympus.edit_mode.resolve import resolve_edit_mode

_BIAS_ROW_KEYS: tuple[str, ...] = (
    "macro_regime",
    "equity_bias",
    "crypto_bias",
    "bond_bias",
    "commodity_bias",
    "forex_bias",
    "vix_level",
    "inst_flow",
    "options_sentiment",
    "cta_direction",
    "hf_consensus",
    "fed_odds",
    "onchain_positioning",
    "notes",
)


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
    """Extract a compact fed_odds summary from the preflight market_context."""
    full = state.data_layer.market_context.get("fed_odds")
    if not isinstance(full, dict) or not full:
        return None
    out: dict[str, Any] = {"meeting_date": full.get("meeting_date")}
    kalshi = full.get("kalshi") or {}
    dist = kalshi.get("distribution") or {}
    if dist:
        out["most_likely"] = kalshi.get("most_likely")
        out["distribution"] = dist
    polymarket = full.get("polymarket")
    if polymarket:
        out["polymarket_top"] = polymarket[0] if polymarket else None
    out["sources"] = full.get("sources", [])
    return out


def _onchain_positioning_compact(state: AtlasResearchState) -> dict[str, Any] | None:
    compact = state.data_layer.market_context.get("onchain_positioning")
    return compact if isinstance(compact, dict) and compact else None


def _prior_snapshot_date(state: AtlasResearchState) -> date | None:
    if not state.prior_context.last_snapshots:
        return None
    snap_row = state.prior_context.last_snapshots[0]
    if not isinstance(snap_row, dict):
        return None
    snap_date = snap_row.get("date")
    if isinstance(snap_date, str):
        return date.fromisoformat(snap_date)
    return None


def _prior_bias_row(state: AtlasResearchState) -> dict[str, Any] | None:
    if not state.prior_context.last_snapshots:
        return None
    snap = state.prior_context.last_snapshots[0].get("snapshot") or {}
    if not isinstance(snap, dict):
        return None
    row = {key: snap[key] for key in _BIAS_ROW_KEYS if key in snap}
    return row or None


class _BiasPriorLoader:
    def __init__(self, state: AtlasResearchState) -> None:
        self._state = state

    def load(self, artifact_key: tuple[str, str], run_date: date) -> PriorPublished | None:
        del artifact_key
        prior_date = _prior_snapshot_date(self._state)
        prior_row = _prior_bias_row(self._state)
        if prior_date is None or prior_row is None or prior_date >= run_date:
            return None
        return PriorPublished(
            date=prior_date,
            document_key="digest",
            payload=dict(prior_row),
        )


def _digest_triage_signal(state: AtlasResearchState) -> TriageSignal | None:
    if state.triage is None:
        return None
    if state.triage.decisions and all(d.decision == "carry" for d in state.triage.decisions):
        return TriageSignal(mode="quiet")
    return TriageSignal(mode="stale")


def _recompute_bias_row(state: AtlasResearchState) -> Phase6BiasRow:
    return {
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
        "fed_odds": _fed_odds_compact(state),
        "onchain_positioning": _onchain_positioning_compact(state),
        "notes": "",
    }


def _bias_row_document_patch(
    *,
    state: AtlasResearchState,
    prior_row: dict[str, Any],
    new_row: Phase6BiasRow,
) -> DocumentPatch | None:
    prior_date = _prior_snapshot_date(state)
    if prior_date is None:
        return None
    ops: list[PatchOp] = []
    for key in _BIAS_ROW_KEYS:
        new_val = new_row.get(key)
        if prior_row.get(key) != new_val:
            ops.append(
                PatchOp(
                    op="set",
                    path=f"/{key}",
                    value=new_val,
                    reason="deterministic_segment_refresh",
                )
            )
    if not ops:
        return None
    return DocumentPatch(
        schema_version="1.0",
        date=state.run_date,
        prior_date=prior_date,
        target_document_key="digest",
        status="updated",
        ops=ops,
    )


def _phase6_node(state: AtlasResearchState) -> dict[str, Any]:
    """Assemble the daily_snapshots bias row from phases 1–5."""
    mode = resolve_edit_mode(
        artifact_key=("digest", "digest"),
        run_date=state.run_date,
        prior_loader=_BiasPriorLoader(state),
        triage=_digest_triage_signal(state),
        force_full_rewrite=refresh_scope_forces_full(state.refresh_scope, artifact="digest"),
    )

    if mode == "skip":
        prior_row = _prior_bias_row(state)
        if prior_row is not None:
            carried: Phase6BiasRow = {
                "date": state.run_date.isoformat(),
                "run_type": state.run_type,
                "macro_regime": str(prior_row.get("macro_regime") or ""),
                "equity_bias": str(prior_row.get("equity_bias") or ""),
                "crypto_bias": str(prior_row.get("crypto_bias") or ""),
                "bond_bias": str(prior_row.get("bond_bias") or ""),
                "commodity_bias": str(prior_row.get("commodity_bias") or ""),
                "forex_bias": str(prior_row.get("forex_bias") or ""),
                "vix_level": prior_row.get("vix_level"),
                "inst_flow": str(prior_row.get("inst_flow") or ""),
                "options_sentiment": str(prior_row.get("options_sentiment") or ""),
                "cta_direction": str(prior_row.get("cta_direction") or ""),
                "hf_consensus": str(prior_row.get("hf_consensus") or ""),
                "fed_odds": prior_row.get("fed_odds"),
                "onchain_positioning": prior_row.get("onchain_positioning"),
                "notes": str(prior_row.get("notes") or ""),
            }
            return {"phase6_bias_row": carried}

    new_row = _recompute_bias_row(state)
    update: dict[str, Any] = {"phase6_bias_row": new_row}

    prior_row = _prior_bias_row(state)
    if prior_row is not None:
        patch = _bias_row_document_patch(state=state, prior_row=prior_row, new_row=new_row)
        if patch is not None:
            merge_document_patch(dict(prior_row), patch)
            update["document_deltas"] = {"digest": patch.model_dump(mode="json")}

    return update


def build_phase6() -> PipelinePhase:
    return PipelinePhase(
        name="phase6_consolidate",
        nodes=[NodeSpec(name="consolidate", run=_phase6_node)],
    )


__all__ = ["build_phase6"]
