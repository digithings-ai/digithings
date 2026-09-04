"""digismith HTTP API: health and non-sensitive tracing status."""

from __future__ import annotations

from digibase.cors import install_cors
from digibase.errors import register_fastapi_error_handlers
from digibase.http import install_request_id_logging, install_request_id_middleware
from digibase.metrics import install_metrics
from digibase.otel import setup_otel_fastapi
from fastapi import FastAPI, Request

from digismith import __version__
from digismith.config import (
    SmithStatus,
    langsmith_host_sanitized,
    langsmith_sdk_importable,
    tracing_enabled,
)

app = FastAPI(
    title="digismith",
    description=(
        "LangSmith-aligned observability control plane for digithings. "
        "HTTP surface is intentionally thin (health + secret-free status). "
        "Interactive docs: `/docs` (Swagger) and `/redoc`."
    ),
    version=__version__,
    openapi_tags=[
        {"name": "health", "description": "Liveness probes."},
        {"name": "status", "description": "Non-sensitive tracing configuration status."},
    ],
)
install_metrics(app, service="digismith", version=__version__)
install_cors(app, service="digismith")
install_request_id_middleware(app)
install_request_id_logging()


@app.get("/health", tags=["health"], summary="Legacy health check")
def health() -> dict[str, str]:
    """Legacy health check (kept for back-compat)."""
    return {"status": "ok"}


@app.get("/healthz", tags=["health"], summary="Liveness probe")
def healthz() -> dict[str, bool]:
    """Minimal liveness probe. Auth-exempt, secret-free.

    Returns HTTP 200 with ``{"ok": true}``. For richer diagnostics (tracing
    configuration, LangSmith host), see ``/v1/status``.
    """
    return {"ok": True}


@app.get("/v1/status", response_model=SmithStatus, tags=["status"], summary="Tracing status")
def status(request: Request) -> SmithStatus:
    return SmithStatus(
        version=__version__,
        tracing_configured=tracing_enabled(),
        langsmith_sdk_installed=langsmith_sdk_importable(),
        langsmith_host=langsmith_host_sanitized(),
        request_id=getattr(request.state, "request_id", None),
    )


register_fastapi_error_handlers(app, service="digismith")
setup_otel_fastapi(app, service_name="digismith", service_version=__version__)
