"""Environment-driven tracing configuration (no secrets in API responses).

digitrace is OTLP-only by design. External observability vendors are providers
it can export to over the generic OTLP endpoint/headers pair, never a backend
this library configures or a secret the stack provisions.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field


class TraceStatus(BaseModel):
    """Public status for GET /v1/status."""

    version: str = Field(description="digitrace package version")
    tracing_configured: bool = Field(
        description="An OTLP endpoint is set, so spans would be exported"
    )
    request_id: str | None = Field(
        default=None,
        description="X-Request-ID of the call that produced this status (echoed for correlation)",
    )
    otel_export_configured: bool = Field(
        default=False,
        description="An OTLP endpoint env var is set (OTel export leg active)",
    )
    export_backend: str = Field(
        default="none",
        description="One of otel|none",
    )


# Temporary compat alias for the pre-rename model name (Phase 0, #4929).
# Prefer TraceStatus in new code; SmithStatus will be removed in Phase 3.
SmithStatus = TraceStatus


# The in-house digitrace OTLP ingest is plain OTel HTTP/protobuf, so the leg
# reuses the standard OTLP endpoint + headers variables already honored by
# digibase.otel. Pointing any of them at a vendor collector is an operator
# choice, not something the stack provisions.
_OTLP_ENDPOINT_ENVS = (
    "DIGI_OTEL_ENDPOINT",
    "DIGITRACE_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
)


def otel_export_configured() -> bool:
    """True when any OTLP endpoint env var is set (the OTel export leg is active)."""
    return any((os.environ.get(key) or "").strip() for key in _OTLP_ENDPOINT_ENVS)


def tracing_enabled() -> bool:
    """True when tracing is configured (an OTLP endpoint is set)."""
    return otel_export_configured()


def export_backend() -> str:
    """Backend summary: ``otel|none`` (no secrets)."""
    return "otel" if otel_export_configured() else "none"
