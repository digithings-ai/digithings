# DigiKey Architecture

**Version:** 0.1.0
**Service port:** 8005
**Source root:** `digikey/src/digikey/`

---

## 1. Overview

DigiKey is the single authentication and authorization control plane for the DigiThings ecosystem. Every protected route on every other service — DigiGraph, DigiQuant, DigiSearch — refuses traffic unless the caller presents a short-lived JWT signed by DigiKey. No service issues its own tokens. No service trusts tokens from any other issuer. This is the zero-trust boundary.

The service has two responsibilities:

1. **Opaque API key management.** External callers hold a `dgk_live_` prefixed secret. DigiKey stores only a bcrypt hash. The raw secret is shown once on creation and never retrievable again.

2. **JWT issuance via token exchange.** A caller presents their opaque API key (or a BFF session credential) to `POST /v1/oauth/token`. DigiKey verifies the key, checks revocation, and returns a short-lived RS256 JWT that carries the caller's scopes, tenant context, and identity. Downstream services verify this JWT locally against the published JWKS — they never call DigiKey per-request.

This architecture means DigiKey sits on the hot path for key exchange but is completely off the hot path for request verification. A JWKS cache in each consumer service means DigiKey can be down for minutes without affecting in-flight requests.

---

## 2. Current Implementation State

### Implemented in v0.1

**JWT issuance (RS256, JWKS)**
- `crypto_keys.py`: loads or generates a 2048-bit RSA key pair on startup. Key material source is controlled by `DIGIKEY_PRIVATE_KEY_PEM` (preferred) or `DIGIKEY_ALLOW_EPHEMERAL_KEY=1` (development only; JWKS rotates on restart).
- `jwt_issue.py`: signs JWTs with PyJWT using `RS256`, embeds `kid` in the header, returns `(token_str, jti)`.
- `server.py` (`GET /.well-known/jwks.json`): serves the public key as a JWKS document via `public_jwks()`.

**API key types**
- `standard`: service-to-service or machine keys. Prefix `dgk_live_`. Scopes are explicitly assigned at creation time.
- `dev_global`: wildcard-scope keys (`scopes=["*"]`). Requires `DIGIKEY_ALLOW_DEV_GLOBAL=1`. Intended for local development only.
- Both kinds are stored with the same bcrypt-hashed schema.

**Token exchange (`POST /v1/oauth/token`)**
- `grant_type=api_key`: caller presents raw key; DigiKey looks up by prefix, runs bcrypt verification, checks `revoked_at`, emits JWT.
- `grant_type=bff_session`: DigiChat's BFF presents `Authorization: Bearer DIGIKEY_BFF_TOKEN`. DigiKey issues a JWT with `principal_kind=bff_session` and `sub=bff:<subject>`.

**Admin key issuance (`POST /v1/admin/keys`)**
- Protected by `DIGIKEY_ADMIN_TOKEN` bearer. Creates a new `ApiKeyRow`, returns the plaintext key once.

**Scope enforcement**
- `scopes.py`: wildcard matching. `*` grants everything. `service:*` grants all sub-scopes for that service. Exact string match for leaf scopes. Scope downscoping: callers can request a subset of their granted scopes by passing `requested_scopes`; DigiKey verifies the subset is within the granted set before issuing.

**Source file map**

| File | Responsibility |
|------|---------------|
| `server.py` | FastAPI app, all HTTP routes, startup hook |
| `jwt_issue.py` | JWT construction, JWKS document |
| `jwt_verify.py` | JWT decode + JWKS client (used by consumers) |
| `crypto_keys.py` | RSA key load/generate, PEM serialization |
| `key_crypto.py` | API key generation (`secrets`), bcrypt hash/verify |
| `db.py` | SQLAlchemy engine and session factory |
| `db_schema.py` | `ApiKeyRow` ORM model, `digikey_api_keys` table |
| `scopes.py` | Scope matching logic, `DEFAULT_BFF_SESSION_SCOPES` |
| `settings.py` | Env-driven constants (`KEY_PREFIX_LEN=16`, `RAW_KEY_PREFIX="dgk_live_"`) |
| `models.py` | `TokenClaims`, `DigiAuthContext`, `PrincipalKind` Pydantic v2 models |
| `integrations/service_middleware.py` | `DigiAuthMiddleware`, per-service path-scope tables |
| `ratelimit.py` | In-process per-IP token-bucket limiter + FastAPI dependency for auth-path routes |
| `cli.py` | Bootstrap CLI (`digikey issue-key`) |

