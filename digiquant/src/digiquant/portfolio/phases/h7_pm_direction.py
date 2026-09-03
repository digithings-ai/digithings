"""H7 — PM direction memo (direction + rank + confidence; no weights).

WP4.5 (#2660): after LLM success or prior-memo fail-soft, deterministically bind
each roster row to the current run's effective forecast (never model-supplied IDs).

WP-G: roster rows may carry ``confidence`` in ``[0, 1]``. Rank remains order, not
size. H8 scales each long by that confidence (cash-first).

WP5.4 (#2684): at this existing H6→H7 boundary, attach cutoff-safe shadow
calibration artifacts into typed state for H9 persistence. Observational only —
never feeds incumbent H8 and does not add a graph node.
"""

from __future__ import annotations

import logging
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import ValidationError

from digiquant.dashboard.research_retrieval.context_wiring import wire_h7_phase_inputs
from digiquant.dashboard.research_retrieval.store import ResearchStateStore
from digiquant.portfolio.candidates import holdings_from_prior_book
from digiquant.portfolio.forecast_calibration import (
    ShadowCalibrationAttachment,
    attach_shadow_calibrations_from_state,
)
from digiquant.portfolio.models.forecast_calibration import ForecastOutcome
from digiquant.portfolio.models.pm_direction import (
    PMDirectionMemo,
    bind_forecast_references,
)
from digiquant.portfolio.payloads import analyst_payloads, deliberation_summaries
from digiquant.portfolio.phases.portfolio_common import _portfolio_grounding
from digiquant.portfolio.skills import load_skill_full
from digiquant.portfolio.state import PortfolioState
from digiquant.research.forecast_outcomes import list_resolved_outcomes_as_of
from digiquant.research.phases._node_factory import (
    _shared_context,
    apply_web_grounding_to_inputs,
)
from digiquant.research.state import PhaseError, PhasePortfolioState
from digiquant.research.supabase_io import SupabaseClient
from digiquant.tool_rounds import run_olympus_research_agent as run_research_agent

NODE_ID = "portfolio/pm-direction"
PHASE_NAME = "portfolio_h7_pm_direction"
ARTIFACT_KEY = ("pm", "direction-memo")

logger = logging.getLogger(__name__)


def _current_weights_from_config(state: PortfolioState) -> dict[str, float]:
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


def _prior_direction_payload(state: PortfolioState) -> dict[str, Any]:
    row = (state.prior_context.latest_segments or {}).get("pm-direction-memo") or {}
    payload = row.get("payload") if isinstance(row, dict) else {}
    return dict(payload) if isinstance(payload, dict) else {}


def _prior_analyst_gaps(state: PortfolioState) -> dict[str, dict[str, Any]]:
    held = set(holdings_from_prior_book(state.prior_context.prior_book))
    gaps = held - set(analyst_payloads(state).keys())
    by_ticker = state.prior_context.prior_analyst_by_ticker
    return {ticker: dict(by_ticker[ticker]) for ticker in gaps if ticker in by_ticker}


def _focus_roster_tickers(state: PortfolioState) -> list[str]:
    tickers = [entry.ticker for entry in state.phase_portfolio.focus_roster if entry.ticker]
    if tickers:
        return tickers
    return list(analyst_payloads(state).keys())


def _prior_memo_fallback(state: PortfolioState) -> PMDirectionMemo | None:
    """Parse the prior pm-direction memo for the H7 LLM-failure carry (#1665)."""
    payload = _prior_direction_payload(state)
    if not payload:
        return None
    try:
        prior = PMDirectionMemo.model_validate(payload)
    except ValidationError:
        return None
    return prior.model_copy(update={"date": state.run_date})


def _bind_forecast_references(memo: PMDirectionMemo, state: PortfolioState) -> PMDirectionMemo:
    """Attach authoritative ForecastReference per roster row from *this* run's map."""
    return bind_forecast_references(
        memo,
        deliberation_by_ticker=deliberation_summaries(state),
    )


def _load_cutoff_outcomes(
    *,
    client: SupabaseClient | None,
    state: PortfolioState,
) -> list[ForecastOutcome]:
    cutoff = state.knowledge_cutoff_at
    if client is None or cutoff is None:
        return []
    try:
        return list_resolved_outcomes_as_of(client=client, knowledge_cutoff_at=cutoff)
    except Exception as exc:
        logger.warning(
            "H7 shadow calibration: outcome load failed (%s: %s); empty cohort",
            type(exc).__name__,
            exc,
        )
        return []


def _attach_shadow_calibration(
    state: PortfolioState,
    *,
    client: SupabaseClient | None,
) -> ShadowCalibrationAttachment:
    """Observational attach at H6→H7 boundary — never raises into H7 direction."""
    try:
        outcomes = _load_cutoff_outcomes(client=client, state=state)
        return attach_shadow_calibrations_from_state(state, outcomes=outcomes)
    except Exception as exc:
        logger.warning(
            "H7 shadow calibration attach failed (%s: %s); empty attachment",
            type(exc).__name__,
            exc,
        )
        return ShadowCalibrationAttachment(calibrations=(), calibrated_forecasts=())


