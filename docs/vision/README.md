# DigiThings — Ecosystem Overview
> A modular AI production platform that assembles the best open-source infrastructure into a pre-wired stack, with proprietary domain expertise layered on top.

## What it is

DigiThings is a modular AI production platform sitting at the intersection of AI engineering, quantitative finance, and developer infrastructure. It assembles best-of-breed open-source tools — LiteLLM, LangGraph, NautilusTrader, Supabase, OpenBB — into a pre-wired, production-ready stack, then layers proprietary domain expertise on top through a library of specialised agent sub-graphs (composable, independently deployable workflow units).

The core value proposition: a declarative project spec — config file plus index definitions plus API key — collapses weeks of engineering setup into hours. A consultant can deploy a client-facing intelligent application over their data without rebuilding auth, RAG (retrieval-augmented generation), orchestration, or LLM routing from scratch. The stack is pre-integrated; the configuration is the work.

**Three customer shapes:**

1. **Independent researcher or quant** — personal toolkit for strategy development, research synthesis, and portfolio management. Low barrier; deploy locally or via managed hosting.
2. **Consultancy client (SITAAS pattern)** — config plus index plus API key produces a deployed, client-facing product in hours. The first pilot is SITAAS, deployed with Microsoft SSO and domain-specific RAG over internal documents.
3. **Developer** — open-core modules to build and extend. Proprietary agents and skills available as paid add-ons.

## The problem it solves

Most AI deployments fall into one of two failure modes: thin wrappers that provide no domain expertise and break under real-world complexity, or fully bespoke builds where every engagement rebuilds auth, retrieval, routing, and streaming from scratch. Neither scales.

DigiThings is the composable middle ground. It provides the infrastructure layer pre-built and pre-integrated, so the work that remains is configuration and domain logic — not plumbing.

**Why not just use LiteLLM, LangChain, or existing SDKs?** LiteLLM routes models. LangChain provides primitives. DigiThings routes entire workflows — research, analysis, retrieval, execution, auth, audit — and the proprietary value is in domain-specific agent sub-graphs and the integration pattern. The difference between plumbing materials and a working kitchen. Using LiteLLM is a component choice within DigiThings, not an alternative to it.

## How it fits in the ecosystem

DigiThings occupies the layer between raw AI infrastructure (model providers, vector databases, execution engines) and client-facing applications. It does not compete with model providers or cloud platforms. It competes with the engineering time and cost of building production AI systems from scratch.

**No lock-in philosophy:** Use the entire DigiThings platform, or integrate individual modules into an existing stack. Every capability is exposed as a REST endpoint, MCP tool (for Claude Desktop, Cursor, and other AI apps), CLI command, and Docker container via DigiLink. Switching costs nothing because no module assumes you are using any other DigiThings module exclusively.

The platform integrates with and extends the open-source tools clients may already have in place — it is additive, not replacement.

## Capabilities — Current

Shipped and in active use:

### DigiGraph — agent orchestration hub
LangGraph-based workflow engine with a supervisor node, research and analysis sub-graphs, dynamic tool registry, OpenAI-compatible API, server-sent event (SSE) streaming, JWT auth, per-IP rate limiting, LiteLLM routing, DigiSmith tracing, and an MCP server. Parallel tool execution and tool allowlist/policy enforcement included.

### DigiQuant — quantitative finance platform
NautilusTrader-backed strategy engine with backtest and optimisation nodes wired into DigiGraph. Connects to OpenBB for market data. Atlas (research), Hermes (portfolio), and Kairos (strategy execution) are in active development as sub-graph modules.

### DigiSearch — RAG and retrieval pipeline
Document ingestion, chunking, embedding, and hybrid vector/keyword search. Pluggable backends. Powers the SITAAS internal document search deployment.

### DigiChat — chat interface and BFF
Next.js production chat UI deployed at chat.digithings.ai. BYOK (bring-your-own-key) flow, model selector, Auth.js authentication, Drizzle ORM, adaptive UI scoped by access level.

### DigiKey — auth control plane
JWT-based authentication with scoped API keys (RS256, JWKS endpoint), SSO federation groundwork, org and project membership model.

### DigiSmith — observability
LangSmith tracing, Prometheus metrics, correlation IDs (workflow, request, session). `/v1/status` public endpoint.

### DigiClaw — always-on agent orchestration
Scheduled and continuous agent execution via OpenClaw. Heartbeat and audit capabilities. MCP skill interface.

### DigiBase — shared library
HTTP utilities, error envelopes, immutable audit logging (JSONL with redaction). Shared across all service boundaries.

**Note — not yet shipped:** DigiStore (unified storage abstraction over Supabase, SQLite, S3/MinIO) and DigiLink (the protocol translation and connector layer) are designed and specced but not yet implemented as standalone modules. Their functions exist today within individual services.

## Capabilities — 12-month roadmap

- **Atlas** running daily research cycles autonomously — parallel, batched, prompt-cached, fully integrated as a DigiGraph sub-graph
- **Hermes** maintaining live portfolio allocations with deliberation sub-graph and human approval gate before any execution
- **Kairos** enabling chat-based strategy development through DigiChat — a quant researcher's interactive strategy workbench
- **SITAAS** fully deployed with Microsoft SSO, proper domain RAG, and a client-facing chat interface
- **DigiLink** formalised as a module — MCP adapter generation from OpenAPI specs, CLI wrapper auto-generation, desktop AI app connector library (Claude Desktop, Cursor, Windsurf)
- **DigiStore** shipping as a unified storage abstraction with Supabase, SQLite, and S3/MinIO backends behind a single interface
- **Graphiti graph memory** integrated into DigiGraph for persistent, structured knowledge across sessions
- **digithings.ai and digiquant.io** live with embedded chat demos
- **Expanded proprietary sub-graph library** — investor document builder, scholarly article synthesis, exploration agent, strategy development pipeline

## Open source vs. proprietary

**Open (MIT/Apache):**
- DigiGraph engine, tool registry, LangGraph integration, OpenAI-compatible API, MCP server
- DigiSearch ingestion and retrieval pipeline
- DigiKey auth primitives
- DigiSmith tracing helpers
- DigiClaw heartbeat and audit core
- DigiBase shared library
- DigiLink connector framework (when shipped)
- DigiStore storage abstraction (when shipped)

**Proprietary (commercial):**
- Domain-specific sub-graph implementations: Atlas research cycles, Hermes portfolio deliberation, Kairos strategy execution
- Strategy library and backtest configuration templates
- Investor document builder and scholarly synthesis sub-graphs
- Managed hosting and deployment
- Enterprise SSO federation and org management extensions

The open core is the infrastructure. The proprietary layer is the domain expertise that makes it immediately useful for finance, research, and consulting deployments.