---

## 3. API Surface

### DigiKey-owned endpoints

**`GET /health`** and **`GET /healthz`**
`/health` returns `{"status": "ok", "service": "digikey"}` (legacy, kept for back-compat). `/healthz` returns `{"ok": true}` — the preferred liveness probe. Both are always public, rate-limit-exempt, and secret-free. Docker healthcheck targets `/healthz`. See AGENTS.md "Liveness vs status".

**`GET /.well-known/jwks.json`**
Public. Returns the RSA public key as a JWKS document. Consumers cache this with a TTL (default 300 seconds, configurable via `DIGIKEY_JWKS_CACHE_SEC`). No authentication required — the public key is safe to expose.

**`POST /v1/oauth/token`**
Body: `TokenRequest` (Pydantic v2). Supported `grant_type` values: `api_key`, `bff_session`.

Response shape:
```json
{
  "access_token": "<RS256 JWT>",
  "token_type": "Bearer",
  "expires_in": 900,
  "litellm_proxy_api_key": "<optional>"
}
```
`litellm_proxy_api_key` is present only when `DIGIKEY_LITELLM_PROXY_KEY` is set.

**`POST /v1/admin/keys`**
Requires `Authorization: Bearer <DIGIKEY_ADMIN_TOKEN>`. Body: `AdminIssueBody`. Returns `AdminIssueResponse` with the plaintext key (shown once). If `DIGIKEY_ADMIN_TOKEN` is unset, returns 503 — no anonymous key creation.

### DigiAuthMiddleware (shared across services)

`digikey.integrations.service_middleware.DigiAuthMiddleware` is a Starlette `BaseHTTPMiddleware` shipped as part of the `digikey` package. All three consumer services register it at app startup:

```python
# digigraph/src/digigraph/server.py
app.add_middleware(DigiAuthMiddleware, service="digigraph", path_scopes=digigraph_path_scopes)

# digiquant/src/digiquant/server.py
app.add_middleware(DigiAuthMiddleware, service="digiquant", path_scopes=digiquant_path_scopes)

# digisearch/src/digisearch/server.py
app.add_middleware(DigiAuthMiddleware, service="digisearch", path_scopes=digisearch_path_scopes)
```

Middleware behaviour on each request:
1. OPTIONS requests bypass auth (CORS preflight).
2. `path_scopes(method, path)` returns `None` (exempt) or a list of required scopes.
3. If required is `None` (e.g., `/health`, `/docs`): pass through.
4. If `DIGIKEY_JWKS_URL` and `DIGIKEY_PUBLIC_KEY_PEM` are both unset: return 503 `auth_not_configured`. No silent fallback to anonymous access.
5. Extract `Authorization: Bearer <token>`. If missing: 401.
6. Decode and verify JWT via `jwt_verify.decode_token`. If invalid/expired: 401.
7. Check `scope_grants_required`. If insufficient: 403 `insufficient_scope`.
8. Attach `DigiAuthContext` to `request.state.digi_auth`. Downstream handlers read tenant, scopes, and project context from there.

---

## 4. Data Model

### JWT claims

All tokens issued by DigiKey include these claims:

| Claim | Type | Notes |
|-------|------|-------|
| `sub` | string | `key:<row_id>` for api_key grants; `bff:<subject>` for bff_session |
| `iss` | string | `DIGIKEY_ISSUER` (default `http://127.0.0.1:8005`) |
| `aud` | string | `DIGIKEY_AUDIENCE` (default `digi-ecosystem`) |
| `iat` | int | Unix timestamp, issued-at |
| `exp` | int | Unix timestamp, expiry (`iat + DIGIKEY_JWT_TTL_SEC`, default 900s) |
| `jti` | string | UUID hex, unique token ID — present but not indexed for revocation |
| `tenant_slug` | string | Tenant identifier from key row or bff request |
| `scopes` | list[str] | Granted scopes list |
| `scope` | string | Space-separated scopes (OAuth 2.0 interop) |
| `principal_kind` | string | `api_key` / `bff_session` / `legacy_static` |
| `legacy_static` | bool | Always `false` for new tokens |
| `key_pub` | string? | Key prefix (first 16 chars), api_key grants only |
| `project_id` | string? | Optional project scoping |
| `project_config_ref` | string? | Optional project config reference |
| `tenant_id` | string? | Optional tenant UUID (not currently populated by server) |

