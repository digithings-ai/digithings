---
type: api-operations-guide
title: digikey API and Operations
description: digikey HTTP surface and operations — health, JWKS, admin key issuance, token exchange, revocation, rate limiting, and env vars.
tags: [digikey, api, auth, operations]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-9219d171d061bc6f0f3c0bae
    resource: repo://digikey/src/digikey/ratelimit.py
  - id: openwiki-source-409717f2c30d896df6ac16b7
    resource: repo://digikey/src/digikey/server.py
  - id: openwiki-source-ff9d5c900be2d38b925af32e
    resource: repo://digikey/src/digikey/settings.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digikey API and Operations

digikey (port 8005) exposes a small, sharply-permissioned surface: public
liveness and JWKS, admin-gated key management, and the token-exchange
endpoint that mints every JWT in the ecosystem. **Human gate:** auth,
JWT, and crypto changes always require human review — this page describes
the surface, not a license to modify it.

## Endpoints

- `GET /health` / `GET /healthz` — legacy and preferred liveness
  (`{"ok": true}`), auth-exempt and rate-limit-exempt.
- `GET /.well-known/jwks.json` — RS256 public key set consumers cache
  for local verification. Public by design.
- `POST /v1/admin/keys` — issue an API key; requires
  `Authorization: Bearer DIGIKEY_ADMIN_TOKEN`, returns the plaintext
  `dgk_live_…` key **once**. Unset admin token → `503`.
- `POST /v1/oauth/token` — exchange (`api_key` or `bff_session` grant)
  for a short-lived JWT. `dev_global` (`scopes=["*"]`) creation refuses
  with 403 unless `DIGIKEY_ALLOW_DEV_GLOBAL=1`.
- `POST /v1/admin/keys/{key_id}/revoke` — revoke a key and blocklist its
  live JTIs (ADR-0007, Redis-backed when configured).

## Rate limiting

Auth-path routes sit behind an in-process per-IP token-bucket limiter
(`ratelimit.TokenBucketRateLimiter`, env-tunable per-min/burst) as a
FastAPI dependency — brute-force exchange attempts throttle per client IP.

## Environment

| Variable | Purpose |
|----------|---------|
| `DIGIKEY_PRIVATE_KEY_PEM` | Preferred RSA signing key material |
| `DIGIKEY_ALLOW_EPHEMERAL_KEY=1` | Dev-only: generate a keypair at startup (JWKS rotates on restart) |
| `DIGIKEY_ADMIN_TOKEN` | Bearer for key issuance/revocation; unset → 503 |
| `DIGIKEY_BFF_TOKEN` | Credential digichat's BFF presents for `bff_session` grants |
| `DIGIKEY_ALLOW_DEV_GLOBAL=1` | Dev-only wildcard keys; never in production |
| `DIGIKEY_BLOCKLIST_REDIS_URL` | Opt-in Redis JTI blocklist for fail-closed revocation |
| `DIGIKEY_DATABASE_URL` | Key store (SQLite dev, Postgres prod) |

Startup warns when the admin token is unset and refuses ephemeral keys
unless explicitly allowed. Raw key material is never logged — only
`key_id` and prefix.

## Container

Loopback-bound `:8005` with a `/healthz` healthcheck; the CLI
(`digikey issue-key`) bootstraps the first key. Standard digibase
middleware (metrics, CORS, request-ID, error envelopes) applies.
