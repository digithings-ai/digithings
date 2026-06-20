"""Phase 7 — master digest synthesis (single LLM node).

Research-only: summarizes findings from phases 1–5. Portfolio positioning,
thesis lifecycle, and trade recommendations are Hermes's domain (phases 7C–7E).
"""

from __future__ import annotations

import re
from typing import Any, Literal  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field

from digiquant.olympus.atlas.phases._node_factory import _shared_context
from digiquant.olympus.atlas.segments import SegmentReport
from digiquant.olympus.atlas.state import AtlasResearchState


class SegmentFreshness(BaseModel):
    """Per-segment provenance marker used by the dashboard."""

    source: Literal["today", "baseline"]
    as_of: str = Field(description="ISO date")


class ActionableItem(BaseModel):
    priority: int = Field(ge=1, le=5)
    label: str = Field()
    rationale: str = Field()


class RiskItem(BaseModel):
    horizon_hours: int = Field(ge=1, le=168)
    label: str = Field()
    trigger: str = Field()


class DigestSnapshot(SegmentReport):
    """Phase 7 master synthesis payload."""

    market_regime_snapshot: str = Field()
    alt_data_dashboard: str = Field()
    institutional_summary: str = Field()
    asset_classes_summary: str = Field()
    us_equities_summary: str = Field()
    # Deprecated — kept for schema backward compat; always empty (Hermes owns positioning).
    thesis_tracker: str = Field(
        default="",
        description="Deprecated — Hermes owns thesis lifecycle; always empty on new runs.",
    )
    portfolio_recommendations: str = Field(
        default="",
        description="Deprecated — Hermes owns allocation; always empty on new runs.",
    )
    actionable_summary: list[ActionableItem] = Field(default_factory=list)
    risk_radar: list[RiskItem] = Field(default_factory=list)
    segment_freshness: dict[str, SegmentFreshness] = Field(
        default_factory=dict,
        description="Per-segment provenance (today vs. carried) — populated from state",
    )
    # Short machine-readable regime token for the dashboard chip.
    # The LLM is asked to populate this from phase3; when it omits it we
    # deterministically backfill from state.phase3_output.payload.body.get("regime_label")
    # — same fail-soft pattern used for segment_freshness above.
    regime_label: str = Field(
        default="",
        description=(
            "Short regime token, e.g. 'Risk-on / Policy easing' — "
            "NOT the full market_regime_snapshot paragraph."
        ),
    )


def _segment_freshness(state: AtlasResearchState) -> dict[str, SegmentFreshness]:
    """Derive the freshness map from state — does not rely on the LLM."""
    out: dict[str, SegmentFreshness] = {}
    for bag in (
        state.phase1_outputs,
        state.phase2_outputs,
        state.phase4_outputs,
        state.phase5_outputs,
    ):
        for slug, slot in bag.items():
            source = "today" if slot.payload.source == "today" else "baseline"
            as_of_val = getattr(slot.payload, "as_of", None) or getattr(
                slot.payload, "baseline_date", None
            )
            as_of = as_of_val.isoformat() if as_of_val else ""
            out[slug] = SegmentFreshness(source=source, as_of=as_of)  # type: ignore[arg-type]
    if state.phase3_output is not None:
        source = "today" if state.phase3_output.payload.source == "today" else "baseline"
        as_of_val = getattr(state.phase3_output.payload, "as_of", None) or getattr(
            state.phase3_output.payload, "baseline_date", None
        )
        out["macro"] = SegmentFreshness(
            source=source,  # type: ignore[arg-type]
            as_of=as_of_val.isoformat() if as_of_val else "",
        )
    return out


# Deterministic rewrite of allocation/trade verbs into research-watchlist
# language. Atlas is research-only (ADR-0015): the digest may *flag* what to
# watch but must not issue allocation directives — that is Hermes's domain.
# The digest skill is told this, but the LLM still slips trade verbs into
# ``actionable_summary`` items; this map neutralizes them deterministically.
# Ordered longest-phrase-first so multi-word verbs match before single words
# (e.g. "reduce exposure" before any bare "reduce"). Each pattern carries word
# boundaries so substrings inside larger words are left intact.
_TRADE_VERB_REWRITES: tuple[tuple[str, str], ...] = (
    ("reduce exposure to", "monitor downside risk in"),
    ("increase exposure to", "monitor upside potential in"),
    ("reduce exposure", "monitor downside risk"),
    ("increase exposure", "monitor upside potential"),
    ("rotate into", "watch relative strength in"),
    ("add to", "watch for confirmation in"),
    ("overweight", "favorable risk/reward in"),
    ("underweight", "unfavorable risk/reward in"),
    ("trim", "watch for weakness in"),
)