### API key storage (`digikey_api_keys` table)

| Column | Type | Notes |
|--------|------|-------|
| `id` | `VARCHAR(36)` PK | UUID v4 |
| `key_hash` | `TEXT` NOT NULL | bcrypt hash of full raw key |
| `key_prefix` | `VARCHAR(64)` UNIQUE INDEX | First 16 characters of raw key, used for DB lookup |
| `tenant_slug` | `VARCHAR(256)` INDEX | Tenant identifier |
| `project_id` | `VARCHAR(512)` nullable | |
| `project_config_ref` | `TEXT` nullable | |
| `scopes` | `JSONB` / `JSON` | List of scope strings |
| `kind` | `VARCHAR(32)` | `standard` or `dev_global` |
| `label` | `VARCHAR(256)` nullable | Human-readable description |
| `created_at` | `TIMESTAMPTZ` | Server-generated |
| `revoked_at` | `TIMESTAMPTZ` nullable | Set to revoke; checked on every exchange |

Column type note: `scopes` uses `JSONB` on Postgres and `JSON` on SQLite via SQLAlchemy dialect variants (`db_schema.py:_json_type()`).

### Scope definitions

Scopes follow a `service:action` namespace. Defined (implicitly) in `scopes.py` and `service_middleware.py`:

| Scope | Service | Grants access to |
|-------|---------|-----------------|
| `digigraph:workflow` | DigiGraph | `POST /workflow`, debug endpoints, default fallback |
| `digigraph:chat` | DigiGraph | `/v1/chat/completions`, `/v1/models` |
| `digigraph:mcp` | DigiGraph | `/threads/*`, `/files/*` |
| `digiquant:backtest` | DigiQuant | `/run_backtest`, `/backtest/*`, `/v1/jobs/*`, `/v1/orchestrator_tools` |
| `digiquant:optimize` | DigiQuant | `/run_optimize`, `/run_pipeline`, `/v1/workflow` |
| `digisearch:query` | DigiSearch | `/query`, `/v1/research_turn`, `/v1/orchestrator_tools`, `/indexes/*` |
| `digisearch:ingest` | DigiSearch | `/ingest*` |
| `*` | all | Wildcard — all scopes |

Default BFF session scopes (from `scopes.py`): `digigraph:workflow`, `digigraph:chat`, `digigraph:mcp`, `digiquant:backtest`, `digiquant:optimize`, `digisearch:query`, `digisearch:ingest`.

### LiteLLM proxy key funnel

When `DIGIKEY_LITELLM_PROXY_KEY` is set on the DigiKey container, `POST /v1/oauth/token` appends `litellm_proxy_api_key` to the response. This key (typically equal to `LITELLM_MASTER_KEY`) is forwarded by DigiChat as `X-LiteLLM-Proxy-Key` to DigiGraph, enabling one token exchange to bootstrap both service JWT auth and LiteLLM bearer auth. The LiteLLM key is a static pass-through — DigiKey does not scope or validate it.

---

## 5. Internal Architecture

### Token exchange flow

```
Client                   DigiKey                     DB
  |                         |                          |
  | POST /v1/oauth/token    |                          |
  | {grant_type: api_key,   |                          |
  |  api_key: "dgk_live_…"} |                          |
  |------------------------>|                          |
  |                         | SELECT WHERE             |
  |                         | key_prefix = raw[:16]    |
  |                         |------------------------->|
  |                         |<-- [ApiKeyRow(s)]        |
  |                         |                          |
  |                         | bcrypt.checkpw(raw, hash)|
  |                         | check revoked_at is None |
  |                         | check dev_global allowed |
  |                         | apply scope downscoping  |
  |                         | issue_access_token()     |
  |                         |  → RS256 JWT + jti       |
  |<------------------------|                          |
  | {access_token, expires} |                          |
```

### Consumer JWT verification (no DigiKey call)

