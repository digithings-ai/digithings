---
title: "digichat — API reference"
type: reference
status: generated
created: 2026-10-02
tags:
  - api
  - core
relevance:
  - digichat
---
# digichat — API reference

> Talk to your stack with your keys, models and audit log.

**Role:** Chat surface · Next.js BFF · BYOK · **Tier:** core

## Overview
A Next.js and React BFF streaming digigraph through the Vercel AI SDK, your key forwarded per request — never stored, never logged.

Auth.js handles identity; Postgres and Drizzle persist sessions for humans and agents alike.

## Authentication
`POST /api/chat` requires a digichat session, unless the request is a verified embed or an anonymous install the deployment allows. The body is `{ messages }`. The response is a stream, not a JSON object of content and tool calls. `GET /api/health` is public readiness and can return 503 with `{ ok, checks, version, license_status }`. `GET /api/ecosystem/config` requires a session. Profile A secrets are `AUTH_SECRET` and `DIGIKEY_BFF_TOKEN`. `OPENROUTER_API_KEY` and `CORE_SUPABASE_*` are not required to boot the Docker BFF. Auth.js exchanges a BFF session for a digikey JWT when the deployment calls digigraph.


## Run locally
```bash
docker compose --profile digichat up -d
```

```bash
make digichat-dev   # Next.js dev server with hot reload
```

## Configuration
- `AUTH_SECRET` — required: Auth.js secret (Profile A): openssl rand -base64 32.
- `DIGIKEY_BFF_TOKEN` — required: Bearer for grant_type=bff_session (Profile A).
- `OPENROUTER_API_KEY`: Optional. Not required to boot the Docker BFF.
- `CORE_SUPABASE_URL`: Optional vault Supabase project URL. Not required to boot the Docker BFF.
- `CORE_SUPABASE_ANON_KEY`: Optional anon key. Not required to boot the Docker BFF.

## Endpoints

Base URL: `$DIGICHAT_URL` (the service URL from docker-compose.yml).

### GET /api/health
Public readiness. 200 when required checks pass, otherwise 503.

auth: none

Response example:
```json
{ "ok": true, "checks": { "service": "ok" }, "version": "2.4.0", "license_status": "valid" }
```

### POST /api/chat
Streams one chat turn. Retrieval tools are available to the assistant; they are not called on every reply.

auth: session, verified embed, or allowed anonymous install

Request:
- `messages` (UIMessage[]) — required: Conversation so far.

```bash
curl -N -X POST $DIGICHAT_URL/api/chat \
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

auth: session

### POST /api/v1/chat
OpenAI-compatible chat proxy through the BFF.

auth: session

## Notes
- Committed OpenAPI: docs/openapi/digichat.json (authored; path existence checked in tests/contracts).
- Self-host: make up-ghcr-digichat pulls ghcr.io/digithings-ai/digichat (see infra/self-host/compose.ghcr.yml).

## Stack
Next.js, React, Vercel AI SDK, Auth.js, Postgres, Drizzle

## Related
digigraph, digikey, digisearch

## Links
- [Open digichat](https://digithings.ai/chat)
- [Source](https://github.com/digithings-ai)

See also [[digichat]].
