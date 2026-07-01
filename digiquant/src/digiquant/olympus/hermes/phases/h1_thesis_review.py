"""H1 — daily thesis review (confidence + criteria refresh)."""

from __future__ import annotations

import logging
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.models.thesis import ThesisReviewOutput
from digiquant.olympus.hermes.phases.thesis_common import (
    build_thesis_document,
    run_thesis_phase_llm,
)
from digiquant.olympus.hermes.state import HermesState
from digiquant.olympus.hermes.writers.thesis_io import (
    invalidation_hits_from_signals,
    merge_review_with_invalidation_hits,
    persist_thesis_review,
)

logger = logging.getLogger(__name__)

NODE_ID = "hermes/thesis/market-review"
PHASE_NAME = "hermes_h1_thesis_review"
ARTIFACT_KEY = ("thesis", "thesis-review")
DOC_TYPE = "Thesis Review"


def _invalidation_hits_for_state(state: HermesState) -> dict[str, list[str]]:
    """Map active theses → fired invalidation criteria (from bias row signals)."""
    signals: dict[str, list[str]] | None = None
    bias = state.phase6_bias_row
    if isinstance(bias, dict):
        raw = bias.get("invalidation_signals")
        if isinstance(raw, dict):
            signals = {
                str(key): [str(v) for v in val] for key, val in raw.items() if isinstance(val, list)
            }
    return invalidation_hits_from_signals(
        state.prior_context.active_theses,
        triggered_criteria=signals,
    )


def _run_h1_llm(state: HermesState) -> ThesisReviewOutput:
    review, _doc, errors = run_thesis_phase_llm(
        state=state,
        skill_slug="thesis",
        artifact_key=ARTIFACT_KEY,
        retrieval_phase="h1_thesis",
        phase_slug=NODE_ID,
        output_model=ThesisReviewOutput,
        phase_inputs={
            "doc_type": DOC_TYPE,
            "segment": NODE_ID,
            "active_theses": list(state.prior_context.active_theses),
            "digest": state.phase7_digest or {},
            "portfolio_performance": dict(state.prior_context.portfolio_performance),
        },
        context_keys=("digest", "digest-delta"),
    )
    if review is None:
        return ThesisReviewOutput()
    if errors:
        logger.warning("H1 thesis review completed with %d recoverable errors", len(errors))
    return review


def _h1_node_factory(client: SupabaseClient | None):
    def _node(state: HermesState) -> dict[str, Any]:
        review = _run_h1_llm(state)
        hits = _invalidation_hits_for_state(state)
        review = merge_review_with_invalidation_hits(
            review,
            state.prior_context.active_theses,
            hits,
        )
        document = build_thesis_document(
            doc_type=DOC_TYPE,
            run_date=state.run_date,
            body=review.model_dump(mode="json"),
        )
        if client is not None:
            persist_thesis_review(
                client,
                run_date=state.run_date,
                review=review,
                active_theses=state.prior_context.active_theses,
            )
        return {
            "phase_hermes": state.phase_hermes.model_copy(update={"thesis_review": document}),
        }

    return _node


def build_h1_thesis_review(*, client: SupabaseClient | None = None) -> PipelinePhase:
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_h1_node_factory(client))],
    )
