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
from collections.abc import Collection
from typing import Any, Literal

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field

from digiquant.olympus.atlas.data.queries import MARKET_DATA_TABLES
from digiquant.olympus.atlas.phases._node_factory import _shared_context, build_grounding
from digiquant.olympus.hermes.state import HermesState


def _debate_tools(state: HermesState):
    """query_data + computed tools for the debaters, scoped to market data only.

    Bull/bear/manager argue on the analyst's thesis and may cite real price/level
    numbers — but stay blinded to the book (positions/nav_history/theses), like the
    analysts, so the debate isn't anchored to current weights.
    """
    return build_grounding(
        use_data_tools=True,
        live_search=False,
        run_date=state.run_date,
        data_tool_tables=MARKET_DATA_TABLES,
    )


logger = logging.getLogger(__name__)


_DEFAULT_DEBATE_ROUNDS = 1
"""Number of bull-then-bear cycles before the research manager judges."""


class DebateRoundContribution(BaseModel):
    """One side's argument for a single round.

    Bull and bear researchers each emit one of these; the research
    manager assembles them into ``DebateRound`` instances.
    """

    role: Literal["bull", "bear"]
    ticker: str = Field()
    round_number: int = Field(ge=1, le=5)
    argument: str = Field()


class DebateRound(BaseModel):
    """One full bull-then-bear exchange."""

    round_number: int = Field(ge=1, le=5)
    bull_argument: str = Field()
    bear_argument: str = Field()


class DebateSummary(BaseModel):
    """Research-manager output. Lands in ``state.phase7cd_debates[ticker]``."""

    ticker: str = Field()
    rounds: list[DebateRound] = Field(default_factory=list)
    bull_thesis: str = Field()
    bear_thesis: str = Field()
    net_stance: Literal["bullish", "neutral", "bearish"]
    conviction_delta: int = Field(
        ge=-2,
        le=2,
        description="Adjustment to Phase 7C analyst conviction_score.",
    )


def clamp_debate_rounds(raw: Any, *, default: int = _DEFAULT_DEBATE_ROUNDS) -> int:
    """Clamp ``raw`` to [1, 5], falling back to ``default`` on bad input.

    Returns values in [1, 5] — TradingAgents uses 1–2; headroom prevents
    misconfig from producing 100-round debates.
    """
    try:
        return max(1, min(5, int(raw)))
    except (TypeError, ValueError):
        return default


def _round_count(state: HermesState) -> int:
    """Resolve the configured round count from preferences (default 1)."""
    return clamp_debate_rounds(
        state.config.preferences.get("debate_rounds", _DEFAULT_DEBATE_ROUNDS)
    )


def _analyst_for(state: HermesState, ticker: str) -> dict[str, Any]:
    """Phase 7C analyst payload for this ticker (empty if missing)."""
    return dict(state.phase7c_analysts.get(ticker, {}))


def _prior_rounds(
    state: HermesState, ticker: str, role: Literal["bull", "bear"]
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

    from digiquant.olympus.hermes.skills import load_skill

    def _node(state: HermesState) -> dict[str, Any]:
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
        tools, execute_tool, _ = _debate_tools(state)
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=_shared_context(
                state, context_keys=(f"analyst/{ticker}",), data_layer_scope="ticker"
            ),
            output_model=DebateRoundContribution,
            phase_slug=f"bull-researcher-{ticker}",
            tools=tools,
            execute_tool=execute_tool,
        )
        debate["pending"] = {
            "round_number": result.round_number,
            "bull_argument": result.argument,
        }
        return {"phase7cd_debates": {ticker: debate}}

    return _node


def _bear_node_factory(ticker: str):
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.olympus.hermes.skills import load_skill

    def _node(state: HermesState) -> dict[str, Any]:
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
        tools, execute_tool, _ = _debate_tools(state)
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=_shared_context(
                state, context_keys=(f"analyst/{ticker}",), data_layer_scope="ticker"
            ),
            output_model=DebateRoundContribution,
            phase_slug=f"bear-researcher-{ticker}",
            tools=tools,
            execute_tool=execute_tool,
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


def _deterministic_conviction_delta(
    net_stance: Literal["bullish", "neutral", "bearish"],
    analyst_conviction_score: int,
) -> int:
    """Compute conviction_delta from the debate outcome.

    The LLM research-manager returns a qualitative ``net_stance``; the delta is
    derived deterministically so it is reproducible and never silently defaults to 0.

    - ``bullish`` → +1 (or +2 when pre-debate score ≤ −3, allowing a larger correction)
    - ``bearish``  → −1 (or −2 when pre-debate score ≥ +3)
    - ``neutral``  → 0

    Returns values in [−2, +2] matching ``DebateSummary.conviction_delta`` bounds.
    """
    if net_stance == "bullish":
        return 2 if analyst_conviction_score <= -3 else 1
    if net_stance == "bearish":
        return -2 if analyst_conviction_score >= 3 else -1
    return 0


def _debate_output(summary_dict: dict[str, Any], rounds_count: int) -> dict[str, Any]:
    """Attach the ``rounds_count`` convenience field and return the dict.

    ``rounds_count`` is consumed by the Olympus dashboard and is NOT part of
    the ``DebateSummary`` schema; it is appended here so deliberation/{ticker}
    documents always carry it.
    """
    summary_dict["rounds_count"] = rounds_count
    return summary_dict


