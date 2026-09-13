---
type: api-operations-guide
title: Status API and Operations
description: digismith HTTP surface and operations — health probes, secret-free status, metrics, middleware, env vars, and container wiring.
tags: [digismith, status-api, operations, health, metrics]
sources:
  - id: openwiki-source-acc01443fc8b95f02bdc8db2
    resource: repo://digibase/src/digibase/otel.py
  - id: openwiki-source-5c7b6be6bf0bcff60bbd689d
    resource: repo://digismith/Dockerfile
  - id: openwiki-source-e502a2c67cf187dc015ba472
    resource: repo://digismith/src/digismith/config.py
  - id: openwiki-source-01a7f90e3c3e6e8ce426b71e
    resource: repo://digismith/src/digismith/server.py
  - id: openwiki-source-77a4ffd4726d030792a3851c
    resource: repo://tests/dsm/test_cors.py
  - id: openwiki-source-951b7db648e549f088d67857
    resource: repo://tests/dsm/test_healthz.py
  - id: openwiki-source-d7f6e17132bab6b5e28c2b7a
    resource: repo://tests/dsm/test_metrics_endpoint.py
  - id: openwiki-source-9a4673012f353df9d1250866
    resource: repo://tests/dsm/test_server.py
generated: { by: "opencode", at: "2026-09-07T22:31:53.755Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# Status API and Operations

The digismith HTTP service (`digismith.server:app`) is a thin, read-only
surface: two liveness probes, one secret-free tracing-status diagnostic, and
a Prometheus metrics endpoint, fronted by shared digibase middleware. It
holds no state and is optional — removing the container never breaks
tracing, which flows directly from instrumented processes to LangSmith.

## Liveness: `/healthz` and `/health`

- `GET /healthz` → `{"ok": true}`. This is the preferred liveness probe and
  the Docker Compose healthcheck target. It is auth-exempt, secret-free, and
  safe for load balancers.
- `GET /health` → `{"status": "ok"}`. Retained for backward compatibility.

Contract: `/healthz` never replaces `/v1/status` — both must stay available.
Liveness answers "is the process up"; status answers "is tracing configured".

## Operator diagnostic: `GET /v1/status`

Returns a `SmithStatus` object describing the runtime tracing configuration:

```json
{
  "version": "0.1.0",
  "tracing_configured": true,
  "langsmith_sdk_installed": true,
  "langsmith_host": "api.smith.langchain.com",
  "request_id": "1f0b9c3e4a7d4f62a9c58d1e3c9b2a10"
}
```

Semantics:

- `tracing_configured` is true only when `LANGSMITH_API_KEY` is non-empty
  **and** the `langsmith` package is importable.
- `langsmith_host` is only the hostname parsed out of `LANGSMITH_ENDPOINT`
  (no path, credentials, or query string); it defaults to
  `api.smith.langchain.com` when the variable is unset.
- `request_id` echoes the request's `X-Request-ID` (via the shared
  request-ID middleware) so operators can correlate the response with logs.
- The response is public metadata by design: it never contains the API key
  or the full endpoint URL. Tests assert the key material appears nowhere
  in the response body.

A richer `/v1/status/detailed` endpoint with a live LangSmith connectivity
check is explicitly deferred — do not document or implement it here.

## Metrics: `GET /metrics`

Installed via the shared `digibase.metrics.install_metrics` helper with
`service="digismith"`. The endpoint exposes the standard cross-service
series (`http_requests_total`, `http_request_duration_seconds`,
`http_requests_in_flight`) labelled with `service`, `version`, and
`environment` (`version` from the package `__version__`, `environment` from
`DIGI_ENV`, default `"dev"`). Like `/healthz`, it is unauthenticated for
internal Prometheus scraping. digismith does not export trace-derived
counters — that remains a Phase 2 follow-up.

## Middleware stack

In order at app construction: Prometheus instrumentation, CORS
(`digibase.cors.install_cors` with `service="digismith"`), request-ID
middleware plus request-ID logging, FastAPI error handlers, and OTel
FastAPI auto-instrumentation (`setup_otel_fastapi`, a no-op unless
`OTEL_EXPORTER_OTLP_ENDPOINT` is set).

CORS allowlist precedence is `DIGISMITH_CORS_ORIGINS` →
`DIGI_CORS_ORIGINS` → legacy `DIGI_ALLOWED_ORIGINS`, defaulting to empty
(deny). Origins not on the allowlist receive no
`access-control-allow-origin` response header.

## Environment variables

| Variable | Required | Effect |
|----------|----------|--------|
| `LANGSMITH_API_KEY` | No | Enables trace export; absence makes `traceable` a no-op |
| `LANGSMITH_ENDPOINT` | No | LangSmith base URL; only its hostname surfaces in `/v1/status` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | When set, enables OTel HTTP/protobuf export of the service's own HTTP spans |
| `DIGI_ENV` | No | Environment label on metrics (default `"dev"`) |
| `DIGI_PII_PATTERNS` | No | Extra comma-separated redaction regexes (see tracing page) |
| `DIGISMITH_CORS_ORIGINS` / `DIGI_CORS_ORIGINS` | No | CORS allowlist |

All are sourced from `.env` via `env_file` in Compose; the key lives in the
container environment, so host access to `docker inspect`/`exec` is part of
the trust boundary.

## Container wiring

The Compose service builds from the repo root (`digismith/Dockerfile`,
which installs `digibase` then `digismith[langsmith]`), publishes
`127.0.0.1:8003:8003` on the host, and healthchecks
`http://127.0.0.1:8003/healthz` every 15s. The image runs uvicorn as
`digismith.server:app --host 0.0.0.0 --port 8003`. No other service depends
on it; `digigraph` carries a reserved `DIGISMITH_URL` and digichat a
`DIGISMITH_INTERNAL_URL`, both for future status polling, neither read by
service code today.

## Smoke checks

```bash
curl -s http://localhost:8003/healthz    # {"ok": true}
curl -s http://localhost:8003/v1/status  # SmithStatus JSON, no secrets
curl -s http://localhost:8003/metrics    # Prometheus text exposition
```
