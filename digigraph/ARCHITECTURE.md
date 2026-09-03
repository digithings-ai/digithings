# digigraph Architecture

**Service:** digigraph
**Port:** 8000 (HTTP), 8766 (MCP streamable-http)
**Role:** Orchestration hub — LangGraph state machine, tool registry, OpenAI-compatible API, SSE streaming
**Status:** Phase 1 implemented; Phase 2 features (Graphiti memory, remote MCP enumeration, distributed checkpoints) are roadmap items

---

## 1. Overview

digigraph is the central orchestration brain of the digithings stack. Every user request flows through it: from digiclaw (gateway), from digichat (Next.js BFF), from Open WebUI (OpenAI-compatible model), or directly from Claude Desktop (MCP). digigraph owns three distinct roles:

1. **LangGraph state machine.** Maintains a compiled `StateGraph[WorkflowState]` that routes through research, strategy validation, backtest, and optional optimize nodes. Profile-driven conditional edges control which path executes.

2. **Tool registry and dispatcher.** Provides an in-process registry of named orchestrator tools (search, agents, digistore introspection, planning primitives). Verticals (digisearch, digiquant) own their own OpenAI tool schemas, published via `POST /v1/orchestrator_tools`; digigraph fetches those schemas lazily and invokes them via `POST /v1/orchestrator_invoke`.

3. **HTTP + MCP API surface.** Exposes a `POST /workflow` endpoint (digiclaw custom skill), a `POST /v1/chat/completions` endpoint (Open WebUI / digichat), thread state APIs (opt-in), and an MCP server for Claude Desktop and digiclaw agent integration.

digigraph is deliberately minimal as a hub: it does not implement the quant pipeline ordering (owned by digiquant) or tiered RAG (owned by digisearch). It coordinates them.

---

## 2. Current Implementation State

The following is built and functional as of this architecture review (March 2026):

| Area | State | Key Files |
|------|-------|-----------|
| FastAPI HTTP app | Built | `server.py` |
| LangGraph `StateGraph[WorkflowState]` | Built | `graph/graph.py`, `graph/state.py` |
| Research subgraph (LLM + tool loop) | Built | `graph/research.py`, `graph/research_subgraph.py` |
| Two-tier context compaction | Built | `compaction.py` (wired from `graph/research.py`, `graph/research_agent.py`) |
| Research brief builder | Built | `graph/research_brief.py`, `research_brief_models.py` |
| Backtest node (digiquant jobs + fallback) | Built | `graph/nodes.py` |
| Optimize node | Built | `graph/nodes.py` |
| Supervisor node (opt-in via `DIGI_SUPERVISOR=1`) | Built | `graph/nodes.py` |
| Orchestrator tool registry | Built | `orchestration/registry.py` |
| Built-in tools + skills | Built | `orchestration/builtin.py` |
| Vertical hub clients (digisearch, digiquant, digivault) | Built | `vertical_orchestrator/digisearch_hub.py`, `vertical_orchestrator/digiquant_hub.py`, `vertical_orchestrator/digivault_hub.py` |
| SSE streaming via background thread + queue | Built | `server.py`, `workflow.py` |
| LLM client (OpenAI SDK, LiteLLM compat) | Built | `digillm` (toolkit) + `llm_client.py` wrappers |
| In-process LLM response cache (SHA-256, TTL) | Built | `digillm` |
| Parallel tool execution for `parallel_safe` tools | Built | `digillm` (`run_tools`); set computed in `llm_client.py` |
| digiauth JWT middleware (digikey) | Built | `server.py` (via `digikey.integrations.service_middleware`) |
| Per-IP sliding-window rate limiter | Built | `rate_limit.py`, `server.py` |
| Correlation ID middleware (`X-Request-ID`) | Built | `server.py` |
| Tool allowlist enforcement | Built | `orchestration/registry.py`, `tool_policy.py` |
| Policy flags (code exec, debug, thread API) | Built | `policy.py` |
| digistore (session-scoped named datasets) | Built | `digistore.py`, `run_storage.py` |
| MCP server (FastMCP, streamable-http + stdio) | Built | `mcp_server.py` |
| Thread state / history / resume endpoints (opt-in) | Built | `server.py` |
| digismith tracing (`traceable` wrappers) | Built | `digillm` (via `digismith.trace.traceable`) |
| OpenTelemetry export (opt-in) | Built | `server.py` (via `digibase.otel.setup_otel_fastapi`) |
| Ordered body-free run call events | Built | `usage.py`, `graph/research_agent.py`, `digillm` observer |
| Logical provider-call purpose and lineage | Built | `llm_client.py`, `usage.py`, `graph/research_agent.py`, `digillm` contracts |
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
| `POST` | `/workflow` | digikey JWT (optional) | 10 req/min/IP | digiclaw custom skill; body: `WorkflowRequest` |
| `GET` | `/v1/models` | digikey JWT (optional) | 30 req/min/IP | OpenAI model list; returns `digigraph-rag` |
| `GET` | `/v1/model-info` | digikey JWT (optional) | 30 req/min/IP | Current model + mode |
| `POST` | `/v1/chat/completions` | digikey JWT (optional) | 10 req/min/IP | OpenAI chat completions; body: `ChatCompletionRequest`; supports `stream: true` |
| `GET` | `/v1/debug/input_messages` | digikey JWT | 30 req/min/IP | Last N request summaries; **requires `DIGI_ENABLE_DEBUG_ENDPOINTS=1`** |
| `GET` | `/test_llm` | digikey JWT | 30 req/min/IP | LLM connectivity test; **requires `DIGI_ENABLE_DEBUG_ENDPOINTS=1`** |
| `GET` | `/threads/{thread_id}/state` | digikey JWT | 30 req/min/IP | LangGraph checkpoint state; **requires `DIGI_ENABLE_THREAD_API=1`** |
| `GET` | `/threads/{thread_id}/history` | digikey JWT | 30 req/min/IP | Full checkpoint history; **requires `DIGI_ENABLE_THREAD_API=1`** |
| `POST` | `/threads/{thread_id}/resume` | digikey JWT | 30 req/min/IP | Resume interrupted workflow; **requires `DIGI_ENABLE_THREAD_API=1`** |
| `GET` | `/files/{path:path}` | digikey JWT | 30 req/min/IP | Serve exported files from `run_data_dir`; **requires `DIGI_ENABLE_THREAD_API=1`** |

Auth is enforced by `DigiAuthMiddleware` from `digikey.integrations.service_middleware`. Path-scope mappings are defined in `digigraph_path_scopes`. When `DIGIKEY_JWKS_URL` or `DIGIKEY_PUBLIC_KEY_PEM` is unset, the middleware operates in passthrough mode.

Rate limits are per-IP (sliding window, in-process `deque`). `X-Forwarded-For` is honored only from a configured trusted proxy (`DIGI_TRUSTED_PROXIES`) and validated before use — see Section 12.8 for the extraction algorithm and Section 6 (Security Analysis) for the trust-boundary discussion.

A request that opts into `require_tool_calls=true` (body field or `X-Require-Tool-Calls` header — see §6.2.1) is metered by a **second, stricter** per-IP budget on top of the 10 req/min above: `_enforce_require_tool_calls_budget` in `server.py`, default 3 req/min, overridable via `DIGI_REQUIRE_TOOL_CALLS_RATE_LIMIT_MAX`. Forcing `tool_choice="required"` reliably exhausts all `max_tool_rounds` completions instead of returning after one — a ~4-5x LLM-spend multiplier any caller with plain `digigraph:chat` scope can opt into per request — so the two budgets are checked independently and either can 429 the request. A deployment that itself mandates `require_tool_calls` via project config / `DIGI_REQUIRE_TOOL_CALLS` isn't newly constrained by this: the budget only meters a request's own opt-in signal, not the resolved floor.

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

1. A background `threading.Thread` runs `run_digigraph_workflow_streaming` with a `Queue` as the event sink (`workflow.py:340`). The target is wrapped in `contextvars.copy_context().run(...)` taken at spawn, because a bare `Thread` starts with an **empty** context: without the copy every per-request `ContextVar` — including all three BYOK bindings `push_byok_header` sets (`llm_auth.py`) — reads as its default inside the worker, so a streaming BYOK request was answered on the operator's key and the operator's model while the user's key was shown as active. The copy is taken in the generator frame, which still holds the bindings; the worker has no `Request` to re-read them from. Because the copy outlives the request — the thread is neither daemonic nor joined, and `byok_header_context`'s `finally` runs `pop_byok` as soon as streaming starts, resetting the *parent's* vars only — the worker calls `clear_byok_bindings()` in its own `finally`, so the user's key does not stay resident in a context copy after the request it came from is gone. (Distinct from the `ThreadPoolExecutor` note in §4.0 — same root cause, different subsystem, and dashboard passes labels explicitly instead.)
2. The HTTP response is a `StreamingResponse` whose generator consumes the queue and yields SSE chunks.
3. Event types produced by the workflow thread:
   - `tool_call` / `tool_result` — formatted with the stream formatter (neutral or Open WebUI `<details>` style)
   - `content` — LLM token deltas, HTML-escaped
   - `reasoning` — accumulated into a `<thinking>` block before the first `content` chunk (skipped when `X-Suppress-Tool-Stream` is set)
   - `trace` — `TraceEventV1` dicts embedded in `delta.digigraph_trace` for digichat
     (`tool_call` / `tool_result` / `rag_sources` / `round_boundary`, …). The
     `round_boundary` event marks the end of a digillm tool round: `round_idx` is the
     zero-based round number, and `narration` is the assistant text produced that round
     (with `stream_deltas`, content deltas were already emitted; without streaming,
     `round_boundary` is the only callback that exposes that narration).
   - `done` — terminates the generator loop
