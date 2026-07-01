---
title: "digibase — API reference"
type: reference
status: generated
created: 2026-06-29
tags:
  - api
  - support
relevance:
  - digibase
---
# digibase — API reference

> The shared Python library every service builds on — and nothing more.

**Role:** Shared HTTP + audit library · **Tier:** support

## Overview
Not a service but a deliberately minimal library: auth middleware, error handlers, request-ID logging, and a Prometheus metrics endpoint.

Imported by every other module so they all behave consistently, with optional OpenTelemetry setup.

## Authentication
Shared Python library imported by every service — not a network surface.


## Run locally
```bash
# installed as a dependency of each service; no standalone run
```

## Configuration
- `DIGI_ENV` (default `dev`): Environment label for metrics.
- `DIGI_CORS_ORIGINS`: Global CORS allowlist (comma-separated).
- `DIGI_PII_PATTERNS`: Extra regex patterns for PII redaction.

## Public interface
- `from digibase.errors import register_fastapi_error_handlers` — Standard error envelope: {error:{code,message,request_id,service}}.
- `from digibase.http import outbound_service_headers` — Builds X-Request-ID + Authorization headers for service-to-service calls.
- `from digibase.http import install_request_id_middleware` — Reads/generates X-Request-ID, stores on request.state, echoes on the response.
- `from digibase.audit import redact_mapping` — Redacts password/api_key/token/secret keys from a payload before logging.
- `from digibase.metrics import install_metrics` — Mounts Prometheus /metrics with http_requests_total / _duration / _in_flight.
- `from digibase.otel import setup_otel_fastapi` — Optional OTel wiring; no-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set.

## Stack
Pydantic, FastAPI, Prometheus, OpenTelemetry

## Related
digismith, digisearch

## Links
- [Source](https://github.com/digithings-ai)

See also [[digibase]].
