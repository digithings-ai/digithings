"""H2 — market thesis exploration (propose/revise market theses)."""

from __future__ import annotations

import logging
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.models.thesis import MarketThesisExplorationOutput
from digiquant.olympus.hermes.phases.thesis_common import (
    build_thesis_document,
    run_thesis_phase_llm,
)
from digiquant.olympus.hermes.state import HermesState
from digiquant.olympus.hermes.writers.thesis_io import persist_market_thesis_exploration

logger = logging.getLogger(__name__)

NODE_ID = "hermes/thesis/market-exploration"
PHASE_NAME = "hermes_h2_market_exploration"
ARTIFACT_KEY = ("thesis", "market-exploration")
DOC_TYPE = "market_thesis_exploration"


def _run_h2_llm(state: HermesState) -> MarketThesisExplorationOutput:
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
            "digest": state.phase7_digest or {},
            "active_theses": list(state.prior_context.active_theses),
            "thesis_review": state.phase_hermes.thesis_review,
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
    def _node(state: HermesState) -> dict[str, Any]:
        exploration = _run_h2_llm(state)
        document = build_thesis_document(
            doc_type=DOC_TYPE,
            run_date=state.run_date,
            body=exploration.model_dump(mode="json"),
            meta={"research_refs": []},
        )
        if client is not None and exploration.theses:
            persist_market_thesis_exploration(
                client,
                run_date=state.run_date,
                exploration=exploration,
            )
        return {
            "phase_hermes": state.phase_hermes.model_copy(
                update={"market_thesis_exploration": document}
            ),
        }

    return _node


def build_h2_market_thesis_exploration(*, client: SupabaseClient | None = None) -> PipelinePhase:
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_h2_node_factory(client))],
    )
