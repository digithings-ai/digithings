# Digi – Small Firm Deployment (Phase 3)

One-command run and optional packaging for running your own agentic stack.

## One-click run

From the repo root, with [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose) running:

```bash
cp .env.example .env
# Edit .env: set OLLAMA_API_KEY (or OPENAI_API_KEY) and any overrides
docker compose up -d
```

- **DigiGraph** → http://127.0.0.1:8000  
- **DigiQuant** → http://127.0.0.1:8001  
- **LiteLLM** → http://127.0.0.1:4000  

All bind to loopback only. **Note:** Default DigiQuant image includes NautilusTrader; backtest returns real results. Set `NAUTILUS=0` when building to exclude Nautilus (backtest/optimize/pipeline then return 503). Use Tailscale or Cloudflare Tunnel for remote access (see **SECURITY.md**).

## With heartbeat (24/7 monitoring)

```bash
docker compose --profile heartbeat up -d
```

Adds the heartbeat service: health checks every 30 min and audit log to `digiquant/results/audit/events.jsonl`. If ADDM reports drift (when implemented), re-optimize is triggered automatically.

## Packaging for distribution

To produce a tarball for another machine or small firm:

```bash
# From repo root
./scripts/package.sh
# Or: make package
```

This creates `digi-bundle-YYYYMMDD.tar.gz` with the repo (excluding .git, .venv, __pycache__). Recipients:

1. Extract, copy `.env.example` to `.env`, and set secrets.
2. Run `docker compose up -d` (optionally `--profile heartbeat`).
3. See **DOCKER.md** and **HEARTBEAT.md** for verification and cron.

## 7-day unattended run (Phase 3 milestone)

To run for 7 days without manual intervention:

1. Start with heartbeat: `docker compose --profile heartbeat up -d`.
2. Set `AUDIT_LOG_PATH` so audit is written to a persistent volume (default in compose uses `./digiquant/results/audit`).
3. Optionally set `REOPTIMIZE_STRATEGY` in the heartbeat container if using ADDM drift → re-optimize.
4. Monitor audit log and service health; no live trading without explicit human gates (see **SECURITY.md**).

See **HEARTBEAT.md** for the checklist the heartbeat agent follows.
