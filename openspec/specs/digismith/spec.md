# DigiSmith — Spec

**Port:** 8003  
**Role:** LangSmith-aligned observability library and operator status API.

## Capabilities

- Distributed trace collection compatible with LangSmith schema
- Run/span lifecycle management
- Operator status endpoint reporting config and versions
- OTel integration for exporting traces

## Invariants

- `/healthz` is the liveness probe — auth-exempt, always `{"ok": true}`, no downstream checks
- `/v1/status` is the operator diagnostic — may report config/versions; not for load balancers
- Tracing is best-effort — a tracing failure must never cause a request to fail

## Public API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness probe |
| GET | `/v1/status` | Operator diagnostic (config, versions) |
| POST | `/v1/runs` | Ingest run/span data |

## Extension Pattern

New observability integrations are added as exporters, not as new HTTP endpoints. The `/v1/status` response schema is append-only — never remove fields.
