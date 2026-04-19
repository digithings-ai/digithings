# DigiGraph
> The orchestration hub — every agent workflow, tool call, and sub-graph in the DigiThings ecosystem flows through here.

## What it is

DigiGraph is the central orchestration brain of the DigiThings stack. It maintains a LangGraph StateGraph (a directed graph of stateful processing nodes) that routes user requests through research, analysis, retrieval, and execution nodes depending on what the request requires. It exposes an OpenAI-compatible API so any client that speaks the standard OpenAI protocol — including third-party tools and existing integrations — can use it without modification.

The dynamic tool registry is DigiGraph's core architectural feature: vertical services like DigiQuant and DigiSearch register their capabilities at runtime via `POST /v1/orchestrator_tools`. DigiGraph discovers and calls them without hardcoded configuration. Adding a new capability to the ecosystem means registering it; DigiGraph routes to it automatically.

## The problem it solves

Agent orchestration is consistently the hardest part of building AI systems in production. Every team rebuilds routing logic, tool management, session state, authentication, and streaming from scratch. The patterns are not obvious, the failure modes are subtle, and the work does not compound — each new project starts over.

DigiGraph provides this as a pre-built, extensible foundation. The plumbing is done. The work that remains is adding domain-specific nodes and sub-graphs, not rebuilding the infrastructure they run on.

## How it fits in the ecosystem

DigiGraph sits at the centre of the DigiThings stack. All inbound requests — from DigiChat, from MCP clients, from REST callers — enter through DigiGraph. It dispatches to DigiQuant for quantitative tasks, DigiSearch for retrieval, and DigiKey for auth decisions. DigiSmith records spans for every workflow.

### Sub-graph registry pattern

Sub-graphs are composable, independently deployable workflow units that register alongside tools in the same registry. A workflow can invoke one sub-graph or chain several; there is no forced coupling. Sub-graphs can be used in isolation or composed into larger pipelines. This pattern is how DigiThings separates infrastructure (open) from domain expertise (proprietary): the engine that runs sub-graphs is open; the sub-graphs that encode domain logic are the commercial product.

### Architecture decision guide — when to use what

Choosing the right abstraction level matters for maintainability and cost:

- **Skill or instruction file** — stateless, single-turn, no tool calls. Lightest option. Use for prompt templates, formatting rules, constrained generation.
- **Agent** — multi-turn reasoning, tool use, memory, or iteration required. Use when the output depends on intermediate results.
- **Sub-graph** — ordered pipeline with defined stages, branching, or parallel execution. Use when the *structure* of the work matters, not just the output. Atlas research cycles and Hermes portfolio deliberation are sub-graphs because their stage ordering and branching logic are as important as their outputs.

Start with the lightest abstraction that works. Promote up only when the task demands it.

## Capabilities — Current

Shipped and in production:

- LangGraph StateGraph with supervisor node, research node, backtest node, and optimisation node
- Dynamic tool registry — verticals register at runtime, no hardcoded routing
- OpenAI-compatible REST API (`/workflow`, `/v1/chat/completions`)
- Server-sent event (SSE) streaming for real-time response delivery
- JWT authentication via DigiKey
- Per-IP rate limiting
- Checkpoint persistence via `DIGI_CHECKPOINTER` (memory / SQLite / Postgres today; migrates to DigiStore once that module ships)
- LiteLLM routing — model selection, caching, cost controls
- DigiSmith tracing — every workflow tagged with `workflow_id`, `request_id`, `session_id`
- MCP server — DigiGraph capabilities available as MCP tools for Claude Desktop and similar clients
- Parallel tool execution
- Planning executor (multi-step plan before execution)
- Tool allowlist and policy flags

## Capabilities — 12-month roadmap

**Engine improvements:**
- Graphiti graph memory integration — persistent, structured knowledge that survives session boundaries
- Remote MCP enumeration — discover and call external MCP servers registered at runtime
- Auth-bound checkpoints — per-API-key RBAC on graph state, so different principals see different checkpoints
- OpenAI Responses API support (in addition to existing Chat Completions compatibility)

**Sub-graph migrations:**
- Atlas research cycles fully migrated from standalone scripts to DigiGraph sub-graphs — parallel batching, prompt caching, scheduled daily runs
- Hermes portfolio deliberation as a DigiGraph sub-graph with human approval gate before any allocation change

**Proprietary sub-graph library expansion:**
- Strategy development pipeline (Kairos) — chat-based, connected to DigiQuant
- Investor document builder — structured output from research inputs
- Scholarly article synthesis — multi-source ingestion into a persistent research library
- Exploration agent — cheap model, exhaustive index search, surfaces candidates for deeper analysis

## Open source vs. proprietary

**Open (MIT/Apache):**
- DigiGraph engine: StateGraph management, supervisor routing, streaming, checkpointing
- Tool registry: registration protocol, discovery, parallel dispatch
- LangGraph integration layer
- OpenAI-compatible API surface
- MCP server implementation
- DigiSmith integration and tracing decorators

**Proprietary (commercial):**
- Specific sub-graph implementations with domain logic: Atlas research cycles, Hermes portfolio deliberation, Kairos strategy execution
- Investor document builder, scholarly synthesis, and exploration agent sub-graphs
- The strategy library and research prompt templates that drive the proprietary sub-graphs

The engine is the open infrastructure. The sub-graphs that encode years of domain expertise in quantitative research and portfolio management are the commercial product.
