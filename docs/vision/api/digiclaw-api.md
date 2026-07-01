---
title: "digiclaw — API reference"
type: reference
status: generated
created: 2026-06-29
tags:
  - api
  - support
relevance:
  - digiclaw
---
# digiclaw — API reference

> The always-on agent runtime — heartbeats, scheduling, immutable audit.

**Role:** Always-on runtime · heartbeat · audit · **Tier:** support

## Overview
A heartbeat service that keeps agents running: Atlas runner scheduling and drift detection, calling digigraph over HTTP on an interval.

Every action lands in an immutable audit log, and it runs no LLM of its own.

## Authentication
CLI-only — no HTTP service. A heartbeat runner pings service health and appends an immutable audit log.


## Run locally
```bash
python -m digiclaw            # one cycle
docker compose --profile heartbeat up -d heartbeat
```

## Configuration
- `DIGIGRAPH_URL`: DigiGraph base URL for health checks.
- `DIGIQUANT_URL`: DigiQuant base URL for health + drift checks.
- `DIGICLAW_DIGIKEY_API_KEY`: Key (digiquant:backtest+optimize) for auth-gated drift checks.
- `AUDIT_LOG_PATH` (default `digiquant/results/audit/events.jsonl`): Append-only JSONL audit destination.
- `REOPTIMIZE_STRATEGY` (default `mean_reversion_tech`): Strategy id for the drift check.

## Public interface
- `python -m digiclaw` — Run one heartbeat cycle: health-check services, run an auth-gated drift check, and (on drift) trigger re-optimization.
- `audit_log(event_type, agent_id, payload)` — Append one redacted JSON line to the audit log.

## Notes
- Audit event types: heartbeat, reoptimize_triggered, reoptimize_completed, reoptimize_failed, drift_check_skipped.
- Keys matching password / api_key / token / secret are redacted before write.

## Stack
HTTPx, digibase

## Related
digiquant, digismith

## Links
- [Source](https://github.com/digithings-ai)

See also [[digiclaw]].
