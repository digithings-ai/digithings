---
type: service-architecture
title: digitrace Architecture
description: Module map and design of digitrace — conditional LangSmith plus OTLP tracing library plus a stateless status HTTP service.
tags: [digitrace, observability, langsmith, architecture]
sources:
  - id: openwiki-source-3b0f3d164015c293da5dd7f8
    resource: repo://digillm/src/digillm/client.py
  - id: openwiki-source-5c7b6be6bf0bcff60bbd689d
    resource: repo://digitrace/Dockerfile
  - id: openwiki-source-547ed06a5101c68f4d4922cc
    resource: repo://digitrace/pyproject.toml
  - id: openwiki-source-e502a2c67cf187dc015ba472
    resource: repo://digitrace/src/digitrace/config.py
  - id: openwiki-source-01a7f90e3c3e6e8ce426b71e
    resource: repo://digitrace/src/digitrace/server.py
  - id: openwiki-source-c00fdd1354f900a1d45b111a
    resource: repo://digitrace/src/digitrace/trace.py
  - id: openwiki-source-ecab72add51be212920aacbe
    resource: repo://tests/dsm/test_trace.py
generated: { by: "opencode", at: "2026-09-07T22:31:53.755Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# digitrace Architecture

digitrace is the observability helper of the digithings stack. It has two
faces that are deliberately decoupled: a Python library that adds optional
LangSmith tracing and an OTel fan-out to any function via one decorator, and
a stateless HTTP microservice (port 8003) that reports whether tracing is
configured — without ever handling a trace itself.

## The two faces

**Library** (`digitrace.trace`, `digitrace.config`, `digitrace.redaction`):
a thin conditional wrapper around the LangSmith SDK plus an OTel leg. When
`LANGSMITH_API_KEY` is set and the `langsmith` package is importable,
`traceable(name)` wraps the target with `langsmith.traceable`. When an OTLP
endpoint is set, it also opens one OTel span per call (run name and short
correlation ids only). When neither leg is active it returns the original
function unmodified, so unconfigured environments pay zero per-call overhead.

**HTTP service** (`digitrace.server`, FastAPI app `digitrace.server:app`):
exposes liveness probes (`/health`, `/healthz`) and a secret-free operator
diagnostic (`GET /v1/status`), plus a Prometheus `/metrics` endpoint. The
service never receives, stores, or forwards spans — spans leave the
instrumented process on the LangSmith leg, the OTLP leg, or both.

## Module map

| File | Role |
|------|------|
| `__init__.py` | Package identity only (`__version__ = "0.1.0"`) |
| `config.py` | Env introspection (`tracing_enabled`, `langsmith_sdk_importable`, `langsmith_host_sanitized`, `otel_export_configured`, `export_backend`) + `TraceStatus` response model |
| `trace.py` | `traceable(name)` dual-export decorator with PII-redaction hookup |
| `redaction.py` | `PiiRedactor` — value-pattern redaction for span payloads |
| `server.py` | FastAPI app: `/health`, `/healthz`, `/v1/status`, `/metrics`, CORS, request-ID, OTel wiring |

There is no database, no background worker, no queue, and no internal graph.
digitrace is stateless by design; adding persistence or workers is explicitly
out of scope for the current implementation.

## Conditional-tracing pattern

`trace.py` guards the SDK import at module level and checks configuration at
decoration time (import time), not at call time:

- LangSmith SDK missing or `LANGSMITH_API_KEY` unset → that leg is skipped.
- Both present → the function is wrapped with `langsmith.traceable(name=…,
  process_inputs=…, process_outputs=…)`, where the process hooks are the
  `PiiRedactor` methods that scrub span payloads before submission.
- An OTLP endpoint set → `_maybe_wrap_otel` adds a span that does not carry
  prompts. Neither leg active → the original function object is returned
  unchanged.
- If the installed SDK version rejects the `process_*` kwargs, setup logs
  at debug and skips the LangSmith leg rather than crashing the host. The
  OTel leg still applies when it is configured.

One consequence: a key added after import does not activate tracing for
already-decorated functions in that process lifetime. Conversely,
`tracing_enabled()` re-reads the environment on every call, so it is safe
for tests that mutate env vars.

## Consumer boundary

The tracing path never touches the digitrace HTTP service. The current
in-repo consumer is `digillm`, which imports `traceable` lazily and degrades
to a local no-op decorator when digitrace is not installed — so `digillm`
works with or without the library, and removing the port-8003 container never
breaks tracing. The HTTP service exists solely for status introspection by
orchestrators and dashboards polling `/v1/status`.

## Dependencies and runtime

Hard dependencies are `pydantic>=2`, `fastapi`, `uvicorn`, and `digibase`
(shared CORS, metrics, request-ID, and OTel helpers). The LangSmith SDK is a
soft optional (`digitrace[tracing]`, alias `digitrace[langsmith]`), and OTel
support rides on `digibase[otel]` via `digitrace[otel]` — both absent-safe.
The Docker image installs `.[tracing]` and serves `digitrace.server:app` on
port 8003 via uvicorn.
The library modules perform no I/O at import time (no threads, sockets, or
file writes); OTel provider setup happens in `server.py` at app construction
and is itself a no-op unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set.

## Representative tests

- `tests/dsm/test_trace.py` — no-op without SDK/key, redaction hooks reach
  the SDK when active, graceful fallback on setup failure.
- `tests/dsm/test_server.py` — `/health` shape, `/v1/status` shape, and the
  no-secret response contract.
- `tests/dsm/test_redaction.py` — email/key/phone redaction, nested
  structures, `DIGI_PII_PATTERNS` extras, invalid-regex tolerance.
- `tests/dsm/test_healthz.py`, `tests/dsm/test_metrics_endpoint.py`,
  `tests/dsm/test_cors.py` — liveness, Prometheus label, and CORS contracts.
