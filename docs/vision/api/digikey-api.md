---
title: "digikey — API reference"
type: reference
status: generated
created: 2026-06-29
tags:
  - api
  - support
relevance:
  - digikey
---
# digikey — API reference

> Identity, JWTs, and scoped keys — one issuer for humans and machines.

**Role:** Auth · RS256 JWTs · scoped API keys · **Tier:** support

## Overview
RS256-signed JWTs with a published JWKS, organization and project membership, and row-level scopes baked into the token.

SQLAlchemy over Postgres stores keys, bcrypt hashes them, and an optional Redis blocklist handles revocation.

## Authentication
digikey is the issuer. Admin routes require the `DIGIKEY_ADMIN_TOKEN` bearer; token exchange takes a raw API key or a BFF-session grant. JWKS and /healthz are public.

- `digigraph:workflow / :chat / :mcp` — DigiGraph routes
- `digiquant:backtest / :optimize` — DigiQuant routes
- `digisearch:query / :ingest` — DigiSearch routes
- `*` — Wildcard (all scopes) — dev_global keys only

## Run locally
```bash
docker compose up -d digikey
```

```bash
uvicorn digikey.server:app
```

## Configuration
- `DIGIKEY_DATABASE_URL` — required: SQLite or Postgres URL for key storage.
- `DIGIKEY_PRIVATE_KEY_PEM`: RSA 2048 PEM for RS256 signing (prod).
- `DIGIKEY_ADMIN_TOKEN` — required: Bearer for POST /v1/admin/keys.
- `DIGIKEY_BFF_TOKEN`: Bearer for grant_type=bff_session (DigiChat).
- `DIGIKEY_JWT_TTL_SEC` (default `900`): Access-token lifetime.
- `DIGIKEY_BLOCKLIST_REDIS_URL`: Redis for JWT revocation (prod).

## Endpoints

Base URL: `$DIGIKEY_URL` (the service URL from docker-compose.yml).

### GET /.well-known/jwks.json
RSA public key set for verifying issued JWTs.

auth: none

```bash
curl $DIGIKEY_URL/.well-known/jwks.json
```

### POST /v1/admin/keys
Create an API key. The raw key is returned ONCE.

auth: admin token · rate: 10/min/IP

Request:
- `tenant_slug` (string) — required: Tenant identifier.
- `label` (string): Human-readable key name.
- `scopes` (string[]): Granted scopes.

Response example:
```json
{ "key_prefix": "dgk_live_…", "api_key": "dgk_live_…(once)", "id": "<uuid>" }
```

```bash
curl -X POST $DIGIKEY_URL/v1/admin/keys \
  -H "Authorization: Bearer $DIGIKEY_ADMIN_TOKEN" -H "content-type: application/json" \
  -d '{"tenant_slug":"acme","scopes":["digiquant:backtest"]}'
```

### POST /v1/oauth/token
Exchange an API key (or BFF session) for a short-lived RS256 JWT.

auth: none (key in body) · rate: 10/min/IP

Request:
- `grant_type` (string) — required: "api_key" | "bff_session".
- `api_key` (string): Raw dgk_live_ key (api_key grant).
- `requested_scopes` (string[]): Downscope to a subset of granted scopes.

Response example:
```json
{ "access_token": "<JWT>", "token_type": "Bearer", "expires_in": 900 }
```

```bash
curl -X POST $DIGIKEY_URL/v1/oauth/token \
  -H "content-type: application/json" \
  -d '{"grant_type":"api_key","api_key":"'"$DIGI_API_KEY"'"}'
```

```python
tok = httpx.post(
    f"{os.environ['DIGIKEY_URL']}/v1/oauth/token",
    json={"grant_type": "api_key", "api_key": os.environ["DIGI_API_KEY"]},
).json()["access_token"]
```

### POST /v1/admin/keys/{key_id}/revoke
Revoke a key and blocklist its live JWTs (when Redis is configured).

auth: admin token · rate: 10/min/IP

Response example:
```json
{ "revoked": true, "jtis_invalidated": 3 }
```

## Stack
PyJWT, cryptography, bcrypt, SQLAlchemy, Postgres, Redis

## Related
digichat, digigraph, digismith

## Links
- [Source](https://github.com/digithings-ai)

See also [[digikey]].
