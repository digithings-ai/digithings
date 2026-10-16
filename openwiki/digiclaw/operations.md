---
type: operations-guide
title: digiclaw Operations
description: Running digiclaw — heartbeat loop, drift wiring, audit sinks, scheduler env, monitors_tick configuration, and container profile.
tags: [digiclaw, operations, heartbeat, audit]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
sources:
  - id: openwiki-source-72050835d3541ab62444987d
    resource: repo://digiclaw/AGENTS.md
  - id: openwiki-source-8e060f8c1849eeb359de3487
    resource: repo://digiclaw/agents/web-watch-tick.yaml
  - id: openwiki-source-431d9db0a509b4927d0cfbf7
    resource: repo://digiclaw/ARCHITECTURE.md
  - id: openwiki-source-89f82bf9acfe38c98e0f20b2
    resource: repo://digiclaw/Dockerfile
  - id: openwiki-source-8b4ee7822ae07e223005983d
    resource: repo://digiclaw/src/digiclaw/cli.py
  - id: openwiki-source-a78d5139fbc45c09b4977f54
    resource: repo://digiclaw/src/digiclaw/digikey_auth.py
  - id: openwiki-source-03ae8e0b4a74134f450c8b0d
    resource: repo://digiclaw/src/digiclaw/heartbeat_runner.py
  - id: openwiki-source-76fe85e1283b473010f98f63
    resource: repo://digiclaw/src/digiclaw/monitors_tick.py
  - id: openwiki-source-3c35a18a896912fa07b94ee5
    resource: repo://digiclaw/src/digiclaw/scheduler.py
  - id: openwiki-source-b79fbbd921df689b4bbdc82f
    resource: repo://docker-compose.yml
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
---

# digiclaw Operations

digiclaw runs as a Compose service (`--profile heartbeat`) wrapping three
foreground processes inside one `entrypoint` shell. Everything it touches is
observable through the audit log.

## Container profile

The `heartbeat` profile in `docker-compose.yml` builds and starts the digiclaw
container via `digiclaw/Dockerfile`. It depends on `digigraph` and `digiquant`
being healthy, mounts the repo root read-only at `/workspace`, and uses a
named volume `digiclaw_state` for scheduler persistence:

```bash
docker compose --profile heartbeat up -d
```

The entrypoint runs three processes in a single shell (no `exec`, no
supervisor):

1.  **Bootstrap** — `digiclaw schedule start web-watch-tick || exit 1`. The
    `start` command is idempotent when the agent is already RUNNING (exit 0,
    re-arms), so `|| exit 1` turns only real bootstrap failures into a loud
    container exit.
2.  **Heartbeat loop** — `while true; do python -m digiclaw; sleep 1800; done &`.
    Backgrounded; runs the single-shot heartbeat cycle every 30 minutes.
3.  **Scheduler tick loop** — `while true; do digiclaw schedule tick; sleep 60; done`.
    Foreground; checks for due agents every 60 seconds.

Compose-level environment variables override loopback defaults to internal
Docker service names:

| Variable | Compose value | Purpose |
|---|---|---|
| `DIGIGRAPH_URL` | `http://digigraph:8000` | Health ping target |
| `DIGIQUANT_URL` | `http://digiquant:8001` | Health ping + drift check target |
| `DIGISEARCH_URL` | `http://digisearch:8002` | Monitor tick target |
| `DIGIKEY_URL` | `${DIGIKEY_URL:-http://digikey:8005}` | JWT exchange base URL |
| `DIGICLAW_DIGIKEY_API_KEY` | `${DIGICLAW_DIGIKEY_API_KEY:-}` | Machine API key for JWT minting |
| `DIGIQUANT_DATA_DIR` | `/app/data` | Required for re-optimization path |
| `AUDIT_LOG_PATH` | `/audit/events.jsonl` | Converged audit file |
| `DIGI_WORKSPACE` | `/workspace` | Workspace root |
| `DIGICLAW_AGENTS_DIR` | `/workspace/digiclaw/agents` | Agent YAML directory (read-only mount) |
| `DIGICLAW_SCHEDULER_STATE` | `/state/scheduler_state.json` | Durable state on the named volume |

## Heartbeat loop

```bash
while true; do python -m digiclaw; sleep 1800; done
```

The image (`python:3.12-slim` + `digibase` + `digiclaw`) runs
`CMD ["python3", "-m", "digiclaw"]` with an import-level `HEALTHCHECK`.
Each cycle: ping `DIGIGRAPH_URL` (default `http://127.0.0.1:8000`) and
`DIGIQUANT_URL` (default `http://127.0.0.1:8001`), emit one `heartbeat`
event with per-service OK/detail, then run the drift check.

## Drift wiring

`REOPTIMIZE_STRATEGY` (default `mean_reversion_tech`) selects the strategy
polled at `GET /check_drift`. The bearer comes from
`digikey_bearer_token()`: `DIGICLAW_DIGIKEY_API_KEY` (or legacy
`DIGIKEY_API_KEY`) exchanged at `DIGIKEY_URL` for a JWT scoped to
`digiquant:backtest` + `digiquant:optimize`. No key → explicit
`drift_check_skipped` event (expected in dev). Drift detected →
`reoptimize_triggered`, then re-optimization requires `DIGIQUANT_DATA_DIR`
or a `reoptimize_skipped` event is logged. Every failure path audits —
nothing skips silently.

