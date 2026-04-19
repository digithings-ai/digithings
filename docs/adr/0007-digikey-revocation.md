# ADR 0007: JWT Revocation for DigiKey via jti Blocklist in Redis

**Status:** proposed
**Date:** 2026-04-19

## Context

DigiKey issues short-lived RS256 JWTs (default TTL 900 seconds) that downstream services — DigiGraph, DigiQuant, DigiSearch — verify locally against a cached JWKS document. DigiKey sits on the hot path for token exchange but is completely off the hot path for per-request verification. That is a deliberate scalability choice documented in `digikey/ARCHITECTURE.md` §7.

The current revocation story has a critical gap (§6 of the same doc): `revoked_at` on the `digikey_api_keys` table only blocks future token exchanges. Any JWT issued before a key is revoked remains cryptographically valid until `exp`. The `jti` claim is generated and embedded in every token but is written nowhere queryable at verification time.

Three concrete scenarios expose the blast radius:

| Scenario | Window of exposure |
|---|---|
| API key leaked (e.g., committed to a public repo) | Up to `DIGIKEY_JWT_TTL_SEC` (default 15 min) after `revoked_at` is set, for all JWTs already exchanged by the attacker |
| Employee offboarding — key deleted | Same as above: any session JWT in the employee's hands keeps working |
| Key compromise discovered hours later | Attacker may have exchanged many JWTs; all remain valid until their individual `exp` |

For a single-tenant dev deployment the 15-minute window is acceptable. For multi-tenant production use, where a leaked key could access all services with any scope that key was granted, it is not.

Issue #6 requires a mechanism to revoke issued JWTs before natural expiry. This ADR evaluates the options and selects one.

## Decision

**Introduce a `jti` blocklist backed by Redis with per-entry TTL equal to remaining token lifetime. Make the blocklist check a mandatory step in `DigiAuthMiddleware` on every protected request.**

### How it works

| Step | What happens | Where |
|---|---|---|
| Token exchange | `jwt_issue.py` writes `jti` → `exp` to DigiKey's DB (`jti_issued` table) at issue time | DigiKey |
| Revocation | New endpoint `POST /v1/admin/keys/{id}/revoke` queries all live `jti_issued` rows for that key (where `exp > now()`), writes each as a Redis key `jti:<uuid>` with `TTL = exp - now()` | DigiKey |
| Per-request check | `DigiAuthMiddleware.decode_token()` calls `Redis.exists(jti:<uuid>)` after signature verification but before returning 200 | Each consumer service |
| Self-cleaning | Redis keys expire automatically at `exp`; no background cleanup job needed | Redis |

### Key design choices

**Redis as new dependency.** DigiKey does not currently use Redis. The rate limiter in `ratelimit.py` is in-process. Adding Redis is a new infrastructure dependency — acknowledged in Consequences below. Redis is chosen over a Postgres `jti_blocklist` table because:

- Native TTL semantics: keys self-expire without a purge job.
- O(1) `EXISTS` check: single-command, ~0.1ms round-trip on localhost or the same Docker network.
- The blocklist is ephemeral state, not business data — a Redis restart or eviction loses blocklist entries, meaning previously-revoked tokens could be accepted again; the `jti_issued` DB table is the durable source of truth and can be used to re-populate Redis on startup.

**Fail-closed on Redis unavailability.** If the Redis connection fails, `DigiAuthMiddleware` returns HTTP 503 (`{"detail":"auth_backend_unavailable"}`). This is consistent with the precedent set in ADR-0005 (guest-tier rate limits), which also fails closed when Redis is down. Availability is sacrificed for security correctness: during a Redis outage, no request can be confirmed unrevoked.

**Fail-open on Redis cache miss (expired key).** A `jti` entry in Redis expires at `exp`. If Redis is available but the entry is absent, the token is treated as not revoked — normal path. Entries that were never written (old tokens issued before this feature ships) also fall through as not revoked.

**Revocation granularity — all JTIs for a key, not one.** The motivating scenario (key leak) requires revoking every JWT exchanged by the leaked key, not just a specific token. On `POST /v1/admin/keys/{id}/revoke`:
1. Set `revoked_at = now()` on the `ApiKeyRow` (existing mechanism, blocks future exchanges).
2. Query `jti_issued` for all rows where `api_key_id = id` and `exp > now()`.
3. Write each `jti:<uuid>` to Redis with the appropriate TTL.

This guarantees every live JWT from the revoked key is blocked within one Redis round-trip per consumer request.

**`jti_issued` table in DigiKey DB.** A new table stores issued JTIs:

| Column | Type | Notes |
|---|---|---|
| `jti` | `VARCHAR(36)` PK | UUID hex from `jwt_issue.py` |
| `api_key_id` | `VARCHAR(36)` FK → `digikey_api_keys.id` | For enumeration on key revoke |
| `exp` | `INT` NOT NULL | Unix timestamp; used to set Redis TTL and filter stale rows |
| `issued_at` | `TIMESTAMPTZ` | Audit trail |

Rows where `exp < now()` are dead and can be purged by a nightly job or a short-TTL Postgres cleanup trigger. Unlike the Redis blocklist, this table is the source of truth for "which JTIs were ever issued for this key" — it needs to survive Redis restarts.

**No change to JWT structure.** `jti` is already present in every token. No client-side changes and no token format bump.

**New environment variable.** `DIGIKEY_BLOCKLIST_REDIS_URL` — standard Redis URL. If unset, DigiKey starts but logs a warning and skips blocklist writes on revoke. `DigiAuthMiddleware` must fail at startup (or fail closed per-request) if blocklist checking is enabled but the URL is unconfigured.