```
Client                 DigiAuthMiddleware              JWKS Cache
  |                         |                              |
  | GET /workflow            |                              |
  | Authorization: Bearer <JWT>                            |
  |------------------------>|                              |
  |                         | path_scopes("GET","/workflow")|
  |                         | → ["digigraph:workflow"]     |
  |                         |                              |
  |                         | PyJWKClient.get_signing_key  |
  |                         |----------------------------->|
  |                         |<-- RSAPublicKey (cached 300s)|
  |                         |                              |
  |                         | jwt.decode(RS256, aud, iss)  |
  |                         | scope_grants_required()      |
  |                         | → attach request.state       |
  |<-- 200 OK               |                              |
```

### JWKS rotation

The signing key is loaded once at process startup in `server.py` at module level:

```python
_private_key, _kid = load_or_create_signing_key()
```

`kid` comes from `DIGIKEY_KEY_ID` (default `"digikey-1"`). There is no in-process rotation. Key rotation requires a new deployment. Consumers cache the JWKS for up to `DIGIKEY_JWKS_CACHE_SEC` seconds (default 300). During a key rotation, tokens signed by the old key will fail verification once the cache expires and the consumer fetches the new JWKS. There is no overlap/grace period implemented.

### SQLAlchemy DB schema

Single table: `digikey_api_keys`. Engine is initialized lazily at first use via `db.py`. SQLite uses `check_same_thread=False` to allow access from FastAPI's async thread pool. Postgres uses the default pool. `pool_pre_ping=True` reconnects stale connections.

### Scope matching (wildcards)

`scopes.py:scope_grants_required(granted, required)` implements three-level matching:
1. If any granted scope is `"*"`: grant everything.
2. Exact string match: `"digisearch:query"` satisfies `"digisearch:query"`.
3. Prefix wildcard: granted `"digisearch:*"` satisfies any `"digisearch:X"`.
4. Reverse wildcard: required `"digisearch:*"` is satisfied if the caller has any specific `"digisearch:X"` scope.

---

## 6. Security Analysis

### RS256 signing

DigiKey uses asymmetric RS256 (RSA 2048-bit). The private key never leaves the DigiKey container. Consumer services hold only the public key or a JWKS URL. This is correct for a multi-service ecosystem: compromise of a consumer service does not expose signing capability.

**Gap:** The default `kid` is the static string `"digikey-1"`. Without a meaningful `kid` rotation scheme, JWKS consumers cannot distinguish keys across rotations.

### bcrypt key storage

Raw API keys are never stored. Only bcrypt hashes are persisted in the `key_hash` column. Key lookup is a two-step process: fetch by `key_prefix` (plaintext, indexed), then bcrypt verify the matching rows. This is correct. The prefix is not a secret — it only narrows the bcrypt candidates from the full table.

**Gap:** bcrypt work factor is not set explicitly. `bcrypt.gensalt()` defaults to cost factor 12. This is reasonable but should be documented and potentially tunable for high-throughput environments.

### JWT revocation (Redis blocklist — ADR-0007)

When `DIGIKEY_BLOCKLIST_REDIS_URL` is set (wired in root `docker-compose.yml`), DigiKey:

1. Persists issued `jti` values in Postgres (`jti_issued`) at token exchange time.
2. On `POST /v1/revoke`, marks the API key revoked and adds live JTIs to the Redis blocklist.
3. Consumer `DigiAuthMiddleware` calls `blocklist.is_blocked(jti)` — **fail-closed** when Redis is configured but unreachable.

When Redis is **unset**, blocklist checks are skipped (legacy dev mode). Production stacks must set `DIGIKEY_BLOCKLIST_REDIS_URL`.

### Historical gap (pre–Wave 1 remediation)

Prior to ADR-0007 implementation, `jti` was included in tokens but not indexed for revocation. See git history for the fail-closed middleware and compose wiring landed in audit Wave 1.

### `dev_global` keys risk

Keys with `kind=dev_global` carry `scopes=["*"]` — full access to all services. They are gated behind `DIGIKEY_ALLOW_DEV_GLOBAL=1`, which must never be set in production. No additional runtime enforcement prevents `DIGIKEY_ALLOW_DEV_GLOBAL=1` from being set in a production deployment. In the Docker Compose file, it defaults to `0`, which is correct.

### Admin token rotation risk

`DIGIKEY_ADMIN_TOKEN` is a static bearer secret with no expiry. Leaking this token grants unlimited key creation ability. There is no per-request rate limit or audit trail on `POST /v1/admin/keys` beyond what the standard FastAPI error handler provides.

### SQLite single-writer bottleneck

