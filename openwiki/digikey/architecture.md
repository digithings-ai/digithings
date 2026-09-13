---
type: service-architecture
title: digikey Architecture
description: Auth plane design of digikey — opaque API keys, RS256 JWT issuance, JWKS-based local verification, and module map.
tags: [digikey, auth, jwt, architecture]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
sources:
  - id: openwiki-source-89092abbe1894e77dc33d695
    resource: repo://digikey/ARCHITECTURE.md
  - id: openwiki-source-a9c19178ed8f5a7e328d94f4
    resource: repo://digikey/src/digikey/crypto_keys.py
  - id: openwiki-source-ab05f480f2322e42995383f8
    resource: repo://digikey/src/digikey/models.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digikey Architecture

digikey (port 8005) is the single authentication and authorization control
plane: every protected route on digigraph, digiquant, and digisearch
refuses traffic without a short-lived JWT it signed. No service issues its
own tokens; no service trusts another issuer. The design keeps digikey on
the hot path for key exchange but **off** the hot path for verification —
consumers verify locally against a cached JWKS, so digikey can be down for
minutes without breaking in-flight requests.

## Two responsibilities

**Opaque API key management.** External callers hold a `dgk_live_`-prefixed
secret; digikey stores only a bcrypt hash (`ApiKeyRow`, immutable after
creation) and shows the raw secret once. Two kinds: `standard`
(explicitly assigned scopes) and `dev_global` (`scopes=["*"]`, dev-only
behind `DIGIKEY_ALLOW_DEV_GLOBAL=1`).

**JWT issuance via token exchange.** `POST /v1/oauth/token` verifies the
key (prefix lookup, bcrypt, `revoked_at` check) and returns a short-lived
RS256 JWT carrying scopes, tenant context, identity, and optional profile
pointer. Signing uses a 2048-bit RSA pair from `DIGIKEY_PRIVATE_KEY_PEM`
(preferred) or an ephemeral dev key (`kid` in the header via
`jwt_issue.py`); startup refuses to run with neither.

## Claims and context

`TokenClaims` normalizes verified JWTs (`sub/iss/aud/exp/jti`,
`tenant_slug`, `project_id`, `profile_id/version`, `scopes`, `key_pub`
prefix only, `principal_kind`); `claims_to_context()` attaches a
`DigiAuthContext` to `request.state` for downstream handlers. Raw key
material appears nowhere in claims, logs, or responses.

## Module map

| File | Role |
|------|------|
| `server.py` | FastAPI app, routes, startup hook |
| `crypto_keys.py` | RSA load/generate, PEM serialization |
| `jwt_issue.py` / `jwt_verify.py` | Sign + JWKS document / decode + JWKS client |
| `key_crypto.py` | Key generation (`secrets`), bcrypt hash/verify |
| `db.py` / `db_schema.py` | SQLAlchemy engine, sessions, `ApiKeyRow` |
| `scopes.py` | Wildcard matching, downscoping |
| `integrations/service_middleware.py` | `DigiAuthMiddleware` + per-service path-scope tables |
| `ratelimit.py` | Per-IP token bucket for auth paths |
| `blocklist*.py` | Redis JTI blocklist (ADR-0007) |
| `cli.py` | `digikey issue-key` bootstrap |

Hard deps: Pydantic v2, FastAPI, SQLAlchemy 2, bcrypt, PyJWT.
