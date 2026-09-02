"""H1 — daily thesis review (confidence + criteria refresh)."""

from __future__ import annotations

import logging
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.research.segments import digest_briefing_for_portfolio
from digiquant.research.supabase_io import SupabaseClient, publish_document
from digiquant.dashboard.edit_mode.prior import artifact_document_key
from digiquant.portfolio.models.thesis import ThesisReviewOutput
from digiquant.portfolio.phases.thesis_common import (
    build_thesis_document,
    run_thesis_phase_llm,
)
from digiquant.portfolio.state import PortfolioState
from digiquant.portfolio.writers.thesis_io import (
    invalidation_hits_from_signals,
    merge_review_with_invalidation_hits,
    persist_thesis_review,
)
from digiquant.dashboard.overlay.persist import portfolio_document_key, skip_overlay_shared_register

logger = logging.getLogger(__name__)

NODE_ID = "portfolio/thesis/market-review"
PHASE_NAME = "portfolio_h1_thesis_review"
ARTIFACT_KEY = ("thesis", "thesis-review")
DOCUMENT_KEY = artifact_document_key(ARTIFACT_KEY)
DOC_TYPE = "Thesis Review"


def _invalidation_hits_for_state(state: PortfolioState) -> dict[str, list[str]]:
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


def _thesis_review_markdown(document: dict[str, Any]) -> str:
    body = document.get("body") if isinstance(document.get("body"), dict) else document
    date_str = str(document.get("date") or "")
    notes = str((body or {}).get("notes") or "").strip()
    reviewed = (body or {}).get("reviewed_theses") or []
    lines = [f"# Thesis review {date_str}", ""]
    if notes:
        lines.extend([notes, ""])
    if isinstance(reviewed, list) and reviewed:
        lines.extend(["| Thesis | Prior | New | Evidence |", "| --- | --- | --- | --- |"])
        for item in reviewed:
            if not isinstance(item, dict):
                continue
            evidence = item.get("evidence") or []
            if isinstance(evidence, list):
                evidence_text = "; ".join(str(x) for x in evidence if str(x).strip())
            else:
                evidence_text = str(evidence)
            lines.append(
                f"| {item.get('thesis_id') or '—'} | {item.get('prior_status') or '—'} | "
                f"{item.get('new_status') or '—'} | {evidence_text or '—'} |"
            )
        lines.append("")
    return "\n".join(lines)


def _publish_thesis_review_document(
    client: SupabaseClient, state: PortfolioState, document: dict[str, Any]
) -> None:
    date_str = state.run_date.isoformat()
    workspace_id = state.config.workspace_id
    publish_document(
        client=client,
        document_key=portfolio_document_key(DOCUMENT_KEY, workspace_id),
        payload=dict(document),
        doc_type=None,
        run_type=state.run_type,
        title=f"Thesis review {date_str}",
        date_str=date_str,
        category="portfolio",
        segment="thesis-review",
        content_markdown=_thesis_review_markdown(document),
        workspace_id=workspace_id,
    )


def _run_h1_llm(state: PortfolioState) -> ThesisReviewOutput:
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
            "digest": digest_briefing_for_portfolio(state.phase7_digest),
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
    def _node(state: PortfolioState) -> dict[str, Any]:
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
        if client is not None and not skip_overlay_shared_register(state.config.workspace_id):
            persist_thesis_review(
                client,
                run_date=state.run_date,
                review=review,
                active_theses=state.prior_context.active_theses,
                workspace_id=state.config.workspace_id,
            )
        if client is not None:
            try:
                _publish_thesis_review_document(client, state, document)
            except Exception:
                logger.exception(
                    "H1: thesis-review document publish failed for %s; continuing",
                    state.run_date,
                )
        return {
            "phase_portfolio": state.phase_portfolio.model_copy(update={"thesis_review": document}),
        }

    return _node


def build_h1_thesis_review(*, client: SupabaseClient | None = None) -> PipelinePhase:
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_h1_node_factory(client))],
    )
