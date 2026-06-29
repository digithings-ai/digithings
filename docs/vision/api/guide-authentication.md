---
title: "Authentication — guide"
type: reference
status: generated
created: 2026-06-29
tags:
  - api
  - guide
---
# Authentication

> Issue and use digikey JWTs across the stack — mint a key, exchange for a token, call a service.

digikey is the single issuer of RS256 JWTs. Services verify tokens against digikey's JWKS and enforce per-route scopes. The flow: mint an API key (admin), exchange it for a short-lived JWT, then call services with `Authorization: Bearer <jwt>`.

### 1 · Mint an API key (admin)

```bash
curl -X POST $DIGIKEY_URL/v1/admin/keys \
  -H "Authorization: Bearer $DIGIKEY_ADMIN_TOKEN" \
  -H "content-type: application/json" \
  -d '{"tenant_slug":"acme","scopes":["digiquant:backtest","digigraph:workflow"]}'
# → { "api_key": "dgk_live_… (shown once)", "key_prefix": "dgk_live_…", "id": "<uuid>" }
```

### 2 · Exchange for a JWT

```bash
curl -X POST $DIGIKEY_URL/v1/oauth/token \
  -H "content-type: application/json" \
  -d '{"grant_type":"api_key","api_key":"'"$DIGI_API_KEY"'"}'
# → { "access_token": "<JWT>", "token_type": "Bearer", "expires_in": 900 }
```

```python
import os, httpx

tok = httpx.post(
    f"{os.environ['DIGIKEY_URL']}/v1/oauth/token",
    json={"grant_type": "api_key", "api_key": os.environ["DIGI_API_KEY"]},
).json()["access_token"]
```

```typescript
const r = await fetch(`${process.env.DIGIKEY_URL}/v1/oauth/token`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ grant_type: "api_key", api_key: process.env.DIGI_API_KEY }),
});
const { access_token } = await r.json();
```

### 3 · Call a service

```bash
curl -X POST $DIGIGRAPH_URL/workflow \
  -H "Authorization: Bearer $JWT" -H "content-type: application/json" \
  -d '{"prompt":"Backtest a momentum strategy on AAPL"}'
```

### Scopes

- `digigraph:workflow`, `digigraph:chat`, `digigraph:mcp`
- `digiquant:backtest`, `digiquant:optimize`
- `digisearch:query`, `digisearch:ingest`
- JWTs are short-lived (default 900s); revoke a key via `POST /v1/admin/keys/{id}/revoke`.
