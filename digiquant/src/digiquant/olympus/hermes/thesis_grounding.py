"""Shared grounding helper for thesis-track Hermes nodes (H1–H4)."""

from __future__ import annotations

from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digiquant.olympus.atlas.phases._node_factory import build_grounding
from digiquant.olympus.hermes.state import HermesState
from digiquant.olympus.research_retrieval.blinding import RetrievalPhase


def build_thesis_grounding(
    state: HermesState,
    *,
    phase: RetrievalPhase,
    use_data_tools: bool = False,
) -> tuple[list[dict[str, Any]] | None, Any, dict | None]:
    """Grounding bundle for thesis nodes — always includes ``RESEARCH_TOOLS``."""
    return build_grounding(
        use_data_tools=use_data_tools,
        live_search=True,
        run_date=state.run_date,
        use_research_tools=True,
        research_phase=phase,
        watchlist=tuple(state.config.watchlist),
    )
