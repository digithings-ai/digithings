# DigiClaw Architecture

**Component:** DigiClaw — Gateway, Heartbeat, and Audit Layer
**Status:** Phase 3 (heartbeat + audit implemented); OpenClaw gateway deferred
**Last updated:** 2026-03-29

---

## 1. Overview

DigiClaw is the intended user-facing gateway and runtime layer for the DigiThings stack. Its full vision encompasses a persistent, multi-channel interface (Slack, Discord, Telegram, WhatsApp), session and queue management, a WebSocket control plane, and a self-healing loop driven by ADDM drift detection. In practice, as of Phase 3, only two concerns are implemented:

1. **Heartbeat runner** — a single-shot Python script that pings DigiGraph and DigiQuant health endpoints, checks for strategy drift via a stub ADDM endpoint, and logs results to the JSONL audit file.
2. **JSONL audit log** — an append-only structured log consumed by any component that imports `digiclaw.audit.audit_log`.

Everything else in scope for DigiClaw — a persistent gateway runtime with channel adapters, session manager, queue manager, WebSocket control plane, and MCP skill integration — is deferred. The `digiclaw/skills/README.md` defines the `run_digigraph_workflow` skill contract as a Phase 0 placeholder; no runtime implements it yet.

**What is NOT implemented today:**
- OpenClaw Node.js runtime (any version)
- Channel adapters (Slack, Discord, Telegram, WhatsApp)
- Session manager and queue manager
- WebSocket control plane
- `run_digigraph_workflow` MCP skill execution
- Full ADDM drift detection (stub only — always returns no drift)
- Any HTTP API or REST health endpoint for DigiClaw itself

---

## 2. Current Implementation State

### Source files

| File | Role |
|------|------|
| `digiclaw/__init__.py` | Package stub; one-line comment noting OpenClaw integration is deferred |
| `digiclaw/__main__.py` | Entry point: imports `heartbeat_runner.main` and calls it via `raise SystemExit(main())` |
| `digiclaw/heartbeat_runner.py` | Single-cycle heartbeat: pings `/health` on DigiGraph and DigiQuant, calls stub ADDM, triggers re-optimization when drift is reported, writes `HEARTBEAT.md` checklist-seen event |
| `digiclaw/audit.py` | `audit_log()` function: appends one JSONL line per call; optionally POSTs a copy to `AUDIT_SINK_URL` |
| `digiclaw/skills/README.md` | Skill contract definition for `run_digigraph_workflow` (Phase 0 contract only, no implementation) |
| `HEARTBEAT.md` (repo root) | Checklist document read by the heartbeat agent; documents four check categories and the 7-day unattended run milestone |

### Heartbeat runner behaviour

`python -m digiclaw` executes one cycle and exits with code 0 if it completes without an unhandled exception. In Docker, the heartbeat service wraps this in a shell loop:

```
while true; do python -m digiclaw; sleep 1800; done
```

One cycle does the following in sequence:

1. `run_heartbeat()` — HTTP GET to `{DIGIGRAPH_URL}/health` and `{DIGIQUANT_URL}/health` with a 5-second timeout; logs one `heartbeat` audit event with per-service OK/detail fields.
2. `_check_drift_and_reoptimize()` — HTTP GET to `{DIGIQUANT_URL}/check_drift?strategy_id=<REOPTIMIZE_STRATEGY>`; if `drift_detected` is true in the response body, logs `reoptimize_triggered`, then POSTs to `{DIGIQUANT_URL}/run_optimize`; logs `reoptimize_completed` or `reoptimize_failed`.
3. `HEARTBEAT.md` presence check — if the file exists at `{DIGI_WORKSPACE}/HEARTBEAT.md`, logs `heartbeat_checklist_seen`.

The current DigiQuant stub at `/check_drift` always returns `{"drift_detected": false}`, so steps 2b–2c never execute in practice.

### Audit log behaviour

