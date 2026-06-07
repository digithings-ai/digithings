"""Phase 7C — per-ticker 4-axis analyst specialization (#430).

Architecture (per ticker in ``state.config.watchlist``):

    Phase 7C fan-out (parallel specialists):
      technical-analyst-{ticker}    → SpecialistPayload
      sentiment-analyst-{ticker}    → SpecialistPayload
      news-analyst-{ticker}         → SpecialistPayload
      fundamental-analyst-{ticker}  → SpecialistPayload

    Phase 7C join (sequential):
      join-analyst-{ticker}         → AnalystPayload (deterministic aggregator)

Each specialist makes one LLM call with axis-specific inputs:

- ``technical``    — Phase 5 equity body (OHLCV + technicals).
- ``sentiment``    — Phase 1 alt-data outputs (FNG, positioning).
- ``news``         — Phase 3 macro regime + Phase 2 institutional flows.
- ``fundamental``  — Phase 5 sector context + equity body.

The join is deterministic (no LLM): it averages the 4 ``conviction_axis``
values, picks the majority stance with weighting by axis conviction, and
synthesises the final ``AnalystPayload``. Single ``conviction_score`` and
``stance`` fields preserve the downstream PM contract — Phase 7D does not
need to know about the split.

Specialists are blinded to portfolio weights (existing rule preserved).
``ATLAS_MAX_ANALYSTS`` env var still caps the watchlist size; with the
4-axis split, total LLM calls per run = 4 × min(len(watchlist), cap).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field

from digiquant.olympus.atlas.phases._node_factory import _shared_context
from digiquant.olympus.hermes.state import HermesState

logger = logging.getLogger(__name__)


_AXES: tuple[Literal["technical", "sentiment", "news", "fundamental"], ...] = (
    "technical",
    "sentiment",
    "news",
    "fundamental",
)


class SpecialistPayload(BaseModel):
    """One axis of analyst opinion for one ticker.

    The four axes are validated against the same schema — only the
    inputs and skill prompt differ. This keeps the join arithmetic
    trivial (axis-blind aggregation).
    """

    axis: Literal["technical", "sentiment", "news", "fundamental"]
    ticker: str = Field()
    conviction_axis: float = Field(ge=0.0, le=1.0)
    stance_axis: Literal["buy", "hold", "sell", "watch"]
    rationale: str = Field()
    sources: list[str] = Field(default_factory=list)


class AnalystPayload(BaseModel):
    """Per-ticker analyst output — Phase 7D PM contract.

    Field names + bounds intentionally unchanged from the pre-#430 single-call
    shape so Phase 7D ``_pm_node`` keeps reading the same dict without
    modification. The 4-specialist body just changes how this gets produced.
    """

    ticker: str = Field()
    conviction_score: int = Field(ge=-5, le=5, description="-5 strong sell … +5 strong buy")
    stance: Literal["buy", "hold", "sell", "watch"]
    thesis: str = Field()
    risks: str = Field(default="")
    sources: list[str] = Field(default_factory=list)


def _macro_body(state: HermesState) -> dict[str, Any]:
    if state.phase3_output is None or state.phase3_output.payload.source != "today":
        return {}
    return dict(state.phase3_output.payload.body)  # type: ignore[union-attr]


def _phase5_equity_body(state: HermesState) -> dict[str, Any]:
    slot = state.phase5_outputs.get("equity")
    if slot is None or slot.payload.source != "today":
        return {}
    return dict(slot.payload.body)  # type: ignore[union-attr]


def _relevant_sectors_for(state: HermesState, ticker: str) -> dict[str, dict[str, Any]]:
    """Sector payloads that mention ``ticker`` in their top_tickers.

    Blinded-analyst rule: derived from public config, not from weight signals.
    Used by ``fundamental`` specialist (sector context) and ``news``
    specialist (sector-level catalysts).
    """
    from digiquant.olympus.atlas.sectors_config import load_sectors

    relevant_slugs = {s.slug for s in load_sectors() if ticker in s.top_tickers}
    return {
        slug: slot.payload.model_dump(mode="json")
        for slug, slot in state.phase5_outputs.items()
        if slug in relevant_slugs
    }


def _phase1_alt_data(state: HermesState) -> dict[str, dict[str, Any]]:
    """All Phase 1 alt-data segment payloads (sentiment + positioning + options + politicians)."""
    return {
        slug: slot.payload.model_dump(mode="json")
        for slug, slot in state.phase1_outputs.items()
        if slot.payload.source == "today"
    }


def _phase2_institutional(state: HermesState) -> dict[str, dict[str, Any]]:
    return {
        slug: slot.payload.model_dump(mode="json")
        for slug, slot in state.phase2_outputs.items()
        if slot.payload.source == "today"
    }


def _axis_inputs(
    *,
    axis: str,
    ticker: str,
    state: HermesState,
) -> dict[str, Any]:
    """Per-axis ``phase_inputs`` block.

    Each axis sees only the upstream segments relevant to its analytical
    lane. This is the whole point of the split — narrower inputs let one
    LLM call reason deeply on one axis instead of shallowly on four.
    """
    base = {
        "segment": f"{axis}-analyst-{ticker}",
        "ticker": ticker,
        "axis": axis,
        "bias_row": state.phase6_bias_row or {},
    }
    if axis == "technical":
        base["phase5_equity"] = _phase5_equity_body(state)
    elif axis == "sentiment":
        base["phase1_alt_data"] = _phase1_alt_data(state)
    elif axis == "news":
        base["phase3_macro"] = _macro_body(state)
        base["phase2_institutional"] = _phase2_institutional(state)
        base["relevant_sectors"] = _relevant_sectors_for(state, ticker)
    elif axis == "fundamental":
        base["phase5_equity"] = _phase5_equity_body(state)
        base["relevant_sectors"] = _relevant_sectors_for(state, ticker)
    return base


def _specialist_node_factory(axis: str, ticker: str):
    """Build one specialist node bound to (axis, ticker)."""
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.olympus.hermes.skills import load_skill

    skill_slug = f"{axis}-analyst"

    def _node(state: HermesState) -> dict[str, Any]:
        skill_text = load_skill(skill_slug)
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=_axis_inputs(axis=axis, ticker=ticker, state=state),
            shared_context=_shared_context(state),
            output_model=SpecialistPayload,
            phase_slug=f"{axis}-analyst-{ticker}",
        )
        return {"phase7c_specialists": {ticker: {axis: result.model_dump(mode="json")}}}

    return _node


_STANCE_TO_SCORE: dict[str, int] = {
    "sell": -2,
    "watch": -1,
    "hold": 0,
    "buy": 2,
}


def _join_analyst_node_factory(ticker: str):
    """Build the deterministic per-ticker join node.

    Aggregates the 4 specialists' outputs into a single ``AnalystPayload``:
    ``conviction_score`` is the [-5,+5] int from the weighted-average axis
    score; ``stance`` is the highest-weighted axis stance (with tie-break
    to "hold"); ``thesis`` concatenates the per-axis rationales and notes
    any missing axes; ``risks`` stays empty (a follow-up issue wires it);
    ``sources`` unions across axes preserving insertion order.
    """

    def _node(state: HermesState) -> dict[str, Any]:
        ticker_axes = state.phase7c_specialists.get(ticker, {})
        present = [ax for ax in _AXES if ax in ticker_axes]
        missing = [ax for ax in _AXES if ax not in ticker_axes]

        if not present:
            # Watchlist mismatch or full specialist failure — emit a
            # neutral payload so the PM step doesn't trip on a missing key.
            payload = AnalystPayload(
                ticker=ticker,
                conviction_score=0,
                stance="hold",
                thesis="(no specialist outputs available for this ticker)",
                risks="",
                sources=[],
            )
            return {"phase7c_analysts": {ticker: payload.model_dump(mode="json")}}

        weighted_score = 0.0
        weight_total = 0.0
        stance_weights: dict[str, float] = {"buy": 0.0, "hold": 0.0, "sell": 0.0, "watch": 0.0}
        thesis_parts: list[str] = []
        sources_seen: dict[str, None] = {}

        for axis in present:
            entry = ticker_axes[axis]
            conviction = float(entry.get("conviction_axis", 0.0))
            stance = str(entry.get("stance_axis", "hold"))
            weighted_score += conviction * _STANCE_TO_SCORE.get(stance, 0)
            weight_total += conviction
            stance_weights[stance] = stance_weights.get(stance, 0.0) + conviction
            thesis_parts.append(f"[{axis}] {entry.get('rationale', '').strip()}")
            for source in entry.get("sources", []):
                if isinstance(source, str) and source.strip():
                    sources_seen.setdefault(source.strip(), None)

        # ``_STANCE_TO_SCORE`` lives in {-2, -1, 0, 2}; the weighted average
        # therefore sits in [-2, +2]. Scale ×2.5 then clamp to the [-5, +5]
        # integer band the AnalystPayload schema expects.
        normalized = (weighted_score / weight_total) if weight_total > 0 else 0.0
        conviction_score = max(-5, min(5, round(normalized * 2.5)))

        if weight_total == 0.0:
            # All specialists reported zero conviction — no signal. Default
            # to "hold" so the reflector doesn't seed alpha against a bogus
            # buy decision (matches the no-specialists branch above).
            chosen_stance = "hold"
        else:
            # Tie-break to "hold" so the join doesn't lean bullish on
            # dict-insertion order when buy ↔ sell weights are equal.
            chosen_stance = max(
                stance_weights.items(),
                key=lambda kv: (kv[1], kv[0] == "hold"),
            )[0]

        if missing:
            thesis_parts.append("[degraded] missing specialist axes: " + ", ".join(sorted(missing)))
        thesis = "\n".join(thesis_parts)[:1200]

        payload = AnalystPayload(
            ticker=ticker,
            conviction_score=conviction_score,
            stance=chosen_stance,  # type: ignore[arg-type]
            thesis=thesis,
            risks="",
            sources=list(sources_seen),
        )
        return {"phase7c_analysts": {ticker: payload.model_dump(mode="json")}}

    return _node


def _capped_tickers(tickers: list[str]) -> list[str]:
    """Apply ``ATLAS_MAX_ANALYSTS`` cap (kept identical to pre-#430 behavior)."""
    max_analysts = int(os.environ.get("ATLAS_MAX_ANALYSTS", "0") or "0")
    if max_analysts > 0 and len(tickers) > max_analysts:
        logger.info(
            "Phase 7C limited to %d/%d tickers (ATLAS_MAX_ANALYSTS=%d); "
            "set ATLAS_MAX_ANALYSTS=0 for full watchlist",
            max_analysts,
            len(tickers),
            max_analysts,
        )
        return tickers[:max_analysts]
    return list(tickers)


def build_phase7c_specialists(tickers: list[str]) -> PipelinePhase:
    """Phase 7C-i: 4 × N specialist nodes running in parallel."""
    capped = _capped_tickers(tickers)
    if not capped:

        def _noop(_state: HermesState) -> dict[str, Any]:
            return {}

        return PipelinePhase(
            name="phase7c_specialists",
            nodes=[NodeSpec(name="specialist-noop", run=_noop)],
        )

    nodes = [
        NodeSpec(
            name=f"{axis}-analyst-{ticker}",
            run=_specialist_node_factory(axis, ticker),
        )
        for ticker in capped
        for axis in _AXES
    ]
    return PipelinePhase(name="phase7c_specialists", nodes=nodes)


def build_phase7c_join(tickers: list[str]) -> PipelinePhase:
    """Phase 7C-ii: N deterministic join nodes (one per ticker)."""
    capped = _capped_tickers(tickers)
    if not capped:

        def _noop(_state: HermesState) -> dict[str, Any]:
            return {}

        return PipelinePhase(
            name="phase7c_join",
            nodes=[NodeSpec(name="join-noop", run=_noop)],
        )

    return PipelinePhase(
        name="phase7c_join",
        nodes=[
            NodeSpec(name=f"join-analyst-{ticker}", run=_join_analyst_node_factory(ticker))
            for ticker in capped
        ],
    )


def build_phase7c(tickers: list[str]) -> list[PipelinePhase]:
    """Return the two Phase 7C sub-phases in execution order.

    Phase 7C is decomposed because the LangGraph pipeline builder runs
    nodes within a phase in parallel; the specialist outputs must all
    settle before the join nodes consume them. Two sub-phases give the
    correct ordering with no extra synchronization.

    The returned shape (``list[PipelinePhase]``) mirrors Phase 5's split.
    """
    return [build_phase7c_specialists(tickers), build_phase7c_join(tickers)]


__all__ = [
    "AnalystPayload",
    "SpecialistPayload",
    "build_phase7c",
    "build_phase7c_join",
    "build_phase7c_specialists",
]
