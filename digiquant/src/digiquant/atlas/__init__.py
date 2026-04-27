"""digiquant.atlas — frontend-consumable shapes for the Atlas pipeline.

This sub-package holds shared *contract* models that crystallize the shape of
artifacts published by the Atlas pipeline (which lives in
``apps/digiquant-atlas/src/digiquant_atlas/``). It is intentionally a small,
import-light surface so the Atlas Next.js frontend, BFF helpers, and any
downstream consumers can validate the JSON they load from Supabase without
pulling LangGraph or the orchestration runtime.

See ``apps/digiquant-atlas/docs/agentic/ARCHITECTURE.md`` (section "Snapshot
read path") for the data flow and consumption pattern.
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
    "personalize_snapshot",
]
