# DigiBase Architecture — Critical Analysis

> **Status:** Library shipped (v0.1.0). DigiBase data-plane service not yet built.
> **Last updated:** 2026-03-29

---

## 1. Overview

DigiBase plays two distinct roles that must not be conflated:

**Role 1 — Shared Python library (current state).** The `digibase` package (`digibase/src/digibase/`) is a thin, zero-state utility layer installed as an editable dependency inside every Python service in the monorepo. It provides four cross-cutting concerns: standardized JSON error envelopes, outbound HTTP correlation headers, audit payload redaction, and optional OpenTelemetry wiring. The library has no server port, no network listener, and no persistent state. It is a passive toolkit consumed at import time.

**Role 2 — Data-plane broker service (roadmap).** A future `DigiBase` HTTP service would sit between application services and shared infrastructure backends (Postgres, Redis, blob storage). Instead of each service container holding raw `DATABASE_URL` or `REDIS_URL` secrets, they would request short-lived scoped handles from DigiBase using DigiKey-issued tokens. DigiBase would enforce quota, routing, audit, and credential rotation in one place.

**Why the split matters.** Conflating the two roles creates confusion: the library is already deployed everywhere and changes to it have immediate fleet-wide impact. The service does not exist yet and its design must account for latency, availability, and trust boundary concerns the library never had. The naming overlap (`digibase` package vs `DigiBase` service) is a deliberate choice per `ARCHITECTURE.md` — the library retains its name and stays lightweight for Lambda and worker deployments; the service will live in a new module (tentatively `digibase-server` or `digibase-plane`).

---

## 2. Current Implementation State

The library ships modules under `digibase/src/digibase/`, including optional
`connectors/` write clients (Notion via `digibase[notion]`, Supabase via
`digibase[supabase]`).

