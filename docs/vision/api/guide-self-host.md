---
title: "Self-host from GHCR — guide"
type: reference
status: generated
created: 2026-08-10
tags:
  - api
  - guide
---
# Self-host from GHCR

> Pull GHCR images and run digithings without a local compose build — tags, profiles, loopback defaults.

Prefer published images when you do not want to `docker compose build`. Requires Compose **v2.24+** and a clone of the repo for compose files, `config/`, and `.env` (build context is not required).

### Quick start

```bash
cp .env.example .env
# Edit .env: provider keys, DIGIKEY_*, optional AUTH_* for digichat

docker compose \
  -f docker-compose.yml \
  -f infra/self-host/compose.ghcr.yml \
  pull
docker compose \
  -f docker-compose.yml \
  -f infra/self-host/compose.ghcr.yml \
  up -d
```

Or: `make up-ghcr` / `make up-ghcr-digichat`.

### Profiles

- `digichat` — digichat + Postgres
- `digivault` — digivault
- `heartbeat` — digiclaw loop
- `litellm-cache` — Redis for LiteLLM
- `observability` — Prometheus + Grafana

### Image tags

- `DIGI_IMAGE_TAG` — digikey, digigraph, digiquant, digisearch, digismith, digivault, digiclaw (pin `sha-<12>` in production).
- `DIGICHAT_IMAGE_TAG` — digichat only; prefer `vX.Y.Z` from release-please.

All services bind loopback by default. Use Tailscale or Cloudflare Tunnel for remote access — never expose ports publicly. Full notes: `docs/templates/self-host/README.md` and `docs/DEPLOYMENT.md` in the repo.

See also [[digigraph]].
