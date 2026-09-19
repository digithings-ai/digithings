---
type: operations-guide
title: digiclaw Operations
description: Running digiclaw — heartbeat loop, drift wiring, audit sinks, scheduler env, and container.
tags: [digiclaw, operations, heartbeat, audit]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-19T12:20:11.463Z
sources:
  - id: openwiki-source-72050835d3541ab62444987d
    resource: repo://digiclaw/AGENTS.md
  - id: openwiki-source-8e060f8c1849eeb359de3487
    resource: repo://digiclaw/agents/web-watch-tick.yaml
  - id: openwiki-source-431d9db0a509b4927d0cfbf7
    resource: repo://digiclaw/ARCHITECTURE.md
  - id: openwiki-source-89f82bf9acfe38c98e0f20b2
    resource: repo://digiclaw/Dockerfile
  - id: openwiki-source-a78d5139fbc45c09b4977f54
    resource: repo://digiclaw/src/digiclaw/digikey_auth.py
  - id: openwiki-source-03ae8e0b4a74134f450c8b0d
    resource: repo://digiclaw/src/digiclaw/heartbeat_runner.py
  - id: openwiki-source-76fe85e1283b473010f98f63
    resource: repo://digiclaw/src/digiclaw/monitors_tick.py
  - id: openwiki-source-b79fbbd921df689b4bbdc82f
    resource: repo://docker-compose.yml
generated: { by: "openwiki/0.5.0", at: "2026-09-19T12:20:11.463Z" }
---

# digiclaw Operations

digiclaw runs as a Compose service (`--profile heartbeat`) wrapping the single-shot
runner in a shell loop, plus a parallel `digiclaw schedule tick` loop for the
agent scheduler and a one-time bootstrap for the web-watch-tick agent. Everything
it touches is observable through the audit log.

## Container

The image (`python:3.12-slim` + editable `digibase` and `digiclaw` installs)
runs `CMD ["python3", "-m", "digiclaw"]` with an import-level `HEALTHCHECK`
(`python3 -c "import digiclaw"`, 60 s interval, 5 s timeout, 10 s start-period).

### Compose wiring

```yaml
heartbeat:
  build:
    context: .
    dockerfile: digiclaw/Dockerfile
  image: digi-digiclaw:latest
  profiles: [heartbeat]
  env_file: .env
  environment:
    - DIGIGRAPH_URL=http://digigraph:8000
    - DIGIQUANT_URL=http://digiquant:8001
    - DIGISEARCH_URL=http://digisearch:8002
    - DIGIKEY_URL=${DIGIKEY_URL:-http://digikey:8005}
    - DIGICLAW_DIGIKEY_API_KEY=${DIGICLAW_DIGIKEY_API_KEY:-}
    - DIGIQUANT_DATA_DIR=/app/data
    - AUDIT_LOG_PATH=/audit/events.jsonl
    - DIGI_WORKSPACE=/workspace
    - DIGICLAW_AGENTS_DIR=/workspace/digiclaw/agents
    - DIGICLAW_SCHEDULER_STATE=/state/scheduler_state.json
  volumes:
    - ./digiquant/results/audit:/audit
    - ./:/workspace:ro
    - digiclaw_state:/state
  entrypoint: ["/bin/sh", "-c"]
  command:
    - |
      digiclaw schedule start web-watch-tick || exit 1
      while true; do python -m digiclaw; sleep 1800; done &
      while true; do digiclaw schedule tick; sleep 60; done
  depends_on:
    digigraph:
      condition: service_healthy
    digiquant:
      condition: service_healthy
```

Three concurrent processes run inside the container:

1. **Bootstrap** — `digiclaw schedule start web-watch-tick || exit 1`. `start`
   is idempotent when the agent is already RUNNING; `|| exit 1` only triggers
   on a real bootstrap failure.
2. **Heartbeat loop** (background) — `while true; do python -m digiclaw; sleep
   1800; done &`. One cycle every 30 minutes.
3. **Scheduler tick loop** (foreground) — `while true; do digiclaw schedule
   tick; sleep 60; done`. Processes every due agent every 60 seconds.

The service depends on `digigraph` and `digiquant` being healthy before startup.

Three volumes are mounted:

| Mount | Purpose |
|-------|---------|
| `./digiquant/results/audit:/audit` | Shared audit JSONL (also used by digigraph and digiquant) |
| `./:/workspace:ro` | Read-only repo mount; provides `digiclaw/agents/*.yaml` |
| `digiclaw_state:/state` | Named volume for durable scheduler state |

## Heartbeat loop

Each cycle: ping `DIGIGRAPH_URL` (default `http://127.0.0.1:8000`) and
`DIGIQUANT_URL` (default `http://127.0.0.1:8001`), emit one `heartbeat`
audit event with per-service `OK`/detail fields, then run the drift check and
the `HEARTBEAT.md` presence check. In Docker, URLs resolve via the internal
network: `http://digigraph:8000` and `http://digiquant:8001`.

The heartbeat runner is single-shot — `main()` exits 0 when all health pings
succeed and 1 when any service is unhealthy (REM-073).

## Drift wiring

`REOPTIMIZE_STRATEGY` (default `mean_reversion_tech`) selects the strategy
polled at `GET /check_drift`. The bearer comes from
`digikey_bearer_token()`: `DIGICLAW_DIGIKEY_API_KEY` (or legacy
`DIGIKEY_API_KEY`) exchanged at `DIGIKEY_URL` (default
`http://127.0.0.1:8005`) → `POST /v1/oauth/token` for a JWT scoped to
`digiquant:backtest` + `digiquant:optimize`. No key → explicit
`drift_check_skipped` audit event (expected in dev). Drift detected →
`reoptimize_triggered`, then re-optimization requires `DIGIQUANT_DATA_DIR`
or a `reoptimize_skipped` event is logged. Every failure path emits an
audit event (`drift_check_failed`, `reoptimize_failed`) — nothing skips
silently.

