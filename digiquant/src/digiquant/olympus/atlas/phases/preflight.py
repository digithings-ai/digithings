"""Pre-flight: config load, prior context, data-layer probe (no LLM).

See ``atlas/docs/agentic/ARCHITECTURE.md`` Pre-Flight Protocol.
``preflight_reflect`` resolves due ``decision_log`` rows (Phase B #432).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable  # noqa: F401 — used for heterogeneous node-update dict shape

from digiquant.olympus.atlas.decision_log import (
    ReflectorOutput,
    fetch_recent_lessons,
    resolve_pending,
)
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    DataLayerSnapshot,
    PriorContext,
)
from digiquant.olympus.atlas.supabase_io import (
    SupabaseClient,
    load_prior_context,
    query_macro_series_freshness,
    query_price_technicals_freshness,
)

# decision_log may be empty or not yet migrated — do not fail the rest of preflight.
_SUPABASE_READ_ERRORS = (OSError, RuntimeError, ValueError, TypeError, KeyError)


@dataclass(frozen=True)
class PreflightDeps:
    """Wiring deps for the preflight node (injected client + config_loader)."""

    client: SupabaseClient
    config_loader: Callable[[], AtlasConfigBundle]
    # Staleness threshold for price_technicals: if the latest date is older
    # than run_date - this many days, we flag a fallback in DataLayerSnapshot.
    price_staleness_days: int = 3


def _data_layer_snapshot(deps: PreflightDeps, run_date: date) -> DataLayerSnapshot:
    """Probe price_technicals + macro_series freshness; empty tables are valid."""
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
    """Return the LangGraph preflight node bound to ``deps``."""

    def preflight(state: AtlasResearchState) -> dict:
        # Delta runs MUST supply a baseline_date. We enforce it here (not at
        # state construction) so the caller sees a clear error instead of a
        # silent ignored field. See docs/plans/atlas-digigraph-migration.md §3.
        if state.run_type == "delta" and state.baseline_date is None:
            raise ValueError("delta run requires baseline_date to be set on AtlasResearchState")

        config = deps.config_loader()
        prior_context = load_prior_context(client=deps.client, run_date=state.run_date)
        data_layer = _data_layer_snapshot(deps, state.run_date)

        # Hydrate ``decision_lessons`` from ``decision_log`` so the PM (Phase 7D)
        # sees prior reflections this run. The fetch is bounded:
        # - up to 5 same-ticker rows per watchlist member,
        # - up to 3 cross-ticker rows.
        # An empty list on first run is fine — the PM skill ignores it.
        watchlist = tuple(config.watchlist) if config.watchlist else ()
        try:
            lessons = fetch_recent_lessons(
                client=deps.client,
                run_date=state.run_date,
                watchlist=watchlist,
            )
        except _SUPABASE_READ_ERRORS:
            lessons = []

        prior_context = PriorContext(
            last_snapshots=prior_context.last_snapshots,
            latest_segments=prior_context.latest_segments,
            active_theses=prior_context.active_theses,
            decision_lessons=lessons,
        )

        return {
            "config": config,
            "prior_context": prior_context,
            "data_layer": data_layer,
        }

    return preflight


@dataclass(frozen=True)
class PreflightReflectDeps:
    """Wiring deps for ``preflight_reflect`` (optional stub ``reflector``)."""

    client: SupabaseClient
    reflector: Callable[[dict[str, Any]], ReflectorOutput] | None = None


def build_preflight_reflect_node(
    deps: PreflightReflectDeps,
) -> Callable[[AtlasResearchState], dict[str, Any]]:
    """Return the Phase B reflect node bound to ``deps``."""

    def reflect(state: AtlasResearchState) -> dict[str, Any]:
        resolve_pending(
            client=deps.client,
            run_date=state.run_date,
            reflector=deps.reflector,
        )
        return {}

    return reflect
