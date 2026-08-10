---
title: "digichat — API reference"
type: reference
status: generated
created: 2026-08-10
tags:
  - api
  - core
relevance:
  - digichat
---
# digichat — API reference

> Talk to your stack with your keys, your models, your audit log.

**Role:** Chat surface · Next.js BFF · BYOK · **Tier:** core

## Overview
A Next.js and React BFF streaming digigraph through the Vercel AI SDK, your key forwarded per request — never stored, never logged.

NextAuth handles identity; Postgres and Drizzle persist sessions for humans and agents alike.

## Authentication
The deployed digithings.ai chat is an agentic Cloudflare Pages Function (no login) that grounds answers in the digivault docs. The full Docker BFF additionally authenticates users via NextAuth and exchanges a BFF session for a digikey JWT to call digigraph.


## Run locally
```bash
docker compose --profile digichat up -d
```

```bash
make digichat-dev   # Next.js dev server with hot reload
```

## Configuration
- `OPENROUTER_API_KEY` — required: LLM calls via OpenRouter free models.
- `CORE_SUPABASE_URL` — required: Vault Supabase project URL (RLS read).
- `CORE_SUPABASE_ANON_KEY` — required: Anon key for RLS-gated vault reads.
- `AUTH_SECRET`: NextAuth secret (Docker BFF): openssl rand -base64 32.
- `DIGIKEY_BFF_TOKEN`: Bearer for grant_type=bff_session (Docker BFF).

## Endpoints

Base URL: `$DIGICHAT_URL` (the service URL from docker-compose.yml).

### GET /api/health
Liveness probe.

auth: none

Response example:
```json
{ "ok": true }
```

### POST /api/chat
Agentic chat grounded in digivault (single tool: search_digivault).

auth: none (public, rate-limited)

Request:
- `messages` ({role,content}[]) — required: Conversation so far.
- `model` (string): OpenRouter free model id.

Response example:
```json
{ "content": "…grounded answer…", "tool_calls": [] }
```

```bash
curl -X POST $DIGICHAT_URL/api/chat \
  -H "content-type: application/json" \
  -d '{"messages":[{"role":"user","content":"What does digigraph do?"}]}'
```

### GET /api/conversations
List persisted conversations (Docker BFF).

auth: session

### POST /api/conversations
Create a conversation (Docker BFF).

auth: session

### GET /api/conversations/{id}
Fetch one conversation (Docker BFF).

auth: session

### DELETE /api/conversations/{id}
Delete a conversation (Docker BFF).

auth: session

### GET /api/ecosystem/config
Ecosystem config for the chat shell.

auth: none / session

### POST /api/v1/chat
OpenAI-compatible chat proxy through the BFF.

auth: session

## Notes
- Committed OpenAPI: docs/openapi/digichat.json (authored; path existence checked in tests/contracts).
- Self-host: make up-ghcr-digichat pulls ghcr.io/digithings-ai/digichat (see infra/self-host/compose.ghcr.yml).

## Stack
Next.js, React, Vercel AI SDK, NextAuth, Postgres, Drizzle

## Related
digigraph, digikey, digisearch

## Links
- [Open digichat](https://digithings.ai/chat)
- [Source](https://github.com/digithings-ai)

See also [[digichat]].
