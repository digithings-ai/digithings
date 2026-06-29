---
title: "Conventions — guide"
type: reference
status: generated
created: 2026-06-29
tags:
  - api
  - guide
---
# Conventions

> Shared HTTP conventions across services — liveness, error envelope, correlation IDs, rate limits, CORS.

### Liveness vs status

`GET /healthz` is the auth-exempt liveness probe — always `{"ok": true}`, for load balancers. `GET /v1/status` (DigiGraph, DigiSmith) is a richer operator diagnostic; never use it for health checks.

### Error envelope

Every service returns the same error shape:

```json
{
  "error": {
    "code": "http_401",
    "message": "Bearer token required",
    "request_id": "req-…",
    "service": "digigraph"
  }
}
```

- `http_401` — missing/invalid token · `http_403` / `insufficient_scope` — scope denied.
- `validation_error` — request body failed validation.
- `rate_limited` — HTTP 429, with a `Retry-After` header.

### Correlation

Send `X-Request-ID` to correlate a call across services; it is generated if absent and echoed on the response and in the audit log.

### Rate limits & CORS

Mutating routes are rate-limited per IP (typically 10/min, 429 + `Retry-After` on breach). CORS uses an explicit allowlist (`DIGI_CORS_ORIGINS`) — no wildcard — with credentials enabled for session cookies.

See also [[digibase]].
