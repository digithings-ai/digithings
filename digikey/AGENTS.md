# Agent Guide: DigiKey

## Purpose

DigiKey is the single authentication and authorization control plane for DigiThings. It manages opaque API keys (bcrypt-hashed, shown once), issues short-lived RS256 JWTs via token exchange, publishes a JWKS endpoint so consumers verify tokens locally, and enforces scope-based access. Every protected route on every service refuses traffic without a valid DigiKey-issued JWT.

---

## Read First

In this order, before writing any code:

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — JWT claims structure, bcrypt storage, scope definitions, token exchange flow, security gaps (JWT revocation), integration guide for consumers
2. [`../AGENTS.md`](../AGENTS.md) — non-negotiable stack-wide rules
3. [`../ROADMAP.md`](../ROADMAP.md) — Redis blocklist revocation is shipped (opt-in); multi-tenant RBAC is Phase 2+
4. [`../SECURITY.md`](../SECURITY.md) — auth gates, scope enforcement, critical security requirements
5. [`../docs/agent-backlog/INDEX.md`](../docs/agent-backlog/INDEX.md) — current task queue

---

## Pre-Flight Checklist

Before making any change to `digikey/`:

- [ ] Read `ARCHITECTURE.md` Section 3 (API Surface) and Section 5 (Security Analysis)
- [ ] Run `pytest tests/ -m unit -k "digikey" -v` — passes before and after
- [ ] Run `ruff check digikey/ && ruff format --check digikey/` — zero errors
- [ ] Confirm raw API key material is **never logged** — only `key_id` and key prefix are safe to log
- [ ] Confirm bcrypt verification path is unchanged — do not swap to a weaker hash
- [ ] Confirm `DIGIKEY_ALLOW_DEV_GLOBAL=1` and `DIGIKEY_ALLOW_EPHEMERAL_KEY=1` are rejected in production (these env vars must not appear in any production Compose or Helm config)
- [ ] Confirm any new endpoint uses `DIGIKEY_ADMIN_TOKEN` bearer or is explicitly public (health, JWKS)
- [ ] Confirm no new scope is added without updating `ARCHITECTURE.md` scope table and notifying consuming services

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **bcrypt only for key storage**: Never store raw keys or use a weaker hash (MD5, SHA-256). The bcrypt column in `ApiKeyRow` is immutable after creation.
- **Raw key shown once**: The plaintext `dgk_live_` key is returned from `POST /v1/admin/keys` and never retrievable again. This is by design — do not add a "show key" endpoint.
- **RS256, not HS256**: JWTs are signed with the RSA private key. Never accept or emit HS256 tokens. The `crypto_keys.py` module enforces the key type.
- **Short-lived JWTs, JWKS caching**: Default JWT TTL should remain short (minutes, not hours). JWKS consumers cache the public key — DigiKey can be down without affecting in-flight request verification.
- **JWT revocation (Redis blocklist)**: When `DIGIKEY_BLOCKLIST_REDIS_URL` is set, `POST /v1/admin/keys/{key_id}/revoke` blocklists live `jti` values until token `exp`. Consumers must call `blocklist.is_blocked(jti)` (via `DigiAuthMiddleware`) for fail-closed revocation. When Redis is unset, revocation only blocks **new** token exchanges (`revoked_at` on the key) — already-issued JWTs remain valid until `exp` (see `ARCHITECTURE.md` Section 5).
- **Scope downscoping only**: Callers requesting a JWT can only request a **subset** of their granted scopes. `scopes.py` enforces this. Never issue a JWT with scopes beyond what the key was granted.
- **`DIGIKEY_ALLOW_DEV_GLOBAL=1` is dev-only**: `dev_global` keys (`scopes=["*"]`) must never be created in production. The guard in `server.py` must not be weakened.
- **Admin token is a secret**: `DIGIKEY_ADMIN_TOKEN` is bearer auth for `POST /v1/admin/keys`. It must never appear in logs, responses, or span attributes.

---

## Test Commands

```bash
# Unit tests (no stack required)
pytest tests/ -m unit -k "digikey" -v

# Single test file
pytest tests/digikey/test_jwt.py -v

# Full unit suite
make test-unit

# Lint
ruff check digikey/ && ruff format --check digikey/

# Stack smoke test (requires make up)
curl -s http://localhost:8005/health
curl -s http://localhost:8005/.well-known/jwks.json

# Issue a test JWT (requires DIGIKEY_ADMIN_TOKEN and a valid API key)
digikey issue-key --tenant dev --name test-key --scopes "digigraph:workflow digisearch:query"
```

---


---

## More

Extension patterns, anti-patterns, and integration boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc when changing interfaces or behavior.
