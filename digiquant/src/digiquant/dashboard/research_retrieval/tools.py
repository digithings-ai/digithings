"""LLM tool definitions for dashboard retrieval (spec §6.1).

WP14.4 binds drill-down dispatchers to compiled context manifests and persists
pre-call manifest rows plus WP1 token linkage telemetry.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import (  # scored-lint suppression: heterogeneous graph / dict shapes
    Any,
    Callable,
    get_args,
)

from digiquant.dashboard.envcompat import RETRIEVAL_MANIFEST_MODE, env_lookup
from digiquant.dashboard.research_retrieval.blinding import RetrievalPhase
from digiquant.dashboard.research_retrieval.cache import ResearchCache
from digiquant.dashboard.research_retrieval.context import ContextCapsule, ContextManifest
from digiquant.dashboard.research_retrieval.context_wiring import RoleContextWireResult
from digiquant.dashboard.research_retrieval.queries import (
    RetrievalManifestMode,
    RetrievalQueryPin,
    build_retrieval_query_pin,
    extract_section,
    query_portfolio,
    query_research,
    search_research,
)
from digiquant.dashboard.research_retrieval.store import (
    ActualProviderAttemptUsage,
    LoadedResearchState,
    PersistedRoleContextManifest,
    ProviderAttemptTokenLink,
    RoleRetrievalManifestStore,
    provider_attempt_token_link_id,
    role_context_manifest_record_id,
)
from digiquant.dashboard.temporal import require_utc_datetime
from digiquant.research.supabase_io import SupabaseClient

logger = logging.getLogger(__name__)

DIGIQUANT_RETRIEVAL_MANIFEST_MODE_ENV = "DIGIQUANT_RETRIEVAL_MANIFEST_MODE"

RESEARCH_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_research",
            "description": (
                "Search the research pipeline and book for prior work. Reads live rows from "
                "Supabase and transparently hydrates archived document payloads from R2. "
                "Use document_key (e.g. macro, equity, digest) or segment slug for an exact "
                "fetch; use dataset/date_from/date_to/ticker/sector/subject/doc_type for a "
                "filtered search. Defaults to the baseline run for the current run_date. "
                "Set include_prior=true to span prior days for continuity. When a context "
                "manifest pin is active, as_of_date must match an allowed ref. "
                "This is a read of stored rows: repeating a call with the same arguments "
                "returns the same rows, and re-phrasing the same question with a different "
                "subject/dataset/ticker cannot surface a row that was not already there. "
                "The document your own segment is writing today does not exist yet, so an "
                "exact fetch for it on the run date returns nothing by design — that is an "
                "answer, not a failure. "
                "Use it for continuity (one prior fetch per key) and stop; an empty result "
                "means the evidence genuinely is not in the store."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset": {
                        "type": "string",
                        "enum": [
                            "documents",
                            "daily_snapshots",
                            "theses",
                            "thesis_vehicles",
                            "positions",
                            "nav_history",
                            "portfolio_metrics",
                            "position_events",
                            "decision_log",
                        ],
                        "description": "Which research/book dataset to search (default documents)",
                    },
                    "run_type": {
                        "type": "string",
                        "description": "Pipeline run type (default baseline)",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Optional run identifier (decision_log)",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Inclusive lower bound YYYY-MM-DD",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Inclusive upper bound YYYY-MM-DD",
                    },
                    "document_key": {"type": "string"},
                    "segment": {"type": "string"},
                    "ticker": {"type": "string"},
                    "sector": {"type": "string"},
                    "subject": {
                        "type": "string",
                        "description": "Free-text match on title/category/key",
                    },
                    "doc_type": {"type": "string"},
                    "phase": {
                        "type": "string",
                        "enum": list(get_args(RetrievalPhase)),
                        "description": (
                            "Retrieval/blinding phase. In-process, the node's own phase "
                            "governs and cannot be raised by the caller."
                        ),
                    },
                    "include_prior": {
                        "type": "boolean",
                        "description": "Span prior days (default false = single run_date)",
                    },
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "limit": {"type": "integer", "description": "Max rows 1-500 (default 50)"},
                    "offset": {"type": "integer", "description": "Pagination offset (default 0)"},
                    "full_content": {
                        "type": "boolean",
                        "description": "Return full document content instead of a bounded preview",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_prior_document",
            "description": (
                "Fetch prior materialized document body (or one section) for edit-mode "
                "patching. Pass the segment slug or document_key exactly as published — one "
                "call is enough to read your prior document, and calling again returns the "
                "same bytes. The document for the current run date does not exist yet (you "
                "are writing it), so fetch the prior day's body for continuity and move on."
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
    """Read ``DIGIQUANT_RETRIEVAL_MANIFEST_MODE``; unknown values → shadow."""
    raw = env_lookup(RETRIEVAL_MANIFEST_MODE, default="shadow").strip().lower()
    try:
        return RetrievalManifestMode(raw)
    except ValueError:
        logger.warning(
            "invalid %s=%r; using shadow (allowed: off|shadow|enforce)",
            DIGIQUANT_RETRIEVAL_MANIFEST_MODE_ENV,
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
                search_keys = {
                    "dataset",
                    "run_type",
                    "run_id",
                    "date_from",
                    "date_to",
                    "ticker",
                    "sector",
                    "subject",
                    "doc_type",
                    "include_prior",
                    "limit",
                    "offset",
                    "full_content",
                }
                if search_keys & set(args):
                    result = search_research(
                        client,
                        run_date=run_date,
                        dataset=str(args.get("dataset") or "documents"),
                        run_type=str(args.get("run_type") or "baseline"),
                        run_id=args.get("run_id"),
                        date_from=_parse_optional_date(args.get("date_from")),
                        date_to=_parse_optional_date(args.get("date_to")),
                        document_key=args.get("document_key"),
                        segment=args.get("segment"),
                        ticker=args.get("ticker"),
                        sector=args.get("sector"),
                        subject=args.get("subject"),
                        doc_type=args.get("doc_type"),
                        include_prior=bool(args.get("include_prior", False)),
                        as_of_date=_parse_optional_date(args.get("as_of_date")),
                        limit=int(args.get("limit", 50)),
                        offset=int(args.get("offset", 0)),
                        full_content=bool(args.get("full_content", False)),
                        retrieval_phase=phase,
                        retrieval_pin=effective_pin,
                    )
                else:
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
