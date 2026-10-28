# digitrace Architecture

**Component:** digitrace — observability helpers + HTTP status API (OTel leg shipped; the platform is decided by ADR-0036)
**Version:** 0.1.0
**Status:** Library complete and HTTP service stable. The observability platform is **decided**
(ADR-0036, accepted 2026-10-09) and **not yet built**: the ingest pipeline lands under DIG-2657.

> **Superseded in part (2026-10-09):** the hosting target and the platform-scope statements
> below are superseded by [ADR-0036](../docs/adr/0036-digitrace-cloudflare-native-tracing.md).
> digitrace tracing is a Cloudflare-native pipeline — an ingest Worker and Queue, an R2 archive
> as the system of record, a Supabase `public` index with per-table RLS, Workers Analytics
> Engine aggregates — with MLflow on demand for the deep analysis. Self-hosted Langfuse is
> dropped: no new paid services.
>
> What ADR-0036 supersedes is the **platform** philosophy: "no database, no background worker,
> no queue" no longer holds for digitrace as a component (DIG-2657 lands the pipeline). It does
> **not** supersede the **library** contract: `digitrace.trace` keeps its zero-mandatory-
> dependency rule. **In-house digitrace over OTLP is the default export; LangSmith remains
> a supported, optional integration** and is never selected implicitly. ADR-0036 retired the
> self-hosted Langfuse *deployment* and its OTLP export mode with it.

---

## 1. Overview

digitrace occupies the observability role in the digithings stack. It has two distinct faces:

**As a Python library** (`digitrace.trace`, `digitrace.config`), it provides a thin conditional wrapper over the OpenTelemetry SDK, exporting by default to the in-house digitrace OTLP ingest. Every service in the stack can import it and get spans for key functions — or a transparent no-op when no export leg is configured. The library has zero mandatory dependencies beyond the packages already present in any digithings service (`pydantic`, `fastapi`); the OTLP leg is the soft optional `digitrace[tracing]` extra. LangSmith (`digitrace[langsmith]`, `LANGSMITH_API_KEY`) remains a **supported, optional integration**, never the default. After ADR-0036 the library is the OTel emit wrapper: it gains the `gen_ai` attributes and the tenant, run and session ids (DIG-2656).

**As an HTTP microservice** (port 8003), it exposes two read-only endpoints that tell orchestrators and dashboards which export backend resolved (in-house `otel` by default), and — only when an operator configured one — the sanitized host of the optional LangSmith leg, all without ever surfacing a secret.

### Phase 1 hosting target: Cloudflare-native ingest and store (was self-hosted Langfuse; now ADR-0036)

The self-hosted Langfuse plan (Web + Worker on Cloudflare Containers with external ClickHouse +
Redis) is **dropped**. It needed two new paid services, and the decision of 2026-10-09 was "no new
paid services".

The hosting target is now the ADR-0036 pipeline:

```
apps → OTLP/HTTP → digitrace-ingest Worker → Queue → consumer
     → R2 digitrace-archive (system of record; OTLP-JSON NDJSON, one object per batch,
       key `tenant=<slug>/date=<YYYY-MM-DD>/<source>/<uuid>.ndjson`)
     → D1 digitrace (digitrace_traces, digitrace_spans_index, digitrace_scores,
       digitrace_sessions), tenant-scoped on workspace_id in Worker code (DIG-2887 S1)
     → Workers Analytics Engine (tokens, cost, latency per tenant and model)
dashboard Traces tab reads through dashboard-api; `digitrace replay` loads an R2 window into
MLflow 3.10+ with the [genai] extra over OTLP/HTTP /v1/traces, on the Mac or on a scale-to-zero
Cloudflare Container.
```

Decision record: [ADR-0036](../docs/adr/0036-digitrace-cloudflare-native-tracing.md).
Self-hosted Langfuse is retired **by** that ADR. It was **never deployed** — the Worker
`digitrace-langfuse` was never created on the Cloudflare account — and the app, its
Dockerfiles, its deploy job and its runbook steps were removed by DIG-5136. The tombstone is
[`docs/ops/digitrace-langfuse.md`](../docs/ops/digitrace-langfuse.md).

