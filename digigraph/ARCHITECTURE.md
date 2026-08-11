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
| `GET` | `/v1/models` | digikey JWT (optional) | 30 req/min/IP | OpenAI model list; returns `sitaas-rag` |
| `GET` | `/v1/model-info` | digikey JWT (optional) | 30 req/min/IP | Current model + mode |
| `POST` | `/v1/chat/completions` | digikey JWT (optional) | 10 req/min/IP | OpenAI chat completions; body: `ChatCompletionRequest`; supports `stream: true` |
| `GET` | `/v1/debug/input_messages` | digikey JWT | 30 req/min/IP | Last N request summaries; **requires `DIGI_ENABLE_DEBUG_ENDPOINTS=1`** |
| `GET` | `/test_llm` | digikey JWT | 30 req/min/IP | LLM connectivity test; **requires `DIGI_ENABLE_DEBUG_ENDPOINTS=1`** |
| `GET` | `/threads/{thread_id}/state` | digikey JWT | 30 req/min/IP | LangGraph checkpoint state; **requires `DIGI_ENABLE_THREAD_API=1`** |
| `GET` | `/threads/{thread_id}/history` | digikey JWT | 30 req/min/IP | Full checkpoint history; **requires `DIGI_ENABLE_THREAD_API=1`** |
| `POST` | `/threads/{thread_id}/resume` | digikey JWT | 30 req/min/IP | Resume interrupted workflow; **requires `DIGI_ENABLE_THREAD_API=1`** |
| `GET` | `/files/{path:path}` | digikey JWT | 30 req/min/IP | Serve exported files from `run_data_dir`; **requires `DIGI_ENABLE_THREAD_API=1`** |

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
   - `reasoning` — accumulated into a `<thinking>` block before the first `content` chunk (skipped when `X-Suppress-Tool-Stream` is set)
   - `trace` — `TraceEventV1` dicts embedded in `delta.digigraph_trace` for digichat
   - `done` — terminates the generator loop
4. If the client disconnects mid-stream, the generator raises an exception; the background thread continues running until it completes naturally. There is no cancellation token or thread interrupt mechanism — see Section 6 (Security Analysis).

---

## 4. Data Model

### 4.0 Olympus call-event capture

`usage.start()` activates ordered aggregate events and a temporary, lock-protected detailed
telemetry buffer for an Olympus process. `digillm` contributes terminal model/search events;
`graph/research_agent.py` times actual tool execution. `call_context(node_run_id, phase, operation,
document_key)` labels model/search calls, while the tool wrapper also passes display labels
explicitly because `ContextVar` state does not propagate into `ThreadPoolExecutor` workers.

`RunCallEvent` is a frozen Pydantic v2 model. It stores fixed labels, status, duration, retries,
usage totals, source count, and code-generated shape summaries. All public text is length-bounded.
It never stores prompts, argument or result values, document bodies, credentials, PII-heavy
values, model output, or chain-of-thought. `events_snapshot()` returns the ordered body-free
records; aggregate `snapshot()` includes them under `events` for the Atlas diagnostics writer.

#### Logical provider-call boundary

**Purpose:** label each logical provider invocation with generic intent, parentage, and artifact
disposition. **Reason:** the aggregate explains run totals and physical attempts explain transport,
but neither explains why a call existed or which prior call caused a repair or follow-up.
**Intent:** make provider work attributable without moving Olympus policy into digigraph or adding
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
second identifier is minted; `AtlasResearchState.run_id` is a per-process `uuid4` that joins to
nothing and is deliberately not used.

**When identity is unavailable, nothing is recorded.** This is the honest case, not a gap:

