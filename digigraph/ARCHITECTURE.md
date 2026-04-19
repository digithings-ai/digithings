# DigiGraph Architecture

**Service:** DigiGraph
**Port:** 8000 (HTTP), 8766 (MCP streamable-http)
**Role:** Orchestration hub — LangGraph state machine, tool registry, OpenAI-compatible API, SSE streaming
**Status:** Phase 1 implemented; Phase 2 features (Graphiti memory, remote MCP enumeration, distributed checkpoints) are roadmap items

---

## 1. Overview

DigiGraph is the central orchestration brain of the DigiThings stack. Every user request flows through it: from DigiClaw (gateway), from DigiChat (Next.js BFF), from Open WebUI (OpenAI-compatible model), or directly from Claude Desktop (MCP). DigiGraph owns three distinct roles:

1. **LangGraph state machine.** Maintains a compiled `StateGraph[WorkflowState]` that routes through research, strategy validation, backtest, and optional optimize nodes. Profile-driven conditional edges control which path executes.

2. **Tool registry and dispatcher.** Provides an in-process registry of named orchestrator tools (search, agents, Digistore introspection, planning primitives). Verticals (DigiSearch, DigiQuant) own their own OpenAI tool schemas, published via `POST /v1/orchestrator_tools`; DigiGraph fetches those schemas lazily and invokes them via `POST /v1/orchestrator_invoke`.

3. **HTTP + MCP API surface.** Exposes a `POST /workflow` endpoint (DigiClaw custom skill), a `POST /v1/chat/completions` endpoint (Open WebUI / DigiChat), thread state APIs (opt-in), and an MCP server for Claude Desktop and DigiClaw agent integration.

DigiGraph is deliberately minimal as a hub: it does not implement the quant pipeline ordering (owned by DigiQuant) or tiered RAG (owned by DigiSearch). It coordinates them.

---

## 2. Current Implementation State

The following is built and functional as of this architecture review (March 2026):

| Area | State | Key Files |
|------|-------|-----------|
| FastAPI HTTP app | Built | `server.py` |
| LangGraph `StateGraph[WorkflowState]` | Built | `graph/graph.py`, `graph/state.py` |
| Research subgraph (LLM + tool loop) | Built | `graph/research.py`, `graph/research_subgraph.py` |
| Research brief builder | Built | `graph/research_brief.py`, `research_brief_models.py` |
| Backtest node (DigiQuant jobs + fallback) | Built | `graph/nodes.py` |
| Optimize node | Built | `graph/nodes.py` |
| Supervisor node (opt-in via `DIGI_SUPERVISOR=1`) | Built | `graph/nodes.py` |
| Orchestrator tool registry | Built | `orchestration/registry.py` |
| Built-in tools + skills | Built | `orchestration/builtin.py` |
| Vertical hub clients (DigiSearch, DigiQuant) | Built | `vertical_orchestrator/digisearch_hub.py`, `vertical_orchestrator/digiquant_hub.py` |
| SSE streaming via background thread + queue | Built | `server.py`, `workflow.py` |
| LLM client (OpenAI SDK, LiteLLM compat) | Built | `llm.py` |
| In-process LLM response cache (SHA-256, TTL) | Built | `llm.py` |
| Parallel tool execution for `parallel_safe` tools | Built | `llm.py` |
| DigiAuth JWT middleware (DigiKey) | Built | `server.py` (via `digikey.integrations.service_middleware`) |
| Per-IP sliding-window rate limiter | Built | `rate_limit.py`, `server.py` |
| Correlation ID middleware (`X-Request-ID`) | Built | `server.py` |
| Tool allowlist enforcement | Built | `orchestration/registry.py`, `tool_policy.py` |
| Policy flags (code exec, debug, thread API) | Built | `policy.py` |
| Digistore (session-scoped named datasets) | Built | `digistore.py`, `run_storage.py` |
| MCP server (FastMCP, streamable-http + stdio) | Built | `mcp_server.py` |
| Thread state / history / resume endpoints (opt-in) | Built | `server.py` |
| DigiSmith tracing (`traceable` wrappers) | Built | `llm.py` (via `digismith.trace.traceable`) |
| OpenTelemetry export (opt-in) | Built | `server.py` (via `digibase.otel.setup_otel_fastapi`) |
| Planning executor (topo-sort + parallel steps) | Built | `planning/executor.py` |
| Graphiti graph memory | **Not built** | Phase 2 roadmap |
| Remote MCP server enumeration | **Not built** | Phase 2 roadmap |
| Auth-bound checkpoints (per-key RBAC) | **Not built** | Phase 2 roadmap |
| OpenAI Responses API | **Not built** | Phase 2 roadmap |

---

## 3. API Surface

### 3.1 REST Endpoints

| Method | Path | Auth | Rate Limit | Notes |
|--------|------|------|------------|-------|
| `GET` | `/health` | None | Unlimited | Legacy health check (back-compat; prefer `/healthz`) |
| `GET` | `/healthz` | None | Unlimited | Liveness probe — returns `{"ok": true}`; see AGENTS.md "Liveness vs status" |
| `POST` | `/workflow` | DigiKey JWT (optional) | 10 req/min/IP | DigiClaw custom skill; body: `WorkflowRequest` |
| `GET` | `/v1/models` | DigiKey JWT (optional) | 30 req/min/IP | OpenAI model list; returns `sitaas-rag` |
| `GET` | `/v1/model-info` | DigiKey JWT (optional) | 30 req/min/IP | Current model + mode |
| `POST` | `/v1/chat/completions` | DigiKey JWT (optional) | 10 req/min/IP | OpenAI chat completions; body: `ChatCompletionRequest`; supports `stream: true` |
| `GET` | `/v1/debug/input_messages` | DigiKey JWT | 30 req/min/IP | Last N request summaries; **requires `DIGI_ENABLE_DEBUG_ENDPOINTS=1`** |
| `GET` | `/test_llm` | DigiKey JWT | 30 req/min/IP | LLM connectivity test; **requires `DIGI_ENABLE_DEBUG_ENDPOINTS=1`** |
| `GET` | `/threads/{thread_id}/state` | DigiKey JWT | 30 req/min/IP | LangGraph checkpoint state; **requires `DIGI_ENABLE_THREAD_API=1`** |
| `GET` | `/threads/{thread_id}/history` | DigiKey JWT | 30 req/min/IP | Full checkpoint history; **requires `DIGI_ENABLE_THREAD_API=1`** |
| `POST` | `/threads/{thread_id}/resume` | DigiKey JWT | 30 req/min/IP | Resume interrupted workflow; **requires `DIGI_ENABLE_THREAD_API=1`** |
| `GET` | `/files/{path:path}` | DigiKey JWT | 30 req/min/IP | Serve exported files from `run_data_dir`; **requires `DIGI_ENABLE_THREAD_API=1`** |

