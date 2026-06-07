"""digiquant.olympus.atlas — phase-structured research pipeline over DigiGraph.

Public surface:

Runtime entry points:
    - :class:`digiquant.olympus.atlas.state.AtlasResearchState` — sub-graph state model.
    - :func:`digiquant.olympus.atlas.graph.build_atlas_graph` — compiled LangGraph entry point.
    - :class:`digiquant.olympus.atlas.graph.AtlasInput` — DigiClaw-facing invocation contract.
    - :func:`digiquant.olympus.atlas.skills.load_skill` — SKILL.md loader.
    - :func:`digiquant.olympus.atlas.schemas.load_schema` — JSON-Schema loader.

Frontend-consumable contracts:
    - :class:`digiquant.olympus.atlas.snapshot.SnapshotEnvelope` — daily snapshot shape.
    - :class:`digiquant.olympus.atlas.personalization.PersonalizedSnapshot` — profile-overlaid view.
"""

from __future__ import annotations

from digiquant.olympus.atlas.personalization import (
    PersonalizedSnapshot,
    personalize_snapshot,
)
from digiquant.olympus.atlas.snapshot import (
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
