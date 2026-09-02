"""H6 — cyclic PM↔analyst deliberation per ticker (spec §10)."""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)

from digigraph.graph.pipeline_builder import FanOutPhase, NodeSpec, PipelinePhase
from digigraph.graph.research_agent import run_research_agent
from digigraph.model_config import get_model_for_mode, get_model_for_phase

from digiquant.research.phases._node_factory import (
    _shared_context,
    build_grounding,
)
from digiquant.research.state import PhaseError, PhasePortfolioState
from digiquant.research.supabase_io import prior_book_current_weights
from digiquant.dashboard.envcompat import (
    ATTEMPT,
    DELIBERATION_MAX_ROUNDS,
    DELIBERATION_MIN_ROUNDS,
    env_lookup,
)
from digiquant.portfolio.candidates import holdings_from_prior_book
from digiquant.portfolio.focus_roster import (
    fanout_ticker,
    focus_roster_tickers,
    ticker_in_focus_roster,
    with_fanout_ticker,
)
from digiquant.portfolio.models.deliberation import (
    CARRY_ATTENTION,
    CARRY_FINGERPRINT_SKIP,
    CARRY_LLM_FAILURE,
    CARRY_LOW_VALUE,
    DeliberationAnalystTurn,
    DeliberationPmTurn,
    DeliberationSummary,
    DeliberationTurn,
    MissingFactProposal,
)
from digiquant.portfolio.models.forecast import (
    AmendmentOutcome,
    EffectiveForecast,
    ForecastAmendment,
    ForecastAssessment,
    ForecastTerms,
    fill_forecast_tenor_from_base,
    materialize_forecast_amendment,
    resolve_effective_forecast,
    unwrap_forecast_terms_payload,
)
from digiquant.portfolio.research_attention import research_attention_h6_enforce_path
from digiquant.portfolio.roster_cap import capped_tickers
from digiquant.portfolio.skills import load_skill_full
from digiquant.portfolio.state import PortfolioState
from digiquant.portfolio.ticker_fingerprint import deliberation_skip_signal
from digiquant.dashboard.research_retrieval.context_wiring import wire_h6_phase_inputs
from digiquant.dashboard.research_retrieval.evidence_bundle import evidence_bundle_writer_enabled
from digiquant.dashboard.research_retrieval.h6_amendment import (
    H6AmendmentOutcome,
    H6AmendmentResult,
    attempt_h6_evidence_amendment,
)
from digiquant.dashboard.research_retrieval.models import (
    TickerEvidenceBundle,
    TypedProvenance,
)
from digiquant.dashboard.research_retrieval.planner import (
    H6Action,
    H6Selection,
    H6SelectionMode,
    H6SelectionReason,
    assert_no_materiality_in_prompt,
    build_h6_decision_features,
    incumbent_fallback_selection,
    resolve_h6_selection_mode,
    select_h6,
)
from digiquant.dashboard.research_retrieval.store import EvidenceBundleStore, ResearchStateStore

logger = logging.getLogger(__name__)

NODE_ID = "portfolio/deliberation"
PHASE_NAME = "portfolio_h6_deliberation"
DEFAULT_DELIBERATION_MAX_ROUNDS = 10
DEFAULT_DELIBERATION_MIN_ROUNDS = 2


def _h6_attempt_id() -> str:
    raw = env_lookup(ATTEMPT).strip()
    return raw or "1"


def _base_bundle_for_ticker(state: PortfolioState, ticker: str) -> TickerEvidenceBundle | None:
    sym = ticker.strip().upper()
    raw = state.phase_portfolio.ticker_evidence_bundles.get(sym)
    if not isinstance(raw, dict):
        raw = state.phase_portfolio.ticker_evidence_bundles.get(ticker)
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return TickerEvidenceBundle.model_validate(raw)
    except Exception:
        return None


def _h6_grounding(state: PortfolioState, *, segment: str = ""):
    """H6 grounding — research tools only; generic web search forbidden (#2908)."""
    return build_grounding(
        use_data_tools=False,
        live_search=False,
        run_date=state.run_date,
        segment=segment or "portfolio/h6_deliberation",
        use_research_tools=True,
        research_phase="h6_deliberation",
        watchlist=tuple(state.config.watchlist),
    )


