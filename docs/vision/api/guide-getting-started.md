---
title: "Getting started — guide"
type: reference
status: generated
created: 2026-06-29
tags:
  - api
  - guide
---
# Getting started

> Run the digithings stack locally — prerequisites, compose, environment, and make targets.

digithings is an open-core agentic stack — orchestration, quant research, retrieval, and chat behind one supervisor. Self-hosted, BYOK, audit-on by default.

### Prerequisites

- Docker (with Compose)
- Python ≥ 3.12 (for running services outside Docker)
- Node.js LTS (for the frontends)

### Run the whole stack

```bash
git clone https://github.com/digithings-ai/digithings && cd digithings
cp .env.example .env   # add your keys
docker compose up -d
```

Each backend service exposes a liveness probe at `GET /healthz`. The service URLs and ports are defined in `docker-compose.yml`; reference them through env vars (`$DIGIGRAPH_URL`, `$DIGIKEY_URL`, …) rather than hardcoding an address.

### Essential environment

- `OPENROUTER_API_KEY` / `OPENAI_API_KEY` — LLM access via the LiteLLM proxy.
- `DIGIKEY_ADMIN_TOKEN` — required to mint API keys (see Authentication).
- `DIGIKEY_PRIVATE_KEY_PEM` — stable RS256 signing key for production.
- See `.env.example` for the full, annotated list.

### Useful make targets

- `make up` / `make down` — start / stop the core stack.
- `make up-digichat` — start the chat BFF + its Postgres.
- `make stack-local` — run the Python services without Docker.
- `make test-unit` — unit tests (no stack required).

See also [[digigraph]].