`audit_log()` in `digiclaw/audit.py`:
- Creates parent directories if missing (`Path.mkdir(parents=True, exist_ok=True)`).
- Writes one JSON line per call, UTF-8 encoded, newline-terminated.
- Default path: `digiquant/results/audit/events.jsonl` (overridden by `AUDIT_LOG_PATH`).
- Redacts payload keys containing `password`, `api_key`, `token`, or `secret` (case-insensitive substring match) by replacing values with `"[REDACTED]"`.
- If `AUDIT_SINK_URL` is set, makes a fire-and-forget `POST` with `Content-Type: application/x-ndjson`; any exception is silently swallowed (`except Exception: pass`).

---

## 3. API Surface

### Today

| Surface | Description |
|---------|-------------|
| `python -m digiclaw` | CLI entry point; runs one heartbeat cycle and exits |
| `AUDIT_LOG_PATH` (JSONL file) | Append-only event log written by all components that import `digiclaw.audit` |
| `AUDIT_SINK_URL` (HTTP POST) | Optional remote audit mirror (NDJSON); best-effort, no auth, no retry |

DigiClaw has **no HTTP server of its own**. It only calls outbound HTTP (DigiGraph `/health`, DigiQuant `/health`, DigiQuant `/check_drift`, DigiQuant `/run_optimize`, optional `AUDIT_SINK_URL`).

### Planned (deferred)

| Surface | Description |
|---------|-------------|
| OpenClaw Node.js gateway | WebSocket control plane, REST health endpoints, skill invocation surface |
| `run_digigraph_workflow` MCP skill | POST `{DIGIGRAPH_URL}/workflow` with user prompt; return result in chat |
| Channel adapter webhooks | Slack Events API, Discord interactions, Telegram webhook, WhatsApp cloud API |
| REST health endpoint | `GET /health` for gateway liveness (not yet implemented) |

---

## 4. Data Model

### Audit event (JSONL)

Every line written by `audit_log()` is a JSON object with the following schema:

```
{
  "ts":         "<ISO-8601 UTC timestamp>",       // always present
  "event_type": "<string>",                        // always present
  "agent_id":   "<string>",                        // always present (may be empty)
  "payload":    { ... },                           // always present (may be empty dict)
  "key_prefix": "<string>",                        // optional; DigiKey correlation
  "tenant":     "<string>",                        // optional; DigiKey correlation
  "project_id": "<string>",                        // optional; DigiKey correlation
  "jti":        "<string>",                        // optional; DigiKey JWT ID
  "path":       "<string>"                         // optional; HTTP path that triggered the event
}
```

Optional fields are omitted entirely when empty; they are not written as `null`.

### Heartbeat event payload

For `event_type = "heartbeat"`, the `payload` object contains:

```
{
  "digigraph_url":    "<string>",
  "digigraph_ok":     <bool>,
  "digigraph_detail": "<string>",   // HTTP status code or error reason
  "digiquant_url":    "<string>",
  "digiquant_ok":     <bool>,
  "digiquant_detail": "<string>"
}
```

### ADDM-triggered re-optimization events

| `event_type` | `payload` keys |
|---|---|
| `reoptimize_triggered` | `strategy_id`, `reason` (always `"addm_drift"`) |
| `reoptimize_completed` | `run_id` |
| `reoptimize_failed` | `error` |
| `reoptimize_skipped` | `error` (e.g. `"DIGIQUANT_DATA_DIR required"`) |

### DigiKey correlation fields

When DigiGraph validates a JWT and emits an audit event, it may pass `key_prefix`, `tenant`, `project_id`, and `jti` into `audit_log()`. These fields allow post-hoc correlation of audit lines with the issuing API key or JWT without embedding the full token. The heartbeat runner does not currently populate these fields.

---

## 5. Internal Architecture

### Heartbeat runner loop