def _attach_evidence_amendment(
    summary: DeliberationSummary,
    *,
    base_bundle: TickerEvidenceBundle | None,
    amendment_result: H6AmendmentResult | None,
) -> DeliberationSummary:
    update: dict[str, Any] = {}
    if base_bundle is not None:
        update["base_bundle_id"] = str(base_bundle.bundle_id)
    if amendment_result is None:
        update["evidence_amendment_outcome"] = H6AmendmentOutcome.NONE.value
        return summary.model_copy(update=update)
    update["evidence_amendment_outcome"] = amendment_result.outcome.value
    if amendment_result.failure_reason:
        update["evidence_amendment_failure_reason"] = amendment_result.failure_reason
    if amendment_result.missing_fact_request is not None:
        update["missing_fact_request_id"] = str(amendment_result.missing_fact_request.request_id)
    if amendment_result.amendment is not None:
        update["evidence_amendment_id"] = str(amendment_result.amendment.amendment_id)
    return summary.model_copy(update=update)


def _maybe_attempt_missing_fact_amendment(
    *,
    state: PortfolioState,
    ticker: str,
    proposal: MissingFactProposal | None,
    base_bundle: TickerEvidenceBundle | None,
    execute_tool: Any,
    store: EvidenceBundleStore | None,
    prior_result: H6AmendmentResult | None,
) -> H6AmendmentResult | None:
    if prior_result is not None:
        return prior_result
    if proposal is None or base_bundle is None:
        return None
    cutoff = state.knowledge_cutoff_at or base_bundle.recorded_at
    provenance = TypedProvenance(
        source_run_id=str(state.run_id),
        attempt_id=_h6_attempt_id(),
        artifact_id=f"artifact-h6-{ticker.strip().upper()}",
    )
    return attempt_h6_evidence_amendment(
        proposal=proposal,
        base_bundle=base_bundle,
        ticker=ticker,
        execute_tool=execute_tool,
        store=store if evidence_bundle_writer_enabled() else None,
        recorded_at=cutoff,
        provenance=provenance,
    )


def deliberation_max_rounds() -> int:
    """``ATLAS_DELIBERATION_MAX_ROUNDS`` env override; default 6."""
    raw = env_lookup(DELIBERATION_MAX_ROUNDS).strip()
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
    raw = env_lookup(DELIBERATION_MIN_ROUNDS).strip()
    if not raw:
        return DEFAULT_DELIBERATION_MIN_ROUNDS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_DELIBERATION_MIN_ROUNDS


def _prior_deliberation_summary(state: PortfolioState, ticker: str) -> dict[str, Any] | None:
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


def _analyst_payload(state: PortfolioState, ticker: str) -> dict[str, Any]:
    return dict(state.phase_portfolio.asset_analysts.get(ticker, {}))


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
    state: PortfolioState,
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
    state: PortfolioState,
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
        payload = unwrap_forecast_terms_payload(amendment_terms_raw)
        if not isinstance(payload, dict):
            raise TypeError("amendment terms must be an object")
        terms = ForecastTerms.model_validate(fill_forecast_tenor_from_base(payload, base.terms))
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


def _portfolio_phase_inputs(state: PortfolioState, ticker: str) -> dict[str, Any]:
    inputs = {
        "ticker": ticker,
        "analyst_payload": _analyst_payload(state, ticker),
        "prior_book": list(state.prior_context.prior_book),
        "active_theses": list(state.prior_context.active_theses),
        "preferences": dict(state.config.preferences),
        "held_in_prior_book": ticker
        in set(holdings_from_prior_book(state.prior_context.prior_book)),
    }
    # WP11.3: selection materiality features must never enter provider prompts.
    assert_no_materiality_in_prompt(inputs)
    return inputs


def _roster_reason_for(state: PortfolioState, ticker: str) -> str:
    sym = ticker.strip().upper()
    for entry in state.phase_portfolio.focus_roster:
        if str(entry.ticker).strip().upper() == sym:
            return str(entry.roster_reason)
    return "other"


