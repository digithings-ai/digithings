# digibase

Shared **digithings** building blocks for HTTP services:

- **HTTP** — outbound `X-Request-ID` header helper for service-to-service calls.
- **Errors** — consistent JSON error envelope for FastAPI (`code`, `message`, `request_id`).
- **Audit** — shared redaction keys for audit payloads.
- **OpenTelemetry** (optional extra `digibase[otel]`) — wire FastAPI + httpx when
  `DIGI_OTEL_ENDPOINT` or `OTEL_EXPORTER_OTLP_ENDPOINT` is set. No-op otherwise.

Install (monorepo):

```bash
pip install -e "./digibase"
pip install -e "./digibase[otel]"   # tracing
```

See [ARCHITECTURE.md](../ARCHITECTURE.md) for API compatibility and versioning.

### digibase data plane (roadmap)

The **`digibase` package** stays a small **library**. A future **digibase HTTP service** would centralize managed **Postgres**, **cache (Redis)**, and optional **object/vector connection policy** for digichat, digigraph checkpoints, digikey, and other services — with digikey-scoped credentials instead of duplicating secrets in every container. **Today** each service uses direct URLs (`DIGICHAT_DATABASE_URL`, etc.); migration would be phased and optional.

**Full vision, scope, and phasing:** [ARCHITECTURE.md](ARCHITECTURE.md).
