---
type: quickstart
title: digiclaw Quickstart
description: Run a digiclaw heartbeat cycle, inspect the audit log, check scheduler and web-watch-tick status, and run unit gates.
tags: [digiclaw, quickstart, heartbeat]
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
  - id: openwiki-source-8b4ee7822ae07e223005983d
    resource: repo://digiclaw/src/digiclaw/cli.py
  - id: openwiki-source-76fe85e1283b473010f98f63
    resource: repo://digiclaw/src/digiclaw/monitors_tick.py
  - id: openwiki-source-3c35a18a896912fa07b94ee5
    resource: repo://digiclaw/src/digiclaw/scheduler.py
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
---

# digiclaw Quickstart

digiclaw is a CLI with no port and no HTTP server: a single-shot
heartbeat, an append-only audit log, and an agent scheduler. The gateway
vision (channels, sessions, WebSocket plane) is deferred — what you can
run today is below.

## 1. Heartbeat

```bash
make up # stack with digigraph + digiquant up
python -m digiclaw # one cycle, exits 0 on clean completion
# or: digiclaw heartbeat
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
digiclaw schedule status                  # list agents, lifecycle, next runs
digiclaw schedule start web-watch-tick    # activate the continuous 60s ticker
digiclaw schedule status                  # confirm RUNNING with next_run_at
```

The `web-watch-tick` agent (defined in `digiclaw/agents/web-watch-tick.yaml`)
defaults to `stopped` even though `enabled: true` is set. `digiclaw schedule
start web-watch-tick` sets it to `RUNNING` with an immediate pending tick;
subsequent `digiclaw schedule tick` invocations POST `/v1/monitors/tick` to
digisearch every 60 seconds. `schedule start` is idempotent when the agent is
already RUNNING (re-arms, exit 0).

## 4. Unit gates

```bash
pytest tests/dc -m unit -v               # unit tests
ruff check digiclaw/ && ruff format --check digiclaw/
```

## Where next

- [digiclaw Architecture](/openwiki/digiclaw/architecture.md) — runner,
  audit, scheduler, deferred scope.
- [digiclaw Operations](/openwiki/digiclaw/operations.md) — loop, drift
  wiring, sinks, redaction.
