---
type: quickstart
title: digiclaw Quickstart
description: Run a digiclaw heartbeat cycle, inspect the audit log, and check scheduler status.
tags: [digiclaw, quickstart, heartbeat]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-19T12:20:11.463Z
sources:
  - id: openwiki-source-72050835d3541ab62444987d
    resource: repo://digiclaw/AGENTS.md
  - id: openwiki-source-431d9db0a509b4927d0cfbf7
    resource: repo://digiclaw/ARCHITECTURE.md
generated: { by: "openwiki/0.5.0", at: "2026-09-19T12:20:11.463Z" }
---

# digiclaw Quickstart

digiclaw is a CLI with no port and no HTTP server: a single-shot
heartbeat, an append-only audit log, and an agent scheduler. The gateway
vision (channels, sessions, WebSocket plane) is deferred — what you can
run today is below.

## 1. Heartbeat

```bash
make up           # stack with digigraph + digiquant up (no heartbeat)
make up-heartbeat # alternative: Docker profile with heartbeat loop + scheduler tick
python -m digiclaw # one cycle, exits 0 when all services healthy, 1 otherwise
# or: digiclaw heartbeat
```

One cycle does three things in sequence:

1. **Health pings** — GETs `{DIGIGRAPH_URL}/health` and
   `{DIGIQUANT_URL}/health` (5 s timeout each), writes a `heartbeat`
   audit event with per-service `OK`/detail fields.
2. **Drift check** — calls digiquant `/check_drift` with a digikey bearer
   when available. Without a bearer, logs `drift_check_skipped` (normal in
   dev). With auth and ≥3 Sharpe observations, may detect drift and trigger
   re-optimization.
3. **HEARTBEAT.md presence check** — if `HEARTBEAT.md` exists at
   `DIGI_WORKSPACE`, logs `heartbeat_checklist_seen`.

**Exit codes:** 0 when all health pings succeed, 1 if any service is
unhealthy (REM-073).

```bash
# Run from repo root with stack up
export DIGIGRAPH_URL=http://127.0.0.1:8000
export DIGIQUANT_URL=http://127.0.0.1:8001
export AUDIT_LOG_PATH=./digiquant/results/audit/events.jsonl
python -m digiclaw
```

## 2. Audit log

```bash
cat digiquant/results/audit/events.jsonl | head -20
```

The audit log is append-only JSONL, written via `digibase.audit.emit_event`.
Keys containing `password`, `api_key`, `token`, or `secret` are redacted
to `[REDACTED]` before writing. Override the path with `AUDIT_LOG_PATH`.
An optional `AUDIT_SINK_URL` mirrors each line via fire-and-forget POST
(failures are silently swallowed).

## 3. Scheduler and gates

```bash
digiclaw schedule status           # next-run visibility over digiclaw/agents/*.yaml
digiclaw schedule start <agent>    # start a scheduled agent (idempotent)
digiclaw schedule stop <agent>     # stop an agent
digiclaw schedule pause <agent>    # pause a running agent
digiclaw schedule resume <agent>   # resume a paused agent
digiclaw schedule tick             # process due jobs once (for tests / supervisors)
```

Agent definitions live in `digiclaw/agents/` as YAML files with three
schedule modes: `cron` (5-field expression), `continuous`
(`interval_seconds`), and `event` (schema-only). The `web-watch-tick`
agent (continuous, 60 s) drives digisearch's scheduled web watches by
posting `POST /v1/monitors/tick`.

Scheduler state persists at `{DIGI_WORKSPACE}/.digiclaw/scheduler_state.json`
(or `DIGICLAW_SCHEDULER_STATE`) via atomic write — durable across restarts.

```bash
pytest tests/dc -m unit -v                           # unit tests
ruff check digiclaw/ && ruff format --check digiclaw/ # lint
```

## Where next

- [digiclaw Architecture](/openwiki/digiclaw/architecture.md) — runner,
  audit, scheduler, monitors-tick integration, and deferred scope.
- [digiclaw Operations](/openwiki/digiclaw/operations.md) — loop, drift
  wiring, sinks, redaction, Docker container, and environment variables.