Auth is enforced by `DigiAuthMiddleware` from `digikey.integrations.service_middleware`. Path-scope mappings are defined in `digigraph_path_scopes`. When `DIGIKEY_JWKS_URL` or `DIGIKEY_PUBLIC_KEY_PEM` is unset, the middleware operates in passthrough mode.

Rate limits are per-IP (sliding window, in-process `deque`). The `X-Forwarded-For` header is trusted for IP extraction — see Section 6 (Security Analysis) for implications.

### 3.2 MCP Tools

The MCP server (`mcp_server.py`, FastMCP) exposes:

| Tool | Description |
|------|-------------|
| `workflow(prompt, thread_id?)` | Run the full research + backtest graph; returns JSON `WorkflowResult` |
| `chat(message, thread_id?, model?)` | Single-turn chat via the `/v1/chat/completions` endpoint (in-process TestClient) |
| `thread_state(thread_id)` | Return LangGraph checkpoint state for a thread |
| `list_orchestrator_tools()` | List registered orchestrator tool names (JSON array) |
| `list_orchestrator_tools_detailed()` | Manifest: name, tags, `dynamic_schema` flag |

Default transport: **streamable-http** on port 8766. `--stdio` mode available for Claude Desktop integration.

The MCP server uses FastAPI's `TestClient` internally for `chat` and `thread_state` calls — it instantiates the full FastAPI app in-process rather than making real HTTP calls. This means MCP requests bypass the rate limiter and auth middleware (TestClient is exempted by the `ip == "testclient"` check in `rate_limit.py:62`).

### 3.3 Streaming Behavior

When `stream: true` in `POST /v1/chat/completions`:

1. A background `threading.Thread` runs `run_digigraph_workflow_streaming` with a `Queue` as the event sink (`workflow.py:245`).
2. The HTTP response is a `StreamingResponse` whose generator consumes the queue and yields SSE chunks.
3. Event types produced by the workflow thread:
   - `tool_call` / `tool_result` — formatted with the stream formatter (neutral or Open WebUI `<details>` style)
   - `content` — LLM token deltas, HTML-escaped
   - `reasoning` — accumulated into a `<thinking>` block before the first `content` chunk
   - `trace` — `TraceEventV1` dicts embedded in `delta.digigraph_trace` for DigiChat
   - `done` — terminates the generator loop
4. If the client disconnects mid-stream, the generator raises an exception; the background thread continues running until it completes naturally. There is no cancellation token or thread interrupt mechanism — see Section 6 (Security Analysis).

---

## 4. Data Model

### 4.1 WorkflowState (`graph/state.py`)

`TypedDict` passed through all LangGraph nodes. All keys are optional (`total=False`). No reducers are defined — last writer wins for every key.

| Key | Type | Purpose |
|-----|------|---------|
| `prompt` | `str` | User input |
| `session_id` | `str \| None` | Conversation ID; maps to LangGraph `thread_id` and Digistore namespace |
| `request_id` | `str \| None` | Correlation ID propagated to outbound HTTP |
| `workflow_id` | `str \| None` | Per-run UUID for audit log correlation |
| `digi_bearer` | `str \| None` | JWT forwarded to DigiSearch and DigiQuant |
| `allowed_tool_names` | `list[str] \| None` | Tool allowlist; `None` = unrestricted |
| `strategy_name` | `str` | LLM-extracted strategy for DigiQuant |
| `symbols` | `list[str]` | Ticker list |
| `strategy_params` | `dict[str, Any]` | Optional pre-filled DigiQuant parameters |
| `trading_profile` | `dict[str, Any]` | User/tenant trading profile; merged into `optimization_constraints` |
| `research_note` | `str` | Research path label (`"LLM-extracted"`, `"document-mode"`, `"error"`) |
| `research_response` | `str` | Freeform LLM answer in document/RAG mode |
| `rag_sources` | `list[dict]` | Aggregated DigiSearch citations |
| `research_brief` | `dict[str, Any]` | Serialized `ResearchBrief` |
| `profiling_questions` | `list[str]` | Brief + trading profile gap questions |
| `research_filters` | `list[dict]` | Injected into every DigiSearch tool call |
| `evidence_tier_preference` | `list[str]` | Evidence tier filter injected into DigiSearch |
| `backtest_result` | `dict \| None` | DigiQuant result |
| `backtest_job_id` | `str \| None` | Async job ID from `/v1/jobs/backtest` |
| `optimize_result` | `dict \| None` | DigiQuant optimization result |
| `optimize_error` | `str \| None` | Non-fatal error from optimize step |
| `optimization_constraints` | `dict[str, Any]` | Merged from `trading_profile` + research |
| `quant_artifact_uri` | `str \| None` | Opaque artifact ref (Phase 2 contract) |
| `error` | `str \| None` | Terminal error; stops further node execution |
| `stored_datasets` | `dict[str, dict]` | Ref → profile map (survives across turns via checkpointer) |
| `stream_callback` | `Callable` | Not serialized; injected per-request for streaming |
| `workflow_profile` | `str` | Active profile (`full_stack`, `research_rag`, `quant_backtest`, `plan_execute`) |
| `supervisor_depth_remaining` | `int` | Depth budget for supervisor loop |
| `supervisor_route` | `str \| None` | Next route chosen by supervisor |

### 4.2 WorkflowRequest (`models.py`)

Pydantic v2 model for `POST /workflow` and internal use:

| Field | Type | Notes |
|-------|------|-------|
| `prompt` | `str` | Required |
| `session_id` | `str \| None` | Maps to LangGraph `thread_id` |
| `request_id` | `str \| None` | Taken from `X-Request-ID` when omitted |
| `allowed_tools` | `list[str] \| None` | Overrides project/env allowlist |
| `trading_profile` | `dict \| None` | Maps to `optimization_constraints` |
| `strategy_params` | `dict \| None` | Skip LLM param extraction |
| `research_filters` | `list[dict] \| None` | Injected into DigiSearch calls |
| `digi_bearer` | `str \| None` | JWT propagated downstream |
| `digi_trace_key_prefix` / `digi_trace_tenant` / `digi_trace_project_id` / `digi_trace_jti` | `str \| None` | DigiKey audit fields |
| `evidence_tier_preference` | `list[str] \| None` | Evidence tier filter |

