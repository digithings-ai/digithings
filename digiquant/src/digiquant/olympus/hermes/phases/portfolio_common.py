"""Shared helpers for H5/H6 portfolio-track Hermes nodes."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, TypeVar  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from pydantic import BaseModel, ValidationError

from digigraph.graph.research_agent import run_research_agent
from digigraph.model_config import get_model_for_mode, get_model_for_phase

from digiquant.olympus.atlas.data.queries import MARKET_DATA_TABLES
from digiquant.olympus.atlas.phases._node_factory import _shared_context, build_grounding
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
from digiquant.olympus.hermes.skills import load_skill_edit, load_skill_full
from digiquant.olympus.hermes.state import HermesState
from digiquant.olympus.hermes.ticker_fingerprint import news_hash_for_ticker, ticker_triage_signal
from digiquant.olympus.research_retrieval.blinding import RetrievalPhase

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


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
    return resolve_edit_mode(
        artifact_key=artifact_key,
        run_date=state.run_date,
        prior_loader=_TickerPriorLoader(state, artifact_key),
        triage=triage,
        force_full_rewrite=refresh_scope_forces_full(state.refresh_scope, artifact="segment")
        or state.refresh_scope == "hermes",
    )


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
    return {
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


def _stance_to_bias(stance: str) -> str:
    return {
        "buy": "overweight",
        "sell": "underweight",
        "watch": "neutral",
        "hold": "neutral",
    }.get(stance, "neutral")


def _portfolio_grounding(state: HermesState, *, phase: RetrievalPhase):
    return build_grounding(
        use_data_tools=True,
        live_search=False,
        run_date=state.run_date,
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
) -> tuple[AnalystPayload | None, dict[str, Any] | None, list[PhaseError]]:
    errors: list[PhaseError] = []
    artifact_key = analyst_artifact_key(ticker)
    mode = resolve_analyst_edit_mode(state, ticker)
    prior_loader = _TickerPriorLoader(state, artifact_key)
    prior = prior_loader.load(artifact_key, state.run_date)

    if mode == "skip" and prior is not None:
        body = prior.payload.get("body", prior.payload)
        if isinstance(body, dict):
            carried = build_analyst_document(
                ticker=ticker,
                run_date=state.run_date,
                body=body,
                linked_thesis_id=roster_entry.get("linked_market_thesis_id"),
            )
            payload = AnalystPayload.model_validate({**body, "ticker": ticker})
            return payload, carried, errors
        return None, None, errors

    skill_text = (
        load_skill_edit("asset-analyst") if mode == "edit" else load_skill_full("asset-analyst")
    )
    tools, execute_tool, _ = _portfolio_grounding(state, phase="h5_analyst")
    phase_inputs: dict[str, Any] = {
        "segment": phase_slug,
        "ticker": ticker,
        "roster_reason": roster_entry.get("roster_reason"),
        "linked_market_thesis_id": roster_entry.get("linked_market_thesis_id"),
        "bias_row": state.phase6_bias_row or {},
        "active_theses": list(state.prior_context.active_theses),
        "price_deltas": dict(state.price_deltas),
        "held_in_prior_book": ticker
        in set(holdings_from_prior_book(state.prior_context.prior_book)),
    }
    if prior is not None:
        phase_inputs["prior_analyst"] = dict(prior.payload)

    eff_model = get_model_for_phase(phase_slug) or get_model_for_mode()

    if mode == "edit" and prior is not None:
        phase_inputs.update(
            {
                "edit_mode": "edit",
                "prior_date": prior.date.isoformat(),
                "prior_document": prior.payload,
            }
        )
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=_shared_context(state, context_keys=(), data_layer_scope="ticker"),
            output_model=DocumentPatch,
            phase_slug=phase_slug,
            tools=tools,
            execute_tool=execute_tool,
            model=eff_model,
        )
        patch = coerce_document_patch(result)
        try:
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
            body = prior.payload.get("body", prior.payload)
            payload = AnalystPayload.model_validate(
                {**(body if isinstance(body, dict) else {}), "ticker": ticker}
            )
            return payload, dict(prior.payload), errors
        materialized = dict(merge_result.materialized)
        body_raw = materialized.get("body", materialized)
        payload = AnalystPayload.model_validate({**body_raw, "ticker": ticker})
        doc = build_analyst_document(
            ticker=ticker,
            run_date=state.run_date,
            body=body_raw if isinstance(body_raw, dict) else payload.model_dump(mode="json"),
            linked_thesis_id=roster_entry.get("linked_market_thesis_id"),
        )
        return payload, doc, errors

    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=_shared_context(state, context_keys=(), data_layer_scope="ticker"),
        output_model=AnalystPayload,
        phase_slug=phase_slug,
        tools=tools,
        execute_tool=execute_tool,
        model=eff_model,
    )
    payload = result.model_copy(
        update={"fingerprint_news_hash": news_hash_for_ticker(state, ticker)}
    )
    body = analyst_body_from_payload(payload)
    doc = build_analyst_document(
        ticker=ticker,
        run_date=state.run_date,
        body=body,
        linked_thesis_id=roster_entry.get("linked_market_thesis_id"),
    )
    return payload, doc, errors
