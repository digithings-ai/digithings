"""digiquant.research — phase-structured research pipeline over digigraph.

Public surface:

Runtime entry points:
    - :class:`digiquant.research.state.AtlasResearchState` — sub-graph state model.
    - :func:`digiquant.research.graph.build_atlas_graph` — compiled LangGraph entry point.
    - :class:`digiquant.research.graph.AtlasInput` — digiclaw-facing invocation contract.
    - :func:`digiquant.research.skills.load_skill` — SKILL.md loader.
    - :func:`digiquant.research.schemas.load_schema` — JSON-Schema loader.

Frontend-consumable contracts:
    - :class:`digiquant.research.snapshot.SnapshotEnvelope` — daily snapshot shape.
    - :class:`digiquant.research.personalization.PersonalizedSnapshot` — profile-overlaid view.
"""

from __future__ import annotations

from digiquant.research.personalization import (
    PersonalizedSnapshot,
    personalize_snapshot,
)
from digiquant.research.snapshot import (
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
