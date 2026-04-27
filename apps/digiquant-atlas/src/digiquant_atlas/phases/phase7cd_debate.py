"""Phase 7C-D — Bull/Bear adversarial debate per ticker (#429).

Inserts an adversarial debate phase between Phase 7C (analyst fan-out)
and Phase 7D (PM rebalance). For each ticker the bull/bear researcher
exchange arguments for ``N`` rounds (default 1, configurable via
``state.config.preferences["debate_rounds"]``); the research manager
then judges the round(s) and emits a structured ``DebateSummary``.

Sub-phase structure (per ticker):

    bull-researcher-{ticker}    → DebateRoundContribution
    bear-researcher-{ticker}    → DebateRoundContribution (counter)
    research-manager-{ticker}   → DebateSummary

Sequential — each step reads the prior one's output. Implemented as
three single-node sub-phases per ticker so LangGraph's "nodes within a
phase run in parallel" rule keeps each LLM call ordered.

The PM (`phase7d_pm._pm_node`) consumes the resulting
``state.phase7cd_debates[ticker]`` as a sibling of the analyst payload.
Graceful degradation: when debate summaries are empty (e.g. empty
watchlist, or the phase wasn't wired for a given graph shape), the PM
still produces a decision from analyst payloads alone.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field

from digiquant_atlas.phases._node_factory import _shared_context
from digiquant_atlas.state import AtlasResearchState

logger = logging.getLogger(__name__)


_DEFAULT_DEBATE_ROUNDS = 1
"""Number of bull-then-bear cycles before the research manager judges."""


class DebateRoundContribution(BaseModel):
    """One side's argument for a single round.

    Bull and bear researchers each emit one of these; the research
    manager assembles them into ``DebateRound`` instances.
    """

    role: Literal["bull", "bear"]
    ticker: str = Field(max_length=16)
    round_number: int = Field(ge=1, le=5)
    argument: str = Field(max_length=600)


class DebateRound(BaseModel):
    """One full bull-then-bear exchange."""

    round_number: int = Field(ge=1, le=5)
    bull_argument: str = Field(max_length=600)
    bear_argument: str = Field(max_length=600)


class DebateSummary(BaseModel):
    """Research-manager output. Lands in ``state.phase7cd_debates[ticker]``."""

    ticker: str = Field(max_length=16)
    rounds: list[DebateRound] = Field(default_factory=list)
    bull_thesis: str = Field(max_length=800)
    bear_thesis: str = Field(max_length=800)
    net_stance: Literal["bullish", "neutral", "bearish"]
    conviction_delta: int = Field(
        ge=-2,
        le=2,
        description="Adjustment to Phase 7C analyst conviction_score.",
    )


def _round_count(state: AtlasResearchState) -> int:
    """Resolve the configured round count from preferences (default 1)."""
    raw = state.config.preferences.get("debate_rounds", _DEFAULT_DEBATE_ROUNDS)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_DEBATE_ROUNDS
    # Bound at 1..5 — TradingAgents typically uses 1-2; leave headroom
    # without letting a misconfig produce 100-round debates.
    return max(1, min(5, n))


def _analyst_for(state: AtlasResearchState, ticker: str) -> dict[str, Any]:
    """Phase 7C analyst payload for this ticker (empty if missing)."""
    return dict(state.phase7c_analysts.get(ticker, {}))


def _prior_rounds(
    state: AtlasResearchState, ticker: str, role: Literal["bull", "bear"]
) -> list[dict[str, Any]]:
    """Return prior debate rounds plus, for the bear, the bull's pending
    contribution so it can read what's been argued this round."""
    debate = state.phase7cd_debates.get(ticker, {}) or {}
    rounds = list(debate.get("rounds") or [])
    pending = debate.get("pending") or {}
    if role == "bear" and pending.get("bull_argument"):
        rounds.append(
            {
                "round_number": pending.get("round_number", len(rounds) + 1),
                "bull_argument": pending["bull_argument"],
                "bear_argument": "",
            }
        )
    return rounds