| File | Purpose | Shipped |
|------|---------|---------|
| `__init__.py` | Package entry point; re-exports HTTP helpers, metrics, clients | Yes |
| `errors.py` | Pydantic error envelope models; FastAPI error handler registration | Yes |
| `http.py` | Outbound header helpers plus inbound X-Request-ID correlation middleware, ContextVar, and logging filter (task #213) | Yes |
| `http_client.py` | Bounded-timeout ``httpx`` client factories (epic #2 hardening) | Yes |
| `audit.py` | Key-pattern-based redaction for audit payloads | Yes |
| `metrics.py` | Prometheus `/metrics` endpoint + HTTP instrumentation middleware (ADR-0003) | Yes |
| `otel.py` | Optional OTel FastAPI instrumentation wiring (requires `digibase[otel]`) | Yes |
| `cors.py` | Shared CORS helper for FastAPI services | Yes |
| `connectors/base.py` | Abstract `ConnectorPayload` / `ConnectorResult` DTOs for write actions | Yes |
| `connectors/notion.py` | Notion database/page write client (requires `digibase[notion]`) | Yes |
| `connectors/supabase.py` | Supabase upsert + filtered-select connector (requires `digibase[supabase]`) | Yes |
| `util.py` | Small shared utilities | Yes |

The package is declared in `digibase/pyproject.toml` at version `0.1.0`. It requires Python 3.12+, Pydantic v2, httpx 0.27+, FastAPI 0.115+, and `prometheus-client >= 0.20`. OTel support is gated behind the `[otel]` optional extra, which pulls in the OpenTelemetry SDK, OTLP HTTP exporter, and FastAPI instrumentation packages.

### `digibase.metrics`

```python
install_metrics(
    app: FastAPI,
    *,
    service: str,
    version: str | None = None,
    environment: str | None = None,
) -> None
```

Attaches an ASGI middleware that records three metrics per request and exposes them at `GET /metrics` in the Prometheus text format:

| Metric | Type | Labels |
|--------|------|--------|
| `http_requests_total` | Counter | `service`, `version`, `environment`, `method`, `route`, `status` |
| `http_request_duration_seconds` | Histogram (11 buckets, 5 ms → 10 s) | same as above |
| `http_requests_in_flight` | Gauge | `service`, `version`, `environment` |

- `version` defaults to `"0.1.0"` when omitted.
- `environment` defaults to the `DIGI_ENV` env var, or `"dev"` when unset.
- The `route` label uses the FastAPI route template (`/items/{id}`), not the raw path, to keep cardinality bounded.
- Metric objects are cached per `(service, version, environment)` so multiple FastAPI apps or repeated test harness constructions in the same process are idempotent against the default Prometheus registry.
- DigiClaw does not expose `/metrics` — it is a CLI runner (`python -m digiclaw`) and has no HTTP surface.

No REST endpoints, no database, no background threads. The library is intentionally side-effect-free on import — all functions are pure or accept explicit parameters.

---

## 3. API Surface

### `digibase.http`

```python
outbound_request_id_headers(request_id: str | None) -> dict[str, str] | None
```
Returns `{"X-Request-ID": "<id>"}` if the id is non-empty, otherwise `None`. Guards against whitespace-only strings.

```python
outbound_service_headers(
    request_id: str | None,
    bearer_token: str | None,
    *,
    extra: dict[str, str] | None = None,
) -> dict[str, str]
```
Merges correlation id header, optional `Authorization: Bearer <token>` header (raw secret or JWT — no prefix expected in the argument), and arbitrary extras. Returns a plain dict safe to pass directly to httpx or similar clients. Filters out falsy values in `extra`.

```python
install_request_id_middleware(app: FastAPI) -> None
current_request_id() -> str | None
install_request_id_logging(logger: logging.Logger | None = None) -> RequestIdLogFilter
```

Inbound correlation primitives (task #213). `install_request_id_middleware` registers an HTTP middleware that reads `X-Request-ID` from the incoming request (generating a uuid4 hex when absent or blank), stores it on `request.state.request_id`, binds it to a `ContextVar` for the duration of the request, and echoes it on the response. Must be registered **after** any rate-limit middleware so the id wraps rate-limit rejections and error handlers (Starlette applies `@middleware` in LIFO outer-to-inner order). `current_request_id()` reads the ContextVar — use it from outbound call sites instead of threading the `Request` through every layer. `install_request_id_logging()` attaches a `RequestIdLogFilter` to the target logger (root by default) so every `LogRecord` carries `record.request_id`; records emitted outside any request get `"-"` so formatters with `%(request_id)s` never raise.

### `digibase.http_client`

```python
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

async_client(**kwargs) -> httpx.AsyncClient
sync_client(**kwargs) -> httpx.Client
```

Thin factories that construct `httpx.AsyncClient` / `httpx.Client` with the
`DEFAULT_TIMEOUT` pre-applied. Any standard httpx keyword argument (`base_url`,
`headers`, `auth`, `transport`, `limits`, `verify`, `http2`, …) is forwarded
unchanged. Callers that need a different envelope pass an explicit `timeout=`
kwarg — the helpers pop it from `kwargs` before calling httpx, so there is no
conflict with the default. Override types mirror httpx: `float`/`int`,
`httpx.Timeout`, or `None` to disable (discouraged).

**Timeout envelope rationale.**

| Phase | Default | Reason |
|-------|---------|--------|
| `connect` | 5 s | TCP/TLS handshake budget. Internal services on the Compose network and broker APIs should connect in <1 s; 5 s tolerates DNS hiccups without masking a dead upstream. |
| `read` | 30 s | Between-chunk socket read. LLM completions are the long pole — single token streams can legitimately idle for several seconds on complex prompts. Non-streaming JSON APIs are well inside this budget. |
| `write` | 10 s | Between-chunk socket write. Request bodies are small JSON; conservative headroom. |
| `pool` | 5 s | Wait time to acquire a pooled connection. Kept short on purpose — a starved pool is usually a bug, not a reason to wedge a caller. |

Every service-to-service call site in the monorepo uses these helpers so that
"bare" `httpx.AsyncClient()` / `httpx.Client()` — which default to *no* read
timeout and can hang forever against a slow upstream — never reach production
code. Long-running call sites (optimization, 600 s backtest submission)
continue to pass their explicit `timeout=` overrides; the helpers preserve
that behaviour verbatim.

### `digibase.errors`

```python
class ApiErrorBody(BaseModel):
    code: str          # Stable machine-readable code, e.g. "http_404", "validation_error"
    message: str       # Human-readable description
    request_id: str | None
    service: str | None

class ApiErrorEnvelope(BaseModel):
    error: ApiErrorBody
```

```python
json_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request: Request | None = None,
    service: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse
```
Builds a `JSONResponse` with the standard `{"error": {...}}` body. Extracts `request_id` from `request.state.request_id` if set (by correlation middleware), falling back to the `X-Request-ID` request header.

```python
register_fastapi_error_handlers(app: Any, *, service: str) -> None
```
Registers two exception handlers on the FastAPI application instance: one for `StarletteHTTPException` (maps to `http_<status_code>` code) and one for `RequestValidationError` (maps to `validation_error` code with first error message). Both produce `ApiErrorEnvelope` JSON bodies.

### `digibase.audit`

```python
DEFAULT_REDACT_SUBSTRINGS: tuple[str, ...] = ("password", "api_key", "token", "secret")

redact_mapping(
    payload: dict[str, Any],
    redact: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]
```
Returns a shallow copy of `payload` with any key whose lowercase form contains a redact substring replaced by the string `"[REDACTED]"`. If `redact` is `None`, the default substrings are used. Does not recurse into nested dicts.

### `digibase.metrics`

```python
install_metrics(app: FastAPI, *, service: str) -> None
```
Installs Prometheus instrumentation on *app* per [ADR-0003](../docs/adr/0003-observability-baseline.md):

- Mounts `GET /metrics` returning the default `prometheus_client` global registry in `text/plain; version=0.0.4; charset=utf-8` (hardcoded to stay on the 0.0.4 text format even if `prometheus_client` flips its default to OpenMetrics 1.0.0).
- Registers an ASGI middleware that records three metric families labelled consistently across services:
  - `http_requests_total{service,method,route,status}` — Counter.
  - `http_request_duration_seconds{service,method,route,status}` — Histogram with API-tuned buckets (5ms → 10s).
  - `http_requests_in_flight{service}` — Gauge.
- The `route` label is collapsed to the matched FastAPI route template (e.g. `/items/{item_id}`) via the app router so cardinality is bounded by declared routes. Unmatched requests fall back to `"<unmatched>"`.
- Requests against `/metrics` itself are not counted (avoids recursive inflation on every scrape).
- Default process, GC, and platform collectors ship automatically because `prometheus_client` attaches them to the global `REGISTRY` at import time — no extra wiring is required.

`install_metrics` is idempotent across multiple invocations in the same process (test suites building throwaway apps are safe); a module-level cache fetches already-registered collectors instead of raising `Duplicated timeseries`. The function raises `ValueError` if `service` is empty.

`/metrics` has no authentication and carries no secrets — operators bind the host port to loopback via docker-compose, matching every other management endpoint. The endpoint is not advertised in OpenAPI (`include_in_schema=False`) and is deliberately kept separate from the public `/v1/status` contract.

### `digibase.otel`

```python
setup_otel_fastapi(app: Any, *, service_name: str) -> None
```
No-op unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set in the environment. When set, attempts to import OpenTelemetry SDK packages; if they are missing (base install without `[otel]`), logs a warning and returns. When packages are present, creates a `TracerProvider` backed by a `BatchSpanProcessor` writing to `OTLPSpanExporter` at the configured endpoint, and instruments the FastAPI app via `FastAPIInstrumentor`. Logs the outcome at INFO level.

### `digibase.connectors.supabase`

Requires the `digibase[supabase]` optional extra (`supabase>=2`). The `supabase`
import is deferred into `from_env`, so importing the module — and the connector
base types — never pulls the dependency on a lightweight base install. Mirrors
the digiquant Supabase wrappers (`SupabaseClient` Protocol, `from_env`,
metadata-only audit redaction) so DigiQuant can adopt this connector later, and
consolidates twelve-x's hand-rolled `client.table(T).upsert(...)` /
`.select(...).eq(...)` access.

```python
class SupabaseClient(Protocol):
    def table(self, name: str) -> Any: ...

class SupabaseNotConfiguredError(RuntimeError): ...

@dataclass
class SupabaseWriteResult:
    success: bool
    table: str = ""
    rows: int = 0          # rows sent (chunked upserts sum across batches)
    error: str = ""

@dataclass
class SupabaseReadResult:
    success: bool
    rows: list[dict[str, Any]] = field(default_factory=list)
    count: int | None = None   # server-side total when count= requested
    error: str = ""

class SupabaseConnector:
    DEFAULT_CHUNK = 500

    def __init__(self, client: SupabaseClient) -> None: ...

    @classmethod
    def from_env(
        cls, *, url_var: str = "SUPABASE_URL", key_var: str = "SUPABASE_SERVICE_KEY"
    ) -> SupabaseConnector: ...

    @property
    def client(self) -> SupabaseClient: ...

    def upsert(
        self,
        table: str,
        rows: dict[str, Any] | list[dict[str, Any]],
        *,
        on_conflict: str | None = None,
        chunk: int = DEFAULT_CHUNK,
    ) -> SupabaseWriteResult: ...

    def select(
        self,
        table: str,
        columns: str = "*",
        *,
        eq: dict[str, Any] | None = None,
        gte: dict[str, Any] | None = None,
        lte: dict[str, Any] | None = None,
        in_: dict[str, list[Any] | tuple[Any, ...]] | None = None,
        order: str | None = None,
        desc: bool = False,
        limit: int | None = None,
        count: str | None = None,
    ) -> SupabaseReadResult: ...
```

`from_env` resolves `SUPABASE_URL` + the service-role key (`SUPABASE_SERVICE_KEY`
by default; both overridable), raising `SupabaseNotConfiguredError` when either
is unset/blank — this guard runs *before* the deferred `create_client` import,
so a missing-config error never requires the optional dependency. Construct with
an injected client for tests (a fake satisfying `SupabaseClient`) or callers that
already hold a `supabase.Client`.

`upsert` accepts a single row or a list, batches lists in `chunk`-sized requests
(default 500), and is idempotent when `on_conflict` names the row's unique
key(s). Client/transport errors are caught and surfaced as
`SupabaseWriteResult(success=False, error=...)` rather than raised — matching
`NotionConnector`'s `UpsertResult` contract. `select` composes PostgREST filters
(logical AND) and returns decoded `response.data`; failures surface as
`SupabaseReadResult(success=False, error=...)`.

**Audit (security).** Every successful upsert emits one redacted audit line via
`digibase.audit.redact_mapping` containing *only* metadata — `table`,
`operation`, `rows`, `on_conflict`. Row bodies are never logged: `redact_mapping`
is shallow and key-name-based, so it cannot scrub PII or licensed data carried
inside row dicts. This matches the explicit warnings in both digiquant Supabase
modules.

---

## 4. Data Model

### Error envelope (v1)

The canonical over-the-wire shape used by every DigiThings HTTP service:

```json
{
  "error": {
    "code": "http_404",
    "message": "Not found",
    "request_id": "req-abc123",
    "service": "digigraph"
  }
}
```

`code` is machine-readable and stable across releases. Current codes produced by the library: `http_<N>` for HTTP exceptions, `validation_error` for Pydantic request validation failures. Services may define additional codes but must not reuse these reserved prefixes with different semantics.

`request_id` is nullable and echoes the correlation id propagated by `X-Request-ID` or set on `request.state.request_id` by middleware. Its absence in a response means the request either had no correlation id or arrived before middleware ran (e.g., a startup exception).

`service` is nullable and identifies the originating service for cross-service error attribution. It is set explicitly by each service via the `service` parameter to `register_fastapi_error_handlers` and `json_error_response`.

### Audit event schema (informal — not yet a Pydantic model)

Each audit consumer builds its own event dict and calls `redact_mapping` before writing. The schema is by convention, not enforcement. Observed fields across `digigraph/audit.py`:

```json
{
  "ts": "<ISO-8601 UTC>",
  "event_type": "<string>",
  "agent_id": "<string>",
  "payload": { "...redacted fields replaced by [REDACTED]..." },
  "key_prefix": "<string, optional>",
  "tenant": "<string, optional>",
  "project_id": "<string, optional>",
  "jti": "<string, optional>",
  "path": "<string, optional>"
}
```

This informal contract is a known gap — see Section 12, recommendation (d).

### OTel span attribute contract

Per `ARCHITECTURE.md` and project conventions, spans emitted by services MUST include `workflow_id`, `request_id`, and `session_id` attributes. Raw prompts, API keys, and full document bodies must never appear in span attributes. The `digibase` library does not enforce this contract; it only wires the exporter. Enforcement is the responsibility of each service.

---

## 5. Internal Architecture

### Module dependency graph (library)

```
digibase/__init__.py
    └── digibase.http (outbound_request_id_headers re-exported)

digibase.errors
    ├── pydantic (BaseModel, Field)
    ├── fastapi (Request, RequestValidationError, JSONResponse)
    └── starlette.exceptions (HTTPException)

digibase.http
    └── (no imports — pure Python)

digibase.audit
    └── (no imports — pure Python)

digibase.otel
    ├── logging (stdlib)
    ├── os (stdlib)
    └── opentelemetry.* (optional, guarded by try/except ImportError)
```

The library has no internal circular dependencies. `errors.py` is the only module with framework dependencies (FastAPI/Starlette). `http.py` and `audit.py` are pure Python with no third-party imports, making them safe to use in any context — Lambda, CLI, test harness — without pulling in the web framework.

### Consumer dependency map

| Service | `http.py` | `errors.py` | `audit.py` | `otel.py` |
|---------|-----------|-------------|------------|-----------|
| DigiGraph | `outbound_service_headers` (connectors, hub, nodes, tools) | `json_error_response`, `register_fastapi_error_handlers` | `redact_mapping` (via `digigraph/audit.py`) | `setup_otel_fastapi` |
| DigiQuant | — | `json_error_response`, `register_fastapi_error_handlers` | — | `setup_otel_fastapi` |
| DigiSearch | — | `json_error_response`, `register_fastapi_error_handlers` | — | `setup_otel_fastapi` |
| DigiSmith | — | `register_fastapi_error_handlers` | — | `setup_otel_fastapi` |
| DigiKey | — | `register_fastapi_error_handlers` | — | — |

DigiGraph is the heaviest consumer: it uses `outbound_service_headers` in five locations (both connector modules, both vertical orchestrator hub modules, and the graph nodes module) to propagate correlation ids and bearer tokens on every outbound service-to-service call.

DigiClaw does not appear to import digibase directly; it uses the shared audit format by convention rather than by library import.

---

## 6. Security Analysis

### Secret redaction

`redact_mapping` operates on key names, not values. A key named `"api_key"` is redacted; a key named `"credentials"` is not (it does not contain any default substring). This is a deliberate design trade-off: substring matching on key names is fast and predictable, but it is not exhaustive. Risk: a developer could name a secret-bearing field `"auth_header"` and it would pass through unredacted. Mitigation: callers can pass a custom `redact` tuple to extend the defaults; this is optional and easy to forget.

The redaction is shallow — nested dicts are not traversed. A payload structured as `{"inner": {"api_key": "secret"}}` would not have `inner.api_key` redacted. This is a known limitation that should be addressed if audit payloads ever carry nested credential structures.

### Error envelope and stack trace leakage

`errors.py` never includes exception objects, tracebacks, or raw internal state in the response body. The `message` field in the error body for `StarletteHTTPException` is taken from `exc.detail` (which FastAPI/Starlette sets to human-readable strings, not tracebacks). For `RequestValidationError`, only the first validation error's `msg` field is included. This is correct behavior for a production API.

There is no mechanism that could accidentally include Python exception tracebacks in responses — the handler explicitly constructs the envelope from controlled inputs.

### OTel export channel

`setup_otel_fastapi` uses OTLP over HTTP to the configured endpoint. The transport security of the OTel channel depends entirely on the `OTEL_EXPORTER_OTLP_ENDPOINT` value provided by the operator. If the endpoint is `http://` (as is typical in Docker Compose using a local collector), traffic is unencrypted on the internal network. In production with a remote collector, the endpoint should use `https://` and the collector should require authentication. The library does not validate or enforce this — it is a configuration concern, not a library concern, but should be called out explicitly in operator documentation.

Span attribute secrets: the library instruments FastAPI routes automatically via `FastAPIInstrumentor`. This instrument captures request paths, HTTP methods, and status codes. It does not automatically capture request bodies or headers containing secrets — but if future code calls `span.set_attribute("authorization", ...)` manually, that would leak tokens to the collector. The `digibase` library has no guardrail against this.

### Library vs service trust boundary

Today, because `digibase` is a library, there is no network trust boundary to enforce: all consumers run in the same process space and importing the library implicitly trusts all of its behavior. The planned DigiBase service introduces a genuine trust boundary. Services will authenticate to it using DigiKey-scoped tokens, and DigiBase will make authorization decisions about which service may access which database handle. This is a significant architectural upgrade — library-level convenience helpers become service-level authorization policy — and the transition requires careful sequencing to avoid either a flag day migration or a prolonged dual-mode period.

---

## 7. Scalability Analysis

### Library (current)

The library has no scalability dimension. It contributes zero overhead to scaling decisions. `redact_mapping` creates a shallow dict copy; `outbound_service_headers` allocates a small dict; `json_error_response` serializes a small Pydantic model. None of these are on any hot path that would affect throughput at scale.

### Future DigiBase service

The service design must address several non-trivial scalability problems:

**Postgres connection brokering.** If DigiBase sits in front of Postgres, every service that currently holds a direct connection pool through SQLAlchemy or asyncpg will instead hold a pool of connections to DigiBase. DigiBase must then maintain its own pool to Postgres. This double-pooling can be beneficial (DigiBase enforces a global cap on total Postgres connections, preventing pool exhaustion across a growing service fleet) but requires DigiBase to be highly available and low-latency. A single DigiBase instance becomes a single point of failure for all database operations.

**Multi-tenant credential scoping.** The security model described in `ARCHITECTURE.md` calls for per-tenant and per-service credential scoping (aligned with DigiKey). Credential issuance at scale requires a low-latency token store and efficient revocation. If each service request causes a synchronous credential lookup in DigiBase, the latency budget shrinks. Caching scoped credentials at the service level (with short TTLs and revocation push-down) is likely necessary.

**Redis credential brokering.** Phase 2 extends the model to Redis namespaced credentials. Redis is commonly used for high-throughput caching and rate limiting — paths that demand single-digit millisecond latency. Inserting DigiBase as a credential broker adds a round trip before the Redis call unless the credential is cached locally. Design must account for this.

**High availability.** DigiBase as a service must be deployed with redundancy and a health-check that services can use to detect outages and fail open or fail closed based on policy. Current Compose services use loopback-only bindings; DigiBase must follow the same model internally while being accessible to all services that depend on it.

---

## 8. Performance Analysis

### Library (current)

The library contributes negligible overhead:

- `outbound_request_id_headers` and `outbound_service_headers`: two string operations, one dict allocation. Nanosecond-scale.
- `redact_mapping`: one `dict()` shallow copy, one iteration over keys. Linear in key count, but audit payloads are small (tens of keys). Microsecond-scale.
- `json_error_response`: one `ApiErrorEnvelope.model_dump()` call. Pydantic v2 with compiled validators. Sub-millisecond on any modern hardware.
- `register_fastapi_error_handlers`: called once at application startup. Zero runtime cost.

### OTel batching

`setup_otel_fastapi` uses `BatchSpanProcessor`, which buffers spans in memory and flushes to the OTLP endpoint in batches. The batch processor has configurable `max_export_batch_size` (default 512), `schedule_delay_millis` (default 5000ms), and `export_timeout_millis` (default 30000ms). None of these are configured by `digibase`; they use SDK defaults. This is adequate for development and low-traffic deployments but should be tuned in production (larger batches, lower delay) to balance throughput against latency of trace visibility.

The batch processor uses a background thread. If the application process is killed without flushing, buffered spans are lost. In Docker Compose deployments that use `SIGTERM` + timeout, this is typically acceptable. For critical audit-grade traces, consider a synchronous exporter or explicit flush in the shutdown handler.

### Audit JSONL append

`digigraph/audit.py` (the primary consumer of `redact_mapping`) writes audit events by opening the JSONL file in append mode (`"a"`) per event, writing, and closing. This is correct for correctness (no partial writes, no shared file handle state between calls) but suboptimal for throughput: each `audit_log()` call pays an `open()` + `write()` + `close()` syscall sequence. Under normal DigiGraph usage (tens of events per minute), this is inconsequential. Under high-frequency automated workflows, this could become a bottleneck and a source of file descriptor exhaustion on high-concurrency event loops. A buffered writer with periodic flush would be more efficient.

### Future service: connection pool sizing

The DigiBase service will need to expose Postgres connection pools sized for the aggregate demand of all downstream services. A naive approach of one pool per logical database (DigiChat, DigiKey, DigiGraph checkpoints) multiplied by service replicas could easily exhaust Postgres connection limits (default 100 on many managed instances). PgBouncer-style pooling (session vs transaction vs statement mode) built into DigiBase, or reliance on an external pgBouncer, should be an explicit design decision before Phase 1 implementation.

---

## 9. Integration Points

### How each service uses digibase today

**DigiGraph** (`digigraph/src/digigraph/`) is the primary consumer. It uses `outbound_service_headers` in every outbound call to DigiQuant and DigiSearch, ensuring correlation ids and bearer tokens are forwarded. It uses `json_error_response` for the rate limit middleware response and `register_fastapi_error_handlers` at app startup. It calls `setup_otel_fastapi` to optionally enable tracing. Its local `audit.py` wraps `redact_mapping` from digibase with DigiGraph-specific event construction.

**DigiQuant** (`digiquant/src/digiquant/server.py`) uses `json_error_response`, `register_fastapi_error_handlers`, and `setup_otel_fastapi`. It does not use the HTTP header helpers directly (it is a destination service, not a hub).

**DigiSearch** (`digisearch/src/digisearch/server.py`) mirrors DigiQuant: error handlers and OTel wiring, no outbound header usage from digibase.

**DigiSmith** (`digismith/src/digismith/server.py`) uses `register_fastapi_error_handlers` and `setup_otel_fastapi`. Minimal consumer — it is itself a thin observability status service.

**DigiKey** (`digikey/src/digikey/server.py`) uses only `register_fastapi_error_handlers`. It does not emit OTel traces via digibase (it may have its own tracing concerns given its role as the identity service).

### Library as foundation layer

The library is the single lowest-level shared artifact in the monorepo Python stack. Every Python HTTP service depends on it. This makes it:

- A natural place to evolve cross-cutting standards (error envelope version bumps, new correlation headers, audit schema changes).
- A high-impact change target: breaking changes in `digibase` affect all five services simultaneously. The `__all__` exports are intentionally narrow to minimize accidental coupling. Note: `__init__.py` only re-exports `outbound_request_id_headers`; `outbound_service_headers` (the more heavily used function) is imported directly from `digibase.http` by all consumers — a gap worth closing in a future patch.
- A deployment dependency: every service image must install the package. Current `pyproject.toml` sets it as a direct editable install from the monorepo. This is correct for local dev; production Docker builds must copy and install the package explicitly.

### Future service: position in the stack

Once built, the DigiBase service would sit between application services and shared infrastructure:

```
DigiChat / DigiKey / DigiGraph
        |
  [DigiKey JWT token]
        |
  DigiBase (HTTP :8006 proposed)
        |
  Postgres pool / Redis handles
```

Application services would replace direct `DATABASE_URL` environment variables with `DIGIBASE_URL` + `DIGIKEY_SERVICE_TOKEN`, removing raw credentials from their environment and centralizing rotation in DigiBase. The library would gain helpers for making DigiBase client calls, wrapping the same `outbound_service_headers` pattern already established.

---

## 10. Docker and MCP Composition

### Current state

There is no `digibase` service in `docker-compose.yml`. The library is installed silently inside other service images. No port is allocated, no healthcheck exists for it as a standalone entity, and no Compose profile references it.

The library is a build-time dependency only. When DigiGraph's Dockerfile runs `pip install`, it installs `digibase` from the monorepo context. No runtime container management is involved.

### Future service design

When Phase 1 is implemented, the Compose file should gain a `digibase` service in the default profile (not an optional profile, since DigiChat and DigiKey will depend on it):

```yaml
digibase:
  build:
    context: .
    dockerfile: digibase/Dockerfile
  image: digi-digibase:latest
  container_name: digi-digibase
  ports:
    - "127.0.0.1:8006:8006"
  environment:
    - DIGIBASE_DATABASE_URL=${DIGIBASE_DATABASE_URL:-postgresql://digibase:changeme@postgres:5432/digibase}
    - DIGIKEY_JWKS_URL=${DIGIKEY_JWKS_URL:-http://digikey:8005/.well-known/jwks.json}
  depends_on:
    digikey:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://127.0.0.1:8006/health"]
    interval: 15s
    timeout: 5s
    retries: 3
    start_period: 10s
```

Services that migrate to DigiBase-brokered connections would add `digibase: condition: service_healthy` to their `depends_on`. This creates a new critical path in the startup dependency graph: DigiKey → DigiBase → DigiChat/DigiGraph.

### MCP exposure

There is no plan in the roadmap to expose DigiBase as an MCP tool server. Its role is infrastructure brokering, not agent capability. The `digibase` library may eventually include an MCP-compatible helper for tool call parameter redaction (reusing `redact_mapping`), but this is not currently planned.

---

## 11. Phase 2+ Gaps and Roadmap

| Phase | Outcome | Key consumers | Missing today |
|-------|---------|---------------|--------------|
| **0 (current)** | Direct `DATABASE_URL`/`REDIS_URL` per service; `digibase` library for errors, headers, audit redaction, OTel | All Python services | Service-side secret management; audit schema enforcement |
| **1** | DigiBase **Postgres gateway**: logical DB name resolution, tenant routing, credential issuance via DigiKey token; DigiChat and DigiKey migrate first | DigiChat (`DIGICHAT_DATABASE_URL` → DigiBase handle), DigiKey (`DIGIKEY_DATABASE_URL` → DigiBase handle) | DigiBase server implementation; library client helpers; Compose integration |
| **2** | **Cache namespace API**: Redis URL/credential brokering; per-consumer namespace isolation; TTL cap enforcement; LiteLLM optional integration | DigiSearch embedding cache, LiteLLM proxy cache, DigiGraph idempotency keys | Namespace policy model; Redis auth delegation |
| **3** | **Artifact/object handles**: signed read/write handles for Digistore-like blobs; optional vector metadata routing for DigiSearch without exposing raw Chroma credentials | DigiSearch (Chroma index isolation), DigiQuant (result artifact export), future Digistore | Object store abstraction; signed URL generation; handle expiry |

**Credential rotation gap.** The most urgent gap is credential rotation. Currently, rotating a Postgres password requires updating environment variables and restarting every service that holds a direct pool. With DigiBase brokering, rotation is atomic from DigiBase's perspective — it updates its internal credential, and services obtain fresh handles on their next request. Without DigiBase, rotation requires coordinated restarts across DigiChat, DigiKey, and any other Postgres consumer simultaneously.

**DigiKey-scoped tokens.** Phase 1 requires DigiKey to issue service-scoped tokens that DigiBase accepts and validates. This is a dependency between DigiKey and DigiBase that does not exist in `../digikey/ARCHITECTURE.md` today. The scoping model (which service token grants access to which logical database) needs to be specified before Phase 1 implementation.

**Audit schema gap.** DigiBase (service) would emit its own audit events for connection issuance, policy denials, and admin changes. These must align with the DigiClaw JSONL format. Neither format is currently specified as a Pydantic model, making cross-service audit log analysis fragile.

---

## 12. Redesign Recommendations

The following are actionable recommendations ordered by urgency:

**(a) Implement Phase 1 DigiBase service immediately.**
DigiChat and DigiKey are the first consumers that need managed Postgres credentials. Both are active development priorities. Delaying DigiBase means more code is written against direct `DATABASE_URL` environment variables, increasing the migration cost later. The minimal Phase 1 surface is small: a `/v1/db/handle` endpoint that validates a DigiKey service token and returns a scoped connection string or pool reference. The existing `digibase` library already provides the error envelope and HTTP helpers to build this service correctly.

**(b) Add `audit.py` emit-to-remote buffering with retry.**
`digigraph/audit.py` currently writes to a local JSONL file with no retry, no batching, and no remote destination. If the `AUDIT_LOG_PATH` volume is unavailable (mount failure, permissions error), `audit_log()` raises an exception that propagates into the agent workflow. This should be wrapped in a try/except so audit failures are logged but do not crash the service. For production, an async buffered writer with configurable flush interval and an optional remote sink (HTTP POST to DigiClaw or DigiBase) would make audit events durable and observable across the fleet without requiring log volume aggregation.

**(c) Add OTel trace context propagation helper for HTTP outbound calls.**
`digibase.http.outbound_service_headers` correctly propagates `X-Request-ID` but does not inject W3C `traceparent`/`tracestate` headers. Services using `FastAPIInstrumentor` receive inbound trace context automatically, but when they make outbound calls with httpx, the trace context is not propagated unless `httpx` is also instrumented via `opentelemetry-instrumentation-httpx`. Add a `propagate_trace_context(headers: dict[str, str]) -> dict[str, str]` helper to `digibase.otel` that calls `opentelemetry.propagate.inject(headers)` when OTel is configured, making distributed trace stitching automatic for all callers of `outbound_service_headers`.

**(d) Standardize audit event schema with a Pydantic model.**
Define `AuditEvent` in `digibase/audit.py` as a Pydantic v2 model with required fields (`ts`, `event_type`) and optional fields matching the observed schema (`agent_id`, `payload`, `key_prefix`, `tenant`, `project_id`, `jti`, `path`). Callers use `AuditEvent(...).model_dump()` before writing, ensuring the schema is validated at construction time. This eliminates silent schema drift across DigiGraph, DigiClaw, DigiQuant, and the future DigiBase service. The `redact_mapping` call should be integrated as a validator on the `payload` field (applied automatically).

**(e) Add `digibase[vault]` extra for HashiCorp Vault credential fetching.**
Phase 1 DigiBase service needs to fetch credentials from somewhere. Hard-coded environment variables are an operational risk. Add an optional `digibase[vault]` extra that wraps `hvac` (the Python Vault client) and exposes a `fetch_secret(path: str) -> str` helper that caches the result with TTL and renews leases. This extra would be used by the DigiBase server module only, not by application services, keeping the library surface clean for lightweight installs.

**(f) Library should validate span attributes against contract (opt-in).**
The OTel span attribute contract (required: `workflow_id`, `request_id`, `session_id`; prohibited: raw prompts, API keys, full doc bodies) is enforced only by convention and code review. Add an opt-in `ValidatingSpanProcessor` to `digibase.otel` that checks spans for missing required attributes and rejects or warns on spans containing key names matching the `DEFAULT_REDACT_SUBSTRINGS` pattern. This would be instantiated alongside the `BatchSpanProcessor` when `DIGIBASE_OTEL_VALIDATE=1` is set. It is a development-time guardrail, not a performance-sensitive production component.