### 4.3 WorkflowResult (`models.py`)

| Field | Type | Notes |
|-------|------|-------|
| `success` | `bool` | |
| `message` | `str` | Human-readable summary or full RAG response |
| `backtest_result` | `dict \| None` | DigiQuant `BacktestResult` |
| `optimize_result` | `dict \| None` | DigiQuant optimization result |
| `optimize_error` | `str \| None` | Non-fatal optimize error |
| `research_brief` | `dict \| None` | Serialized `ResearchBrief` |
| `rag_sources` | `list[dict] \| None` | Aggregated citations |
| `profiling_questions` | `list[str] \| None` | Open questions for user follow-up |

### 4.4 ResearchBrief (`research_brief_models.py`)

Typed output of the `research_brief_builder_node`:

| Field | Type | Notes |
|-------|------|-------|
| `themes` | `list[Theme]` | Each theme has `label`, `summary`, `source_ids` (citation refs) |
| `contradictions` | `list[str]` | Conflicting claims found in corpus |
| `assumptions` | `list[str]` | Unstated assumptions in the request |
| `corpus_gaps` | `list[str]` | Topics not covered by the retrieved corpus |
| `profiling_questions` | `list[str]` | Follow-up questions for user |
| `suggested_catalog_strategies` | `list[str]` | Strategy names from DigiQuant catalog |
| `strategy_out_of_catalog` | `bool` | True when the strategy is novel |
| `suggested_symbols` | `list[str]` | Ticker suggestions |
| `suggested_strategy_params` | `dict[str, Any]` | Parameter hints |

### 4.5 ChatCompletionRequest (`models.py`)

OpenAI-compatible body for `POST /v1/chat/completions`:

| Field | Type | Notes |
|-------|------|-------|
| `model` | `str` | Default `"sitaas-rag"`; not used for routing (LiteLLM handles it) |
| `messages` | `list[ChatMessage]` | Role + content; content coerced from AI SDK part lists |
| `stream` | `bool` | SSE streaming |
| `openwebui_format` | `bool` | Open WebUI `<details>` tool blocks |
| `session_id` | `str \| None` | Conversation isolation |
| `allowed_tools` | `list[str] \| None` | Tool allowlist for this request |

---

## 5. Internal Architecture

### 5.1 Module Structure

```
digigraph/src/digigraph/
├── server.py                    FastAPI app, middleware stack, all HTTP routes
├── workflow.py                  run_digigraph_workflow (sync + streaming variants)
├── models.py                    Pydantic I/O models (WorkflowRequest, WorkflowResult, ChatCompletion*)
├── models/                      Extended model subpackage (if present)
├── research_brief_models.py     ResearchBrief, Theme, CitationRef
├── llm.py                       OpenAI SDK client, model mode resolution, LLM cache, tool loop
├── policy.py                    Feature flag gate functions (debug, thread API, code exec, hub mode)
├── rate_limit.py                Per-IP sliding-window rate limiter (in-process deque)
├── digistore.py                 Session-scoped named dataset store (filesystem JSON)
├── run_storage.py               Lower-level session path helpers, search result writer
├── mcp_server.py                FastMCP server exposing workflow, chat, thread_state, tool lists
├── audit.py                     JSONL audit log writer (workflow_start, workflow_end, tool_denied)
├── trace_events.py              TraceEventV1, RagSourceItem, rag_sources_from_results
├── tool_policy.py               Allowed tool name resolution (request → project config → env)
├── trading_profile.py           optimization_constraints_dict_from_profile
├── project_config.py            DigiProjectConfig loader (DIGI_PROJECT_CONFIG YAML)
├── path_utils.py                assert_safe_path for file serving
├── circuit_breaker.py           Circuit breaker utility
├── graph/
│   ├── graph.py                 build_workflow_graph() — StateGraph compiler + checkpointer init
│   ├── state.py                 WorkflowState TypedDict
│   ├── nodes.py                 supervisor_node, strategy_validator_node, backtest_node, optimize_node
│   ├── research.py              research_node, _run_document_rag_path, _run_quant_or_augmented_path
│   ├── research_subgraph.py     build_research_subgraph() — research_inner + research_brief_builder
│   └── research_brief.py        research_brief_builder_node
├── orchestration/
│   ├── registry.py              ToolContext, register_tool, register_skill, get_tools, execute
│   ├── builtin.py               All built-in tool + skill registrations; loads entry points
│   └── plugins.py               setuptools entry point loader (digigraph.tools)
├── vertical_orchestrator/
│   ├── digisearch_hub.py        fetch_digisearch_tool_dicts, invoke_digisearch_tool
│   └── digiquant_hub.py         fetch_digiquant_tool_dicts, invoke_digiquant_tool
├── agents/
│   ├── analysis/                run_analysis_agent, ANALYSIS_AGENT_TOOL
│   ├── data_engineer/           run_data_engineer_agent, DATA_ENGINEER_AGENT_TOOL
│   ├── data_manipulation/       run_data_manipulation_agent
│   ├── data_prep/               run_data_prep_agent
│   └── visualization/           run_visualization_agent, VISUALIZATION_AGENT_TOOL
├── tools/
│   └── digisearch.py            Thin POST /query client (non-orchestrator call sites)
├── planning/
│   └── executor.py              Plan executor: topo-sort, placeholder resolution, parallel steps
├── skills/
│   └── __init__.py              get_tools_for_skills (delegates to registry)
├── formatters/
│   └── __init__.py              get_stream_formatter, neutral and Open WebUI formatters
└── connectors/                  (reserved for Phase 2 connector extensions)
```

### 5.2 LangGraph StateGraph

```
START
  │
  ├─[DIGI_SUPERVISOR=1]─► supervisor_node ─► (error → END) or research
  │
  └─[default]─────────────► research subgraph
                                │
                                ├─ research_inner (research_node)
                                └─ research_brief_builder
                               │
                               ├─ error → END
                               ├─ research_rag profile → END
                               ├─ no strategy_name (document mode) → END
                               └─ has strategy_name → validate_strategy
                                                          │
                                                          ├─ error → END
                                                          └─ backtest
                                                               │
                                                               ├─ error → END
                                                               ├─ no result → END
                                                               └─ optimize enabled → optimize → END
```