def _bull_node_factory(ticker: str):
    from digigraph.graph.research_agent import run_research_agent

    from digiquant_atlas.skills import load_skill

    def _node(state: AtlasResearchState) -> dict[str, Any]:
        round_cap = _round_count(state)
        debate = dict(state.phase7cd_debates.get(ticker, {}) or {})
        # Bull opens the next round; abort if we've already hit the cap.
        round_number = len(debate.get("rounds") or []) + 1
        if round_number > round_cap:
            return {}

        skill_text = load_skill("research-debate")
        phase_inputs: dict[str, Any] = {
            "segment": f"bull-researcher-{ticker}",
            "ticker": ticker,
            "role": "bull",
            "round_number": round_number,
            "analyst_payload": _analyst_for(state, ticker),
            "prior_rounds": _prior_rounds(state, ticker, role="bull"),
            "bias_row": state.phase6_bias_row or {},
        }
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=_shared_context(state),
            output_model=DebateRoundContribution,
            phase_slug=f"bull-researcher-{ticker}",
        )
        debate["pending"] = {
            "round_number": result.round_number,
            "bull_argument": result.argument,
        }
        return {"phase7cd_debates": {ticker: debate}}

    return _node


def _bear_node_factory(ticker: str):
    from digigraph.graph.research_agent import run_research_agent

    from digiquant_atlas.skills import load_skill

    def _node(state: AtlasResearchState) -> dict[str, Any]:
        debate = dict(state.phase7cd_debates.get(ticker, {}) or {})
        pending = dict(debate.get("pending") or {})
        if not pending.get("bull_argument"):
            return {}  # bull node was skipped (e.g. round cap)

        skill_text = load_skill("research-debate")
        phase_inputs: dict[str, Any] = {
            "segment": f"bear-researcher-{ticker}",
            "ticker": ticker,
            "role": "bear",
            "round_number": pending.get("round_number", 1),
            "analyst_payload": _analyst_for(state, ticker),
            "bull_argument": pending["bull_argument"],
            "prior_rounds": _prior_rounds(state, ticker, role="bear"),
            "bias_row": state.phase6_bias_row or {},
        }
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=_shared_context(state),
            output_model=DebateRoundContribution,
            phase_slug=f"bear-researcher-{ticker}",
        )
        completed = list(debate.get("rounds") or [])
        completed.append(
            DebateRound(
                round_number=pending.get("round_number", 1),
                bull_argument=pending["bull_argument"],
                bear_argument=result.argument,
            ).model_dump(mode="json")
        )
        debate["rounds"] = completed
        debate["pending"] = {}
        return {"phase7cd_debates": {ticker: debate}}

    return _node


def _research_manager_node_factory(ticker: str):
    from digigraph.graph.research_agent import run_research_agent

    from digiquant_atlas.skills import load_skill

    def _node(state: AtlasResearchState) -> dict[str, Any]:
        debate = dict(state.phase7cd_debates.get(ticker, {}) or {})
        rounds = list(debate.get("rounds") or [])
        if not rounds:
            # No completed rounds — emit a neutral summary so the PM
            # phase still has a stable shape to read.
            summary = DebateSummary(
                ticker=ticker,
                rounds=[],
                bull_thesis="(no debate rounds completed)",
                bear_thesis="(no debate rounds completed)",
                net_stance="neutral",
                conviction_delta=0,
            )
            return {"phase7cd_debates": {ticker: summary.model_dump(mode="json")}}

        skill_text = load_skill("research-manager")
        phase_inputs: dict[str, Any] = {
            "segment": f"research-manager-{ticker}",
            "ticker": ticker,
            "rounds": rounds,
            "analyst_payload": _analyst_for(state, ticker),
            "bias_row": state.phase6_bias_row or {},
        }
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=_shared_context(state),
            output_model=DebateSummary,
            phase_slug=f"research-manager-{ticker}",
        )
        # The skill is told to return rounds verbatim; if it doesn't, we
        # overwrite with the deterministic record from state to keep
        # the audit trail intact.
        merged = result.model_copy(
            update={"rounds": [DebateRound.model_validate(r) for r in rounds]}
        )
        return {"phase7cd_debates": {ticker: merged.model_dump(mode="json")}}

    return _node


