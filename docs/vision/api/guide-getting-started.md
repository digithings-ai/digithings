---
title: "Getting started — guide"
type: reference
status: generated
created: 2026-08-10
tags:
  - api
  - guide
---
# Getting started

> Run the digithings stack locally — prerequisites, compose, environment, and make targets.

digithings is open-source, MIT-licensed AI infrastructure: modules that plug into the stack you already run rather than replacing it. digigraph orchestrates specialist sub-graphs — quant research, retrieval, vault, and chat. Self-hosted anywhere, BYOK, audit-on by default.

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

Interactive OpenAPI for every HTTP surface lives at [OpenAPI explorer](https://digithings.ai/docs/api/) — committed specs under `docs/openapi/`, not live FastAPI `/docs` on localhost.

See also [[digigraph]].
