"""LLM tool definitions for Olympus retrieval (spec §6.1).

WP14.4 binds drill-down dispatchers to compiled context manifests and persists
pre-call manifest rows plus WP1 token linkage telemetry.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, date, datetime
from typing import (  # scored-lint suppression: heterogeneous graph / dict shapes
    Any,
    Callable,
)

from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.research_retrieval.blinding import RetrievalPhase
from digiquant.olympus.research_retrieval.cache import ResearchCache
from digiquant.olympus.research_retrieval.context import ContextCapsule, ContextManifest
from digiquant.olympus.research_retrieval.context_wiring import RoleContextWireResult
from digiquant.olympus.research_retrieval.queries import (
    RetrievalManifestMode,
    RetrievalQueryPin,
    build_retrieval_query_pin,
    extract_section,
    query_portfolio,
    query_research,
)
from digiquant.olympus.research_retrieval.store import (
    ActualProviderAttemptUsage,
    LoadedResearchState,
    PersistedRoleContextManifest,
    ProviderAttemptTokenLink,
    RoleRetrievalManifestStore,
    provider_attempt_token_link_id,
    role_context_manifest_record_id,
)
from digiquant.olympus.temporal import require_utc_datetime

logger = logging.getLogger(__name__)

OLYMPUS_RETRIEVAL_MANIFEST_MODE_ENV = "OLYMPUS_RETRIEVAL_MANIFEST_MODE"

RESEARCH_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_research",
            "description": (
                "Fetch a research vertical document or daily digest snapshot from Supabase. "
                "Use document_key (e.g. macro, equity, digest) or segment slug. "
                "When a context manifest pin is active, as_of_date must match an allowed ref."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_key": {"type": "string"},
                    "segment": {"type": "string"},
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_prior_document",
            "description": (
                "Fetch prior materialized document body (or one section) for edit-mode patching."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_key": {"type": "string"},
                    "section_path": {
                        "type": "string",
                        "description": "JSON Pointer path; omit for full body",
                    },
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["document_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_portfolio",
            "description": (
                "Fetch positions, NAV, active theses, and recent decision_log lessons. "
                "Not available on blinded analyst phases."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "ticker": {"type": "string"},
                },
            },
        },
    },
]


def resolve_retrieval_manifest_mode() -> RetrievalManifestMode:
    """Read ``OLYMPUS_RETRIEVAL_MANIFEST_MODE``; unknown values → shadow."""
    raw = os.environ.get(OLYMPUS_RETRIEVAL_MANIFEST_MODE_ENV, "shadow").strip().lower()
    try:
        return RetrievalManifestMode(raw)
    except ValueError:
        logger.warning(
            "invalid %s=%r; using shadow (allowed: off|shadow|enforce)",
            OLYMPUS_RETRIEVAL_MANIFEST_MODE_ENV,
            raw,
        )
        return RetrievalManifestMode.SHADOW


def retrieval_pin_from_wire_result(
    wire: RoleContextWireResult,
    *,
    state: LoadedResearchState,
    mode: RetrievalManifestMode | None = None,
) -> RetrievalQueryPin | None:
    """Build a drill-down pin from WP14.2/14.3 manifest linkage on a wire result."""
    if wire.manifest is None:
        return None
    effective_mode = mode or resolve_retrieval_manifest_mode()
    if effective_mode is RetrievalManifestMode.OFF:
        return None
    return build_retrieval_query_pin(
        manifest=wire.manifest,
        state=state,
        mode=effective_mode,
    )


def persist_pre_call_role_manifest(
    store: RoleRetrievalManifestStore,
    *,
    run_id: str,
    attempt_id: str,
    manifest: ContextManifest,
    capsule: ContextCapsule | None = None,
    recorded_at: datetime | None = None,
) -> PersistedRoleContextManifest:
    """Persist one immutable pre-call context manifest row."""
    stamp = require_utc_datetime(
        recorded_at or datetime.now(tz=UTC),
        field_name="recorded_at",
    )
    record = PersistedRoleContextManifest(
        record_id=role_context_manifest_record_id(
            run_id=run_id,
            attempt_id=attempt_id,
            role=manifest.role.value,
            manifest_id=manifest.manifest_id,
        ),
        run_id=run_id,
        attempt_id=attempt_id,
        role=manifest.role.value,
        manifest_id=manifest.manifest_id,
        manifest_content_hash=manifest.content_hash,
        state_version_id=manifest.state_version_id,
        estimated_tokens=manifest.estimated_tokens,
        capsule_id=None if capsule is None else capsule.capsule_id,
        recorded_at=stamp,
    )
    return store.append_pre_call_manifest(record)


def link_manifest_provider_tokens(
    store: RoleRetrievalManifestStore,
    *,
    manifest: ContextManifest,
    usage: ActualProviderAttemptUsage,
    recorded_at: datetime | None = None,
) -> ProviderAttemptTokenLink:
    """Link manifest estimated tokens to WP1 actual usage without mutating manifest."""
    stamp = require_utc_datetime(
        recorded_at or datetime.now(tz=UTC),
        field_name="recorded_at",
    )
    link = ProviderAttemptTokenLink(
        link_id=provider_attempt_token_link_id(
            manifest_id=manifest.manifest_id,
            provider_attempt_id=usage.provider_attempt_id,
        ),
        manifest_id=manifest.manifest_id,
        provider_attempt_id=usage.provider_attempt_id,
        estimated_tokens=manifest.estimated_tokens,
        actual_prompt_tokens=usage.prompt_tokens,
        actual_completion_tokens=usage.completion_tokens,
        recorded_at=stamp,
    )
    return store.append_provider_token_link(link)


def _parse_optional_date(raw: Any) -> date | None:
    if raw in (None, ""):
        return None
    return date.fromisoformat(str(raw)[:10])


def _dispatcher_requires_pin(
    *,
    retrieval_pin: RetrievalQueryPin | None,
    pin_mode: RetrievalManifestMode,
    tool_name: str,
) -> str | None:
    if pin_mode is not RetrievalManifestMode.ENFORCE:
        return None
    if retrieval_pin is None:
        return f"Error: {tool_name} requires a context manifest pin in enforce mode"
    return None


def build_research_tool_dispatcher(
    client: SupabaseClient,
    *,
    run_date: date,
    phase: RetrievalPhase,
    cache: ResearchCache | None = None,
    watchlist: tuple[str, ...] = (),
    retrieval_pin: RetrievalQueryPin | None = None,
    pin_mode: RetrievalManifestMode | None = None,
) -> Callable[[str, dict[str, Any]], str]:
    """Return ``execute_tool(name, args) -> json_str`` for retrieval tools."""
    effective_mode = pin_mode or resolve_retrieval_manifest_mode()
    effective_pin = retrieval_pin
    if effective_mode is RetrievalManifestMode.OFF:
        effective_pin = None

    def execute_tool(name: str, args: dict[str, Any]) -> str:
        try:
            pin_err = _dispatcher_requires_pin(
                retrieval_pin=effective_pin,
                pin_mode=effective_mode,
                tool_name=name,
            )
            if pin_err is not None:
                return pin_err

            if name == "query_research":
                result = query_research(
                    client,
                    run_date=run_date,
                    document_key=args.get("document_key"),
                    segment=args.get("segment"),
                    as_of_date=_parse_optional_date(args.get("as_of_date")),
                    phase=phase,
                    cache=cache,
                    retrieval_pin=effective_pin,
                )
            elif name == "fetch_prior_document":
                document_key = args.get("document_key")
                if not document_key:
                    return "Error: fetch_prior_document requires document_key"
                research = query_research(
                    client,
                    run_date=run_date,
                    document_key=str(document_key),
                    as_of_date=_parse_optional_date(args.get("as_of_date")),
                    phase=phase,
                    cache=cache,
                    retrieval_pin=effective_pin,
                )
                if "error" in research:
                    result = research
                else:
                    payload = research.get("payload")
                    body = payload if isinstance(payload, dict) else {}
                    result = extract_section(body, args.get("section_path"))
            elif name == "query_portfolio":
                result = query_portfolio(
                    client,
                    run_date=run_date,
                    phase=phase,
                    as_of_date=_parse_optional_date(args.get("as_of_date")),
                    ticker=args.get("ticker"),
                    watchlist=watchlist,
                    retrieval_pin=effective_pin,
                )
            else:
                return f"Error: unknown tool {name!r}"
            return json.dumps(result, default=str)
        except Exception as exc:  # tool errors are returned to the model
            logger.warning("research tool %s failed: %s", name, exc)
            return f"Error: {name} failed: {exc}"

    return execute_tool
