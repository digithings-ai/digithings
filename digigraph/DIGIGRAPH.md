# DigiGraph – Orchestration Brain

**Purpose** (from `DIGI.md`): Stateful LangGraph core that defines layered agent families, routing, persistent memory, and controlled autonomy.

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
  - **research** (Data Science Family): calls LLM (OpenAI-compatible: Ollama, LiteLLM, OpenAI) to extract `strategy_name` and `symbols` from the user prompt; falls back to heuristics if LLM is unavailable or returns invalid JSON.  
  - **backtest**: HTTP POST to DigiQuant `run_backtest`; writes result or error into state.
- **LLM:** `digigraph/llm.py` — `get_client()` and `chat_completion()` using `OPENAI_API_BASE` and `OPENAI_API_KEY`. `get_model_for_mode()` reads `config/model_modes.yaml` and `DIGI_LLM_MODE` (test|medium|best). In Docker, DigiGraph uses LiteLLM at `http://litellm:4000/v1`; LiteLLM routes to Ollama Cloud, local Ollama, or OpenAI per config.
- **Entrypoint:** `POST /workflow` invokes `run_digigraph_workflow(req)`; workflow builds the graph, invokes it with `{ "prompt", "session_id" }`, and maps final state to `WorkflowResult`. `GET /test_llm` exercises the same LLM path (no workflow) for quick sanity checks.
- **LiteLLM:** Wired in default stack. DigiGraph depends on LiteLLM; model list in `config/litellm.yaml`, mode defaults in `config/model_modes.yaml`. See **config/MODELS.md** for adding/updating models.
- **MCP / Graphiti:** Not yet implemented. Next (Phase 2): expose research/backtest as MCP tools; DigiClaw skill integration; Graphiti/GraphRAG stub.