4. If the client disconnects mid-stream, the generator sets the `threading.Event` it passed the worker (`server.py`, on both `GeneratorExit` and the generator's `finally`). The worker polls it between graph nodes, and — since the event queue is bounded and the generator stops draining it on disconnect — every event the worker emits goes through `workflow._emit_event`, which drops the event rather than blocking once the event is set. Without that, a full queue would wedge the worker *inside* a node forever, so the bound below would not hold at all. Overshoot is therefore bounded by one node — not zero, since there is still no interrupt injected into a node already in flight. See §6.6.

---

## 4. Data Model

### 4.0 dashboard call-event capture

`usage.start()` activates ordered aggregate events and a temporary, lock-protected detailed
telemetry buffer for an dashboard process. `digillm` contributes terminal model/search events;
`graph/research_agent.py` times actual tool execution. `call_context(node_run_id, phase, operation,
document_key)` labels model/search calls, while the tool wrapper also passes display labels
explicitly because `ContextVar` state does not propagate into `ThreadPoolExecutor` workers
on its own. That is a property of the pool, not of dashboard: the two pools on the *credential*
path (§8.4, `planning/executor.py` and `digillm.run_tools`) submit through
`contextvars.copy_context().run(...)` instead, which is the alternative to threading the value
through by hand. dashboard keeps the explicit labels — passing a display string is cheaper than
a context copy and does not silently widen what a worker inherits.

`RunCallEvent` is a frozen Pydantic v2 model. It stores fixed labels, status, duration, retries,
usage totals, source count, and code-generated shape summaries. All public text is length-bounded.
It never stores prompts, argument or result values, document bodies, credentials, PII-heavy
values, model output, or chain-of-thought. `events_snapshot()` returns the ordered body-free
records; aggregate `snapshot()` includes them under `events` for the research diagnostics writer.

#### Logical provider-call boundary

**Purpose:** label each logical provider invocation with generic intent, parentage, and artifact
disposition. **Reason:** the aggregate explains run totals and physical attempts explain transport,
but neither explains why a call existed or which prior call caused a repair or follow-up.
**Intent:** make provider work attributable without moving dashboard policy into digigraph or adding
nodes to the canonical graph. **System contribution:** detailed usage, artifact linkage, and later
research-policy evaluation can share one stable lineage.

`llm_client.py` registers `usage.DETAILED_USAGE_OBSERVER` process-wide and wraps digillm entry
points with `provider_call_context(...)` only when `call_context` contains a real `node_run_id`.
No placeholder identity is generated. `logical_call_context(...)` may override generic purpose,
parent, artifact references, and no-artifact reason for a nearby call. Defaults distinguish initial
generation, structured completion, tool selection/follow-up, web grounding, and X grounding;
`graph/research_agent.py` marks validation retries as structured repairs and links each repair to
the rejected call ID. Structured calls defer successful logical-record delivery until Pydantic
validation assigns the final disposition, so a rejected parent is appended once as
`validation_rejected`; provider failures and cancellations remain immediate terminal records.

`detailed_usage_projection()` is a temporary reconciliation view, not a second accounting ledger.
It selects one terminal successful physical attempt for each successful non-cache logical call so
its call/token/cost totals match the incumbent one-event aggregate where provider evidence exists.
Retries remain present in detailed attempt records, cache hits remain explicit zero-attempt logical
calls, and any unavailable token or cost value makes the corresponding projection value `None`
rather than fabricated zero.

Collector and observer failures are fail-soft and cannot change cache ordering, retry/backoff,
routing, tool execution, return values, or exceptions. Strict records have no prompt, response,
search text, secret, API key, or raw exception fields. Task 1.5 owns persistence, flush, durable
reconciliation, and any retirement of the aggregate-only writer. Rollback removes logical metadata
injection and detailed observer registration while retaining strict contracts, physical attempts,
and the incumbent aggregate.

#### Run and node context (#1978, Task 1.4)

`build_pipeline` registers every node wrapped in `usage.node_run_scope(...)`, so a node's provider
calls carry its identity and each execution emits exactly one terminal `NodeRunRecord`. There is no
node-name registry: identity is `NodeSpec.name` plus the per-`Send` cursor, and nothing parses a
ticker out of `phase` or `phase_slug`.

The wrapper is `functools.wraps` + `*args/**kwargs`, and the form is load-bearing. LangGraph decides
what to inject from `inspect.signature(func).parameters`, matched on parameter name *and*
annotation, and `inspect.signature` follows `__wrapped__`. A `(state)`-only wrapper — with or
without `wraps` — raises `TypeError` for any node declaring `config`, `writer`, `store`, or
`runtime`. `tests/dg/test_node_run_context.py::test_node_declaring_runnable_config_still_receives_it`
is the regression guard.

**Run identity.** `usage.start(run_id=...)` takes the `GITHUB_RUN_ID` that `atlas_run_diagnostics`
already writes with `on_conflict="run_id,attempt"`, so detailed telemetry and the diagnostics row
join on one value. It is stored verbatim — truncating a join key would corrupt reconciliation. No
second identifier is minted; `ResearchState.run_id` is a per-process `uuid4` that joins to
nothing and is deliberately not used.

**When identity is unavailable, nothing is recorded.** This is the honest case, not a gap:

| Case | `run_id` | Effect |
|------|----------|--------|
| CI, via `cli_main` | `GITHUB_RUN_ID` | Node records join the diagnostics row |
| Off CI, via `cli_main` | `{cadence}-{run_date}-local` — reused, not minted | `-local` is a suffix no CI run id can carry, so the two can never be confused |
| `deps.diagnostics is None` (library/test callers) | `None` | No node records, no logical calls; physical attempts unchanged. Such a run writes no diagnostics row either, so there is nothing to reconcile against |
| Blank/whitespace | normalised to `None` | `run_id text NOT NULL CHECK (length(run_id) > 0)` can never be violated from this producer |
| `usage.start()` with no argument (operator scripts, the research simulator, the chat workflow) | `None` | Emits nothing **by design** |

**A NULL `fanout_key` means "this execution had no fan-out cursor", never "instrumentation
missing".** research `phase5_sectors` nodes and the compile-time per-ticker H5/H6 variants already
carry their discriminator in `node_name`, so they leave `fanout_key` NULL correctly. A worker that
no-ops on a falsy cursor still emits an honest `SUCCEEDED` record with no child provider call.

`node_run_scope` records `FAILED` on `BaseException`, deliberately broader than digillm's
`except Exception`: losing a record on the exact path where a run dies is the worst place to lose
one, and an incomplete run has to be a counted signal. A LangGraph control-flow exception would be
recorded `FAILED`; no `build_pipeline` node uses `interrupt()` today, so that path is dead rather
than wrong. Synthetic barriers are not wrapped — they run no user code, so reconciliation counts
real node executions rather than compiled graph nodes.

### 4.1 WorkflowState (`graph/state.py`)

`TypedDict` passed through all LangGraph nodes. All keys are optional (`total=False`). No reducers are defined — last writer wins for every key.

| Key | Type | Purpose |
|-----|------|---------|
| `prompt` | `str` | User input |
| `session_id` | `str \| None` | Conversation ID; maps to LangGraph `thread_id` and digistore namespace |
| `request_id` | `str \| None` | Correlation ID propagated to outbound HTTP |
| `workflow_id` | `str \| None` | Per-run UUID for audit log correlation |
| `digi_bearer` | `str \| None` | JWT forwarded to digisearch and digiquant |
| `digi_subject` | `str \| None` | JWT subject; namespaces the cross-thread Store (see §5.5) and the checkpoint `thread_id`. Client-writable on `WorkflowRequest`, but `server.py`'s `_digi_fields_from_request` unconditionally overwrites it — to the verified `auth.subject` when present and non-empty, else `None` (no auth, or an auth object with an empty subject claim) — before it reaches graph state; see §6.10 |
| `allowed_tool_names` | `list[str] \| None` | Tool allowlist; `None` = unrestricted |
| `require_tool_calls` | `bool` | Deployment-grain `tool_choice="required"` mandate — see `tool_policy.require_tool_calls_for_workflow`. **Must** be declared — LangGraph drops undeclared keys. |
| `strategy_name` | `str` | LLM-extracted strategy for digiquant |
| `symbols` | `list[str]` | Ticker list |
| `strategy_params` | `dict[str, Any]` | Optional pre-filled digiquant parameters |
| `trading_profile` | `dict[str, Any]` | User/tenant trading profile; its `max_drawdown_pct` is a negative fraction (e.g. `-0.15` is −15%) and is converted to a negative percent before merging into `optimization_constraints` |
| `research_note` | `str` | Research path label (`"LLM-extracted"`, `"document-mode"`, `"error"`) |
| `research_response` | `str` | Freeform LLM answer in document/RAG mode |
| `rag_sources` | `list[dict]` | Aggregated digisearch citations |
| `research_brief` | `dict[str, Any]` | Serialized `ResearchBrief` |
| `profiling_questions` | `list[str]` | Brief + trading profile gap questions |
| `research_filters` | `list[dict]` | Injected into every digisearch tool call |
| `evidence_tier_preference` | `list[str]` | Evidence tier filter injected into digisearch |
| `backtest_result` | `dict \| None` | digiquant result |
| `backtest_job_id` | `str \| None` | Async job ID from `/v1/jobs/backtest` |
| `optimize_result` | `dict \| None` | digiquant optimization result |
| `optimize_error` | `str \| None` | Non-fatal error from optimize step |
| `optimization_constraints` | `dict[str, Any]` | Merged from `trading_profile` + research |
| `quant_artifact_uri` | `str \| None` | Opaque artifact ref (Phase 2 contract) |
| `error` | `str \| None` | Terminal error; stops further node execution |
| `stored_datasets` | `dict[str, dict]` | Ref → profile map (survives across turns via checkpointer) |
| `workflow_profile` | `str` | Active profile (`full_stack`, `research_rag`, `quant_backtest`, `plan_execute`) |
| `digisearch_index` | `str \| None` | Per-request digisearch index override (`X-Digi-Corpus-Index` / tenant map). **Must** be declared — LangGraph drops undeclared keys. `_initial_graph_state` writes this (and `vault_path_prefix` / `research_system_prompt_override` / `digi_subject`) **unconditionally including `None`**, so a map-driven clear for an unmapped tenant actually clears checkpointed state instead of leaving the prior turn's corpus sticky. |
| `vault_path_prefix` | `str \| None` | Per-request digivault path prefix (`X-Digi-Vault-Prefix` / tenant map); same unconditional-None write as `digisearch_index`. |
| `research_system_prompt_override` | `str \| None` | Optional research system prompt from tenant corpus map; same unconditional-None write as `digisearch_index`. |
| `response_language` | `str \| None` | Per-request response-language code (`X-Digi-Language`). **Must** be declared — LangGraph drops undeclared keys. See `digigraph.languages`. |
| `force_tool` | `str \| None` | Per-request locate tool to inject with the user string as its query (`X-Digi-Force-Tool`; aliases `search`/`digisearch`, `docs`/`digivault`). **Must** be declared. Resolved by `digigraph.retrieval.resolve_force_tool`. |
| `supervisor_depth_remaining` | `int` | Depth budget for supervisor loop |
| `supervisor_route` | `str \| None` | Next route chosen by supervisor |
| `_compaction_event` | `dict \| None` | Lean two-tier compaction event (#399); originals in session workspace. **Must** be declared — LangGraph drops undeclared keys. |
| `llm_messages` | `list[dict] \| None` | Compacted LLM-facing transcript for multi-turn research; optional |

### 4.2 WorkflowRequest (`models.py`)

Pydantic v2 model for `POST /workflow` and internal use:

| Field | Type | Notes |
|-------|------|-------|
| `prompt` | `str` | Required |
| `session_id` | `str \| None` | Maps to LangGraph `thread_id` |
| `request_id` | `str \| None` | Taken from `X-Request-ID` when omitted |
| `allowed_tools` | `list[str] \| None` | Overrides project/env allowlist |
| `require_tool_calls` | `bool \| None` | Combined with project config / env as a FLOOR — can only raise, never lower, the deployment's mandate; see 4.1 |
| `trading_profile` | `dict \| None` | Maps to `optimization_constraints` |
| `strategy_params` | `dict \| None` | Skip LLM param extraction |
| `research_filters` | `list[dict] \| None` | Injected into digisearch calls |
| `digi_bearer` | `str \| None` | JWT propagated downstream |
| `digi_trace_key_prefix` / `digi_trace_tenant` / `digi_trace_project_id` / `digi_trace_jti` | `str \| None` | digikey audit fields |
| `evidence_tier_preference` | `list[str] \| None` | Evidence tier filter |
| `response_language` | `str \| None` | Per-request response-language code (`X-Digi-Language`); see 4.1 |
| `force_tool` | `str \| None` | Optional locate tool to inject (`X-Digi-Force-Tool`); aliases `search`/`digisearch`, `docs`/`digivault`. The model is not hinted — see 5.2 |
| `digi_subject` | `str \| None` | Client-writable, but never trusted as-is: `server.py`'s `_digi_fields_from_request` unconditionally overwrites it with the verified `auth.subject` (or clears it to `None` when auth is absent or its subject claim is empty) before it reaches graph state — see §6.10 |

### 4.3 WorkflowResult (`models.py`)

| Field | Type | Notes |
|-------|------|-------|
| `success` | `bool` | |
| `message` | `str` | Human-readable summary or full RAG response |
| `backtest_result` | `dict \| None` | digiquant `BacktestResult` |
| `optimize_result` | `dict \| None` | digiquant optimization result |
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
| `suggested_catalog_strategies` | `list[str]` | Strategy names from digiquant catalog |
| `strategy_out_of_catalog` | `bool` | True when the strategy is novel |
| `suggested_symbols` | `list[str]` | Ticker suggestions |
| `suggested_strategy_params` | `dict[str, Any]` | Parameter hints |

### 4.5 ChatCompletionRequest (`models.py`)

OpenAI-compatible body for `POST /v1/chat/completions`:

| Field | Type | Notes |
|-------|------|-------|
| `model` | `str` | Default `"digigraph-rag"`; not used for routing (LiteLLM handles it) |
| `messages` | `list[ChatMessage]` | Role + content; content coerced from AI SDK part lists. Flattened into the workflow `prompt` via `chat_prompt.messages_to_workflow_prompt` — **full user+assistant history** (multi-turn), not user-only |
| `stream` | `bool` | SSE streaming |
| `openwebui_format` | `bool` | Open WebUI `<details>` tool blocks. Enabled only by this field or `X-Response-Format: openwebui` — **not** by `model=digigraph-rag`. Opt out via `X-Suppress-Tool-Stream` or `X-Response-Format: plain\|neutral\|none\|digichat` |
| `session_id` | `str \| None` | Conversation isolation |
| `allowed_tools` | `list[str] \| None` | Tool allowlist for this request |
| `require_tool_calls` | `bool \| None` | Also accepted via `X-Require-Tool-Calls` header; floor semantics, see 4.1/4.2 |
| `force_tool` | `str \| None` | Also accepted via `X-Digi-Force-Tool`; aliases `search`/`digisearch`, `docs`/`digivault`. Injected locate then synthesize — the model is not asked to write the query |

---

## 5. Internal Architecture

### 5.1 Module Structure

```
digigraph/src/digigraph/
├── chat_prompt.py               Flatten OpenAI chat messages → workflow prompt (multi-turn)
├── languages.py                 Curated X-Digi-Language directive (do not translate retrieval queries)
├── retrieval.py                 Force-tool aliases, vault-path extraction, auto digivault_get_note hop (batch ≤20)
├── server.py                    FastAPI app, middleware stack, all HTTP routes
├── workflow.py                  run_digigraph_workflow (sync + streaming variants)
├── models.py                    Pydantic I/O models (WorkflowRequest, WorkflowResult, ChatCompletion*)
├── models/                      Extended model subpackage (if present)
├── research_brief_models.py     ResearchBrief, Theme
├── model_config.py             Model-mode resolution + request→effective model routing (feeds digillm)
├── llm_auth.py                 Per-request LiteLLM-proxy / BYOK funnel → digillm contextvars
├── llm_client.py               completion / completion_text / run_tools wrappers over digillm
├── policy.py                    Feature flag gate functions (debug, thread API, code exec, hub mode)
├── rate_limit.py                Per-IP sliding-window rate limiter (in-process deque)
├── digistore.py                 Session-scoped named dataset store (filesystem JSON)
├── run_storage.py               Lower-level session path helpers, search result writer
├── mcp_server.py                FastMCP server exposing workflow, chat, thread_state, tool lists
├── audit.py                     Thin audit_log → digibase.audit.emit_event (workflow_start/end, tool_denied)
├── trace_events.py              TraceEventV1, RagSourceItem (optional capped `body` for get_note / #3419), rag_sources_from_results
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
│   ├── digiquant_hub.py         fetch_digiquant_tool_dicts, invoke_digiquant_tool
│   └── digivault_hub.py         fetch_digivault_tool_dicts, invoke_digivault_tool
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
                                └─ research_brief_builder (skipped when `agents.research_brief: false` / `DIGI_RESEARCH_BRIEF=0`)
                               │
                               ├─ error → END
                               ├─ research_rag profile → END
                               ├─ DIGIQUANT_URL explicitly empty → END (Profile A / chat-only)
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

Retrieval is model-driven by default: `research_node` (document RAG path) hands the full tool set to `run_tools` with a `max_tool_rounds=4` budget and lets the model decide whether and when to call `digisearch` / `digivault_search_notes`. After a locate, `auto_load_notes` (`retrieval.py`) calls `digivault_get_note` (batch ≤20 vault paths) so the model synthesizes from full notes instead of asking permission to read what it already found. `RagSourceItem.body` is stamped only on get_note (`include_body=True`, cap `MAX_RAG_SOURCE_BODY_CHARS`) and overlaid onto duplicate locate keys in `merge_loaded_notes` / `merge_rag_sources_accumulator`; WorkflowState strips `body` before checkpoint so the pane reads the stream, not graph state. Slash `/search` and `/docs` on the public embed set `force_tool` / `X-Digi-Force-Tool`: `last_user_turn()` (`chat_prompt.py`) extracts the current user string from the flattened `User:` / `Assistant:` transcript so the tool `query` is that turn, not the whole history. The locate is injected *before* the LLM turn **only when** `allowed_tool_names` is unrestricted (`None`) or includes the resolved tool — otherwise tenants with an allowlist would still get a started `tool_call` / Searching… row and a deny blob in `force_tool_messages` even though `execute()` would refuse the call. Then `run_tools` synthesizes with `tool_choice="auto"` (even when `require_tool_calls` is set). `agents.always_retrieve_tools` is dead configuration — `DigiProjectConfig.get_always_retrieve_tools()` still exists and still parses the key, but nothing calls it, since the prefetch it used to gate was removed. All shipped `digiproject.yaml` files have had the key dropped. If the model calls no tools (and no force-tool ran), `run_tools` runs a single streamed completion (no tool rounds). **`max_tool_rounds=4` bounds tool-calling rounds, not completions outright**: `digillm.client.run_tools` (`digillm/src/digillm/client.py:2138-2147`) fires one additional tool-free completion when the round budget is exhausted and the model still hasn't produced final content, so a fully-exhausted budget costs up to **5** completions, not 4.

`agents.research_brief` (default `true`; env `DIGI_RESEARCH_BRIEF=0/1` overrides) controls whether `build_research_subgraph()` wires `research_brief_builder` after `research_inner`. When false, the subgraph ends when the answer stream completes — dogfood chat uses this to avoid a post-answer `completion_text` latency tax.

The graph is compiled once per `build_workflow_graph()` call. In practice, `workflow.py` calls `build_workflow_graph()` on **every** request — there is no module-level compiled graph cache. This means the StateGraph is recompiled on each call; the checkpointer instance is shared (process-wide singleton).

### 5.3 Orchestrator Tool Registry Pattern

Three-layer structure:

1. **Primitives** (`tools/`): stateless callables not exposed to the LLM directly.
2. **Orchestrator tools** (`orchestration/`): `(name, schema, handler, tags)`. Schema may be a static dict or a `SchemaFactory(context) -> dict` for context-dependent schemas (e.g. digisearch tools fetched from the vertical manifest). Registered once at module import via `_register_tools()` at the bottom of `builtin.py`.
3. **Skills** (`orchestration/registry.py`): named bundles of tool names with a `when(context) -> bool` predicate. The `search` skill activates only when `DIGISEARCH_URL` is set. The `project_rag` skill activates only when `run_data_dir` is set. The `digivault` skill (`digivault_search_notes` and `digivault_get_note`, the locate-then-load pair) activates only when `DIGIVAULT_URL` is set. The `web` skill (`web_search` via digillm) activates only when `WorkflowState.enable_web_search` is true — digichat sends `X-Digi-Enable-Web-Search` after tenant + user opt-in (#3420); default off so web never mixes into corpus RAG silently. External cites use `evidence_tier: External` and supplement vault/search hits.

The registry is a module-level dict (`_tools`, `_skills` in `registry.py`). It is global to the process — all requests share the same registry. `register_tool` raises `ValueError` on duplicate names, so plugins loaded via `load_entrypoint_tools()` must use unique names.

### 5.4 Vertical Connector Pattern

digisearch, digiquant, and digivault each own their tool schemas via `POST /v1/orchestrator_tools`. digigraph:

1. Calls `fetch_digisearch_tool_dicts(base_url, index_config, bearer, request_id)` at schema resolution time. Results are cached in a module-level dict (`_MANIFEST_CACHE`) keyed on `(base_url, index_config)` — this cache is **never invalidated** for the lifetime of the process.
2. Invokes tools via `invoke_digisearch_tool(base_url, tool, args, ...)` → `POST /v1/orchestrator_invoke`.
3. The digiquant connector follows the same pattern via `digiquant_hub.py`.
4. The digivault connector (`digivault_hub.py`) follows the same pattern for two tools: `digivault_search_notes` — full-text search over the digithings architecture vault (D1 FTS5 when configured, else filesystem/Supabase) — and `digivault_get_note`, which loads one note in full by the `vault_path` a search hit returns, so the model can read the whole page instead of reasoning from `digivault_search_notes`'s ~300-char excerpt. `digivault_get_note` is D1-only (503s on a non-D1 deployment) and requires `path_prefix`; digigraph's handler overwrites `path_prefix` from `ToolContext.vault_path_prefix` unconditionally (never trusting a model-supplied value) so a model cannot select another tenant's corpus — `_handle_digivault_search` does the same. Neither tool has an `index_config` (vault search/load is not index-scoped), so the manifest cache key is the base URL alone.

The manifest cache uses synchronous `httpx.Client` (blocking calls inside async FastAPI). This can block the event loop thread during tool schema resolution. The current request handling is synchronous (FastAPI's thread pool), so this is acceptable but limits throughput under high concurrency.

Each hub's `invoke_*` function (`invoke_digisearch_tool`/`invoke_digiquant_tool`/`invoke_digivault_tool`) is wrapped by a per-service `CircuitBreaker` (`digigraph/circuit_breaker.py`, `failure_threshold=5`, `recovery_timeout=30.0`) — and the legacy `tools/digisearch.py` `POST /query` helper uses the same breaker class with identical failure scoping. Only the network call itself (`client.post(...)`) runs inside the breaker's `with _cb:` scope, so only a genuine transport failure (`httpx.RequestError`: connection refused, timeout, DNS failure) counts toward opening the circuit. `raise_for_status()`/`.json()` run *outside* that scope: a raised `httpx.HTTPStatusError` (4xx/5xx) or a JSON decode error still returns the caller's normal failure contract (`{"ok": False, ...}` for hubs; `None` for the legacy helper), but does not trip the breaker — the same `httpx.RequestError`-only, never-`HTTPStatusError` scoping rationale that `graph/nodes.py`'s `_DIGIQUANT_CLIENT_ERRORS` handling follows ("never `httpx.HTTPStatusError` — a 4xx/5xx is a real rejection, not a blip"). This matters because a single caller sending malformed arguments (a client-caused 4xx) must not open the process-wide circuit for 30 seconds for every other user.

### 5.5 Checkpointing

Process-wide singleton via `get_checkpointer()` in `graph/graph.py:108`:

| `DIGI_CHECKPOINTER` value | Backend | Notes |
|--------------------------|---------|-------|
| unset + project active | `SqliteSaver` | **Default when `digiproject.yaml` is present** (project mode); survives restarts |
| unset + no project | `MemorySaver` (in-process dict) | Default standalone mode; lost on restart |
| `memory` | `MemorySaver` (in-process dict) | Explicit; lost on restart |
| `sqlite` | `SqliteSaver` | File path via `DIGI_CHECKPOINTER_SQLITE_URI` |
| `postgres` | `PostgresSaver` | Connection string via `DIGI_CHECKPOINTER_POSTGRES_URI` |
| `none` / `off` / `0` / `false` | None (no checkpointing) | Breaks multi-turn and thread APIs |

**Project-mode default:** When `get_checkpointer()` is called and `DIGI_CHECKPOINTER` is unset, the function probes for an active project config via `_resolve_config_path()`. If a `digiproject.yaml` is found, it defaults to `sqlite` so multi-turn conversation state persists across HTTP requests. The env var always takes precedence over this auto-detection.

#### 5.5.1 High availability (multi-replica) — REM-099

For **more than one digigraph replica** behind a load balancer, operators **must** set:

```bash
DIGI_CHECKPOINTER=postgres
DIGI_CHECKPOINTER_POSTGRES_URI=postgresql://...
```

`memory` and `sqlite` are single-process backends; checkpoints are not shared across pods. Postgres is the only supported shared store today. Per-thread advisory locking for concurrent writes on the same `thread_id` is still recommended (see §7.5). Install with `pip install digigraph[checkpoint-postgres]`.

A `threading.Lock` (`_checkpointer_lock`) guards lazy initialization. Context managers for SQLite and Postgres are stored in `_cm_holders` to prevent garbage collection — this is a manual resource management pattern that will leak if the process forks.

#### 5.5.2 Postgres retention — the checkpointer does not prune itself (#1758)

`PostgresSaver` never deletes thread state. Nothing in `langgraph-checkpoint-postgres` expires a `thread_id`, so **any deployment using `DIGI_CHECKPOINTER=postgres` with non-reusable thread ids grows without bound** and the operator owns retention.

dashboard is the load-bearing case: `portfolio/chain.py:125` derives `thread_id` as `"<GITHUB_RUN_ID>::research"` / `"::portfolio"`, which is never reused, so no row ever became collectable. By 2026-08-01 the four checkpointer tables held 952 MB of a 1263 MB database (75%) and were growing ~50-58 MB/day.

Retention is enforced **in the database, not in digigraph** — the pruner must not depend on a Python process being alive, and digigraph has no scheduler. `digiquant/supabase/migrations/061_checkpointer_retention.sql` installs `public.prune_langgraph_checkpoints(retain_days integer DEFAULT 14)` plus two daily pg_cron jobs (prune at 05:20 UTC, plain `VACUUM (ANALYZE)` at 05:50 UTC). See [`digiquant/supabase/SCHEMA.md`](../digiquant/supabase/SCHEMA.md) for the operator view (pause, verify, ownership requirement).

Three properties that any other Postgres-checkpointer deployment should copy:

- **Prune by `thread_id`, not by checkpoint.** `checkpoint_blobs` is keyed `(thread_id, checkpoint_ns, channel, version)` with **no `checkpoint_id`** column, so a per-checkpoint delete leaves unreachable blobs behind — and blobs are where the bytes are.
- **Key staleness on `max((checkpoint->>'ts')::timestamptz)` per thread.** Per-row it is a reliable ISO 8601 timestamp; taking the max means an in-flight or freshly-resumed thread can never be eligible, and an unparsable/absent `ts` yields `NULL`, fails the comparison, and is retained.
- **Retention is a resume ceiling.** Any resume-from-checkpoint feature (here, `pipeline-digiquant.yml`'s `resume_run_id`) can only reach back as far as the retention window, so the window can never be zero.

**The real cost driver is upstream of retention.** 94% of the bytes sit on the `__pregel_tasks` channel: `FanOutPhase` dispatches one `Send` per item and `pipeline_builder.py:57-58` hands each worker a **full copy of the live state**, so one H6 superstep persisted 52 complete `ResearchState` copies (a single 48 MB row was measured). That is `O(fan-out width x state size)` per superstep and it contradicts `AGENTS.md`'s "State stays lean … no large DataFrames in state or LangGraph checkpoints" as well as [`docs/LANGGRAPH_REVIEW.md`](docs/LANGGRAPH_REVIEW.md). Shrinking the `Send` payload to a cursor is a ~20x lever; it changes `FanOutPhase`'s state-copy contract in this shared library and is therefore deferred as a human-gated architecture change (follow-up to #1758). Retention caps the footprint; it does not reduce the write volume.
#### 5.5.3 Postgres connection bounds — #1734

`PostgresSaver.from_conn_string` forwards its argument straight to `psycopg.Connection.connect`, which applies **no** connect timeout and **no** TCP keepalives, and exposes no kwarg for either. An established connection to a peer that disappears without sending an RST therefore stays in `ESTABLISHED` indefinitely, and a checkpoint read/write blocks with nothing but the caller's own job timeout as a backstop — the shape of the 2026-07-30 dashboard stall (210 minutes of silence inside a 240-minute job, beginning at a checkpoint-write boundary).

`_bounded_conn_string()` closes that by merging the bounds into the conninfo itself, which libpq accepts as ordinary connection parameters:

| Parameter | Value | Bounds |
|---|---|---|
| `connect_timeout` | `10` | establishing a connection |
| `keepalives` / `keepalives_idle` / `keepalives_interval` / `keepalives_count` | `1` / `30` / `10` / `5` | an established-but-dead connection (~80s to detect) |

It accepts either libpq spelling (`postgresql://` URI or `host=… dbname=…` keyword/value) via `psycopg.conninfo.make_conninfo`, and **any parameter already present in `DIGI_CHECKPOINTER_POSTGRES_URI` wins** — that env var is the override path. Missing psycopg or an unparseable conninfo returns the string unchanged with a warning: bounding a connection must never itself be why a process fails to start.

`statement_timeout` is deliberately **not** set. It is enforced server-side, so it cannot help when the network path is gone, and it risks aborting a legitimately slow write against a checkpoint table already at ~950 MB in production (#1758).

Timing is the only thing that changes: an unreachable Postgres already raised `psycopg.OperationalError` out of `get_checkpointer()` (via `cm.__enter__()`), so no new failure *mode* is introduced — it now surfaces in ~10s instead of hanging on the OS TCP timeout. On the dashboard path `portfolio/chain.py::_acquire_checkpointer` catches `Exception` and degrades to an uncheckpointed run.

#### 5.5.4 Store (cross-thread memory) — parallel but not identical backend selection

`get_store()` (`graph/graph.py:183`, Task 7) provides a **process-wide `Store`**, distinct from the checkpointer above: the checkpointer is scoped to a single `thread_id`, while the Store holds values that should survive a subject opening a brand-new thread (today: a `response_language` preference, keyed by `digi_subject` — see `supervisor_node`, gated behind `DIGI_SUPERVISOR=1`). It mirrors `DIGI_CHECKPOINTER`'s *kind* selection where LangGraph has an equivalent, but the mapping is **not one-to-one**:

| `DIGI_CHECKPOINTER` value | `get_checkpointer()` backend | `get_store()` backend |
|--------------------------|-------------------------------|------------------------|
| unset / `memory` | `MemorySaver` | `InMemoryStore` |
| `sqlite` | `SqliteSaver` (persistent, file-backed) | `InMemoryStore` (**not** persistent) |
| `postgres` | `PostgresSaver` | `PostgresStore` (same conn string, reusing `_bounded_conn_string`'s connect-timeout/keepalive bounds) |

LangGraph ships no first-class `Store` equivalent of `SqliteSaver`, so `sqlite` maps to `InMemoryStore` here — a documented, same-process choice, not a silent one: unlike `get_checkpointer()`'s sqlite path, **`DIGI_CHECKPOINTER=sqlite` gets no persistent cross-thread Store at all**. A response-language preference set under `sqlite` is lost on process restart and is never shared across replicas, even though the checkpointer itself (thread-scoped state) survives both. Only `DIGI_CHECKPOINTER=postgres` gets a Store that persists and is shared across replicas; every other setting (including sqlite) silently falls back to `InMemoryStore`, with a warning now logged for both failure paths that can produce that fallback under `postgres` (missing `langgraph-checkpoint-postgres` install, or `DIGI_CHECKPOINTER_POSTGRES_URI` unset).

Today's realized impact is low: `DIGI_SUPERVISOR` defaults off, so the supervisor node (the only current Store reader/writer) does not run by default, and the Store holds nothing but a language preference even when it is on. See §6 for the Store's namespace-trust dependency on `digi_subject`.

### 5.6 Streaming SSE Architecture

```
HTTP request (stream=true)
        │
        ▼
_stream_completions_progressive (server.py generator)
        │
        ├── spawns Thread(ctx.run) → run_digigraph_workflow_streaming(req, event_queue)
        │                           │
        │                           ├── defines stream_callback(event_type, data) closure
        │                           │     (content/tool_call/round_boundary/tool_result handling)
        │                           ├── graph.stream(initial, config=config,
        │                           │               stream_mode=["updates", "custom"], version="v2",
        │                           │               subgraphs=True)   # required -- research runs in a subgraph
        │                           │     │
        │                           │     ├── part["type"] == "custom"   (any ns, never filtered)
        │                           │     │     (event_type, data) = part["data"]
        │                           │     │     └── stream_callback(event_type, data)   [called directly]
        │                           │     │
        │                           │     └── part["type"] == "updates"
        │                           │           ├── part["ns"] non-empty (inner-subgraph node) → skip
        │                           │           └── part["ns"] == () (top-level node) →
        │                           │                 _stream_update_summary(update)
        │                           │                 └── event_queue.put(("trace", graph_update))
        │                           │
        │                           │   Inside the graph run (research subgraph), research_node → _run_document_rag_path:
        │                           │     writer = _safe_stream_writer()   # get_stream_writer(), no-op outside a real invocation
        │                           │     run_tools(..., on_tool_step=stream_callback)
        │                           │           └── stream_callback(...) → writer((event_type, data))
        │                           │                 └── surfaces above as a "custom" part
        │                           │
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

Nodes emit streaming events via LangGraph's native `get_stream_writer()` (`langgraph.config`), not via a callback threaded through state, config, or a `ContextVar` — that 3-tier resolver was collapsed in c32a7a970. `_run_document_rag_path` (`research.py:311`) resolves the writer through `_safe_stream_writer()` (`research.py:26-34`): it calls `get_stream_writer()` and catches the `RuntimeError` LangGraph raises when it's invoked outside a real graph run (e.g. a unit test calling a node function directly instead of going through `graph.invoke()`/`graph.stream()`), falling back to a no-op `lambda _data: None`. This is what lets `tests/dg/test_nodes.py` call node functions in isolation without a full graph invocation. (`_safe_get_store()`, `research.py:37-54`, mirrors the same pattern for `get_store()` — see §5.5.4 and §6.10.) The resolved `writer` (`research.py:390`) is closed over by a local `stream_callback(event_type, data)` (`research.py:392-399`) that enriches `digisearch`/`digisearch_fetch_all` `tool_call` events with `index_name` before calling `writer((event_type, data))`; that `stream_callback` is passed to `run_tools(..., on_tool_step=stream_callback)`, so every `tool_call`/`tool_result`/`content`/`reasoning` event the tool loop emits flows out through the writer.

`workflow.py`'s `run_digigraph_workflow_streaming` (`workflow.py:293-`) drives the graph with `graph.stream(initial, config=config, stream_mode=["updates", "custom"], version="v2", durability="sync", subgraphs=True)` (`workflow.py:426-433`). The dual-mode list means each yielded `part` carries a `"type"` discriminant: a `part["type"] == "custom"` entry is exactly the `(event_type, data)` tuple a node wrote via `get_stream_writer()`, and the driver loop unpacks it and calls its own rich `stream_callback` closure (`workflow.py:317-409`) directly — the same content-buffering, `tool_call` → `code_block` trace synthesis for `data_engineer_agent`, `round_boundary` → trace event (#2306), and `tool_result`-with-`rag_sources` → `rag_sources` trace event handling this closure has always done, just invoked without an intermediate `ContextVar` hop. A `part["type"] == "updates"` entry is the per-node state delta LangGraph emits natively; `_stream_update_summary` reduces it to `{node: {"keys": [...]}}` (avoiding serialization of large state values) and it is forwarded as a `graph_update` trace event. There is no config channel and no module-level `ContextVar`: the writer `get_stream_writer()` returns is scoped to the current graph run by LangGraph itself, so `workflow.py` never needs to inject anything into `research.py` — it only needs to be the consumer on the other end of `graph.stream(...)`.

**`subgraphs=True` is required, not optional.** `research_node`/`research_brief_builder_node` run inside a *compiled subgraph* (`graph/research_subgraph.py`'s `build_research_subgraph()`, added as the single `"research"` node by `graph/graph.py`'s `build_workflow_graph()`), not as top-level nodes on the outer graph. LangGraph filters `"custom"`/`"updates"` parts sourced from inside a subgraph unless the outer `.stream()` call passes `subgraphs=True` — without it, every `_safe_stream_writer()` write from `_run_document_rag_path` (`tool_call`, `tool_result`, `content`, `reasoning`, `round_boundary` — nearly everything the diagram above shows) was silently dropped before ever reaching this loop (fixed; previously a live regression). With `subgraphs=True` on, `"updates"` parts also start arriving for inner-subgraph nodes with a non-empty `ns` (e.g. `ns=("research:<uuid>",)`); the driver loop skips those (`if part["ns"]: continue`) before building the `graph_update` trace event, so only the outer, top-level node completions are reported — this filter does **not** apply to `"custom"` parts, which must flow through regardless of which namespace they originated from. See `tests/dg/test_subgraph_streaming.py` for a standalone regression test of this exact mechanism.

---

## 6. Security Analysis

### 6.1 digikey JWT Authentication

`DigiAuthMiddleware` validates JWTs via `DIGIKEY_JWKS_URL` (JWKS endpoint) or `DIGIKEY_PUBLIC_KEY_PEM` (static PEM). Path-scope mappings control which scopes are required per route. When neither is configured, the middleware passes through unauthenticated requests — this is the default for local dev but must not be used in production.

The JWT subject (`sub`) is not bound to checkpoint state. Any authenticated caller with a valid JWT can read or resume any `thread_id` via the thread API. This is a known gap — see Section 11 (Redesign Recommendations).

### 6.2 Tool Allowlists

Three sources merged in `tool_policy.py`:
1. `WorkflowRequest.allowed_tools` (per-request override, highest priority)
2. Project config `agents.allowed_tools` (per-project)
3. `DIGI_ALLOWED_TOOLS` env var (per-deployment)

When an allowlist is active, `execute()` in `registry.py:106` rejects denied tools with an audit log entry (`tool_denied` event). The schema-level filter in `get_tools()` also removes denied tools from the LLM context, preventing the model from attempting to call them.

An allowlist of `[]` (empty list) blocks all tools, forcing research-only mode. `None` means unrestricted.
`research_node` deserializes via `tool_policy.frozen_from_state_list` so an empty list is never
coerced to unrestricted by a falsy check.

#### 6.2.1 Tool Choice Requirement

`agents.require_tool_calls` (bool, default `false`) forces `tool_choice="required"`
on every tool-calling turn in `research_node`'s `run_tools()` call — for deployments
(e.g. OCC) that depend on multi-round tool calls for retrieval and should never
silently answer from parametric knowledge alone. Resolved as a **floor**, not an
override, by `tool_policy.require_tool_calls_for_workflow()`: project config or
`DIGI_REQUIRE_TOOL_CALLS` wins over a request/`X-Require-Tool-Calls` header value
of `false` — deliberately the opposite precedence from `agents.allowed_tools`,
since this flag has no registry-bounded ceiling the way a tool allowlist does.

Forcing `tool_choice="required"` also changes the cost and failure shape of the
round budget described above. With it off, `tool_calls` can come back empty and
`run_tools()` returns early, so `max_tool_rounds` is a ceiling the model rarely
exhausts; with it on, a tool-enabled round returning empty `tool_calls` is no
longer treated as an early final answer — `run_tools()` raises instead, so a
provider that ignores the `required` hint doesn't get to silently answer without
calling a tool. A compliant model still hits every round in the budget, so with
`research.py`'s current `max_tool_rounds=4` a request with `require_tool_calls:
true` makes 4 tool rounds plus one tool-free wrap-up completion — 5 total — only
when the last round's own narration was empty; when that round already carried
non-empty content, it's returned directly with no wrap-up, for 4. Either way,
not the fixed 5 this used to claim. It also changes what happens when a model
can't comply at the provider level: a provider that rejects forced tool use for
that model outright now returns a hard error for the whole request, rather than
the model quietly answering without tools the way a tool-incapable model
degrades today.

### 6.3 Code Execution Gate

`policy.code_execution_allowed()` gates **execution**, not tool registration. `data_engineer_agent` is always registered in `orchestration/builtin.py` but `execute_python_on_datasets()` in `tools/analytics/execute_python.py` returns an error when `DIGI_ALLOW_CODE_EXEC` is unset. The `project_rag` skill only exposes the tool when `run_data_dir` is set; callers still need `DIGI_ALLOW_CODE_EXEC=1` for code to run.

### 6.4 Thread State Access

`GET /threads/{thread_id}/state` requires `DIGI_ENABLE_THREAD_API=1` but performs no subject-binding check. Any request with a valid JWT (or no JWT in passthrough mode) can read any thread's state. The `_THREAD_STATE_KEYS` allowlist (`server.py:249`) limits which state keys are returned, but `stored_datasets`, `research_response`, `research_note`, `error`, `backtest_result`, `strategy_name`, and `symbols` are all exposed.

**Risk:** In a multi-tenant deployment, tenant A can read tenant B's research output and dataset refs if they know or guess the `thread_id`. Since `thread_id` defaults to `session_id` (which defaults to `"default"`), all sessions without an explicit `session_id` share a single checkpoint namespace.

### 6.5 Debug Endpoint Risks

`GET /v1/debug/input_messages` returns the last 5 chat completion request summaries, including the first 400 characters of the prompt. This is stored in a module-level global (`_DEBUG_REQUEST_LOG` in `server.py:16`) shared across all requests. In a multi-tenant deployment with the debug endpoint enabled, a second tenant can read another tenant's prompt preview. The endpoint should be disabled in production (`DIGI_ENABLE_DEBUG_ENDPOINTS` defaults to `0` in Compose).

### 6.6 Streaming Cancellation Gap

When a client disconnects from an SSE stream, the background thread (`run_digigraph_workflow_streaming`) continues executing until it completes or errors. A cooperative `threading.Event` does bound this: `_stream_completions_progressive` sets it on `GeneratorExit` (raised into the generator at its `yield` when the client goes away) and again in its `finally`, and the worker checks it between graph nodes.

Two things are needed for that bound to be real, and only the first is obvious. The generator stops draining the queue as soon as the event is set, and the queue is bounded (`maxsize=256`) — so the worker's *writes* have to be cancellation-aware too, or the very first `put` onto a full queue blocks on a reader that will never return. That blocks inside a node, so the between-nodes poll is never reached, the thread is neither daemonic nor joined, and its `finally` — which clears the request's BYOK credentials from the thread's context copy — never runs. `workflow._emit_event` closes that: it polls with a timeout and drops the event once the event is set, so a disconnect ends the worker at its next node boundary instead of leaking a thread holding a user's API key for the lifetime of the process.

What is still missing is preemption — no exception is injected into a node already running, so a single long LLM call or tool round runs to completion after the client is gone. Under load, workflow threads can therefore still accumulate for up to one node each, each holding LLM connections and potentially making outbound HTTP calls to digisearch and digiquant.

### 6.7 Rate Limiter Trust Boundary

`RateLimiter._get_ip()` (see §12.8) only consults `X-Forwarded-For` when the direct peer is in `DIGI_TRUSTED_PROXIES`; with that unset (the default), a client's `X-Forwarded-For` is ignored entirely and `request.client.host` is used, so `X-Forwarded-For: 1.2.3.4` cannot impersonate another IP. Setting `DIGI_TRUSTED_PROXIES` moves the trust boundary to whichever proxy hops are listed there — see §12.8 for the operational requirement to list every hop in the chain, not just the innermost one. Currently there is no proxy in the default Compose stack — digigraph is directly exposed on `127.0.0.1:8000` — so `DIGI_TRUSTED_PROXIES` should stay unset there.

### 6.8 MCP Server Auth Gap

The MCP server (`mcp_server.py`) has no built-in authentication layer. The `streamable-http` transport binds to `0.0.0.0:8766` by default, making it network-accessible. The `workflow` and `chat` MCP tools invoke the workflow directly (bypassing HTTP middleware including `DigiAuthMiddleware`). Operators must use network policy or a gateway in front of the MCP server.

### 6.9 Manifest Cache Never Invalidates

The vertical manifest caches in `digisearch_hub.py`, `digiquant_hub.py`, and `digivault_hub.py` are module-level dicts with no TTL or invalidation. If digisearch, digiquant, or digivault adds, removes, or changes a tool definition, the cached schema is stale until the digigraph process restarts. This affects tool schema accuracy in long-running deployments.

### 6.10 Store Namespace Trust — `digi_subject` Is Server-Verified Before It Reaches Graph State

The Store added in Task 7 (§5.5.4) namespaces every entry by `digi_subject` (`(subject, "prefs")` in `supervisor_node`). `digi_subject` is a **client-writable field** on `WorkflowRequest`. Previously, `server.py`'s `_digi_fields_from_request` only overrode it server-side when `auth.subject` was truthy — a conditional-only override — so an unauthenticated request, or one whose `auth` object carried an empty `subject` claim, let the client's own `digi_subject` value survive untouched all the way into graph state and the Store namespace key: a CWE-639 IDOR letting a client read or overwrite another subject's stored preference by supplying its value.

**Fixed:** `_digi_fields_from_request` now sets `updates["digi_subject"]` **unconditionally** on every call — to the verified `auth.subject` when `auth` is present and its `subject` claim is non-empty, and explicitly to `None` in every other case (no `auth` object at all, or an `auth` object present with an empty/falsy `subject`). This distinction matters because `req.model_copy(update=updates)` (in `_with_digi_request_context`) only clears a field when its key is *explicitly present* in `updates` — an absent key leaves the client's original value untouched, so the pre-fix conditional-only override never actually cleared anything; it only skipped setting a new value. Setting the key to `None` unconditionally is what makes it a real override. See `tests/dg/test_api.py::TestDigiSubjectTrustBoundary` for the three pinned cases: authenticated with a real subject (unchanged), no auth object at all (forced to `None`), and an auth object with an empty subject claim (also forced to `None` — the specific gap this fix closes that a "just check `auth is None`" fix would have missed).

This also strictly tightens `workflow_thread_id`'s subject-based `thread_id` scoping (used by both `workflow.py`'s `_graph_thread_config` and `server.py`'s chat/completions path): since `req.digi_subject` itself is now cleared for unauthenticated/empty-subject requests rather than merely the Store lookup being gated, `workflow_thread_id(None, session_id)` degrades to the unscoped `session_id` it already handled gracefully — no functional loss, since a falsy subject was already "no scoping" there.

**Risk before this fix was low but not zero:** the Store currently holds only a `response_language` preference (§5.5.4), gated behind `DIGI_SUPERVISOR=1` which defaults off, so a realized exploit at most let one subject read or overwrite another's language preference. Recorded here for completeness now that it is closed, since the Store's blast radius would have grown with whatever future data any new supervisor-node logic decides to persist there.

---

## 7. Scalability Analysis

### 7.1 Shared In-Process Checkpointer (Single-Node Constraint)

The `MemorySaver` default stores all thread state in a Python dict in the digigraph process. Multiple digigraph replicas cannot share this state. SQLite is similarly single-process. Only the Postgres backend supports horizontal scaling, but even with Postgres, there is no distributed locking: two concurrent requests for the same `thread_id` can produce conflicting checkpoint writes.

**Practical limit:** A single digigraph instance can handle concurrent requests limited by the Python GIL + thread pool size. Each streaming request holds a thread for the duration of the workflow (potentially 30–120 seconds for backtest-inclusive flows). The default FastAPI thread pool is CPU-count × 5; large backtests can saturate it quickly.

### 7.2 In-Memory Rate Limiter

`RateLimiter` uses an in-process `dict[str, deque]` protected by a single `threading.Lock`. This works for a single process but:
- State is lost on restart (all rate limit windows reset)
- Multiple replicas have independent limits, so the effective rate is multiplied by the replica count
- The lock is a single point of contention under high request rates

Each bucket's own `deque` is already bounded to `max_requests` entries (the `popleft` loop in `check()` drops anything older than the current window), so the growth risk is the *number* of distinct buckets, not any one bucket's size — a client hit once and never again used to leave a permanent dict entry with nothing to reclaim it (#2378). `check()` now sweeps fully-idle buckets out of `_windows` every `_SWEEP_INTERVAL` (1000) calls — every `check()` call counts toward that interval, whether it accepts or 429-rejects the request, so a sustained flood of already-over-quota (rejected) requests against one bucket cannot stall the sweep and leave other, genuinely idle buckets unreclaimed for the flood's duration. This bounds the dict to roughly the number of distinct clients active within a sweep interval rather than every distinct client ever seen. The sweep assumes a single `RateLimiter` instance is always called with the same `window` — true for both instances in `server.py` (`_rate_limiter`, `_require_tool_calls_limiter`), each with exactly one call site.

`_windows` is an `OrderedDict`, not a plain `dict`: `check()` calls `move_to_end` on a bucket exactly when it accepts a request (never on the 429-reject path), so front-to-back order is always ascending by "time of last accepted request." The sweep walks from the front and stops at the first still-active bucket instead of scanning the whole dict — cost is O(evicted), not O(total buckets ever seen). This matters because a naive full-dict scan runs synchronously inside the (single-worker, single-event-loop) `async def rate_limit` middleware while `self._lock` is held, so an O(n) sweep over a `_windows` grown huge by a sustained distinct-source flood would stall every concurrent request for the scan's full duration; the ordered, early-stopping sweep keeps each sweep's cost bounded to roughly one `_SWEEP_INTERVAL` batch regardless of how large `_windows`'s cumulative history gets. A bucket whose very first request was already over quota (`max_requests <= 0`, e.g. a misconfigured `DIGI_REQUIRE_TOOL_CALLS_RATE_LIMIT_MAX=0`) is created but never appended-to, leaving a permanently empty deque; the sweep treats an empty deque as unconditionally idle rather than evaluating its (nonexistent) newest entry, so it gets reclaimed instead of raising.

### 7.3 Graph Compilation Per Request

`build_workflow_graph()` is called inside `run_digigraph_workflow()` on every invocation. LangGraph compiles the graph (creates the `CompiledStateGraph` object, resolves edges and node references) on each call. This is unnecessary overhead — the compiled graph object is immutable and could be cached as a module-level singleton, reusing the shared checkpointer.

### 7.4 Vertical Manifest HTTP Blocking

`fetch_digisearch_tool_dicts`, `fetch_digiquant_tool_dicts`, and `fetch_digivault_tool_dicts` make synchronous `httpx` calls at schema resolution time, inside FastAPI's synchronous thread pool. If digisearch, digiquant, or digivault is slow or unavailable, this blocks a worker thread for up to 30 seconds (`timeout=30.0`). The first request after startup or cache invalidation pays this cost.

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

`digillm` implements an in-process SHA-256 keyed cache for non-tool `completion` calls (digigraph reaches it through `llm_client.completion`):
- Cache key: `sha256(json.dumps({model, messages, temperature}, sort_keys=True))`
- TTL: configurable via `DIGI_LLM_CACHE_TTL_SECONDS` (default 3600s)
- Capacity: 256 entries, FIFO eviction on overflow
- Exclusions: calls with `tools` (side effects) are never cached

This provides meaningful speedup for repeated identical prompts (e.g. heartbeat probes, repeated research queries). Tool calls and streaming completions bypass the cache. The 256-entry FIFO eviction is a weak strategy — LRU or LFU would have better hit rates for diverse workloads.

### 8.2 Model Mode System

`get_model_for_mode()` (now in `model_config.py`) resolves the model via `_load_model_modes()`, which is **mtime-cached per process**: `config/model_modes.yaml` is opened and parsed by PyYAML only when its mtime changes, so steady-state calls cost a single `path.stat()` plus the env reads (`DIGI_CONFIG_PATH`, `DIGI_MODEL_MODES_FILE`). The mode itself is re-read from env/config on every LLM call to pick up runtime changes.

Four modes — **`llm_mode` is access/cost policy, not a product catalog**: `free` (resolved model must be free-tier: OpenRouter `:free` or local Ollama), `test` (minimal), `medium` (balanced), `best` (largest). The project config YAML `agents.llm_mode` overrides `DIGI_LLM_MODE`. **Actual model id** comes from (in order) `agents.llm` → `DIGI_LLM_PROVIDER`/`DIGI_LLM_MODEL` → LiteLLM alias / deploy config — **not** a shared `model_modes.yaml` `free:` pin (OpenRouter free roster rotates). `llm_mode: free` without an explicit pin raises a clear error (`set agents.llm or DIGI_LLM_MODEL`); non-`:free` (non-Ollama) pins are refused. Having `OPENROUTER_API_KEY` set alone does **not** auto-swap digigraph chat onto paid dashboard models — dashboard/research use `get_model_for_phase()`.

**BYOK spend path** (`llm_auth.py`): user keys via `X-BYOK-Key` / `X-BYOK-Provider` / `X-BYOK-Model` are spent only for routable providers — OpenAI, OpenRouter, Gemini, Anthropic, x.ai. Anthropic uses Anthropic's OpenAI-compatible endpoint (`https://api.anthropic.com/v1`) with the **user's** key (never operator fallthrough). Non-OpenAI BYOK requires `X-BYOK-Model`. This allowlist (`_BYOK_BASE_URLS` / `BYOK_ROUTABLE_PROVIDERS` / `BYOK_MODEL_REQUIRED_PROVIDERS`, plus `_BYOK_MODEL_EXAMPLES` — `_load_byok_catalog` returns three of the four and derives `BYOK_ROUTABLE_PROVIDERS` from the first) is no longer a hand-edited Python dict — it loads from `config/byok-providers.json` once at import time, and a missing or malformed catalog raises there, crashing the process at startup rather than silently 400ing every BYOK request. **One field is exempt from fail-loud, deliberately:** each entry's optional `fallbackModels` is read for exactly one purpose — the `(e.g. …)` parenthetical in `byok_default_model_refusal` — so a bad value there cannot break routing, and `_clean_examples` strips it, drops what it cannot use, warns, and carries on. Fail-loud is there to stop a broken catalog from 400ing every request; escalating a cosmetic parenthetical to a startup crash buys nothing and would newly break an operator catalog carrying `fallbackModels: null`, which imported fine while the key was an untyped extra. It strips because this value is quoted verbatim into user-facing copy — as the entry `id`s are by `byok_provider_unsupported`, but those `_id_non_empty` already strips. Do not "harden" it into a raise — `test_a_malformed_example_list_does_not_crash_startup` pins the tolerance and `test_example_is_stripped_before_it_reaches_user_facing_copy` the strip. Path resolution honors `DIGI_CONFIG_PATH` when set (falling back to a `__file__`-relative repo path otherwise), and the same catalog file is vendored into `infra/digichat-release/config/byok-providers.json` so the Cloudflare stack image and the Profile A self-host compose target — which bake/mount `infra/digichat-release/config` rather than the repo-root `config/` — get it too; a test (`TestByokCatalogVendoredCopy`) pins the two copies as parsed-JSON-equal (not byte-for-byte — a whitespace reformat of either file would still pass) so they cannot silently diverge in content.

`config/byok-providers.json` is the source of truth for the BYOK allowlist **specifically** — i.e. which providers a user-supplied key is actually routed to and spent on. It is not a general provider-base-URL registry for the monorepo: `digillm`'s own `_EXTERNAL_PROVIDERS` table (`digillm/src/digillm/client.py`) is a deliberately separate table serving a different, non-BYOK concern — routing on the *operator's* keys — and `digillm` is a standalone installable library that must not reach for repo-root config. The two tables are not kept in lockstep and are not expected to be: `_EXTERNAL_PROVIDERS` has no `openai` entry at all (operator OpenAI calls don't go through this table), and its `anthropic` base URL still carries a trailing slash that the BYOK catalog deliberately dropped — harmless on both sides, since `digillm/src/digillm/client.py`'s own base-URL comparison strips trailing slashes and the OpenAI-compatible client normalizes it internally regardless — but proof the two lists already diverge in fields where it happens not to matter. Do not "fix" `_EXTERNAL_PROVIDERS` to import from the BYOK catalog.
**`X-BYOK-Model` cannot redirect the bill.** The three headers are independent strings from the caller, so a request could declare `X-BYOK-Provider: openai`, paste a real OpenAI key, and pass `X-BYOK-Model: gemini/gemini-2.5-flash`. Every *registered* provider's slug is re-prefixed to itself before routing and so cannot carry a foreign prefix, but `openai` is deliberately absent from `_EXTERNAL_PROVIDERS` (its canonical slug is bare), so an `openai/`-declared request was the one shape where a foreign prefix survived all the way to `digillm`, which then built a Gemini client on the **operator's** `GEMINI_API_KEY`. The user's key was accepted, shown as active, and never spent. Two predicates in `llm_auth.py` close it: `byok_routable_model(provider, model)` returns the exact slug that will be routed (it strips the provider's own prefix to a **fixpoint**, so applying it twice never doubles a prefix *and* the verdict cannot depend on how many self-prefixes a caller stacked — that invariance is what keeps the middleware, which reads the raw header, and `_apply_byok_model_override`, which reads the once-stripped slug, from disagreeing at prefix depth two), and `byok_model_routes_elsewhere(provider, model)` is true when that routable form leads with a *registered* provider other than the declared one. The rule is a post-condition on the routable form, not prefix equality, because OpenRouter's shipped `anthropic/claude-sonnet-4` vendor sub-slug is legitimate — `openrouter` is registered, so its slug becomes `openrouter/anthropic/…` and the head stays `openrouter`. Membership is read from `digillm`'s registry via `is_registered_provider`, not the BYOK catalog, because the registry is what decides which env-keyed client gets built; `openai`'s absence from it falls out of the rule rather than being special-cased. A mismatch is refused at the middleware with HTTP 400 `byok_model_provider_mismatch` rather than silently answered on the wrong credential, and `_apply_byok_model_override` independently discards a foreign slug so the invariant holds for any caller that reaches the resolver without passing the middleware. Discarding means falling through to the *no-header* branch, not returning the operator-resolved model: those were the same thing until the omission case below gave the no-header branch a refusal of its own, and returning the resolved model here would have routed around it. The warning names the provider only — the model slug is contractually never logged (see `_byok_model_override`).

**No `X-BYOK-Model` is not consent to bill the operator.** The rule above governs a model the caller *named*; omitting the header is the other half of the same invariant. With a key bound and no model, `get_model_for_mode()` used to hand back this deployment's tier default unchanged — and on the shipped release config (`infra/digichat-release/config/model_modes.yaml`) every tier is an `openrouter/…` slug, so the answer was billed to the operator's `OPENROUTER_API_KEY` while the user's key sat bound and displayed as active. That is the same mis-billing as a foreign `X-BYOK-Model`, arrived at by saying nothing (#2490). The refusal is `byok_default_model_provider_mismatch` (HTTP 400) at the middleware and a `ValueError` from `_apply_byok_model_override` for in-process callers — the phase-model path in particular never meets the middleware. It is a **refusal, not a substitution**: digigraph does not pick some default `gpt-4o-mini` on the caller's behalf, because silently choosing a model the user did not choose is the same class of surprise as silently choosing a key. The remediation the message advertises is to send `X-BYOK-Model`.

The operator default is tested **un-normalized**, which is why `byok_operator_model_routes_elsewhere` exists alongside `byok_model_routes_elsewhere` rather than the latter being reused. The caller-facing predicate first runs the slug through `byok_routable_model`, which re-prefixes it to the declared provider — correct for a header the user sent, and fatal here: normalizing `gemini/gemini-2.5-flash` under a declared `openrouter` yields `openrouter/gemini/…`, whose head is `openrouter` by construction, so the verdict would be unconditionally `False` for every registered provider. Both entry points share one core rule (`_routes_to_another_provider`); only the normalization differs. `operator_default_model()` resolves the deployment default with **no** BYOK override applied, so the middleware's question does not depend on middleware ordering. It does not fail open — it *raises* when the default cannot be resolved at all (e.g. `llm_mode: free` with no pin). The fail-**open** is one level up, in the middleware helper `_byok_default_routes_elsewhere` (`server.py`), which catches `_LLM_PROBE_ERRORS` and returns `False`, because a *server* misconfiguration must not turn into a 400 blaming the caller's key. That catch is not partial: both of `operator_default_model`'s raise sites raise `ValueError` (`_FREE_MODE_MODEL_REQUIRED` and `_refuse_paid_in_free_mode`), which is in `_LLM_PROBE_ERRORS`. Nothing escapes through that open failure, by two mechanisms rather than one. On the mode path, `get_model_for_mode` evaluates `operator_default_model()` as the *argument* to `_apply_byok_model_override`, so a failure that recurs re-raises before the resolver is entered — the request fails rather than being billed — while a transient one (`_LLM_PROBE_ERRORS` is wider than the free-mode `ValueError`) lets the resolver judge the same string. On the phase path, `get_model_for_phase` never calls `operator_default_model` at all: the resolver is handed a `phase_models` override or a capability model, not the default judged here, and refuses on that. Either way the refusal — or the failure — lands on whatever the request would actually have been billed for.

digichat forwards `X-BYOK-Model` from all four of its send paths (`chat-panel.tsx`, `use-embed-digi-chat.ts`, the `/api/chat` BFF, and `byok-ping.ts`) whenever the user chose a model — including for providers whose catalog entry sets `requiresModel: false`. That flag decides whether a model is *mandatory*, never whether a chosen one is forwarded; three of the four used to gate the header on it and so dropped an OpenAI user's chosen model on the floor.

**`OLLAMA_MODEL` must not clobber a BYOK bare slug.** After `_apply_byok_model_override` returns the spendable model, `llm_client` still runs it through `resolve_request_model`. For registered providers that path already keeps the slug when a matching BYOK override is bound. OpenAI BYOK models are bare (`gpt-4o-mini`) because `openai` is absent from digillm's registry, so they used to fall into `resolve_effective_model`, which prefers `OLLAMA_MODEL` over the request string. With `OLLAMA_MODEL=ollama/qwen3:8b` set (common on local/free deployments), an OpenAI BYOK chat therefore called `api.openai.com` with model `ollama/qwen3:8b` on the user's key — `model_not_found` while digichat still showed BYOK active. `resolve_request_model` now returns a bare slug unchanged whenever a BYOK override is bound **for a routable provider** (`byok_provider_supported`, not mere presence — see the function's docstring for why presence alone isn't the right gate); without BYOK, `OLLAMA_MODEL` still wins (operator local routing).

This closes only the `OLLAMA_MODEL`-clobber case. A deployment whose *mode default* (`model_modes.yaml`) is itself an Ollama slug — this repo's shipped default — hits the same `model_not_found` by a different path: with no `X-BYOK-Model` header, `_apply_byok_model_override` passes the operator default through unchanged (`byok_operator_model_routes_elsewhere` only refuses *registered*-provider defaults), so `resolve_request_model` now returns that Ollama slug unchanged too, and digillm still sends it to the BYOK provider's endpoint. Not this fix's scope; tracked as a follow-up rather than silently assumed closed.

**Free-quota errors:** provider 429 / RPD under `llm_mode: free` maps to stable code `free_quota_exceeded` (HTTP 429 + SSE `delta.digigraph_error`) for digichat BYOK handoff. Generic rate limits outside free mode use `rate_limit`.

**`delta.digigraph_error` contract (streaming):** `run_digigraph_workflow_streaming` emits an `("error", {"code", "message"})` queue event only when `final["error_code"]` is set (`workflow.py` — without a code, the error is surfaced as plain `content` only). Today that code is written only for `free_quota_exceeded` and `rate_limit` via `_user_facing_llm_error` in `graph/research.py`; both messages are static product copy, never exception text. digichat's stream adapter relays the SSE `message` for those codes; for `BYOK_MODEL_REMEDIABLE_CODES` it relays the code only and lets `embed-chat-error` supply trusted copy (#2536).

CLI: `digi llm-settings` / `python -m digigraph.cli llm-settings` prints effective provider/model/key-env present (never secrets).

### 8.3 digistore for LLM Context Reduction

Search results from digisearch are written to `{run_data_dir}/{session_id}/datasets/` as JSON files. Only a compact preview (5 rows × 300 chars) is injected into the LLM context (`_search_payload_for_llm` in `builtin.py:58`). The full dataset is referenced by `dataset_ref` and loaded on demand by agent runners. This implements the "≥70% token reduction vs naive prompts" target from the architecture principles.

`digistore_get` / `resolve_dataset_ref` enforce the session boundary: a ref (logical name, relative path, or absolute path returned by `digistore_put`) must resolve under `{run_data_dir}/{session_id}/`. Paths that only stay under the run-data root — e.g. `../other_session/datasets/search_1.json` or another session's absolute ref — are rejected. Same-session absolute refs continue to work.

**Write boundary:** `data_manipulation._helpers.write_result` (used by `data_manipulation_agent` / `data_engineer_agent`) accepts only a logical leaf `output_name` (same rules as `digistore._safe_name`). Path separators, `..`, and absolute paths fail closed. When digistore is available, size-cap / validation `ValueError`s also fail closed — they must not fall back to an unsanitized `Path` join under `{run_data_dir}/{session}/datasets/`, which previously allowed cross-session overwrites.

### 8.3.1 Two-tier context compaction (#399)

Long research sessions (document RAG + research `run_research_agent`) accumulate tool results that would otherwise blow past the model context window. digigraph applies **non-destructive** two-tier compaction modelled on LangAlpha's `CompactionMiddleware`:

| Tier | When | What happens |
|------|------|----------------|
| **1 — Truncation** | Tool result outside the last `keep_recent_messages` exceeds `tier1_truncation_kb` (default 2 KB) | Original written to `{run_data_dir}/{session}/workspace/tool_results/msg_<id>.json`; LLM sees `[truncated — full result in workspace/tool_results/msg_<id>.json]` |
| **2 — Summarisation** | Estimated tokens (chars/4) exceed `token_threshold` (default 80 000) | Oldest messages (excluding the recent window and prior summaries) are offloaded to `workspace/compaction/evicted_<event_id>.json`, summarised with `summary_model` (config default `digi/fast` via `digigraph.llm_client.completion_text`), and replaced by a tagged HumanMessage containing `[COMPACTION_SUMMARY]` so later passes do not re-summarise it |

**Integration (pre-LLM step, not a new graph node):**

- `digigraph.compaction.compact_messages` — pure orchestrator (tier 1 then tier 2)
- `graph/research.py` `_run_document_rag_path` — compacts `llm_messages` (+ current turn) before `run_tools`
- `graph/research_agent.py` — same pre-LLM compaction for research/portfolio phase calls (retries re-compact)
- Same-turn tool results are **not** stubbed at `execute_tool` time: digillm already caps injected tool text via `DIGI_TOOL_MESSAGE_MAX_CHARS` (default 12k) while keeping a usable prefix. Stubbing before inject hid digisearch hits from the model whenever `DIGI_RUN_DATA_DIR` was set (typical project RAG).

**State contract:** `WorkflowState._compaction_event` holds a lean `CompactionEvent` dict (refs, counts, token deltas). `WorkflowState.llm_messages` holds the compacted LLM view for the next turn. Originals are **not** deleted from the session workspace — resume reloads them via the event's `tier1_refs` / `tier2_evicted_ref`. Checkpointer policy is unchanged (`DIGI_CHECKPOINTER=memory|sqlite|postgres`).

**Config** (`CompactionConfig` / env):

| Field / env | Default | Notes |
|-------------|---------|-------|
| `enabled` / `DIGI_COMPACTION_ENABLED` | `true` | Master switch |
| `token_threshold` / `DIGI_COMPACTION_TOKEN_THRESHOLD` | `80000` | Tier-2 trigger |
| `keep_recent_messages` / `DIGI_COMPACTION_KEEP_RECENT` | `10` | Intact recent window |
| `tier1_truncation_kb` / `DIGI_COMPACTION_TIER1_KB` | `2` | Tool-result size floor |
| `summary_model` / `DIGI_COMPACTION_SUMMARY_MODEL` | `digi/fast` | Resolved through `llm_client` / `resolve_request_model` |

### 8.4 Parallel Tool Execution

When the LLM returns multiple tool calls in one turn and all tools are tagged `parallel_safe` (currently: `visualization_agent`, `analysis_agent`, `data_prep_agent`, `data_manipulation_agent`, `data_engineer_agent`, delegate tools), they are dispatched in parallel via `ThreadPoolExecutor` inside `digillm.run_tools` (the `parallel_safe` set is computed from the registry in `llm_client.py` and passed through). Tool results are appended to the conversation in original order. This reduces multi-tool latency from O(n×tool_time) to O(max_tool_time).

Every submission — here and in `planning/executor.py`'s layer fan-out — goes through a **freshly copied context** (`contextvars.copy_context().run(...)`). A pool worker starts with an empty context, and these tools are the delegate agents: each one runs its *own* LLM completion, so without the copy a BYOK request spends the operator's key inside the fan-out while the user's is bound on the calling thread. Unlike the streaming worker in §3.3 this hop is on the non-streaming path too. The copy must be per submit: one shared `Context` cannot be entered by two threads at once and raises `RuntimeError: cannot enter context ... is already entered` in the second — `test_parallel_branch_carries_the_byok_override_into_each_worker` uses a `threading.Barrier` to force the overlap that makes that regression visible.

A copy propagates *references*, so the same submission must **not** carry the logical-call telemetry handle: all N workers would hold the one mutable `ProviderCallContextHandle` the caller holds and race its `last_call_id` and deferred-record list. That handle is bound in **two** context vars, and clearing one is not enough — `digillm`'s own `_provider_call_metadata`, and `usage._LOGICAL_CALL_CONTEXT`, which digigraph layers on top and which stores the same object inside its frozen `LogicalCallContext`. So both fan-out sites drop both: `digillm.detach_provider_call_context()` and `usage.detach_logical_call_context()`, inside the worker before any work — propagate credentials, not the mutable handle.

The two sites reach the second clear differently. `digillm.run_tools` owns its own pool, so `llm_client` registers `usage.detach_logical_call_context` once via `digillm.set_fan_out_detach_hook` — a consumer callback in the same idiom as the usage and telemetry observers registered beside it, because a leaf library cannot import into its consumer to clear a var it does not own. `planning/executor.py` submits to its own pool, where that hook never fires, so `_run_step_in_fan_out` calls both functions directly — behind a guard, because they run *outside* `_run_step`'s handler and `run_plan` reads `future.result()` bare, so an unguarded `ImportError` on the worker-local imports would discard the whole layer where the single-step branch degrades to one error string. Skipping the detach costs nothing there: the module that binds the handle is the module that failed to import, so no bound handle is left to share. A detach that *itself* raises still propagates.

Both clears are token-free by necessity: a copied context carries values but no reset tokens. `_CALL_CONTEXT` is deliberately left **inherited** — its `CallContext` is frozen and holds no mutable state, so the node identity crossing the boundary costs nothing and improves attribution. The single-step path in `planning/executor.py` deliberately skips the wrapper entirely: it runs in the caller's own context rather than a copy of it, so unbinding the handle would lose the caller's deferred records; `test_the_pool_does_not_share_the_telemetry_handle` fails if that path is routed through the wrapper.

### 8.5 SSE Streaming for Time-to-First-Token

Streaming via the background thread + queue delivers tool call blocks to the client as soon as each tool completes, rather than waiting for the full workflow. Reasoning content is buffered and delivered as a `<thinking>` block just before the first `content` chunk — this means reasoning latency adds to the first visible token time.

### 8.6 OpenAI Client Connection Pooling

`get_client()` caches `OpenAI` instances by `(api_key, base_url)`. The `OpenAI` SDK uses an `httpx.Client` with connection pooling under the hood, avoiding per-request TCP handshakes. The cache is invalidated when env vars change, which covers test scenarios with different API keys.

---

## 9. Integration Points

### 9.1 digisearch

**Protocol:** HTTP via `digisearch_hub.py`

- **Manifest:** `POST /v1/orchestrator_tools` — returns OpenAI tool dicts for `digisearch`, `digisearch_fetch_all`, `digisearch_research_delegate` (federated mode). Cached per `(base_url, index_config)`.
- **Invoke:** `POST /v1/orchestrator_invoke` — dispatches tool execution. Accepts `{tool, arguments, default_index_name}`.
- **Legacy:** `tools/digisearch.py` uses `POST /query` for non-orchestrator call sites (e.g. `_run_quant_or_augmented_path` in `research.py`).
- **Auth:** Bearer token from `WorkflowState.digi_bearer` is forwarded via `Authorization: Bearer` header.
- **Request correlation:** `X-Request-ID` forwarded from `ToolContext.request_id`.
- **Filters:** `research_filters` and `evidence_tier_preference` from state are merged into every digisearch call by `_merged_digisearch_filters` in `builtin.py:34`.
- **Env:** `DIGISEARCH_URL` (required; empty = digisearch tools disabled). In Docker: `http://digisearch:8002`.

### 9.2 digiquant

**Protocol:** HTTP via `digiquant_hub.py` (federated mode) + direct `httpx` in `graph/nodes.py` (backtest/optimize nodes)

- **Manifest:** `POST /v1/orchestrator_tools` — returns tool dicts for `digiquant_pipeline_delegate`. Cached per `base_url`.
- **Invoke:** `POST /v1/orchestrator_invoke` — dispatches pipeline tool. Timeout: 600s.
- **Backtest node (direct):** Tries `POST /v1/jobs/backtest` first; falls back to `POST /backtest/start` + SSE progress, then `POST /run_backtest`. Polls `GET /v1/jobs/{id}/status` for async jobs; fetches result via `GET /backtest/{id}/result`.
- **Optimize node (direct):** `POST /run_optimize`. Timeout: 300s.
- **Auth:** Bearer via `outbound_service_headers(request_id, bearer)` from `digibase.http`.
- **Env:** `DIGIQUANT_URL` (default `http://127.0.0.1:8001` when unset). Explicit empty `DIGIQUANT_URL=` disables the backtest route (Profile A / chat-only). `DIGIQUANT_DATA_DIR` required for backtest and optimize nodes when digiquant is enabled.

### 9.3 digikey

**Protocol:** JWT validation middleware (in-process)

- `DigiAuthMiddleware` from `digikey.integrations.service_middleware` validates JWTs on every non-health request.
- Configuration: `DIGIKEY_JWKS_URL` (JWKS endpoint, e.g. `http://digikey:8005/.well-known/jwks.json`) or `DIGIKEY_PUBLIC_KEY_PEM`.
- `DIGIKEY_ISSUER` and `DIGIKEY_AUDIENCE` for claim validation.
- The middleware populates `request.state.digi_auth` (key_prefix, tenant_slug, project_id, jti) and `request.state.digi_bearer` (raw token) for downstream use.
- Per-request LiteLLM proxy key override: `X-LiteLLM-Proxy-Key` header is parsed by the `lite_llm_proxy_header_context` middleware (`llm_auth.py`) and forwarded to digillm's proxy-key `ContextVar`, used by digillm's client.

### 9.4 digismith

**Protocol:** Library calls (no HTTP)

- `digismith.trace.traceable` decorates `completion` and `run_tools` in `digillm`.
- Activates when `LANGSMITH_API_KEY` is set and `langsmith` is installed.
- Span attributes must include `workflow_id`, `request_id`, `session_id`. Raw prompts, API keys, and full doc bodies must not appear in spans.
- In Docker Compose, a digismith container exposes `GET /v1/status` on port 8003. digigraph does not make HTTP calls to digismith; the library communicates with LangSmith directly.

### 9.5 digichat

**Protocol:** HTTP (digichat → digigraph)

- digichat (Next.js BFF) proxies browser requests to `POST /v1/chat/completions` with `stream: true`.
- digichat forwards `X-Session-Id` (browser session), `X-LiteLLM-Proxy-Key` (from digikey token exchange), and `X-Allowed-Tools` headers.
- The `_digi_fields_from_request` helper in `server.py:145` extracts digikey JWT fields from middleware state and injects them into `WorkflowRequest` for audit correlation.
- digichat receives `digigraph_trace` SSE deltas in `delta.digigraph_trace` for tool block rendering.
- Internal URL in Docker: `DIGIGRAPH_INTERNAL_URL=http://digigraph:8000`.

### 9.6 LiteLLM

**Protocol:** OpenAI SDK to LiteLLM proxy

- digillm's `get_client()` (used by digigraph via `llm_client`) creates an `OpenAI` instance pointed at `OPENAI_API_BASE` (default: `http://litellm:4000/v1` in Docker).
- All LLM calls (research, brief builder, synthesis) go through LiteLLM, which routes to Ollama, OpenAI, or other configured providers.
- Model selection: `get_model_for_mode()` returns the model ID from `config/model_modes.yaml` for the current mode. LiteLLM translates provider-prefixed IDs (e.g. `ollama/qwen3:8b`) to the target provider's expected format.
- **Model routing:** callers must pass a concrete model string. digiquant
  phase pins in `config/digiquant_models.yaml` are **unprefixed** OpenRouter
  slugs listed as `model_name` entries in `config/litellm.yaml` so traffic is
  always caller → digillm → LiteLLM → vendor (or the user's OpenAI-compat
  endpoint). House keys and BYOK keys both stay on that path: BYOK is passed
  through LiteLLM as request `api_key` / `api_base` (clientside credentials),
  not as a direct vendor HTTP client. Registered prefixes (`openrouter/`,
  `gemini/`, `anthropic/`, `xai/`) are leftover caller spellings and
  no-proxy diagnostics — they do not skip a LiteLLM `OPENAI_API_BASE`. The
  leftover CLI rewrite (`apply_digiquant_openrouter_env` in
  `digigraph/src/digigraph/model_config.py`) points the default base at
  `openrouter.ai`; that is not LiteLLM, so prefixed BYOK uses the user Bearer
  against the vendor URL and leftover `gemini/` / `xai/` stay vendor clients.
  `openrouter/auto`
  remains the diagnostic auto-router id (preflight structured-output probe),
  not a phase pin. Grounding uses unprefixed `:online` / `perplexity/*` slugs
  via `get_grounding_model()`. Optional OmniRoute is a separate overlay
  (`config/litellm.omniroute.yaml`, compose profile `omniroute`) — off by
  default; do not cut house pins over to it. See `docs/providers/omniroute.md`.
- Caching: LiteLLM supports Redis-backed semantic caching when `REDIS_URL` is set (Compose profile: `litellm-cache`).

### 9.7 digivault

**Protocol:** HTTP via `digivault_hub.py`

- **Manifest:** `POST /v1/orchestrator_tools` — returns the OpenAI tool dicts for `digivault_search_notes` and `digivault_get_note` (and other digivault-owned tools digigraph does not register). Cached per `base_url` (no `index_config` — vault search is not index-scoped).
- **Invoke:** `POST /v1/orchestrator_invoke` — for `digivault_search_notes`, dispatches to D1 FTS5 when configured, else the local filesystem vault, else `SupabaseStore.search` (the `search_architecture_notes` RPC); for `digivault_get_note`, a D1-only note fetch by `vault_path` (no filesystem/Supabase fallback). Accepts `{tool, arguments}`.
- **Auth:** Bearer token from `WorkflowState.digi_bearer` is forwarded via `Authorization: Bearer` header; `X-Request-ID` forwarded from `ToolContext.request_id`.
- **Env:** `DIGIVAULT_URL` (empty = the `digivault` skill is not registered for the request; other skills are unaffected). In Docker: `http://digivault:8004`.
- **Tenant scoping:** both handlers overwrite the `path_prefix` argument from `ToolContext.vault_path_prefix` unconditionally before invoking — a model-supplied `path_prefix` is always discarded, never merely defaulted-if-omitted, so the model cannot read another tenant's corpus. With no context prefix (unmapped tenant slug), `path_prefix` is passed through as `None`. `digivault_get_note` is D1-only, so this always ends in digivault's handler refusing the unscoped call with `ok=False` rather than falling back to a full-vault read (D1 has no unscoped mode). `digivault_search_notes` refuses the same way on D1, but that refusal is deployment-scoped: on a non-D1 backend (local filesystem vault, or Supabase), a `None` prefix is treated as "no filter" rather than refused — `search_local_vault` (`digivault/src/digivault/local_search.py:88`) and `SupabaseStore.search` both then read across the whole corpus. Production is D1-backed, so this gap only reaches a non-D1 deployment.
- **Error surfacing:** `invoke_digivault_tool` calls `raise_for_status()`, which raises and drops the response body on any non-2xx status — so a *raised* HTTP error from digivault reaches the model as a bare status code, never the `detail` string. digivault's argument-validation failures (e.g. missing `path_prefix`) are therefore returned as `OrchestratorInvokeResponse(ok=False, error=...)` at HTTP 200, specifically so the reason string survives this hop.
- **Purpose:** reproduces the vault-grounded documentation search the digithings.ai chat widget calls directly today ([ADR-0018](../docs/adr/0018-digichat-path-routing.md), epic #1248) — the tool digichat's BFF needs once traffic moves off the bespoke widget onto digigraph. `digivault_get_note` extends this to full-note loads so the model is not limited to reasoning from a short excerpt.

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
| `DIGIQUANT_URL` | `http://digiquant:8001` | digiquant HTTP base URL |
| `DIGISEARCH_URL` | `http://digisearch:8002` | digisearch HTTP base URL; empty = search disabled |
| `DIGIVAULT_URL` | `http://digivault:8004` | digivault HTTP base URL; empty = `digivault_search_notes` / `digivault_get_note` disabled |
| `DIGISMITH_URL` | `http://digismith:8003` | digismith status URL (unused by digigraph HTTP) |
| `DIGIKEY_JWKS_URL` | `http://digikey:8005/.well-known/jwks.json` | JWT public key endpoint |
| `DIGIKEY_ISSUER` | `http://digikey:8005` | JWT issuer claim |
| `DIGIKEY_AUDIENCE` | `digi-ecosystem` | JWT audience claim |
| `DIGIKEY_PUBLIC_KEY_PEM` | (empty) | Static PEM alternative to JWKS |
| `OPENAI_API_BASE` | `http://litellm:4000/v1` | LLM proxy base URL |
| `OPENAI_API_KEY` | (from `.env`) | API key for LLM proxy (fallback to `LITELLM_PROXY_API_KEY`) |
| `LITELLM_PROXY_API_KEY` | (from `.env`) | LiteLLM bearer; overrides `OPENAI_API_KEY` for proxy calls |
| `DIGI_LLM_MODE` | `test` | LLM model tier: `test` / `medium` / `best` |
| `DIGI_CONFIG_PATH` | `/app/config` | Directory containing `model_modes.yaml` **and** `byok-providers.json` — a mount missing `byok-providers.json` crashes digigraph at startup (`_load_byok_catalog` fails loud, by design; see the BYOK spend path note above) — as does one whose entries carry a bad `id`, `baseUrl` or `requiresModel`, **but not** a bad `fallbackModels`, the one cosmetic field, which is cleaned and warned about instead; a mount missing `model_modes.yaml` does **not** crash — `_load_model_modes()` silently falls back to a hardcoded default model instead, so supply both regardless |
| `DIGI_PROJECT_CONFIG` | (empty) | Path to project YAML (optional) |
| `DIGI_CHECKPOINTER` | `sqlite` when project active, else `memory` | Checkpointer backend: `memory` / `sqlite` / `postgres` / `none` |
| `DIGI_CHECKPOINTER_SQLITE_URI` | `~/.digigraph/checkpoints.sqlite` | SQLite file path |
| `DIGI_CHECKPOINTER_POSTGRES_URI` | (empty) | Postgres connection string |
| `DIGIQUANT_URL` | `http://127.0.0.1:8001` when unset | digiquant base URL. Explicit empty string disables backtest routing (Profile A). |
| `DIGIQUANT_DATA_DIR` | `/app/data` | Path to CSV files for backtests (required only when digiquant is enabled) |
| `DIGISEARCH_INDEX` | `default` | Default vector index name |
| `DIGI_TENANT_CORPUS_MAP` | (empty) | Optional JSON map of tenant slug → `{digisearchIndex, vaultPathPrefix, researchSystemPrompt}` for multi-tenant corpus isolation (OCC). When non-empty, the map is **authoritative** for the authenticated tenant — client headers `X-Digi-Corpus-Index` / `X-Digi-Vault-Prefix` and body `digisearch_index` / `vault_path_prefix` cannot select another tenant's corpus (digisearch has no server-side tenant→index bind). Unmapped / empty-tenant requests clear those fields to `None` on the request **and** in `_initial_graph_state` so LangGraph checkpoints do not keep a prior turn's index sticky on a reused `session_id`. When unset (single-tenant), those headers may still select corpus. **Unset ≠ broken:** a set-but-unusable value (invalid JSON, non-object top level, or every entry individually dropped) raises `TenantCorpusMapError` → HTTP 503 — same fail-closed contract as digivault `tenant_scope` — and never silently re-enables client corpus selection. Slug keys are lowercased on parse so `OCC` matches digivault's keys. |
| `DIGI_ENABLE_DEBUG_ENDPOINTS` | `0` | Enable `/test_llm` and `/v1/debug/*` |
| `DIGI_ENABLE_THREAD_API` | `0` | Enable `/threads/*` and `/files/*` |
| `DIGI_SUPERVISOR` | (empty) | Enable supervisor node: `1` / `true` |
| `DIGI_HUB_MODE` | `legacy` | Hub mode: `legacy` (default) or `federated` |
| `DIGI_WORKFLOW_PROFILE` | `full_stack` | Workflow profile when not set in project config |
| `DIGI_RESEARCH_BRIEF` | (unset → YAML / default on) | Override `agents.research_brief`: `0`/`false` skips ResearchBrief post-pass |
| `DIGI_ALLOWED_TOOLS` | (empty) | Comma-separated allowlist (env fallback) |
| `DIGI_REQUIRE_TOOL_CALLS` | (empty) | Force `tool_choice="required"` deployment-wide: `1`/`true` |
| `DIGI_REQUIRE_TOOL_CALLS_RATE_LIMIT_MAX` | `3` | Per-IP req/min budget for requests opting into `require_tool_calls=true` (see §3.1) |
| `DIGI_ALLOW_CODE_EXEC` | (empty) | Enable `data_engineer_agent` code execution: `1` / `true` |
| `DIGI_RUN_DATA_DIR` | (empty) | Session dataset storage; enables `project_rag` skill |
| `DIGI_DISABLE_RATE_LIMIT` | (empty) | Disable rate limiting for tests/dev |
| `DIGI_CORS_ORIGINS` / `DIGIGRAPH_CORS_ORIGINS` | (empty) | CORS allowlist — applied via shared `digibase.cors.install_cors`. `DIGI_ALLOWED_ORIGINS` still honored as legacy fallback. See `SECURITY.md` §"CORS policy". |
| `DIGI_TOOL_MESSAGE_MAX_CHARS` | `12000` | Max chars per tool result message to LLM |
| `DIGI_COMPACTION_ENABLED` | `1` | Two-tier context compaction master switch (#399) |
| `DIGI_COMPACTION_TOKEN_THRESHOLD` | `80000` | Tier-2 summarisation trigger (approx tokens) |
| `DIGI_COMPACTION_KEEP_RECENT` | `10` | Messages kept intact at the tail |
| `DIGI_COMPACTION_TIER1_KB` | `2` | Truncate tool results above this size (KB) |
| `DIGI_COMPACTION_SUMMARY_MODEL` | `digi/fast` | Model for tier-2 summaries (via `llm_client`) |
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
| **Remote MCP enumeration** | digigraph cannot discover or integrate arbitrary third-party MCP servers | Only in-process registry + digisearch/digiquant vertical HTTP |
| **OpenAI Responses API** | Not implemented; Chat Completions is the only LLM protocol | LiteLLM `/v1/responses` compatibility noted as future path |
| **Distributed checkpoints** | MemorySaver/SQLite are single-node; Postgres has no advisory locks | Single digigraph instance |
| **Per-user RBAC** | JWT subject not bound to checkpoint or tool access | Shared `thread_id` namespace; allowlists are per-request not per-user |
| **Auth-bound checkpoints** | `thread_id` is caller-supplied; no ownership enforcement | Trust the client not to use other users' thread IDs |
| **Request cancellation** | No mechanism to cancel in-flight streaming workflows | Background threads run to completion |
| **digiclaw subgraph exposure** | digiclaw can attach only to the hub, not to vertical MCP servers directly | digiclaw calls `/workflow` only |

---

## 12. Redesign Recommendations

The following are critical recommendations based on observed architectural gaps:

### 12.1 Distributed Checkpointing with Postgres Advisory Locks

**Problem:** Multiple digigraph replicas with shared Postgres checkpoints can interleave writes to the same `thread_id`, corrupting state.

**Recommendation:** Wrap each `graph.invoke()` call with a Postgres advisory lock keyed on `hash(thread_id)`. The `PostgresSaver` in `langgraph-checkpoint-postgres` does not implement this. A thin wrapper should acquire an advisory lock before `invoke` and release it in a `finally` block. Use `pg_try_advisory_xact_lock` for timeout semantics. This enables true horizontal scaling with guaranteed per-thread serialization.

### 12.2 Per-Request Cancellation Tokens

**Problem:** Client disconnects leave orphaned workflow threads consuming LLM tokens and downstream service connections indefinitely.

**Recommendation:** Introduce a `threading.Event` per streaming request. Pass it into `run_digigraph_workflow_streaming` as a `cancel_event` argument. The research tool loop should poll `cancel_event.is_set()` between tool rounds (after each `event_queue.put`). The streaming generator should set the event when it detects client disconnect (when `StreamingResponse` generator raises `GeneratorExit`). This bounds the maximum waste to one tool round's latency.

### 12.3 Thread State Scoping to digikey JWT Subject

**Problem:** Any authenticated caller can read any thread's state. In multi-tenant deployments, `session_id` collisions (especially `"default"`) expose one tenant's data to another.

**Recommendation:** Prefix `thread_id` with the JWT `sub` claim extracted from `request.state.digi_auth`. In `workflow.py:_initial_graph_state`, set the LangGraph config `thread_id` to `f"{jwt_sub}:{session_id}"` when a subject is available. The thread state endpoints should enforce that the `thread_id` path parameter matches the caller's `sub` prefix. This provides tenant isolation without requiring a separate authorization database.

### 12.4 Sandboxed Code Execution

**Problem:** `data_engineer_agent` executes arbitrary Python code (Polars operations). Even with `DIGI_ALLOW_CODE_EXEC` as a gate, the execution is in the same process as digigraph with access to all environment variables (including API keys) and the full filesystem.

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

**Problem:** There are no observable performance or business metrics exported from digigraph. Operators cannot measure request latency, LLM cache hit rates, tool call counts, or streaming session counts without parsing logs.

**Recommendation:** Add `prometheus-client` as a dependency. Expose `GET /metrics` (Prometheus text format) with:
- `digigraph_workflow_duration_seconds` (histogram, labels: profile, has_backtest)
- `digigraph_llm_cache_hits_total` / `digigraph_llm_cache_misses_total`
- `digigraph_tool_calls_total` (labels: tool_name, status)
- `digigraph_active_streaming_sessions` (gauge)
- `digigraph_rate_limit_rejections_total` (labels: path)

This complements digismith's LangSmith tracing with operational metrics visible to Grafana or similar systems.

### 12.7 Compiled Graph Cache

**Problem:** `build_workflow_graph()` is called on every `run_digigraph_workflow` invocation. LangGraph graph compilation is not free — it resolves all node references and edge conditions.

**Recommendation:** Cache the compiled graph as a module-level singleton, invalidated only when `DIGI_SUPERVISOR`, `DIGI_CHECKPOINTER`, `DIGI_INTERRUPT_AFTER_RESEARCH`, or related env vars change. The checkpointer instance is already a singleton; the compiled graph should be too.

### 12.8 X-Forwarded-For Validation

**Implemented (REM-027):** `rate_limit.py` reads `DIGI_TRUSTED_PROXIES` (comma-separated hosts/CIDRs, matched via `ipaddress` so entries and observed peers are compared as parsed addresses, not raw strings). `X-Forwarded-For` is honored only when the direct client is in that set, walking the chain from the right and skipping trusted hops to find the first non-trusted, IP-parseable entry; otherwise the limiter uses `request.client.host`.

Operators must list **every** hop between the internet and this service, not just the innermost reverse proxy — e.g. a CDN edge in front of an internal load balancer needs the CDN's own egress ranges in `DIGI_TRUSTED_PROXIES` too. Omitting an intermediate hop makes it look like a non-trusted entry, so the limiter returns that hop's own address (not the true client) as the bucket key, coarsely grouping every client behind the omitted hop into one bucket.

A `DIGI_TRUSTED_PROXIES` entry that parses as neither a valid IP/CIDR nor a widen-able one (e.g. a typo like `10.0.0.999`) is dropped and logs a `logger.warning` naming the bad entry (#2378) — previously this failed silently, so a typo'd entry left the intended proxy permanently untrusted with no diagnostic trail.

`_get_ip()` re-reads and re-parses `DIGI_TRUSTED_PROXIES` on every request (so a config change takes effect without a restart), which would otherwise re-run that warning on every single request for a misconfigured entry — a log-flood risk under normal traffic. `_parse_trusted_proxies` caches its parsed result per `RateLimiter` instance, keyed by the exact raw env-var string, so the warning fires once per distinct misconfigured value that instance has seen rather than once per request; a genuine config change (a new raw string) still gets parsed, and still warned about if still invalid.

## Observability

This service exposes a Prometheus `/metrics` endpoint (counter, histogram, in-flight gauge for every HTTP route) via `digibase.metrics.install_metrics`; scraped by the `observability` compose profile per [ADR-0003](../docs/adr/0003-observability-baseline.md).

## Input Validation Posture

All HTTP request bodies are typed with Pydantic v2 models using `ConfigDict(extra="forbid")`, which rejects unknown fields with HTTP 422 at the framework boundary. Shared validation-error shape lives in `digibase.errors`.

## Generic Research Agent + Pipeline Builder (Phase Sub-graphs)

`digigraph/src/digigraph/graph/research_agent.py` and
`digigraph/src/digigraph/graph/pipeline_builder.py` provide reusable
primitives for composing phase-structured research sub-graphs. The digiquant
research migration (issue #176, ADR-0009) is the first consumer.

- `run_research_agent(skill_text, phase_inputs, shared_context, output_model)` —
  calls LiteLLM with an analyst-persona system prompt, injecting a skill file
  as the "what to research" context and a Pydantic class as the "what shape
  to return." Stable blocks (shared context, skill, output schema) carry
  `cache_control: ephemeral` for Anthropic prompt caching.
  - **Two request shapes, and the retry deliberately switches between them (#1739).**
    Without `tools` the call is `completion_text(..., response_format=json_schema
    strict)` — provider-side schema enforcement. With `tools` the first attempt is
    `run_tools(...)` and carries **no** `response_format`, because `digillm`'s
    `completion` drops that field whenever `tools` is set. So a chatty model can
    answer a tool-grounded turn with a prose preamble that fails `json.loads` at
    char 0.
  - Therefore **every retry is tool-free and enforced**, never a second tool loop.
    `digillm.run_tools` builds its tool-result conversation in a local copy and
    returns only the final string, so re-running it would re-bill 2-6 completions to
    rebuild grounding the caller cannot see — and still send no `response_format`.
    The failing attempt's raw text is already in the conversation, so one tool-free
    `completion_text` call asks the provider to re-emit it as schema-valid JSON.
  - If the enforced retry itself fails at the provider, the **original** parse error
    is re-raised, so downstream fail-soft handlers see the same exception shape they
    saw before this behaviour existed.
- `build_pipeline(state_cls, phases)` — compiles a `list[PipelinePhase]` into
  a LangGraph `StateGraph`. Phases run sequentially; nodes inside a phase
  run in parallel with synthetic fan-in barriers. The `__barrier__` prefix
  is reserved.

These primitives stay research-agnostic on purpose. Any sub-graph that wants
phase-structured parallel research can reuse them by declaring its own
phase list.
