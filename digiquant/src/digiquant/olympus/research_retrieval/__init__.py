"""Olympus unified research + portfolio retrieval (spec §6.1).

Phase 3 WP12.1 frozen research-state contracts live in
:mod:`digiquant.olympus.research_retrieval.models` (prose remains a view).
WP12.2 append-only store: :mod:`digiquant.olympus.research_retrieval.store`.
WP12.3 preflight pin: :mod:`digiquant.olympus.research_retrieval.pin`.
WP12.4 legacy inventory backfill:
:mod:`digiquant.olympus.research_retrieval.legacy_backfill`.
WP12.5 compiled prose views:
:mod:`digiquant.olympus.research_retrieval.views`.
"""

from __future__ import annotations

from digiquant.olympus.research_retrieval.blinding import (
    DIGEST_DOCUMENT_KEY,
    RetrievalPhase,
    portfolio_tool_allowed,
    research_document_allowed,
)
from digiquant.olympus.research_retrieval.cache import ResearchCache
from digiquant.olympus.research_retrieval.legacy_backfill import (
    BackfillCounts,
    LegacySourceDocument,
    backfill_legacy_manifests,
    build_legacy_document_ref,
)
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
from digiquant.olympus.research_retrieval.pin import (
    STATE_UNAVAILABLE,
    ResearchStatePinResult,
    ResearchStateUnavailableError,
    child_version_must_name_parent,
    pin_research_state_for_preflight,
    require_research_state_pin,
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
from digiquant.olympus.research_retrieval.views import (
    COMPILED_BRIEF_DOCUMENT_KEY,
    COMPILED_DIGEST_DOCUMENT_KEY,
    VIEW_SCHEMA_VERSION,
    CompiledResearchView,
    ResearchViewKind,
    ResearchViewPublishBlocked,
    compile_research_brief,
    compile_research_digest,
    compile_research_view,
    compile_views_from_store,
    document_key_for_view,
    publish_compiled_views,
    require_structured_write_ok,
)

__all__ = [
    "BackfillCounts",
    "BeliefStatus",
    "BeliefVersion",
    "COMPILED_BRIEF_DOCUMENT_KEY",
    "COMPILED_DIGEST_DOCUMENT_KEY",
    "CompiledResearchView",
    "DIGEST_DOCUMENT_KEY",
    "EvidenceRecord",
    "ExpectedEventStatus",
    "ExpectedEventVersion",
    "LegacyDocumentRef",
    "LegacySourceDocument",
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
    "ResearchStatePinResult",
    "ResearchStateStore",
    "ResearchStateUnavailableError",
    "ResearchStateVersion",
    "ResearchViewKind",
    "ResearchViewPublishBlocked",
    "RetrievalPhase",
    "STATE_UNAVAILABLE",
    "TypedProvenance",
    "VIEW_SCHEMA_VERSION",
    "backfill_legacy_manifests",
    "build_legacy_document_ref",
    "build_research_tool_dispatcher",
    "child_version_must_name_parent",
    "compile_research_brief",
    "compile_research_digest",
    "compile_research_view",
    "compile_views_from_store",
    "document_key_for_view",
    "extract_section",
    "pin_research_state_for_preflight",
    "portfolio_tool_allowed",
    "publish_compiled_views",
    "query_portfolio",
    "query_research",
    "require_research_state_pin",
    "require_structured_write_ok",
    "research_document_allowed",
]
