# DigiSmith Architecture

**Component:** DigiSmith — LangSmith-aligned observability helpers + HTTP status API
**Version:** 0.1.0
**Status:** Minimal viable implementation — library complete, HTTP service stable, Phase 2 observability platform deferred

---

## 1. Overview

DigiSmith occupies the observability role in the DigiThings stack. It has two distinct faces:

**As a Python library** (`digismith.trace`, `digismith.config`), it provides a thin conditional wrapper around the LangSmith SDK. Every service in the stack can import it and immediately get LangSmith tracing for key functions — or get a transparent no-op when LangSmith is not configured. The library has zero mandatory dependencies beyond the packages already present in any DigiThings service (`pydantic`, `fastapi`); the LangSmith SDK is a soft optional (`digismith[langsmith]`).

**As an HTTP microservice** (port 8003), it exposes two read-only endpoints that tell orchestrators and dashboards whether tracing is active, which LangSmith host is configured, and whether the SDK is installed — all without ever surfacing a secret.

### Current scope vs. intended platform

The current implementation is deliberately minimal. What exists today is a tracing shim and a health surface, not a full observability platform. The wider roadmap — PII redaction middleware, span schema validation, Prometheus metrics export, custom samplers, centralized trace dashboards — is described in the gap analysis in Section 11. The current code is correct and production-safe for its narrow scope; the risks are in what it does not yet do.

---

## 2. Current Implementation State

DigiSmith ships exactly four source files under `digismith/src/digismith/`:

| File | Role | Truly implemented | Placeholder / stub |
|------|------|------------------|--------------------|
| `__init__.py` | Package identity, `__version__ = "0.1.0"` | Version string | Everything else |
| `config.py` | Environment introspection + `SmithStatus` model | All four public symbols | Nothing deferred |
| `trace.py` | `traceable(name)` decorator | Conditional wrapping, no-op fallback | Span attribute enforcement, sampling |
| `server.py` | FastAPI application, `/health`, `/v1/status` | Both endpoints, OTel wiring, correlation ID | `/v1/status/detailed`, metrics endpoint |

There is no database, no background worker, no queue, and no internal LangGraph graph. DigiSmith does not receive traces — it only enables other services to emit them via the LangSmith SDK.

---

## 3. API Surface

### `GET /health`

Liveness probe. Returns `{"status": "ok"}` unconditionally. Used by Docker Compose healthcheck (`curl -f http://127.0.0.1:8003/health`).

```
HTTP 200 OK
{"status": "ok"}
```

No authentication required. No secrets in response. Safe to expose to any internal load balancer.

### `GET /v1/status`

Returns a `SmithStatus` JSON object reflecting the current runtime environment. Designed to be **public metadata**: orchestrators and dashboards can poll it to decide whether to display trace links. Must never return a secret.

```
HTTP 200 OK
{
  "version": "0.1.0",
  "tracing_configured": true,
  "langsmith_sdk_installed": true,
  "langsmith_host": "api.smith.langchain.com"
}
```

`tracing_configured` is `true` iff `LANGSMITH_API_KEY` is non-empty **and** `langsmith` is importable. `langsmith_host` is the hostname extracted from `LANGSMITH_ENDPOINT` (no path, no credentials, no query string). If `LANGSMITH_ENDPOINT` is not set, the default `api.smith.langchain.com` appears.

### Python library: `digismith.trace.traceable`

```python
from digismith.trace import traceable

@traceable("chat_completion")
def chat_completion(...): ...
```

A higher-order decorator. When `LANGSMITH_API_KEY` is set and `langsmith` is importable, wraps the function with `langsmith.traceable(name=name)`. Otherwise returns the original function unmodified. The decorator is applied at module import time; there is no per-call check.

### Python library: `digismith.config.tracing_enabled`

```python
from digismith.config import tracing_enabled

if tracing_enabled():
    ...
```

A runtime boolean function. Re-reads `LANGSMITH_API_KEY` on each call, so it is safe to use in tests that manipulate environment variables.

---

## 4. Data Model

### `SmithStatus` (Pydantic v2)

Defined in `digismith/src/digismith/config.py`:

```python
class SmithStatus(BaseModel):
    version: str
    tracing_configured: bool
    langsmith_sdk_installed: bool
    langsmith_host: str | None = None
```

All fields are non-secret by construction. The model is used directly as the FastAPI `response_model` for `GET /v1/status`.

### Span attribute contract