def _bundle_conflict_signal(bundle_dump: Mapping[str, Any] | None) -> bool:
    """True when the H5 bundle dump carries conflict diagnostics (if present)."""
    if not isinstance(bundle_dump, Mapping):
        return False
    conflicts = bundle_dump.get("conflicts")
    if isinstance(conflicts, (list, tuple)) and conflicts:
        return True
    # Bundle contract itself has no conflicts field; counter-evidence lives on forecast.
    return False


def _invalidation_risk_for(state: PortfolioState, ticker: str, analyst: Mapping[str, Any]) -> bool:
    """Thesis challenged / invalidation hit for this ticker → select H6."""
    sym = ticker.strip().upper()
    for thesis in state.prior_context.active_theses:
        if not isinstance(thesis, Mapping):
            continue
        status = str(thesis.get("status") or "").strip().lower()
        if status not in {"challenged", "invalidated"}:
            continue
        linked = str(thesis.get("ticker") or thesis.get("linked_ticker") or "").upper()
        if linked == sym:
            return True
        vehicles = thesis.get("candidate_tickers") or thesis.get("tickers") or []
        if isinstance(vehicles, (list, tuple)) and sym in {
            str(v).strip().upper() for v in vehicles
        }:
            return True
    risks = str(analyst.get("risks") or "").lower()
    if "invalidat" in risks or "thesis break" in risks or "breached" in risks:
        return True
    return False


def _resolve_h6_selection(state: PortfolioState, ticker: str, analyst: dict[str, Any]) -> H6Selection:
    """Build features + selection; planner errors → incumbent fallback (full H6)."""
    mode = resolve_h6_selection_mode()
    if mode is H6SelectionMode.OFF:
        # Off: no selection record required for actuation; still emit typed incumbent reason.
        held = ticker in set(holdings_from_prior_book(state.prior_context.prior_book))
        feats = build_h6_decision_features(
            ticker=ticker,
            roster_reason=_roster_reason_for(state, ticker),
            held=held,
            weight_pct=0.0,
            analyst=analyst,
        )
        return incumbent_fallback_selection(feats, mode=mode)

    try:
        held_set = set(holdings_from_prior_book(state.prior_context.prior_book))
        held = ticker.strip().upper() in held_set
        weights = prior_book_current_weights(list(state.prior_context.prior_book))
        weight_pct = float(weights.get(ticker.strip().upper(), 0.0) or 0.0)
        prior_analyst = state.prior_context.prior_analyst_by_ticker.get(ticker.strip().upper())
        if not isinstance(prior_analyst, dict):
            prior_analyst = state.prior_context.prior_analyst_by_ticker.get(ticker)
        bundle_dump = state.phase_portfolio.ticker_evidence_bundles.get(ticker.strip().upper())
        if not isinstance(bundle_dump, dict):
            bundle_dump = state.phase_portfolio.ticker_evidence_bundles.get(ticker)
        bundle_id = None
        if isinstance(bundle_dump, dict) and bundle_dump.get("bundle_id"):
            bundle_id = str(bundle_dump["bundle_id"])
        price_delta = state.price_deltas.get(ticker.strip().upper())
        if price_delta is None:
            price_delta = state.price_deltas.get(ticker)
        feats = build_h6_decision_features(
            ticker=ticker,
            roster_reason=_roster_reason_for(state, ticker),
            held=held,
            weight_pct=weight_pct,
            analyst=analyst,
            prior_analyst=prior_analyst if isinstance(prior_analyst, dict) else None,
            price_delta=float(price_delta) if price_delta is not None else None,
            evidence_bundle_id=bundle_id,
            has_evidence_conflict=_bundle_conflict_signal(bundle_dump),
            invalidation_risk=_invalidation_risk_for(state, ticker, analyst),
        )
        return select_h6(feats, mode=mode)
    except Exception as exc:
        logger.warning(
            "H6 selection failed for %s (%s: %s); falling back to full incumbent H6",
            ticker,
            type(exc).__name__,
            exc,
        )
        held = ticker in set(holdings_from_prior_book(state.prior_context.prior_book))
        feats = build_h6_decision_features(
            ticker=ticker,
            roster_reason=_roster_reason_for(state, ticker),
            held=held,
            weight_pct=0.0,
            analyst=analyst,
        )
        return incumbent_fallback_selection(feats, mode=mode)


