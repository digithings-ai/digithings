# DigiClaw — Spec

**Port:** none (background process)  
**Role:** Heartbeat runner and append-only JSONL audit log.

## Capabilities

- Periodic heartbeat checks across all services (liveness polling)
- Append-only JSONL audit log for security-relevant events
- Audit record schema: `{timestamp, actor, action, resource, outcome, metadata}`

## Invariants

- No HTTP server — digiclaw is a background process/CLI only
- Audit log is append-only — records are never modified or deleted
- Heartbeat failures are logged and surfaced; they never throw unhandled exceptions
- Each audit record must include `timestamp` (ISO 8601 UTC), `actor`, and `action`

## Audit Event Categories

| Category | Description |
|----------|-------------|
| `auth` | Login, token issuance, API key operations |
| `data` | Document ingest, index mutations |
| `config` | Strategy registration, parameter changes |
| `system` | Service start/stop, heartbeat failures |

## Extension Pattern

Add new audit event types by extending the audit record schema (additive only). Never modify or re-emit existing records. New heartbeat targets are added to the target registry in `heartbeat_runner.py`.
