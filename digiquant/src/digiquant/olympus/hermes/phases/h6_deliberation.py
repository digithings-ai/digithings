"""H6 — cyclic PM↔analyst deliberation per ticker (spec §10)."""

from __future__ import annotations

import logging
import os
from collections.abc import Collection
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)

from digigraph.graph.pipeline_builder import FanOutPhase, NodeSpec, PipelinePhase
from digigraph.graph.research_agent import run_research_agent
from digigraph.model_config import get_model_for_mode, get_model_for_phase

from digiquant.olympus.atlas.phases._node_factory import (
    _shared_context,
    apply_web_grounding_to_inputs,
)
from digiquant.olympus.atlas.state import PhaseError, PhaseHermesState
from digiquant.olympus.hermes.candidates import holdings_from_prior_book
from digiquant.olympus.hermes.focus_roster import (
    fanout_ticker,
    focus_roster_tickers,
    ticker_in_focus_roster,
    with_fanout_ticker,
)
from digiquant.olympus.hermes.models.deliberation import (
    CARRY_FINGERPRINT_SKIP,
    CARRY_LLM_FAILURE,
    DeliberationAnalystTurn,
    DeliberationPmTurn,
    DeliberationSummary,
    DeliberationTurn,
)
from digiquant.olympus.hermes.models.forecast import (
    AmendmentOutcome,
    EffectiveForecast,
    ForecastAmendment,
    ForecastAssessment,
    ForecastTerms,
    materialize_forecast_amendment,
    resolve_effective_forecast,
)
from digiquant.olympus.hermes.phases.portfolio_common import _portfolio_grounding
from digiquant.olympus.hermes.roster_cap import capped_tickers
from digiquant.olympus.hermes.skills import load_skill_full
from digiquant.olympus.hermes.state import HermesState
from digiquant.olympus.hermes.ticker_fingerprint import deliberation_skip_signal

logger = logging.getLogger(__name__)

NODE_ID = "hermes/portfolio/deliberation"
PHASE_NAME = "hermes_h6_deliberation"
DEFAULT_DELIBERATION_MAX_ROUNDS = 10
DEFAULT_DELIBERATION_MIN_ROUNDS = 2


def deliberation_max_rounds() -> int:
    """``ATLAS_DELIBERATION_MAX_ROUNDS`` env override; default 6."""
    raw = os.environ.get("ATLAS_DELIBERATION_MAX_ROUNDS", "").strip()
    if not raw:
        return DEFAULT_DELIBERATION_MAX_ROUNDS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_DELIBERATION_MAX_ROUNDS


def deliberation_min_rounds() -> int:
    """``ATLAS_DELIBERATION_MIN_ROUNDS`` env override; default 2.

    The PM may not register convergence before this many rounds. The floor of 2 forces at
    least one real challenge + analyst response, stopping the round-1 rubber-stamp the
    Jun-2026 audit found on every debate (#945). Set 1 to restore the cost-saving quiet
    path (instant convergence). The caller clamps it to ``max_rounds`` so it can never
    deadlock the loop.
    """
    raw = os.environ.get("ATLAS_DELIBERATION_MIN_ROUNDS", "").strip()
    if not raw:
        return DEFAULT_DELIBERATION_MIN_ROUNDS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_DELIBERATION_MIN_ROUNDS


def _prior_deliberation_summary(state: HermesState, ticker: str) -> dict[str, Any] | None:
    # Preferred: slim carry hydrated in preflight (#925). ``deliberation/*`` is excluded
    # from ``latest_segments`` so the full transcript never bloats every node — the slim
    # summary lives in ``prior_deliberation_by_ticker`` instead.
    slim = state.prior_context.prior_deliberation_by_ticker.get(ticker)
    if isinstance(slim, dict) and slim:
        return dict(slim)
    # Fallback for callers that still stash a full payload in latest_segments.
    row = state.prior_context.latest_segments.get(f"deliberation/{ticker}")
    if not isinstance(row, dict):
        return None
    payload = row.get("payload")
    return dict(payload) if isinstance(payload, dict) else None


def _analyst_payload(state: HermesState, ticker: str) -> dict[str, Any]:
    return dict(state.phase_hermes.asset_analysts.get(ticker, {}))


def _base_forecast_from_analyst(analyst: dict[str, Any]) -> ForecastAssessment | None:
    raw = analyst.get("forecast_assessment")
    if raw is None:
        return None
    try:
        return ForecastAssessment.model_validate(raw)
    except Exception:
        return None


