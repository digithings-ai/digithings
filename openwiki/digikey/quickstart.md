---
type: quickstart
title: digikey Quickstart
description: Issue a dev API key, exchange it for a JWT, verify the JWKS, and run digikey tests.
tags: [digikey, quickstart, auth]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
sources:
  - id: openwiki-source-5a73d428d9c326b6be1e4770
    resource: repo://digikey/AGENTS.md
  - id: openwiki-source-89092abbe1894e77dc33d695
    resource: repo://digikey/ARCHITECTURE.md
  - id: openwiki-source-c7787f357945f31c54c47a46
    resource: repo://digikey/src/digikey/cli.py
  - id: openwiki-source-409717f2c30d896df6ac16b7
    resource: repo://digikey/src/digikey/server.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digikey Quickstart

> **Human gate.** `digikey/` auth, JWT, and crypto changes always require
> human review. The flows below are for local development only —
> `DIGIKEY_ALLOW_DEV_GLOBAL` and `DIGIKEY_ALLOW_EPHEMERAL_KEY` must never
> appear in production config.

## 1. Issue a dev key

```bash
export DIGIKEY_DATABASE_URL="sqlite:////workspace/.local_digikey.sqlite" \
       DIGIKEY_ALLOW_DEV_GLOBAL=1
python -m digikey.cli issue-key --tenant default --label dev \
  --scopes '*' --kind dev_global
```

The plaintext `dgk_live_…` key prints once — store it; it is never
retrievable again (only its bcrypt hash persists).

## 2. Exchange for a JWT and verify

```bash
curl -s http://127.0.0.1:8005/v1/oauth/token \
  -H 'Content-Type: application/json' \
  -d '{"grant_type":"api_key","api_key":"dgk_live_..."}'
curl -s http://127.0.0.1:8005/.well-known/jwks.json
```

Downstream services verify the JWT locally against the JWKS — they never
call digikey per request.

## 3. Gates

```bash
pytest tests/ -m unit -k "digikey" -v
ruff check digikey/ && ruff format --check digikey/
```

## Where next

- [digikey Architecture](/openwiki/digikey/architecture.md) — control
  plane, keys, claims, module map.
- [digikey Token Exchange and Scopes](/openwiki/digikey/token-exchange-and-scopes.md) —
  grants, scopes, revocation, middleware.
- [digikey API and Operations](/openwiki/digikey/api-and-operations.md) —
  endpoints, rate limits, env vars.