The graph is compiled once per `build_workflow_graph()` call. In practice, `workflow.py` calls `build_workflow_graph()` on **every** request — there is no module-level compiled graph cache. This means the StateGraph is recompiled on each call; the checkpointer instance is shared (process-wide singleton).

### 5.3 Orchestrator Tool Registry Pattern

Three-layer structure:

1. **Primitives** (`tools/`): stateless callables not exposed to the LLM directly.
2. **Orchestrator tools** (`orchestration/`): `(name, schema, handler, tags)`. Schema may be a static dict or a `SchemaFactory(context) -> dict` for context-dependent schemas (e.g. DigiSearch tools fetched from the vertical manifest). Registered once at module import via `_register_tools()` in `builtin.py:585`.
3. **Skills** (`orchestration/registry.py`): named bundles of tool names with a `when(context) -> bool` predicate. The `search` skill activates only when `DIGISEARCH_URL` is set. The `sitaas_rag` skill activates only when `run_data_dir` is set.

The registry is a module-level dict (`_tools`, `_skills` in `registry.py`). It is global to the process — all requests share the same registry. `register_tool` raises `ValueError` on duplicate names, so plugins loaded via `load_entrypoint_tools()` must use unique names.

### 5.4 Vertical Connector Pattern

DigiSearch and DigiQuant each own their tool schemas via `POST /v1/orchestrator_tools`. DigiGraph:

1. Calls `fetch_digisearch_tool_dicts(base_url, index_config, bearer, request_id)` at schema resolution time. Results are cached in a module-level dict (`_MANIFEST_CACHE`) keyed on `(base_url, index_config)` — this cache is **never invalidated** for the lifetime of the process.
2. Invokes tools via `invoke_digisearch_tool(base_url, tool, args, ...)` → `POST /v1/orchestrator_invoke`.
3. The DigiQuant connector follows the same pattern via `digiquant_hub.py`.

