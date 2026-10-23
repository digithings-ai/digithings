---
type: quickstart
title: digibot Quickstart
description: Run a digibot heartbeat cycle, inspect the audit log, check scheduler and web-watch-tick status, and run unit gates.
tags: [digibot, quickstart, heartbeat]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
sources:
  - id: openwiki-source-72050835d3541ab62444987d
    resource: repo://digibot/AGENTS.md
  - id: openwiki-source-8e060f8c1849eeb359de3487
    resource: repo://digibot/agents/web-watch-tick.yaml
  - id: openwiki-source-431d9db0a509b4927d0cfbf7
    resource: repo://digibot/ARCHITECTURE.md
  - id: openwiki-source-8b4ee7822ae07e223005983d
    resource: repo://digibot/src/digibot/cli.py
  - id: openwiki-source-76fe85e1283b473010f98f63
    resource: repo://digibot/src/digibot/monitors_tick.py
  - id: openwiki-source-3c35a18a896912fa07b94ee5
    resource: repo://digibot/src/digibot/scheduler.py
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
---

# digibot Quickstart

digibot is a CLI with no port and no HTTP server: a single-shot
heartbeat, an append-only audit log, and an agent scheduler. The gateway
vision (channels, sessions, WebSocket plane) is deferred — what you can
run today is below.

## 1. Heartbeat

```bash
make up # stack with digigraph + digiquant up
python -m digibot # one cycle, exits 0 on clean completion
# or: digibot heartbeat
```

One cycle pings digigraph/digiquant health, attempts the drift check (logs
`drift_check_skipped` without a digikey bearer — normal in dev), and
writes a `heartbeat` audit event.

## 2. Audit log

```bash
cat digiquant/results/audit/events.jsonl | head -20
```

## 3. Scheduler and web-watch-tick

```bash
digibot schedule status                  # list agents, lifecycle, next runs
digibot schedule start web-watch-tick    # activate the continuous 60s ticker
digibot schedule status                  # confirm RUNNING with next_run_at
```

The `web-watch-tick` agent (defined in `digibot/agents/web-watch-tick.yaml`)
defaults to `stopped` even though `enabled: true` is set. `digibot schedule
start web-watch-tick` sets it to `RUNNING` with an immediate pending tick;
subsequent `digibot schedule tick` invocations POST `/v1/monitors/tick` to
digisearch every 60 seconds. `schedule start` is idempotent when the agent is
already RUNNING (re-arms, exit 0).

## 4. Unit gates

```bash
pytest tests/dc -m unit -v               # unit tests
ruff check digibot/ && ruff format --check digibot/
```

## Where next

- [digibot Architecture](/openwiki/digibot/architecture.md) — runner,
  audit, scheduler, deferred scope.
- [digibot Operations](/openwiki/digibot/operations.md) — loop, drift
  wiring, sinks, redaction.