Phase 2 (#4931) dual-export is **shipped** (see § Phase 2 dual-export below).
Do not point `LANGSMITH_ENDPOINT` at a trace store.

**Position on vendors (ADR-0036):** in-house digitrace over OTLP is
the default; LangSmith is a supported, optional integration, selected only by its own
environment variables and never implicitly.

### Phase 2 dual-export (shipped, #4931)

`digitrace.trace.traceable` fans out per call to whichever legs are configured, with the
in-house OTel leg as the default:

- **OTel leg (default)** — when an OTLP endpoint env var is set through
  `digibase.otel` (`DIGI_OTEL_ENDPOINT`, falling back to
  `OTEL_EXPORTER_OTLP_ENDPOINT`; the Langfuse-only aliases are gone with the
  app, DIG-5136). Opens one span per call named `digitrace.<name>` carrying the
  allowlisted `gen_ai.*` / OpenInference attributes (model, provider, token
  counts, span kind), the ADR-0036 ids (`tenant.id`, `pipeline.run_id`,
  `session.id`), the pre-existing `digi.*` correlation ids, and a SHA-256 hash
  plus character count of the redacted input and output. No prompt or
  completion text is exported; a redacted preview is opt-in only
  (`DIGI_TRACE_CONTENT_PREVIEW=1`, off by default). Headers are parsed by
  `digibase.otel` (`DIGI_OTEL_HEADERS` / `OTEL_EXPORTER_OTLP_HEADERS`).
- **LangSmith leg (optional integration)** — only when `LANGSMITH_API_KEY` is
  set and the SDK is installed (PII redaction via `process_inputs` /
  `process_outputs`). Selecting it is an operator choice; with the key plus an
  OTLP endpoint the backend is `dual`.


Either leg degrades to the other; both missing is a pure no-op. Backend
summary helpers live in `digitrace.config` (`export_backend()` →
`dual|langsmith|otel|none`) and are surfaced secret-free on
`GET /v1/status`. digigraph wraps its three workflow entry points in a shared
`digigraph_workflow_run` span plus per-node spans for the plain-function
nodes (supervisor / validate / backtest / optimize); the compiled research
subgraph stays unwrapped so `graph.stream(..., subgraphs=True)` custom events
keep flowing — its spans come from OTel auto-instrumentation when a vendor
auto-instrumentor is installed. `LANGSMITH_ENDPOINT` remains the real LangSmith
API.

### Current scope vs. intended platform

The current implementation is deliberately minimal. What exists today is a tracing shim, a health surface, and a Prometheus `/metrics` endpoint backed by the shared `digibase.metrics.install_metrics` helper. The wider roadmap — PII redaction middleware, span schema validation, custom samplers, centralized trace dashboards — is described in the gap analysis in Section 11. The current code is correct and production-safe for its narrow scope; the risks are in what it does not yet do.

**The intended platform is now decided, and this section no longer describes it.**
[ADR-0036](../docs/adr/0036-digitrace-cloudflare-native-tracing.md) replaces the "no database, no
background worker, no queue" picture with a real pipeline: an ingest Worker, a Queue, a consumer,
an R2 archive, a Supabase index with per-table RLS, an on-demand MLflow analysis path and a
read-only MCP server. The sections below still describe the library as it stands; the platform
target is the ADR.

### Observability contract (Prometheus)

Every digithings FastAPI service exposes the same three Prometheus series via `digibase.metrics.install_metrics`:

- `http_requests_total{service,version,environment,method,route,status}` — counter.
- `http_request_duration_seconds{service,version,environment,method,route,status}` — histogram.
- `http_requests_in_flight{service,version,environment}` — gauge.

`service`, `version`, and `environment` are the cross-service identity labels that enable unified Grafana dashboards to slice by deployed version and environment. `version` is sourced from each service's `__version__` (falls back to `"0.1.0"`); `environment` is read from `DIGI_ENV` (defaults to `"dev"`). The `/metrics` endpoint is unauthenticated — the same trust boundary as `/health` — so Prometheus can scrape it on the internal network.

The rollout covers five FastAPI services: digigraph, digiquant, digisearch, digikey, and digitrace. digibot is intentionally excluded — it is a CLI runner (`python -m digibot`), not an HTTP service.

---

## 2. Current Implementation State

digitrace ships exactly five source files under `digitrace/src/digitrace/`:

| File | Role | Truly implemented | Placeholder / stub |
|------|------|------------------|--------------------|
| `__init__.py` | Package identity, `__version__ = "0.1.0"` | Version string | Everything else |
| `config.py` | Environment introspection + `TraceStatus` model | All four public symbols | Nothing deferred |
| `trace.py` | `traceable(name)` decorator | Conditional wrapping, no-op fallback, PII redaction hookup, allowlisted `gen_ai.*` / OpenInference span attributes, hash + length content, ADR-0036 ids | Sampling |
| `redaction.py` | `PiiRedactor` — value-pattern and structural redaction for trace payloads | Emails, API-key prefixes, phone numbers, `DIGI_PII_PATTERNS` extras, credential key names, long-document hash summarisation | Nothing deferred |
| `server.py` | FastAPI application, `/health`, `/v1/status`, `/metrics` | All three endpoints, OTel wiring, correlation ID, Prometheus instrumentation | `/v1/status/detailed` |

As shipped today there is no database, no background worker, no queue, and no internal LangGraph graph: digitrace does not receive traces; it emits them — by default to the in-house digitrace OTLP endpoint, and optionally to LangSmith when an operator configures it.

---

## 3. API Surface

### `GET /health` and `GET /healthz`

Liveness probes. `/healthz` is the preferred endpoint (returns `{"ok": true}`); `/health` is retained for back-compat (returns `{"status": "ok"}`). Docker Compose healthcheck targets `/healthz`. See AGENTS.md "Liveness vs status" for the contract that distinguishes `/healthz` (liveness) from `/v1/status` (richer diagnostics).

```
HTTP 200 OK
{"ok": true}
```

No authentication required. No secrets in response. Safe to expose to any internal load balancer.

### `GET /v1/status`

Returns a `TraceStatus` JSON object reflecting the current runtime environment. Designed to be **public metadata**: orchestrators and dashboards can poll it to decide whether to display trace links. Must never return a secret.

```
HTTP 200 OK
{
  "version": "0.1.0",
  "tracing_configured": true,
  "langsmith_sdk_installed": false,
  "langsmith_host": null,
  "request_id": "1f0b9c3e4a7d4f62a9c58d1e3c9b2a10",
  "otel_export_configured": true,
  "dual_export": false,
  "export_backend": "otel"
}
```

`export_backend` resolves to `otel` (the in-house digitrace ingest, the default), `none`
when no OTLP endpoint exists, and to `langsmith` or `dual` only when the operator has set
that vendor's own variables. `tracing_configured` is `true` iff at least
one export leg is configured. `langsmith_host` is the hostname extracted from
`LANGSMITH_ENDPOINT` (no path, no credentials, no query string) and is `null` unless
`LANGSMITH_API_KEY` or `LANGSMITH_ENDPOINT` is set, so status never implies a vendor
backend nobody selected. `request_id` echoes the `X-Request-ID` of the call that produced this response (sourced from `digibase.http.install_request_id_middleware`) so operators can correlate the status response with logs and traces (task #213).

### Python library: `digitrace.trace.traceable`

```python
from digitrace.trace import traceable

@traceable("chat_completion")
def chat_completion(...): ...
```

A higher-order decorator. The OTel leg wraps the function in one span per call when an
OTLP endpoint is configured and the OpenTelemetry SDK is importable. The optional
LangSmith leg, when `LANGSMITH_API_KEY` is set and `langsmith` is importable, wraps it
with `langsmith.traceable(name=name)` first (with PII redaction) and the OTel span sits
outside it. With neither leg active it returns the original function unmodified.

### Python library: `digitrace.config.tracing_enabled`

```python
from digitrace.config import tracing_enabled

if tracing_enabled():
    ...
```

A runtime boolean function: true when `export_backend()` is anything but `none`. It
re-reads the environment on each call, so it is safe to use in tests that manipulate
environment variables.

---

## 4. Data Model

### `TraceStatus` (Pydantic v2)

Defined in `digitrace/src/digitrace/config.py`:

```python
class TraceStatus(BaseModel):
    version: str
    tracing_configured: bool
    langsmith_sdk_installed: bool
    langsmith_host: str | None = None
    request_id: str | None = None
    otel_export_configured: bool = False
    dual_export: bool = False
    export_backend: str = "none"
```

All fields are non-secret by construction. The model is used directly as the FastAPI `response_model` for `GET /v1/status`.

### Span attribute contract

The OTel leg's span attribute contract is **enforced at runtime** (ADR-0036 §7,
DIG-2656). `digitrace.trace.SPAN_ATTRIBUTE_ALLOWLIST` is the one place a key may
come from; `apply_span_allowlist()` drops every key that is not on it, so a
caller cannot add arbitrary keyword arguments to a span.

**Identity and correlation (kept):**
- `digi.run_name` — the decorated function's span name
- `digi.workflow_id` — correlates spans to a single digigraph workflow execution
- `digi.request_id` — mirrors the `X-Request-ID` header for cross-service correlation
- `digi.session_id` — links spans to a user session
- `tenant.id` — the tenant (ADR-0036; from `tenant_id` / `tenant` / `tenant_slug`)
- `pipeline.run_id` — the pipeline run (from `pipeline_run_id` / `run_id`)
- `session.id` — the ADR-0036 name for the same session id

**Model and usage (OTel GenAI + OpenInference):**
- `gen_ai.request.model` / `llm.model_name` — the requested model
- `gen_ai.system`, `gen_ai.provider.name`, `llm.provider` — the provider
  (explicit `provider` keyword, else the model prefix before `/`)
- `gen_ai.usage.input_tokens` / `output_tokens` / `total_tokens` and
  `llm.token_count.prompt` / `completion` / `total` — from the result's `usage`
  block when it reports one
- `gen_ai.operation.name` — `chat` (LLM), `invoke_agent` (agent),
  `execute_tool` (tool), `embeddings` (embedding)
- `openinference.span.kind` — `LLM`, `CHAIN`, `TOOL`, `AGENT`, `RETRIEVER`,
  `EMBEDDING`, `RERANKER` or `UNKNOWN`; inferred from the span name or pinned
  with `traceable(..., span_kind=...)`

**Content (hash + length only):**
- `digi.input.sha256` / `digi.input.length`
- `digi.output.sha256` / `digi.output.length`
- `digi.input.preview` / `digi.output.preview` — **only** when
  `DIGI_TRACE_CONTENT_PREVIEW` is set (off by default); the preview is the
  already-redacted payload truncated to `DIGI_TRACE_PREVIEW_CHARS` (default
  200, maximum 1000)

The hash is over the redacted payload, so the same PII does not change the
digest.

**Failure:**
- `error.type` — the exception class name only. The message and the stack
  trace are never recorded, because both can carry prompt or document text.

**Forbidden (MUST NOT include):**
- Raw LLM prompts or completions (even redacted — hash and length only)
- API keys or bearer tokens
- File paths outside approved workspace roots
- Full document bodies (summarize or hash instead)

This contract is enforced for the OTel leg. The LangSmith leg keeps its
documented-but-unenforced contract until it is cut (DIG-2663). See Section 6 for
the security implications.

---

## 5. Internal Architecture

### Module structure

```
digitrace/
  src/digitrace/
    __init__.py     # __version__ only
    config.py       # TraceStatus model + env introspection helpers
    trace.py        # traceable() decorator
    server.py       # FastAPI app
  pyproject.toml    # deps: pydantic, fastapi, uvicorn, digibase; optional: langsmith, otel
  Dockerfile        # python:3.12-slim, installs digibase + digitrace[tracing]
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

digitrace imposes no mandatory runtime dependency on any other digithings service. digigraph (the primary consumer) imports `digitrace.trace.traceable` directly as a decorator on `chat_completion` and `chat_completion_with_tools` in `digigraph/src/digigraph/llm.py`. If `digitrace` is not installed, digigraph fails at startup — so the library is a hard dependency of digigraph's image, but the LangSmith SDK inside it is soft.

The digitrace HTTP service is never called by digigraph for tracing. Spans go directly from the exporter embedded in digigraph's process to the configured OTLP endpoint — in-house digitrace by default, or the LangSmith API when that optional integration is selected. The HTTP service exists solely for status introspection.

### OTel integration path

`server.py` calls `setup_otel_fastapi(app, service_name="digitrace")` from `digibase.otel`. This call is a no-op unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set in the environment. When set, it installs:

1. A `TracerProvider` with `Resource({"service.name": "digitrace"})`
2. An `OTLPSpanExporter` (HTTP/protobuf) pointing at the configured endpoint
3. A `BatchSpanProcessor` for async export
4. `FastAPIInstrumentor` auto-instrumentation for all HTTP requests

This is infrastructure-level tracing (HTTP spans for `/health`, `/v1/status`) and is independent of LangSmith LLM tracing. The `digibase[otel]` extras must be installed; if they are absent, a warning is logged and the app continues without OTel.

---

## 6. Security Analysis

### `/v1/status` is public by design

The endpoint deliberately returns only non-secret metadata. `langsmith_host_sanitized()` uses `urllib.parse.urlparse` to extract only the hostname, discarding path, query, credentials, and fragment. This design is sound.

**Risk:** Future contributors may be tempted to add richer fields (e.g., project name, tracing tags, endpoint path) without recognizing that these can leak operational details. The constraint must be explicitly maintained via code review and documentation.

### PII redaction before LangSmith submission

`digitrace.trace.traceable` attaches a :class:`~digitrace.redaction.PiiRedactor`
to every active LangSmith span via the SDK's native `process_inputs` and
`process_outputs` callbacks. Inputs and outputs are walked recursively
(`dict`, `list`, `tuple`, `str`) and value-pattern redaction replaces:

| Pattern | Sentinel |
|---------|----------|
| Email (RFC-5321-lite) | `[REDACTED_EMAIL]` |
| API-key prefixes — `sk-`, `sk_`, `dgk_live_`, `dgk_test_`, `lsv2_` | `[REDACTED_KEY]` |
| E.164 / common North-American phone | `[REDACTED_PHONE]` |
| Extra regexes from `DIGI_PII_PATTERNS` (comma-separated) | `[REDACTED]` |

Non-string scalars (`int`, `bool`, `None`) pass through untouched. The redactor
is keyed by *value pattern*, complementing `digibase.audit.redact_mapping`
(which redacts by *key name* only). If a pinned `langsmith` SDK lacks
`process_inputs`/`process_outputs`, the decorator logs a debug message and
falls back to plain `traceable(name=…)` — tracing still flows, but redaction
is skipped; operators should upgrade the SDK. When `LANGSMITH_API_KEY` is
unset (i.e. `tracing_enabled()` is false) the decorator is a pure no-op and
the redactor is never constructed.

### Span attribute contract not enforced at ingestion

The emit-side contract is enforced (Section 4, DIG-2656): the OTel leg only
writes allowlisted keys and never writes raw prompt/completion text. Ingestion
is a different boundary: the ingest Worker does not re-validate span
attributes, so a non-digitrace source can still send any attribute its emitter
writes. That validation belongs with the ingest contract (DIG-2657).

### LangSmith API key in environment

`LANGSMITH_API_KEY` is read from the environment. In Docker Compose, it is sourced from `.env` via `env_file`. The key is never written to any log, metric, or response. However, the digitrace service container holds the key in its environment, which is accessible to anyone who can `docker inspect` the container or `exec` into it.

**Risk:** The `GET /v1/status` endpoint confirms whether a key is configured (`tracing_configured: true`) and reveals the LangSmith host. An attacker who knows tracing is active and the host is `api.smith.langchain.com` gains no direct access, but can infer that LangSmith is in use and target it separately.

---

## 7. Scalability Analysis

### HTTP service is optional for library usage

digigraph does not call the digitrace HTTP service at all. The service is optional — useful for health dashboards and status checks, but removing it from a deployment does not break tracing. This is a well-designed separation.

### LangSmith SDK async batching

`langsmith.traceable` uses the LangSmith Python SDK's internal batch exporter. Spans are collected in memory and flushed in background threads with configurable batch size and interval. This means:
- Tracing adds negligible latency to decorated functions (no synchronous HTTP calls in the hot path).
- Spans may be lost if the process exits without flushing. There is no guaranteed-delivery mechanism.
- Under high throughput (many concurrent `chat_completion` calls), the SDK's internal buffer may back up. The SDK does not expose a backpressure signal to the application.

### OTel collector bottleneck

When `OTEL_EXPORTER_OTLP_ENDPOINT` is set, `BatchSpanProcessor` exports via HTTP/protobuf to the configured collector. The default batch settings (512 spans, 5s timeout) are suitable for low-to-moderate traffic on the digitrace HTTP service itself (only two endpoints). At high request rates, the exporter may drop spans if the collector is slow; `BatchSpanProcessor` uses a fixed-size queue and silently drops when full.

For digitrace's current traffic profile (health checks + status polls), this is a non-issue. If digitrace grows to handle trace aggregation itself, the OTel export path would need tuning.

---

## 8. Performance Analysis

### No-op decorator overhead

When no export leg is configured — no OTLP endpoint and no `LANGSMITH_API_KEY`, or the SDKs are not installed — `traceable()` returns the original function unchanged. The decoration itself happens at module import. Per-call overhead is zero — no closure, no wrapper, no conditional check.

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

`digibase/otel.py` uses `OTLPSpanExporter` from `opentelemetry.exporter.otlp.proto.http.trace_exporter` — the HTTP/protobuf variant, not gRPC. HTTP/protobuf is slightly higher overhead than gRPC due to HTTP framing, but avoids the gRPC dependency and is compatible with most collectors (Jaeger, Tempo, OTEL Collector) out of the box. For digitrace's traffic volume, the difference is immaterial.

---

## 9. Integration Points

### digigraph

digigraph is the only service that currently uses the digitrace library. The integration is in `digigraph/src/digigraph/llm.py`:

```python
from digitrace.trace import traceable as _traceable

@_traceable("chat_completion")
def chat_completion(...): ...

@_traceable("chat_completion_with_tools")
def chat_completion_with_tools(...): ...
```

Both top-level LLM entry points are decorated. The decorator wraps the entire function including the tool-calling loop in `chat_completion_with_tools`. digigraph installs `digitrace[tracing]` in its Docker image (via `digigraph/Dockerfile`, which copies and installs the `digitrace` package with tracing extras).

digigraph also has `DIGITRACE_URL=http://digitrace:8003` in its Docker Compose environment, but this URL is not read by any digigraph source code in v1. It is reserved for future discovery and health-check integration.

### Other services

digisearch, digiquant, and digibot do not currently import `digitrace`. They use `digibase[otel]` directly (via `setup_otel_fastapi`) for infrastructure-level OTel tracing when `OTEL_EXPORTER_OTLP_ENDPOINT` is configured. They do not emit LangSmith spans.

### digichat

digichat (Next.js BFF) references `DIGITRACE_INTERNAL_URL=http://digitrace:8003` in its Docker Compose environment. The intended use is to poll `GET /v1/status` to display tracing status in the UI. This integration is reserved for future implementation.

### Optional Docker service vs library-only usage

digitrace can be used in two modes:

1. **Library-only**: Install `digitrace[tracing]` in the consuming service's image. No digitrace container needed. Tracing works independently.
2. **Full service**: Run the digitrace container (port 8003). Adds health and status introspection without affecting tracing behavior.

The Dockerfile installs `digitrace[tracing]`, so the Docker service image includes both modes.

---

## 10. Docker and MCP Composition

### Docker Compose service definition

digitrace is defined as a first-class service in `docker-compose.yml` (not behind a profile):

```yaml
digitrace:
  build:
    context: .
    dockerfile: digitrace/Dockerfile
  image: digi-digitrace:latest
  container_name: digi-digitrace
  ports:
    - "127.0.0.1:8003:8003"
  env_file:
    - .env
  healthcheck:
    test: ["CMD", "curl", "-f", "http://127.0.0.1:8003/healthz"]
    interval: 15s
    timeout: 5s
    retries: 3
    start_period: 10s
```

The service binds to loopback (`127.0.0.1:8003`) on the host, following the stack-wide least-privilege network policy. The container runs on all interfaces (`0.0.0.0:8003`) inside Docker's internal network, which is correct for inter-container communication.

Unlike digigraph, digitrace does not depend on any other service in Compose. It starts independently.

### Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `LANGSMITH_API_KEY` | No | Optional LangSmith integration: enables LangSmith trace export when set **and** the SDK is installed. Absent by default; the in-house OTLP leg is the default path. |
| `LANGSMITH_ENDPOINT` | No | LangSmith API base URL for the optional integration. Default: `https://api.smith.langchain.com`. Hostname appears in `/v1/status` only when the integration is configured. Never point at a trace store. |
| `DIGI_OTEL_ENDPOINT` / `DIGITRACE_OTLP_ENDPOINT` / `OTEL_EXPORTER_OTLP_ENDPOINT` | No | OTLP endpoint. Under ADR-0036 it is the in-house digitrace ingest endpoint `https://<ingest-host>/v1/traces`. Parsed by `digibase.otel`; `digitrace.config` keeps no second copy. |
| `DIGI_OTEL_HEADERS` / `OTEL_EXPORTER_OTLP_HEADERS` | No | OTLP headers. Under ADR-0036 they carry `x-digitrace-token` and `x-digitrace-tenant`. Parsed by `digibase.otel`. |
| `DIGI_TRACE_CONTENT_PREVIEW` | No | **Opt-in, off by default.** Set to `1`/`true` to add a redacted, truncated `digi.input.preview` / `digi.output.preview` attribute to OTel spans. Leave unset for hash + length only. |
| `DIGI_TRACE_PREVIEW_CHARS` | No | Preview length when `DIGI_TRACE_CONTENT_PREVIEW` is on. Default 200, capped at 1000. |
| `DIGI_PII_MAX_DOCUMENT_CHARS` | No | Strings longer than this are replaced by `[DOCUMENT sha256:<digest> chars:<n>]` in redacted payloads. Default 4000; `0` disables summarisation. |
| `DIGI_PII_PATTERNS` | No | Comma-separated extra redaction regexes, appended to the built-in email / API-key / phone rules. |

The `LANGSMITH_API_KEY` and `LANGSMITH_ENDPOINT` variables are sourced from the `.env` file via `env_file`. They are available to the digitrace container but are also available to digigraph and any other service using the same `.env` — tracing is configured per-container, not centrally.

### MCP server

digitrace does not expose an MCP server today: there are no MCP tools, no tool registry
entries, and no `POST /v1/orchestrator_tools` endpoint. Under ADR-0036 that stops being a
design position. A **read-only** `digitrace.mcp_server` — `get_trace`, `search_traces`,
`get_cost_summary`, tenant-scoped, no secrets in a response — is in scope and is owned by
DIG-5141 (lane M, R&D Engineer). It follows the digiquant, digigraph and digivault MCP
precedent.

---

## 11. Phase 2+ Gaps and Roadmap

### PII validation and redaction layer — IMPLEMENTED (#214, DIG-2656)

`digitrace.redaction.PiiRedactor` covers value patterns (email, API-key
prefixes, phone, `DIGI_PII_PATTERNS`), credential key names (a whole value
becomes `[REDACTED]`; token *counts* are exempt), and long-document
summarisation (hash + character count). It is wired into LangSmith's
`process_inputs`/`process_outputs` callbacks and reused on the OTel leg, where
only a SHA-256 digest and a length of the redacted payload reach the span.
Remaining follow-up: share the credential key-name rules with
`digibase.audit`.

### Custom trace samplers

LangSmith and the OTel `BatchSpanProcessor` use default sampling (all spans). There is no per-workflow-type sampling rate configuration. High-volume workflows (e.g. bulk backtests, batch RAG ingestion) would generate disproportionate trace volume and cost. A configurable head-based sampler (e.g. 10% for routine tool calls, 100% for errors) would reduce LangSmith costs and collector load.

### Centralized trace dashboard

The intended future state — described in the `ARCHITECTURE.md` digibase roadmap — is for a digibase HTTP data-plane to aggregate trace metadata and expose it to digichat's UI. Today, the digichat BFF has `DIGITRACE_INTERNAL_URL` wired but no code to use it. A `/v1/traces` endpoint or a trace search proxy is absent.

### Trace-derived Prometheus metrics (roadmap)

digitrace exposes HTTP request metrics via `digibase.metrics.install_metrics` at `GET /metrics` (same contract as other FastAPI services). It does **not** yet export LangSmith/trace-derived series (`digitrace_llm_calls_total`, latency histograms from `traceable` wrappers). Those remain a Phase 2 follow-up.

### Span schema validation

The span attribute contract (Section 4) is documented but unenforced. No Pydantic model or validator checks that emitted spans include required fields or exclude forbidden ones. A `SpanAttributes` Pydantic model with validation could be applied as a thin wrapper around `traceable` to catch missing `workflow_id`, `request_id`, or `session_id` at development time rather than in production.

---

## 12. Redesign Recommendations

The following are specific, actionable changes that would materially improve digitrace's production readiness. They are ordered by risk reduction impact.

> **Re-framed by ADR-0036 (2026-10-09):** (e) is **decided** — OTel-first is the architecture: the in-house ingest is the default, and LangSmith is an optional integration that is never the default and is scheduled for removal at the cut (DIG-2663). (a) becomes "redaction and an allowlisted, hash-and-length span payload before any data reaches the store" and is delivered by DIG-2656. (f) becomes "a sampling rate per workflow, decided after the DIG-2663 parity window" and is owned by DIG-2657. The rest of the section stays as the recommendation list it was.


### (a) Enforce PII redaction as middleware before export — IMPLEMENTED (DIG-2656)

`langsmith.traceable` accepts `process_inputs` and `process_outputs` callbacks
for filtering span data before export, and `digitrace.trace.traceable` wires
`PiiRedactor` into them. The same redactor runs on the OTel leg before the
payload is reduced to a digest and a length. It covers:
- credential key names (`api_key`, `openai_api_key`, `authorization`,
  `password`, `session_token`, …) — the whole value becomes `[REDACTED]`;
  token counts such as `total_tokens` are exempt
- full document bodies → `[DOCUMENT sha256:<digest> chars:<n>]`
- the built-in value patterns plus `DIGI_PII_PATTERNS`

The OTel span carries no prompt or completion text at all; see the span
attribute contract in Section 4. A redacted preview is opt-in only.

### (b) Add trace-derived counters on existing `/metrics`

HTTP metrics already ship via `install_metrics`. Add in-memory counters on the `traceable` wrapper (`digitrace_traceable_calls_total`, `digitrace_traceable_duration_seconds`) and expose them on the existing `GET /metrics` scrape path.

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

### (e) Consider an OpenTelemetry-first approach, replacing LangSmith dependency — decided by ADR-0036

**Decision:** ADR-0036 (accepted 2026-10-09) adopts the OTel-first approach: digitrace emits
OTel to a Cloudflare-native ingest pipeline and MLflow is the on-demand analysis surface.
In-house digitrace is the default export; the LangSmith integration is kept as a supported,
optional integration and is never the default. The reasoning below is
kept as the record of the decision.

LangSmith is an external SaaS product with a per-trace billing model and opinionated data format. An OTel-first design would:
- Use `opentelemetry-api` spans with standard attributes for all LLM calls
- Export via OTLP to any collector (Jaeger, Tempo, Honeycomb, LangSmith's OTLP endpoint)
- Allow LangSmith to be one optional backend among many, not the sole tracing target

The `digibase.otel` module already provides the foundation. Replacing `langsmith.traceable` with a custom OTel span wrapper would decouple digitrace from LangSmith's SDK entirely and give operators control over where traces go without code changes.

### (f) Add sampling rate configuration per workflow type

Define a `DIGITRACE_SAMPLE_RATES` environment variable accepting JSON:

```json
{"default": 1.0, "chat_completion": 0.1, "backtest": 1.0}
```

The `traceable` decorator wrapper should read this config and apply head-based sampling before forwarding to LangSmith. This prevents trace volume from growing linearly with traffic for high-frequency, low-value calls (e.g. repeated tool-checking completions) while preserving full fidelity for business-critical flows (backtests, research workflows).

## Observability

This service exposes a Prometheus `/metrics` endpoint (counter, histogram, in-flight gauge for every HTTP route) via `digibase.metrics.install_metrics`; scraped by the `observability` compose profile per [ADR-0003](../docs/adr/0003-observability-baseline.md).

## CORS

CORS is installed via the shared `digibase.cors.install_cors(app, service="digitrace")` helper; allowlist precedence is `DIGITRACE_CORS_ORIGINS` → `DIGI_CORS_ORIGINS` → legacy `DIGI_ALLOWED_ORIGINS`, defaulting to empty. Phase 0 compat (#4929): a set `DIGISMITH_CORS_ORIGINS` is honored for one release when `DIGITRACE_CORS_ORIGINS` is empty. See `SECURITY.md` §"CORS policy".
