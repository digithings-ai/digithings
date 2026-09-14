---
type: api-operations-guide
title: digisearch Query and Operations
description: digisearch query behavior and operations — retrieval, filters, rerank, orchestrator tools, scopes, and container.
tags: [digisearch, query, retrieval, operations]
sources:
  - id: openwiki-source-d16d9586117b95e03b7f1549
    resource: repo://digisearch/AGENTS.md
  - id: openwiki-source-d8c103ce2f8d842e27878849
    resource: repo://digisearch/src/digisearch/search/hybrid.py
  - id: openwiki-source-8b875aebc71266c49b090ec7
    resource: repo://digisearch/src/digisearch/search/reranker.py
  - id: openwiki-source-8639f2733ed2c02f7d26be5f
    resource: repo://digisearch/src/digisearch/server.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# digisearch Query and Operations

Queries flow through the backend router into normalized hits, with
optional hybrid fusion and reranking before the response. The same
retrieval backs REST, the orchestrator manifest, and MCP.

## Endpoints

- `GET /health` / `GET /healthz` — legacy and preferred liveness.
- `GET /azure_status` — backend config/reachability probe (stays behind
  `digisearch:query` scope, never public).
- `POST /query` → `QueryResponse` — the retrieval entry point.
- `POST /ingest`, `GET /indexes`, `GET /indexes/{name}`,
  `DELETE /indexes/{name}/documents/{doc_id}` — writes and index admin.
- `POST /v1/orchestrator_tools` / `POST /v1/orchestrator_invoke` —
  digigraph's federated entry points; schemas and dispatch owned here.
- `POST /v1/research_turn` — research-pipeline turn.

## Retrieval behavior

`query_index()` routes to the configured backend; hits normalize via
`normalize_query_hit()` to the standard JSON shape with evidence
metadata. `HybridSearcher` fuses keyword + vector rankings with RRF
(k=60); `Reranker` (Cohere / BGE / CrossEncoder, top_n) reorders before
return. Callers pass structured `filters: list[dict]`; raw OData strings
require the `allow_raw_filter` flag for trusted internal callers only.

## Scopes and operations

New endpoints carry `digisearch:query` or `digisearch:ingest` via
`DigiAuthMiddleware`. The Compose service binds `127.0.0.1:8002` with a
`/healthz` healthcheck; the MCP profile serves `:8765/mcp`. Key env:
`DIGISEARCH_CHUNKER`, `DIGISEARCH_INDEX`, `CHROMA_PATH`,
`AZURE_SEARCH_*`, embedding provider keys. Standard digibase middleware
(metrics, CORS, request-ID, error envelopes, optional OTel) applies.