def _phase_portfolio_with_shadow(
    *,
    memo: PMDirectionMemo | None,
    shadow: ShadowCalibrationAttachment,
) -> PhasePortfolioState:
    return PhasePortfolioState(
        pm_direction_memo=memo,
        forecast_calibrations=shadow.calibration_dumps(),
        calibrated_forecasts=shadow.calibrated_forecast_dumps(),
    )


def _h7_node(
    state: PortfolioState,
    *,
    client: SupabaseClient | None = None,
    research_state_store: ResearchStateStore | None = None,
) -> dict[str, Any]:
    """H7 node body; ``client`` optional for cutoff-safe outcome load (WP5.4)."""
    # WP5.4: attach before LLM so fail-soft memo path still carries shadows.
    shadow = _attach_shadow_calibration(state, client=client)

    current_weights = _current_weights_from_config(state)
    lesson_pin = state.outcome_lesson_pin if isinstance(state.outcome_lesson_pin, dict) else None
    legacy_lessons = (
        []
        if lesson_pin and lesson_pin.get("lesson_version_id")
        else list(state.prior_context.decision_lessons)
    )
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
        "past_context": legacy_lessons,
        "active_theses": list(state.prior_context.active_theses),
        "portfolio_performance": dict(state.prior_context.portfolio_performance),
        "prior_analyst_gaps": _prior_analyst_gaps(state),
        "focus_roster": _focus_roster_tickers(state),
        "fed_odds": (state.phase6_bias_row or {}).get("fed_odds"),
    }
    pin = state.research_state_pin if isinstance(state.research_state_pin, dict) else None
    prereq = (
        state.h7_prerequisite_snapshot if isinstance(state.h7_prerequisite_snapshot, dict) else None
    )
    phase_inputs = wire_h7_phase_inputs(
        phase_inputs,
        research_state_pin=pin,
        research_state_store=research_state_store,
        h7_prerequisite_snapshot=prereq,
        outcome_lesson_pin=lesson_pin,
        analyst_payloads=analyst_payloads(state),
        deliberation_summaries=deliberation_summaries(state),
        shadow_calibrations=shadow.calibration_dumps(),
        calibrated_forecasts=shadow.calibrated_forecast_dumps(),
        prior_direction=_prior_direction_payload(state),
        decision_lessons=tuple(legacy_lessons),
        focus_roster=tuple(_focus_roster_tickers(state)),
    ).phase_inputs
    tools, execute_tool, web_grounding = _portfolio_grounding(state, phase="h7_pm", segment=NODE_ID)
    phase_inputs = apply_web_grounding_to_inputs(
        phase_inputs,
        web_grounding=web_grounding,
        segment=NODE_ID,
        live_search=True,
    )
    try:
        result = run_research_agent(
            skill_text=load_skill_full("pm-direction"),
            phase_inputs=phase_inputs,
            shared_context=_shared_context(
                state,
                # `digest-baseline` is never written by anything — publish_phase.py
                # writes plain `digest` on baseline runs, `digest-delta` on delta runs.
                # The old tuple silently dropped the freshest baseline digest from
                # context every Monday (#1270).
                context_keys=("pm-rebalance", "digest", "digest-delta"),
                data_layer_scope="portfolio",
            ),
            output_model=PMDirectionMemo,
            phase_slug=NODE_ID,
            tools=tools,
            execute_tool=execute_tool,
        )
    except Exception as exc:  # LLM-output failure degrades H7, never the chain (#1665)
        # Fallback: carry the PRIOR direction memo re-dated to today. Held names it
        # addressed keep their directions; anything it misses is covered by the
        # #1649 memo-unaddressed held-carry, so the book still coheres and COMMITS —
        # which keeps retry_worthy False and the run single-attempt. No parseable
        # prior → memo None (H8's legacy sizing path).
        # WP4.5: re-bind forecast references from *this* run's effective map —
        # prior memo IDs must not masquerade as today's authoritative forecasts.
        memo = _prior_memo_fallback(state)
        if memo is not None:
            memo = _bind_forecast_references(memo, state)
        mode = "prior memo carried" if memo is not None else "no prior memo; legacy sizing"
        logger.warning("H7 pm-direction LLM failed (%s: %s); %s", type(exc).__name__, exc, mode)
        err = PhaseError(
            phase=PHASE_NAME,
            node=NODE_ID,
            message=f"pm-direction LLM failed ({mode}): {exc}"[:500],
            retryable=False,
        )
        return {
            "phase_portfolio": _phase_portfolio_with_shadow(memo=memo, shadow=shadow),
            "errors": [err],
        }
    memo = result.model_copy(update={"date": state.run_date})
    memo = _bind_forecast_references(memo, state)
    return {"phase_portfolio": _phase_portfolio_with_shadow(memo=memo, shadow=shadow)}


def build_h7_pm_direction(
    *,
    client: SupabaseClient | None = None,
    research_state_store: ResearchStateStore | None = None,
) -> PipelinePhase:
    """Build H7; optional ``client`` loads cutoff-safe outcomes for shadow calibration."""

    def _bound(state: PortfolioState) -> dict[str, Any]:
        return _h7_node(state, client=client, research_state_store=research_state_store)

    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_bound)],
    )


__all__ = [
    "NODE_ID",
    "PHASE_NAME",
    "build_h7_pm_direction",
    "_bind_forecast_references",
    "_h7_node",
]
