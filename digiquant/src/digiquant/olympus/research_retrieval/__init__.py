"""Olympus unified research + portfolio retrieval (spec §6.1).

Phase 3 WP12.1 frozen research-state contracts live in
:mod:`digiquant.olympus.research_retrieval.models` (prose remains a view).
WP12.2 append-only store: :mod:`digiquant.olympus.research_retrieval.store`.
"""

from __future__ import annotations

from digiquant.olympus.research_retrieval.blinding import (
    DIGEST_DOCUMENT_KEY,
    RetrievalPhase,
    portfolio_tool_allowed,
    research_document_allowed,
)
from digiquant.olympus.research_retrieval.cache import ResearchCache
from digiquant.olympus.research_retrieval.models import (
    BeliefStatus,
    BeliefVersion,
    EvidenceRecord,
    ExpectedEventStatus,
    ExpectedEventVersion,
    LegacyDocumentRef,
    PatchMode,
    PatchTargetKind,
    ResearchPatch,
    ResearchStateManifest,
    ResearchStatePin,
    ResearchStateVersion,
    TypedProvenance,
)
from digiquant.olympus.research_retrieval.queries import (
    extract_section,
    query_portfolio,
    query_research,
)
from digiquant.olympus.research_retrieval.retriever import ResearchRetriever
from digiquant.olympus.research_retrieval.store import (
    LoadedResearchState,
    ResearchStateConflict,
    ResearchStateError,
    ResearchStateMissingError,
    ResearchStateStore,
)
from digiquant.olympus.research_retrieval.tools import (
    RESEARCH_TOOLS,
    build_research_tool_dispatcher,
)

__all__ = [
    "BeliefStatus",
    "BeliefVersion",
    "DIGEST_DOCUMENT_KEY",
    "EvidenceRecord",
    "ExpectedEventStatus",
    "ExpectedEventVersion",
    "LegacyDocumentRef",
    "LoadedResearchState",
    "PatchMode",
    "PatchTargetKind",
    "RESEARCH_TOOLS",
    "ResearchCache",
    "ResearchPatch",
    "ResearchRetriever",
    "ResearchStateConflict",
    "ResearchStateError",
    "ResearchStateManifest",
    "ResearchStateMissingError",
    "ResearchStatePin",
    "ResearchStateStore",
    "ResearchStateVersion",
    "RetrievalPhase",
    "TypedProvenance",
    "build_research_tool_dispatcher",
    "extract_section",
    "portfolio_tool_allowed",
    "query_portfolio",
    "query_research",
    "research_document_allowed",
]
