# DigiFlow – Prototyping & Demos (Langflow)

**Part of [DigiThings](https://github.com/digithings-ai/digithings) (digithings.ai).**  
**Purpose:** Langflow-based visual flows for quick prototyping and demos that attach to other DigiThings components. DigiFlow is **not** the orchestration brain—DigiGraph (LangGraph) remains the single source of truth for production workflows.

**Use cases**
- Rapid prototyping of research prompts, sub-flows, or demo agents before implementing in DigiGraph.
- Standalone demos (e.g. “flow as MCP tool”) that call or are called by DigiQuant, DigiClaw, or external MCP servers.
- Internal or one-off flows (reporting, non-quant agents) that don’t need to live in the supervisor + sub-graph core.

**Boundaries**
- Production orchestration, state, and strategy memory stay in **DigiGraph** (see `digigraph/DIGIGRAPH.md`).
- DigiFlow flows can consume DigiQuant/DigiGraph via HTTP or MCP when useful; canonical MCP exposure for the ecosystem remains DigiGraph and DigiClaw.

**DigiSearch integration**
- DigiSearch exposes HTTP API (`POST /query`, `POST /ingest`) and MCP server (`digisearch_query` tool).
- Point Langflow at DigiSearch: HTTP `http://digisearch:8002` or MCP `http://digisearch-mcp:8765/mcp` (when `--profile digisearch-mcp`).
- Add DigiSearch as a Langflow component: connect to DigiSearch MCP server for document search in flows.

**Future implementation**
- Add Langflow to Docker Compose (optional service) when needed for prototyping or demos.
- Document how to point Langflow at DigiQuant/DigiGraph endpoints or MCP servers.
- Optionally version exported flows (JSON) under `digiflow/flows/` for reference or re-import.
- Keep AGENTS.md and ARCHITECTURE.md updated if DigiFlow becomes a standard optional component.

**Reference**
- [Langflow](https://github.com/langflow-ai/langflow) — visual builder; deploy as API or MCP server.
- Run locally: `uv pip install langflow -U` then `uv run langflow run` (default <http://127.0.0.1:7860>).
- Docker: `docker run -p 7860:7860 langflowai/langflow:latest`.

This file is the single reference for DigiFlow. Update as implementation progresses.
