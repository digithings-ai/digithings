# digibase

Shared **DigiThings** building blocks for HTTP services:

- **HTTP** — outbound `X-Request-ID` header helper for service-to-service calls.
- **Errors** — consistent JSON error envelope for FastAPI (`code`, `message`, `request_id`).
- **Audit** — shared redaction keys for audit payloads.
- **OpenTelemetry** (optional extra `digibase[otel]`) — wire FastAPI when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.

Install (monorepo):

```bash
pip install -e "./digibase"
pip install -e "./digibase[otel]"   # tracing
```

See [ARCHITECTURE.md](../ARCHITECTURE.md) for API compatibility and versioning.

### DigiBase data plane (roadmap)

The **`digibase` package** stays a small **library**. A future **DigiBase HTTP service** would centralize managed **Postgres**, **cache (Redis)**, and optional **object/vector connection policy** for DigiChat, DigiGraph checkpoints, DigiKey, and other services — with DigiKey-scoped credentials instead of duplicating secrets in every container. **Today** each service uses direct URLs (`DIGICHAT_DATABASE_URL`, etc.); migration would be phased and optional.

**Full vision, scope, and phasing:** [DIGIBASE.md](DIGIBASE.md).
