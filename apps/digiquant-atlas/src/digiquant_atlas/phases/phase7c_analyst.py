"""Phase 7C — per-ticker asset-analyst fan-out.

One LLM call per ticker in ``state.config.watchlist`` (or a trimmed
portfolio list). Analysts are **blinded to current portfolio weights** —
they read only the published segment payloads and produce an independent
conviction score. The fan-out width equals the watchlist size; this is
bounded by the caller (watchlist cap is managed upstream).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field

from digiquant_atlas.phases._node_factory import _shared_context
from digiquant_atlas.state import AtlasResearchState

logger = logging.getLogger(__name__)


class AnalystPayload(BaseModel):
    """Per-ticker analyst output."""

    ticker: str = Field(max_length=16)
    conviction_score: int = Field(ge=-5, le=5, description="-5 strong sell … +5 strong buy")
    stance: Literal["buy", "hold", "sell", "watch"]
    thesis: str = Field(max_length=1200)
    risks: str = Field(default="", max_length=800)
    sources: list[str] = Field(default_factory=list)


def _analyst_node_factory(ticker: str):
    from digigraph.graph.research_agent import run_research_agent

    from digiquant_atlas.skills import load_skill

    def _node(state: AtlasResearchState) -> dict[str, Any]:
        skill_text = load_skill("asset-analyst")
        phase_inputs: dict[str, Any] = {
            "segment": f"analyst-{ticker}",
            "ticker": ticker,
            "bias_row": state.phase6_bias_row or {},
            "phase3_macro": _macro_body(state),
            "phase5_equity": _phase5_equity_body(state),
            "relevant_sectors": _relevant_sectors_for(state, ticker),
        }
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=_shared_context(state),
            output_model=AnalystPayload,
            phase_slug=f"analyst-{ticker}",
        )
        return {"phase7c_analysts": {ticker: result.model_dump(mode="json")}}

    return _node


def _macro_body(state: AtlasResearchState) -> dict[str, Any]:
    if state.phase3_output is None or state.phase3_output.payload.source != "today":
        return {}
    return dict(state.phase3_output.payload.body)  # type: ignore[union-attr]


def _phase5_equity_body(state: AtlasResearchState) -> dict[str, Any]:
    slot = state.phase5_outputs.get("equity")
    if slot is None or slot.payload.source != "today":
        return {}
    return dict(slot.payload.body)  # type: ignore[union-attr]


def _relevant_sectors_for(state: AtlasResearchState, ticker: str) -> dict[str, dict[str, Any]]:
    """Return sector payloads that reference ``ticker`` in their top_tickers.

    Blinded-analyst rule: no portfolio-weight leak. We only pass sector
    research for sectors whose top-ticker list includes this symbol — that
    is a derived fact from the public config, not a weight signal.
    """
    # Imported here to avoid circular import at module top.
    from digiquant_atlas.sectors_config import load_sectors

    relevant_slugs = {s.slug for s in load_sectors() if ticker in s.top_tickers}
    return {
        slug: slot.payload.model_dump(mode="json")
        for slug, slot in state.phase5_outputs.items()
        if slug in relevant_slugs
    }


def build_phase7c(tickers: list[str]) -> PipelinePhase:
    """Return a parallel fan-out phase with one node per ticker.

    ``tickers`` is materialized at graph-compile time — the watchlist is
    read from Atlas config before the graph is built.

    ``ATLAS_MAX_ANALYSTS`` (env var, default 0 = unlimited) caps the fan-out.
    CI sets it to 25 to stay within Groq free-tier concurrency limits.
    """
    max_analysts = int(os.environ.get("ATLAS_MAX_ANALYSTS", "0") or "0")
    if max_analysts > 0 and len(tickers) > max_analysts:
        logger.info(
            "Phase 7C limited to %d/%d tickers (ATLAS_MAX_ANALYSTS=%d); "
            "set ATLAS_MAX_ANALYSTS=0 for full watchlist",
            max_analysts,
            len(tickers),
            max_analysts,
        )
        tickers = tickers[:max_analysts]

    if not tickers:
        # Degenerate case: empty watchlist → insert a no-op so the graph
        # stays well-formed. Phase 7D can still run against an empty
        # analyst set.
        def _noop(_state: AtlasResearchState) -> dict[str, Any]:
            return {}

        return PipelinePhase(
            name="phase7c_analyst",
            nodes=[NodeSpec(name="analyst-noop", run=_noop)],
        )
    return PipelinePhase(
        name="phase7c_analyst",
        nodes=[
            NodeSpec(name=f"analyst-{ticker}", run=_analyst_node_factory(ticker))
            for ticker in tickers
        ],
    )


__all__ = ["AnalystPayload", "build_phase7c"]