```
[cron / Docker shell loop]
        |
        | every 1800s
        v
  python -m digiclaw
        |
        v
  heartbeat_runner.main()
        |
        +-- run_heartbeat()   [return value dict discarded by main()]
        |       |-- HTTP GET {DIGIGRAPH_URL}/health  (timeout 5s)
        |       |-- HTTP GET {DIGIQUANT_URL}/health  (timeout 5s)
        |       `-- audit_log("heartbeat", ...)
        |
        +-- _check_drift_and_reoptimize()
        |       |-- HTTP GET {DIGIQUANT_URL}/check_drift?strategy_id=...  (timeout 5s)
        |       |   [stub: always returns drift_detected=false]
        |       |-- if drift_detected:
        |       |       audit_log("reoptimize_triggered", ...)
        |       |       HTTP POST {DIGIQUANT_URL}/run_optimize  (timeout 60s)
        |       |       audit_log("reoptimize_completed" | "reoptimize_failed", ...)
        |       `-- if not drift_detected: return (no-op)
        |
        `-- HEARTBEAT.md presence check
                `-- if file exists: audit_log("heartbeat_checklist_seen", ...)
```

### Audit event flow

```
Any component (digiclaw / digigraph / digiquant)
        |
        v
  audit_log(event_type, agent_id, payload, ...)
        |
        +-- redact secrets in payload (key substring match)
        +-- build event dict with ts, event_type, agent_id, payload, optional DigiKey fields
        +-- open(AUDIT_LOG_PATH, "a") → write JSON line + "\n"
        |
        `-- if AUDIT_SINK_URL:
                HTTP POST AUDIT_SINK_URL (timeout 3s, swallow exception)
```

There is no queue, no buffer, and no batching. Each call opens, appends, and closes the file. Concurrent writes from multiple processes to the same path are subject to OS-level append atomicity (safe on Linux ext4/XFS but not guaranteed on all network filesystems).

### HEARTBEAT.md-driven checklist

`HEARTBEAT.md` in the repo root defines four check categories: service health, portfolio/strategy drift, security, and macro/data. The heartbeat runner does not parse the checklist; it only tests whether the file exists at `{DIGI_WORKSPACE}/HEARTBEAT.md` and logs a `heartbeat_checklist_seen` event. All actual checklist logic is encoded in Python, not driven from the Markdown file. The file functions as documentation and a human-readable record of intent, not as executable configuration.

### ADDM detection (stub to planned)

The current `_check_drift_and_reoptimize()` function calls DigiQuant's `/check_drift` endpoint and acts on the response. The DigiQuant stub implementation always returns `{"drift_detected": false}`. No statistical computation occurs anywhere in the codebase today. The re-optimization pathway is wired correctly — if a real ADDM implementation returns `drift_detected: true`, the heartbeat runner will immediately POST to `/run_optimize` with a hardcoded symbol list (`["AAPL", "MSFT", "GOOGL"]`). See Section 12 for a redesign recommendation.

---

## 6. Security Analysis

### Current posture

**Loopback-only by default.** All service ports in `docker-compose.yml` are bound to `127.0.0.1`. The heartbeat container has no published port at all. There is no DigiClaw-owned network surface to attack remotely in the current implementation.

**No public interface.** DigiClaw makes only outbound HTTP calls to DigiGraph and DigiQuant on the internal Docker network (`http://digigraph:8000`, `http://digiquant:8001`). It does not listen on any port.

**Audit log append-only.** The audit file is opened with `"a"` mode (append). There is no delete or overwrite path in `audit.py`. The Docker heartbeat service mounts the audit directory as a writable volume (`./digiquant/results/audit:/audit`); the workspace is mounted read-only (`.:/workspace:ro`).

**Secret redaction.** `audit_log()` redacts payload keys containing `password`, `api_key`, `token`, or `secret` by case-insensitive substring match before writing to disk or forwarding to `AUDIT_SINK_URL`. This protects against accidental inclusion of credentials in heartbeat payloads.

**Filesystem least privilege.** The heartbeat Docker container mounts the workspace read-only. It only requires write access to the audit volume. No broker keys, LiteLLM master keys, or DigiKey secrets are passed to the heartbeat environment by default.

