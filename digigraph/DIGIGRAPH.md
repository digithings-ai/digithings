# DigiGraph – Orchestration Brain

**Part of [DigiThings](https://github.com/digithings-ai/digithings) (digithings.ai).**  
**Purpose** (from root `DIGI.md`): Stateful LangGraph core that defines layered agent families, routing, persistent memory, and controlled autonomy.

**Key Patterns (2026 standard)**
- Supervisor + sub-graph architecture
- Layered families (Research Supervisor → Data Science Family → Strategy Generator → Execution Monitor)
- GraphRAG with Graphiti (temporal bi-model memory)
- LiteLLM router (100+ providers, full feature passthrough)
- All outputs Pydantic-structured

**MCP-First Principle**  
Every tool and every agent family has an MCP entrypoint. Orchestration discovers tools at runtime from DigiQuant and other MCP servers; dual interface (HTTP for deployment, stdio for local) where useful. Tool schemas are machine-readable so the supervisor can route and validate without ad-hoc wiring.

**State and Checkpointing**  
Shared agent state carries conversation messages, session/conversation identity, current agent and handoff history, pending and completed tool calls, and security context (e.g. allowed tools and agents per key). LangGraph checkpoints persist this state; checkpointer is configurable (memory, SQLite, or PostgreSQL for production). Where required, persistence is auth-aware so sessions are bound to the calling identity.

**Tool Adapter Pattern**  
MCP tools from DigiQuant and other servers are wrapped for LangGraph execution. A central registry provides namespacing and discovery; tool execution is security-wrapped so only permitted tools run for a given session. This keeps the graph declarative while preserving MCP as the single contract for external capabilities.

**Handoff and Multi-Agent Coordination**  
Specialist subgraphs (e.g. Data Science Family, Strategy Generator) are invoked by the supervisor via a clear handoff protocol: the supervisor chooses the next agent, updates state (current agent, history), and passes control. Specialists return to the supervisor for routing to tools or the next agent, keeping failures and complexity isolated within subgraphs.

**Agent Activation and Observability**  
Which agent families are active is config-driven (e.g. enabled families and agents). Feature flags and gradual rollout support safe migration of graph or node changes. Observability follows 2026 norms: tracing (e.g. LangSmith-compatible), performance utilities (caching, batching, rate limiting), and cost-per-run visibility for FinOps.

**Agent Family Template** (copy for new families)
```python
# digigraph/agents/<family>/supervisor.py
from langgraph.graph import StateGraph
# ... specialists + supervisor node
```

**Persistent Memory**  
LangGraph checkpoints + Neo4j + Graphiti. Every strategy, backtest, and macro event is stored with temporal validity. Short-term scratchpad state lives in the graph; long-term, strategy-relevant decisions and results are written to the shared strategy memory graph so future runs stay coherent.

**MCP Exposure**  
Every major node (research, backtest, optimize) is exposed as a discoverable MCP tool for DigiClaw. DigiClaw invokes workflows via a single custom skill; DigiGraph resolves the request to the appropriate subgraph and tools.

**Integration Points**  
- Receives calls from digiclaw/  
- Delegates heavy compute to digiquant/  
- Writes to shared strategy memory graph

---

## Phase 1 implementation (current)

- **Graph:** `digigraph/graph/` — `StateGraph(WorkflowState)` with linear flow: **START → research → backtest → END**. Supervisor is implicit (single path); conditional routing in later Phase 1.
- **Nodes:**  
  - **research** (Data Science Family): calls LLM (OpenAI-compatible: Ollama, LiteLLM, OpenAI) to extract `strategy_name` and `symbols` from the user prompt; falls back to heuristics if LLM is unavailable or returns invalid JSON. In **document mode** (project config `research_system_prompt` set) with DigiSearch available: RAG-style flow—LLM receives the user query, calls `digisearch` tool with a query it generates, receives results, then summarizes for the user. The `digisearch` tool supports optional `filter` / `filters` (OData or structured), `columns`, `top_k`, `response_mode` (`full` | `summary`), and `summarize_if_over`; the model can explore with filters and summary first, then do a second call with tighter filter and `response_mode=full` for precise extraction.  
  - **backtest**: HTTP POST to DigiQuant `run_backtest`; writes result or error into state.
- **LLM:** `digigraph/llm.py` — `get_client()` and `chat_completion()` using `OPENAI_API_BASE` and `OPENAI_API_KEY`. `get_model_for_mode()` reads `config/model_modes.yaml` and `DIGI_LLM_MODE` (test|medium|best). When `DIGI_PROJECT_CONFIG` is set, `agents.llm_mode` in the project YAML overrides `DIGI_LLM_MODE`. In Docker, DigiGraph uses LiteLLM at `http://litellm:4000/v1`; LiteLLM routes to Ollama Cloud, local Ollama, or OpenAI per config.
- **Project config:** Optional per-project config is loaded via `DIGI_PROJECT_CONFIG` (path to a YAML file; local-only, not in repo). When set, it can specify index config, skills, and `run_data_dir`. Optional `run_data_dir` (or env `DIGI_RUN_DATA_DIR`) enables run storage and delegate tools (visualization_agent, analysis_agent, data_prep_agent).
- **Entrypoint:** `POST /workflow` invokes `run_digigraph_workflow(req)`; workflow builds the graph, invokes it with `{ "prompt", "session_id" }`, and maps final state to `WorkflowResult`. `GET /test_llm` exercises the same LLM path (no workflow) for quick sanity checks. **Thread state:** When a checkpointer is enabled, `GET /threads/{thread_id}/state` returns the latest checkpoint state (stored_datasets, research_response, error, etc.); optional `?checkpoint_id=` returns that checkpoint. `GET /threads/{thread_id}/history` returns the list of checkpoints for the thread (debug). **Human-in-the-loop:** Set `DIGI_INTERRUPT_AFTER_RESEARCH=1` to pause after the research node; then `POST /threads/{thread_id}/resume` (optional body `{"resume": <value>}`) continues the graph. Requires a checkpointer.
- **OpenAI-compatible API (Open WebUI):** `GET /v1/models`, `POST /v1/chat/completions` expose DigiGraph as a chat model. When `stream: true`, the stream includes tool-call and tool-result blocks. Optional **Open WebUI format** (`openwebui_format: true`, or model `sitaas-rag`, or header `X-Response-Format: openwebui`) renders those blocks with `<details type="tool_calls">` (summary “Searching {index}…”, Input/Output) so Open WebUI shows them as tool-call UI. See **digigraph/docs/OPENWEBUI.md** for usage.
- **LiteLLM:** Wired in default stack. DigiGraph depends on LiteLLM; model list in `config/litellm.yaml`, mode defaults in `config/model_modes.yaml`. See **config/MODELS.md** for adding/updating models.
- **Run storage & Digistore:** When `run_data_dir` is set, search results are written to session-scoped storage. **Digistore** (`digigraph/digistore.py`) provides named datasets under `{run_data_dir}/{session_id}/datasets/` with `digistore_put`, `digistore_get`, `digistore_list`, `digistore_profile`. The `digisearch` and `digisearch_fetch_all` tools write results into Digistore (e.g. `search_1`, `search_2`). Use `resolve_dataset_ref(session_id, dataset_ref)` to resolve paths or logical names. **LangGraph persistence:** Optional `stored_datasets` in `WorkflowState` holds refs and short profiles (row_count, columns) so dataset lists survive across turns when the graph is compiled with a checkpointer. Set `DIGI_CHECKPOINTER=memory` (default in-process), `sqlite` (file: `DIGI_CHECKPOINTER_SQLITE_URI`, default `~/.digigraph/checkpoints.sqlite`; optional dep `langgraph-checkpoint-sqlite`), or `postgres` (require `DIGI_CHECKPOINTER_POSTGRES_URI`; optional dep `langgraph-checkpoint-postgres`). A shared checkpointer is used so `thread_id` persists across HTTP requests; invoke with `config={"configurable": {"thread_id": session_id}}`. The `stream_callback` in state is not serialized—streaming is request-scoped only. See **digigraph/docs/LANGGRAPH_REVIEW.md**.
- **Iterative search:** For "all" result sets (e.g. all emails from user X), use **digisearch_fetch_all**: it paginates automatically and returns a single combined `dataset_ref`. The research prompt and tool descriptions guide the model to use filters (fromAddress, etc.) and fetch_all when appropriate.
- **Sub-agents:** When run storage is enabled, the research node exposes `visualization_agent`, `analysis_agent`, `data_prep_agent`, **data_manipulation_agent**, and **data_engineer_agent**. **Data manipulation** does column math, round, transform, group/aggregate, merge/join, and append via Polars; outputs are written to Digistore. **Data engineer** runs sandboxed Python (Polars only) on one or more datasets; code receives `df_0`, `df_1`, ... and must set `result` to a DataFrame. **Visualization** includes ECharts tools (echarts_line, echarts_bar, echarts_scatter, echarts_pie, echarts_from_code) that return `echarts_option` JSON for frontend rendering with `echarts.init().setOption()`. If Node.js and `echarts` are installed in `digigraph/.../echarts/` (`npm install` there), ECharts results are also converted to SVG and returned as `image_path` so Open WebUI shows the chart inline. Full tool list: **digigraph/docs/OPENWEBUI.md**.
- **MCP / Graphiti:** Not yet implemented. Next (Phase 2): expose research/backtest as MCP tools; DigiClaw skill integration; Graphiti/GraphRAG stub.

### Orchestration: tools, agents, skills

Tools and agents are organized in three layers so the research node stays decoupled and extensible.

1. **Primitives** — Stateless callables under `digigraph/tools/` (e.g. `tools/digisearch.py`, `tools/analytics/`). Used by sub-agents or by orchestrator tool handlers. No orchestrator schema lives here.
2. **Orchestrator tools** — The surface the research node sees: **name**, OpenAI **schema**, **handler** `(args, context) -> result`, and optional **tags** (e.g. `delegate`, `parallel_safe`). Each is registered in the orchestration registry. Handlers receive a `ToolContext` (session_id, run_data_dir, index_name, index_config, state).
3. **Skills** — Named bundles of orchestrator tool names with an optional **when** predicate. The registry resolves `get_tools(skill_ids, context)` to the list of tool dicts for the LLM; only tools from skills whose `when(context)` is true are included.

**Registry and built-ins:** `digigraph/orchestration/registry.py` defines `ToolContext`, `register_tool`, `register_skill`, `get_tools`, `execute`, and `list_tool_names`. `digigraph/orchestration/builtin.py` registers all built-in tools (digisearch, digisearch_fetch_all, visualization_agent, analysis_agent, data_prep_agent, data_manipulation_agent, data_engineer_agent) and two skills: **search** (digisearch + digisearch_fetch_all, when DigiSearch URL is set) and **sitaas_rag** (search tools + all delegate agents, when `run_data_dir` is set). The research node builds `ToolContext`, calls `get_tools(cfg.get_enabled_skills(), context)` for the tool list, and uses `execute(name, args, context)` for dispatch. Formatters use `list_tool_names(tag="delegate")` so new delegate agents get correct formatting without code changes.

**Project config:** Optional `skills.enabled` in project YAML can override the default skill list (default is `["search", "sitaas_rag"]`). See `DigiProjectConfig.get_enabled_skills()`.

**Adding a new orchestrator tool (e.g. a new agent):**
1. Add the agent under `digigraph/agents/<name>/`: `schema.py` (OpenAI function tool dict) and `runner.py` (e.g. `run_<name>_agent(...)`).
2. In `digigraph/orchestration/builtin.py`, register the tool: `register_tool("my_agent", MY_AGENT_TOOL, _handle_my_agent, tags={"delegate", "parallel_safe"})` and add a handler that calls your runner with args and `context.session_id` (and other context fields as needed).
3. Add the tool name to the **sitaas_rag** skill in `builtin.py` so it is included when `run_data_dir` is set.
4. No changes needed in `graph/nodes.py` or formatters; the registry and `list_tool_names(tag="delegate")` cover discovery and formatting.

**Adding a new primitive:** Implement the function under `tools/` (e.g. `tools/analytics/`). If it is only used by an existing sub-agent, wire it in that agent’s runner. If it should be callable by the orchestrator as a direct tool, register it in `builtin.py` with a schema and handler, and add it to the appropriate skill.