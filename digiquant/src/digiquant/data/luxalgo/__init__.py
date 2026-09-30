"""LuxAlgo Library thin wrap (#4779 P0).

A thin client over the hosted LuxAlgo MCP (``https://mcp.luxalgo.com/mcp``,
streamable HTTP JSON-RPC), mirroring the digifetch x Gloomberb layering: the
``luxalgo_*`` MCP tools (registered in ``mcp_server.py``) and the orchestrator
manifest schemas (``orchestrator_tools.py``) share the client, envelope, and
dispatcher in this package. The in-process agent surface for the pipeline
lives in :mod:`digiquant.data.luxalgo.agent_tools` — the manifest-generated
schemas, the research subset, and the dispatcher; the shared client factory
and envelope serializer also live there and ``mcp_server`` imports them.

P0 subset (Library research only): search, get_concept, get_indicator
(metadata — never source code), list_concepts, list_indicators, list_tags,
list_families, get_family. All keyless (``free``), read-scope, default-ON
behind ``LUXALGO_ENABLED``.
"""

from __future__ import annotations

from .agent_tools import (
    LUXALGO_DISPATCH,
    LUXALGO_TOOLS,
    RESEARCH_TOOLS,
    LuxalgoDispatch,
    available_luxalgo_tools,
    build_luxalgo_client,
    build_luxalgo_tool_dispatcher,
    close_luxalgo_client,
    luxalgo_envelope_json,
)
from .attribution import (
    LUXALGO_ATTRIBUTION,
    LUXALGO_LIBRARY_URL,
    LUXALGO_LICENSE_NOTE,
    LUXALGO_LICENSE_STATE_NOTE_DISABLED,
    LUXALGO_LICENSE_STATE_NOTE_ENABLED,
    attribution_fields,
    commercial_license_note,
)
from .client import (
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    LUXALGO_CONTEXT,
    LUXALGO_ENABLED_ENV,
    LUXALGO_MCP_URL,
    LuxAlgoClient,
    luxalgo_enabled,
    luxalgo_error_message,
)
from .entitlements import (
    ENTITLEMENT_DESCRIPTIONS,
    TOOL_ENTITLEMENTS,
    Entitlement,
    entitlement_for,
    entitlement_note,
    with_entitlement_note,
)
from .license_guard import (
    LUXALGO_COMMERCIAL_LICENSE_ENV,
    PAID_RENDER_SURFACES,
    PERSIST_SINKS,
    SCAN_ALLOWLIST,
    SOURCE_CODE_PAYLOAD_KEYS,
    SOURCE_CODE_TOOL_NAME,
    SOURCE_CODE_TOOL_NAMES,
    SOURCE_CODE_UPSTREAM_TOOL,
    LicenseBoundaryError,
    assert_payload_has_no_source_code,
    is_source_code_tool,
    luxalgo_commercial_license_enabled,
    payload_contains_source_code,
    run_boundary_checks,
    scan_source_code_references,
    source_code_refusal_message,
    source_code_violations,
)
from .models import (
    PROVIDER_ID,
    SOURCE,
    ErrorCode,
    LibraryGetConceptEnvelope,
    LibraryGetConceptInput,
    LibraryGetFamilyEnvelope,
    LibraryGetFamilyInput,
    LibraryGetIndicatorEnvelope,
    LibraryGetIndicatorInput,
    LibraryListConceptsEnvelope,
    LibraryListConceptsInput,
    LibraryListFamiliesEnvelope,
    LibraryListFamiliesInput,
    LibraryListIndicatorsEnvelope,
    LibraryListIndicatorsInput,
    LibraryListTagsEnvelope,
    LibraryListTagsInput,
    LibrarySearchEnvelope,
    LibrarySearchInput,
    LuxalgoEnvelope,
    LuxalgoError,
    envelope_error,
)

__all__ = [
    # in-process agent tool surface
    "LUXALGO_TOOLS",
    "LUXALGO_DISPATCH",
    "LuxalgoDispatch",
    "RESEARCH_TOOLS",
    "available_luxalgo_tools",
    "build_luxalgo_tool_dispatcher",
    "build_luxalgo_client",
    "close_luxalgo_client",
    "luxalgo_envelope_json",
    # attribution
    "LUXALGO_ATTRIBUTION",
    "LUXALGO_LIBRARY_URL",
    "LUXALGO_LICENSE_NOTE",
    "LUXALGO_LICENSE_STATE_NOTE_ENABLED",
    "LUXALGO_LICENSE_STATE_NOTE_DISABLED",
    "commercial_license_note",
    "attribution_fields",
    # client
    "LuxAlgoClient",
    "luxalgo_enabled",
    "luxalgo_error_message",
    "LUXALGO_MCP_URL",
    "LUXALGO_ENABLED_ENV",
    "LUXALGO_CONTEXT",
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    # entitlements
    "Entitlement",
    "TOOL_ENTITLEMENTS",
    "ENTITLEMENT_DESCRIPTIONS",
    "entitlement_for",
    "entitlement_note",
    "with_entitlement_note",
    # commercial-license guard (#4845)
    "LUXALGO_COMMERCIAL_LICENSE_ENV",
    "luxalgo_commercial_license_enabled",
    "SOURCE_CODE_UPSTREAM_TOOL",
    "SOURCE_CODE_TOOL_NAME",
    "SOURCE_CODE_TOOL_NAMES",
    "PERSIST_SINKS",
    "PAID_RENDER_SURFACES",
    "SOURCE_CODE_PAYLOAD_KEYS",
    "SCAN_ALLOWLIST",
    "LicenseBoundaryError",
    "is_source_code_tool",
    "source_code_refusal_message",
    "payload_contains_source_code",
    "assert_payload_has_no_source_code",
    "source_code_violations",
    "scan_source_code_references",
    "run_boundary_checks",
    # models
    "SOURCE",
    "PROVIDER_ID",
    "ErrorCode",
    "LuxalgoEnvelope",
    "LuxalgoError",
    "envelope_error",
    "LibrarySearchInput",
    "LibraryGetConceptInput",
    "LibraryGetIndicatorInput",
    "LibraryListConceptsInput",
    "LibraryListIndicatorsInput",
    "LibraryListTagsInput",
    "LibraryListFamiliesInput",
    "LibraryGetFamilyInput",
    "LibrarySearchEnvelope",
    "LibraryGetConceptEnvelope",
    "LibraryGetIndicatorEnvelope",
    "LibraryListConceptsEnvelope",
    "LibraryListIndicatorsEnvelope",
    "LibraryListTagsEnvelope",
    "LibraryListFamiliesEnvelope",
    "LibraryGetFamilyEnvelope",
]
