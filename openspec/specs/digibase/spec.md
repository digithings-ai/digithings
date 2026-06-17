# DigiBase — Spec

**Port:** none (shared library)  
**Role:** Shared Python library providing error envelopes, HTTP helpers, and OTel instrumentation used by all services.

## Capabilities

- Standardised error envelope: `{"ok": false, "error": {"code": ..., "message": ...}}`
- HTTP client helpers with retry and timeout defaults
- OpenTelemetry span helpers for distributed tracing
- Common Pydantic v2 base models

## Invariants

- No service-specific logic — digibase must remain service-agnostic
- Polars is a permitted dependency; pandas is not
- No FastAPI dependency — digibase is a pure library
- Backwards-compatible changes only: never remove or rename exported symbols without a deprecation cycle

## Exported Surface

| Module | Purpose |
|--------|---------|
| `digibase.errors` | Error envelope types and helpers |
| `digibase.http` | Async HTTP client wrappers |
| `digibase.otel` | OTel span helpers |
| `digibase.models` | Shared Pydantic v2 base models |

## Extension Pattern

Add new shared utilities as new modules or functions. Never add service-specific logic. Keep imports lazy where possible to avoid circular dependencies.
