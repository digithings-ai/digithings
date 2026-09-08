---
type: service-architecture
title: digiclaw Architecture
description: Design of the digiclaw gateway layer — single-shot heartbeat runner, append-only JSONL audit, and agent scheduler, with deferred gateway scope.
tags: [digiclaw, heartbeat, audit, scheduler]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-72050835d3541ab62444987d
    resource: repo://digiclaw/AGENTS.md
  - id: openwiki-source-431d9db0a509b4927d0cfbf7
    resource: repo://digiclaw/ARCHITECTURE.md
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digiclaw Architecture

digiclaw is the intended user-facing gateway and runtime layer of the
digithings stack. As built (Phase 3), it ships three implemented concerns
— a heartbeat runner, a JSONL audit log, and an agent scheduler — as a
**CLI with no HTTP server of its own**. Channel adapters (Slack, Discord,
Telegram, WhatsApp), session/queue managers, the WebSocket control plane,
and the `run_digigraph_workflow` skill runtime are explicitly deferred.

## Heartbeat runner

`python -m digiclaw` (or `digiclaw heartbeat`) executes **one cycle and
exits 0** on clean completion. One cycle GETs `{DIGIGRAPH_URL}/health` and
`{DIGIQUANT_URL}/health` (5s timeout), calls digiquant `GET /check_drift`
with a digikey bearer when available, triggers re-optimization on reported
drift, and logs one `heartbeat` audit event with per-service status. The
Docker loop (`while true; do python -m digiclaw; sleep 1800; done`) lives
outside the runner — no daemon loop inside.

## JSONL audit

`digiclaw.audit.audit_log()` is a thin wrapper over
`digibase.audit.emit_event`: append-only structured lines, never delete or
truncate. Four key patterns (`password`, `api_key`, `token`, `secret`)
redact to `[REDACTED]` before writing — no fast-path bypass. An optional
`AUDIT_SINK_URL` POST is best-effort: failures are swallowed, never
propagated.

## Agent scheduler

`digiclaw schedule …` owns agent lifecycle (`start`/`stop`/`pause`/`resume`)
over YAML definitions in `digiclaw/agents/`, with 5-field cron parsing,
next-fire calculation, durable tick state, and `schedule status` for
next-run visibility. Continuous mode is `interval_seconds` between isolated
ticks via `digiclaw schedule tick`. Event-triggered runs are schema-only.

## Explicitly not built

OpenClaw runtime, channel adapters, session/queue managers, WebSocket
control plane, skill execution, full agent registry (#217), durable ADDM
history across restarts (in-process deque today), and any REST surface —
adding an HTTP server requires its own scoped task covering auth, loopback
binding, and scopes.

## Representative tests

`tests/dc/`: audit append/redaction behavior, scheduler lifecycle and cron,
heartbeat cycle with drift-check skipped semantics when no bearer is
configured.