DigiSmith defines a contract (documented in `ARCHITECTURE.md`) for what span attributes LangSmith traces SHOULD carry. This is a documentation contract, not an enforced schema:

**Required (SHOULD include when known):**
- `workflow_id` — correlates spans to a single DigiGraph workflow execution
- `request_id` — mirrors the `X-Request-ID` header for cross-service correlation
- `session_id` — links spans to a user session
- `job_id` — backtest job identifier from DigiQuant
- tool or run name — e.g. `chat_completion`, `orchestrator_tool_id`

**Forbidden (MUST NOT include):**
- Raw LLM prompts or completions
- API keys or bearer tokens
- File paths outside approved workspace roots
- Full document bodies (summarize or hash instead)

This contract is referenced by DigiGraph and DigiQuant but is not enforced by any runtime validator. See Section 6 for the security implications.

---

## 5. Internal Architecture

### Module structure

```
digismith/
  src/digismith/
    __init__.py     # __version__ only
    config.py       # SmithStatus model + env introspection helpers
    trace.py        # traceable() decorator
    server.py       # FastAPI app
  pyproject.toml    # deps: pydantic, fastapi, uvicorn, digibase; optional: langsmith, otel
  Dockerfile        # python:3.12-slim, installs digibase + digismith[langsmith]
```

### Conditional tracing decorator pattern

`trace.py` performs a module-level import guard:

```python
try:
    import langsmith as _langsmith
    LANGSMITH_SDK_AVAILABLE = True
except ImportError:
    _langsmith = None
    LANGSMITH_SDK_AVAILABLE = False
```

`traceable()` checks `LANGSMITH_SDK_AVAILABLE` and `os.environ.get("LANGSMITH_API_KEY")` at decoration time, not at call time. This means:
- If the key is absent at import time but later set, already-decorated functions remain no-ops for that process lifetime.
- The check is safe for test environments that set the env variable after import.

### Non-invasive design

DigiSmith imposes no mandatory runtime dependency on any other DigiThings service. DigiGraph (the primary consumer) imports `digismith.trace.traceable` directly as a decorator on `chat_completion` and `chat_completion_with_tools` in `digigraph/src/digigraph/llm.py`. If `digismith` is not installed, DigiGraph fails at startup — so the library is a hard dependency of DigiGraph's image, but the LangSmith SDK inside it is soft.

The DigiSmith HTTP service is never called by DigiGraph for tracing. Traces go directly from the LangSmith SDK embedded in DigiGraph's process to the LangSmith API endpoint. The HTTP service exists solely for status introspection.

### OTel integration path

`server.py` calls `setup_otel_fastapi(app, service_name="digismith")` from `digibase.otel`. This call is a no-op unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set in the environment. When set, it installs:

1. A `TracerProvider` with `Resource({"service.name": "digismith"})`
2. An `OTLPSpanExporter` (HTTP/protobuf) pointing at the configured endpoint
3. A `BatchSpanProcessor` for async export
4. `FastAPIInstrumentor` auto-instrumentation for all HTTP requests

This is infrastructure-level tracing (HTTP spans for `/health`, `/v1/status`) and is independent of LangSmith LLM tracing. The `digibase[otel]` extras must be installed; if they are absent, a warning is logged and the app continues without OTel.

---

## 6. Security Analysis

### `/v1/status` is public by design

The endpoint deliberately returns only non-secret metadata. `langsmith_host_sanitized()` uses `urllib.parse.urlparse` to extract only the hostname, discarding path, query, credentials, and fragment. This design is sound.

**Risk:** Future contributors may be tempted to add richer fields (e.g., project name, tracing tags, endpoint path) without recognizing that these can leak operational details. The constraint must be explicitly maintained via code review and documentation.

### PII risk in LangSmith spans

LangSmith's `traceable` decorator captures function inputs and outputs and sends them to the LangSmith API. In DigiGraph's `chat_completion`, the `messages` parameter contains the full LLM message history — including system prompts, user queries, and potentially retrieved document content.

The span attribute contract says "do not put raw prompts" in spans, but `langsmith.traceable` records function arguments by default. The `@_traceable("chat_completion")` decoration on `chat_completion(model, messages, ...)` likely sends the full `messages` list to LangSmith unless the LangSmith SDK is explicitly configured to exclude or truncate inputs.

