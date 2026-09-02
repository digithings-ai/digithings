"""H5 — unified asset analyst per focus-roster ticker (spec §9)."""

from __future__ import annotations

import logging
from collections.abc import Collection
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)

from digigraph.graph.pipeline_builder import FanOutPhase, NodeSpec, PipelinePhase

from digiquant.dashboard.edit_mode import artifact_document_key
from digiquant.dashboard.overlay.persist import skip_overlay_shared_register
from digiquant.dashboard.research_retrieval.store import EvidenceBundleStore, ResearchStateStore
from digiquant.portfolio.focus_roster import (
    fanout_ticker,
    focus_roster_tickers,
    ticker_in_focus_roster,
    with_fanout_ticker,
)
from digiquant.portfolio.phases.portfolio_common import (
    analyst_artifact_key,
    run_asset_analyst_llm,
)
from digiquant.portfolio.roster_cap import capped_tickers
from digiquant.portfolio.state import PortfolioState
from digiquant.portfolio.writers.analyst_io import upsert_analyst_coverage
from digiquant.portfolio.writers.thesis_io import upsert_vehicle_thesis_from_analyst
from digiquant.research.state import PhasePortfolioState
from digiquant.research.supabase_io import SupabaseClient

logger = logging.getLogger(__name__)

NODE_ID = "portfolio/asset-analyst"

_EXPLORATORY_REASONS = frozenset({"technical", "momentum", "other"})


def _should_backfill_vehicle_thesis(entry: dict[str, Any]) -> bool:
    """Post-hoc vehicle thesis only for genuinely-unlinked exploratory picks —
    never for held or thesis-linked names (the reversed-arrow fix, #1017)."""
    if entry.get("linked_market_thesis_id"):
        return False
    return entry.get("roster_reason") in _EXPLORATORY_REASONS


PHASE_NAME = "portfolio_h5_asset_analyst"


def _roster_entry_map(state: PortfolioState) -> dict[str, dict[str, Any]]:
    return {
        entry.ticker.upper(): entry.model_dump(mode="json")
        for entry in state.phase_portfolio.focus_roster
    }


def _h5_node_factory(
    ticker: str,
    client: SupabaseClient | None,
    evidence_bundle_store: EvidenceBundleStore | None = None,
    research_state_store: ResearchStateStore | None = None,
):
    def _node(state: PortfolioState) -> dict[str, Any]:
        if not ticker_in_focus_roster(state, ticker):
            return {}
        roster = _roster_entry_map(state)
        entry = roster.get(ticker.upper(), {"ticker": ticker, "roster_reason": "other"})
        payload, _document, errors, evidence_bundle = run_asset_analyst_llm(
            state=state,
            ticker=ticker,
            roster_entry=entry,
            phase_slug=f"{NODE_ID}-{ticker}",
            evidence_bundle_store=evidence_bundle_store,
            research_state_store=research_state_store,
        )
        portfolio_update = PhasePortfolioState()
        if evidence_bundle is not None:
            portfolio_update = PhasePortfolioState(
                ticker_evidence_bundles={
                    ticker.upper(): evidence_bundle.model_dump(mode="json"),
                }
            )
        if payload is None:
            # Provider failure: still surface the pre-provider base bundle (WP11.2).
            if evidence_bundle is None:
                return {}
            if errors:
                logger.warning(
                    "H5 %s failed after evidence publish (%d errors); bundle retained",
                    ticker,
                    len(errors),
                )
            return {"phase_portfolio": portfolio_update}
        if errors:
            logger.warning("H5 %s completed with %d recoverable errors", ticker, len(errors))
        doc_key = artifact_document_key(analyst_artifact_key(ticker))
        if client is not None and not skip_overlay_shared_register(state.config.workspace_id):
            upsert_analyst_coverage(
                client,
                run_date=state.run_date,
                ticker=ticker,
                document_key=doc_key,
                thesis_ids=[entry["linked_market_thesis_id"]]
                if entry.get("linked_market_thesis_id")
                else None,
                workspace_id=state.config.workspace_id,
            )
            if _should_backfill_vehicle_thesis(entry):
                upsert_vehicle_thesis_from_analyst(
                    client,
                    run_date=state.run_date,
                    ticker=ticker,
                    analyst_payload=payload.model_dump(mode="json"),
                    workspace_id=state.config.workspace_id,
                )
        analysts = {ticker: payload.model_dump(mode="json")}
        return {
            "phase_portfolio": portfolio_update.model_copy(
                update={"asset_analysts": analysts},
            )
        }

    return _node


def build_h5_asset_analyst(
    tickers: list[str],
    *,
    held: Collection[str] = (),
    client: SupabaseClient | None = None,
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
                run=_h5_node_factory(ticker, client, evidence_bundle_store, research_state_store),
            )
            for ticker in capped
        ],
    )


def build_h5_from_state(
    client: SupabaseClient | None = None,
    *,
    evidence_bundle_store: EvidenceBundleStore | None = None,
    research_state_store: ResearchStateStore | None = None,
) -> FanOutPhase:
    """Runtime roster fan-out — one parallel ``Send`` worker per H4 ``focus_roster`` ticker.

    The roster is computed at run time by H4 (so it can't be a compile-time per-ticker phase);
    ``FanOutPhase`` maps each ticker to a concurrent worker invocation and the ``phase_portfolio``
    reducer merges their analyst payloads. This replaces the prior single node that looped the
    tickers serially — N analyst LLM calls now run in parallel instead of back-to-back.
    """

    def _worker(state: PortfolioState) -> dict[str, Any]:
        ticker = state.portfolio_fanout_ticker
        if not ticker:
            return {}
        return _h5_node_factory(ticker, client, evidence_bundle_store, research_state_store)(state)

    return FanOutPhase(
        name=PHASE_NAME,
        worker=NodeSpec(name=f"{NODE_ID}-worker", run=_worker),
        items=focus_roster_tickers,
        with_item=with_fanout_ticker,
        item_key=fanout_ticker,
    )