_TRADE_VERB_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rf"\b{re.escape(verb)}\b", re.IGNORECASE), replacement)
    for verb, replacement in _TRADE_VERB_REWRITES
)


def _strip_trade_verbs(text: str) -> str:
    """Rewrite allocation/trade verbs in ``text`` into research/watchlist language."""
    for pattern, replacement in _TRADE_VERB_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _enforce_research_only_boundary(digest: DigestSnapshot) -> DigestSnapshot:
    """Strip position-oriented fields the LLM may still emit despite the skill boundary.

    ``thesis_tracker`` and ``portfolio_recommendations`` are zeroed (#859);
    trade/allocation verbs inside ``actionable_summary`` items are rewritten
    into research/watchlist language (#927) rather than dropped, so the
    research signal survives without an allocation directive.
    """
    rewritten_summary = [
        item.model_copy(
            update={
                "label": _strip_trade_verbs(item.label),
                "rationale": _strip_trade_verbs(item.rationale),
            }
        )
        for item in digest.actionable_summary
    ]
    return digest.model_copy(
        update={
            "thesis_tracker": "",
            "portfolio_recommendations": "",
            "actionable_summary": rewritten_summary,
        }
    )


def _synthesis_node(state: AtlasResearchState) -> dict[str, Any]:
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.olympus.atlas.skills import load_skill

    skill_text = load_skill("digest")
    phase_inputs: dict[str, Any] = {
        "segment": "master-digest",
        "bias_row": state.phase6_bias_row or {},
        "phase1": _bodies(state.phase1_outputs),
        "phase2": _bodies(state.phase2_outputs),
        "phase3": _body(state.phase3_output),
        "phase4": _bodies(state.phase4_outputs),
        "phase5": _bodies(state.phase5_outputs),
    }
    # Custom research prompt threading (#313). Surfaced as an explicit
    # ``custom_prompt`` field rather than mixed into ``bias_row`` so the
    # digest skill can detect and prioritize it. Absent on routine runs.
    if state.custom_prompt:
        phase_inputs["custom_prompt"] = state.custom_prompt
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=_shared_context(state),
        output_model=DigestSnapshot,
        phase_slug="master-digest",
    )
    # Overwrite the LLM-proposed freshness map with the deterministic one.
    # The LLM is prone to inferring freshness incorrectly on delta runs;
    # state is authoritative.
    overrides: dict[str, Any] = {"segment_freshness": _segment_freshness(state)}
    # Deterministically backfill regime_label when the LLM omitted it.
    # Phase 3's macro body carries the authoritative short regime token; the
    # digest skill is asked to copy it but may leave the field empty.
    if not result.regime_label:
        overrides["regime_label"] = _regime_label_from_phase3(state)
    digest = _enforce_research_only_boundary(result.model_copy(update=overrides))
    return {"phase7_digest": digest.model_dump(mode="json")}


def _regime_label_from_phase3(state: AtlasResearchState) -> str:
    """Return the short regime token from phase3's macro body (fail-soft to empty string)."""
    if state.phase3_output is None or state.phase3_output.payload.source != "today":
        return ""
    return str(state.phase3_output.payload.body.get("regime_label") or "")  # type: ignore[union-attr]


def _body(slot: Any) -> dict[str, Any]:
    if slot is None or slot.payload.source != "today":
        return {}
    return dict(slot.payload.body)


def _bodies(bag: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return only today-source segment bodies (parity with ``_body``).

    On delta runs, carried (``source != "today"``) slots are baseline
    segments. Feeding them back into Phase 7 makes the digest re-synthesize
    unchanged baseline material, violating the research-only / delta boundary
    (ADR-0015). Carried provenance is still surfaced via ``segment_freshness``,
    which is derived from full state — not from this digest-input map.
    """
    return {
        slug: slot.payload.model_dump(mode="json")
        for slug, slot in bag.items()
        if slot.payload.source == "today"
    }


def build_phase7() -> PipelinePhase:
    return PipelinePhase(
        name="phase7_synthesis",
        nodes=[NodeSpec(name="master-digest", run=_synthesis_node)],
    )


__all__ = [
    "ActionableItem",
    "DigestSnapshot",
    "RiskItem",
    "SegmentFreshness",
    "build_phase7",
    "_enforce_research_only_boundary",
]
