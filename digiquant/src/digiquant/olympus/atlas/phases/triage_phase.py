"""Triage phase — ``state.triage`` + ``price_deltas`` on every daily run.

``deps=None`` skips price lookup (conservative regenerate). See ``graph.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any  # noqa: F401 -- used for LangGraph update dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.atlas.supabase_io import SupabaseClient, query_price_deltas
from digiquant.olympus.atlas.triage import evaluate
from digiquant.olympus.atlas.triage_signals import all_tracked_tickers


@dataclass(frozen=True)
class TriageDeps:
    """Wiring deps for the triage node (Supabase client + price lookback window)."""

    client: SupabaseClient
    # Trading-day window for the price-history lookup. 14 calendar days is
    # enough headroom to cross any long-weekend / holiday gap; bumped via
    # this dep so tests (or future stale-data hardening) can pin a different
    # value.
    price_lookback_days: int = 14


def build_triage_node(deps: TriageDeps | None):
    """Return the triage node bound to ``deps``.

    Returned callable matches LangGraph's node signature
    (``(state) -> dict of field updates``).
    """

    def _triage(state: AtlasResearchState) -> dict[str, Any]:
        price_deltas: dict[str, float] = {}
        if deps is not None:
            tickers = all_tracked_tickers()
            if tickers:
                price_deltas = query_price_deltas(
                    client=deps.client,
                    tickers=tickers,
                    run_date=state.run_date,
                    lookback_days=deps.price_lookback_days,
                )

        # Mutate-via-update so the rule engine sees the deltas without us
        # passing them through every evaluator signature. The state copy is
        # cheap (dict[str, float] of ~50 entries).
        state_with_prices = state.model_copy(update={"price_deltas": price_deltas})
        result = evaluate(state_with_prices)
        return {"triage": result, "price_deltas": price_deltas}

    return _triage


def build_triage_phase(deps: TriageDeps | None = None) -> PipelinePhase:
    """Build the single-node triage phase.

    ``deps=None`` preserves the legacy test path (no Supabase client), at
    the cost of dropping the price-delta signal. Production callers pass
    real deps from ``graph.py``.
    """
    return PipelinePhase(
        name="triage",
        nodes=[NodeSpec(name="triage", run=build_triage_node(deps))],
    )


__all__ = ["TriageDeps", "build_triage_node", "build_triage_phase"]
