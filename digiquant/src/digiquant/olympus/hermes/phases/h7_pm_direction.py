"""H7 — PM direction memo (direction + conviction rank only; no weights).

WP4.5 (#2660): after LLM success or prior-memo fail-soft, deterministically bind
each roster row to the current run's effective forecast (never model-supplied IDs).
"""

from __future__ import annotations

import logging
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from digigraph.graph.research_agent import run_research_agent
from pydantic import ValidationError

from digiquant.olympus.atlas.phases._node_factory import (
    _shared_context,
    apply_web_grounding_to_inputs,
)
from digiquant.olympus.atlas.state import PhaseError, PhaseHermesState
from digiquant.olympus.hermes.candidates import holdings_from_prior_book
from digiquant.olympus.hermes.models.forecast import (
    AmendmentOutcome,
    EffectiveForecast,
    ForecastAssessment,
    resolve_effective_forecast,
)
from digiquant.olympus.hermes.models.pm_direction import (
    ForecastReference,
    PMDirectionMemo,
)
from digiquant.olympus.hermes.payloads import analyst_payloads, deliberation_summaries
from digiquant.olympus.hermes.phases.portfolio_common import _portfolio_grounding
from digiquant.olympus.hermes.skills import load_skill_full
from digiquant.olympus.hermes.state import HermesState

NODE_ID = "hermes/portfolio/pm-direction"
PHASE_NAME = "hermes_h7_pm_direction"
ARTIFACT_KEY = ("pm", "direction-memo")

logger = logging.getLogger(__name__)


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


def _prior_memo_fallback(state: HermesState) -> PMDirectionMemo | None:
    """Parse the prior pm-direction memo for the H7 LLM-failure carry (#1665)."""
    payload = _prior_direction_payload(state)
    if not payload:
        return None
    try:
        prior = PMDirectionMemo.model_validate(payload)
    except ValidationError:
        return None
    return prior.model_copy(update={"date": state.run_date})


def _effective_forecast_map(state: HermesState) -> dict[str, EffectiveForecast]:
    """Ticker → EffectiveForecast from the current run (H6 map, else H5 assessment).

    Never fabricates identity. Invalid blobs are skipped.
    """
    out: dict[str, EffectiveForecast] = {}
    for ticker, summary in deliberation_summaries(state).items():
        raw = summary.get("effective_forecast")
        if not isinstance(raw, dict) or not raw:
            continue
        try:
            out[ticker] = EffectiveForecast.model_validate(raw)
        except Exception:
            logger.debug("H7: skip invalid effective_forecast for %s", ticker)
            continue

    for ticker, payload in analyst_payloads(state).items():
        if ticker in out:
            continue
        raw_assessment = payload.get("forecast_assessment")
        if not isinstance(raw_assessment, dict) or not raw_assessment:
            continue
        try:
            base = ForecastAssessment.model_validate(raw_assessment)
        except Exception:
            continue
        cutoff = state.knowledge_cutoff_at or base.known_at
        out[ticker] = resolve_effective_forecast(
            base=base,
            amendment=None,
            amendment_outcome=AmendmentOutcome.NONE,
            known_at=cutoff,
        )
    return out


def _reference_for(
    *,
    ticker: str,
    effective: EffectiveForecast | None,
) -> ForecastReference | None:
    if effective is None:
        return None
    return ForecastReference(
        effective_forecast_id=effective.effective_id,
        base_forecast_id=effective.base_forecast_id,
        amendment_id=effective.amendment_id,
        ticker=ticker,
        degradation_reason=effective.degradation_reason,
    )


def _bind_forecast_references(memo: PMDirectionMemo, state: HermesState) -> PMDirectionMemo:
    """Attach authoritative ForecastReference per roster row; clear stale/prior IDs."""
    eff_map = _effective_forecast_map(state)
    roster = [
        row.model_copy(
            update={
                "forecast_reference": _reference_for(
                    ticker=row.ticker,
                    effective=eff_map.get(row.ticker),
                )
            }
        )
        for row in memo.roster
    ]
    return memo.model_copy(update={"roster": roster})


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
        return {"phase_hermes": PhaseHermesState(pm_direction_memo=memo), "errors": [err]}
    memo = result.model_copy(update={"date": state.run_date})
    memo = _bind_forecast_references(memo, state)
    return {"phase_hermes": PhaseHermesState(pm_direction_memo=memo)}


def build_h7_pm_direction() -> PipelinePhase:
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_h7_node)],
    )


__all__ = [
    "NODE_ID",
    "PHASE_NAME",
    "build_h7_pm_direction",
    "_bind_forecast_references",
    "_effective_forecast_map",
]