## Consequences

**Positive**

- A revoked key's JWTs stop working within one Redis round-trip, eliminating the up-to-15-minute exposure window.
- Blocklist entries self-expire at `exp` — no unbounded growth, no purge job required for the Redis layer.
- No client-side changes: `jti` is already in the token, JWKS is unchanged, consumers just add one Redis check in the existing middleware.
- Revocation endpoint is admin-gated (`DIGIKEY_ADMIN_TOKEN`), consistent with key creation.

**Negative / tradeoffs**

- **New infrastructure dependency.** Redis is not currently used anywhere in DigiKey. Every deployment (Docker Compose, production) must provision and operate a Redis instance. This is the most significant operational cost of this decision.
- **Per-request latency added to all consumer services.** The zero-network-call verification property (celebrated in `ARCHITECTURE.md` §7) is broken for the revocation check. A Redis `EXISTS` call adds ~0.1ms on the same Docker network, ~1-3ms across availability zones. At high request rates this adds up.
- **Fail-closed availability risk.** A Redis outage blocks all protected requests until Redis recovers. The existing model (DigiKey can be down for minutes) no longer holds for the blocklist path.
- **`jti_issued` table write on every token exchange.** A DB insert at exchange time adds latency to `POST /v1/oauth/token`. bcrypt dominates that path at ~100ms, so the insert is negligible — but it must be accounted for in migration scripts.
- **SQLite single-writer constraint.** If `DIGIKEY_DATABASE_URL` points at SQLite, concurrent inserts to `jti_issued` will contend on the write lock. Postgres is strongly recommended for any deployment using revocation.

## Alternatives considered

1. **Short-lived tokens + refresh flow.** Issue JWTs with TTL of 60 seconds; when a key is revoked, wait up to 60 seconds for exposure to close naturally. Rejected: requires a refresh-token grant (`grant_type=refresh_token`) that does not exist, requires client changes to handle 401 and re-exchange, and every BFF session would need to refresh silently every minute. Issue #6 explicitly requires proactive revocation, not just shorter windows.

2. **Token introspection endpoint (`POST /v1/introspect`, RFC 7662).** Each consumer calls DigiKey on every request to check real-time validity. Rejected: this puts DigiKey on the per-request hot path of all three consumer services, eliminating the "DigiKey can be down for minutes without affecting in-flight requests" property that `ARCHITECTURE.md` identifies as a core design goal. The Redis blocklist achieves real-time revocation without DigiKey being on the critical path.

3. **`jti_blocklist` in Postgres (no Redis).** Add a `jti_blocklist` table to the DigiKey DB; consumers query it on each request via a shared DB connection. Rejected: consumers currently have zero DB dependencies — adding a Postgres connection to DigiGraph, DigiQuant, and DigiSearch just for blocklist checks is a heavier dependency than a Redis client. Postgres connection pools also scale less gracefully under the fan-out pattern (many consumer services × many concurrent requests). Redis with O(1) `EXISTS` is a better fit for read-heavy, single-answer membership checks.

4. **Opaque tokens (replace JWTs entirely).** Issue random bearer tokens; consumers call DigiKey for every verification. Rejected: the JWKS model is already deployed and working. Opaque tokens would require removing `DigiAuthMiddleware`'s local verification and adding a network call for every request — the worst properties of the introspection approach with none of the JWT benefits retained.

5. **No revocation (accept the 15-minute window).** Leave the gap documented and rely on short TTL. Rejected by issue #6. Acceptable for development environments; not acceptable for multi-tenant production deployments.

## Implementation sketch

1. **DigiKey: add `jti_issued` table** (`db_schema.py`). Migration required.
2. **DigiKey: write `jti` row on every token exchange** (`server.py` → `jwt_issue.py`). Fire after bcrypt verify, before returning the token response. SQLAlchemy insert, same session as the key lookup.
3. **DigiKey: add `POST /v1/admin/keys/{id}/revoke` endpoint** (`server.py`). Admin-gated. Sets `revoked_at`, enumerates live `jti_issued` rows, writes to Redis with TTL. Return `{"revoked": true, "jtis_invalidated": N}`.
4. **DigiKey: add Redis client** (`blocklist.py`). Thin wrapper around `redis-py`. Reads `DIGIKEY_BLOCKLIST_REDIS_URL`. Exposes `write_blocklist(jti, ttl_sec)` and `is_blocked(jti) → bool`.
5. **Consumer: update `DigiAuthMiddleware`** (`integrations/service_middleware.py`). After `jwt.decode()`, call `blocklist.is_blocked(claims["jti"])`. Return 401 `{"detail":"token_revoked"}` if blocked. Redis client configured via `DIGIKEY_BLOCKLIST_REDIS_URL` on consumer containers.
6. **Docker Compose: add Redis service** (`docker-compose.yml`). Internal network only, loopback-equivalent. Add `DIGIKEY_BLOCKLIST_REDIS_URL` to DigiKey and all consumer service environment blocks.
7. **Tests:** unit tests for `blocklist.py` (mock Redis), integration test for the revoke endpoint, middleware test asserting blocked `jti` returns 401.

## Links

- Related: issue #6 (this decision)
- Architecture background: `digikey/ARCHITECTURE.md` §6 (security gap), §11 (Phase 2 gaps), §12(a) (recommended approach)
- Precedent for fail-closed Redis: ADR-0005 (guest-tier rate limits)
- Introspection option from: `digikey/ARCHITECTURE.md` §12(c)
