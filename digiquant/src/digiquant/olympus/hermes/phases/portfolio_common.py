"""Shared helpers for H5/H6 portfolio-track Hermes nodes."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import UTC, date, datetime
from typing import (  # scored-lint suppression: heterogeneous graph / dict shapes
    Any,
    TypeVar,
)

from digigraph.graph.research_agent import run_research_agent
from digigraph.model_config import get_model_for_mode, get_model_for_phase
from digigraph.usage import provider_calls_snapshot
from pydantic import BaseModel, ValidationError

from digiquant.olympus.atlas.data.queries import MARKET_DATA_TABLES
from digiquant.olympus.atlas.phases._node_factory import (
    _shared_context,
    apply_web_grounding_to_inputs,
    build_grounding,
)
from digiquant.olympus.atlas.state import PhaseError, refresh_scope_forces_full
from digiquant.olympus.edit_mode import (
    DocumentPatch,
    EditMode,
    PriorPublished,
    artifact_document_key,
    merge_document_patch,
    resolve_edit_mode,
)
from digiquant.olympus.edit_mode.merge import MergeError, coerce_document_patch
from digiquant.olympus.hermes.candidates import holdings_from_prior_book
from digiquant.olympus.hermes.models.analyst import AnalystPayload
from digiquant.olympus.hermes.models.forecast import (
    ForecastAssessment,
    ForecastTerms,
    PriceAnchor,
    PriceAnchorStatus,
    forecast_assessment_id,
    forecast_terms_content_hash,
)
from digiquant.olympus.hermes.research_attention import (
    apply_analyst_metric_patch,
    research_attention_h5_enforce_path,
)
from digiquant.olympus.hermes.skills import load_skill_edit, load_skill_full
from digiquant.olympus.hermes.state import HermesState
from digiquant.olympus.hermes.ticker_fingerprint import news_hash_for_ticker, ticker_triage_signal
from digiquant.olympus.research_retrieval.blinding import RetrievalPhase
from digiquant.olympus.research_retrieval.evidence_bundle import (
    build_h5_evidence_bundle,
    cite_evidence_bundle_on_forecast,
    facts_from_phase_inputs,
    publish_h5_evidence_bundle,
    resolve_h5_state_version_id,
)
from digiquant.olympus.research_retrieval.models import TickerEvidenceBundle, TypedProvenance
from digiquant.olympus.research_retrieval.store import EvidenceBundleStore
from digiquant.olympus.temporal import require_knowledge_cutoff_at

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_FORECAST_WHOLE_PATHS = frozenset({"/body/forecast", "/forecast"})
_FORECAST_ASSESSMENT_PATHS = frozenset({"/body/forecast_assessment", "/forecast_assessment"})
_FORECAST_NESTED_PREFIXES = ("/body/forecast/", "/forecast/")


def _resolve_linked_thesis(
    thesis_id: str | None, active_theses: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Return the single active-thesis row matching ``thesis_id`` (or None)."""
    if not thesis_id:
        return None
    for row in active_theses:
        if isinstance(row, dict) and str(row.get("thesis_id") or "") == thesis_id:
            return dict(row)
    return None


class _TickerPriorLoader:
    def __init__(self, state: HermesState, artifact_key: tuple[str, str]) -> None:
        self._state = state
        self._artifact_key = artifact_key

    def load(self, artifact_key: tuple[str, str], run_date: date) -> PriorPublished | None:
        del artifact_key
        doc_key = artifact_document_key(self._artifact_key)
        row = self._state.prior_context.latest_segments.get(doc_key)
        if not isinstance(row, dict):
            slim = self._state.prior_context.prior_analyst_by_ticker.get(self._artifact_key[1], {})
            if not slim:
                return None
            return PriorPublished(
                date=date.fromisoformat(str(slim.get("date", run_date))[:10]),
                document_key=doc_key,
                payload={"body": dict(slim)},
            )
        payload = row.get("payload")
        if not isinstance(payload, dict):
            return None
        raw_date = row.get("date")
        try:
            prior_date = date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            prior_date = run_date
        return PriorPublished(date=prior_date, document_key=doc_key, payload=payload)


def analyst_artifact_key(ticker: str) -> tuple[str, str]:
    return ("analyst", ticker.strip().upper())


