# Agent Guide: DigiSmith

## Purpose

DigiSmith provides the observability layer for the DigiThings stack. As a **library** (`digismith.trace`, `digismith.config`), it wraps LangSmith tracing for every service via a single decorator. As an **HTTP microservice** (port 8003), it exposes read-only status endpoints that tell orchestrators whether tracing is active — without ever surfacing a secret.

---

## Read First

In this order, before writing any code:

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — full implementation state, API surface, security analysis, gap analysis, and PII risks
2. [`../AGENTS.md`](../AGENTS.md) — non-negotiable stack-wide rules
3. [`../ROADMAP.md`](../ROADMAP.md) — Phase 2 observability platform (PII redaction middleware, Prometheus export, custom samplers) is deferred; do not build it now
4. [`../docs/agent-backlog/INDEX.md`](../docs/agent-backlog/INDEX.md) — current task queue

---

## Pre-Flight Checklist

Before making any change to `digismith/`:

- [ ] Read `ARCHITECTURE.md` Section 2 (Implementation State) and Section 4 (Security Analysis)
- [ ] Run `pytest tests/ -m unit -k "digismith" -v` — passes before and after
- [ ] Run `ruff check digismith/ && ruff format --check digismith/` — zero errors
- [ ] Confirm `GET /v1/status` response contains **no secrets** — no API keys, no full `LANGSMITH_ENDPOINT` URL, no credentials
- [ ] Confirm any new span attribute does not carry raw prompt text, full document bodies, or bearer tokens
- [ ] Confirm `traceable()` decorator gracefully no-ops when `LANGSMITH_API_KEY` is absent
- [ ] Confirm the library remains importable with zero mandatory non-stdlib deps beyond `pydantic` and `fastapi`

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **No PII in spans**: Span attributes must never carry raw prompts, API keys, full document bodies, or bearer tokens. Permitted: `workflow_id`, `request_id`, `session_id`, model names, counts, latency, error codes.
- **Status endpoint stays secret-free**: `GET /v1/status` exposes only boolean flags and the hostname of `LANGSMITH_ENDPOINT` (no path, no credentials). Any change must preserve this contract.
- **Library is side-effect-free on import**: `digismith.trace` and `digismith.config` must not start threads, open sockets, or write files at import time.
- **No-op fallback is not optional**: `traceable()` must return the unmodified function when LangSmith is not configured. Tests that run without `LANGSMITH_API_KEY` must still pass.
- **LangSmith SDK is a soft optional**: Do not move `langsmith` from `[langsmith]` extra to a hard dependency. Services that don't need tracing must not pay the install cost.
- **Do not add a database or background worker**: DigiSmith is stateless by design. Phase 2 observability platform additions belong in a separate scoped task.
- **`/v1/status/detailed` is deferred**: Do not implement this endpoint — it is a placeholder listed in `ARCHITECTURE.md` Section 11. Leave it until Phase 2 is explicitly scoped.

---

## Test Commands

```bash
# Unit tests (no stack required)
pytest tests/ -m unit -k "digismith" -v

# Single test file
pytest tests/digismith/test_trace.py -v

# Full unit suite
make test-unit

# Lint
ruff check digismith/ && ruff format --check digismith/

# Stack smoke test (requires make up)
curl -s http://localhost:8003/health
curl -s http://localhost:8003/v1/status
```

---


---

## More

Extension patterns, anti-patterns, and integration boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc when changing interfaces or behavior.
