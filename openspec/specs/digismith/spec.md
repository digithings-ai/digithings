# DigiSmith — Spec

**Port:** 8003  
**Role:** LangSmith-aligned observability library and operator status API.

## Capabilities

- Distributed trace collection compatible with LangSmith schema
- Run/span lifecycle management (library, not HTTP API)
- Operator status endpoint reporting config and versions
- OTel integration for exporting traces

## Invariants

- `/healthz` is the liveness probe — auth-exempt, always `{"ok": true}`, no downstream checks
- `/v1/status` is the operator diagnostic — may report config/versions; not for load balancers
- Tracing is best-effort — a tracing failure must never cause a request to fail
- Run/span ingest is handled in-process via the library, not via an HTTP endpoint

## Public API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness probe |
| GET | `/v1/status` | Operator diagnostic (config, versions) |

## Extension Pattern

New observability integrations are added as exporters inside the library, not as new HTTP endpoints. The `/v1/status` response schema is append-only — never remove fields.