def _research_manager_node_factory(ticker: str):
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.olympus.hermes.skills import load_skill

    def _node(state: HermesState) -> dict[str, Any]:
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
            return {
                "phase7cd_debates": {ticker: _debate_output(summary.model_dump(mode="json"), 0)}
            }

        analyst = _analyst_for(state, ticker)
        analyst_conviction_score = int(analyst.get("conviction_score") or 0)

        skill_text = load_skill("research-manager")
        phase_inputs: dict[str, Any] = {
            "segment": f"research-manager-{ticker}",
            "ticker": ticker,
            "rounds": rounds,
            "analyst_payload": analyst,
            "bias_row": state.phase6_bias_row or {},
        }
        tools, execute_tool, _ = _debate_tools(state)
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=_shared_context(
                state, context_keys=(f"analyst/{ticker}",), data_layer_scope="ticker"
            ),
            output_model=DebateSummary,
            phase_slug=f"research-manager-{ticker}",
            tools=tools,
            execute_tool=execute_tool,
        )
        # Overwrite rounds with the deterministic record from state (the skill
        # is told to echo them verbatim, but state is authoritative for audit).
        canonical_rounds = [DebateRound.model_validate(r) for r in rounds]
        merged = result.model_copy(
            update={
                "rounds": canonical_rounds,
                "conviction_delta": _deterministic_conviction_delta(
                    result.net_stance, analyst_conviction_score
                ),
            }
        )
        return {
            "phase7cd_debates": {
                ticker: _debate_output(merged.model_dump(mode="json"), len(canonical_rounds))
            }
        }

    return _node


def _capped_tickers(tickers: list[str], held: Collection[str] = ()) -> list[str]:
    """Apply the same ``ATLAS_MAX_ANALYSTS`` cap Phase 7C uses, held-ticker aware (#936).

    The debate fan-out MUST cover the same set as the 7C analyst fan-out: every
    held (prior-book) ticker survives the cap, the budget is spent on non-held
    candidates, and held names over budget are kept (over budget) with a warning
    rather than dropped. See ``phase7c_analyst._capped_tickers`` — kept in lockstep.
    """
    max_analysts = int(os.environ.get("ATLAS_MAX_ANALYSTS", "0") or "0")
    if max_analysts <= 0 or len(tickers) <= max_analysts:
        return list(tickers)

    held_set = set(held)
    held_in_order = [t for t in tickers if t in held_set]
    candidates = [t for t in tickers if t not in held_set]

    if len(held_in_order) >= max_analysts:
        logger.warning(
            "Phase 7C-D: %d held tickers exceed ATLAS_MAX_ANALYSTS=%d; keeping ALL held "
            "(over budget) so no prior-book holding is dropped from the debate (#936): %s",
            len(held_in_order),
            max_analysts,
            ", ".join(held_in_order),
        )
        return held_in_order

    budget = max_analysts - len(held_in_order)
    kept_candidates = candidates[:budget]
    logger.info(
        "Phase 7C-D limited to %d/%d tickers (ATLAS_MAX_ANALYSTS=%d): %d held (always kept) "
        "+ %d candidates",
        max_analysts,
        len(tickers),
        max_analysts,
        len(held_in_order),
        len(kept_candidates),
    )
    kept = set(held_in_order) | set(kept_candidates)
    return [t for t in tickers if t in kept]


def _noop(_state: HermesState) -> dict[str, Any]:
    return {}


def build_phase7cd_round(
    round_number: int, tickers: list[str], held: Collection[str] = ()
) -> list[PipelinePhase]:
    """Return one round = bull phase + bear phase (sequential)."""
    capped = _capped_tickers(tickers, held=held)
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


def build_phase7cd_research_manager(
    tickers: list[str], held: Collection[str] = ()
) -> PipelinePhase:
    """Final per-ticker judgment phase — emits the DebateSummary."""
    capped = _capped_tickers(tickers, held=held)
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
    held: Collection[str] = (),
) -> list[PipelinePhase]:
    """Build the full Phase 7C-D pipeline for one debate.

    ``rounds`` is the *graph-compile-time* upper bound. The actual round
    count is read from ``state.config.preferences["debate_rounds"]`` at
    invocation time (defaults to 1, max 5). Compile time uses ``rounds``
    to decide how many bull/bear sub-phases to wire; runtime uses the
    state to decide how many of those sub-phases actually do work.

    ``held`` (prior-book holdings) is threaded to the cap so the debate fans
    out over the same ticker set as the 7C analysts — no holding dropped (#936).
    """
    bound = max(1, min(5, rounds))
    phases: list[PipelinePhase] = []
    for r in range(1, bound + 1):
        phases.extend(build_phase7cd_round(r, tickers, held=held))
    phases.append(build_phase7cd_research_manager(tickers, held=held))
    return phases


__all__ = [
    "DebateRound",
    "DebateRoundContribution",
    "DebateSummary",
    "clamp_debate_rounds",
    "build_phase7cd",
    "build_phase7cd_research_manager",
    "build_phase7cd_round",
]
