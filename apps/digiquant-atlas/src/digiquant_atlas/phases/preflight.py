"""Pre-flight phase: load config + prior context + data-layer probe.

Maps to the ``Pre-Flight Protocol`` section of
``apps/digiquant-atlas/docs/agentic/ARCHITECTURE.md``. Runs once before
Phase 1; populates the frozen shared-context fields of
``AtlasResearchState`` so downstream phase nodes' LLM calls can cache them.

The preflight node itself is pure data loading — no LLM costs there. The
companion ``preflight_reflect`` node (Phase B of #432, sequenced
*immediately after* preflight in the pipeline) is the one place during the
pre-flight stage that calls an LLM: once per due ``decision_log`` row to
generate the post-mortem reflection. The split keeps the data-load
invariant intact while colocating the reflection logic where it belongs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable  # noqa: F401 — used for heterogeneous node-update dict shape

from digiquant_atlas.decision_log import (
    ReflectorOutput,
    fetch_recent_lessons,
    resolve_pending,
)
from digiquant_atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    DataLayerSnapshot,
    PriorContext,
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

    Loads ``decision_lessons`` into PriorContext when the Supabase client
    is available — those rows feed the Phase 7D PM context on this run. The
    resolution / reflection step (which generates new lessons) runs in the
    sibling ``preflight_reflect`` node; ordering is enforced by the graph
    compiler so reflect lands BEFORE any preflight that reads lessons,
    EXCEPT that preflight itself is the very first node — meaning the
    reflect node sequenced *after* preflight contributes lessons to the
    NEXT run, not this one. That's the intended closed-loop semantics:
    lessons resolved at start of run N are picked up by preflight on run N+1.
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
        except Exception:  # noqa: BLE001 — preflight must not block on a missing table
            # On a fresh tenant the ``decision_log`` table may exist but be
            # empty (fine — the queries return []), or migration 026 may not
            # yet be applied (raises a Supabase error). Either way the rest
            # of preflight should still complete; the PM just runs without
            # past-decision context.
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
    """Wiring deps for the ``preflight_reflect`` node (Phase B of #432).

    Splits the ``decision_log`` resolver concerns from the data-load
    preflight: this node CALLS the LLM (one shot per due decision), so
    isolating it lets unit tests for plain preflight stay LLM-free.

    ``reflector`` is dependency-injected so tests can substitute a stub
    callable. ``None`` means "use the default LiteLLM-backed reflector"
    — see :func:`digiquant_atlas.decision_log._default_reflector`.
    """

    client: SupabaseClient
    reflector: Callable[[dict[str, Any]], ReflectorOutput] | None = None


def build_preflight_reflect_node(
    deps: PreflightReflectDeps,
) -> Callable[[AtlasResearchState], dict[str, Any]]:
    """Return the Phase B reflect node bound to ``deps``.

    Runs after preflight; resolves any due ``decision_log`` rows and writes
    the reflection back. Returns an empty update dict — the side effect is
    the Supabase write. Errors bubble up so a misconfigured Supabase fails
    the run loud (preflight already validated the client when loading
    prior context).
    """

    def reflect(state: AtlasResearchState) -> dict[str, Any]:
        resolve_pending(
            client=deps.client,
            run_date=state.run_date,
            reflector=deps.reflector,
        )
        return {}

    return reflect
