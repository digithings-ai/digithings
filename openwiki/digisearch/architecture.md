---
type: service-architecture
title: digisearch Architecture
description: RAG design of digisearch — ingest-to-query pipeline, pluggable index backends, vertical role under digigraph, and module map.
tags: [digisearch, rag, architecture]
sources:
  - id: openwiki-source-0739fb1c67fa358e627b1663
    resource: repo://digisearch/ARCHITECTURE.md
  - id: openwiki-source-e6328240b5125d6213ffa41c
    resource: repo://digisearch/src/digisearch/search/_stub.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# digisearch Architecture

digisearch (port 8002 HTTP, 8765 MCP) is the centralized RAG vertical:
it owns ingest → parse → chunk → embed → index → query → rerank end to
end, and serves it over REST, MCP, CLI, and the orchestrator-tool
manifest digigraph consumes. Entity names drop the `Digi` prefix
(`Document`, `Chunk`, `Query`, `Result`).

## Pipeline

```
source → ParserRegistry → ChunkerBackend → EmbeddingCache/BatchEmbedder
  → DigiIndex.add()  …  query_index() router → normalize_query_hit()
  → optional rerank / RRF hybrid fusion → SearchResponse
```

Parsers cover PDF/DOCX/HTML/Markdown/CSV/text with OCR fallback;
chunking defaults to Chonkie semantic (`DIGISEARCH_CHUNKER` or per-index
config, segment-aware on ingest); embeddings fan out to OpenAI, Azure,
Cohere, HuggingFace, or Ollama behind cache + batching.

## Backend registry

`search/_stub.py` routes `query_index()` across three real backends —
Azure AI Search (BM25 + vector, OData filters), Cloudflare Vectorize v2
(cosine, remote-only), Chroma (cosine ANN, where-clause filters) — plus
an in-memory substring stub that runs **only** when
`DIGISEARCH_ALLOW_STUB=1` (unit tests; `_require_real_search_backend`
enforces this at startup). New backends register here; no `if
backend == "x"` dispatch in the query path. Every `ChromaBackend`
construction passes an explicit `embedding_provider` (never Chroma's
bundled ONNX default), and partial embedding batches raise rather than
dropping vectors.

## Vertical role

Under digigraph's federated hub, the `digisearch`,
`digisearch_fetch_all`, and `digisearch_research_delegate` tool schemas
and dispatch live entirely in digisearch — digigraph only forwards.
Direct consumers: digiflow via REST/MCP, CLI operators, digiclaw MCP
clients on `:8765/mcp`, and power users on `:8002`.

## Module map (selected)

| Area | Role |
|------|------|
| `ingestion/` + `chunking/` | Parsers, `ChunkerBackend` factory |
| `embedding/` + `embeddings/` | Providers, cache, batch embedder |
| `indexes/` | `DigiIndex`, backend implementations |
| `search/` | Router, hybrid RRF, reranker, stub guard |
| `agent/` | Research pipeline (citations, models) |
| `ingest_worker.py` | Bulk worker — logs and exits (stub until Phase 2) |
| `server.py`, `mcp_server.py`, `cli.py` | REST, MCP, Typer CLI |
| `orchestrator_tools.py` | Manifest digigraph fetches |

## Non-negotiable boundaries

Polars-only with no Nautilus exception; structured `filters: list[dict]`
over raw OData; ingest `source` is a validated server-side path (no raw
URLs, no traversal); new endpoints carry `digisearch:query`/`ingest`
scopes; no prompt or chunk bodies in trace spans.