def _attach_forecast_lineage(
    summary: DeliberationSummary,
    *,
    effective: EffectiveForecast | None,
    amendment: ForecastAmendment | None = None,
) -> DeliberationSummary:
    if effective is None:
        return summary
    update: dict[str, Any] = {
        "base_forecast_id": str(effective.base_forecast_id),
        "amendment_id": str(effective.amendment_id) if effective.amendment_id else None,
        "effective_forecast_id": str(effective.effective_id),
        "amendment_outcome": effective.amendment_outcome.value,
        "forecast_degradation": effective.degradation_reason,
        "effective_forecast": effective.model_dump(mode="json"),
    }
    if amendment is not None and effective.amendment_outcome is AmendmentOutcome.ACCEPTED:
        update["forecast_amendment"] = amendment.model_dump(mode="json")
    return summary.model_copy(update=update)


def _carry_prior_effective(
    *,
    prior: dict[str, Any],
    base: ForecastAssessment | None,
    state: HermesState,
) -> EffectiveForecast | None:
    """Fingerprint skip: preserve prior effective identity/time/hash when present."""
    raw_eff = prior.get("effective_forecast")
    if isinstance(raw_eff, dict) and raw_eff:
        try:
            prior_eff = EffectiveForecast.model_validate(raw_eff)
        except Exception:
            prior_eff = None
        else:
            cutoff = state.knowledge_cutoff_at
            if cutoff is not None and prior_eff.known_at > cutoff:
                if base is None:
                    return None
                return resolve_effective_forecast(
                    base=base,
                    amendment=None,
                    amendment_outcome=AmendmentOutcome.REJECTED,
                    degradation_reason="prior_amendment_after_knowledge_cutoff",
                    known_at=cutoff,
                )
            return prior_eff
    if base is None:
        return None
    return resolve_effective_forecast(base=base, amendment_outcome=AmendmentOutcome.NONE)


def _resolve_from_debate(
    *,
    state: HermesState,
    ticker: str,
    analyst: dict[str, Any],
    amendment_terms_raw: dict[str, Any] | None,
    amendment_reason: str,
) -> tuple[EffectiveForecast | None, ForecastAmendment | None]:
    base = _base_forecast_from_analyst(analyst)
    if base is None:
        return None, None
    cutoff = state.knowledge_cutoff_at or base.known_at
    if not amendment_terms_raw:
        return (
            resolve_effective_forecast(
                base=base,
                amendment=None,
                amendment_outcome=AmendmentOutcome.NONE,
                known_at=cutoff,
            ),
            None,
        )
    try:
        terms = ForecastTerms.model_validate(amendment_terms_raw)
        amendment = materialize_forecast_amendment(
            base=base,
            terms=terms,
            reason=amendment_reason or "h6_challenge_revision",
            source_run_id=str(state.run_id),
            provider_invocation_id=f"h6:{ticker}:{state.run_id}",
            effective_at=cutoff,
            known_at=cutoff,
        )
        return (
            resolve_effective_forecast(
                base=base,
                amendment=amendment,
                amendment_outcome=AmendmentOutcome.ACCEPTED,
                known_at=cutoff,
            ),
            amendment,
        )
    except Exception as exc:
        logger.warning(
            "H6 amendment for %s rejected (%s: %s); preserving base forecast",
            ticker,
            type(exc).__name__,
            exc,
        )
        return (
            resolve_effective_forecast(
                base=base,
                amendment=None,
                amendment_outcome=AmendmentOutcome.REJECTED,
                degradation_reason="amendment_rejected",
                known_at=cutoff,
            ),
            None,
        )


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
    escalated: bool = False,
    cap_reason: str | None = None,
) -> DeliberationSummary:
    return DeliberationSummary(
        ticker=ticker,
        converged=True,
        conclusion=conclusion,
        net_stance=net_stance,  # type: ignore[arg-type]
        conviction_delta=conviction_delta,
        transcript=transcript,
        escalated=escalated,
        cap_reason=cap_reason,
    )


