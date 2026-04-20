"""Pre-flight phase: load config + prior context + data-layer probe.

Maps to the ``Pre-Flight Protocol`` section of
``apps/digiquant-atlas/docs/agentic/ARCHITECTURE.md``. Runs once before
Phase 1; populates the frozen shared-context fields of
``AtlasResearchState`` so downstream phase nodes' LLM calls can cache them.

This module intentionally does not touch the LLM — pre-flight is pure data
loading. LLM costs start at Phase 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from digiquant_atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    DataLayerSnapshot,
)
from digiquant_atlas.supabase_io import (
    SupabaseClient,
    load_prior_context,
    query_macro_series_freshness,
    query_price_technicals_freshness,
)


@dataclass(frozen=True)
class PreflightDeps:
    """Wiring deps for the preflight node.

    Dependency-injected so the phase-4 integration test and the production
    graph builder both get the same entry point. ``config_loader`` is a
    caller-supplied closure that reads ``apps/digiquant-atlas/config/*``
    (or a test fixture) and returns an ``AtlasConfigBundle``.
    """

    client: SupabaseClient
    config_loader: Callable[[], AtlasConfigBundle]
    # Staleness threshold for price_technicals: if the latest date is older
    # than run_date - this many days, we flag a fallback in DataLayerSnapshot.
    price_staleness_days: int = 3


def _data_layer_snapshot(deps: PreflightDeps, run_date: date) -> DataLayerSnapshot:
    """Probe price_technicals + macro_series freshness. Never raises on
    empty tables — absence is a valid answer here, and the sub-graph
    compensates via fallback_used."""
    latest_tech, ticker_count = query_price_technicals_freshness(client=deps.client)
    macro_latest = query_macro_series_freshness(client=deps.client)

    fallback: str = "supabase"
    if latest_tech is None:
        fallback = "none"
    else:
        # Stale data → caller should prefer scripts/mcp fallback. This decision
        # lives with the phase-3 macro node today, but we surface it here so
        # triage (commit 8) can consider it.
        stale_cutoff = run_date - _days(deps.price_staleness_days)
        if latest_tech < stale_cutoff:
            fallback = "scripts"

    return DataLayerSnapshot(
        price_technicals_latest=latest_tech,
        price_technicals_ticker_count=ticker_count,
        macro_series_latest=macro_latest,
        fallback_used=fallback,  # type: ignore[arg-type]
    )


def _days(n: int):
    """Return a timedelta(days=n). Import deferred to keep module-top small."""
    from datetime import timedelta

    return timedelta(days=n)


def build_preflight_node(deps: PreflightDeps) -> Callable[[AtlasResearchState], dict]:
    """Return the preflight node function bound to ``deps``.

    The returned callable matches LangGraph's node signature
    (``(state) -> dict of field updates``) and is registered via
    pipeline_builder's ``NodeSpec``.
    """

    def preflight(state: AtlasResearchState) -> dict:
        # Delta runs MUST supply a baseline_date. We enforce it here (not at
        # state construction) so the caller sees a clear error instead of a
        # silent ignored field. See docs/plans/atlas-digigraph-migration.md §3.
        if state.run_type == "delta" and state.baseline_date is None:
            raise ValueError("delta run requires baseline_date to be set on AtlasResearchState")

        config = deps.config_loader()
        prior_context = load_prior_context(client=deps.client, run_date=state.run_date)
        data_layer = _data_layer_snapshot(deps, state.run_date)

        return {
            "config": config,
            "prior_context": prior_context,
            "data_layer": data_layer,
        }

    return preflight