def _body_from_prior_payload(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("body", payload)
    return body if isinstance(body, dict) else {}


def prior_has_typed_forecast(body: dict[str, Any] | None) -> bool:
    """True when prior analyst body carries valid typed forecast terms or assessment."""
    if not isinstance(body, dict):
        return False
    raw_assessment = body.get("forecast_assessment")
    if raw_assessment is not None:
        try:
            ForecastAssessment.model_validate(raw_assessment)
            return True
        except ValidationError:
            return False
    raw_terms = body.get("forecast")
    if raw_terms is not None:
        try:
            ForecastTerms.model_validate(raw_terms)
            return True
        except ValidationError:
            return False
    return False


def resolve_analyst_edit_mode(state: HermesState, ticker: str) -> EditMode:
    artifact_key = analyst_artifact_key(ticker)
    prior = state.prior_context.prior_analyst_by_ticker.get(ticker)
    prior_stance = prior.get("stance") if isinstance(prior, dict) else None
    triage = ticker_triage_signal(
        state,
        ticker,
        current_stance=prior_stance,
        prior_stance=prior_stance,
        prior_news_hash=str((prior or {}).get("fingerprint_news_hash") or "") or None,
    )
    mode = resolve_edit_mode(
        artifact_key=artifact_key,
        run_date=state.run_date,
        prior_loader=_TickerPriorLoader(state, artifact_key),
        triage=triage,
        force_full_rewrite=refresh_scope_forces_full(state.refresh_scope, artifact="segment")
        or state.refresh_scope == "hermes",
    )
    if mode == "full":
        return mode
    # Legacy docs without typed forecast terms must not skip/edit — force full
    # analysis rather than synthesizing economics from conviction/price_targets.
    prior_pub = _TickerPriorLoader(state, artifact_key).load(artifact_key, state.run_date)
    prior_body = _body_from_prior_payload(prior_pub.payload) if prior_pub is not None else None
    if not prior_has_typed_forecast(prior_body):
        return "full"
    return mode


def build_analyst_document(
    *,
    ticker: str,
    run_date: date,
    body: dict[str, Any],
    linked_thesis_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "doc_type": "asset_recommendation",
        "date": run_date.isoformat(),
        "ticker": ticker,
        "meta": {
            "category": "deep-dive",
            "analyst": "asset_analyst",
            "thesis_id": linked_thesis_id,
        },
        "body": body,
    }


def analyst_body_from_payload(payload: AnalystPayload) -> dict[str, Any]:
    data = payload.model_dump(mode="json")
    ticker = data.pop("ticker")
    body: dict[str, Any] = {
        "ticker": ticker,
        "conviction_score": data["conviction_score"],
        "stance": data["stance"],
        "thesis": data["thesis"],
        "risks": data["risks"],
        "sources": data["sources"],
        "fundamentals": data["fundamentals"],
        "technicals": data["technicals"],
        "headwinds": data["headwinds"],
        "tailwinds": data["tailwinds"],
        "bull_case": data["bull_case"],
        "bear_case": data["bear_case"],
        "price_targets": data["price_targets"],
        "expectations": data["expectations"],
        "fingerprint_news_hash": data["fingerprint_news_hash"],
        "context": {
            "price": None,
            "day_pct": None,
            "segment_bias": "neutral",
        },
        "verdict": {
            "bias": _stance_to_bias(data["stance"]),
            "thesis_status": "ACTIVE",
            "recommended_weight_pct": None,
            "rationale": data["thesis"][:2000],
        },
    }
    if data.get("evidence") is not None:
        body["evidence"] = data["evidence"]
    if data.get("forecast") is not None:
        body["forecast"] = data["forecast"]
    if data.get("forecast_assessment") is not None:
        body["forecast_assessment"] = data["forecast_assessment"]
    return body


def _stance_to_bias(stance: str) -> str:
    return {
        "buy": "overweight",
        "sell": "underweight",
        "watch": "neutral",
        "hold": "neutral",
    }.get(stance, "neutral")


def reject_partial_forecast_edits(patch: DocumentPatch) -> None:
    """Forbid nested forecast patches and any forecast_assessment mutation.

    Edit mode may replace the entire ``forecast`` object or leave it untouched.
    Partial field writes would silently diverge from immutable assessment lineage.
    """
    for op in patch.ops:
        path = op.path
        if path in _FORECAST_ASSESSMENT_PATHS or any(
            path.startswith(f"{p}/") for p in _FORECAST_ASSESSMENT_PATHS
        ):
            raise MergeError("forecast_assessment is immutable; cannot patch assessment identity")
        if path in _FORECAST_WHOLE_PATHS:
            continue
        if any(path.startswith(prefix) for prefix in _FORECAST_NESTED_PREFIXES):
            raise MergeError("partial nested forecast edit rejected; replace entire /body/forecast")


def materialize_forecast_assessment(
    *,
    ticker: str,
    terms: ForecastTerms,
    source_run_id: str,
    provider_invocation_id: str,
    prompt_version: str,
    artifact_version: str,
    price_anchor: PriceAnchor,
    effective_at: datetime,
    known_at: datetime,
) -> ForecastAssessment:
    """Build an immutable base :class:`ForecastAssessment` from validated terms."""
    content_hash = forecast_terms_content_hash(terms)
    return ForecastAssessment(
        forecast_id=forecast_assessment_id(
            ticker=ticker,
            source_run_id=source_run_id,
            content_hash=content_hash,
        ),
        ticker=ticker.strip().upper(),
        terms=terms,
        source_run_id=source_run_id,
        provider_invocation_id=provider_invocation_id,
        prompt_version=prompt_version,
        artifact_version=artifact_version,
        price_anchor=price_anchor,
        effective_at=effective_at,
        known_at=known_at,
        content_hash=content_hash,
    )


def _h5_price_anchor(_state: HermesState, _ticker: str) -> PriceAnchor:
    """H5 state carries pct deltas, not absolute marks — typed unavailability."""
    return PriceAnchor(
        status=PriceAnchorStatus.UNAVAILABLE,
        unavailable_reason="mark_price_not_available_in_h5_state",
    )


def _provider_invocation_id(*, phase_slug: str, run_id: str, ticker: str) -> str:
    calls = provider_calls_snapshot()
    if calls:
        return str(calls[-1].call_id)
    return f"provider_invocation_unavailable:{run_id}:{ticker.upper()}:{phase_slug}"


def _skill_versions(mode: EditMode) -> tuple[str, str]:
    skill_text = (
        load_skill_edit("asset-analyst") if mode == "edit" else load_skill_full("asset-analyst")
    )
    digest = hashlib.sha256(skill_text.encode("utf-8")).hexdigest()[:16]
    prompt_version = f"asset-analyst-{mode}@{digest}"
    artifact_version = f"h5-{mode}@1"
    return prompt_version, artifact_version


def _cutoff_or_run_date(state: HermesState) -> datetime:
    try:
        return require_knowledge_cutoff_at(state)
    except ValueError:
        return datetime(
            state.run_date.year,
            state.run_date.month,
            state.run_date.day,
            tzinfo=UTC,
        )


def _assessment_from_body(body: dict[str, Any]) -> ForecastAssessment | None:
    raw = body.get("forecast_assessment")
    if raw is None:
        return None
    try:
        return ForecastAssessment.model_validate(raw)
    except ValidationError:
        return None


def _terms_from_body(body: dict[str, Any]) -> ForecastTerms | None:
    raw = body.get("forecast")
    if raw is None:
        return None
    try:
        return ForecastTerms.model_validate(raw)
    except ValidationError:
        return None


def _attach_forecast_lineage(
    *,
    payload: AnalystPayload,
    state: HermesState,
    ticker: str,
    mode: EditMode,
    phase_slug: str,
    prior_body: dict[str, Any] | None,
    errors: list[PhaseError],
    evidence_bundle: TickerEvidenceBundle | None = None,
) -> AnalystPayload:
    """Materialize or carry :class:`ForecastAssessment`; never invent terms.

    Full mode without ``ForecastTerms`` retains analyst prose (shadow rollout) and
    records ``forecast_unavailable`` rather than dropping the ticker.

    When materializing a **new** assessment, cite the H5 base bundle / evidence
    IDs on ``ForecastTerms.evidence_ids`` (WP11.2). Skip / identical-content
    carries preserve prior identity without re-citing.
    """
    terms = payload.forecast
    prior_assessment = _assessment_from_body(prior_body) if prior_body else None
    prior_terms = _terms_from_body(prior_body) if prior_body else None

    if terms is None:
        # Edit/skip without terms change: carry prior typed lineage when present.
        if prior_assessment is not None:
            return payload.model_copy(
                update={
                    "forecast": prior_terms,
                    "forecast_assessment": prior_assessment,
                }
            )
        if prior_terms is not None:
            terms = prior_terms
        else:
            if mode == "full":
                logger.warning(
                    "H5 full analysis for %s missing ForecastTerms; "
                    "forecast_unavailable (analyst payload retained)",
                    ticker,
                )
                errors.append(
                    PhaseError(
                        phase="phase_hermes",
                        node=phase_slug,
                        message="forecast_unavailable: full H5 missing ForecastTerms",
                    )
                )
            return payload

    assert terms is not None
    if (
        prior_assessment is not None
        and prior_assessment.content_hash == forecast_terms_content_hash(terms)
    ):
        return payload.model_copy(
            update={"forecast": terms, "forecast_assessment": prior_assessment}
        )

    if evidence_bundle is not None:
        terms = cite_evidence_bundle_on_forecast(terms, evidence_bundle)

    cutoff = _cutoff_or_run_date(state)
    prompt_version, artifact_version = _skill_versions(mode)
    assessment = materialize_forecast_assessment(
        ticker=ticker,
        terms=terms,
        source_run_id=str(state.run_id),
        provider_invocation_id=_provider_invocation_id(
            phase_slug=phase_slug, run_id=str(state.run_id), ticker=ticker
        ),
        prompt_version=prompt_version,
        artifact_version=artifact_version,
        price_anchor=_h5_price_anchor(state, ticker),
        effective_at=cutoff,
        known_at=cutoff,
    )
    return payload.model_copy(update={"forecast": terms, "forecast_assessment": assessment})


def _h5_attempt_id() -> str:
    raw = os.environ.get("OLYMPUS_ATTEMPT", "").strip()
    return raw or "1"


def _publish_base_bundle_before_provider(
    *,
    state: HermesState,
    ticker: str,
    phase_inputs: dict[str, Any],
    phase_slug: str,
    store: EvidenceBundleStore | None,
) -> TickerEvidenceBundle:
    """Canonicalize + optionally persist one base bundle before the LLM call."""
    cutoff = _cutoff_or_run_date(state)
    recorded_at = cutoff
    run_id = str(state.run_id)
    attempt_id = _h5_attempt_id()
    state_version_id = resolve_h5_state_version_id(
        state.research_state_pin if isinstance(state.research_state_pin, dict) else None,
        source_run_id=run_id,
    )
    facts, missing = facts_from_phase_inputs(
        ticker=ticker,
        phase_inputs=phase_inputs,
        knowledge_cutoff_at=cutoff,
    )
    provenance = TypedProvenance(
        source_run_id=run_id,
        attempt_id=attempt_id,
        artifact_id=f"artifact-h5-{ticker.strip().upper()}",
    )
    built = build_h5_evidence_bundle(
        ticker=ticker,
        source_run_id=run_id,
        attempt_id=attempt_id,
        state_version_id=state_version_id,
        facts=facts,
        recorded_at=recorded_at,
        provenance=provenance,
        missing_fields=missing,
    )
    bundle = publish_h5_evidence_bundle(built=built, store=store)
    logger.info(
        "H5 evidence bundle published for %s bundle_id=%s durable=%s phase=%s",
        ticker,
        bundle.bundle_id,
        store is not None,
        phase_slug,
    )
    return bundle


def _portfolio_grounding(state: HermesState, *, phase: RetrievalPhase, segment: str = ""):
    return build_grounding(
        use_data_tools=True,
        live_search=True,
        run_date=state.run_date,
        segment=segment or f"hermes/{phase}",
        data_tool_tables=MARKET_DATA_TABLES,
        use_research_tools=True,
        research_phase=phase,
        watchlist=tuple(state.config.watchlist),
    )


def run_asset_analyst_llm(
    *,
    state: HermesState,
    ticker: str,
    roster_entry: dict[str, Any],
    phase_slug: str,
    evidence_bundle_store: EvidenceBundleStore | None = None,
) -> tuple[
    AnalystPayload | None,
    dict[str, Any] | None,
    list[PhaseError],
    TickerEvidenceBundle | None,
]:
    errors: list[PhaseError] = []
    artifact_key = analyst_artifact_key(ticker)
    mode = resolve_analyst_edit_mode(state, ticker)
    enforce_path = research_attention_h5_enforce_path(state, ticker=ticker)
    if enforce_path == "full":
        mode = "full"
    elif enforce_path == "carry" and mode != "full":
        mode = "skip"
    prior_loader = _TickerPriorLoader(state, artifact_key)
    prior = prior_loader.load(artifact_key, state.run_date)
    prior_body = _body_from_prior_payload(prior.payload) if prior is not None else None
    evidence_bundle: TickerEvidenceBundle | None = None

    if (
        enforce_path == "metric_patch"
        and mode != "full"
        and prior is not None
        and prior_body
    ):
        patched = apply_analyst_metric_patch(
            state,
            ticker,
            prior,
            roster_entry=roster_entry,
        )
        skip_inputs: dict[str, Any] = {
            "ticker": ticker,
            "price_deltas": dict(state.price_deltas),
            "bias_row": state.phase6_bias_row or {},
            "metric_patch": True,
        }
        evidence_bundle = _publish_base_bundle_before_provider(
            state=state,
            ticker=ticker,
            phase_inputs=skip_inputs,
            phase_slug=phase_slug,
            store=evidence_bundle_store,
        )
        body_raw = patched.get("body", patched)
        if not isinstance(body_raw, dict):
            body_raw = prior_body or {}
        payload = AnalystPayload.model_validate({**body_raw, "ticker": ticker})
        enriched = _attach_forecast_lineage(
            payload=payload,
            state=state,
            ticker=ticker,
            mode="skip",
            phase_slug=phase_slug,
            prior_body=prior_body,
            errors=errors,
            evidence_bundle=evidence_bundle,
        )
        body = analyst_body_from_payload(enriched)
        document = build_analyst_document(
            ticker=ticker,
            run_date=state.run_date,
            body=body,
            linked_thesis_id=roster_entry.get("linked_market_thesis_id"),
        )
        return enriched, document, errors, evidence_bundle

    if mode == "skip" and prior is not None and prior_body:
        skip_inputs: dict[str, Any] = {
            "ticker": ticker,
            "price_deltas": dict(state.price_deltas),
            "bias_row": state.phase6_bias_row or {},
        }
        evidence_bundle = _publish_base_bundle_before_provider(
            state=state,
            ticker=ticker,
            phase_inputs=skip_inputs,
            phase_slug=phase_slug,
            store=evidence_bundle_store,
        )
        payload = AnalystPayload.model_validate({**prior_body, "ticker": ticker})
        enriched = _attach_forecast_lineage(
            payload=payload,
            state=state,
            ticker=ticker,
            mode=mode,
            phase_slug=phase_slug,
            prior_body=prior_body,
            errors=errors,
            evidence_bundle=evidence_bundle,
        )
        body = analyst_body_from_payload(enriched)
        carried = build_analyst_document(
            ticker=ticker,
            run_date=state.run_date,
            body=body,
            linked_thesis_id=roster_entry.get("linked_market_thesis_id"),
        )
        return enriched, carried, errors, evidence_bundle

    skill_text = (
        load_skill_edit("asset-analyst") if mode == "edit" else load_skill_full("asset-analyst")
    )
    tools, execute_tool, web_grounding = _portfolio_grounding(
        state, phase="h5_analyst", segment=phase_slug
    )
    _active = list(state.prior_context.active_theses)
    phase_inputs: dict[str, Any] = {
        "segment": phase_slug,
        "ticker": ticker,
        "roster_reason": roster_entry.get("roster_reason"),
        "rationale": roster_entry.get("rationale", ""),
        "linked_market_thesis_id": roster_entry.get("linked_market_thesis_id"),
        "linked_thesis": _resolve_linked_thesis(
            roster_entry.get("linked_market_thesis_id"), _active
        ),
        "bias_row": state.phase6_bias_row or {},
        "active_theses": _active,
        "price_deltas": dict(state.price_deltas),
        "held_in_prior_book": ticker
        in set(holdings_from_prior_book(state.prior_context.prior_book)),
    }
    phase_inputs = apply_web_grounding_to_inputs(
        phase_inputs,
        web_grounding=web_grounding,
        segment=phase_slug,
        live_search=True,
    )
    if prior is not None:
        phase_inputs["prior_analyst"] = dict(prior.payload)

    # WP11.2: one base bundle per H5-attempted ticker — before provider call.
    evidence_bundle = _publish_base_bundle_before_provider(
        state=state,
        ticker=ticker,
        phase_inputs=phase_inputs,
        phase_slug=phase_slug,
        store=evidence_bundle_store,
    )

    eff_model = get_model_for_phase(phase_slug) or get_model_for_mode()

    if mode == "edit" and prior is not None:
        phase_inputs.update(
            {
                "edit_mode": "edit",
                "prior_date": prior.date.isoformat(),
                "prior_document": prior.payload,
            }
        )
        try:
            result = run_research_agent(
                skill_text=skill_text,
                phase_inputs=phase_inputs,
                shared_context=_shared_context(
                    state, context_keys=("digest", "digest-delta"), data_layer_scope="ticker"
                ),
                output_model=DocumentPatch,
                phase_slug=phase_slug,
                tools=tools,
                execute_tool=execute_tool,
                model=eff_model,
            )
        except Exception as exc:
            logger.warning(
                "H5 analyst edit LLM failed for %s (%s: %s); bundle retained",
                ticker,
                type(exc).__name__,
                exc,
            )
            errors.append(
                PhaseError(
                    phase="phase_hermes",
                    node=phase_slug,
                    message=f"analyst LLM failed: {exc}"[:500],
                )
            )
            return None, None, errors, evidence_bundle
        patch = coerce_document_patch(result)
        try:
            reject_partial_forecast_edits(patch)
            merge_result = merge_document_patch(
                prior.payload,
                patch,
                schema_validator=lambda body: AnalystPayload.model_validate(
                    body.get("body", body) if isinstance(body, dict) else body
                ),
            )
        except (MergeError, ValidationError) as exc:
            logger.warning("H5 analyst edit merge failed for %s (%s)", ticker, exc)
            errors.append(PhaseError(phase="phase_hermes", node=phase_slug, message=str(exc)[:500]))
            body_raw = prior_body or {}
            payload = AnalystPayload.model_validate({**body_raw, "ticker": ticker})
            enriched = _attach_forecast_lineage(
                payload=payload,
                state=state,
                ticker=ticker,
                mode="skip",
                phase_slug=phase_slug,
                prior_body=body_raw,
                errors=errors,
                evidence_bundle=evidence_bundle,
            )
            return enriched, dict(prior.payload), errors, evidence_bundle
        materialized = dict(merge_result.materialized)
        body_raw = materialized.get("body", materialized)
        if not isinstance(body_raw, dict):
            body_raw = {}
        payload = AnalystPayload.model_validate({**body_raw, "ticker": ticker})
        enriched = _attach_forecast_lineage(
            payload=payload,
            state=state,
            ticker=ticker,
            mode=mode,
            phase_slug=phase_slug,
            prior_body=prior_body,
            errors=errors,
            evidence_bundle=evidence_bundle,
        )
        doc = build_analyst_document(
            ticker=ticker,
            run_date=state.run_date,
            body=analyst_body_from_payload(enriched),
            linked_thesis_id=roster_entry.get("linked_market_thesis_id"),
        )
        return enriched, doc, errors, evidence_bundle

    try:
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=_shared_context(
                state, context_keys=("digest", "digest-delta"), data_layer_scope="ticker"
            ),
            output_model=AnalystPayload,
            phase_slug=phase_slug,
            tools=tools,
            execute_tool=execute_tool,
            model=eff_model,
        )
    except Exception as exc:  # LLM-output failure degrades this ticker, never the chain (#1665)
        logger.warning(
            "H5 analyst LLM failed for %s (%s: %s); skipping ticker (bundle retained)",
            ticker,
            type(exc).__name__,
            exc,
        )
        errors.append(
            PhaseError(
                phase="phase_hermes", node=phase_slug, message=f"analyst LLM failed: {exc}"[:500]
            )
        )
        return None, None, errors, evidence_bundle
    payload = result.model_copy(
        update={"fingerprint_news_hash": news_hash_for_ticker(state, ticker)}
    )
    enriched = _attach_forecast_lineage(
        payload=payload,
        state=state,
        ticker=ticker,
        mode=mode,
        phase_slug=phase_slug,
        prior_body=prior_body,
        errors=errors,
        evidence_bundle=evidence_bundle,
    )
    body = analyst_body_from_payload(enriched)
    doc = build_analyst_document(
        ticker=ticker,
        run_date=state.run_date,
        body=body,
        linked_thesis_id=roster_entry.get("linked_market_thesis_id"),
    )
    return enriched, doc, errors, evidence_bundle