**Human gates.** `SECURITY.md` mandates explicit user confirmation for all irreversible actions (live trades, fund transfers, email sends). The current stub ADDM implementation never triggers re-optimization, so no automated irreversible action is possible. When ADDM is fully implemented, the re-optimization pathway (backtesting and optimizer invocation) must remain behind a human gate before any live execution.

### OpenClaw CVE-2026-25253 context

CVE-2026-25253 disclosed a one-click RCE pathway in the OpenClaw runtime: a malicious web page could pivot through a victim's browser tab to exfiltrate the gateway's auth token and achieve remote code execution on the host. Since DigiClaw does not yet run OpenClaw, this CVE does not affect the current codebase. However, it is the primary reason `SECURITY.md` mandates container isolation, loopback-only binding, and Tailscale/Cloudflare Tunnel for any remote access before OpenClaw integration proceeds.

### ClawHavoc campaign context

The ClawHavoc campaign identified over 800 malicious skills in the public ClawHub registry (approximately 20% of the marketplace), many delivering the Atomic macOS Stealer (AMOS). DigiClaw's `digiclaw/skills/README.md` defines a custom `run_digigraph_workflow` skill. This skill must be implemented as a local, internally-audited skill — never sourced from ClawHub or any third-party registry — when OpenClaw integration proceeds.

### Hardened deployment requirements

Per `SECURITY.md`:
- Run the gateway in an isolated container or VM with no host-network access.
- Bind only to loopback; use Tailscale or Cloudflare Tunnel for remote access.
- Apply AppArmor or seccomp profiles to restrict syscalls available to the gateway container.
- DigiKey JWTs (not static API keys) must authenticate all service-to-service calls.
- MCP tools exposed by DigiQuant are read-only by default; no MCP skill may have fund-transfer rights without human gate configuration.

### Audit sink risk

`AUDIT_SINK_URL` is posted to without authentication headers. Any secret that survives the redaction step (e.g., a key whose name does not contain `password`, `api_key`, `token`, or `secret`) would be transmitted in plaintext to an arbitrary URL. Operators must ensure `AUDIT_SINK_URL` uses HTTPS, and consider adding bearer auth support before enabling this in production.

---

## 7. Scalability Analysis

### Single-instance heartbeat runner

The heartbeat runner is a single-process, single-threaded Python script with no horizontal scaling mechanism. One instance per deployment is both the current reality and the intended design for the monitoring use case. There is no distributed locking, no leader election, and no consensus protocol. Running multiple instances against the same `AUDIT_LOG_PATH` would produce duplicate heartbeat events and concurrent file writes (see Section 5 note on append atomicity).

### JSONL log rotation

`audit.py` has no log rotation logic. On a long-running deployment with frequent audit events (every MCP call and workflow run is intended to be logged), the file grows without bound. There is no `maxBytes`, no `backupCount`, and no external rotation hook. Operators must configure logrotate or an equivalent tool externally. The Docker Compose setup mounts `./digiquant/results/audit` as a host directory, making host-side logrotate feasible but not automated.

### Remote audit sink

The `AUDIT_SINK_URL` integration is fire-and-forget with a 3-second timeout and no retry, no backpressure, and no local queue. Under network partition or sink unavailability, audit events are silently dropped from the remote mirror while the local JSONL log continues to grow. For regulatory compliance (FINRA 2026 audit trail requirements), silent drop at the remote sink is a liability. The local JSONL remains the authoritative record, but operators relying on the remote sink for real-time monitoring or SIEM ingestion will experience gaps. See Section 12(b) for the recommended retry-with-backoff fix.

### Future Node.js gateway concurrency model

The planned OpenClaw Node.js gateway is an event-loop-based runtime suited to concurrent WebSocket sessions and I/O-bound channel adapter work. The queue manager subsystem (per-session serialization) is necessary to prevent race conditions when multiple channel messages arrive for the same session simultaneously. CPU-bound work (strategy computation) is delegated to DigiQuant via HTTP rather than executed in the gateway process.

