"""DigiQuant Atlas — phase-structured research pipeline over DigiGraph.

Public surface (added across commits 2–9):

- :class:`digiquant_atlas.state.AtlasResearchState` — the sub-graph state model.
- :func:`digiquant_atlas.skills.load_skill` — SKILL.md loader.
- :func:`digiquant_atlas.schemas.load_schema` — JSON-Schema loader (authoritative shape source).
- :func:`digiquant_atlas.graph.build_atlas_graph` — compiled LangGraph entry point (commit 9).
- :class:`digiquant_atlas.graph.AtlasInput` — DigiClaw-facing invocation contract (commit 9).
"""

from __future__ import annotations

__all__ = [
    "__version__",
]

__version__ = "0.1.0"