## Audit sinks and redaction

Events append to the JSONL log (`DIGI_WORKSPACE`-relative); an optional
`AUDIT_SINK_URL` POST mirrors them best-effort. Password, api_key, token,
and secret substrings redact before writing. Inspect with:

```bash
cat digiquant/results/audit/events.jsonl | head -20
```

## Scheduler

```bash
digiclaw schedule status # next-run visibility over digiclaw/agents/*.yaml
```

Lifecycle (`start`/`stop`/`pause`/`resume`) and isolated ticks persist
durable state; supervisors invoke `digiclaw schedule tick` for continuous
`interval_seconds` schedules.

State is persisted as atomic tmp-file-replace JSON at
`DIGICLAW_SCHEDULER_STATE` (default
`{DIGI_WORKSPACE}/.digiclaw/scheduler_state.json`). On restart, running
agents whose `next_run_at` is overdue or marked `pending` are re-queued
immediately so missed ticks are not dropped. Each tick invokes the agent's
runner in isolation: an exception records `last_status="error"` +
`last_error` and still advances `next_run_at`, so one failing agent never
poisons the next schedule.

## Phase C monitors_tick (web-watch-tick)

The `web-watch-tick` agent (`digiclaw/agents/web-watch-tick.yaml`) is a
continuous schedule with `interval_seconds: 60` and `enabled: true`. It is
the only non-no-op agent runner in the current codebase: every other agent
name keeps the scheduler's `default_agent_runner` (a no-op placeholder until
further runtimes exist).

### How it runs

The scheduler tick loop invokes `digiclaw schedule tick` every 60 seconds.
When the scheduler's `tick()` finds `web-watch-tick` RUNNING and due, it
calls `_dispatch_agent` in `cli.py`, which maps the agent name to
`digiclaw.monitors_tick.run_due_monitors()`.

### JWT exchange

`run_due_monitors()` mints a digikey service JWT via a fully qualified lazy
import of `digibase.service_auth.get_service_jwt`, consuming:

| Parameter | Value |
|---|---|
| `key_env` | `DIGICLAW_DIGIKEY_API_KEY` |
| `digikey_url_env` | `DIGIKEY_URL` |
| `scopes` | `("digisearch:query",)` |

The JWT import is deliberately lazy and fully qualified inside the function
so that importing the `monitors_tick` module needs neither credentials nor
the `digibase` module, and the stable patch target
`digibase.service_auth.get_service_jwt` keeps working for tests.

An explicit `bearer_token` argument skips minting entirely (useful in
tests). Both missing-key and token-exchange failures **raise** rather than
returning an empty tick; the scheduler persists them as the agent's
`last_status="error"` + `last_error`, and `digiclaw schedule tick` prints
the failed outcome.

### POST to digisearch

The tick POSTs `{DIGISEARCH_URL}/v1/monitors/tick` with a 120s httpx
timeout and `raise_for_status()`. The base URL resolves as:

1.  Explicit `digisearch_url` argument
2.  `DIGISEARCH_URL` environment variable
3.  Default `http://127.0.0.1:8002`

Blank env values fall through to the default; trailing `/` is normalized
before appending `/v1/monitors/tick`.

The response payload is `{"runs": [...]}`. `run_due_monitors()` returns
`{"runs": n, "failed": m}`, where `failed` counts runs with
`status == "failed"` (per-watch failures are isolated inside digisearch and
still return as stored runs). A `no_change` outcome from digisearch counts as
a successful run.

## Environment variable reference

| Variable | Default | Used by |
|---|---|---|
| `DIGIGRAPH_URL` | `http://127.0.0.1:8000` | Heartbeat health ping |
| `DIGIQUANT_URL` | `http://127.0.0.1:8001` | Heartbeat health ping, drift check, re-optimize |
| `DIGISEARCH_URL` | `http://127.0.0.1:8002` | `monitors_tick` POST target |
| `DIGIKEY_URL` | `http://127.0.0.1:8005` | JWT token exchange base URL |
| `DIGICLAW_DIGIKEY_API_KEY` | (unset) | Machine API key for JWT minting; missing → heartbeat skips drift, tick raises |
| `DIGIKEY_API_KEY` | (unset) | Legacy alias for `DIGICLAW_DIGIKEY_API_KEY` (heartbeat only) |
| `REOPTIMIZE_STRATEGY` | `mean_reversion_tech` | Strategy ID polled at `/check_drift` |
| `DIGIQUANT_DATA_DIR` | (required for re-optimize) | Data directory passed to `/run_optimize` POST body |
| `AUDIT_LOG_PATH` | `digiquant/results/audit/events.jsonl` | JSONL audit file path |
| `AUDIT_SINK_URL` | (unset) | Optional NDJSON POST mirror |
| `DIGI_WORKSPACE` | `.` | Workspace root for resolving paths |
| `DIGICLAW_AGENTS_DIR` | `digiclaw/agents` (resolved from package) | Directory of agent schedule YAML files |
| `DIGICLAW_SCHEDULER_STATE` | `{DIGI_WORKSPACE}/.digiclaw/scheduler_state.json` | Durable scheduler lifecycle state |
