"""Olympus unified research + portfolio retrieval (spec §6.1).

Phase 3 WP12.1 frozen research-state contracts live in
:mod:`digiquant.olympus.research_retrieval.models` (prose remains a view).
WP12.2 append-only store: :mod:`digiquant.olympus.research_retrieval.store`.
WP12.3 preflight pin: :mod:`digiquant.olympus.research_retrieval.pin`.
WP12.4 legacy inventory backfill:
:mod:`digiquant.olympus.research_retrieval.legacy_backfill`.
WP12.5 compiled prose views:
:mod:`digiquant.olympus.research_retrieval.views`.
WP11.1 ticker evidence bundles + amendments:
:class:`~digiquant.olympus.research_retrieval.store.EvidenceBundleStore`
(models in the same ``models`` module; H6 selection cutover is WP11.3+;
WP13.1 research attention policy extends ``research_retrieval/planner.py``).
WP11.2 H5 publish:
:mod:`digiquant.olympus.research_retrieval.evidence_bundle`
(one base bundle per H5-attempted ticker before the provider call).
WP11.3 deterministic H6 selection:
:mod:`digiquant.olympus.research_retrieval.planner`
(``H6Selection`` reasons/features/budget; ``OLYMPUS_H6_SELECTION_MODE``).
WP11.4 bounded H6 missing-fact amendment:
:mod:`digiquant.olympus.research_retrieval.h6_amendment`
(one validated proposal → targeted retrieval → append-only amendment; no generic H6 search).
WP13.2 attention persistence:
:class:`~digiquant.olympus.research_retrieval.store.AttentionStore`
(plans/decisions/context manifests/policy evaluations; migration
``092_olympus_attention_context.sql``; storage only — WP13.3+ runtime wiring).
WP13.5 shadow evaluation:
:mod:`digiquant.olympus.research_retrieval.shadow_evaluation`
(reconcile plans to WP1 attempts + downstream artifacts; evidence-only).
"""

from __future__ import annotations