| Case | `run_id` | Effect |
|------|----------|--------|
| CI, via `cli_main` | `GITHUB_RUN_ID` | Node records join the diagnostics row |
| Off CI, via `cli_main` | `{cadence}-{run_date}-local` — reused, not minted | `-local` is a suffix no CI run id can carry, so the two can never be confused |
| `deps.diagnostics is None` (library/test callers) | `None` | No node records, no logical calls; physical attempts unchanged. Such a run writes no diagnostics row either, so there is nothing to reconcile against |
| Blank/whitespace | normalised to `None` | `run_id text NOT NULL CHECK (length(run_id) > 0)` can never be violated from this producer |
| `usage.start()` with no argument (operator scripts, the Atlas simulator, the chat workflow) | `None` | Emits nothing **by design** |

**A NULL `fanout_key` means "this execution had no fan-out cursor", never "instrumentation
missing".** Atlas `phase5_sectors` nodes and the compile-time per-ticker H5/H6 variants already
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
| `allowed_tool_names` | `list[str] \| None` | Tool allowlist; `None` = unrestricted |
| `strategy_name` | `str` | LLM-extracted strategy for digiquant |
| `symbols` | `list[str]` | Ticker list |
| `strategy_params` | `dict[str, Any]` | Optional pre-filled digiquant parameters |
| `trading_profile` | `dict[str, Any]` | User/tenant trading profile; merged into `optimization_constraints` |
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
| `stream_callback` | `Callable` | Not serialized; injected per-request for streaming |
| `workflow_profile` | `str` | Active profile (`full_stack`, `research_rag`, `quant_backtest`, `plan_execute`) |
| `digisearch_index` | `str \| None` | Per-request digisearch index override (`X-Digi-Corpus-Index` / tenant map). **Must** be declared — LangGraph drops undeclared keys. |
| `vault_path_prefix` | `str \| None` | Per-request digivault path prefix (`X-Digi-Vault-Prefix` / tenant map) |
| `research_system_prompt_override` | `str \| None` | Optional research system prompt from tenant corpus map |
| `response_language` | `str \| None` | Per-request response-language code (`X-Digi-Language`). **Must** be declared — LangGraph drops undeclared keys. See `digigraph.languages`. |
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
| `research_filters` | `list[dict] \| None` | Injected into digisearch calls |
| `digi_bearer` | `str \| None` | JWT propagated downstream |
| `digi_trace_key_prefix` / `digi_trace_tenant` / `digi_trace_project_id` / `digi_trace_jti` | `str \| None` | digikey audit fields |
| `evidence_tier_preference` | `list[str] \| None` | Evidence tier filter |
| `response_language` | `str \| None` | Per-request response-language code (`X-Digi-Language`); see 4.1 |

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
| `model` | `str` | Default `"sitaas-rag"`; not used for routing (LiteLLM handles it) |
| `messages` | `list[ChatMessage]` | Role + content; content coerced from AI SDK part lists. Flattened into the workflow `prompt` via `chat_prompt.messages_to_workflow_prompt` — **full user+assistant history** (multi-turn), not user-only |
| `stream` | `bool` | SSE streaming |
| `openwebui_format` | `bool` | Open WebUI `<details>` tool blocks. Enabled only by this field or `X-Response-Format: openwebui` — **not** by `model=sitaas-rag`. Opt out via `X-Suppress-Tool-Stream` or `X-Response-Format: plain\|neutral\|none\|digichat` |
| `session_id` | `str \| None` | Conversation isolation |
| `allowed_tools` | `list[str] \| None` | Tool allowlist for this request |

---

## 5. Internal Architecture

### 5.1 Module Structure