**This is a significant gap.** There is no middleware, no input sanitizer, and no `hide_inputs=True` flag passed to `langsmith.traceable`. Any PII in user messages, any API keys passed as tool results, and any retrieved document text will flow to LangSmith if tracing is active.

### Span attribute contract not enforced at ingestion

The contract documented in `ARCHITECTURE.md` is advisory only. No validator checks that `workflow_id` is present, that forbidden fields are absent, or that document bodies are not embedded. Enforcement relies entirely on developer discipline.

### LangSmith API key in environment

`LANGSMITH_API_KEY` is read from the environment. In Docker Compose, it is sourced from `.env` via `env_file`. The key is never written to any log, metric, or response. However, the DigiSmith service container holds the key in its environment, which is accessible to anyone who can `docker inspect` the container or `exec` into it.

**Risk:** The `GET /v1/status` endpoint confirms whether a key is configured (`tracing_configured: true`) and reveals the LangSmith host. An attacker who knows tracing is active and the host is `api.smith.langchain.com` gains no direct access, but can infer that LangSmith is in use and target it separately.

---

## 7. Scalability Analysis

### HTTP service is optional for library usage

DigiGraph does not call the DigiSmith HTTP service at all. The service is optional — useful for health dashboards and status checks, but removing it from a deployment does not break tracing. This is a well-designed separation.

### LangSmith SDK async batching

`langsmith.traceable` uses the LangSmith Python SDK's internal batch exporter. Spans are collected in memory and flushed in background threads with configurable batch size and interval. This means:
- Tracing adds negligible latency to decorated functions (no synchronous HTTP calls in the hot path).
- Spans may be lost if the process exits without flushing. There is no guaranteed-delivery mechanism.
- Under high throughput (many concurrent `chat_completion` calls), the SDK's internal buffer may back up. The SDK does not expose a backpressure signal to the application.

### OTel collector bottleneck

When `OTEL_EXPORTER_OTLP_ENDPOINT` is set, `BatchSpanProcessor` exports via HTTP/protobuf to the configured collector. The default batch settings (512 spans, 5s timeout) are suitable for low-to-moderate traffic on the DigiSmith HTTP service itself (only two endpoints). At high request rates, the exporter may drop spans if the collector is slow; `BatchSpanProcessor` uses a fixed-size queue and silently drops when full.

For DigiSmith's current traffic profile (health checks + status polls), this is a non-issue. If DigiSmith grows to handle trace aggregation itself, the OTel export path would need tuning.

---

## 8. Performance Analysis

### No-op decorator overhead

When `LANGSMITH_API_KEY` is absent or `langsmith` is not installed, `traceable()` returns the original function unchanged. The decoration itself happens once at module import. Per-call overhead is zero — no closure, no wrapper, no conditional check.

When tracing is active, `langsmith.traceable` adds a function wrapper that:
1. Captures `*args` and `**kwargs` at call entry
2. Submits a span to the SDK's background thread
3. Captures the return value or exception at call exit

This adds one context switch and one dict allocation per call. For LLM calls that take hundreds of milliseconds, this overhead is negligible.

### LangSmith trace batching behavior

The SDK accumulates spans and sends them in background HTTP requests to LangSmith. By default, it flushes on a timer (roughly 1s) or when the buffer reaches a threshold. This means:
- Trace data appears in LangSmith with a ~1s lag after the call completes.
- In tests, `langsmith.Client().flush()` may be needed to ensure traces appear before assertions.
- At scale, the background thread can become a bottleneck if the LangSmith API is slow or unavailable.

### OTel OTLP gRPC vs HTTP export

`digibase/otel.py` uses `OTLPSpanExporter` from `opentelemetry.exporter.otlp.proto.http.trace_exporter` — the HTTP/protobuf variant, not gRPC. HTTP/protobuf is slightly higher overhead than gRPC due to HTTP framing, but avoids the gRPC dependency and is compatible with most collectors (Jaeger, Tempo, OTEL Collector) out of the box. For DigiSmith's traffic volume, the difference is immaterial.

---

## 9. Integration Points

### DigiGraph

DigiGraph is the only service that currently uses the DigiSmith library. The integration is in `digigraph/src/digigraph/llm.py`:

```python
from digismith.trace import traceable as _traceable

@_traceable("chat_completion")
def chat_completion(...): ...

@_traceable("chat_completion_with_tools")
def chat_completion_with_tools(...): ...
```