The default `DIGIKEY_DATABASE_URL` is `sqlite:////data/digikey.db`. SQLite has a global write lock. Under concurrent load, key creation and token exchange (which reads the DB) will serialize. For production deployments with any significant token exchange rate, Postgres is required.

Additionally, SQLite's `check_same_thread=False` allows cross-thread access but does not address the write lock. FastAPI runs handlers in a thread pool. Under load, this will cause lock contention.

### JWKS caching staleness in consumers

`jwt_verify.py` maintains a module-level `PyJWKClient` singleton with `lifespan=300` (default). After a DigiKey restart with an ephemeral key (or a deliberate key rotation), consumers continue accepting old-key tokens for up to 5 minutes. This is a feature (resilience) but also a security window: rotated-out keys remain trusted by consumers for 300 seconds.

### Constant-time comparison

`_require_admin` and `bff_session` bearer validation use `secrets.compare_digest`, which prevents timing attacks on token comparison. This is correct.

---

## 7. Scalability Analysis

### Single DB dependency

All state (API keys, revocation via `revoked_at`) lives in one database. DigiKey itself is stateless between requests — the private key is loaded in memory. Horizontal scaling of DigiKey is straightforward as long as all instances share the same Postgres database and the same `DIGIKEY_PRIVATE_KEY_PEM` (or coordinate JWKS via a shared volume/secret store).

SQLite cannot support multi-instance DigiKey. Postgres is required for any horizontal scaling.

### No revocation table bottleneck (current tradeoff)

Because there is no `jti` blocklist, token validation in consumers is purely local (cryptographic). There is no per-request DB call in any consumer service. This is excellent for throughput but comes at the cost of the revocation gap documented in Section 6.

### JWKS caching

Consumers cache the JWKS for 300 seconds by default. DigiKey's `/.well-known/jwks.json` endpoint is read-only and stateless — it can handle high fan-out traffic without DB involvement. The endpoint's bottleneck is CPU (RSA key serialization), not I/O.

### Token exchange rate

`POST /v1/oauth/token` for `grant_type=api_key` involves:
1. One indexed DB read (`SELECT WHERE key_prefix = ?`).
2. One bcrypt verify (CPU-bound, ~100ms at cost factor 12).
3. One RSA sign (CPU-bound, ~1ms for 2048-bit).

At high exchange rates, bcrypt is the bottleneck. DigiKey does not cache exchange results. If the same API key exchanges tokens in a tight loop, each exchange runs a full bcrypt verify. There is no negative effect on correctness, but throughput is bounded by bcrypt latency times available threads.

### Multi-instance considerations

Each DigiKey instance generates its own ephemeral key when `DIGIKEY_ALLOW_EPHEMERAL_KEY=1`. Multiple instances would publish different JWKS documents, causing cross-instance token verification failures. In any multi-instance deployment, `DIGIKEY_PRIVATE_KEY_PEM` must be identical across instances (e.g., injected from a shared secret store).

---

## 8. Performance Analysis

### bcrypt cost factor

`bcrypt.gensalt()` defaults to cost factor 12 (~100-150ms per verification on modern hardware). With FastAPI's default thread pool of `min(32, os.cpu_count() + 4)` threads, the maximum sustained key exchange throughput is approximately:

```
throughput ≈ thread_count / bcrypt_latency_sec
```

For a 4-core host: ~8 threads / 0.1s = ~80 exchanges/second maximum. This is sufficient for most deployments but worth monitoring under high load. Cost factor is not configurable without a code change.

### RS256 JWT verification vs HMAC

RS256 signature verification in consumers is slower than HMAC-SHA256 by roughly 3-5x. For typical request rates (hundreds/second per service), this is not a bottleneck. The JWKS cache ensures the public key is not re-fetched per request.

### JWKS caching TTL in DigiAuthMiddleware

`PyJWKClient` with `lifespan=300` caches signing keys in memory within the consumer process. Cache miss (first request after startup or after TTL expiry) triggers an HTTP request to `DIGIKEY_JWKS_URL`. If DigiKey is unreachable at that moment, the cache miss becomes a hard 401/503 for that request. There is no stale-while-revalidate behavior.

### Connection pool for Postgres

`db.py` uses `create_engine` with defaults (5 connections, 10 overflow). For production Postgres deployments under significant exchange load, pool sizing should be tuned via `DIGIKEY_DATABASE_URL` pool parameters or explicit engine kwargs. The current code does not expose pool sizing via environment variables.

