"""Shared helpers for thesis-track Hermes LLM nodes."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, TypeVar  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from pydantic import BaseModel, ValidationError

from digigraph.graph.research_agent import run_research_agent
from digigraph.model_config import get_model_for_mode, get_model_for_phase

from digiquant.olympus.atlas.phases._node_factory import (
    _shared_context,
    apply_web_grounding_to_inputs,
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
from digiquant.olympus.edit_mode.merge import MergeError, coerce_document_patch, section_index
from digiquant.olympus.hermes.skills import load_skill_edit, load_skill_full
from digiquant.olympus.hermes.state import HermesState
from digiquant.olympus.hermes.thesis_grounding import build_thesis_grounding
from digiquant.olympus.research_retrieval.blinding import RetrievalPhase

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class _StatePriorLoader:
    def __init__(self, state: HermesState) -> None:
        self._state = state

    def load(self, artifact_key: tuple[str, str], run_date: date) -> PriorPublished | None:
        doc_key = artifact_document_key(artifact_key)
        row = self._state.prior_context.latest_segments.get(doc_key)
        if not isinstance(row, dict):
            return None
        payload = row.get("payload")
        if not isinstance(payload, dict):
            return None
        raw_date = row.get("date")
        try:
            prior_date = date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            prior_date = run_date
        return PriorPublished(date=prior_date, document_key=doc_key, payload=payload)


def resolve_thesis_edit_mode(state: HermesState, artifact_key: tuple[str, str]) -> EditMode:
    return resolve_edit_mode(
        artifact_key=artifact_key,
        run_date=state.run_date,
        prior_loader=_StatePriorLoader(state),
        triage=None,
        force_full_rewrite=refresh_scope_forces_full(state.refresh_scope, artifact="segment")
        or state.refresh_scope == "hermes",
    )


def build_thesis_document(
    *,
    doc_type: str,
    run_date: date,
    body: dict[str, Any],
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "doc_type": doc_type,
        "date": run_date.isoformat(),
        "meta": meta or {},
        "body": body,
    }


def run_thesis_phase_llm(
    *,
    state: HermesState,
    skill_slug: str,
    artifact_key: tuple[str, str],
    retrieval_phase: RetrievalPhase,
    phase_slug: str,
    output_model: type[T],
    phase_inputs: dict[str, Any],
    context_keys: tuple[str, ...] = (),
) -> tuple[T | None, dict[str, Any] | None, list[PhaseError]]:
    """Run full or edit-mode LLM for one thesis artifact."""
    errors: list[PhaseError] = []
    mode = resolve_thesis_edit_mode(state, artifact_key)
    if mode == "skip":
        prior = _StatePriorLoader(state).load(artifact_key, state.run_date)
        if prior is None:
            return None, None, errors
        carried = build_thesis_document(
            doc_type=phase_inputs.get("doc_type", ""),
            run_date=state.run_date,
            body=dict(prior.payload.get("body", prior.payload)),
            meta=dict(prior.payload.get("meta", {})),
        )
        return None, carried, errors

    skill_text = load_skill_edit(skill_slug) if mode == "edit" else load_skill_full(skill_slug)
    tools, execute_tool, web_grounding = build_thesis_grounding(
        state, phase=retrieval_phase, use_data_tools=False
    )
    inputs = dict(phase_inputs)
    inputs = apply_web_grounding_to_inputs(
        inputs,
        web_grounding=web_grounding,
        segment=phase_slug,
        live_search=True,
    )

    eff_model = get_model_for_phase(phase_slug) or get_model_for_mode()
    prior = _StatePriorLoader(state).load(artifact_key, state.run_date)

    if mode == "edit" and prior is not None:
        inputs.update(
            {
                "edit_mode": "edit",
                "prior_date": prior.date.isoformat(),
                "prior_document": prior.payload,
                "section_index": section_index(
                    prior.payload.get("body", prior.payload)
                    if isinstance(prior.payload.get("body"), dict)
                    else prior.payload
                ),
            }
        )
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=inputs,
            shared_context=_shared_context(state, context_keys=context_keys),
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
                schema_validator=lambda body: output_model.model_validate(
                    body.get("body", body) if isinstance(body, dict) else body
                ),
            )
        except (MergeError, ValidationError) as exc:
            logger.warning("thesis edit merge failed for %s (%s)", phase_slug, exc)
            errors.append(PhaseError(phase="phase_hermes", node=phase_slug, message=str(exc)[:500]))
            return None, dict(prior.payload), errors
        materialized = dict(merge_result.materialized)
        body_raw = materialized.get("body", materialized)
        return output_model.model_validate(body_raw), materialized, errors

    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=inputs,
        shared_context=_shared_context(state, context_keys=context_keys),
        output_model=output_model,
        phase_slug=phase_slug,
        tools=tools,
        execute_tool=execute_tool,
        model=eff_model,
    )
    doc = build_thesis_document(
        doc_type=str(phase_inputs.get("doc_type") or ""),
        run_date=state.run_date,
        body=result.model_dump(mode="json"),
        meta=dict(phase_inputs.get("meta") or {}),
    )
    return result, doc, errors
