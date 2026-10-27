"""Environment-driven tracing configuration (no secrets in API responses).

digitrace is in-house first. The default export destination is the in-house
digitrace OTLP ingest (``otel``), and with no endpoint at all the backend is
``none`` — a vendor is never chosen implicitly.

LangSmith is a *supported, optional* integration: it is selected only by
``LANGSMITH_API_KEY``, on top of the generic path. ADR-0036 retired the
self-hosted Langfuse deployment and its OTLP export mode with it.
"""

from __future__ import annotations

import os
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

#: The resolved export backend. ``dual`` means a vendor SDK leg and an OTLP leg
#: are both configured. Never derived from an unset variable.
ExportBackend = Literal["dual", "langsmith", "otel", "none"]


def default_langsmith_endpoint() -> str:
    """Return LANGSMITH_ENDPOINT or LangSmith default API URL."""
    return os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").strip()


def langsmith_sdk_importable() -> bool:
    try:
        import langsmith  # noqa: F401

        return True
    except ImportError:
        return False


def langsmith_key_set() -> bool:
    """True when LANGSMITH_API_KEY is set (the operator asked for the integration)."""
    return bool((os.environ.get("LANGSMITH_API_KEY") or "").strip())


def langsmith_configured() -> bool:
    """True when the LangSmith leg can emit (key set + SDK importable)."""
    return langsmith_key_set() and langsmith_sdk_importable()


def tracing_enabled() -> bool:
    """True when at least one export leg is configured (see ``export_backend``)."""
    return export_backend() != "none"


def langsmith_host_sanitized() -> str | None:
    """Hostname of the configured LangSmith API (no path, credentials, or query).

    ``None`` unless the integration is configured, so status never implies a
    vendor backend that nobody selected.
    """
    if not langsmith_key_set() and not (os.environ.get("LANGSMITH_ENDPOINT") or "").strip():
        return None
    raw = default_langsmith_endpoint()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    return parsed.hostname


class TraceStatus(BaseModel):
    """Public status for GET /v1/status."""

    version: str = Field(description="digitrace package version")
    tracing_configured: bool = Field(description="At least one export leg is configured")
    langsmith_sdk_installed: bool = Field(description="langsmith Python package is importable")
    langsmith_host: str | None = Field(
        default=None,
        description="Sanitized API host from LANGSMITH_ENDPOINT (no secrets); null unless configured",
    )
    request_id: str | None = Field(
        default=None,
        description="X-Request-ID of the call that produced this status (echoed for correlation)",
    )
    # Optional LangSmith integration. Non-default by construction and never
    # selected implicitly. All fields are non-secret (booleans + sanitized host).
    otel_export_configured: bool = Field(
        default=False,
        description="An OTLP endpoint env var is set (OTel export leg active)",
    )
    dual_export: bool = Field(
        default=False,
        description="Both a vendor SDK leg and an OTLP leg are configured",
    )
    export_backend: str = Field(
        default="none",
        description="One of dual|langsmith|otel|none (in-house otel is the default)",
    )


# Temporary compat alias for the pre-rename model name (Phase 0, #4929).
# Prefer TraceStatus in new code; SmithStatus will be removed in Phase 3.
SmithStatus = TraceStatus


# The in-house digitrace OTLP ingest and the standard OTel alias are the only
# endpoint names this leaf keeps. LANGSMITH_ENDPOINT always stays the real
# LangSmith API.
_OTLP_ENDPOINT_ENVS = (
    "DIGI_OTEL_ENDPOINT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
)


def otel_export_configured() -> bool:
    """True when any OTLP endpoint env var is set (the OTel fan-out leg is active)."""
    return any((os.environ.get(key) or "").strip() for key in _OTLP_ENDPOINT_ENVS)


def dual_export_enabled() -> bool:
    """True when both the LangSmith leg and an OTLP leg are configured."""
    return export_backend() == "dual"


def export_backend() -> ExportBackend:
    """Resolved backend: ``dual|langsmith|otel|none`` (no secrets).

    Resolution is driven only by explicitly-set variables, so the default with
    nothing configured is ``none`` and with a plain OTLP endpoint it is the
    in-house ``otel`` — never a vendor. LangSmith counts as requested when its
    key is set; ``langsmith_sdk_installed`` reports whether it can actually emit.
    """
    langsmith = langsmith_key_set()
    otel = otel_export_configured()
    if langsmith and otel:
        return "dual"
    if langsmith:
        return "langsmith"
    if otel:
        return "otel"
    return "none"
