---
type: library-guide
title: digibase Library Guide
description: Shared digibase library — error envelopes, request-ID correlation, metrics, OTel, CORS, and audit redaction.
tags: [digibase, shared-library, errors, metrics, otel, audit]
sources:
  - id: openwiki-source-bc62a8a6a6223eadc1325793
    resource: repo://digibase/src/digibase/audit.py
  - id: openwiki-source-795f61c7d1eb8a0be7a67d5e
    resource: repo://digibase/src/digibase/errors.py
  - id: openwiki-source-6a2458b0d8001780e4f44c87
    resource: repo://digibase/src/digibase/http.py
  - id: openwiki-source-4a1d9573a5245c5e5174a455
    resource: repo://digibase/src/digibase/metrics.py
  - id: openwiki-source-acc01443fc8b95f02bdc8db2
    resource: repo://digibase/src/digibase/otel.py
generated: { by: "opencode", at: "2026-09-09T14:37:17.158Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# digibase Library Guide

digibase is a **library, not a service**: a zero-state Python package
installed in every service, with no port, no listener, and no persistence.
It standardizes six cross-cutting concerns so each service's `server.py`
is a few `install_*` calls. All helpers are side-effect-free at import;
a future data-plane *service* is roadmap only and must not be treated as
built.

## Error envelopes

`errors.ApiErrorEnvelope` is the fleet-wide shape —
`{"error": {"code", "message", "request_id", "service"}}`.
`json_error_response(...)` builds it (pulling the request ID from
`request.state` or the `X-Request-ID` header), and
`register_fastapi_error_handlers(app, service=...)` wires it for
`HTTPException` and validation errors. Field renames are fleet-wide
breaking changes.

## Request-ID correlation

`http.install_request_id_middleware(app)` assigns every inbound request a
hex ID (honoring an inbound `X-Request-ID`, generating one when absent)
and stashes it on `request.state`; `install_request_id_logging()` adds it
to log records. Register the middleware **after** rate limiting so the ID
wraps rejections too (Starlette LIFO). `outbound_service_headers(request_id,
bearer_token)` merges the correlation ID with an optional bearer for
service-to-service calls — it never logs or retains the token.

## Metrics

`metrics.install_metrics(app, service=..., version=..., environment=...)`
attaches ASGI middleware recording three series — `http_requests_total`
(counter), `http_request_duration_seconds` (histogram, 11 buckets 5ms→10s),
`http_requests_in_flight` (gauge) — labelled with service, version,
environment, method, route, and status, exposed unauthenticated at
`GET /metrics` for internal scraping.

## OTel

`otel.setup_otel_fastapi(app, service_name=...)` instruments the app with
OTLP/HTTP export **only** when `DIGI_OTEL_ENDPOINT` or
`OTEL_EXPORTER_OTLP_ENDPOINT` is set;
otherwise it is a strict no-op. Requires the `digibase[otel]` extra —
missing packages log a warning and continue without tracing.

## CORS

`cors.install_cors(app, service=...)` applies the shared allowlist with
precedence `{SERVICE}_CORS_ORIGINS` → `DIGI_CORS_ORIGINS` → legacy
`DIGI_ALLOWED_ORIGINS`, defaulting to empty (deny).

## Audit

`audit.redact_mapping(payload)` recursively replaces sensitive keys with
`[REDACTED]` (additive key-substring patterns — never narrow them), and
`audit.emit_event(...)` appends canonical `AuditEvent` JSONL lines
(`ts`, `event_type`, `agent_id`, redacted `payload`, plus sparse digikey
correlation fields). digiclaw's `audit_log()` delegates here; every
`audit.jsonl` writer must pass through redaction first.
