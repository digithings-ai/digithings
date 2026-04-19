"""DigiSmith HTTP API: health and non-sensitive tracing status."""

from __future__ import annotations

import uuid

from digibase.errors import register_fastapi_error_handlers
from digibase.metrics import install_metrics
from digibase.otel import setup_otel_fastapi
from fastapi import FastAPI, Request

from digismith import __version__
from digismith.config import SmithStatus, langsmith_host_sanitized, langsmith_sdk_importable, tracing_enabled

app = FastAPI(
    title="DigiSmith",
    description="LangSmith-aligned observability control plane (DigiThings)",
    version=__version__,
)
install_metrics(app, service="digismith")


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


@app.get("/health")
def health() -> dict[str, str]:
    """Legacy health check (kept for back-compat)."""
    return {"status": "ok"}


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    """Minimal liveness probe. Auth-exempt, secret-free.

    Returns HTTP 200 with ``{"ok": true}``. For richer diagnostics (tracing
    configuration, LangSmith host), see ``/v1/status``.
    """
    return {"ok": True}


@app.get("/v1/status", response_model=SmithStatus)
def status() -> SmithStatus:
    return SmithStatus(
        version=__version__,
        tracing_configured=tracing_enabled(),
        langsmith_sdk_installed=langsmith_sdk_importable(),
        langsmith_host=langsmith_host_sanitized(),
    )


register_fastapi_error_handlers(app, service="digismith")
setup_otel_fastapi(app, service_name="digismith")
