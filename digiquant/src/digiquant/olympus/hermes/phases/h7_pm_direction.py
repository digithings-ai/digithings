"""H7 — PM direction memo (direction + conviction rank only; no weights)."""

from __future__ import annotations

from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from digigraph.graph.research_agent import run_research_agent

from digiquant.olympus.atlas.phases._node_factory import (
    _shared_context,
    apply_web_grounding_to_inputs,
)
from digiquant.olympus.atlas.state import PhaseHermesState
from digiquant.olympus.hermes.candidates import holdings_from_prior_book
from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo
from digiquant.olympus.hermes.payloads import analyst_payloads, deliberation_summaries
from digiquant.olympus.hermes.phases.portfolio_common import _portfolio_grounding
from digiquant.olympus.hermes.skills import load_skill_full
from digiquant.olympus.hermes.state import HermesState

NODE_ID = "hermes/portfolio/pm-direction"
PHASE_NAME = "hermes_h7_pm_direction"
ARTIFACT_KEY = ("pm", "direction-memo")


def _current_weights_from_config(state: HermesState) -> dict[str, float]:
    raw = state.config.preferences.get("current_weights") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, val in raw.items():
        try:
            out[str(key)] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def _prior_direction_payload(state: HermesState) -> dict[str, Any]:
    row = (state.prior_context.latest_segments or {}).get("pm-direction-memo") or {}
    payload = row.get("payload") if isinstance(row, dict) else {}
    return dict(payload) if isinstance(payload, dict) else {}


def _prior_analyst_gaps(state: HermesState) -> dict[str, dict[str, Any]]:
    held = set(holdings_from_prior_book(state.prior_context.prior_book))
    gaps = held - set(analyst_payloads(state).keys())
    by_ticker = state.prior_context.prior_analyst_by_ticker
    return {ticker: dict(by_ticker[ticker]) for ticker in gaps if ticker in by_ticker}


def _focus_roster_tickers(state: HermesState) -> list[str]:
    tickers = [entry.ticker for entry in state.phase_hermes.focus_roster if entry.ticker]
    if tickers:
        return tickers
    return list(analyst_payloads(state).keys())


def _h7_node(state: HermesState) -> dict[str, Any]:
    current_weights = _current_weights_from_config(state)
    phase_inputs: dict[str, Any] = {
        "segment": NODE_ID,
        "bias_row": state.phase6_bias_row or {},
        "analyst_payloads": analyst_payloads(state),
        "debate_summaries": deliberation_summaries(state),
        "current_weights": current_weights,
        "evolution_mode": bool(current_weights),
        "prior_direction": _prior_direction_payload(state),
        "prior_book": list(state.prior_context.prior_book),
        "preferences": dict(state.config.preferences),
        "past_context": list(state.prior_context.decision_lessons),
        "active_theses": list(state.prior_context.active_theses),
        "portfolio_performance": dict(state.prior_context.portfolio_performance),
        "prior_analyst_gaps": _prior_analyst_gaps(state),
        "focus_roster": _focus_roster_tickers(state),
        "fed_odds": (state.phase6_bias_row or {}).get("fed_odds"),
    }
    tools, execute_tool, web_grounding = _portfolio_grounding(state, phase="h7_pm", segment=NODE_ID)
    phase_inputs = apply_web_grounding_to_inputs(
        phase_inputs,
        web_grounding=web_grounding,
        segment=NODE_ID,
        live_search=True,
    )
    result = run_research_agent(
        skill_text=load_skill_full("pm-direction"),
        phase_inputs=phase_inputs,
        shared_context=_shared_context(
            state,
            context_keys=("pm-rebalance", "digest-delta", "digest-baseline"),
            data_layer_scope="portfolio",
        ),
        output_model=PMDirectionMemo,
        phase_slug=NODE_ID,
        tools=tools,
        execute_tool=execute_tool,
    )
    memo = result.model_copy(update={"date": state.run_date})
    return {"phase_hermes": PhaseHermesState(pm_direction_memo=memo)}


def build_h7_pm_direction() -> PipelinePhase:
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_h7_node)],
    )


__all__ = ["NODE_ID", "PHASE_NAME", "build_h7_pm_direction"]