The manifest cache uses synchronous `httpx.Client` (blocking calls inside async FastAPI). This can block the event loop thread during tool schema resolution. The current request handling is synchronous (FastAPI's thread pool), so this is acceptable but limits throughput under high concurrency.

### 5.5 Checkpointing

Process-wide singleton via `get_checkpointer()` in `graph/graph.py:29`:

| `DIGI_CHECKPOINTER` value | Backend | Notes |
|--------------------------|---------|-------|
| unset or `memory` | `MemorySaver` (in-process dict) | Default; lost on restart |
| `sqlite` | `SqliteSaver` | File path via `DIGI_CHECKPOINTER_SQLITE_URI` |
| `postgres` | `PostgresSaver` | Connection string via `DIGI_CHECKPOINTER_POSTGRES_URI` |
| `none` / `off` / `0` / `false` | None (no checkpointing) | Breaks multi-turn and thread APIs |

A `threading.Lock` (`_checkpointer_lock`) guards lazy initialization. Context managers for SQLite and Postgres are stored in `_cm_holders` to prevent garbage collection — this is a manual resource management pattern that will leak if the process forks.

### 5.6 Streaming SSE Architecture

```
HTTP request (stream=true)
        │
        ▼
_stream_completions_progressive (server.py generator)
        │
        ├── spawns Thread → run_digigraph_workflow_streaming(req, event_queue)
        │                           │
        │                           ├── _stream_callback_ctx (ContextVar) set
        │                           ├── graph.stream(..., stream_mode="updates")
        │                           │     └── research_node → chat_completion_with_tools
        │                           │           └── stream_callback("tool_call/result/content/reasoning/trace")
        │                           │                 └── event_queue.put(...)
        │                           └── event_queue.put(("done", None))
        │
        └── while True: ev = event_queue.get()
              ├── "tool_call" → buffer
              ├── "tool_result" → flush tool pair as SSE chunk
              ├── "reasoning" → buffer → flush as <thinking> block before content
              ├── "content" → SSE chunk (HTML-escaped)
              ├── "trace" → SSE chunk with digigraph_trace delta
              └── "done" → break → yield stop chunk → yield [DONE]
```

The `_stream_callback_ctx` is a `ContextVar` used to pass the callback from `workflow.py` to `research.py` without threading state through the LangGraph config. The `stream_mode="updates"` call on `graph.stream` drives per-node progress events; the research node's tool loop emits fine-grained events independently.

---

## 6. Security Analysis

### 6.1 DigiKey JWT Authentication

`DigiAuthMiddleware` validates JWTs via `DIGIKEY_JWKS_URL` (JWKS endpoint) or `DIGIKEY_PUBLIC_KEY_PEM` (static PEM). Path-scope mappings control which scopes are required per route. When neither is configured, the middleware passes through unauthenticated requests — this is the default for local dev but must not be used in production.

The JWT subject (`sub`) is not bound to checkpoint state. Any authenticated caller with a valid JWT can read or resume any `thread_id` via the thread API. This is a known gap — see Section 11 (Redesign Recommendations).

### 6.2 Tool Allowlists

Three sources merged in `tool_policy.py`:
1. `WorkflowRequest.allowed_tools` (per-request override, highest priority)
2. Project config `agents.allowed_tools` (per-project)
3. `DIGI_ALLOWED_TOOLS` env var (per-deployment)

When an allowlist is active, `execute()` in `registry.py:106` rejects denied tools with an audit log entry (`tool_denied` event). The schema-level filter in `get_tools()` also removes denied tools from the LLM context, preventing the model from attempting to call them.

An allowlist of `[]` (empty list) blocks all tools, forcing research-only mode. `None` means unrestricted.

### 6.3 Code Execution Gate

`policy.code_execution_allowed()` gates the `data_engineer_agent` tool (`DIGI_ALLOW_CODE_EXEC=1`). When disabled, the agent runner should check this flag before executing sandboxed Python. The policy check is defined but the enforcement in `agents/data_engineer/runner.py` must be verified to actually call this function before executing code — the gate exists but the execution path was not traced end-to-end in this review.

### 6.4 Thread State Access

`GET /threads/{thread_id}/state` requires `DIGI_ENABLE_THREAD_API=1` but performs no subject-binding check. Any request with a valid JWT (or no JWT in passthrough mode) can read any thread's state. The `_THREAD_STATE_KEYS` allowlist (`server.py:249`) limits which state keys are returned, but `stored_datasets`, `research_response`, `research_note`, `error`, `backtest_result`, `strategy_name`, and `symbols` are all exposed.

**Risk:** In a multi-tenant deployment, tenant A can read tenant B's research output and dataset refs if they know or guess the `thread_id`. Since `thread_id` defaults to `session_id` (which defaults to `"default"`), all sessions without an explicit `session_id` share a single checkpoint namespace.

### 6.5 Debug Endpoint Risks

`GET /v1/debug/input_messages` returns the last 5 chat completion request summaries, including the first 400 characters of the prompt. This is stored in a module-level global (`_DEBUG_REQUEST_LOG` in `server.py:16`) shared across all requests. In a multi-tenant deployment with the debug endpoint enabled, a second tenant can read another tenant's prompt preview. The endpoint should be disabled in production (`DIGI_ENABLE_DEBUG_ENDPOINTS` defaults to `0` in Compose).

### 6.6 Streaming Cancellation Gap

When a client disconnects from an SSE stream, the background thread (`run_digigraph_workflow_streaming`) continues executing until it completes or errors. There is no cancellation mechanism — no `threading.Event`, no exception injection into the thread. Under high load, many orphaned workflow threads can accumulate, each holding LLM connections and potentially making outbound HTTP calls to DigiSearch and DigiQuant. The `Queue.get()` in `_stream_completions_progressive` will eventually raise a `GeneratorExit` exception (when the generator is garbage-collected), which surfaces as a logged exception in the generator but does not stop the background thread.

### 6.7 Rate Limiter Trust Boundary

The `RateLimiter._get_ip()` method trusts `X-Forwarded-For` without validation. A client can set `X-Forwarded-For: 1.2.3.4` to impersonate any IP and bypass per-IP rate limits. In a Docker Compose deployment behind a reverse proxy, this is acceptable only if the proxy strips or overrides the header before it reaches DigiGraph. Currently there is no proxy in the default Compose stack — DigiGraph is directly exposed on `127.0.0.1:8000`.

### 6.8 MCP Server Auth Gap

The MCP server (`mcp_server.py`) has no built-in authentication layer. The `streamable-http` transport binds to `0.0.0.0:8766` by default, making it network-accessible. The `workflow` and `chat` MCP tools invoke the workflow directly (bypassing HTTP middleware including `DigiAuthMiddleware`). Operators must use network policy or a gateway in front of the MCP server.

### 6.9 Manifest Cache Never Invalidates

The vertical manifest caches in `digisearch_hub.py` and `digiquant_hub.py` are module-level dicts with no TTL or invalidation. If DigiSearch or DigiQuant adds, removes, or changes a tool definition, the cached schema is stale until the DigiGraph process restarts. This affects tool schema accuracy in long-running deployments.

---

## 7. Scalability Analysis

### 7.1 Shared In-Process Checkpointer (Single-Node Constraint)

The `MemorySaver` default stores all thread state in a Python dict in the DigiGraph process. Multiple DigiGraph replicas cannot share this state. SQLite is similarly single-process. Only the Postgres backend supports horizontal scaling, but even with Postgres, there is no distributed locking: two concurrent requests for the same `thread_id` can produce conflicting checkpoint writes.

**Practical limit:** A single DigiGraph instance can handle concurrent requests limited by the Python GIL + thread pool size. Each streaming request holds a thread for the duration of the workflow (potentially 30–120 seconds for backtest-inclusive flows). The default FastAPI thread pool is CPU-count × 5; large backtests can saturate it quickly.

### 7.2 In-Memory Rate Limiter

`RateLimiter` uses an in-process `dict[str, deque]` protected by a single `threading.Lock`. This works for a single process but:
- State is lost on restart (all rate limit windows reset)
- Multiple replicas have independent limits, so the effective rate is multiplied by the replica count
- The lock is a single point of contention under high request rates

### 7.3 Graph Compilation Per Request

`build_workflow_graph()` is called inside `run_digigraph_workflow()` on every invocation. LangGraph compiles the graph (creates the `CompiledStateGraph` object, resolves edges and node references) on each call. This is unnecessary overhead — the compiled graph object is immutable and could be cached as a module-level singleton, reusing the shared checkpointer.

### 7.4 Vertical Manifest HTTP Blocking

`fetch_digisearch_tool_dicts` and `fetch_digiquant_tool_dicts` make synchronous `httpx` calls at schema resolution time, inside FastAPI's synchronous thread pool. If DigiSearch or DigiQuant is slow or unavailable, this blocks a worker thread for up to 30 seconds (`timeout=30.0`). The first request after startup or cache invalidation pays this cost.

### 7.5 Postgres Checkpoint Path

When `DIGI_CHECKPOINTER=postgres`, the `PostgresSaver` is initialized synchronously via `__enter__()` and `.setup()` at first request time. This is a blocking operation. Across multiple replicas, each instance runs `setup()` independently (schema migration idempotency depends on `langgraph-checkpoint-postgres` implementation).

### 7.6 Horizontal Scaling Gap Summary

| Concern | Current State | Required for Horizontal Scale |
|---------|--------------|-------------------------------|
| Checkpoint storage | In-process dict | Postgres with advisory locks |
| Rate limiting | In-process deque | Redis or shared store |
| Graph compilation | Per-request | Module-level singleton |
| Manifest cache | Per-process, no TTL | Shared cache (Redis) or short TTL |
| Streaming thread lifetime | Unbounded | Cancellation via event/token |

---

## 8. Performance Analysis

### 8.1 LLM Response Cache

`llm.py` implements an in-process SHA-256 keyed cache for non-tool `chat_completion` calls:
- Cache key: `sha256(json.dumps({model, messages, temperature}, sort_keys=True))`
- TTL: configurable via `DIGI_LLM_CACHE_TTL_SECONDS` (default 3600s)
- Capacity: 256 entries, FIFO eviction on overflow
- Exclusions: calls with `tools` (side effects) are never cached

This provides meaningful speedup for repeated identical prompts (e.g. heartbeat probes, repeated research queries). Tool calls and streaming completions bypass the cache. The 256-entry FIFO eviction is a weak strategy — LRU or LFU would have better hit rates for diverse workloads.

### 8.2 Model Mode System

`get_model_for_mode()` reads `config/model_modes.yaml` on every call via `_load_model_modes()`. The file is opened, parsed with PyYAML, and discarded. For high-throughput deployments, this should be cached. The mode itself is re-read from env/config on every LLM call to pick up runtime changes.

Three modes: `test` (minimal), `medium` (balanced), `best` (largest). The project config YAML `agents.llm_mode` overrides `DIGI_LLM_MODE`.

### 8.3 Digistore for LLM Context Reduction

Search results from DigiSearch are written to `{run_data_dir}/{session_id}/datasets/` as JSON files. Only a compact preview (5 rows × 300 chars) is injected into the LLM context (`_search_payload_for_llm` in `builtin.py:58`). The full dataset is referenced by `dataset_ref` and loaded on demand by agent runners. This implements the "≥70% token reduction vs naive prompts" target from the architecture principles.

### 8.4 Parallel Tool Execution

When the LLM returns multiple tool calls in one turn and all tools are tagged `parallel_safe` (currently: `visualization_agent`, `analysis_agent`, `data_prep_agent`, `data_manipulation_agent`, `data_engineer_agent`, delegate tools), they are dispatched in parallel via `ThreadPoolExecutor(max_workers=len(parsed))` in `llm.py:492`. Tool results are appended to the conversation in original order. This reduces multi-tool latency from O(n×tool_time) to O(max_tool_time).

### 8.5 SSE Streaming for Time-to-First-Token

Streaming via the background thread + queue delivers tool call blocks to the client as soon as each tool completes, rather than waiting for the full workflow. Reasoning content is buffered and delivered as a `<thinking>` block just before the first `content` chunk — this means reasoning latency adds to the first visible token time.

### 8.6 OpenAI Client Connection Pooling

`get_client()` caches `OpenAI` instances by `(api_key, base_url)`. The `OpenAI` SDK uses an `httpx.Client` with connection pooling under the hood, avoiding per-request TCP handshakes. The cache is invalidated when env vars change, which covers test scenarios with different API keys.

---

## 9. Integration Points

### 9.1 DigiSearch

**Protocol:** HTTP via `digisearch_hub.py`

- **Manifest:** `POST /v1/orchestrator_tools` — returns OpenAI tool dicts for `digisearch`, `digisearch_fetch_all`, `digisearch_research_delegate` (federated mode). Cached per `(base_url, index_config)`.
- **Invoke:** `POST /v1/orchestrator_invoke` — dispatches tool execution. Accepts `{tool, arguments, default_index_name}`.
- **Legacy:** `tools/digisearch.py` uses `POST /query` for non-orchestrator call sites (e.g. `_run_quant_or_augmented_path` in `research.py`).
- **Auth:** Bearer token from `WorkflowState.digi_bearer` is forwarded via `Authorization: Bearer` header.
- **Request correlation:** `X-Request-ID` forwarded from `ToolContext.request_id`.
- **Filters:** `research_filters` and `evidence_tier_preference` from state are merged into every DigiSearch call by `_merged_digisearch_filters` in `builtin.py:34`.
- **Env:** `DIGISEARCH_URL` (required; empty = DigiSearch tools disabled). In Docker: `http://digisearch:8002`.

### 9.2 DigiQuant

**Protocol:** HTTP via `digiquant_hub.py` (federated mode) + direct `httpx` in `graph/nodes.py` (backtest/optimize nodes)

- **Manifest:** `POST /v1/orchestrator_tools` — returns tool dicts for `digiquant_pipeline_delegate`. Cached per `base_url`.
- **Invoke:** `POST /v1/orchestrator_invoke` — dispatches pipeline tool. Timeout: 600s.
- **Backtest node (direct):** Tries `POST /v1/jobs/backtest` first; falls back to `POST /backtest/start` + SSE progress, then `POST /run_backtest`. Polls `GET /v1/jobs/{id}/status` for async jobs; fetches result via `GET /backtest/{id}/result`.
- **Optimize node (direct):** `POST /run_optimize`. Timeout: 300s.
- **Auth:** Bearer via `outbound_service_headers(request_id, bearer)` from `digibase.http`.
- **Env:** `DIGIQUANT_URL` (default `http://127.0.0.1:8001`). `DIGIQUANT_DATA_DIR` required for backtest and optimize nodes.

### 9.3 DigiKey

**Protocol:** JWT validation middleware (in-process)

- `DigiAuthMiddleware` from `digikey.integrations.service_middleware` validates JWTs on every non-health request.
- Configuration: `DIGIKEY_JWKS_URL` (JWKS endpoint, e.g. `http://digikey:8005/.well-known/jwks.json`) or `DIGIKEY_PUBLIC_KEY_PEM`.
- `DIGIKEY_ISSUER` and `DIGIKEY_AUDIENCE` for claim validation.
- The middleware populates `request.state.digi_auth` (key_prefix, tenant_slug, project_id, jti) and `request.state.digi_bearer` (raw token) for downstream use.
- Per-request LiteLLM proxy key override: `X-LiteLLM-Proxy-Key` header is parsed by the `lite_llm_proxy_header_context` middleware and stored in a `ContextVar` for use by `get_client()`.

### 9.4 DigiSmith

**Protocol:** Library calls (no HTTP)

- `digismith.trace.traceable` is a decorator applied to `chat_completion` and `chat_completion_with_tools` in `llm.py`.
- Activates when `LANGSMITH_API_KEY` is set and `langsmith` is installed.
- Span attributes must include `workflow_id`, `request_id`, `session_id`. Raw prompts, API keys, and full doc bodies must not appear in spans.
- In Docker Compose, a DigiSmith container exposes `GET /v1/status` on port 8003. DigiGraph does not make HTTP calls to DigiSmith; the library communicates with LangSmith directly.

### 9.5 DigiChat

**Protocol:** HTTP (DigiChat → DigiGraph)

- DigiChat (Next.js BFF) proxies browser requests to `POST /v1/chat/completions` with `stream: true`.
- DigiChat forwards `X-Session-Id` (browser session), `X-LiteLLM-Proxy-Key` (from DigiKey token exchange), and `X-Allowed-Tools` headers.
- The `_digi_fields_from_request` helper in `server.py:145` extracts DigiKey JWT fields from middleware state and injects them into `WorkflowRequest` for audit correlation.
- DigiChat receives `digigraph_trace` SSE deltas in `delta.digigraph_trace` for tool block rendering.
- Internal URL in Docker: `DIGIGRAPH_INTERNAL_URL=http://digigraph:8000`.

### 9.6 LiteLLM

**Protocol:** OpenAI SDK to LiteLLM proxy

- DigiGraph's `get_client()` creates an `OpenAI` instance pointed at `OPENAI_API_BASE` (default: `http://litellm:4000/v1` in Docker).
- All LLM calls (research, brief builder, synthesis) go through LiteLLM, which routes to Ollama, OpenAI, or other configured providers.
- Model selection: `get_model_for_mode()` returns the model ID from `config/model_modes.yaml` for the current mode. LiteLLM translates provider-prefixed IDs (e.g. `ollama/qwen3:8b`) to the target provider's expected format.
- Caching: LiteLLM supports Redis-backed semantic caching when `REDIS_URL` is set (Compose profile: `litellm-cache`).

---

## 10. Docker and MCP Composition

### 10.1 Docker Compose Service Definition

```yaml
digigraph:
  image: digi-digigraph:latest
  ports:
    - "127.0.0.1:8000:8000"      # loopback only
  depends_on:
    digikey, digiquant, digisearch, litellm  # all healthy before start
  healthcheck:
    GET http://127.0.0.1:8000/health
    interval: 15s, timeout: 5s, retries: 3, start_period: 10s
  volumes:
    - ./config:/app/config:ro    # model_modes.yaml, litellm.yaml read-only
    - ./digiquant/results/audit:/audit  # audit JSONL
```

### 10.2 Environment Variables

| Variable | Default (Compose) | Description |
|----------|------------------|-------------|
| `DIGIQUANT_URL` | `http://digiquant:8001` | DigiQuant HTTP base URL |
| `DIGISEARCH_URL` | `http://digisearch:8002` | DigiSearch HTTP base URL; empty = search disabled |
| `DIGISMITH_URL` | `http://digismith:8003` | DigiSmith status URL (unused by DigiGraph HTTP) |
| `DIGIKEY_JWKS_URL` | `http://digikey:8005/.well-known/jwks.json` | JWT public key endpoint |
| `DIGIKEY_ISSUER` | `http://digikey:8005` | JWT issuer claim |
| `DIGIKEY_AUDIENCE` | `digi-ecosystem` | JWT audience claim |
| `DIGIKEY_PUBLIC_KEY_PEM` | (empty) | Static PEM alternative to JWKS |
| `OPENAI_API_BASE` | `http://litellm:4000/v1` | LLM proxy base URL |
| `OPENAI_API_KEY` | (from `.env`) | API key for LLM proxy (fallback to `LITELLM_PROXY_API_KEY`) |
| `LITELLM_PROXY_API_KEY` | (from `.env`) | LiteLLM bearer; overrides `OPENAI_API_KEY` for proxy calls |
| `DIGI_LLM_MODE` | `test` | LLM model tier: `test` / `medium` / `best` |
| `DIGI_CONFIG_PATH` | `/app/config` | Directory containing `model_modes.yaml` |
| `DIGI_PROJECT_CONFIG` | (empty) | Path to project YAML (optional) |
| `DIGI_CHECKPOINTER` | `memory` | Checkpointer backend: `memory` / `sqlite` / `postgres` / `none` |
| `DIGI_CHECKPOINTER_SQLITE_URI` | `~/.digigraph/checkpoints.sqlite` | SQLite file path |
| `DIGI_CHECKPOINTER_POSTGRES_URI` | (empty) | Postgres connection string |
| `DIGIQUANT_DATA_DIR` | `/app/data` | Path to CSV files for backtests |
| `DIGISEARCH_INDEX` | `default` | Default vector index name |
| `DIGI_ENABLE_DEBUG_ENDPOINTS` | `0` | Enable `/test_llm` and `/v1/debug/*` |
| `DIGI_ENABLE_THREAD_API` | `0` | Enable `/threads/*` and `/files/*` |
| `DIGI_SUPERVISOR` | (empty) | Enable supervisor node: `1` / `true` |
| `DIGI_HUB_MODE` | `legacy` | Hub mode: `legacy` (default) or `federated` |
| `DIGI_WORKFLOW_PROFILE` | `full_stack` | Workflow profile when not set in project config |
| `DIGI_ALLOWED_TOOLS` | (empty) | Comma-separated allowlist (env fallback) |
| `DIGI_ALLOW_CODE_EXEC` | (empty) | Enable `data_engineer_agent` code execution: `1` / `true` |
| `DIGI_RUN_DATA_DIR` | (empty) | Session dataset storage; enables `sitaas_rag` skill |
| `DIGI_DISABLE_RATE_LIMIT` | (empty) | Disable rate limiting for tests/dev |
| `DIGI_CORS_ORIGINS` / `DIGIGRAPH_CORS_ORIGINS` | (empty) | CORS allowlist — applied via shared `digibase.cors.install_cors`. `DIGI_ALLOWED_ORIGINS` still honored as legacy fallback. See `SECURITY.md` §"CORS policy". |
| `DIGI_TOOL_MESSAGE_MAX_CHARS` | `12000` | Max chars per tool result message to LLM |
| `DIGI_LLM_CACHE_TTL_SECONDS` | `3600` | LLM response cache TTL |
| `DIGI_INTERRUPT_AFTER_RESEARCH` | (empty) | Interrupt graph after research for HITL: `1` |
| `DIGI_REQUIRE_TRADING_PROFILE` | (empty) | Require `trading_profile` for backtest: `1` |
| `DIGI_GRAPH_OPTIMIZE_AFTER_BACKTEST` | (empty) | Run optimize after every backtest: `1` |
| `DIGI_SUPERVISOR_MAX_DEPTH` | `8` | Max supervisor routing depth |
| `DIGIQUANT_OPTIMIZE_METHOD` | `grid` | Default optimization method |
| `DIGIQUANT_OPTIMIZE_N_TRIALS` | `50` | Default optimization trial count |
| `AUDIT_LOG_PATH` | `/audit/events.jsonl` | JSONL audit log output path |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (empty) | OTel OTLP exporter endpoint (optional) |
| `LANGSMITH_API_KEY` | (from `.env`) | LangSmith tracing key (optional) |

### 10.3 MCP Server Startup

```bash
# Streamable HTTP (default, port 8766)
python -m digigraph.mcp_server

# Stdio (Claude Desktop)
python -m digigraph.mcp_server --stdio

# Custom host/port
python -m digigraph.mcp_server --host 127.0.0.1 --port 8766
```

Installation prerequisite: `pip install -e "digigraph[mcp]"` (installs `mcp` package with `FastMCP`).

The MCP server is a separate process from the FastAPI HTTP server. It does not share the same HTTP middleware stack — auth, rate limiting, and CORS apply only to HTTP clients.

---

## 11. Phase 2+ Gaps and Roadmap

The following are explicitly documented as roadmap items:

| Feature | Gap | Current Workaround |
|---------|-----|-------------------|
| **Graphiti graph memory** | Not implemented; `ARCHITECTURE.md` describes Neo4j + Graphiti for temporal strategy memory | Strategies are not persisted between conversations |
| **Remote MCP enumeration** | DigiGraph cannot discover or integrate arbitrary third-party MCP servers | Only in-process registry + DigiSearch/DigiQuant vertical HTTP |
| **OpenAI Responses API** | Not implemented; Chat Completions is the only LLM protocol | LiteLLM `/v1/responses` compatibility noted as future path |
| **Distributed checkpoints** | MemorySaver/SQLite are single-node; Postgres has no advisory locks | Single DigiGraph instance |
| **Per-user RBAC** | JWT subject not bound to checkpoint or tool access | Shared `thread_id` namespace; allowlists are per-request not per-user |
| **Auth-bound checkpoints** | `thread_id` is caller-supplied; no ownership enforcement | Trust the client not to use other users' thread IDs |
| **Request cancellation** | No mechanism to cancel in-flight streaming workflows | Background threads run to completion |
| **DigiClaw subgraph exposure** | DigiClaw can attach only to the hub, not to vertical MCP servers directly | DigiClaw calls `/workflow` only |

---

## 12. Redesign Recommendations

The following are critical recommendations based on observed architectural gaps:

### 12.1 Distributed Checkpointing with Postgres Advisory Locks

**Problem:** Multiple DigiGraph replicas with shared Postgres checkpoints can interleave writes to the same `thread_id`, corrupting state.

**Recommendation:** Wrap each `graph.invoke()` call with a Postgres advisory lock keyed on `hash(thread_id)`. The `PostgresSaver` in `langgraph-checkpoint-postgres` does not implement this. A thin wrapper should acquire an advisory lock before `invoke` and release it in a `finally` block. Use `pg_try_advisory_xact_lock` for timeout semantics. This enables true horizontal scaling with guaranteed per-thread serialization.

### 12.2 Per-Request Cancellation Tokens

**Problem:** Client disconnects leave orphaned workflow threads consuming LLM tokens and downstream service connections indefinitely.

**Recommendation:** Introduce a `threading.Event` per streaming request. Pass it into `run_digigraph_workflow_streaming` as a `cancel_event` argument. The research tool loop should poll `cancel_event.is_set()` between tool rounds (after each `event_queue.put`). The streaming generator should set the event when it detects client disconnect (when `StreamingResponse` generator raises `GeneratorExit`). This bounds the maximum waste to one tool round's latency.

### 12.3 Thread State Scoping to DigiKey JWT Subject

**Problem:** Any authenticated caller can read any thread's state. In multi-tenant deployments, `session_id` collisions (especially `"default"`) expose one tenant's data to another.

**Recommendation:** Prefix `thread_id` with the JWT `sub` claim extracted from `request.state.digi_auth`. In `workflow.py:_initial_graph_state`, set the LangGraph config `thread_id` to `f"{jwt_sub}:{session_id}"` when a subject is available. The thread state endpoints should enforce that the `thread_id` path parameter matches the caller's `sub` prefix. This provides tenant isolation without requiring a separate authorization database.

### 12.4 Sandboxed Code Execution

**Problem:** `data_engineer_agent` executes arbitrary Python code (Polars operations). Even with `DIGI_ALLOW_CODE_EXEC` as a gate, the execution is in the same process as DigiGraph with access to all environment variables (including API keys) and the full filesystem.

**Recommendation:** Isolate `data_engineer_agent` code execution in a subprocess or container with:
- A restricted Python environment (no `os`, `subprocess`, `importlib`, `socket` imports)
- A separate working directory mounted from `run_data_dir` only
- A CPU/memory/time limit (e.g. via `resource.setrlimit` in the subprocess)
- Environment variable scrubbing (clear `OPENAI_API_KEY`, `LITELLM_PROXY_API_KEY`, etc. before the subprocess starts)

Until this is implemented, `DIGI_ALLOW_CODE_EXEC` should default to `0` and operators should understand the risk.

### 12.5 Streaming Backpressure Mechanism

**Problem:** If the SSE consumer is slower than the workflow thread produces events, the `Queue` accumulates unboundedly. Under high streaming concurrency, this can exhaust memory.

**Recommendation:** Replace `Queue()` with `Queue(maxsize=N)` (e.g. 256). The `stream_callback` in `workflow.py` should use `event_queue.put_nowait` with a `Full` exception handler that drops trace events (lower priority) or blocks for content events. Alternatively, use a bounded queue with a timeout on `put` that triggers workflow abort via the cancellation event from recommendation 12.2.

### 12.6 Prometheus Metrics Endpoints

**Problem:** There are no observable performance or business metrics exported from DigiGraph. Operators cannot measure request latency, LLM cache hit rates, tool call counts, or streaming session counts without parsing logs.

**Recommendation:** Add `prometheus-client` as a dependency. Expose `GET /metrics` (Prometheus text format) with:
- `digigraph_workflow_duration_seconds` (histogram, labels: profile, has_backtest)
- `digigraph_llm_cache_hits_total` / `digigraph_llm_cache_misses_total`
- `digigraph_tool_calls_total` (labels: tool_name, status)
- `digigraph_active_streaming_sessions` (gauge)
- `digigraph_rate_limit_rejections_total` (labels: path)

This complements DigiSmith's LangSmith tracing with operational metrics visible to Grafana or similar systems.

### 12.7 Compiled Graph Cache

**Problem:** `build_workflow_graph()` is called on every `run_digigraph_workflow` invocation. LangGraph graph compilation is not free — it resolves all node references and edge conditions.

**Recommendation:** Cache the compiled graph as a module-level singleton, invalidated only when `DIGI_SUPERVISOR`, `DIGI_CHECKPOINTER`, `DIGI_INTERRUPT_AFTER_RESEARCH`, or related env vars change. The checkpointer instance is already a singleton; the compiled graph should be too.

### 12.8 X-Forwarded-For Validation

**Problem:** The rate limiter trusts `X-Forwarded-For` without validation (see Section 6.7).

**Recommendation:** Add a `DIGI_TRUSTED_PROXIES` env var (CIDR list). Only trust `X-Forwarded-For` when the actual `request.client.host` is in the trusted proxy list. Otherwise, use `request.client.host` directly. This prevents IP spoofing of rate limits.

## Observability

This service exposes a Prometheus `/metrics` endpoint (counter, histogram, in-flight gauge for every HTTP route) via `digibase.metrics.install_metrics`; scraped by the `observability` compose profile per [ADR-0003](../docs/adr/0003-observability-baseline.md).