---

## 8. Performance Analysis

### Heartbeat interval

The Docker shell loop sleeps 1800 seconds (30 minutes) between cycles. `HEARTBEAT.md` specifies 30–60 minutes as the intended interval. The sleep value is hardcoded in the Docker Compose `command` field, not driven by an environment variable. Adjusting it requires editing `docker-compose.yml`.

### JSONL append cost

Each `audit_log()` call opens the file, writes a single line, and closes it. For the heartbeat use case (one event per 30 minutes), this is negligible. For high-frequency audit paths (every MCP tool call in a busy DigiGraph workflow), the repeated `open/write/close` cycle on a high-concurrency service is a potential bottleneck. A buffered async write or a logging handler with `RotatingFileHandler` would be more appropriate at scale.

### Audit sink HTTP round-trip

The remote sink POST has a 3-second timeout. On each `audit_log()` call, if `AUDIT_SINK_URL` is set, the caller blocks for up to 3 seconds waiting for the HTTP response before continuing. In a synchronous FastAPI handler, this adds up to 3 seconds of latency to every audited request if the sink is slow or unreachable. The silent exception swallow means the caller is unaware of the delay cause. A non-blocking (fire-and-forget via a background thread or async task) implementation would eliminate this latency.

### Health check HTTP round-trip

Both health checks in `run_heartbeat()` have a 5-second timeout. The total worst-case blocking time per heartbeat cycle is 70 seconds: 5s + 5s for the two health checks, 5s for `/check_drift`, and up to 60s for `/run_optimize` if drift is detected. For a 30-minute interval daemon this is acceptable.

---

## 9. Integration Points

### DigiGraph

The heartbeat runner polls `{DIGIGRAPH_URL}/health` (default `http://127.0.0.1:8000`) via HTTP GET. In Docker, this resolves to the `digigraph` service container on the internal network. The heartbeat service declares `depends_on: digigraph: condition: service_healthy` in `docker-compose.yml`, so it will not start until DigiGraph's health check passes.

DigiGraph also imports `digiclaw.audit.audit_log` directly for its own audit events. The `AUDIT_LOG_PATH` environment variable is set to `/audit/events.jsonl` in both the `digigraph` and `heartbeat` service definitions, and both mount the same host directory (`./digiquant/results/audit`), so audit lines from all sources converge in one file.

### DigiQuant

The heartbeat runner polls `{DIGIQUANT_URL}/health` (default `http://127.0.0.1:8001`) and calls `/check_drift` and `/run_optimize`. The heartbeat service declares `depends_on: digiquant: condition: service_healthy`.

DigiQuant also writes to the same `AUDIT_LOG_PATH` (`/app/results/audit/events.jsonl` in its container, which maps to the same host path).

### DigiKey

DigiKey correlation fields (`key_prefix`, `tenant`, `project_id`, `jti`) are optional parameters on `audit_log()`. They are populated by DigiGraph when it validates a DigiKey JWT and emits a workflow audit event. The heartbeat runner does not authenticate via DigiKey and does not populate these fields. There is no DigiKey-based authorization on the heartbeat service's outbound HTTP calls to DigiGraph and DigiQuant.

### Optional AUDIT_SINK_URL

Any HTTPS endpoint accepting NDJSON POSTs can serve as a remote audit mirror. No standard authentication is implemented; the caller must trust the network path or add a reverse proxy with auth. Candidates include a self-hosted Loki instance, a cloud SIEM, or a simple append-only HTTP collector.

---

## 10. Docker and MCP Composition

### Docker Compose heartbeat profile

The heartbeat service runs under the `heartbeat` profile and is not started by the default `docker compose up`:

```
docker compose --profile heartbeat up -d
# or
make up-heartbeat
```

The service uses the `python:3.12-slim` base image (not a custom build), mounts the full workspace read-only, and runs the shell loop:

