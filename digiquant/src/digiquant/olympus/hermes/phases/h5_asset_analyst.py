"""H5 — unified asset analyst per focus-roster ticker (spec §9)."""

from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import PhaseHermesState
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.focus_roster import ticker_in_focus_roster
from digiquant.olympus.edit_mode import artifact_document_key
from digiquant.olympus.hermes.phases.portfolio_common import (
    analyst_artifact_key,
    run_asset_analyst_llm,
)
from digiquant.olympus.hermes.roster_cap import capped_tickers
from digiquant.olympus.hermes.state import HermesState
from digiquant.olympus.hermes.writers.analyst_io import upsert_analyst_coverage
from digiquant.olympus.hermes.writers.thesis_io import upsert_vehicle_thesis_from_analyst

logger = logging.getLogger(__name__)

NODE_ID = "hermes/portfolio/asset-analyst"
PHASE_NAME = "hermes_h5_asset_analyst"


def _roster_entry_map(state: HermesState) -> dict[str, dict[str, Any]]:
    return {
        entry.ticker.upper(): entry.model_dump(mode="json")
        for entry in state.phase_hermes.focus_roster
    }


def _h5_node_factory(ticker: str, client: SupabaseClient | None):
    def _node(state: HermesState) -> dict[str, Any]:
        if not ticker_in_focus_roster(state, ticker):
            return {}
        roster = _roster_entry_map(state)
        entry = roster.get(ticker.upper(), {"ticker": ticker, "roster_reason": "other"})
        payload, document, errors = run_asset_analyst_llm(
            state=state,
            ticker=ticker,
            roster_entry=entry,
            phase_slug=f"{NODE_ID}-{ticker}",
        )
        if payload is None:
            return {}
        if errors:
            logger.warning("H5 %s completed with %d recoverable errors", ticker, len(errors))
        doc_key = artifact_document_key(analyst_artifact_key(ticker))
        if client is not None:
            upsert_analyst_coverage(
                client,
                run_date=state.run_date,
                ticker=ticker,
                document_key=doc_key,
                thesis_ids=[entry["linked_market_thesis_id"]]
                if entry.get("linked_market_thesis_id")
                else None,
            )
            if entry.get("roster_reason") != "thesis_mapped":
                upsert_vehicle_thesis_from_analyst(
                    client,
                    run_date=state.run_date,
                    ticker=ticker,
                    analyst_payload=payload.model_dump(mode="json"),
                )
        analysts = {ticker: payload.model_dump(mode="json")}
        return {"phase_hermes": PhaseHermesState(asset_analysts=analysts)}

    return _node


def build_h5_asset_analyst(
    tickers: list[str],
    *,
    held: Collection[str] = (),
    client: SupabaseClient | None = None,
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
            NodeSpec(name=f"{NODE_ID}-{ticker}", run=_h5_node_factory(ticker, client))
            for ticker in capped
        ],
    )


def build_h5_from_state(client: SupabaseClient | None = None) -> PipelinePhase:
    """Runtime roster fan-out — compile a noop phase; nodes gate on focus roster."""

    def _noop(_state: HermesState) -> dict[str, Any]:
        return {}

    return PipelinePhase(name=PHASE_NAME, nodes=[NodeSpec(name=f"{NODE_ID}-noop", run=_noop)])


def build_h5_asset_analyst_phases(
    watchlist: list[str],
    *,
    held: Collection[str] = (),
    client: SupabaseClient | None = None,
) -> list[PipelinePhase]:
    """Return H5 phase(s) for thesis-first graph wiring."""
    return [build_h5_asset_analyst(watchlist, held=held, client=client)]