def _capped_tickers(tickers: list[str]) -> list[str]:
    """Apply the same ``ATLAS_MAX_ANALYSTS`` cap Phase 7C uses."""
    max_analysts = int(os.environ.get("ATLAS_MAX_ANALYSTS", "0") or "0")
    if max_analysts > 0 and len(tickers) > max_analysts:
        logger.info(
            "Phase 7C-D limited to %d/%d tickers (ATLAS_MAX_ANALYSTS=%d)",
            max_analysts,
            len(tickers),
            max_analysts,
        )
        return tickers[:max_analysts]
    return list(tickers)


def _noop(_state: AtlasResearchState) -> dict[str, Any]:
    return {}


def build_phase7cd_round(round_number: int, tickers: list[str]) -> list[PipelinePhase]:
    """Return one round = bull phase + bear phase (sequential)."""
    capped = _capped_tickers(tickers)
    if not capped:
        return [
            PipelinePhase(
                name=f"phase7cd_bull_round{round_number}",
                nodes=[NodeSpec(name=f"debate-bull-r{round_number}-noop", run=_noop)],
            ),
            PipelinePhase(
                name=f"phase7cd_bear_round{round_number}",
                nodes=[NodeSpec(name=f"debate-bear-r{round_number}-noop", run=_noop)],
            ),
        ]

    bull = PipelinePhase(
        name=f"phase7cd_bull_round{round_number}",
        nodes=[
            NodeSpec(
                name=f"bull-researcher-{ticker}-r{round_number}", run=_bull_node_factory(ticker)
            )
            for ticker in capped
        ],
    )
    bear = PipelinePhase(
        name=f"phase7cd_bear_round{round_number}",
        nodes=[
            NodeSpec(
                name=f"bear-researcher-{ticker}-r{round_number}", run=_bear_node_factory(ticker)
            )
            for ticker in capped
        ],
    )
    return [bull, bear]


def build_phase7cd_research_manager(tickers: list[str]) -> PipelinePhase:
    """Final per-ticker judgment phase — emits the DebateSummary."""
    capped = _capped_tickers(tickers)
    if not capped:
        return PipelinePhase(
            name="phase7cd_research_manager",
            nodes=[NodeSpec(name="research-manager-noop", run=_noop)],
        )
    return PipelinePhase(
        name="phase7cd_research_manager",
        nodes=[
            NodeSpec(name=f"research-manager-{ticker}", run=_research_manager_node_factory(ticker))
            for ticker in capped
        ],
    )


def build_phase7cd(
    tickers: list[str],
    *,
    rounds: int = _DEFAULT_DEBATE_ROUNDS,
) -> list[PipelinePhase]:
    """Build the full Phase 7C-D pipeline for one debate.

    ``rounds`` is the *graph-compile-time* upper bound. The actual round
    count is read from ``state.config.preferences["debate_rounds"]`` at
    invocation time (defaults to 1, max 5). Compile time uses ``rounds``
    to decide how many bull/bear sub-phases to wire; runtime uses the
    state to decide how many of those sub-phases actually do work.
    """
    bound = max(1, min(5, rounds))
    phases: list[PipelinePhase] = []
    for r in range(1, bound + 1):
        phases.extend(build_phase7cd_round(r, tickers))
    phases.append(build_phase7cd_research_manager(tickers))
    return phases


__all__ = [
    "DebateRound",
    "DebateRoundContribution",
    "DebateSummary",
    "build_phase7cd",
    "build_phase7cd_research_manager",
    "build_phase7cd_round",
]