```
digigraph/src/digigraph/
├── chat_prompt.py               Flatten OpenAI chat messages → workflow prompt (multi-turn)
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

When `agents.always_retrieve_tools` is set, `research_node` (document RAG path) invokes those tools **before** the LLM turn, injects `[tool_name results]…` blocks into the user message, and **strips** those tool names from `tools_for_llm` so the model cannot re-call the same retrieval tools. Prefetch passes `top_k=4` for digisearch and `limit=3` for `digivault_search_notes` so a tiny seed corpus does not dump the whole index every turn. If no tools remain, `run_tools` runs a single streamed completion (no tool rounds).

`agents.research_brief` (default `true`; env `DIGI_RESEARCH_BRIEF=0/1` overrides) controls whether `build_research_subgraph()` wires `research_brief_builder` after `research_inner`. When false, the subgraph ends when the answer stream completes — dogfood chat uses this to avoid a post-answer `completion_text` latency tax.

The graph is compiled once per `build_workflow_graph()` call. In practice, `workflow.py` calls `build_workflow_graph()` on **every** request — there is no module-level compiled graph cache. This means the StateGraph is recompiled on each call; the checkpointer instance is shared (process-wide singleton).

### 5.3 Orchestrator Tool Registry Pattern

Three-layer structure:

1. **Primitives** (`tools/`): stateless callables not exposed to the LLM directly.
2. **Orchestrator tools** (`orchestration/`): `(name, schema, handler, tags)`. Schema may be a static dict or a `SchemaFactory(context) -> dict` for context-dependent schemas (e.g. digisearch tools fetched from the vertical manifest). Registered once at module import via `_register_tools()` at the bottom of `builtin.py`.
3. **Skills** (`orchestration/registry.py`): named bundles of tool names with a `when(context) -> bool` predicate. The `search` skill activates only when `DIGISEARCH_URL` is set. The `sitaas_rag` skill activates only when `run_data_dir` is set. The `digivault` skill (one tool, `digivault_search_notes`) activates only when `DIGIVAULT_URL` is set.

The registry is a module-level dict (`_tools`, `_skills` in `registry.py`). It is global to the process — all requests share the same registry. `register_tool` raises `ValueError` on duplicate names, so plugins loaded via `load_entrypoint_tools()` must use unique names.

### 5.4 Vertical Connector Pattern

digisearch, digiquant, and digivault each own their tool schemas via `POST /v1/orchestrator_tools`. digigraph:

1. Calls `fetch_digisearch_tool_dicts(base_url, index_config, bearer, request_id)` at schema resolution time. Results are cached in a module-level dict (`_MANIFEST_CACHE`) keyed on `(base_url, index_config)` — this cache is **never invalidated** for the lifetime of the process.
2. Invokes tools via `invoke_digisearch_tool(base_url, tool, args, ...)` → `POST /v1/orchestrator_invoke`.
3. The digiquant connector follows the same pattern via `digiquant_hub.py`.
4. The digivault connector (`digivault_hub.py`) follows the same pattern for one tool, `digivault_search_notes` — full-text search over the digithings architecture vault (Supabase-backed, `SupabaseStore.search`). It has no `index_config` (vault search is not index-scoped), so its manifest cache key is the base URL alone.

The manifest cache uses synchronous `httpx.Client` (blocking calls inside async FastAPI). This can block the event loop thread during tool schema resolution. The current request handling is synchronous (FastAPI's thread pool), so this is acceptable but limits throughput under high concurrency.

### 5.5 Checkpointing

Process-wide singleton via `get_checkpointer()` in `graph/graph.py:29`:

| `DIGI_CHECKPOINTER` value | Backend | Notes |
|--------------------------|---------|-------|
| unset + project active | `SqliteSaver` | **Default when `digiproject.yaml` is present** (SITAAS / project mode); survives restarts |
| unset + no project | `MemorySaver` (in-process dict) | Default standalone mode; lost on restart |
| `memory` | `MemorySaver` (in-process dict) | Explicit; lost on restart |
| `sqlite` | `SqliteSaver` | File path via `DIGI_CHECKPOINTER_SQLITE_URI` |
| `postgres` | `PostgresSaver` | Connection string via `DIGI_CHECKPOINTER_POSTGRES_URI` |
| `none` / `off` / `0` / `false` | None (no checkpointing) | Breaks multi-turn and thread APIs |

**Project-mode default (SITAAS):** When `get_checkpointer()` is called and `DIGI_CHECKPOINTER` is unset, the function probes for an active project config via `_resolve_config_path()`. If a `digiproject.yaml` is found, it defaults to `sqlite` so multi-turn conversation state persists across HTTP requests. The env var always takes precedence over this auto-detection.

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

Olympus is the load-bearing case: `hermes/chain.py:125` derives `thread_id` as `"<GITHUB_RUN_ID>::atlas"` / `"::hermes"`, which is never reused, so no row ever became collectable. By 2026-08-01 the four checkpointer tables held 952 MB of a 1263 MB database (75%) and were growing ~50-58 MB/day.

Retention is enforced **in the database, not in digigraph** — the pruner must not depend on a Python process being alive, and digigraph has no scheduler. `digiquant/supabase/migrations/061_checkpointer_retention.sql` installs `public.prune_langgraph_checkpoints(retain_days integer DEFAULT 14)` plus two daily pg_cron jobs (prune at 05:20 UTC, plain `VACUUM (ANALYZE)` at 05:50 UTC). See [`digiquant/supabase/SCHEMA.md`](../digiquant/supabase/SCHEMA.md) for the operator view (pause, verify, ownership requirement).

Three properties that any other Postgres-checkpointer deployment should copy:

- **Prune by `thread_id`, not by checkpoint.** `checkpoint_blobs` is keyed `(thread_id, checkpoint_ns, channel, version)` with **no `checkpoint_id`** column, so a per-checkpoint delete leaves unreachable blobs behind — and blobs are where the bytes are.
- **Key staleness on `max((checkpoint->>'ts')::timestamptz)` per thread.** Per-row it is a reliable ISO 8601 timestamp; taking the max means an in-flight or freshly-resumed thread can never be eligible, and an unparsable/absent `ts` yields `NULL`, fails the comparison, and is retained.
- **Retention is a resume ceiling.** Any resume-from-checkpoint feature (here, `pipeline-olympus.yml`'s `resume_run_id`) can only reach back as far as the retention window, so the window can never be zero.

**The real cost driver is upstream of retention.** 94% of the bytes sit on the `__pregel_tasks` channel: `FanOutPhase` dispatches one `Send` per item and `pipeline_builder.py:57-58` hands each worker a **full copy of the live state**, so one H6 superstep persisted 52 complete `AtlasResearchState` copies (a single 48 MB row was measured). That is `O(fan-out width x state size)` per superstep and it contradicts `AGENTS.md`'s "State stays lean … no large DataFrames in state or LangGraph checkpoints" as well as [`docs/LANGGRAPH_REVIEW.md`](docs/LANGGRAPH_REVIEW.md). Shrinking the `Send` payload to a cursor is a ~20x lever; it changes `FanOutPhase`'s state-copy contract in this shared library and is therefore deferred as a human-gated architecture change (follow-up to #1758). Retention caps the footprint; it does not reduce the write volume.
#### 5.5.3 Postgres connection bounds — #1734

`PostgresSaver.from_conn_string` forwards its argument straight to `psycopg.Connection.connect`, which applies **no** connect timeout and **no** TCP keepalives, and exposes no kwarg for either. An established connection to a peer that disappears without sending an RST therefore stays in `ESTABLISHED` indefinitely, and a checkpoint read/write blocks with nothing but the caller's own job timeout as a backstop — the shape of the 2026-07-30 Olympus stall (210 minutes of silence inside a 240-minute job, beginning at a checkpoint-write boundary).

`_bounded_conn_string()` closes that by merging the bounds into the conninfo itself, which libpq accepts as ordinary connection parameters:

| Parameter | Value | Bounds |
|---|---|---|
| `connect_timeout` | `10` | establishing a connection |
| `keepalives` / `keepalives_idle` / `keepalives_interval` / `keepalives_count` | `1` / `30` / `10` / `5` | an established-but-dead connection (~80s to detect) |

It accepts either libpq spelling (`postgresql://` URI or `host=… dbname=…` keyword/value) via `psycopg.conninfo.make_conninfo`, and **any parameter already present in `DIGI_CHECKPOINTER_POSTGRES_URI` wins** — that env var is the override path. Missing psycopg or an unparseable conninfo returns the string unchanged with a warning: bounding a connection must never itself be why a process fails to start.