def run_deliberation_loop(
    state: HermesState, ticker: str
) -> tuple[DeliberationSummary, dict[str, Any] | None]:
    """PM↔analyst loop until ``converged=true`` or ``ATLAS_DELIBERATION_MAX_ROUNDS`` cap.

    Returns the summary plus the last analyst-proposed complete ``forecast_amendment``
    terms dict (or ``None`` when the debate did not propose a replacement).
    """
    pm_skill = load_skill_full("deliberation")
    analyst_skill = load_skill_full("asset-analyst")
    tools, execute_tool, web_grounding = _portfolio_grounding(
        state, phase="h6_deliberation", segment=f"{NODE_ID}-{ticker}"
    )
    transcript: list[DeliberationTurn] = []
    round_number = 0
    prior_summary = _prior_deliberation_summary(state, ticker)
    eff_model = get_model_for_phase(f"{NODE_ID}-{ticker}") or get_model_for_mode()
    max_rounds = deliberation_max_rounds()
    min_rounds = min(deliberation_min_rounds(), max_rounds)
    last_amendment_terms: dict[str, Any] | None = None

    while True:
        round_number += 1
        pm_inputs = apply_web_grounding_to_inputs(
            {
                **_portfolio_phase_inputs(state, ticker),
                "segment": f"h6_pm_challenge-{ticker}",
                "role": "pm",
                "round_number": round_number,
                "transcript": [t.model_dump(mode="json") for t in transcript],
                "prior_deliberation": prior_summary,
            },
            web_grounding=web_grounding,
            segment=f"h6_pm_challenge-{ticker}",
            live_search=True,
        )
        pm_result = run_research_agent(
            skill_text=pm_skill,
            phase_inputs=pm_inputs,
            shared_context=_shared_context(
                state,
                # Atlas digest = the curated cross-checked read (#1674); analyst doc = the case.
                context_keys=(f"analyst/{ticker}", "digest", "digest-delta"),
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
        converged_signal = pm_turn.converged or (
            pm_turn.accepts_analyst_position and not pm_turn.open_questions
        )
        # #945: the PM may not converge before ``min_rounds`` (default 2) — forcing at least
        # one challenge + analyst response so the debate isn't a round-1 rubber-stamp. Set
        # ATLAS_DELIBERATION_MIN_ROUNDS=1 to restore the instant-convergence quiet path.
        if converged_signal and round_number >= min_rounds:
            if pm_turn.challenge:
                transcript.append(
                    DeliberationTurn(
                        role="pm", round_number=round_number, message=pm_turn.challenge
                    )
                )
            return (
                _deliberation_summary(
                    ticker=ticker,
                    transcript=transcript,
                    conclusion=pm_turn.conclusion or pm_turn.challenge,
                    net_stance=pm_turn.net_stance,
                    conviction_delta=pm_turn.conviction_delta,
                ),
                last_amendment_terms,
            )

        # Not converged, or held below the min-rounds floor: record the PM's challenge (with a
        # fallback so a gated convergence turn still carries a non-empty probe) and let the
        # analyst respond.
        transcript.append(
            DeliberationTurn(
                role="pm",
                round_number=round_number,
                message=(
                    pm_turn.challenge
                    or pm_turn.conclusion
                    or "PM requests further substantiation before converging."
                ),
            )
        )

        analyst_inputs = apply_web_grounding_to_inputs(
            {
                **_portfolio_phase_inputs(state, ticker),
                "segment": f"h6_analyst_response-{ticker}",
                "role": "analyst",
                "round_number": round_number,
                "pm_challenge": pm_turn.challenge,
                "transcript": [t.model_dump(mode="json") for t in transcript],
            },
            web_grounding=web_grounding,
            segment=f"h6_analyst_response-{ticker}",
            live_search=True,
        )
        analyst_result = run_research_agent(
            skill_text=analyst_skill,
            phase_inputs=analyst_inputs,
            shared_context=_shared_context(
                state,
                context_keys=(f"analyst/{ticker}", "digest", "digest-delta"),
                data_layer_scope="ticker",
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
        if isinstance(analyst_turn.forecast_amendment, dict):
            last_amendment_terms = dict(analyst_turn.forecast_amendment)
        transcript.append(
            DeliberationTurn(
                role="analyst", round_number=round_number, message=analyst_turn.response
            )
        )
        if analyst_turn.converged:
            return (
                _deliberation_summary(
                    ticker=ticker,
                    transcript=transcript,
                    conclusion=analyst_turn.conclusion or analyst_turn.response,
                    net_stance=analyst_turn.net_stance,
                    conviction_delta=analyst_turn.conviction_delta,
                ),
                last_amendment_terms,
            )
        if round_number >= max_rounds:
            return (
                _deliberation_summary(
                    ticker=ticker,
                    transcript=transcript,
                    conclusion=analyst_turn.conclusion or analyst_turn.response,
                    net_stance=analyst_turn.net_stance,
                    conviction_delta=analyst_turn.conviction_delta,
                    escalated=True,
                    cap_reason="max_rounds",
                ),
                last_amendment_terms,
            )


def _h6_node_factory(ticker: str):
    def _node(state: HermesState) -> dict[str, Any]:
        if not ticker_in_focus_roster(state, ticker):
            return {}
        analyst = _analyst_payload(state, ticker)
        if not analyst:
            return {}
        stance = str(analyst.get("stance") or "hold")
        base = _base_forecast_from_analyst(analyst)
        if deliberation_skip_signal(state, ticker, analyst_stance=stance):
            prior = _prior_deliberation_summary(state, ticker)
            if prior:
                carried = DeliberationSummary(
                    ticker=ticker,
                    converged=True,
                    # Slim carry (#925) stores conclusion under ``conclusion_excerpt``;
                    # the full-payload fallback uses ``conclusion`` / ``bull_thesis``.
                    conclusion=str(
                        prior.get("conclusion_excerpt")
                        or prior.get("conclusion")
                        or prior.get("bull_thesis")
                        or ""
                    ),
                    net_stance=prior.get("net_stance", "neutral"),  # type: ignore[arg-type]
                    conviction_delta=int(prior.get("conviction_delta") or 0),
                    transcript=[],
                    carried=True,
                    # Benign: nothing moved, so the prior debate still stands (#925).
                    carry_reason=CARRY_FINGERPRINT_SKIP,
                )
                prior_amendment = None
                raw_am = prior.get("forecast_amendment")
                if isinstance(raw_am, dict) and raw_am:
                    try:
                        prior_amendment = ForecastAmendment.model_validate(raw_am)
                    except Exception:
                        prior_amendment = None
                carried = _attach_forecast_lineage(
                    carried,
                    effective=_carry_prior_effective(prior=prior, base=base, state=state),
                    amendment=prior_amendment,
                )
                return {
                    "phase_hermes": PhaseHermesState(
                        deliberation_summaries={ticker: carried.model_dump(mode="json")}
                    )
                }

        try:
            summary, amendment_terms = run_deliberation_loop(state, ticker)
        except Exception as exc:  # LLM-output failure degrades this ticker, never the chain (#1665)
            stance_map = {"buy": "bullish", "sell": "bearish"}
            logger.warning(
                "H6 deliberation LLM failed for %s (%s: %s); carrying analyst stance",
                ticker,
                type(exc).__name__,
                exc,
            )
            fallback = DeliberationSummary(
                ticker=ticker,
                # NOT converged: no PM challenge ran, so there is no debate to converge.
                # Reporting ``converged=True`` here is what let a crashed deliberation reach
                # H7/H8 and the published document as a settled two-sided debate (#1742).
                converged=False,
                conclusion=str(analyst.get("thesis") or f"carried analyst stance: {stance}"),
                net_stance=stance_map.get(stance, "neutral"),  # type: ignore[arg-type]
                conviction_delta=0,
                transcript=[],
                carried=True,
                carry_reason=CARRY_LLM_FAILURE,
            )
            if base is not None:
                fallback = _attach_forecast_lineage(
                    fallback,
                    effective=resolve_effective_forecast(
                        base=base,
                        amendment=None,
                        amendment_outcome=AmendmentOutcome.LLM_FAILURE,
                        degradation_reason="llm_failure",
                        known_at=state.knowledge_cutoff_at or base.known_at,
                    ),
                )
            return {
                "phase_hermes": PhaseHermesState(
                    deliberation_summaries={ticker: fallback.model_dump(mode="json")}
                ),
                "errors": [
                    PhaseError(
                        phase=PHASE_NAME,
                        node=f"{NODE_ID}-{ticker}",
                        message=f"deliberation LLM failed; carried analyst stance: {exc}"[:500],
                        retryable=False,
                    )
                ],
            }
        effective, amendment = _resolve_from_debate(
            state=state,
            ticker=ticker,
            analyst=analyst,
            amendment_terms_raw=amendment_terms,
            amendment_reason=summary.conclusion or "h6_challenge_revision",
        )
        summary = _attach_forecast_lineage(
            summary,
            effective=effective,
            amendment=amendment,
        )
        result: dict[str, Any] = {
            "phase_hermes": PhaseHermesState(
                deliberation_summaries={ticker: summary.model_dump(mode="json")}
            )
        }
        if summary.escalated:
            result["errors"] = [
                PhaseError(
                    phase=PHASE_NAME,
                    node=f"{NODE_ID}-{ticker}",
                    message=(
                        f"H6 deliberation for {ticker} hit max_rounds cap "
                        f"({summary.cap_reason or 'max_rounds'})"
                    ),
                    retryable=False,
                )
            ]
        return result

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


def build_h6_from_state() -> FanOutPhase:
    """Runtime roster fan-out — one parallel ``Send`` worker per focus-roster ticker.

    Like H5, the roster is only known at run time, so ``FanOutPhase`` maps each ticker to a
    concurrent worker; the ``phase_hermes`` (deliberation) and ``errors`` reducers merge the
    parallel writes. Replaces the prior serial loop so each ticker's PM↔analyst debate runs
    concurrently instead of one after another.
    """

    def _worker(state: HermesState) -> dict[str, Any]:
        ticker = state.hermes_fanout_ticker
        if not ticker:
            return {}
        return _h6_node_factory(ticker)(state)

    return FanOutPhase(
        name=PHASE_NAME,
        worker=NodeSpec(name=f"{NODE_ID}-worker", run=_worker),
        items=focus_roster_tickers,
        with_item=with_fanout_ticker,
        item_key=fanout_ticker,
    )
