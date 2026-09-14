---
type: quickstart
title: digiclaw Quickstart
description: Run a digiclaw heartbeat cycle, inspect the audit log, and check scheduler status.
tags: [digiclaw, quickstart, heartbeat]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
sources:
  - id: openwiki-source-72050835d3541ab62444987d
    resource: repo://digiclaw/AGENTS.md
  - id: openwiki-source-431d9db0a509b4927d0cfbf7
    resource: repo://digiclaw/ARCHITECTURE.md
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digiclaw Quickstart

digiclaw is a CLI with no port and no HTTP server: a single-shot
heartbeat, an append-only audit log, and an agent scheduler. The gateway
vision (channels, sessions, WebSocket plane) is deferred — what you can
run today is below.

## 1. Heartbeat

```bash
make up               # stack with digigraph + digiquant up
python -m digiclaw    # one cycle, exits 0 on clean completion
# or: digiclaw heartbeat
```

One cycle pings digigraph/digiquant health, attempts the drift check (logs
`drift_check_skipped` without a digikey bearer — normal in dev), and
writes a `heartbeat` audit event.

## 2. Audit log

```bash
cat digiquant/results/audit/events.jsonl | head -20
```

## 3. Scheduler and gates

```bash
digiclaw schedule status          # next-run visibility
pytest tests/dc -m unit -v        # unit tests
ruff check digiclaw/ && ruff format --check digiclaw/
```

## Where next

- [digiclaw Architecture](/openwiki/digiclaw/architecture.md) — runner,
  audit, scheduler, deferred scope.
- [digiclaw Operations](/openwiki/digiclaw/operations.md) — loop, drift
  wiring, sinks, redaction.
