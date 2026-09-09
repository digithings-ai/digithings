---
type: operations-guide
title: digiclaw Operations
description: Running digiclaw — heartbeat loop, drift wiring, audit sinks, scheduler env, and container.
tags: [digiclaw, operations, heartbeat, audit]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-72050835d3541ab62444987d
    resource: repo://digiclaw/AGENTS.md
  - id: openwiki-source-431d9db0a509b4927d0cfbf7
    resource: repo://digiclaw/ARCHITECTURE.md
  - id: openwiki-source-89f82bf9acfe38c98e0f20b2
    resource: repo://digiclaw/Dockerfile
  - id: openwiki-source-a78d5139fbc45c09b4977f54
    resource: repo://digiclaw/src/digiclaw/digikey_auth.py
  - id: openwiki-source-03ae8e0b4a74134f450c8b0d
    resource: repo://digiclaw/src/digiclaw/heartbeat_runner.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digiclaw Operations

digiclaw runs as a Compose service wrapping the single-shot runner in a
shell loop, plus a separate `schedule` CLI for agent ticks. Everything it
touches is observable through the audit log.

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
digiclaw schedule status   # next-run visibility over digiclaw/agents/*.yaml
```

Lifecycle (`start`/`stop`/`pause`/`resume`) and isolated ticks persist
durable state; supervisors invoke `digiclaw schedule tick` for continuous
`interval_seconds` schedules.