Both top-level LLM entry points are decorated. The decorator wraps the entire function including the tool-calling loop in `chat_completion_with_tools`. DigiGraph installs `digismith[langsmith]` in its Docker image (via `digigraph/Dockerfile`, which copies and installs the `digismith` package with langsmith extras).

DigiGraph also has `DIGISMITH_URL=http://digismith:8003` in its Docker Compose environment, but this URL is not read by any DigiGraph source code in v1. It is reserved for future discovery and health-check integration.

### Other services

DigiSearch, DigiQuant, and DigiClaw do not currently import `digismith`. They use `digibase[otel]` directly (via `setup_otel_fastapi`) for infrastructure-level OTel tracing when `OTEL_EXPORTER_OTLP_ENDPOINT` is configured. They do not emit LangSmith spans.

### DigiChat

DigiChat (Next.js BFF) references `DIGISMITH_INTERNAL_URL=http://digismith:8003` in its Docker Compose environment. The intended use is to poll `GET /v1/status` to display tracing status in the UI. This integration is reserved for future implementation.

### Optional Docker service vs library-only usage

DigiSmith can be used in two modes:

1. **Library-only**: Install `digismith[langsmith]` in the consuming service's image. No DigiSmith container needed. Tracing works independently.
2. **Full service**: Run the DigiSmith container (port 8003). Adds health and status introspection without affecting tracing behavior.

The Dockerfile installs `digismith[langsmith]`, so the Docker service image includes both modes.

---

## 10. Docker and MCP Composition

### Docker Compose service definition

DigiSmith is defined as a first-class service in `docker-compose.yml` (not behind a profile):

```yaml
digismith:
  build:
    context: .
    dockerfile: digismith/Dockerfile
  image: digi-digismith:latest
  container_name: digi-digismith
  ports:
    - "127.0.0.1:8003:8003"
  env_file:
    - .env
  healthcheck:
    test: ["CMD", "curl", "-f", "http://127.0.0.1:8003/health"]
    interval: 15s
    timeout: 5s
    retries: 3
    start_period: 10s
```

The service binds to loopback (`127.0.0.1:8003`) on the host, following the stack-wide least-privilege network policy. The container runs on all interfaces (`0.0.0.0:8003`) inside Docker's internal network, which is correct for inter-container communication.

Unlike DigiGraph, DigiSmith does not depend on any other service in Compose. It starts independently.

### Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `LANGSMITH_API_KEY` | No | Enables LangSmith trace export. If absent, tracing is a no-op. |
| `LANGSMITH_ENDPOINT` | No | LangSmith API base URL. Default: `https://api.smith.langchain.com`. Hostname appears in `/v1/status`. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | If set, enables OTel HTTP/protobuf export from the DigiSmith HTTP service itself. |

The `LANGSMITH_API_KEY` and `LANGSMITH_ENDPOINT` variables are sourced from the `.env` file via `env_file`. They are available to the DigiSmith container but are also available to DigiGraph and any other service using the same `.env` — tracing is configured per-container, not centrally.

### No MCP server

DigiSmith does not expose an MCP server. There are no MCP tools, no tool registry entries, and no `POST /v1/orchestrator_tools` endpoint. DigiSmith is a passive observability component, not an agent tool. This is correct by design.

---

## 11. Phase 2+ Gaps and Roadmap

### PII validation and redaction layer

There is no PII scrubbing before spans are sent to LangSmith. The `traceable` decorator captures full function inputs by default. A redaction middleware — either a custom `langsmith.traceable` wrapper that filters `messages` fields, or a process-level span processor — is needed before enabling LangSmith tracing in a production deployment with real user data.

### Custom trace samplers

LangSmith and the OTel `BatchSpanProcessor` use default sampling (all spans). There is no per-workflow-type sampling rate configuration. High-volume workflows (e.g. bulk backtests, batch RAG ingestion) would generate disproportionate trace volume and cost. A configurable head-based sampler (e.g. 10% for routine tool calls, 100% for errors) would reduce LangSmith costs and collector load.

### Centralized trace dashboard

The intended future state — described in the `ARCHITECTURE.md` DigiBase roadmap — is for a DigiBase HTTP data-plane to aggregate trace metadata and expose it to DigiChat's UI. Today, the DigiChat BFF has `DIGISMITH_INTERNAL_URL` wired but no code to use it. A `/v1/traces` endpoint or a trace search proxy is absent.

### Prometheus metrics export from traces