```sh
while true; do python -m digiclaw; sleep 1800; done
```

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DIGIGRAPH_URL` | `http://127.0.0.1:8000` | DigiGraph base URL for health and workflow calls |
| `DIGIQUANT_URL` | `http://127.0.0.1:8001` | DigiQuant base URL for health, drift check, and optimize |
| `AUDIT_LOG_PATH` | `digiquant/results/audit/events.jsonl` | Destination for JSONL audit events |
| `AUDIT_SINK_URL` | (unset) | Optional remote NDJSON sink URL |
| `DIGI_WORKSPACE` | `.` | Directory searched for `HEARTBEAT.md` |
| `REOPTIMIZE_STRATEGY` | `mean_reversion_tech` | Strategy ID passed to `/check_drift` and `/run_optimize` |
| `DIGIQUANT_DATA_DIR` | (unset) | Required by `/run_optimize`; skips re-optimization if missing |

In Docker Compose, `DIGIGRAPH_URL` and `DIGIQUANT_URL` are overridden to use internal service names (`http://digigraph:8000`, `http://digiquant:8001`).

### Future MCP server for `run_digigraph_workflow`

The planned skill contract in `digiclaw/skills/README.md` describes a single MCP skill that POSTs to `{DIGIGRAPH_URL}/workflow`. When OpenClaw is integrated, this will require:
1. A running OpenClaw Node.js process as the gateway.
2. A registered custom skill that calls DigiGraph with a DigiKey-scoped Bearer token.
3. `DIGIGRAPH_URL` set to the internal Docker network address of the `digigraph` service.
4. The skill registered in the OpenClaw workspace file, not sourced from ClawHub.

No MCP server exists in the `digiclaw` package today.

---

## 11. Phase 2+ Gaps and Roadmap

### OpenClaw Node.js gateway (Phase 1, currently deferred)

The core gap is the absence of any gateway runtime. The five planned subsystems are:

| Subsystem | Status | Notes |
|-----------|--------|-------|
| Channel adapters (Slack, Discord, Telegram, WhatsApp) | Not started | Each adapter normalizes inbound messages to a common event schema |
| Session manager | Not started | Resolves sender identity; isolates multi-user conversation context |
| Queue manager | Not started | Serializes runs per session; prevents concurrent-agent race conditions |
| Agent runtime (OpenClaw) | Not started | Assembles workspace context from Markdown/YAML; executes skills |
| WebSocket control plane | Not started | CLI and Web UI connections; human-in-the-loop gate interface |

### MCP skill integration

The `run_digigraph_workflow` skill contract is defined but not implemented. When integrated, it needs DigiKey JWT-based auth on the DigiGraph call, not a hardcoded or unauthenticated request.

### Full ADDM implementation

The re-optimization trigger exists; the drift detector does not. A real ADDM implementation requires: (a) a metric time-series from DigiQuant (e.g., rolling Sharpe or out-of-sample error rate), (b) a statistical process control test (e.g., CUSUM or Page-Hinkley), and (c) a severity score that determines whether to re-optimize or only alert. Currently none of this exists. See Section 12 for a concrete redesign recommendation.

### Self-healing loops

Future work includes ensemble model updates driven by FinRL-Meta and GPU-accelerated parallel simulation. None of this is implemented. The re-optimization trigger in `heartbeat_runner.py` is the only self-healing mechanism, and it cannot fire because the stub ADDM always reports no drift.

### Log rotation and remote audit durability

Neither log rotation nor retry logic for the remote audit sink is implemented. These are operational gaps that affect both the Phase 3 codebase and any future scaled deployment.

---

## 12. Redesign Recommendations

The following recommendations address specific, concrete gaps in the current implementation. They are prioritized by operational risk.

### (a) Implement ADDM drift detection using statistical process control

