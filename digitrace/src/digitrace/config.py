"""Environment-driven tracing configuration (no secrets in API responses).

digitrace is in-house first. The default export destination is the in-house
digitrace OTLP ingest (``otel``), and with no endpoint at all the backend is
``none`` — a vendor is never chosen implicitly.

LangSmith and Langfuse-OTLP are *supported, optional* integrations (ADR-0036
amendment): each is selected only by its own environment variables, on top of
the generic path. ADR-0036 retired the self-hosted Langfuse *deployment*, not
the ability to export to a vendor collector over OTLP.
"""

from __future__ import annotations

import os
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

#: The resolved export backend. ``dual`` means a vendor SDK leg and an OTLP leg
#: are both configured. Never derived from an unset variable.
ExportBackend = Literal["dual", "langsmith", "langfuse-otlp", "otel", "none"]


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
    # Optional vendor integrations (LangSmith + Langfuse-OTLP). Non-default by
    # construction and never selected implicitly. All fields are non-secret
    # (booleans + sanitized host only).
    langfuse_configured: bool = Field(
        default=False,
        description="A Langfuse-specific endpoint/host env var is set",
    )
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
        description="One of dual|langsmith|langfuse-otlp|otel|none (in-house otel is the default)",
    )
    langfuse_host: str | None = Field(
        default=None,
        description="Sanitized Langfuse host (no secrets); null unless configured",
    )


# Temporary compat alias for the pre-rename model name (Phase 0, #4929).
# Prefer TraceStatus in new code; SmithStatus will be removed in Phase 3.
SmithStatus = TraceStatus


# Optional Langfuse integration. Langfuse OTLP ingest is plain OTel
# HTTP/protobuf, so that leg reuses the standard OTLP endpoint + headers
# variables already honored by digibase.otel (headers carry the Langfuse
# public:secret Basic auth). LANGSMITH_ENDPOINT always stays the real
# LangSmith API — never point it at Langfuse.
_LANGFUSE_ENDPOINT_ENVS = (
    "DIGITRACE_LANGFUSE_OTLP_ENDPOINT",
    "LANGFUSE_OTLP_ENDPOINT",
)
_LANGFUSE_HOST_ENVS = ("LANGFUSE_HOST", "LANGFUSE_URL")
# In-house digitrace first: DIGI_OTEL_ENDPOINT / DIGITRACE_OTLP_ENDPOINT are
# what the stack sets. The Langfuse names are accepted for operators who
# really do export to a Langfuse collector.
_OTLP_ENDPOINT_ENVS = (
    "DIGI_OTEL_ENDPOINT",
    "DIGITRACE_OTLP_ENDPOINT",
    *_LANGFUSE_ENDPOINT_ENVS,
    "OTEL_EXPORTER_OTLP_ENDPOINT",
)


def langfuse_otlp_endpoint() -> str:
    """Return the configured Langfuse OTLP endpoint, or ``""`` when unset."""
    for key in _LANGFUSE_ENDPOINT_ENVS:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def langfuse_configured() -> bool:
    """True when a Langfuse-specific endpoint/host env var is set (no secret check)."""
    if langfuse_otlp_endpoint():
        return True
    return any((os.environ.get(key) or "").strip() for key in _LANGFUSE_HOST_ENVS)


def otel_export_configured() -> bool:
    """True when any OTLP endpoint env var is set (the OTel fan-out leg is active)."""
    return any((os.environ.get(key) or "").strip() for key in _OTLP_ENDPOINT_ENVS)


def langfuse_host_sanitized() -> str | None:
    """Hostname of the configured Langfuse endpoint/host (no path, credentials, or query)."""
    raw = langfuse_otlp_endpoint()
    if not raw:
        for key in _LANGFUSE_HOST_ENVS:
            value = (os.environ.get(key) or "").strip()
            if value:
                raw = value
                break
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    return urlparse(raw).hostname


def dual_export_enabled() -> bool:
    """True when both the LangSmith leg and an OTLP leg (e.g. Langfuse) are active."""
    return langsmith_configured() and otel_export_configured()


def export_backend() -> ExportBackend:
    """Resolved backend: ``dual|langsmith|langfuse-otlp|otel|none`` (no secrets).

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
        return "langfuse-otlp" if langfuse_configured() else "otel"
    return "none"