def _attach_selection(summary: DeliberationSummary, selection: H6Selection) -> DeliberationSummary:
    return summary.model_copy(
        update={
            "selection_reason": selection.reason.value,
            "h6_selection": selection.model_dump(mode="json"),
        }
    )


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
    state: PortfolioState,
    ticker: str,
    *,
    base_bundle: TickerEvidenceBundle | None = None,
    evidence_bundle_store: EvidenceBundleStore | None = None,
    research_state_store: ResearchStateStore | None = None,
) -> tuple[DeliberationSummary, dict[str, Any] | None, H6AmendmentResult | None]:
    """PM↔analyst loop until ``converged=true`` or ``ATLAS_DELIBERATION_MAX_ROUNDS`` cap.

    Returns the summary, the last analyst-proposed complete ``forecast_amendment``
    terms dict (or ``None``), and optional WP11.4 evidence-amendment provenance.
    """
    pm_skill = load_skill_full("deliberation")
    analyst_skill = load_skill_full("deliberation-analyst-response")
    tools, execute_tool, _web_grounding = _h6_grounding(state, segment=f"{NODE_ID}-{ticker}")
    transcript: list[DeliberationTurn] = []
    round_number = 0
    prior_summary = _prior_deliberation_summary(state, ticker)
    eff_model = get_model_for_phase(f"{NODE_ID}-{ticker}") or get_model_for_mode()
    max_rounds = deliberation_max_rounds()
    min_rounds = min(deliberation_min_rounds(), max_rounds)
    last_amendment_terms: dict[str, Any] | None = None
    amendment_result: H6AmendmentResult | None = None
    pin = state.research_state_pin if isinstance(state.research_state_pin, dict) else None

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
        if base_bundle is not None:
            pm_inputs["base_evidence_bundle"] = base_bundle.model_dump(mode="json")
        if amendment_result is not None and amendment_result.supplemental_evidence:
            pm_inputs["evidence_amendment"] = [
                item.model_dump(mode="json") for item in amendment_result.supplemental_evidence
            ]
        pm_inputs = wire_h6_phase_inputs(
            pm_inputs,
            ticker=ticker,
            bundle=base_bundle,
            research_state_pin=pin,
            research_state_store=research_state_store,
            amendment=amendment_result.amendment if amendment_result else None,
        ).phase_inputs
        pm_result = run_research_agent(
            skill_text=pm_skill,
            phase_inputs=pm_inputs,
            shared_context=_shared_context(
                state,
                # research digest = the curated cross-checked read (#1674); analyst doc = the case.
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
        amendment_result = _maybe_attempt_missing_fact_amendment(
            state=state,
            ticker=ticker,
            proposal=pm_turn.missing_fact,
            base_bundle=base_bundle,
            execute_tool=execute_tool,
            store=evidence_bundle_store,
            prior_result=amendment_result,
        )
        converged_signal = pm_turn.converged or (
            pm_turn.accepts_analyst_position and not pm_turn.open_questions
        )
        # #945: the PM may not converge before ``min_rounds`` (default 2) — forcing at least
        # one challenge + analyst response so the debate isn't a round-1 rubber-stamp. Set
        # ATLAS_DELIBERATION_MIN_ROUNDS=1 to restore the instant-convergence quiet path.
        if converged_signal and round_number >= min_rounds:
            close = (pm_turn.conclusion or pm_turn.challenge).strip()
            transcript.append(
                DeliberationTurn(
                    role="pm",
                    round_number=round_number,
                    message=close or "PM converges.",
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
                amendment_result,
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

        analyst_inputs: dict[str, Any] = {
            **_portfolio_phase_inputs(state, ticker),
            "segment": f"h6_analyst_response-{ticker}",
            "role": "analyst",
            "round_number": round_number,
            "pm_challenge": pm_turn.challenge,
            "transcript": [t.model_dump(mode="json") for t in transcript],
        }
        if base_bundle is not None:
            analyst_inputs["base_evidence_bundle"] = base_bundle.model_dump(mode="json")
        if amendment_result is not None and amendment_result.supplemental_evidence:
            analyst_inputs["evidence_amendment"] = [
                item.model_dump(mode="json") for item in amendment_result.supplemental_evidence
            ]
        if amendment_result is not None and amendment_result.failure_reason:
            analyst_inputs["evidence_amendment_failure"] = amendment_result.failure_reason
        analyst_inputs = wire_h6_phase_inputs(
            analyst_inputs,
            ticker=ticker,
            bundle=base_bundle,
            research_state_pin=pin,
            research_state_store=research_state_store,
            amendment=amendment_result.amendment if amendment_result else None,
        ).phase_inputs
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
                amendment_result,
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
                amendment_result,
            )


def _h6_node_factory(
    ticker: str,
    evidence_bundle_store: EvidenceBundleStore | None = None,
    research_state_store: ResearchStateStore | None = None,
):
    def _node(state: PortfolioState) -> dict[str, Any]:
        if not ticker_in_focus_roster(state, ticker):
            return {}
        analyst = _analyst_payload(state, ticker)
        if not analyst:
            return {}
        stance = str(analyst.get("stance") or "hold")
        base = _base_forecast_from_analyst(analyst)
        selection = _resolve_h6_selection(state, ticker, analyst)
        h6_enforce = research_attention_h6_enforce_path(state, ticker, analyst)

        if h6_enforce == "carry":
            prior = _prior_deliberation_summary(state, ticker)
            stance_map = {"buy": "bullish", "sell": "bearish"}
            if prior:
                net_stance = prior.get("net_stance", "neutral")
                conviction_delta = int(prior.get("conviction_delta") or 0)
                conclusion = str(
                    prior.get("conclusion_excerpt")
                    or prior.get("conclusion")
                    or prior.get("bull_thesis")
                    or analyst.get("thesis")
                    or f"attention carry: {stance}"
                )
            else:
                net_stance = stance_map.get(stance, "neutral")
                conviction_delta = 0
                conclusion = str(analyst.get("thesis") or f"attention carry: {stance}")
            carried = DeliberationSummary(
                ticker=ticker,
                converged=True,
                conclusion=conclusion,
                net_stance=net_stance,  # type: ignore[arg-type]
                conviction_delta=conviction_delta,
                transcript=[],
                carried=True,
                carry_reason=CARRY_ATTENTION,
            )
            if prior:
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
            elif base is not None:
                carried = _attach_forecast_lineage(
                    carried,
                    effective=resolve_effective_forecast(
                        base=base,
                        amendment_outcome=AmendmentOutcome.NONE,
                        known_at=state.knowledge_cutoff_at or base.known_at,
                    ),
                )
            carried = _attach_selection(carried, selection)
            return {
                "phase_portfolio": PhasePortfolioState(
                    deliberation_summaries={ticker: carried.model_dump(mode="json")}
                )
            }

        # Enforce + low-value: carry with zero provider calls (typed reason).
        if (
            h6_enforce is None
            and selection.mode is H6SelectionMode.ENFORCE
            and selection.action is H6Action.CARRY
            and selection.reason is H6SelectionReason.LOW_VALUE_CARRY
        ):
            prior = _prior_deliberation_summary(state, ticker)
            stance_map = {"buy": "bullish", "sell": "bearish"}
            if prior:
                net_stance = prior.get("net_stance", "neutral")
                conviction_delta = int(prior.get("conviction_delta") or 0)
                conclusion = str(
                    prior.get("conclusion_excerpt")
                    or prior.get("conclusion")
                    or prior.get("bull_thesis")
                    or analyst.get("thesis")
                    or f"low-value carry: {stance}"
                )
            else:
                net_stance = stance_map.get(stance, "neutral")
                conviction_delta = 0
                conclusion = str(analyst.get("thesis") or f"low-value carry: {stance}")
            carried = DeliberationSummary(
                ticker=ticker,
                converged=True,
                conclusion=conclusion,
                net_stance=net_stance,  # type: ignore[arg-type]
                conviction_delta=conviction_delta,
                transcript=[],
                carried=True,
                carry_reason=CARRY_LOW_VALUE,
            )
            if prior:
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
            elif base is not None:
                carried = _attach_forecast_lineage(
                    carried,
                    effective=resolve_effective_forecast(
                        base=base,
                        amendment_outcome=AmendmentOutcome.NONE,
                        known_at=state.knowledge_cutoff_at or base.known_at,
                    ),
                )
            carried = _attach_selection(carried, selection)
            return {
                "phase_portfolio": PhasePortfolioState(
                    deliberation_summaries={ticker: carried.model_dump(mode="json")}
                )
            }

        # Enforce + select: skip fingerprint short-circuit so selected success meets round floor.
        allow_fingerprint_skip = h6_enforce != "challenge" and not (
            selection.mode is H6SelectionMode.ENFORCE and selection.action is H6Action.SELECT
        )
        if allow_fingerprint_skip and deliberation_skip_signal(
            state, ticker, analyst_stance=stance
        ):
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
                carried = _attach_selection(carried, selection)
                return {
                    "phase_portfolio": PhasePortfolioState(
                        deliberation_summaries={ticker: carried.model_dump(mode="json")}
                    )
                }

        base_bundle = _base_bundle_for_ticker(state, ticker)
        try:
            summary, amendment_terms, evidence_amendment = run_deliberation_loop(
                state,
                ticker,
                base_bundle=base_bundle,
                evidence_bundle_store=evidence_bundle_store,
                research_state_store=research_state_store,
            )
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
            fallback = _attach_selection(fallback, selection)
            return {
                "phase_portfolio": PhasePortfolioState(
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
        summary = _attach_evidence_amendment(
            summary,
            base_bundle=base_bundle,
            amendment_result=evidence_amendment,
        )
        summary = _attach_forecast_lineage(
            summary,
            effective=effective,
            amendment=amendment,
        )
        summary = _attach_selection(summary, selection)
        result: dict[str, Any] = {
            "phase_portfolio": PhasePortfolioState(
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
    evidence_bundle_store: EvidenceBundleStore | None = None,
    research_state_store: ResearchStateStore | None = None,
) -> PipelinePhase:
    capped = capped_tickers(tickers, held=held)
    if not capped:

        def _noop(_state: PortfolioState) -> dict[str, Any]:
            return {}

        return PipelinePhase(
            name=PHASE_NAME,
            nodes=[NodeSpec(name=f"{NODE_ID}-noop", run=_noop)],
        )
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[
            NodeSpec(
                name=f"{NODE_ID}-{ticker}",
                run=_h6_node_factory(ticker, evidence_bundle_store, research_state_store),
            )
            for ticker in capped
        ],
    )


def build_h6_from_state(
    evidence_bundle_store: EvidenceBundleStore | None = None,
    research_state_store: ResearchStateStore | None = None,
) -> FanOutPhase:
    """Runtime roster fan-out — one parallel ``Send`` worker per focus-roster ticker.

    Like H5, the roster is only known at run time, so ``FanOutPhase`` maps each ticker to a
    concurrent worker; the ``phase_portfolio`` (deliberation) and ``errors`` reducers merge the
    parallel writes. Replaces the prior serial loop so each ticker's PM↔analyst debate runs
    concurrently instead of one after another.
    """

    def _worker(state: PortfolioState) -> dict[str, Any]:
        ticker = state.portfolio_fanout_ticker
        if not ticker:
            return {}
        return _h6_node_factory(ticker, evidence_bundle_store, research_state_store)(state)

    return FanOutPhase(
        name=PHASE_NAME,
        worker=NodeSpec(name=f"{NODE_ID}-worker", run=_worker),
        items=focus_roster_tickers,
        with_item=with_fanout_ticker,
        item_key=fanout_ticker,
    )
