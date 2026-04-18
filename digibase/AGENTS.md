# Agent Guide: DigiBase

## Purpose

DigiBase is both a **shared Python library** (`digibase` package) installed in every service, and a **future data-plane broker service** (roadmap). Today only the library exists: it provides standardized JSON error envelopes, outbound HTTP correlation headers, audit payload redaction, and optional OpenTelemetry wiring. The library has no server, no port, and no persistent state.

---

## Read First

In this order, before writing any code:

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — library vs service distinction, full API surface, security analysis, phase roadmap
2. [`../AGENTS.md`](../AGENTS.md) — non-negotiable stack-wide rules
3. [`../ROADMAP.md`](../ROADMAP.md) — DigiBase data-plane service is Phase 2+; do not build it now
4. [`../docs/agent-backlog/INDEX.md`](../docs/agent-backlog/INDEX.md) — current task queue

---

## Pre-Flight Checklist

Before making any change to `digibase/`:

- [ ] Read `ARCHITECTURE.md` Section 1 (Role 1 vs Role 2 distinction) and Section 3 (API Surface)
- [ ] Run `pytest tests/ -m unit -k "digibase" -v` — passes before and after
- [ ] Run `ruff check digibase/ && ruff format --check digibase/` — zero errors
- [ ] Confirm no side effects at import time — all library functions must be pure or accept explicit parameters
- [ ] Confirm `ApiErrorEnvelope` shape is unchanged (or versioned) — every service depends on this error structure
- [ ] Confirm `outbound_service_headers()` does not log or retain bearer tokens
- [ ] Confirm OTel wiring remains behind `digibase[otel]` optional extra — do not make it a hard dependency

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **Library is side-effect-free on import**: No threads, no sockets, no file writes at import time. All functions are pure or accept explicit parameters.
- **Do not build the data-plane service**: The `DigiBase` broker service (credential vending, quota enforcement, Postgres/Redis handle brokering) is Phase 2+. Do not stub, scaffold, or add HTTP endpoints to `digibase/` without explicit scope.
- **`ApiErrorEnvelope` is a contract**: Every service uses `json_error_response()` and parses `{"error": {"code", "message", "request_id", "service"}}`. Field renames or type changes are fleet-wide breaking changes.
- **OTel stays optional**: `digibase[otel]` is an optional extra. The base package must install and function without any OTel packages present.
- **No secrets in headers helper output**: `outbound_service_headers()` accepts a bearer token argument — it must never log it, cache it, or include it in error messages.
- **Audit redaction patterns are additive**: When adding new redaction patterns to `audit.py`, only add — never remove or narrow existing patterns.
- **No pandas**: Polars-only rule applies even in a utility library.

---

## Test Commands

```bash
# Unit tests (no stack required)
pytest tests/ -m unit -k "digibase" -v

# Single test file
pytest tests/digibase/test_errors.py -v

# Full unit suite
make test-unit

# Lint
ruff check digibase/ && ruff format --check digibase/

# Verify library installs cleanly (no optional extras)
pip install -e digibase/ --dry-run
```

---


---

## More

Extension patterns, anti-patterns, and integration boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc when changing interfaces or behavior.