---

## 9. Integration Points

### Consumer services

All three protected services import from the `digikey` package directly:

```
DigiGraph   → digikey.integrations.service_middleware.{DigiAuthMiddleware, digigraph_path_scopes}
DigiQuant   → digikey.integrations.service_middleware.{DigiAuthMiddleware, digiquant_path_scopes}
DigiSearch  → digikey.integrations.service_middleware.{DigiAuthMiddleware, digisearch_path_scopes}
```

This means the `digikey` package is a compile-time dependency of every service, not just a runtime network dependency. Path-scope tables live in the `digikey` package itself (`service_middleware.py`), not in each service. A scope change requires updating `digikey` and rebuilding all three consumer images.

### DigiChat (BFF)

DigiChat holds `DIGIKEY_URL` and `DIGIKEY_BFF_TOKEN`. On session establishment (user login via OIDC or API key auth), DigiChat calls `POST /v1/oauth/token` with `grant_type=bff_session`. The returned JWT is forwarded as `Authorization: Bearer` to DigiGraph on all upstream calls. `litellm_proxy_api_key` is forwarded as `X-LiteLLM-Proxy-Key`.

The static fallback `DIGIGRAPH_UPSTREAM_API_KEY` bypasses DigiKey entirely. It is documented as emergency/bootstrap only.

### LiteLLM proxy key funnel

DigiKey is not a LiteLLM auth provider. It acts only as a distribution mechanism: the value of `DIGIKEY_LITELLM_PROXY_KEY` (a pre-configured LiteLLM master key) is included verbatim in the token response. DigiKey does not create, validate, or scope LiteLLM keys. If `DIGIKEY_LITELLM_PROXY_KEY` is rotated, all currently-held JWTs contain the old LiteLLM key until they expire.

### Audit trail

JWT claims include `jti`, `tenant_slug`, `project_id`, `key_pub`, and `principal_kind`. Consumer services are expected to include these in audit events (as documented in root `SECURITY.md`). DigiKey itself does not emit audit events on token exchange. There is no `AUDIT_SINK_URL` integration yet.

---

## 10. Docker and Composition

### Service definition

```yaml
# docker-compose.yml (excerpt)
digikey:
  build: { context: ., dockerfile: digikey/Dockerfile }
  ports: ["127.0.0.1:8005:8005"]          # loopback-only
  volumes: [digikey_data:/data]            # SQLite persistence
  healthcheck:
    test: ["CMD", "curl", "-sf", "http://127.0.0.1:8005/health"]
    interval: 15s
    timeout: 5s
    retries: 3
    start_period: 10s
```

DigiKey has no `depends_on` — it starts first. All other services declare `condition: service_healthy` on `digikey`. The full startup order is:

```
digikey (healthy) → digiquant (healthy) → digisearch (healthy) → litellm (healthy) → digigraph (healthy)
```

DigiChat depends on `digikey` and `digigraph` being healthy.

### Environment variables

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `DIGIKEY_DATABASE_URL` | — | Yes | Postgres or SQLite URL |
| `DIGIKEY_PRIVATE_KEY_PEM` | — | Prod: Yes | PEM private key for RS256 signing |
| `DIGIKEY_ALLOW_EPHEMERAL_KEY` | `0` (compose: `1`) | Dev only | Generate ephemeral key if PEM not set |
| `DIGIKEY_KEY_ID` | `digikey-1` | No | `kid` in JWKS and JWT header |
| `DIGIKEY_ISSUER` | `http://127.0.0.1:8005` | Yes (match consumers) | JWT `iss` claim |
| `DIGIKEY_AUDIENCE` | `digi-ecosystem` | No | JWT `aud` claim |
| `DIGIKEY_ADMIN_TOKEN` | — | Yes for key creation | Bearer for `POST /v1/admin/keys` |
| `DIGIKEY_BFF_TOKEN` | — | Yes for DigiChat | Bearer for `bff_session` grants |
| `DIGIKEY_ALLOW_DEV_GLOBAL` | `0` | No (never in prod) | Enable `dev_global` key issuance/exchange |
| `DIGIKEY_JWT_TTL_SEC` | `900` | No | JWT lifetime in seconds |
| `DIGIKEY_LITELLM_PROXY_KEY` | — | No | Forwarded as `litellm_proxy_api_key` |
| `DIGIKEY_JWKS_CACHE_SEC` | `300` | No | Consumer-side JWKS cache TTL |
| `DIGIKEY_RL_PER_MIN` | `10` | No | Auth-path rate limit: sustained req/min per IP |
| `DIGIKEY_RL_BURST` | `20` | No | Auth-path rate limit: burst capacity per IP |

