"""Optional OpenTelemetry wiring for FastAPI (OTLP HTTP)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def setup_otel_fastapi(app: Any, *, service_name: str) -> None:
    """Instrument *app* when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set. No-op otherwise.

    Requires ``digibase[otel]``. Sets batch span export to the configured OTLP endpoint.
    """
    endpoint = (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
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
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but OpenTelemetry packages are missing. "
            "Install digibase[otel] on this service."
        )
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry tracing enabled for service=%s endpoint=%s", service_name, endpoint)


__all__ = ["setup_otel_fastapi"]
