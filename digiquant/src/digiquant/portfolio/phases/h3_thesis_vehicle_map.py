"""H3 — thesis vehicle map (market thesis → tickers)."""

from __future__ import annotations

import logging
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.research.supabase_io import SupabaseClient
from digiquant.portfolio.models.thesis import ThesisVehicleMapOutput
from digiquant.portfolio.phases.thesis_common import (
    build_thesis_document,
    run_thesis_phase_llm,
)
from digiquant.portfolio.state import PortfolioState
from digiquant.portfolio.writers.thesis_io import persist_thesis_vehicle_map
from digiquant.dashboard.overlay.persist import skip_overlay_shared_register

logger = logging.getLogger(__name__)

NODE_ID = "portfolio/thesis/vehicle-map"
PHASE_NAME = "portfolio_h3_vehicle_map"
ARTIFACT_KEY = ("thesis", "vehicle-map")
DOC_TYPE = "thesis_vehicle_map"


def _run_h3_llm(state: PortfolioState) -> ThesisVehicleMapOutput:
    vehicle_map, _doc, errors = run_thesis_phase_llm(
        state=state,
        skill_slug="thesis-vehicle-map",
        artifact_key=ARTIFACT_KEY,
        retrieval_phase="h2_thesis",
        phase_slug=NODE_ID,
        output_model=ThesisVehicleMapOutput,
        phase_inputs={
            "doc_type": DOC_TYPE,
            "segment": NODE_ID,
            "watchlist": list(state.config.watchlist),
            "thesis_review": state.phase_portfolio.thesis_review,
            "market_thesis_exploration": state.phase_portfolio.market_thesis_exploration,
            "meta": {"source_exploration_key": "market-thesis-exploration"},
        },
        # Baseline runs publish `digest`, delta runs publish `digest-delta`
        # (publish_phase.py) — both must be whitelisted or the prior digest
        # silently drops out of context on whichever cadence is missing (#1270).
        context_keys=("digest", "digest-delta"),
    )
    if vehicle_map is None:
        return ThesisVehicleMapOutput()
    if errors:
        logger.warning("H3 vehicle map completed with %d recoverable errors", len(errors))
    return vehicle_map


def _h3_node_factory(client: SupabaseClient | None):
    def _node(state: PortfolioState) -> dict[str, Any]:
        vehicle_map = _run_h3_llm(state)
        document = build_thesis_document(
            doc_type=DOC_TYPE,
            run_date=state.run_date,
            body=vehicle_map.model_dump(mode="json"),
            meta={"source_exploration_key": "market-thesis-exploration"},
        )
        if (
            client is not None
            and vehicle_map.mappings
            and not skip_overlay_shared_register(state.config.workspace_id)
        ):
            persist_thesis_vehicle_map(
                client,
                run_date=state.run_date,
                vehicle_map=vehicle_map,
                workspace_id=state.config.workspace_id,
            )
        return {
            "phase_portfolio": state.phase_portfolio.model_copy(update={"thesis_vehicle_map": document}),
        }

    return _node


def build_h3_thesis_vehicle_map(*, client: SupabaseClient | None = None) -> PipelinePhase:
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_h3_node_factory(client))],
    )
