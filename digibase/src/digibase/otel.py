"""Optional OpenTelemetry wiring for FastAPI (OTLP HTTP)."""

from __future__ import annotations

import logging
import os
from typing import Any, MutableMapping

logger = logging.getLogger(__name__)

# Prefer the digithings alias; fall back to the OpenTelemetry standard env var.
_ENDPOINT_ENVS = ("DIGI_OTEL_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT")


def resolve_otel_endpoint() -> str:
    """Return the configured OTLP endpoint, or ``\"\"`` when tracing is disabled."""
    for key in _ENDPOINT_ENVS:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def inject_trace_context(headers: MutableMapping[str, str]) -> None:
    """Inject W3C ``traceparent`` / ``tracestate`` into *headers* when tracing is on.

    No-op when no endpoint is configured or when ``digibase[otel]`` packages are
    missing — safe to call from ``outbound_service_headers`` on every request.
    """
    if not resolve_otel_endpoint():
        return
    try:
        from opentelemetry.propagate import inject
    except ImportError:
        return
    inject(headers)


def setup_otel_fastapi(
    app: Any,
    *,
    service_name: str,
    service_version: str | None = None,
) -> None:
    """Instrument *app* when ``DIGI_OTEL_ENDPOINT`` or ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set.

    No-op otherwise (zero overhead). Requires ``digibase[otel]``.

    When enabled:
    - FastAPI incoming HTTP requests become root/server spans
    - httpx clients are instrumented so outbound LLM, digisearch, and digikey
      calls become child spans (when ``opentelemetry-instrumentation-httpx`` is
      installed via ``digibase[otel]``)
    - ``service.name`` and optional ``service.version`` are set on the resource
    """
    endpoint = resolve_otel_endpoint()
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "DIGI_OTEL_ENDPOINT/OTEL_EXPORTER_OTLP_ENDPOINT is set but OpenTelemetry "
            "packages are missing. Install digibase[otel] on this service."
        )
        return

    version = (
        (service_version or "").strip()
        or (os.environ.get("OTEL_SERVICE_VERSION") or "").strip()
        or (os.environ.get("DIGI_SERVICE_VERSION") or "").strip()
    )
    resource_attrs: dict[str, str] = {"service.name": service_name}
    if version:
        resource_attrs["service.version"] = version

    resource = Resource.create(resource_attrs)
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except ImportError:
        logger.debug(
            "opentelemetry-instrumentation-httpx not installed; "
            "outbound LLM/search/digikey spans will be limited"
        )

    logger.info(
        "OpenTelemetry tracing enabled for service=%s version=%s endpoint=%s",
        service_name,
        version or "-",
        endpoint,
    )


__all__ = [
    "inject_trace_context",
    "resolve_otel_endpoint",
    "setup_otel_fastapi",
]