Replace the `/check_drift` stub with a real implementation in DigiQuant. The heartbeat runner should query a rolling window of out-of-sample strategy metrics (e.g., Sharpe ratio, max drawdown) from DigiQuant's results store. Apply a CUSUM (cumulative sum control chart) or Page-Hinkley test to detect a shift in the metric distribution. Return a structured response including `drift_detected`, `drift_severity` (float 0–1), and `metric_window` so the heartbeat runner can make a graduated decision: severity below threshold logs a warning; above threshold triggers re-optimization. The hardcoded symbol list `["AAPL", "MSFT", "GOOGL"]` in `heartbeat_runner.py` must be replaced with the actual active strategy positions from DigiQuant's strategy registry.

### (b) Add retry with exponential backoff to the remote audit sink

The current `except Exception: pass` block in `audit_log()` silently discards all delivery failures to `AUDIT_SINK_URL`. For FINRA 2026 compliance, the audit trail must be durable. Add a small in-memory retry queue (3 attempts, 1s/2s/4s backoff) running on a background thread. If all retries fail, emit a `WARN` log to stderr (never to the audit file, to avoid recursion) and increment a `audit_sink_failures_total` counter exposed via `GET /v1/status` (once DigiClaw has an HTTP surface). Until then, write the failure count to a dedicated side-channel file (e.g., `audit_sink_errors.jsonl`).

### (c) Implement log rotation for the JSONL audit file

Add a `RotatingFileHandler`-style wrapper around the audit file write. Cap individual files at 100 MB with 10 backups (`events.jsonl`, `events.jsonl.1`, ..., `events.jsonl.10`). Alternatively, use a `TimedRotatingFileHandler` equivalent with daily rotation and 90-day retention to satisfy Regulation S-P and FINRA recordkeeping requirements. The current `open/write/close` pattern can be replaced with Python's `logging.handlers.RotatingFileHandler` targeting a `logging.Logger`, or a thin custom wrapper that checks `os.path.getsize()` before each append.

### (d) Use DigiKey JWT for all service calls in the OpenClaw gateway

The planned `run_digigraph_workflow` skill must not call DigiGraph with a hardcoded or unauthenticated token. The OpenClaw gateway should be provisioned with a machine API key (`dgk_live_` prefix) from DigiKey at startup. Each skill invocation should exchange that key for a short-lived JWT (`POST /v1/oauth/token`) and send it as `Authorization: Bearer <jwt>` on the DigiGraph call. This enforces the same DigiKey allowlist and audit trail that governs DigiChat and other BFFs. Without this, the gateway becomes a privilege-escalation surface: any connected channel user could trigger arbitrary DigiGraph workflows without authentication.

### (e) Add a channel adapter abstraction registry

Rather than hard-coding channel-specific logic in the OpenClaw gateway, define a `ChannelAdapter` abstract base class (or Protocol) with a standard `ingest(raw_message) -> NormalizedEvent` interface. Register adapters in a dict keyed by channel name. Adding WhatsApp or email then requires only: (1) implement `WhatsAppAdapter(ChannelAdapter)`, (2) add it to the registry, (3) set the corresponding env vars for the webhook URL. No changes to the session manager, queue manager, or agent runtime are needed. This also makes it straightforward to unit-test each adapter in isolation without running the full gateway.

### (f) Publish structured health events to a topic rather than only appending to JSONL

The heartbeat runner currently writes health results only to a local file. For real-time monitoring and alerting, health events should additionally be published to a Redis pub/sub channel (e.g., `digi:heartbeat`) or POSTed to a webhook (`HEARTBEAT_WEBHOOK_URL`). Downstream consumers (a Grafana alerting rule, a Slack notifier, a PagerDuty integration) can then react to health failures within seconds rather than waiting for a human to inspect the JSONL file. The local JSONL remains the authoritative durable record; the pub/sub channel is ephemeral and used only for real-time fan-out. Redis is already referenced in the stack (`redis:7-alpine` under the `litellm-cache` profile), so adding a pub/sub publish to the heartbeat runner requires no new infrastructure dependency.
