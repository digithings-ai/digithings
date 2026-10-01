"""Environment-driven tracing configuration (no secrets in API responses)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from pydantic import BaseModel, Field


def default_langsmith_endpoint() -> str:
    """Return LANGSMITH_ENDPOINT or LangSmith default API URL."""
    return os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").strip()


def langsmith_sdk_importable() -> bool:
    try:
        import langsmith  # noqa: F401

        return True
    except ImportError:
        return False


def tracing_enabled() -> bool:
    """True when an API key is set and the langsmith package is installed."""
    key = (os.environ.get("LANGSMITH_API_KEY") or "").strip()
    return bool(key) and langsmith_sdk_importable()


def langsmith_host_sanitized() -> str | None:
    """Hostname of the configured LangSmith API (no path, credentials, or query)."""
    raw = default_langsmith_endpoint()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = parsed.hostname
    return host


class TraceStatus(BaseModel):
    """Public status for GET /v1/status."""

    version: str = Field(description="digitrace package version")
    tracing_configured: bool = Field(
        description="LangSmith tracing would activate (key + langsmith installed)"
    )
    langsmith_sdk_installed: bool = Field(description="langsmith Python package is importable")
    langsmith_host: str | None = Field(
        default=None,
        description="Sanitized API host from LANGSMITH_ENDPOINT (no secrets)",
    )
    request_id: str | None = Field(
        default=None,
        description="X-Request-ID of the call that produced this status (echoed for correlation)",
    )
    # Phase 2 dual-export (#4931): LangSmith AND Langfuse-OTLP fan-out.
    # All fields are non-secret by construction (booleans + sanitized host only).
    langfuse_configured: bool = Field(
        default=False,
        description="A Langfuse-specific endpoint/host env var is set",
    )
    otel_export_configured: bool = Field(
        default=False,
        description="An OTLP endpoint env var is set (OTel fan-out leg active)",
    )
    dual_export: bool = Field(
        default=False,
        description="Both LangSmith and OTLP legs are active",
    )
    export_backend: str = Field(
        default="none",
        description="One of dual|langsmith|langfuse-otlp|otel|none",
    )
    langfuse_host: str | None = Field(
        default=None,
        description="Sanitized Langfuse host (no secrets)",
    )


# Temporary compat alias for the pre-rename model name (Phase 0, #4929).
# Prefer TraceStatus in new code; SmithStatus will be removed in Phase 3.
SmithStatus = TraceStatus


# Phase 2 dual-export env (#4931). Langfuse OTLP ingest is plain OTel
# HTTP/protobuf, so the Langfuse leg reuses the standard OTLP endpoint +
# headers variables already honored by digibase.otel (headers carry the
# Langfuse public:secret Basic auth). LANGSMITH_ENDPOINT always stays the
# real LangSmith API — never point it at Langfuse.
_LANGFUSE_ENDPOINT_ENVS = (
    "DIGITRACE_LANGFUSE_OTLP_ENDPOINT",
    "LANGFUSE_OTLP_ENDPOINT",
)
_LANGFUSE_HOST_ENVS = ("LANGFUSE_HOST", "LANGFUSE_URL")
_OTLP_ENDPOINT_ENVS = (
    "DIGITRACE_LANGFUSE_OTLP_ENDPOINT",
    "LANGFUSE_OTLP_ENDPOINT",
    "DIGI_OTEL_ENDPOINT",
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
    """True when both the LangSmith leg and the OTLP leg (e.g. Langfuse) are active."""
    return tracing_enabled() and otel_export_configured()


def export_backend() -> str:
    """Backend summary: ``dual|langsmith|langfuse-otlp|otel|none`` (no secrets)."""
    langsmith = tracing_enabled()
    otel = otel_export_configured()
    if langsmith and otel:
        return "dual"
    if langsmith:
        return "langsmith"
    if otel:
        return "langfuse-otlp" if langfuse_configured() else "otel"
    return "none"
