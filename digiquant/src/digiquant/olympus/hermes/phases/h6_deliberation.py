"""H6 — cyclic PM↔analyst deliberation per ticker (spec §10)."""

from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from digigraph.graph.research_agent import run_research_agent
from digigraph.model_config import get_model_for_mode, get_model_for_phase

from digiquant.olympus.atlas.phases._node_factory import _shared_context
from digiquant.olympus.atlas.state import PhaseHermesState
from digiquant.olympus.hermes.candidates import holdings_from_prior_book
from digiquant.olympus.hermes.focus_roster import ticker_in_focus_roster
from digiquant.olympus.hermes.models.deliberation import (
    DeliberationAnalystTurn,
    DeliberationPmTurn,
    DeliberationSummary,
    DeliberationTurn,
)
from digiquant.olympus.hermes.phases.portfolio_common import _portfolio_grounding
from digiquant.olympus.hermes.roster_cap import capped_tickers
from digiquant.olympus.hermes.skills import load_skill_full
from digiquant.olympus.hermes.state import HermesState
from digiquant.olympus.hermes.ticker_fingerprint import deliberation_skip_signal

logger = logging.getLogger(__name__)

NODE_ID = "hermes/portfolio/deliberation"
PHASE_NAME = "hermes_h6_deliberation"


def _prior_deliberation_summary(state: HermesState, ticker: str) -> dict[str, Any] | None:
    row = state.prior_context.latest_segments.get(f"deliberation/{ticker}")
    if not isinstance(row, dict):
        return None
    payload = row.get("payload")
    return dict(payload) if isinstance(payload, dict) else None


def _analyst_payload(state: HermesState, ticker: str) -> dict[str, Any]:
    return dict(state.phase_hermes.asset_analysts.get(ticker, {}))


def _portfolio_phase_inputs(state: HermesState, ticker: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "analyst_payload": _analyst_payload(state, ticker),
        "prior_book": list(state.prior_context.prior_book),
        "active_theses": list(state.prior_context.active_theses),
        "preferences": dict(state.config.preferences),
        "held_in_prior_book": ticker
        in set(holdings_from_prior_book(state.prior_context.prior_book)),
    }


def _deliberation_summary(
    *,
    ticker: str,
    transcript: list[DeliberationTurn],
    conclusion: str,
    net_stance: str,
    conviction_delta: int,
) -> DeliberationSummary:
    return DeliberationSummary(
        ticker=ticker,
        converged=True,
        conclusion=conclusion,
        net_stance=net_stance,  # type: ignore[arg-type]
        conviction_delta=conviction_delta,
        transcript=transcript,
    )


