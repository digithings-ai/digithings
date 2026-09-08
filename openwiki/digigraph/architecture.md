---
type: service-architecture
title: digigraph Architecture
description: Hub design of digigraph — LangGraph state machine, orchestrator tool registry, HTTP-only vertical boundary, and module map.
tags: [digigraph, orchestration, langgraph, architecture]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-deb1497ccdcada935084b098
    resource: repo://digigraph/AGENTS.md
  - id: openwiki-source-de1de5b360063f1d3f60c784
    resource: repo://digigraph/ARCHITECTURE.md
  - id: openwiki-source-c371fe6b6859586069a9e24e
    resource: repo://digigraph/src/digigraph/graph/graph.py
  - id: openwiki-source-90658d6266af009ade56ec79
    resource: repo://digigraph/src/digigraph/orchestration/registry.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digigraph Architecture

digigraph (port 8000) is the central orchestration hub: every user request
flows through it from digiclaw, digichat, Open WebUI, or MCP clients, and
it coordinates the verticals without owning their domain logic. Three
roles, one rule: **coordinate, don't implement** — no quant pipeline
ordering (digiquant's), no tiered RAG (digisearch's), no Python imports of
vertical packages (HTTP only).

## Role 1 — LangGraph state machine

A compiled `StateGraph[WorkflowState]` routes
`research → validate_strategy → backtest → optimize → END` through
profile-driven conditional edges, with an opt-in `supervisor` node
(`DIGI_SUPERVISOR=1`) ahead of research. The research node is itself a
subgraph (LLM + tool loop with two-tier context compaction); backtest and
optimize nodes delegate to digiquant jobs with local fallback. State stays
lean — refs and summaries only, large datasets in digistore, never
checkpoints full of document bodies or DataFrames.

## Role 2 — Tool registry and dispatcher

`orchestration/registry.py` owns named tools and skills
(`register_tool`, `register_skill`, `register_mcp_server`) plus the
`ToolContext.allowed_tool_names` allowlist enforced at dispatch — every
new capability registers here (MCP-first), never inline in a node.
Verticals publish their own OpenAI tool schemas via
`POST /v1/orchestrator_tools`; digigraph fetches schemas lazily and
invokes them via `POST /v1/orchestrator_invoke`. Hub clients
(`vertical_orchestrator/digisearch_hub.py`, `digiquant_hub.py`,
`digivault_hub.py`) wrap the HTTP boundary.

## Role 3 — HTTP + MCP surface

Covered in [API and Operations](/openwiki/digigraph/api-and-operations.md):
`POST /workflow`, OpenAI-compatible chat with SSE, opt-in thread APIs,
and the FastMCP server (8766 / stdio).

## Module map (selected)

| Area | Role |
|------|------|
| `graph/` | StateGraph, state, nodes, research subgraph, brief builder |
| `orchestration/` | Registry, built-in tools, hub clients |
| `vertical_orchestrator/` | digisearch/digiquant/digivault HTTP clients |
| `planning/` | Topo-sorted parallel plan executor |
| `tools/` | Tool implementations behind registry names |
| `llm_client.py` + `digillm` | All LLM traffic (no direct SDK calls) |
| `digistore.py`, `run_storage.py` | Session-scoped named datasets |
| `compaction.py` | Two-tier transcript compaction |
| `rate_limit.py`, `policy.py` | Sliding-window limiter, feature flags |

## Non-negotiable boundaries

Never import digisearch/digiquant packages; route all LLM calls through
`llm_client`; resolve models via `get_model_for_mode()`; extend
`digigraph_path_scopes` for new routes; default checkpointer is memory
(`DIGI_CHECKPOINTER=postgres` for production).