Consumer-side variables (set on DigiGraph/DigiQuant/DigiSearch):

| Variable | Purpose |
|----------|---------|
| `DIGIKEY_JWKS_URL` | Fetch signing keys (preferred) |
| `DIGIKEY_PUBLIC_KEY_PEM` | Static public key alternative |
| `DIGIKEY_ISSUER` | Must match DigiKey's configured issuer |
| `DIGIKEY_AUDIENCE` | Must match DigiKey's configured audience |

### Volume and key persistence

The named volume `digikey_data` is mounted at `/data` inside the container. SQLite writes to `/data/digikey.db`. The private key is not persisted to this volume — it is set via `DIGIKEY_PRIVATE_KEY_PEM` env var (from `.env` or secret store). If using ephemeral keys, a container restart invalidates all previously issued tokens once consumer JWKS caches expire.

### MCP server

DigiKey does not expose an MCP server. It is infrastructure, not a capability provider. There is no `POST /v1/orchestrator_tools` endpoint.

---

## 11. Phase 2+ Gaps and Roadmap

The following capabilities are absent from v0.1. Each represents a production readiness gap or an identified roadmap item from `ARCHITECTURE.md`.

**JWT revocation via `jti` blocklist**
The `jti` field is generated and included in tokens but never written anywhere queryable at verification time. A `jti_blocklist` table (or Redis SET) would allow consumers to reject specific tokens before their natural expiry. Requires all consumers to check the blocklist on every request — a network round-trip per request.

**Vault/KMS-backed signing keys**
Private key material is currently a PEM string in an environment variable. This is acceptable for low-risk deployments but fails compliance requirements (SOC 2, PCI DSS) that mandate HSM-backed keys and key usage audit trails. HashiCorp Vault Transit or AWS KMS would provide signing without exposing private key material.

**OPA policy engine**
Scope definitions are hardcoded in `service_middleware.py`. An OPA integration would externalize policy (scope-to-path mappings) into versioned policy files, enabling policy changes without code deployments or service restarts.

**Usage aggregation from `AUDIT_SINK_URL`**
DigiKey does not emit events on token exchange. An `AUDIT_SINK_URL` integration would let operators track per-tenant, per-key token exchange volume for billing, anomaly detection, and compliance reporting.

**Org-level scope policies**
Current scopes are per-key. There is no concept of an organization-level policy that caps what any key under a tenant can grant. A `TenantPolicy` table could enforce upper bounds on scope grants independent of individual key configuration.

**Refresh token support**
The `grant_type` field accepts `api_key` and `bff_session` only. There is no refresh token mechanism. Clients must re-exchange their API key every 15 minutes (default TTL). A `refresh_token` grant would allow silent re-issuance without re-presenting the API key secret.

**Rate limiting on token endpoint** — *partially closed in v0.1.1.*
A per-IP in-process token-bucket limiter (see `ratelimit.py`) is now applied as a FastAPI dependency on `POST /v1/oauth/token` and `POST /v1/admin/keys`. Defaults: 10 req/min sustained, burst 20 — configurable via `DIGIKEY_RL_PER_MIN` / `DIGIKEY_RL_BURST`. Exempt routes (`/health`, `/.well-known/jwks.json`) carry no limiter overhead. The bucket is process-local; cross-process sharing (Redis or a DigiBase-backed store) is the remaining follow-up for multi-instance deployments, and per-API-key-prefix limiting is still a gap. Responses on breach: HTTP 429 with `{"detail":"rate_limited","retry_after":N}` and a `Retry-After` header.

---

## 12. Redesign Recommendations

These are ordered by severity of current risk.

### (a) Implement `jti` blocklist immediately

The absence of token revocation is the most critical security gap. A stolen API key that has been used to exchange a JWT remains valid until that JWT expires — `revoked_at` only blocks future exchanges.