from digiquant.olympus.research_retrieval.blinding import (
    DIGEST_DOCUMENT_KEY,
    RetrievalPhase,
    portfolio_tool_allowed,
    research_document_allowed,
)
from digiquant.olympus.research_retrieval.cache import ResearchCache
from digiquant.olympus.research_retrieval.evidence_bundle import (
    OLYMPUS_EVIDENCE_BUNDLE_WRITER_ENV,
    EvidenceConflict,
    H5EvidenceBundleBuild,
    H5EvidenceFact,
    MissingEvidenceField,
    build_h5_evidence_bundle,
    cite_evidence_bundle_on_forecast,
    evidence_bundle_writer_enabled,
    facts_from_phase_inputs,
    publish_h5_evidence_bundle,
    resolve_h5_state_version_id,
)
from digiquant.olympus.research_retrieval.h6_amendment import (
    H6_AMENDMENT_POLICY_MAX_PER_BASE,
    H6AmendmentOutcome,
    H6AmendmentResult,
    attempt_h6_evidence_amendment,
    document_key_for_source_kind,
    retrieve_missing_fact_evidence,
    validate_missing_fact_proposal,
)
from digiquant.olympus.research_retrieval.legacy_backfill import (
    BackfillCounts,
    LegacySourceDocument,
    backfill_legacy_manifests,
    build_legacy_document_ref,
)
from digiquant.olympus.research_retrieval.models import (
    BeliefStatus,
    BeliefVersion,
    EvidenceBundleAmendment,
    EvidenceRecord,
    ExpectedEventStatus,
    ExpectedEventVersion,
    LegacyDocumentRef,
    MissingFactRequest,
    PatchMode,
    PatchTargetKind,
    ResearchPatch,
    ResearchStateManifest,
    ResearchStatePin,
    ResearchStateVersion,
    TickerEvidenceBundle,
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
from digiquant.olympus.research_retrieval.planner import (
    H6_SELECTION_PROMPT_FORBIDDEN_KEYS,
    OLYMPUS_H6_SELECTION_MODE_ENV,
    AttentionBudgetEstimate,
    AttentionContextManifest,
    AttentionDecision,
    AttentionDecisionReconciliation,
    AttentionFeatures,
    AttentionMode,
    AttentionPlan,
    AttentionPolicyEvaluation,
    AttentionReason,
    AttentionRolloutMode,
    AttentionTargetKind,
    H6Action,
    H6Budget,
    H6DecisionFeatures,
    H6Selection,
    H6SelectionMode,
    H6SelectionReason,
    PersistedAttentionDecision,
    PersistedAttentionPlan,
    assert_no_materiality_in_prompt,
    attention_decision_id,
    build_h6_decision_features,
    incumbent_fallback_selection,
    resolve_h6_selection_mode,
    select_h6,
)
from digiquant.olympus.research_retrieval.queries import (
    extract_section,
    query_portfolio,
    query_research,
)
from digiquant.olympus.research_retrieval.retriever import ResearchRetriever
from digiquant.olympus.research_retrieval.shadow_evaluation import (
    AttentionDownstreamOutcomes,
    ResearchPolicyShadowEvaluationReport,
    ShadowDecisionEvaluationRow,
    ShadowProviderAttemptDetail,
    evaluate_research_policy_shadow,
    write_shadow_evaluation_report,
)
from digiquant.olympus.research_retrieval.store import (
    ActualProviderAttemptUsage,
    AttentionStore,
    AttentionStoreConflict,
    AttentionStoreError,
    AttentionStoreMissingError,
    EvidenceBundleConflict,
    EvidenceBundleError,
    EvidenceBundleMissingError,
    EvidenceBundleStore,
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
    "ActualProviderAttemptUsage",
    "AttentionBudgetEstimate",
    "AttentionContextManifest",
    "AttentionDecision",
    "AttentionDecisionReconciliation",
    "AttentionDownstreamOutcomes",
    "AttentionFeatures",
    "AttentionMode",
    "AttentionPlan",
    "AttentionPolicyEvaluation",
    "AttentionReason",
    "AttentionRolloutMode",
    "AttentionStore",
    "AttentionStoreConflict",
    "AttentionStoreError",
    "AttentionStoreMissingError",
    "AttentionTargetKind",
    "BackfillCounts",
    "BeliefStatus",
    "BeliefVersion",
    "COMPILED_BRIEF_DOCUMENT_KEY",
    "COMPILED_DIGEST_DOCUMENT_KEY",
    "CompiledResearchView",
    "DIGEST_DOCUMENT_KEY",
    "EvidenceBundleAmendment",
    "EvidenceBundleConflict",
    "EvidenceBundleError",
    "EvidenceBundleMissingError",
    "EvidenceBundleStore",
    "EvidenceConflict",
    "EvidenceRecord",
    "ExpectedEventStatus",
    "ExpectedEventVersion",
    "H5EvidenceBundleBuild",
    "H5EvidenceFact",
    "H6Action",
    "H6Budget",
    "H6DecisionFeatures",
    "H6Selection",
    "H6SelectionMode",
    "H6SelectionReason",
    "H6_AMENDMENT_POLICY_MAX_PER_BASE",
    "H6AmendmentOutcome",
    "H6AmendmentResult",
    "H6_SELECTION_PROMPT_FORBIDDEN_KEYS",
    "LegacyDocumentRef",
    "LegacySourceDocument",
    "LoadedResearchState",
    "MissingEvidenceField",
    "MissingFactRequest",
    "OLYMPUS_EVIDENCE_BUNDLE_WRITER_ENV",
    "OLYMPUS_H6_SELECTION_MODE_ENV",
    "PatchMode",
    "PatchTargetKind",
    "PersistedAttentionDecision",
    "PersistedAttentionPlan",
    "RESEARCH_TOOLS",
    "ResearchCache",
    "ResearchPolicyShadowEvaluationReport",
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
    "ShadowDecisionEvaluationRow",
    "ShadowProviderAttemptDetail",
    "TickerEvidenceBundle",
    "TypedProvenance",
    "VIEW_SCHEMA_VERSION",
    "assert_no_materiality_in_prompt",
    "attempt_h6_evidence_amendment",
    "attention_decision_id",
    "backfill_legacy_manifests",
    "build_h5_evidence_bundle",
    "build_h6_decision_features",
    "build_legacy_document_ref",
    "build_research_tool_dispatcher",
    "child_version_must_name_parent",
    "cite_evidence_bundle_on_forecast",
    "compile_research_brief",
    "compile_research_digest",
    "compile_research_view",
    "compile_views_from_store",
    "document_key_for_source_kind",
    "document_key_for_view",
    "evaluate_research_policy_shadow",
    "evidence_bundle_writer_enabled",
    "extract_section",
    "facts_from_phase_inputs",
    "incumbent_fallback_selection",
    "pin_research_state_for_preflight",
    "portfolio_tool_allowed",
    "publish_compiled_views",
    "publish_h5_evidence_bundle",
    "query_portfolio",
    "query_research",
    "require_research_state_pin",
    "require_structured_write_ok",
    "research_document_allowed",
    "resolve_h5_state_version_id",
    "resolve_h6_selection_mode",
    "retrieve_missing_fact_evidence",
    "select_h6",
    "validate_missing_fact_proposal",
    "write_shadow_evaluation_report",
]