Drift detection is **auth-blocked**, not logic-blocked: without a digikey
bearer the runner never reaches `/check_drift`. With a bearer and sufficient
Sharpe history (≥3 observations via backtests), ADDM may return
`drift_detected: true`.

## Monitors tick

The `web-watch-tick` agent (continuous, 60 s interval) drives digisearch's
scheduled web watches. `digiclaw.monitors_tick.run_due_monitors()` POSTs
`{DIGISEARCH_URL}/v1/monitors/tick` with a digikey service JWT (minted via
`digibase.service_auth.get_service_jwt` from `DIGICLAW_DIGIKEY_API_KEY`,
scoped to `digisearch:query`). Returns `{"runs": n, "failed": m}`.

Transport and auth failures **raise** — the scheduler persists them as the
agent's `last_status="error"` + `last_error`, never a silent successful tick.
The 120 s timeout bounds a hung digisearch server.

## Audit sinks and redaction

`digiclaw.audit.audit_log()` delegates to `digibase.audit.emit_event`, the
sole fleet-wide JSONL emitter. Behavior:

- **Default path:** `digiquant/results/audit/events.jsonl` (hardcoded relative
  path). Override with `AUDIT_LOG_PATH`. In Docker this is set to
  `/audit/events.jsonl`.
- **Parent directory creation:** `ensure_dir()` creates missing parents before
  the first write.
- **Append-only:** One JSON line per call, UTF-8, newline-terminated. Never
  deletes, overwrites, or truncates.
- **Redaction:** Payload keys containing `password`, `api_key`, `token`, or
  `secret` (case-insensitive substring match, recursive) are replaced with
  `"[REDACTED]"` before writing. Redaction is not optional — no fast path
  bypasses it.
- **AUDIT_SINK_URL:** If set, a fire-and-forget `POST` with `Content-Type:
  application/x-ndjson` mirrors the NDJSON line. Sink failures are swallowed
  (3 s timeout; local JSONL write already succeeded). Never let sink failures
  propagate.

Inspect with:

```bash
cat digiquant/results/audit/events.jsonl | head -20
```

## Scheduler

```bash
digiclaw schedule status # next-run visibility over digiclaw/agents/*.yaml
```

Lifecycle commands (`start`/`stop`/`pause`/`resume`) manage agent runtime
state. `digiclaw schedule tick` processes every due running agent once and
is idempotent — supervisors invoke it in a loop for continuous
`interval_seconds` schedules. `start` is idempotent while the agent is
already RUNNING (re-arms, exit 0); it exits 2 only on a real `SchedulerError`.

Three schedule modes are modeled:

| Mode | Trigger | Required field |
|------|---------|---------------|
| `cron` | Standard 5-field cron expression (`*/30 * * * *`) | `cron` |
| `continuous` | Loop with fixed sleep between ticks | `interval_seconds` (≥1) |
| `event` | Schema only; trigger wiring not implemented | `event_name` |

Agent YAML definitions live under `digiclaw/agents/` (or `DIGICLAW_AGENTS_DIR`).

### Scheduler state

Durable state persists at `{DIGI_WORKSPACE}/.digiclaw/scheduler_state.json`
(or `DIGICLAW_SCHEDULER_STATE`). In Docker this is
`/state/scheduler_state.json` on the `digiclaw_state` named volume.

Persistence is atomic: write JSON to a `.tmp` file, then `Path.replace()`.

State includes per-agent lifecycle (`stopped`/`running`/`paused`), `next_run_at`,
`last_run_at`, `last_status`, `last_error`, and `pending`. On process restart
(`restore()`), overdue running agents are re-queued (set `pending=True`).

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DIGIGRAPH_URL` | `http://127.0.0.1:8000` | Health ping target |
| `DIGIQUANT_URL` | `http://127.0.0.1:8001` | Health ping + drift/reoptimize target |
| `DIGISEARCH_URL` | `http://127.0.0.1:8002` | Monitor tick target |
| `DIGIKEY_URL` | `http://127.0.0.1:8005` | OAuth token exchange base |
| `DIGICLAW_DIGIKEY_API_KEY` | — | Machine API key for service JWT (falls back to `DIGIKEY_API_KEY`) |
| `REOPTIMIZE_STRATEGY` | `mean_reversion_tech` | Strategy ID for drift check |
| `DIGIQUANT_DATA_DIR` | — | Required for `POST /run_optimize` |
| `AUDIT_LOG_PATH` | `digiquant/results/audit/events.jsonl` | JSONL output path |
| `AUDIT_SINK_URL` | — | Optional remote NDJSON mirror (best-effort) |
| `DIGI_WORKSPACE` | `.` | Workspace root; used for `HEARTBEAT.md` lookup and scheduler state default |
| `DIGICLAW_AGENTS_DIR` | `digiclaw/agents` | Agent YAML directory |
| `DIGICLAW_SCHEDULER_STATE` | `{DIGI_WORKSPACE}/.digiclaw/scheduler_state.json` | Durable scheduler state path |

## Test commands

```bash
# Unit tests
pytest tests/ -m unit -k "digiclaw" -v

# Scheduler tests
pytest tests/dc/test_scheduler.py -v

# Audit tests
pytest tests/dc/test_audit.py -v

# Heartbeat tests
pytest tests/dc/test_heartbeat.py -v

# Monitors tick tests
pytest tests/dc/test_monitors_tick.py -v

# Lint
ruff check digiclaw/ && ruff format --check digiclaw/
```