Recommended approach: add a `jti_blocklist` table (`jti TEXT PRIMARY KEY, revoked_at TIMESTAMPTZ, exp INT`). On key revocation (a new endpoint `POST /v1/admin/keys/{id}/revoke`), insert all live JTIs for that key (requires JTI persistence — see below). Consumer `DigiAuthMiddleware` checks the blocklist on every request. With Redis, this is a single `SISMEMBER` call (~0.1ms). With Postgres, a single indexed SELECT.

This requires storing issued JTIs at exchange time — a `jti_issued` table or a short-lived Redis SET keyed by `jti`. JTI storage does not need to outlive `exp`.

### (b) Add key rotation ceremony with JWKS key ID overlap

A new DigiKey key pair deployment currently invalidates all in-flight tokens as soon as consumer JWKS caches expire (up to 300 seconds after deployment). Tokens signed with the old key are rejected.

Recommended approach: support multiple keys in the JWKS document. On rotation, publish `{"keys": [new_key, old_key]}` for at least one full cache TTL (300 seconds). Consumers select the correct key by `kid`. After the overlap period, remove the old key from JWKS. This requires:
- `DIGIKEY_KEY_ID` to be rotated (new value) per deployment.
- DigiKey to optionally load a secondary PEM (`DIGIKEY_PREV_KEY_PEM`, `DIGIKEY_PREV_KEY_ID`) and include it in the JWKS response.

### (c) Add token introspection endpoint

Services that need real-time validity checks (e.g., after key revocation) cannot use local JWT verification — they need to call DigiKey. Add `POST /v1/introspect` following RFC 7662:

```json
{ "token": "<JWT>" }
→ { "active": true, "sub": "key:...", "scopes": [...], "exp": ... }
```

This endpoint checks both cryptographic validity and `jti_blocklist` membership. It is optional — services can use local verification for performance and fall back to introspection only when they require real-time revocation guarantees.

### (d) Version and externalize scope definitions

`service_middleware.py` embeds path-scope mappings for all three services. This creates a coupling: adding a new DigiSearch endpoint requires updating `digikey`, rebuilding `digikey`, and redeploying all consumers that inherit the package.

Recommended: move path-scope tables into each service's own configuration (loaded at startup), with DigiKey responsible only for scope validation at exchange time. The middleware's `PathScopeFn` signature already supports this — it just needs to be wired to a config file rather than hardcoded functions.

### (e) Add rate limiting on `POST /v1/oauth/token`

Brute-force guessing of the non-prefix portion of an API key (32 random URL-safe base64 chars) is computationally infeasible, but repeated bcrypt calls from a single source waste CPU. Add per-IP or per-prefix rate limiting. A simple in-process leaky bucket (or Redis with `INCR`/`EXPIRE`) on `(client_ip, key_prefix)` tuples would prevent abuse. Return 429 after the threshold is exceeded.

### (f) Vault integration for HSM-backed signing

For production environments subject to audit or compliance requirements, the private key must not exist as a plaintext environment variable. Integrate with HashiCorp Vault Transit:

- `jwt_issue.py` calls `POST /transit/sign/digikey` instead of `jwt.encode` with local key.
- Vault Transit returns the RS256 signature; DigiKey assembles the JWT.
- JWKS is constructed from Vault Transit's public key endpoint.
- Key rotation is managed by Vault, not DigiKey deployment cycles.

Until this is implemented, at minimum rotate `DIGIKEY_PRIVATE_KEY_PEM` on a regular schedule (monthly) and store it in a secrets manager (AWS Secrets Manager, 1Password Secrets Automation) rather than in `.env` files on disk.

## Observability

This service exposes a Prometheus `/metrics` endpoint (counter, histogram, in-flight gauge for every HTTP route) via `digibase.metrics.install_metrics`; scraped by the `observability` compose profile per [ADR-0003](../docs/adr/0003-observability-baseline.md).

## CORS

CORS is installed via the shared `digibase.cors.install_cors(app, service="digikey")` helper; allowlist precedence is `DIGIKEY_CORS_ORIGINS` → `DIGI_CORS_ORIGINS` → legacy `DIGI_ALLOWED_ORIGINS`, defaulting to empty. See `SECURITY.md` §"CORS policy".

## Input Validation Posture

All HTTP request bodies are typed with Pydantic v2 models using `ConfigDict(extra="forbid")`, which rejects unknown fields with HTTP 422 at the framework boundary. Shared validation-error shape lives in `digibase.errors`.
