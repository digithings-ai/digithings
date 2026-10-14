---
title: "Conventions — guide"
type: reference
status: generated
created: 2026-10-02
tags:
  - api
  - guide
---
# Conventions

> Shared HTTP conventions across services — liveness, error envelope, correlation IDs, rate limits, CORS.

### Liveness vs status

`GET /healthz` is the auth-exempt liveness probe — always `{"ok": true}`, for load balancers. `GET /v1/status` on digitrace is a public operator diagnostic. On digigraph the same path requires `digigraph:workflow`. Do not point a load balancer at `/v1/status`.

### Auth errors

Failures from the shared auth middleware are a flat JSON body, not the envelope below.

```json
{
  "code": "unauthorized",
  "message": "Bearer token required"
}
```

- `unauthorized` (401) — no bearer token.
- `invalid_token` (401) — the token did not verify. `token_revoked` (401) — the `jti` is on the blocklist.
- `insufficient_scope` (403) — the token lacks the route's scope.
- `auth_not_configured` (503) — neither `DIGIKEY_JWKS_URL` nor `DIGIKEY_PUBLIC_KEY_PEM` is set.
- `auth_backend_unavailable` (503) — the revocation blocklist could not be read.

### Error envelope

HTTPException, request validation, and unhandled errors use the digibase envelope. Auth failures do not.

```json
{
  "error": {
    "code": "validation_error",
    "message": "field required",
    "request_id": "req-…",
    "service": "digigraph"
  }
}
```

- `http_<status>` — a raised HTTPException.
- `validation_error` — HTTP 422, the request body failed validation.
- `internal_error` — HTTP 500.

### Correlation

Send `X-Request-ID` to correlate a call across services; it is generated if absent and echoed on the response and in the audit log.

### Rate limits & CORS

digigraph, digiquant, and digisearch answer 429 with code `rate_limit_exceeded` and a `Retry-After` header. digikey answers 429 with `{"detail":"rate_limited","retry_after":N}` and the same header. `/health` and `/healthz` are unlimited. Per IP: `/workflow`, `/query`, and `/run_backtest` are 10/min; `/v1/chat/completions` is 60/min; `/ingest` is 30/min; other routes default to 30/min. CORS uses an explicit allowlist (`DIGI_CORS_ORIGINS`) — no wildcard — with credentials enabled for session cookies.

See also [[digibase]].
