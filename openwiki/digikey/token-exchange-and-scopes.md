---
type: behavior-guide
title: digikey Token Exchange and Scopes
description: How digikey mints JWTs — grant types, scope matching and downscoping, claims, revocation, and consumer middleware.
tags: [digikey, jwt, scopes, auth]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-5a73d428d9c326b6be1e4770
    resource: repo://digikey/AGENTS.md
  - id: openwiki-source-89092abbe1894e77dc33d695
    resource: repo://digikey/ARCHITECTURE.md
  - id: openwiki-source-96809bc2f0f53abfa1722d2a
    resource: repo://digikey/src/digikey/integrations/service_middleware.py
  - id: openwiki-source-7ab6326ed4f6ed875a1db34b
    resource: repo://digikey/src/digikey/jwt_issue.py
  - id: openwiki-source-181ce172e158ab2d61ade6e2
    resource: repo://digikey/src/digikey/scopes.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digikey Token Exchange and Scopes

Every JWT in the ecosystem is minted by `POST /v1/oauth/token` and
verified locally by consumers. This page covers the exchange mechanics;
endpoint operations live in [API and Operations](/openwiki/digikey/api-and-operations.md).

## Grant types

- **`api_key`**: caller presents the raw `dgk_live_…` secret; digikey looks
  up by prefix, verifies bcrypt, checks `revoked_at`, and issues.
- **`bff_session`**: digichat's BFF presents `DIGIKEY_BFF_TOKEN`; digikey
  issues with `principal_kind=bff_session`, `sub=bff:<subject>`, and the
  default BFF scope set (workflow, chat, MCP, backtest, optimize, query,
  ingest, vault read) unless overridden.

`issue_access_token()` returns `(jwt, jti)` signed RS256 with `kid` in the
header; TTL comes from `DIGIKEY_JWT_TTL_SEC` (short by default — minutes,
not hours). Profile pointers (`profile_id` + `profile_version`) are
always emitted together or omitted together.

## Scope matching and downscoping

`scope_grants_required(granted, required)` implements wildcard matching:
`*` grants everything, `service:*` grants the subtree, otherwise exact
match. Callers may request `requested_scopes` but only ever receive a
**subset** of their granted scopes — issuance above grant is refused.
New scopes require updating the ARCHITECTURE scope table and notifying
consumers.

## Revocation

Two tiers: `revoked_at` on the key blocks **new** exchanges always; the
Redis JTI blocklist (`DIGIKEY_BLOCKLIST_REDIS_URL`, ADR-0007) additionally
fails closed on **live** tokens until `exp` when consumers call
`blocklist.is_blocked(jti)` in the middleware path. Without Redis,
already-issued JWTs stay valid until expiry.

## Consumer middleware

`DigiAuthMiddleware(service=..., path_scopes=...)` runs per service with
that service's scope table (`digigraph_path_scopes`,
`digiquant_path_scopes`, `digisearch_path_scopes`, …): `None` means
public, otherwise a bearer is required (401 without, 503 when the consumer
has no JWKS configured). Verified claims land on `request.state.digi_auth`
as a `DigiAuthContext`. Verification uses a cached JWKS client —
`decode_token()` against `DIGIKEY_JWKS_URL` (or a pinned PEM) — so
digikey outages don't break in-flight requests.
