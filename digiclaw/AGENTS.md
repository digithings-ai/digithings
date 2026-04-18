# Agent Guide: DigiClaw

## Purpose

DigiClaw is the heartbeat, audit, and gateway layer of DigiThings. Today it ships two implemented concerns: a single-shot **heartbeat runner** that pings DigiGraph and DigiQuant health endpoints and logs results, and an **append-only JSONL audit log** consumed by every service in the stack. The OpenClaw gateway (Slack/Discord/Telegram adapters, session manager, WebSocket control plane) is deferred to a future phase.

---

## Read First

In this order, before writing any code:

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — full implementation state, heartbeat behaviour, audit log behaviour, security analysis, what is NOT implemented today
2. [`../AGENTS.md`](../AGENTS.md) — non-negotiable stack-wide rules
3. [`../ROADMAP.md`](../ROADMAP.md) — OpenClaw gateway and channel adapters are deferred; do not implement them
4. [`../docs/agent-backlog/INDEX.md`](../docs/agent-backlog/INDEX.md) — current task queue

---

## Pre-Flight Checklist

Before making any change to `digiclaw/`:

- [ ] Read `ARCHITECTURE.md` Section 2 (Implementation State) and Section 3 (API Surface)
- [ ] Run `pytest tests/ -m unit -k "digiclaw" -v` — passes before and after
- [ ] Run `ruff check digiclaw/ && ruff format --check digiclaw/` — zero errors
- [ ] Confirm `audit_log()` redaction is not weakened — keys containing `password`, `api_key`, `token`, `secret` must be `[REDACTED]`
- [ ] Confirm `AUDIT_SINK_URL` POST failure is silently swallowed (fire-and-forget) — do not let it crash the heartbeat
- [ ] Confirm no new HTTP server is added to DigiClaw without explicit Phase 2 scope
- [ ] Confirm drift detection stub still returns `{"drift_detected": false}` and no code relies on it being true

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **Audit log is append-only**: `audit_log()` must never delete, overwrite, or truncate existing entries. Parent directory creation is safe; rotation is not implemented and must not be added without explicit scope.
- **Redaction is not optional**: The four key patterns (`password`, `api_key`, `token`, `secret`) must always be redacted before writing. Never bypass redaction in a "fast path."
- **ADDM stub is not real drift detection**: `/check_drift` on DigiQuant always returns `false`. Do not write logic that depends on drift being detected — it will never fire in practice.
- **No HTTP server without scope**: DigiClaw has no REST API of its own. Do not add one without a Phase 2 task that covers auth, loopback binding, and scope enforcement.
- **Heartbeat is single-shot**: `python -m digiclaw` runs one cycle and exits. The Docker loop (`while true; do python -m digiclaw; sleep 1800; done`) is external. Do not add a daemon loop inside the Python module.
- **AUDIT_SINK_URL is best-effort**: Any exception from the remote POST must be caught and swallowed. Never let audit sink failures propagate to the caller.
- **No channel adapters**: Do not add Slack, Discord, Telegram, or WhatsApp integration. That is OpenClaw scope, Phase 2+.

---

## Test Commands

```bash
# Unit tests (no stack required)
pytest tests/ -m unit -k "digiclaw" -v

# Single test file
pytest tests/digiclaw/test_audit.py -v

# Full unit suite
make test-unit

# Lint
ruff check digiclaw/ && ruff format --check digiclaw/

# Manual heartbeat run (requires stack up)
make up
python -m digiclaw

# Inspect audit log
cat digiquant/results/audit/events.jsonl | head -20
```

---


---

## More

Extension patterns, anti-patterns, and integration boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc when changing interfaces or behavior.
