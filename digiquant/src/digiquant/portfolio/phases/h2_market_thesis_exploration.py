"""H2 — market thesis exploration (propose/revise market theses)."""

from __future__ import annotations

import logging
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.research.segments import digest_briefing_for_portfolio
from digiquant.research.supabase_io import SupabaseClient
from digiquant.portfolio.models.thesis import MarketThesisExplorationOutput
from digiquant.portfolio.phases.thesis_common import (
    build_thesis_document,
    run_thesis_phase_llm,
)
from digiquant.portfolio.state import PortfolioState
from digiquant.portfolio.writers.thesis_io import (
    persist_market_thesis_exploration,
    validate_market_thesis_proposals,
)
from digiquant.dashboard.overlay.persist import skip_overlay_shared_register

logger = logging.getLogger(__name__)

NODE_ID = "portfolio/thesis/market-exploration"
PHASE_NAME = "portfolio_h2_market_exploration"
ARTIFACT_KEY = ("thesis", "market-exploration")
DOC_TYPE = "market_thesis_exploration"


def _reviewed_status_by_id(state: PortfolioState) -> dict[str, str]:
    """H1's same-run status wins when H2 refreshes an existing thesis body."""
    statuses = {
        str(row.get("thesis_id")): str(row.get("status") or "ACTIVE")
        for row in state.prior_context.active_theses
        if row.get("thesis_id")
    }
    review_document = state.phase_portfolio.thesis_review or {}
    body = review_document.get("body") if isinstance(review_document, dict) else None
    reviewed = body.get("reviewed_theses") if isinstance(body, dict) else None
    if not isinstance(reviewed, list):
        return statuses
    for update in reviewed:
        if not isinstance(update, dict):
            continue
        thesis_id = str(update.get("thesis_id") or "").strip()
        new_status = str(update.get("new_status") or "").strip()
        if thesis_id and new_status:
            statuses[thesis_id] = new_status
    return statuses


def _run_h2_llm(state: PortfolioState) -> MarketThesisExplorationOutput:
    exploration, _doc, errors = run_thesis_phase_llm(
        state=state,
        skill_slug="market-thesis-exploration",
        artifact_key=ARTIFACT_KEY,
        retrieval_phase="h2_thesis",
        phase_slug=NODE_ID,
        output_model=MarketThesisExplorationOutput,
        phase_inputs={
            "doc_type": DOC_TYPE,
            "segment": NODE_ID,
            "digest": digest_briefing_for_portfolio(state.phase7_digest),
            "active_theses": list(state.prior_context.active_theses),
            "thesis_review": state.phase_portfolio.thesis_review,
            "meta": {"research_refs": []},
        },
        # Baseline runs publish `digest`, delta runs publish `digest-delta`
        # (publish_phase.py) — both must be whitelisted or the prior digest
        # silently drops out of context on whichever cadence is missing (#1270).
        context_keys=("digest", "digest-delta"),
    )
    if exploration is None:
        return MarketThesisExplorationOutput()
    if errors:
        logger.warning("H2 market exploration completed with %d recoverable errors", len(errors))
    return exploration


def _h2_node_factory(client: SupabaseClient | None):
    def _node(state: PortfolioState) -> dict[str, Any]:
        exploration = _run_h2_llm(state)
        proposals, validation_errors = validate_market_thesis_proposals(
            list(exploration.theses),
            list(state.prior_context.active_theses),
        )
        if validation_errors:
            logger.warning(
                "H2 rejected %d market-thesis proposal(s): %s",
                len(validation_errors),
                "; ".join(validation_errors),
            )
            exploration = exploration.model_copy(update={"theses": proposals})
        document = build_thesis_document(
            doc_type=DOC_TYPE,
            run_date=state.run_date,
            body=exploration.model_dump(mode="json"),
            meta={"research_refs": [], "validation_errors": validation_errors},
        )
        if (
            client is not None
            and exploration.theses
            and not skip_overlay_shared_register(state.config.workspace_id)
        ):
            persist_market_thesis_exploration(
                client,
                run_date=state.run_date,
                exploration=exploration,
                status_by_id=_reviewed_status_by_id(state),
                workspace_id=state.config.workspace_id,
            )
        return {
            "phase_portfolio": state.phase_portfolio.model_copy(
                update={"market_thesis_exploration": document}
            ),
        }

    return _node


def build_h2_market_thesis_exploration(*, client: SupabaseClient | None = None) -> PipelinePhase:
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_h2_node_factory(client))],
    )