def run_deliberation_loop(state: HermesState, ticker: str) -> DeliberationSummary:
    """PM↔analyst loop until ``converged=true`` (no round cap)."""
    pm_skill = load_skill_full("deliberation")
    analyst_skill = load_skill_full("asset-analyst")
    tools, execute_tool, _ = _portfolio_grounding(state, phase="h6_deliberation")
    transcript: list[DeliberationTurn] = []
    round_number = 0
    prior_summary = _prior_deliberation_summary(state, ticker)
    eff_model = get_model_for_phase(f"{NODE_ID}-{ticker}") or get_model_for_mode()

    while True:
        round_number += 1
        pm_inputs = {
            **_portfolio_phase_inputs(state, ticker),
            "segment": f"h6_pm_challenge-{ticker}",
            "role": "pm",
            "round_number": round_number,
            "transcript": [t.model_dump(mode="json") for t in transcript],
            "prior_deliberation": prior_summary,
        }
        pm_result = run_research_agent(
            skill_text=pm_skill,
            phase_inputs=pm_inputs,
            shared_context=_shared_context(
                state,
                context_keys=(f"analyst/{ticker}",),
                data_layer_scope="portfolio",
            ),
            output_model=DeliberationPmTurn,
            phase_slug=f"h6_pm_challenge-{ticker}",
            tools=tools,
            execute_tool=execute_tool,
            model=eff_model,
        )
        pm_turn = (
            pm_result
            if isinstance(pm_result, DeliberationPmTurn)
            else DeliberationPmTurn.model_validate(pm_result)
        )
        if pm_turn.converged or (pm_turn.accepts_analyst_position and not pm_turn.open_questions):
            if pm_turn.challenge:
                transcript.append(
                    DeliberationTurn(
                        role="pm", round_number=round_number, message=pm_turn.challenge
                    )
                )
            return _deliberation_summary(
                ticker=ticker,
                transcript=transcript,
                conclusion=pm_turn.conclusion or pm_turn.challenge,
                net_stance=pm_turn.net_stance,
                conviction_delta=pm_turn.conviction_delta,
            )

        transcript.append(
            DeliberationTurn(role="pm", round_number=round_number, message=pm_turn.challenge)
        )

        analyst_inputs = {
            **_portfolio_phase_inputs(state, ticker),
            "segment": f"h6_analyst_response-{ticker}",
            "role": "analyst",
            "round_number": round_number,
            "pm_challenge": pm_turn.challenge,
            "transcript": [t.model_dump(mode="json") for t in transcript],
        }
        analyst_result = run_research_agent(
            skill_text=analyst_skill,
            phase_inputs=analyst_inputs,
            shared_context=_shared_context(
                state, context_keys=(f"analyst/{ticker}",), data_layer_scope="ticker"
            ),
            output_model=DeliberationAnalystTurn,
            phase_slug=f"h6_analyst_response-{ticker}",
            tools=tools,
            execute_tool=execute_tool,
            model=eff_model,
        )
        analyst_turn = (
            analyst_result
            if isinstance(analyst_result, DeliberationAnalystTurn)
            else DeliberationAnalystTurn.model_validate(analyst_result)
        )
        transcript.append(
            DeliberationTurn(
                role="analyst", round_number=round_number, message=analyst_turn.response
            )
        )
        if analyst_turn.converged:
            return _deliberation_summary(
                ticker=ticker,
                transcript=transcript,
                conclusion=analyst_turn.conclusion or analyst_turn.response,
                net_stance=analyst_turn.net_stance,
                conviction_delta=analyst_turn.conviction_delta,
            )


def _h6_node_factory(ticker: str):
    def _node(state: HermesState) -> dict[str, Any]:
        if not ticker_in_focus_roster(state, ticker):
            return {}
        analyst = _analyst_payload(state, ticker)
        if not analyst:
            return {}
        stance = str(analyst.get("stance") or "hold")
        if deliberation_skip_signal(state, ticker, analyst_stance=stance):
            prior = _prior_deliberation_summary(state, ticker)
            if prior:
                carried = DeliberationSummary(
                    ticker=ticker,
                    converged=True,
                    conclusion=str(prior.get("conclusion") or prior.get("bull_thesis") or ""),
                    net_stance=prior.get("net_stance", "neutral"),  # type: ignore[arg-type]
                    conviction_delta=int(prior.get("conviction_delta") or 0),
                    transcript=[],
                    carried=True,
                )
                return {
                    "phase_hermes": PhaseHermesState(
                        deliberation_summaries={ticker: carried.model_dump(mode="json")}
                    )
                }

        summary = run_deliberation_loop(state, ticker)
        return {
            "phase_hermes": PhaseHermesState(
                deliberation_summaries={ticker: summary.model_dump(mode="json")}
            )
        }

    return _node


def build_h6_deliberation(
    tickers: list[str],
    *,
    held: Collection[str] = (),
) -> PipelinePhase:
    capped = capped_tickers(tickers, held=held)
    if not capped:

        def _noop(_state: HermesState) -> dict[str, Any]:
            return {}

        return PipelinePhase(
            name=PHASE_NAME,
            nodes=[NodeSpec(name=f"{NODE_ID}-noop", run=_noop)],
        )
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[
            NodeSpec(name=f"{NODE_ID}-{ticker}", run=_h6_node_factory(ticker)) for ticker in capped
        ],
    )


def build_h6_deliberation_phases(
    watchlist: list[str],
    *,
    held: Collection[str] = (),
) -> list[PipelinePhase]:
    return [build_h6_deliberation(watchlist, held=held)]