`statement_timeout` is deliberately **not** set. It is enforced server-side, so it cannot help when the network path is gone, and it risks aborting a legitimately slow write against a checkpoint table already at ~950 MB in production (#1758).

Timing is the only thing that changes: an unreachable Postgres already raised `psycopg.OperationalError` out of `get_checkpointer()` (via `cm.__enter__()`), so no new failure *mode* is introduced — it now surfaces in ~10s instead of hanging on the OS TCP timeout. On the Olympus path `hermes/chain.py::_acquire_checkpointer` catches `Exception` and degrades to an uncheckpointed run.

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
        │                           │     └── research_node → run_tools
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

### 6.3 Code Execution Gate

`policy.code_execution_allowed()` gates **execution**, not tool registration. `data_engineer_agent` is always registered in `orchestration/builtin.py` but `execute_python_on_datasets()` in `tools/analytics/execute_python.py` returns an error when `DIGI_ALLOW_CODE_EXEC` is unset. The `sitaas_rag` skill only exposes the tool when `run_data_dir` is set; callers still need `DIGI_ALLOW_CODE_EXEC=1` for code to run.

### 6.4 Thread State Access

`GET /threads/{thread_id}/state` requires `DIGI_ENABLE_THREAD_API=1` but performs no subject-binding check. Any request with a valid JWT (or no JWT in passthrough mode) can read any thread's state. The `_THREAD_STATE_KEYS` allowlist (`server.py:249`) limits which state keys are returned, but `stored_datasets`, `research_response`, `research_note`, `error`, `backtest_result`, `strategy_name`, and `symbols` are all exposed.

**Risk:** In a multi-tenant deployment, tenant A can read tenant B's research output and dataset refs if they know or guess the `thread_id`. Since `thread_id` defaults to `session_id` (which defaults to `"default"`), all sessions without an explicit `session_id` share a single checkpoint namespace.

### 6.5 Debug Endpoint Risks

`GET /v1/debug/input_messages` returns the last 5 chat completion request summaries, including the first 400 characters of the prompt. This is stored in a module-level global (`_DEBUG_REQUEST_LOG` in `server.py:16`) shared across all requests. In a multi-tenant deployment with the debug endpoint enabled, a second tenant can read another tenant's prompt preview. The endpoint should be disabled in production (`DIGI_ENABLE_DEBUG_ENDPOINTS` defaults to `0` in Compose).

### 6.6 Streaming Cancellation Gap

When a client disconnects from an SSE stream, the background thread (`run_digigraph_workflow_streaming`) continues executing until it completes or errors. There is no cancellation mechanism — no `threading.Event`, no exception injection into the thread. Under high load, many orphaned workflow threads can accumulate, each holding LLM connections and potentially making outbound HTTP calls to digisearch and digiquant. The `Queue.get()` in `_stream_completions_progressive` will eventually raise a `GeneratorExit` exception (when the generator is garbage-collected), which surfaces as a logged exception in the generator but does not stop the background thread.

### 6.7 Rate Limiter Trust Boundary

The `RateLimiter._get_ip()` method trusts `X-Forwarded-For` without validation. A client can set `X-Forwarded-For: 1.2.3.4` to impersonate any IP and bypass per-IP rate limits. In a Docker Compose deployment behind a reverse proxy, this is acceptable only if the proxy strips or overrides the header before it reaches digigraph. Currently there is no proxy in the default Compose stack — digigraph is directly exposed on `127.0.0.1:8000`.

### 6.8 MCP Server Auth Gap

The MCP server (`mcp_server.py`) has no built-in authentication layer. The `streamable-http` transport binds to `0.0.0.0:8766` by default, making it network-accessible. The `workflow` and `chat` MCP tools invoke the workflow directly (bypassing HTTP middleware including `DigiAuthMiddleware`). Operators must use network policy or a gateway in front of the MCP server.

### 6.9 Manifest Cache Never Invalidates

The vertical manifest caches in `digisearch_hub.py`, `digiquant_hub.py`, and `digivault_hub.py` are module-level dicts with no TTL or invalidation. If digisearch, digiquant, or digivault adds, removes, or changes a tool definition, the cached schema is stale until the digigraph process restarts. This affects tool schema accuracy in long-running deployments.

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

Four modes — **`llm_mode` is access/cost policy, not a product catalog**: `free` (resolved model must be free-tier: OpenRouter `:free` or local Ollama), `test` (minimal), `medium` (balanced), `best` (largest). The project config YAML `agents.llm_mode` overrides `DIGI_LLM_MODE`. **Actual model id** comes from (in order) `agents.llm` → `DIGI_LLM_PROVIDER`/`DIGI_LLM_MODEL` → LiteLLM alias / deploy config — **not** a shared `model_modes.yaml` `free:` pin (OpenRouter free roster rotates). `llm_mode: free` without an explicit pin raises a clear error (`set agents.llm or DIGI_LLM_MODEL`); non-`:free` (non-Ollama) pins are refused. Having `OPENROUTER_API_KEY` set alone does **not** auto-swap digigraph chat onto paid Olympus models — Olympus/Atlas use `get_model_for_phase()`.

**BYOK spend path** (`llm_auth.py`): user keys via `X-BYOK-Key` / `X-BYOK-Provider` / `X-BYOK-Model` are spent only for routable providers — OpenAI, OpenRouter, Gemini, Anthropic. Anthropic uses Anthropic's OpenAI-compatible endpoint (`https://api.anthropic.com/v1/`) with the **user's** key (never operator fallthrough). Non-OpenAI BYOK requires `X-BYOK-Model`.

**Free-quota errors:** provider 429 / RPD under `llm_mode: free` maps to stable code `free_quota_exceeded` (HTTP 429 + SSE `delta.digigraph_error`) for digichat BYOK handoff. Generic rate limits outside free mode use `rate_limit`.

CLI: `digi llm-settings` / `python -m digigraph.cli llm-settings` prints effective provider/model/key-env present (never secrets).

### 8.3 digistore for LLM Context Reduction

Search results from digisearch are written to `{run_data_dir}/{session_id}/datasets/` as JSON files. Only a compact preview (5 rows × 300 chars) is injected into the LLM context (`_search_payload_for_llm` in `builtin.py:58`). The full dataset is referenced by `dataset_ref` and loaded on demand by agent runners. This implements the "≥70% token reduction vs naive prompts" target from the architecture principles.

### 8.4 Parallel Tool Execution

When the LLM returns multiple tool calls in one turn and all tools are tagged `parallel_safe` (currently: `visualization_agent`, `analysis_agent`, `data_prep_agent`, `data_manipulation_agent`, `data_engineer_agent`, delegate tools), they are dispatched in parallel via `ThreadPoolExecutor` inside `digillm.run_tools` (the `parallel_safe` set is computed from the registry in `llm_client.py` and passed through). Tool results are appended to the conversation in original order. This reduces multi-tool latency from O(n×tool_time) to O(max_tool_time).

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
- **Model routing:** callers must pass a concrete model string resolved via `config/model_modes.yaml`. The `digi/fast`, `digi/balanced`, `digi/best`, `digi/multimodal` named routes have been removed. Atlas/Hermes phases all use `openrouter/openrouter/auto` (OpenRouter Auto Router); set `OPENROUTER_API_KEY`. See `.env.example` and `config/model_modes.yaml`.
- Caching: LiteLLM supports Redis-backed semantic caching when `REDIS_URL` is set (Compose profile: `litellm-cache`).

### 9.7 digivault

**Protocol:** HTTP via `digivault_hub.py`

- **Manifest:** `POST /v1/orchestrator_tools` — returns the OpenAI tool dict for `digivault_search_notes`. Cached per `base_url` (no `index_config` — vault search is not index-scoped).
- **Invoke:** `POST /v1/orchestrator_invoke` — dispatches to `SupabaseStore.search` (the `search_architecture_notes` RPC) on digivault's side. Accepts `{tool, arguments}`.
- **Auth:** Bearer token from `WorkflowState.digi_bearer` is forwarded via `Authorization: Bearer` header; `X-Request-ID` forwarded from `ToolContext.request_id`.
- **Env:** `DIGIVAULT_URL` (empty = the `digivault` skill is not registered for the request; other skills are unaffected). In Docker: `http://digivault:8004`.
- **Purpose:** reproduces the vault-grounded documentation search the digithings.ai chat widget calls directly today ([ADR-0018](../docs/adr/0018-digichat-path-routing.md), epic #1248) — the tool digichat's BFF needs once traffic moves off the bespoke widget onto digigraph.

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
| `DIGIVAULT_URL` | `http://digivault:8004` | digivault HTTP base URL; empty = `digivault_search_notes` disabled |
| `DIGISMITH_URL` | `http://digismith:8003` | digismith status URL (unused by digigraph HTTP) |
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
| `DIGI_CHECKPOINTER` | `sqlite` when project active, else `memory` | Checkpointer backend: `memory` / `sqlite` / `postgres` / `none` |
| `DIGI_CHECKPOINTER_SQLITE_URI` | `~/.digigraph/checkpoints.sqlite` | SQLite file path |
| `DIGI_CHECKPOINTER_POSTGRES_URI` | (empty) | Postgres connection string |
| `DIGIQUANT_URL` | `http://127.0.0.1:8001` when unset | digiquant base URL. Explicit empty string disables backtest routing (Profile A). |
| `DIGIQUANT_DATA_DIR` | `/app/data` | Path to CSV files for backtests (required only when digiquant is enabled) |
| `DIGISEARCH_INDEX` | `default` | Default vector index name |
| `DIGI_TENANT_CORPUS_MAP` | (empty) | Optional JSON map of tenant slug → `{digisearchIndex, vaultPathPrefix, researchSystemPrompt}` for multi-tenant corpus isolation (OCC). Headers `X-Digi-Corpus-Index` / `X-Digi-Vault-Prefix` win when set. |
| `DIGI_ENABLE_DEBUG_ENDPOINTS` | `0` | Enable `/test_llm` and `/v1/debug/*` |
| `DIGI_ENABLE_THREAD_API` | `0` | Enable `/threads/*` and `/files/*` |
| `DIGI_SUPERVISOR` | (empty) | Enable supervisor node: `1` / `true` |
| `DIGI_HUB_MODE` | `legacy` | Hub mode: `legacy` (default) or `federated` |
| `DIGI_WORKFLOW_PROFILE` | `full_stack` | Workflow profile when not set in project config |
| `DIGI_RESEARCH_BRIEF` | (unset → YAML / default on) | Override `agents.research_brief`: `0`/`false` skips ResearchBrief post-pass |
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

**Implemented (REM-027):** `rate_limit.py` reads `DIGI_TRUSTED_PROXIES` (comma-separated hosts/CIDRs). `X-Forwarded-For` is honored only when the direct client is in that set; otherwise the limiter uses `request.client.host`.

## Observability

This service exposes a Prometheus `/metrics` endpoint (counter, histogram, in-flight gauge for every HTTP route) via `digibase.metrics.install_metrics`; scraped by the `observability` compose profile per [ADR-0003](../docs/adr/0003-observability-baseline.md).

## Input Validation Posture

All HTTP request bodies are typed with Pydantic v2 models using `ConfigDict(extra="forbid")`, which rejects unknown fields with HTTP 422 at the framework boundary. Shared validation-error shape lives in `digibase.errors`.

## Generic Research Agent + Pipeline Builder (Phase Sub-graphs)

`digigraph/src/digigraph/graph/research_agent.py` and
`digigraph/src/digigraph/graph/pipeline_builder.py` provide reusable
primitives for composing phase-structured research sub-graphs. The digiquant
Atlas migration (issue #176, ADR-0009) is the first consumer.

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

These primitives stay Atlas-agnostic on purpose. Any sub-graph that wants
phase-structured parallel research can reuse them by declaring its own
phase list.
