# Self-host digithings from GHCR

Pull prebuilt service images instead of `docker compose build`.

## Prerequisites

- Docker Engine + Compose **v2.24+** (needed for `build: !reset null` merge)
- A clone of this repo (for `docker-compose.yml`, `config/`, and `.env`) — build context is not required
- GHCR packages readable (public packages, or `docker login ghcr.io`)

## Quick start

```bash
cp .env.example .env
# Edit .env: provider keys, DIGIKEY_*, optional AUTH_* for digichat

# Core stack (digikey, digigraph, digiquant, digisearch, digismith, LiteLLM, Ollama)
docker compose \
  -f docker-compose.yml \
  -f infra/self-host/compose.ghcr.yml \
  pull
docker compose \
  -f docker-compose.yml \
  -f infra/self-host/compose.ghcr.yml \
  up -d
```

## Profiles

Same as the root compose file:

| Profile | Extra services |
|---------|----------------|
| `digichat` | digichat + Postgres |
| `digivault` | digivault |
| `heartbeat` | digiclaw loop |
| `litellm-cache` | Redis for LiteLLM |
| `observability` | Prometheus + Grafana |

Example with digichat:

```bash
docker compose \
  -f docker-compose.yml \
  -f infra/self-host/compose.ghcr.yml \
  --profile digichat \
  up -d
```

## Image tags

| Variable | Default | Notes |
|----------|---------|--------|
| `DIGI_IMAGE_TAG` | `latest` | digikey, digigraph, digiquant, digisearch, digismith, digivault, digiclaw |
| `DIGICHAT_IMAGE_TAG` | `latest` | digichat only (prefer `vX.Y.Z` from release-please) |

Production: pin `DIGI_IMAGE_TAG=sha-<12-char-git-sha>` so every service matches one monorepo commit. See [RELEASES.md](../../../RELEASES.md).

## API docs (Swagger)

With the stack up, each FastAPI service exposes:

| Service | Swagger UI | OpenAPI JSON |
|---------|------------|--------------|
| digigraph | http://127.0.0.1:8000/docs | `/openapi.json` |
| digiquant | http://127.0.0.1:8001/docs | `/openapi.json` |
| digisearch | http://127.0.0.1:8002/docs | `/openapi.json` |
| digismith | http://127.0.0.1:8003/docs | `/openapi.json` |
| digivault | http://127.0.0.1:8004/docs | `/openapi.json` |
| digikey | http://127.0.0.1:8005/docs | `/openapi.json` |

Committed OpenAPI snapshots live under [`docs/openapi/`](../../openapi/) (when exported). digichat is Next.js — see its BFF OpenAPI under the same directory.

## Related

- [docs/DEPLOYMENT.md](../../DEPLOYMENT.md)
- [SECURITY.md](../../../SECURITY.md) — loopback + Tunnel only
- Overlay file: [`compose.ghcr.yml`](../../../infra/self-host/compose.ghcr.yml)
- Epic: https://github.com/digithings-ai/digithings/issues/2016

## Minimal digichat Profile A

Clients who only need digichat + digikey + digigraph + LiteLLM + digivault should use
[`infra/digichat-release/`](../../../infra/digichat-release/) and
[`docs/digichat/INSTALL.md`](../../digichat/INSTALL.md) — not the full-stack
`make up-ghcr` path (which also starts digiquant / digisearch / digismith by default).
