"""dashboard edit-mode continuity — patch merge and mode resolution.

Public API for research/portfolio nodes (spec §4–§5). Wraps the proven
``apply_ops`` merge primitive from ``materialize_snapshot.py``.
"""

from __future__ import annotations

from digiquant.dashboard.edit_mode.config import OLYMPUS_STALE_FULL_DAYS_ENV, stale_full_days
from digiquant.dashboard.edit_mode.merge import MergeError, merge_document_patch
from digiquant.dashboard.edit_mode.models import (
    ArtifactEditOutput,
    ArtifactKey,
    DocumentPatch,
    EditMode,
    FullArtifactBody,
    MergeResult,
    MergeStats,
    PatchOp,
    PriorPublished,
    TriageSignal,
)
from digiquant.dashboard.edit_mode.ops import apply_ops
from digiquant.dashboard.edit_mode.prior import PriorLoader, artifact_document_key
from digiquant.dashboard.edit_mode.resolve import resolve_edit_mode
from digiquant.dashboard.edit_mode.tools import (
    PriorDocumentFetcher,
    QueryResearch,
    ResearchRetriever,
    StubPriorDocumentFetcher,
    StubQueryResearch,
)
from digiquant.dashboard.research_retrieval import (
    RESEARCH_TOOLS,
    ResearchCache,
    build_research_tool_dispatcher,
)

__all__ = [
    "OLYMPUS_STALE_FULL_DAYS_ENV",
    "ArtifactEditOutput",
    "ArtifactKey",
    "DocumentPatch",
    "EditMode",
    "FullArtifactBody",
    "MergeError",
    "MergeResult",
    "MergeStats",
    "PatchOp",
    "PriorDocumentFetcher",
    "PriorLoader",
    "PriorPublished",
    "QueryResearch",
    "RESEARCH_TOOLS",
    "ResearchCache",
    "ResearchRetriever",
    "StubPriorDocumentFetcher",
    "StubQueryResearch",
    "build_research_tool_dispatcher",
    "TriageSignal",
    "apply_ops",
    "artifact_document_key",
    "merge_document_patch",
    "resolve_edit_mode",
    "stale_full_days",
]
