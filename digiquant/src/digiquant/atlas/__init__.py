"""digiquant.atlas — phase-structured research pipeline over DigiGraph.

Public surface:

Runtime entry points:
    - :class:`digiquant.atlas.state.AtlasResearchState` — sub-graph state model.
    - :func:`digiquant.atlas.graph.build_atlas_graph` — compiled LangGraph entry point.
    - :class:`digiquant.atlas.graph.AtlasInput` — DigiClaw-facing invocation contract.
    - :func:`digiquant.atlas.skills.load_skill` — SKILL.md loader.
    - :func:`digiquant.atlas.schemas.load_schema` — JSON-Schema loader.

Frontend-consumable contracts:
    - :class:`digiquant.atlas.snapshot.SnapshotEnvelope` — daily snapshot shape.
    - :class:`digiquant.atlas.personalization.PersonalizedSnapshot` — profile-overlaid view.
"""

from __future__ import annotations

from digiquant.atlas.personalization import (
    PersonalizedSnapshot,
    personalize_snapshot,
)
from digiquant.atlas.snapshot import (
    SCHEMA_VERSION,
    DigestPayload,
    SnapshotEnvelope,
)

__all__ = [
    "SCHEMA_VERSION",
    "DigestPayload",
    "PersonalizedSnapshot",
    "SnapshotEnvelope",
    "__version__",
    "personalize_snapshot",
]

__version__ = "0.2.0"