DigiSmith emits no Prometheus metrics. Operators have no way to observe LLM call rates, latency distributions, or error rates from within their own infrastructure without going to LangSmith's external dashboard. A `GET /metrics` endpoint exposing `digismith_llm_calls_total`, `digismith_llm_latency_seconds`, and `digismith_trace_errors_total` counters would integrate with standard Prometheus/Grafana stacks.

### Span schema validation

The span attribute contract (Section 4) is documented but unenforced. No Pydantic model or validator checks that emitted spans include required fields or exclude forbidden ones. A `SpanAttributes` Pydantic model with validation could be applied as a thin wrapper around `traceable` to catch missing `workflow_id`, `request_id`, or `session_id` at development time rather than in production.

---

## 12. Redesign Recommendations

The following are specific, actionable changes that would materially improve DigiSmith's production readiness. They are ordered by risk reduction impact.

### (a) Enforce PII redaction as middleware before LangSmith export

`langsmith.traceable` accepts `process_inputs` and `process_outputs` callbacks for filtering span data before export. DigiSmith should define a standard `_sanitize_llm_inputs` function that:
- Strips or truncates `messages` list entries longer than a configurable character limit
- Removes any dict key matching a deny-list pattern (e.g. `api_key`, `token`, `password`, `secret`)
- Replaces full document body strings with a hash and character count

This function should be applied in the `traceable` decorator wrapper, not left to each consumer to implement.

### (b) Add Prometheus `/metrics` endpoint aggregating trace data

DigiSmith should maintain in-memory counters (using `prometheus_client` or a simple `threading.Lock`-protected dict) for:
- `digismith_traceable_calls_total{name, status}` — incremented by the `traceable` wrapper
- `digismith_traceable_duration_seconds{name}` — histogram of decorated function latency

A `GET /metrics` endpoint would expose these in Prometheus text format. This gives operators infra-level LLM call visibility without depending on LangSmith's external service.

### (c) Add structured span schema validation via Pydantic

Define a `SpanContext` Pydantic model:

```python
class SpanContext(BaseModel):
    workflow_id: str
    request_id: str
    session_id: str | None = None
    job_id: str | None = None
    run_name: str
```

The `traceable` decorator should accept an optional `span_context: SpanContext` keyword argument. If provided, it validates the context and adds the fields as LangSmith metadata. If absent in development mode (`DIGI_ENV=dev`), it logs a warning. This catches missing correlation IDs at development time.

### (d) Add `/v1/status/detailed` with LangSmith connectivity check

The current `/v1/status` only checks whether the key is configured and the SDK is installed. It does not verify that LangSmith is reachable. A `/v1/status/detailed` endpoint should:
- Make a lightweight authenticated request to the LangSmith API (e.g. `GET /api/tenants`)
- Return `{"langsmith_reachable": true/false, "langsmith_latency_ms": 42}` alongside the existing fields
- Apply a tight timeout (2s) and cache the result for 60s to avoid per-poll API calls

This endpoint should require internal authentication (e.g. a service token) since it reveals connectivity details that are more sensitive than the basic status.

### (e) Consider an OpenTelemetry-first approach, replacing LangSmith dependency

LangSmith is an external SaaS product with a per-trace billing model and opinionated data format. An OTel-first design would:
- Use `opentelemetry-api` spans with standard attributes for all LLM calls
- Export via OTLP to any collector (Jaeger, Tempo, Honeycomb, LangSmith's OTLP endpoint)
- Allow LangSmith to be one optional backend among many, not the sole tracing target

The `digibase.otel` module already provides the foundation. Replacing `langsmith.traceable` with a custom OTel span wrapper would decouple DigiSmith from LangSmith's SDK entirely and give operators control over where traces go without code changes.

### (f) Add sampling rate configuration per workflow type

Define a `DIGISMITH_SAMPLE_RATES` environment variable accepting JSON:

```json
{"default": 1.0, "chat_completion": 0.1, "backtest": 1.0}
```

The `traceable` decorator wrapper should read this config and apply head-based sampling before forwarding to LangSmith. This prevents trace volume from growing linearly with traffic for high-frequency, low-value calls (e.g. repeated tool-checking completions) while preserving full fidelity for business-critical flows (backtests, research workflows).

## Observability

This service exposes a Prometheus `/metrics` endpoint (counter, histogram, in-flight gauge for every HTTP route) via `digibase.metrics.install_metrics`; scraped by the `observability` compose profile per [ADR-0003](../docs/adr/0003-observability-baseline.md).
