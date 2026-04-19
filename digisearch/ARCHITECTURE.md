# DigiSearch Architecture

**Component:** `digisearch`
**Port:** 8002 (HTTP); 8765 (MCP, `digisearch-mcp` profile)
**Codebase root:** `digisearch/src/digisearch/`

---

## Table of Contents

1. [Overview](#1-overview)
2. [Current Implementation State](#2-current-implementation-state)
3. [API Surface](#3-api-surface)
4. [Data Model](#4-data-model)
5. [Internal Architecture](#5-internal-architecture)
6. [Security Analysis](#6-security-analysis)
7. [Scalability Analysis](#7-scalability-analysis)
8. [Performance Analysis](#8-performance-analysis)
9. [Integration Points](#9-integration-points)
10. [Docker and MCP Composition](#10-docker-and-mcp-composition)
11. [Phase 2+ Gaps and Roadmap](#11-phase-2-gaps-and-roadmap)
12. [Redesign Recommendations](#12-redesign-recommendations)

---

## 1. Overview

DigiSearch is the centralized RAG (Retrieval-Augmented Generation) and document-search component of the DigiThings stack. It owns the complete retrieval pipeline: document ingestion, parsing, chunking, embedding, vector indexing, hybrid keyword/vector search, reranking, and result normalization.

### Role in the ecosystem

DigiSearch is consumed as a **vertical** under DigiGraph (the hub). DigiGraph registers DigiSearch as an orchestrator connector and delegates tool calls to it via HTTP. DigiSearch may also be reached directly by:

- **DigiFlow** (Langflow) — via REST or MCP
- **CLI operators** — via the `digisearch` Typer CLI
- **DigiClaw MCP clients** — via MCP attachment at `http://127.0.0.1:8765/mcp`
- **Power users** — directly at `http://127.0.0.1:8002`

In the federated hub model (`DIGI_HUB_MODE=federated`), DigiGraph exposes the `digisearch`, `digisearch_fetch_all`, and optionally `digisearch_research_delegate` tool names to its LLM. The tool schemas and dispatch logic live **entirely in DigiSearch**, not DigiGraph — which is the correct separation of concern.

### RAG pipeline

```
Document source
  │
  ▼
ParserRegistry (PDF / DOCX / HTML / Markdown / CSV / plain text)
  │ + OCR fallback (Tesseract / Azure DI / AWS Textract)
  ▼
Chunker (Fixed / Recursive / Sentence / Sliding / Semantic)
  │ + sidecar YAML metadata merge
  ▼
EmbeddingCache → BatchEmbedder → EmbeddingProvider
                                  (OpenAI / AzureOAI / Cohere / HuggingFace / Ollama)
  ▼
DigiIndex.add() — persists chunks + embeddings
  │
  ▼ (at query time)
query_index() router
  ├─ AzureAISearchBackend  (BM25 + vector natively, OData filters)
  ├─ ChromaBackend         (cosine ANN, Chroma where-clause filters)
  └─ in-memory stub        (substring; tests only)
  ▼
normalize_query_hit() → standard JSON hit shape
  │ optional: Reranker (Cohere / BGE / CrossEncoder)
  │ optional: HybridSearcher RRF fusion (keyword + vector)
  ▼
POST /query → QueryResponse
```

### Multi-backend strategy

DigiSearch uses a **backend registry** pattern (`search/_stub.py`). Backends register as callables `(Query, index_name) -> SearchResponse | None`. The router tries them in registration order (Azure first, then Chroma). Returning `None` means "not configured here; try next." This lets the same codebase serve both an Azure-hosted enterprise deployment and a local Chroma-on-disk deployment with zero code changes — only environment variables differ.

The in-memory stub (`DIGISEARCH_ALLOW_STUB=1`) is permanently last and exists for unit tests only. Startup enforcement (`_require_real_search_backend`) prevents the stub from activating in production.

---

## 2. Current Implementation State

As of the March 2026 codebase snapshot, the following modules are implemented and shipped:

| Module | Status | Source |
|--------|--------|--------|
| Core models (`Document`, `Chunk`, `Query`, `Result`, `SearchResponse`) | Implemented | `core/models.py` |
| `DigiSearchConfig` YAML/TOML loader with `${VAR}` substitution | Implemented | `core/config.py` |
| Evidence metadata normalization + Chroma serialization | Implemented | `core/evidence_metadata.py` |
| Standard hit normalization (`normalize_query_hit`) | Implemented | `core/standard_hits.py` |
| OData filter validator (regex allowlist) | Implemented | `core/filter_validator.py` |
| Structured-filter → Chroma `where` translation | Implemented | `core/chroma_where.py` |
| Structured-filter post-application (stub + Chroma) | Implemented | `core/filter_apply.py` |
| `EmbeddingProvider` abstract base | Implemented | `embedding/base.py` |
| `EmbeddingCache` (SQLite-backed) | Implemented | `embedding/cache.py` |
| `BatchEmbedder` (batching + retry) | Implemented | `embedding/batch.py` |
| `OpenAIEmbedder` provider | Implemented | `embedding/providers/openai.py` |
| `EmbeddingModelSpec` versioning | Implemented | `embeddings/config.py` |
| `DigiIndex` abstract interface | Implemented | `indexes/base.py` |
| `ChromaBackend` (persistent + in-memory) | Implemented | `indexes/backends/chroma.py` |
| `AzureAISearchBackend` (`query_azure`) | Implemented | `indexes/backends/azure_search.py` |
| `FAISSBackend` | Stub / placeholder | `indexes/backends/` |
| Other cloud backends (Pinecone, Qdrant, etc.) | Stub / placeholder | `indexes/backends/` |
| `HippoRAGBackend`, `PageIndexBackend` | Experimental stubs | `indexes/backends/` |
| `HybridSearcher` (RRF fusion) | Implemented | `search/hybrid.py` |
| `Reranker` (Cohere, BGE) | Implemented | `search/reranker.py` |
| `MultiIndexSearcher` | Implemented | `search/multi_index.py` |
| `QueryExpander`, `HyDE` | Implemented | `search/transforms/` |
| Backend router + stub | Implemented | `search/_stub.py` |
| `ParserRegistry` + PDF/DOCX/HTML/MD/CSV/text parsers | Implemented | `ingestion/` |
| OCR providers (Tesseract, Azure DI) | Implemented | `ingestion/ocr/` |
| Chunkers: Fixed, Recursive, Sentence, Sliding, Semantic | Implemented | `ingestion/chunkers/` |
| `FastAPI` server | Implemented | `server.py` |
| MCP server (`FastMCP`) | Implemented | `mcp_server.py` |
| CLI (Typer) | Implemented | `cli.py` |
| Orchestrator tool manifest + dispatch | Implemented | `orchestrator_tools.py` |
| Agent LangGraph pipeline (`plan → retrieve → aggregate`) | Implemented (optional `[agent]` extra) | `agent/pipeline.py` |
| Agent citations helper | Implemented | `agent/citations.py` |
| Crossref discovery | Implemented | `discovery/crossref.py` |
| Bulk ingest worker | **Placeholder** — logs and exits | `ingest_worker.py` |
| HTTP client helpers | Implemented | `http_client.py` |
| EDGAR dev corpus exporter | Implemented (dev/test) | `dev/edgar_sample_export.py` |

**Critical gap:** The bulk ingest worker (`digisearch-worker`) is a shell — it logs "no queue loop yet" and exits. All production ingest runs synchronously through `POST /ingest` on the query-serving FastAPI process.

---

## 3. API Surface

### REST Endpoints

All paths under the FastAPI app in `server.py`. Base URL: `http://digisearch:8002`.

#### `GET /health` and `GET /healthz`

Public (no auth). Both endpoints are rate-limit-exempt. `/health` returns `{"status": "ok", "service": "digisearch"}` (legacy, kept for back-compat). `/healthz` returns `{"ok": true}` — the preferred liveness probe for load balancers and k8s (see AGENTS.md "Liveness vs status"). Used by Docker healthcheck and DigiGraph startup dependency.

**Gap:** Does not probe backend connectivity. A backend can be offline and both endpoints return 200. See [Redesign Recommendations](#12-redesign-recommendations).

#### `GET /azure_status`

Returns Azure AI Search configuration and reachability status. Calls `get_document_count()` to verify the connection. Not authenticated — leaks configuration state.

#### `POST /query`

Auth required (`digisearch:query` scope). Rate limited: 10 req/min per IP.

```
Request:  QueryRequest
Response: QueryResponse
```

Key request fields:

| Field | Type | Notes |
|-------|------|-------|
| `text` | `str` | Query text (required) |
| `index_name` | `str` | Default: `"default"` |
| `top_k` | `int` | 1–100; default 10 |
| `mode` | `str` | `keyword` \| `vector` \| `hybrid` |
| `filter` | `str?` | Raw OData (only when `allow_raw_filter` is on) |
| `filters` | `list[dict]?` | Structured: `[{field, op, value}]` |
| `columns` | `list[str]?` | Metadata fields to return |
| `facets` | `list[str]?` | Azure facet expressions |
| `highlight_fields` | `list[str]?` | Azure hit highlighting |
| `order_by` | `list[str]?` | Azure sort clauses |
| `skip` | `int` | Pagination offset |
| `include_total_count` | `bool` | Return full match count |
| `response_mode` | `str` | `full` \| `summary` |
| `summarize_if_over` | `int?` | Auto-summarize when result count exceeds threshold |
| `format` | `str` | `default` \| `table` (markdown table in `response.formatted`) |
| `workspace_id` | `str?` | Tenant/workspace isolation hint |

Response includes `backend` field: `azure_ai_search` | `chroma` | `stub`.

#### `POST /ingest`

Auth required (`digisearch:ingest` scope). Rate limited: 30 req/min per IP.

```
Request:  IngestRequest { source: str, index_name: str, doc_type: str?, metadata: dict? }
Response: IngestResponse { doc_id, chunks_created, index_name, status }
```

Ingest pipeline: parse → detect sidecar YAML → merge metadata (sidecar first, then request body) → chunk (RecursiveChunker, 512/64) → merge doc metadata into chunks → add to backend.

**Critical gap:** `source` is a **filesystem path** on the server. The caller must ensure the path is accessible from inside the container. There is no URL-based ingest in the production path.

#### `GET /indexes`

Lists stub index names. Only meaningful when `DIGISEARCH_ALLOW_STUB=1`.

#### `GET /indexes/{name}`

Returns chunk count for named stub index.

#### `DELETE /indexes/{name}/documents/{doc_id}`

Returns HTTP 501. Per-document delete is not implemented.

#### `POST /v1/orchestrator_tools`

Auth required (`digisearch:query` scope). Rate limited: 30 req/min.

Returns OpenAI-style tool definitions for DigiGraph orchestration. Accepts optional `index_config` body to specialize tool schemas (filterable_fields, facetable_fields, result_metadata_fields).

Returns 2 or 3 tools:
- `digisearch` — standard search with pagination
- `digisearch_fetch_all` — auto-paginating fetch of full result sets
- `digisearch_research_delegate` — composite research turn (only when `digisearch[agent]` is installed)

#### `POST /v1/orchestrator_invoke`

Auth required (`digisearch:query` scope). Rate limited: 10 req/min.

Dispatches one named tool: `digisearch`, `digisearch_fetch_all`, or `digisearch_research_delegate`. The hub calls this to execute search without importing DigiSearch Python code directly.

#### `POST /v1/research_turn`

Auth required. Rate limited: 10 req/min.

Directly invokes the internal LangGraph pipeline (`plan → retrieve → aggregate`). Requires `digisearch[agent]` install. Returns `{service, error, trace, query, index_name, total, backend, results, rag_sources, formatted_context}`.

### MCP Tools

MCP server runs on port 8765 via `FastMCP` (`mcp_server.py`). Transport: streamable HTTP.

| Tool | Description | Optional |
|------|-------------|----------|
| `digisearch_query` | Search documents; returns formatted string of hits with score and content preview | No |
| `digisearch_research_turn` | Composite research turn (plan → retrieve → aggregate) with citations | Yes (`digisearch[agent]`) |

Tool parameters for `digisearch_query`: `text`, `index_name`, `top_k`, `mode`.

The MCP server has a module-level client hook (`_digisearch_client`) for wiring a real backend at startup. Without it, falls back to the stub. In production this should always be wired.

### CLI Commands

Entry point: `digisearch` (Typer). All defined in `cli.py`.

| Command | Description |
|---------|-------------|
| `digisearch ingest --index <name> <path>` | Ingest file or directory with optional YAML sidecar; uses stub backend |
| `digisearch ingest-batch --index <name> <dir>` | Batch-ingest all supported files under a directory |
| `digisearch discover-crossref <doi>` | Fetch Crossref metadata and print YAML sidecar snippet |
| `digisearch query --index <name> --text <q>` | Run search query and print ranked results |
| `digisearch serve [--config <path>] [--port 8002]` | Start HTTP API server (uvicorn) |
| `digisearch mcp [--port 8765]` | Start MCP server |
| `digisearch index build --config <path>` | Build/re-index (stub — prints guidance) |
| `digisearch index inspect --index <name>` | Inspect stub index chunk counts |

**Note:** CLI ingest uses the stub backend, not Chroma or Azure. For production ingest via CLI, operators must use `POST /ingest` via the HTTP API or call backend-specific code directly.

---

## 4. Data Model

All core contracts are Python dataclasses in `core/models.py`. Backward-compatibility aliases (`DigiDocument`, `DigiChunk`, etc.) exist but are not used in new code.

### `Document`

```
Document
├── id: str                    # generated UUID or hash at parse time
├── content: str               # full extracted text
├── source: str                # file path, URL, or identifier
├── doc_type: str              # "pdf", "html", "docx", "markdown", "csv", "plaintext"
├── metadata: dict[str, Any]   # normative evidence keys + parser-extracted fields
└── chunks: list[Chunk]        # populated after chunking
```

### `Chunk`

```
Chunk
├── id: str                    # stable per-chunk UUID
├── content: str               # chunk text
├── doc_id: str                # parent Document.id
├── embedding: list[float]?    # populated by EmbeddingProvider; None before embedding
└── metadata: dict[str, Any]  # inherits Document.metadata; chunk keys win on conflict
                               # Chroma-serialized: lists → comma-separated strings
```

### `Query`

```
Query
├── text: str                  # required
├── embedding: list[float]?    # pre-computed query embedding; computed at query time if None
├── top_k: int                 # default 10; capped at 100 in Chroma backend
├── filters: dict              # {"odata": str, "structured": list[{field, op, value}]}
├── mode: str                  # "keyword" | "vector" | "hybrid"
├── columns: list[str]?        # metadata fields to return (Azure only)
├── facets: list[str]?         # Azure facet expressions
├── highlight_fields: list[str]?
├── highlight_pre_tag: str?
├── highlight_post_tag: str?
├── order_by: list[str]?       # Azure sort clauses
├── skip: int                  # pagination offset; default 0
├── include_total_count: bool  # full match count; default False
└── workspace_id: str?         # tenant isolation hint (not enforced at backend level)
```

### `Result`

```
Result
├── chunk: Chunk
├── score: float               # relevance score; backend-specific scale
├── source_doc: Document?      # populated when full document is needed
└── rank: int?                 # 1-based rank after sorting
```

### `SearchResponse`

```
SearchResponse
├── results: list[Result]
├── facets: dict[str, list[{value, count}]]?  # Azure facet counts
├── total_count: int?          # full match count when include_total_count=True
└── backend: str?              # "azure_ai_search" | "chroma" | "stub"
```

### Standard JSON hit shape

`normalize_query_hit()` in `core/standard_hits.py` converts `Result` to the portable dict shape that all consumers (DigiGraph, DigiChat, MCP) depend on:

| Key | Type | Notes |
|-----|------|-------|
| `chunk_id` | `str` | Stable chunk / index key |
| `doc_id` | `str` | Parent document id |
| `rank` | `int?` | 1-based rank |
| `score` | `float` | Backend-specific relevance |
| `content` | `str` | Preview (max 500 chars by default) |
| `content_length` | `int` | Full UTF-8 length before truncation |
| `content_truncated` | `bool` | True when preview is shorter than full chunk |
| `metadata` | `dict` | Evidence metadata without `@search.*` keys |
| `highlights` | `dict?` | Azure `@search.highlights` when present |
| `captions` | `any?` | Azure `@search.captions` when present |
| `reranker_score` | `float?` | Azure semantic ranker score when present |
| `backend_extras` | `dict?` | Remaining `@search.*` keys |

### Evidence metadata (normative)

Defined in `core/evidence_metadata.py`. These keys SHOULD appear on both `Document.metadata` and inherited `Chunk.metadata`:

| Key | Type | Chroma format | Purpose |
|-----|------|---------------|---------|
| `evidence_tier` | `str` | string | `peer_reviewed` \| `working_paper` \| `industry` \| `web` |
| `peer_reviewed` | `bool` | bool | Shortcut flag; aligns with tier |
| `publication_year` | `int` | int | Publication year |
| `venue` | `str` | string | Journal, publisher, or site name |
| `title` | `str` | string | Document title |
| `doi_or_arxiv` | `str` | string | DOI or arXiv identifier |
| `asset_class_tags` | `list[str]` | comma-joined string | e.g. `"gold,equities"` — post-filtered |
| `methodology_tags` | `list[str]` | comma-joined string | e.g. `"momentum,mean_reversion"` — post-filtered |
| `language` | `str` | string | BCP-47 language code or free text |
| `license_notes` | `str` | string | Licensing or access notes |
| `source_url` | `str` | string | Stable source URL |

**Chroma serialization constraint:** ChromaDB only accepts `str`, `int`, `float`, `bool` in metadata. Lists are serialized as comma-joined strings at ingest by `normalize_metadata_for_chroma()`. Tag fields (`asset_class_tags`, `methodology_tags`) cannot be matched by Chroma's native `$in` — they are excluded from `chroma_where` translation and handled by `filter_apply.py` post-retrieval. This two-pass approach over-fetches and post-filters, which increases latency and may miss results if `fetch_n` is insufficient.

---

## 5. Internal Architecture

### Module structure

```
digisearch/src/digisearch/
│
├── server.py                  # FastAPI app: HTTP endpoints, rate limiting, correlation IDs
├── mcp_server.py              # FastMCP: MCP tool server (port 8765)
├── orchestrator_tools.py      # OpenAI-style tool manifest for DigiGraph orchestration
├── cli.py                     # Typer CLI (digisearch)
├── ingest_worker.py           # Bulk ingest placeholder (not implemented)
├── http_client.py             # HTTP client helpers for callers (query_digisearch, format_results_table)
├── client.py                  # DigiSearch Python client
│
├── core/
│   ├── models.py              # Document, Chunk, Query, Result, SearchResponse
│   ├── config.py              # DigiSearchConfig, YAML/TOML loader, ${VAR} substitution
│   ├── evidence_metadata.py   # Evidence tier system, Chroma normalization, sidecar loading
│   ├── standard_hits.py       # normalize_query_hit(), STANDARD_HIT_KEYS, backend labels
│   ├── chroma_where.py        # Structured filters → Chroma $and/$eq/$in etc.
│   ├── filter_apply.py        # Post-retrieval structured-filter matching (stub + Chroma)
│   ├── filter_validator.py    # OData allowlist validator (regex)
│   └── summarize.py           # Result summarization for response_mode=summary
│
├── embedding/
│   ├── base.py                # EmbeddingProvider ABC
│   ├── cache.py               # EmbeddingCache (SQLite, keyed by SHA-256 content hash)
│   ├── batch.py               # BatchEmbedder (batch_size=100, retry, linear backoff)
│   └── providers/
│       └── openai.py          # OpenAIEmbedder (others: azure_openai, cohere, huggingface, ollama)
│
├── embeddings/
│   └── config.py              # EmbeddingModelSpec (model_id, dimensions, version)
│
├── indexes/
│   ├── base.py                # DigiIndex ABC (add, query, delete, update, list_collections, snapshot)
│   └── backends/
│       ├── chroma.py          # ChromaBackend (cosine HNSW, persistent or in-memory)
│       ├── azure_search.py    # AzureAISearchBackend (query_azure, _build_odata_filter)
│       └── faiss.py           # FAISSBackend (stub)
│
├── search/
│   ├── _stub.py               # Backend registry + router; in-memory stub (test only)
│   ├── keyword.py             # BM25Searcher, TFIDFSearcher
│   ├── vector.py              # VectorSearcher
│   ├── hybrid.py              # HybridSearcher (RRF, alpha=0.6)
│   ├── reranker.py            # Reranker (Cohere, BGE)
│   ├── multi_index.py         # MultiIndexSearcher (fan-out + merge)
│   └── transforms/
│       ├── query_expansion.py # QueryExpander
│       └── hyde.py            # HyDE (Hypothetical Document Embeddings)
│
├── ingestion/
│   ├── base.py                # Parser ABC
│   ├── registry.py            # ParserRegistry (extension/MIME detection)
│   ├── parsers/               # pdf, docx, html, markdown, csv, plaintext
│   ├── ocr/                   # base, tesseract, azure_di
│   └── chunkers/              # base, fixed, recursive, sentence, sliding_window, semantic
│
├── agent/
│   ├── pipeline.py            # LangGraph: plan → retrieve → aggregate
│   └── citations.py           # rag_sources_from_hits()
│
├── discovery/
│   └── crossref.py            # DOI → EvidenceMetadata via Crossref REST API
│
└── dev/
    └── edgar_sample_export.py # EDGAR-CORPUS slice exporter (dev/test only)
```

### Pluggable backend pattern

The backend registry in `search/_stub.py` uses a simple callable list pattern:

```
_backends: list[Callable[[Query, str], SearchResponse | None]]

register_backend(fn) → appends fn to _backends

query_index(query, index_name):
  for backend in _backends:
    resp = backend(query, index_name)
    if resp is not None:
      return resp
  # fall through to stub or empty
```

Azure is registered first (preferred), Chroma second, stub last. Adding a new backend requires only calling `register_backend()` at import time. There is no configuration-driven selection — the first configured backend wins.

**Weakness:** if Azure is misconfigured (credentials present but wrong), the Azure backend raises, logs a warning, returns `None`, and silently falls through to Chroma. Operators may not notice that a production query is served by the wrong backend.

### Embedding cache layer

`EmbeddingCache` wraps any `EmbeddingProvider`. On each `embed()` call:

1. Batch-query SQLite for known hashes (`SELECT WHERE hash IN (...)`)
2. Compute embeddings only for cache misses
3. `INSERT OR REPLACE` new embeddings
4. Return full list, preserving positional alignment

The cache key is `SHA-256(text.encode("utf-8"))`. This is content-addressed: identical text always hits the cache regardless of which document it came from. Cache path defaults to `.digisearch_embed_cache.db` in CWD or `DIGISEARCH_CACHE_PATH`.

**Weakness:** SQLite has no expiry mechanism. A model change (different dimensions) without clearing the cache will silently return stale vectors. The `EmbeddingModelSpec` versioning system (`embeddings/config.py`) tracks model + version but does not automatically invalidate or namespace the cache.

### Hybrid RRF fusion

`HybridSearcher` in `search/hybrid.py`:

1. Expand query: fetch `top_k * 2` results from each searcher
2. For each keyword result: add `(1 - alpha) * RRF_score(rank)` to the chunk's cumulative score
3. For each vector result: add `alpha * RRF_score(rank)` to the chunk's cumulative score
4. Sort by cumulative score descending, take top `k`

```
RRF_score(rank, k=60) = 1 / (60 + rank)
```

Default `alpha = 0.6` (60% weight on vector results). The RRF constant `k=60` is hardcoded and not configurable.

**Important:** The `HybridSearcher` class is not what the production server actually uses. The server delegates to `query_index()` which calls the registered backends (Azure or Chroma) directly. Azure supports native hybrid (BM25 + vector) internally. Chroma does not support BM25 natively — the `HybridSearcher` would need to be wired at a higher level for Chroma-based hybrid. The current server uses `mode` as a passthrough hint to the backend, but Chroma only supports ANN (cosine distance) — `mode="keyword"` or `mode="hybrid"` on a Chroma backend falls back to vector-only.

### Orchestrator dispatch pattern

DigiGraph registers DigiSearch via `POST /v1/orchestrator_tools`. When an LLM calls one of the tool names, DigiGraph calls `POST /v1/orchestrator_invoke` with `{tool, arguments, default_index_name}`. The dispatch code in `server.py` (`api_orchestrator_invoke`) maps tool names to internal query logic. This means:

- Tool schemas are owned and versioned by DigiSearch
- DigiGraph has no search logic — it is a pass-through hub
- `digisearch_fetch_all` performs server-side pagination in a while loop (page size 500) and returns the full collected set in a single response, which can be very large

---

## 6. Security Analysis

### DigiKey JWT auth scopes

DigiSearch uses `DigiAuthMiddleware` from `digikey.integrations.service_middleware`. The middleware validates DigiKey JWTs and enforces path-to-scope mappings defined in `digisearch_path_scopes`.

| Endpoint | Required scope |
|----------|---------------|
| `POST /query` | `digisearch:query` |
| `POST /ingest` | `digisearch:ingest` |
| `POST /v1/orchestrator_tools` | `digisearch:query` |
| `POST /v1/orchestrator_invoke` | `digisearch:query` |
| `POST /v1/research_turn` | `digisearch:query` |
| `GET /health` | Public |
| `GET /azure_status` | Public |
| `GET /indexes`, `GET /indexes/{name}` | (unclear — not in server auth logic) |

**Gap:** `GET /azure_status` is unauthenticated and leaks backend configuration state (endpoint URL validity, index name, reachability). Should require at minimum a read scope or be restricted to internal networks.

### Multi-tenant isolation gap

`workspace_id` is accepted on `POST /query` and stored in `Query.workspace_id` but **none of the backend implementations enforce it at query time**. The field is passed into `Query` and then ignored by both `ChromaBackend.query()` and `query_azure()`. There is no index prefix routing, ACL filter injection, or collection scoping based on `workspace_id`.

This means a caller with a valid `digisearch:query` JWT can omit `workspace_id` (or supply any value) and receive results from any tenant's data in the index. For single-tenant deployments this is acceptable; for multi-tenant enterprise deployments this is a critical data isolation failure.

### Filter injection risks

**Raw OData path:** `POST /query` accepts a `filter` string when `allow_raw_filter=True` is set in the index config. The `filter_validator.py` applies:

1. Blocked pattern regex: rejects `exec(`, `eval(`, `<script`, `javascript:`, `data:`
2. Character allowlist: rejects non-OData characters including newlines
3. Returns original string if valid

The allowlist (`^[\w \t'\"<>=!(),./\\:\-\+\*\?%@]+$`) permits `*`, `?`, `@`, and forward slashes, which are all required for OData navigation properties but also create opportunities for crafted expressions. The validator does not parse the OData AST — it is a syntactic allowlist, not a semantic validator. A carefully crafted filter could enumerate fields or extract unexpected data if the index schema has sensitive fields.

**Structured filter path:** `_build_odata_filter()` enforces a `filterable_fields` allowlist. Only fields listed in the index config's `filterable_fields` array are accepted. This is the safer path; injection risk is low if the allowlist is maintained correctly.

**Chroma structured filters:** `structured_filters_to_chroma_where()` maps structured filters to Chroma `$and`/`$eq`/`$in` expressions. The field name is not allowlisted — any string can be used as a Chroma metadata key. An attacker with `digisearch:query` scope could probe for undocumented metadata fields.

### Embedding model API key exposure

The `OpenAIEmbedder` (and other cloud providers) read API keys from environment variables (`OPENAI_API_KEY`, `COHERE_API_KEY`, etc.). These are never logged or returned in API responses. The `Reranker._rerank_cohere()` reads `COHERE_API_KEY` at call time. The digismith/ARCHITECTURE.md spec prohibits including API keys in spans — this is respected in the current implementation.

**Potential risk:** the `EmbeddingCache` stores embedding vectors in a local SQLite file. If the file is accessible to multiple processes or shared across container mounts, the vectors could in principle be used to reconstruct approximate original text via inversion attacks. This is a low-severity theoretical risk for most use cases.

### CORS policy

`DIGI_ALLOWED_ORIGINS` controls allowed CORS origins. Default when unset: `localhost:3000`, `localhost:8000`, `localhost:11434`. This is acceptably restrictive for loopback deployments. Production deployments must explicitly set this.

### Rate limiting

Per-IP rate limiting is implemented in-process (not via a proxy). The limiter uses `threading.Lock` and `collections.deque` — correct for sync workers but not robust under async or multi-process deployments. IP extraction respects `X-Forwarded-For` but does not validate the hop count, which means a caller can supply a fake IP in `X-Forwarded-For` to bypass per-IP limits.

---

## 7. Scalability Analysis

### Chroma single-node limits

ChromaDB runs as a persistent local process (`chromadb.PersistentClient`). In Docker Compose, it runs inside the `digi-digisearch` container with data stored in the `digisearch_chroma` named volume. There is no Chroma HTTP server mode configured — each FastAPI worker process creates its own `PersistentClient` connecting to the same on-disk SQLite/HNSW files. Under concurrency this risks write conflicts during ingest.

Chroma's HNSW index is held in memory. For large corpora (>1M chunks at 1536 dimensions), memory requirements are significant — roughly 6 GB for 1M float32 vectors before HNSW overhead. There is no sharding or collection-splitting logic.

**Ceiling:** Chroma is appropriate for single-tenant workloads up to roughly 500K–1M chunks. Beyond that, the HNSW build time, memory footprint, and single-process write bottleneck become limiting.

### Embedding batch size

`BatchEmbedder` defaults to `batch_size=100`. OpenAI's `text-embedding-3-small` accepts up to 2048 inputs per call. Using 100 means at least 10x more API calls than necessary for large ingest jobs. For a 100K-chunk ingest, this means 1000 API calls instead of ~50.

The retry delay is linear: `delay * (attempt + 1)` seconds. Under heavy rate-limiting, this adds up to 1+2+3 = 6 seconds per failed batch before giving up.

### Redis vs SQLite embedding cache

The current `EmbeddingCache` is SQLite-backed with no TTL, no expiry, and no cross-process coordination. In a multi-container or multi-worker deployment:

- Each container has its own SQLite cache file (volume-mounted or ephemeral)
- Parallel ingest workers redundantly re-embed the same chunks
- No cache invalidation on model change

Redis would provide: shared cache across processes/containers, TTL-based expiry for model migration, atomic cache invalidation by model version namespace, and better concurrent write performance.

### Bulk ingest worker placeholder

`ingest_worker.py` (`digisearch-worker` console script) logs a message and exits. All production ingest goes through `POST /ingest` on the HTTP query process. This means:

- Large ingest jobs block query capacity
- No queue-based retry for failed documents
- No progress tracking for batch jobs
- No backpressure when the backend is slow

The architecture correctly identifies this as the ingest vs query boundary in `ARCHITECTURE.md`, but the implementation does not separate them.

### Multi-index fan-out overhead

`MultiIndexSearcher` fans queries to multiple `DigiIndex` instances in parallel. In `digisearch_fetch_all` (the orchestrator tool), pagination runs in a while loop: each page issues a new query, waits for the response, and accumulates results. For large result sets this can take seconds and holds the FastAPI worker for the duration.

`digisearch_fetch_all` also has no hard ceiling on total results (only `max_results` when provided by the caller). A pathological query returning 10K results would collect all of them in one response and serialize them into a single JSON payload.

---

## 8. Performance Analysis

### Hybrid RRF alpha tuning

The default `alpha=0.6` in `HybridSearcher` is a reasonable starting point biased toward semantic (vector) results. However:

- There is no per-query or per-index alpha override in the current API
- The RRF constant `k=60` is hardcoded; lower values (e.g. `k=20`) favor top-ranked results more strongly
- For the Chroma backend, `mode` is passed as a hint but Chroma only supports vector search — the keyword leg is absent, making alpha irrelevant

For Azure AI Search, the service uses its own internal hybrid ranking. The DigiSearch `mode` parameter maps to `query_type="simple"` in all cases — there is no `"semantic"` or `"vector"` query type being set. This means Azure's BM25 is always active and DigiSearch does not currently unlock Azure's native vector search or semantic ranker modes.

### Embedding cache hit rates

The `EmbeddingCache` logs hit rates at INFO level. For a cold corpus, hit rate is 0%. For repeated ingest of an unchanged corpus, hit rate approaches 100%. The cache is most valuable during development iteration (re-ingesting a modified corpus where most chunks are unchanged).

Hit rate degrades when:
- Different chunkers are used on the same documents (different chunk boundaries → different text → cache miss)
- Chunks are slightly modified between runs (e.g. whitespace normalization changes)
- The cache is not mounted persistently in Docker (ephemeral container restarts)

### Chunking strategy impact on retrieval quality

The default `RecursiveChunker(chunk_size=512, chunk_overlap=64)` is a safe general-purpose default. Impact considerations:

- **Too small (< 128 tokens):** chunks lose context; recall suffers on paraphrase queries
- **Too large (> 1024 tokens):** chunks dilute relevance scores; precision suffers
- **Zero overlap:** boundary queries that span chunks miss evidence
- **Sentence chunker for dense financial text:** preserves semantic units better than fixed splits, but spaCy/NLTK add latency
- **Semantic chunker:** embedding-based boundary detection increases ingest cost ~2x

For SEC filings (EDGAR corpus), recursive chunking with headers preserved (`RecursiveChunker` respects Markdown/heading delimiters) works well for 10-K structured text.

### Reranker latency tradeoff

`Reranker` runs as a second-pass over the initial candidate set (default `top_n=5`). Cost:

- **Cohere Rerank API:** ~200–500ms per call, network-dependent
- **BGE local (sentence-transformers `CrossEncoder`):** ~50–200ms for a batch of 10 candidates on CPU; ~10ms on GPU
- Model load on first call adds several seconds for BGE

The reranker is not wired into the production `POST /query` path. It is available as a class but callers must instantiate and invoke it explicitly. It is not part of the `query_index()` router.

### FAISS vs Chroma for large corpora

| Criterion | Chroma (current default) | FAISS (placeholder) |
|-----------|--------------------------|---------------------|
| Query latency (1M vecs) | ~10–50ms | ~1–5ms |
| Memory footprint | Higher (SQLite overhead) | Lower (pure binary) |
| Metadata filtering | Chroma `where` clause | Requires pre-filtering |
| Persistence | SQLite + HNSW files | `.faiss` + `.pkl` files |
| Write concurrency | Single writer | Single writer |
| Production readiness | Limited (no sharding) | Limited (no HTTP server) |

For the target use case (DigiClone research corpus, tens to hundreds of thousands of chunks), Chroma's performance is adequate. For a large email corpus (millions of items), Azure AI Search is the appropriate backend.

---

## 9. Integration Points

### Orchestrator tools contract with DigiGraph

DigiGraph calls DigiSearch via two HTTP routes:

1. `POST /v1/orchestrator_tools` — fetches tool schemas, optionally specializing them with index metadata (filterable fields, facetable fields, result columns, complex field structures). The hub caches these and presents them to the LLM.

2. `POST /v1/orchestrator_invoke` — dispatches tool execution. The hub passes `{tool, arguments, default_index_name}` and receives `{ok, service, tool, data}`.

The contract is versioned by `{"tools": [...], "version": 1}` in the tools response. DigiGraph should treat unknown tool names from `/v1/orchestrator_tools` gracefully.

`DIGISEARCH_INDEX` env on DigiGraph controls the default index name. When `DIGI_HUB_MODE=federated`, DigiGraph registers DigiSearch as a connector tool that the LLM can call directly.

### DigiClaw MCP attachment

DigiClaw may attach to the DigiSearch MCP server at `http://127.0.0.1:8765/mcp` (loopback, `digisearch-mcp` Docker profile). Tools available: `digisearch_query`, `digisearch_research_turn` (when `[agent]` is installed).

MCP clients (Langflow, IDE tools) attach to the same server. There is no per-client auth on the MCP server itself — access control is purely at network level (loopback binding).

### DigiFlow integration

DigiFlow (Langflow) connects at `http://digisearch:8002` (HTTP) or MCP. Standard `POST /query` with `format=table` for display-ready results. DigiFlow can also import the `DigiSearch` Python client directly if running in the same process.

### Sidecar YAML metadata loading

At ingest time (both `POST /ingest` and CLI `digisearch ingest`), DigiSearch looks for a sidecar file at `{stem}.yaml` or `{stem}.yml` next to the source file. The sidecar `metadata:` block (or flat normative keys at root) is loaded first, then merged with parser-extracted metadata, then with the request body `metadata` field. The request body wins on conflicts.

This allows a document corpus to be annotated with evidence tier, DOI, venue, and tags without embedding metadata in the document itself.

### `DIGI_EXTRACT_STRATEGY_AFTER_DOCUMENT_RAG`

When `DIGI_EXTRACT_STRATEGY_AFTER_DOCUMENT_RAG=1` is set on DigiGraph, DigiGraph performs structured extraction of `strategy_name` and `symbols` after receiving RAG context from DigiSearch. This is a DigiGraph concern — DigiSearch is unaware of it.

---

## 10. Docker and MCP Composition

### Docker Compose service

```yaml
digisearch:
  build:
    context: .
    dockerfile: digisearch/Dockerfile
  image: digi-digisearch:latest
  container_name: digi-digisearch
  ports:
    - "127.0.0.1:8002:8002"      # loopback-only
  environment:
    - CHROMA_PATH=/data/chroma
    - DIGISEARCH_INDEX=${DIGISEARCH_INDEX:-default}
    - DIGIKEY_JWKS_URL=...
    - DIGIKEY_ISSUER=...
    - DIGIKEY_AUDIENCE=...
  volumes:
    - digisearch_chroma:/data/chroma     # persistent Chroma data
    - ./digisearch/devdata/edgar_sample:/data/edgar_dev_corpus:ro
  depends_on:
    digikey:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://127.0.0.1:8002/health"]
    interval: 15s
    timeout: 5s
    retries: 3
    start_period: 10s
```

The `digisearch-mcp` Docker Compose profile starts the MCP server sidecar. To enable:

```bash
docker compose --profile digisearch-mcp up
```

### Environment variables reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `CHROMA_PATH` | _(unset)_ | Path to persistent Chroma data directory; activates Chroma backend |
| `CHROMA_HOST` | _(unset)_ | Chroma HTTP server host; activates Chroma backend (remote mode) |
| `AZURE_SEARCH_ENDPOINT` | _(unset)_ | Azure AI Search service endpoint URL |
| `AZURE_SEARCH_API_KEY` | _(unset)_ | Azure AI Search admin or query key |
| `AZURE_SEARCH_INDEX_NAME` | _(unset)_ | Default Azure index name |
| `AZURE_SEARCH_CONTENT_FIELD` | `content` | Azure field for chunk text |
| `AZURE_SEARCH_KEY_FIELD` | `id` | Azure document key field |
| `AZURE_SEARCH_DOC_ID_FIELD` | `doc_id` | Azure field for parent document id |
| `DIGISEARCH_INDEX` | `default` | Default index name for queries |
| `DIGISEARCH_INDEX_CONFIG` | _(unset)_ | Path to index YAML (field_mapping, schema) |
| `DIGISEARCH_CONFIG_PATH` | _(unset)_ | Path to YAML/TOML DigiSearchConfig |
| `DIGISEARCH_ALLOW_STUB` | `0` | Enable in-memory stub (unit tests only) |
| `DIGISEARCH_CACHE_PATH` | `.digisearch_embed_cache.db` | SQLite embedding cache path |
| `DIGISEARCH_EMBEDDING_MODEL` | _(unset)_ | Active embedding model id for versioning |
| `DIGISEARCH_EMBEDDING_DIM` | `1536` | Vector dimension for versioning |
| `DIGISEARCH_EMBEDDING_VERSION` | `1` | Logical version for index migration |
| `OPENAI_API_KEY` | _(unset)_ | OpenAI API key for OpenAIEmbedder |
| `COHERE_API_KEY` | _(unset)_ | Cohere key for CohereEmbedder / CohereReranker |
| `DIGI_ALLOWED_ORIGINS` | localhost defaults | Comma-separated CORS allowed origins |
| `DIGI_DISABLE_RATE_LIMIT` | `0` | Disable per-IP rate limiting (testing) |
| `DIGIKEY_JWKS_URL` | _(required)_ | DigiKey JWKS endpoint for JWT validation |
| `DIGIKEY_ISSUER` | _(required)_ | JWT issuer |
| `DIGIKEY_AUDIENCE` | _(required)_ | JWT audience |

### MCP server startup

The MCP server is started via `digisearch mcp --port 8765` (CLI) or the `digisearch-mcp` Docker profile. Default transport: streamable HTTP. The server runs `FastMCP("DigiSearch")` from the `mcp` package.

In the current implementation, `_digisearch_client` is only set by calling `create_mcp_with_indexes(client)` explicitly. The `mcp_server.py` module-level setup does not call this automatically — tools fall back to the stub unless caller code wires the client at startup.

---

## 11. Phase 2+ Gaps and Roadmap

### Internal agent graph (`[agent]` extra)

The `digisearch[agent]` optional extra installs `langgraph` and enables:

- `digisearch_research_turn` MCP tool
- `digisearch_research_delegate` orchestrator tool
- `POST /v1/research_turn` REST endpoint
- The `agent/pipeline.py` LangGraph: `plan → retrieve → aggregate`

The current graph is minimal: `node_plan` validates input, `node_retrieve` calls `query_index`, `node_aggregate` formats results and extracts citations. There is no query reformulation, no multi-step retrieval, and no LLM calls within the graph. The `[agent]` label oversells the current capability.

**Roadmap:** A full research-turn graph would include LLM-based query decomposition, sub-query expansion, result deduplication, evidence gap detection, and iterative retrieval.

### Multi-tenant enforcement

`workspace_id` exists in the data model but is not enforced by any backend. Required work per backend:

- **Chroma:** route to a named collection per workspace (`{workspace_id}_{index_name}`) or inject `{"workspace_id": workspace_id}` as a mandatory `where` clause
- **Azure:** inject an OData filter clause `(workspace_id eq '{workspace_id}')` for all queries
- **Stub:** filter post-retrieval by `chunk.metadata.get("workspace_id")`

Without this, `workspace_id` is decorative.

### Bulk ingest queue

`ingest_worker.py` is a placeholder. A production bulk ingest queue would:

1. Accept a batch job submission endpoint (`POST /v1/ingest_jobs`)
2. Queue jobs via Redis or a lightweight queue (ARQ, Celery, or simple DB-backed queue)
3. Run ingest workers in separate processes (not on the query HTTP process)
4. Return job IDs with `GET /v1/ingest_jobs/{job_id}/status`
5. Support retry on parse errors and embedding API failures

### HippoRAG and PageIndex experimental backends

`indexes/backends/hipporag.py` and `indexes/backends/pageindex.py` are listed in the folder structure but are experimental stubs. HippoRAG (KG-augmented RAG) and PageRank-influenced retrieval are not part of the production routing path.

### Reranker wiring

The `Reranker` class is implemented but not wired into the `POST /query` path or `query_index()`. Enabling it requires explicit instantiation by the caller or a configuration-driven pipeline.

### Missing HTTP endpoints

- No `PATCH /indexes/{name}/documents/{doc_id}` for partial updates
- No `POST /indexes/{name}/reindex` for triggering a re-embed
- `DELETE /indexes/{name}/documents/{doc_id}` returns 501
- No `GET /v1/health/detailed` with backend connectivity checks (see Recommendations)

---

## 12. Redesign Recommendations

The following are specific, actionable improvements prioritized by operational impact.

### (a) Enforce `workspace_id` isolation at query time per backend

**Problem:** `workspace_id` is accepted but ignored. Any authenticated caller can read any tenant's data.

**Recommendation:**

For Chroma: when `workspace_id` is non-null, route to a named collection `{workspace_id}__{index_name}` instead of `index_name`. This requires creating collections per workspace at ingest time but provides complete data isolation at zero query overhead.

For Azure: inject a mandatory OData filter clause into every query when `workspace_id` is set: `(workspace_id eq '{workspace_id}')`. This requires the `workspace_id` field to be in the Azure index schema and marked filterable.

The `Query.workspace_id` field should propagate all the way to `ChromaBackend.query()` and `query_azure()` with enforcement, not as a pass-through hint.

### (b) Redis-backed embedding cache for production

**Problem:** The SQLite embedding cache is per-process, has no TTL, and does not support cross-container sharing.

**Recommendation:** Add a `RedisEmbeddingCache` backend that:
- Keys embeddings by `f"{model_id}:{version}:{sha256(text)}"` — namespaced by model version
- Sets TTL to 90 days (configurable via `DIGISEARCH_CACHE_TTL`)
- Falls back to SQLite when Redis is unavailable (`DIGISEARCH_REDIS_URL` unset)
- On model version change, old cache entries under the old prefix naturally expire

Activation: `DIGISEARCH_REDIS_URL=redis://redis:6379/1`.

### (c) Async bulk ingest queue (Celery or ARQ)

**Problem:** All ingest runs synchronously on the query-serving process, blocking it.

**Recommendation:** Wire the `ingest_worker.py` placeholder to a real queue backend:

1. `POST /v1/ingest_jobs` — accepts `{sources: list[str], index_name, chunker, metadata}`, enqueues job, returns `{job_id}`
2. `GET /v1/ingest_jobs/{job_id}` — returns `{status: pending|running|completed|failed, chunks_created, errors}`
3. Worker process (`digisearch-worker`) runs `ARQ` or `Celery` consumer pulling from Redis queue
4. The existing `POST /ingest` remains for low-volume synchronous ingest

ARQ (async Redis queue) is the lightest-weight option and avoids the Celery broker/worker complexity for this use case.

### (d) Add `/v1/health/detailed` with backend connectivity checks

**Problem:** `GET /health` always returns 200 regardless of backend state. DigiGraph and monitoring cannot distinguish "service up but backend offline" from "fully healthy."

**Recommendation:**

```
GET /v1/health/detailed
→ {
    "status": "ok" | "degraded" | "unhealthy",
    "service": "digisearch",
    "backends": {
      "azure": {"configured": bool, "reachable": bool, "latency_ms": int},
      "chroma": {"configured": bool, "reachable": bool, "collection_count": int},
    },
    "embedding_cache": {"backend": "sqlite" | "redis", "reachable": bool},
    "uptime_s": int
  }
```

This endpoint should be **authenticated** (unlike `GET /health`) to avoid leaking topology.

The existing `GET /azure_status` endpoint overlaps with this and should be consolidated.

### (e) Prometheus metrics per backend and mode

**Problem:** There are no metrics. Operators cannot observe query latency, cache hit rates, backend error rates, or ingest throughput.

**Recommendation:** Add a `prometheus-client` integration that exposes `GET /metrics`:

| Metric | Labels | Type |
|--------|--------|------|
| `digisearch_query_duration_seconds` | `backend`, `mode`, `status` | Histogram |
| `digisearch_ingest_duration_seconds` | `chunker`, `status` | Histogram |
| `digisearch_embedding_cache_hits_total` | `backend` | Counter |
| `digisearch_embedding_cache_misses_total` | `backend` | Counter |
| `digisearch_backend_errors_total` | `backend`, `error_type` | Counter |
| `digisearch_query_results_count` | `backend`, `mode` | Histogram |

The embedding cache already logs hit rates at INFO level — these should become metrics.

### (f) Schema versioning for evidence metadata

**Problem:** When the embedding model changes (e.g. from `text-embedding-3-small` to `text-embedding-3-large`), vectors in the index are incompatible. There is no mechanism to detect this or trigger a re-index. The `EmbeddingModelSpec` version string is tracked but not enforced at query time.

**Recommendation:**

1. Store `embedding_model_id`, `embedding_dimensions`, and `embedding_version` in Chroma collection metadata and in Azure index document schema
2. At startup, verify that the configured embedding spec matches the spec stored in the index
3. If there is a mismatch, log an error and optionally raise (configurable via `DIGISEARCH_STRICT_VERSION_CHECK=1`)
4. Provide a `digisearch index reembed --index <name>` CLI command that re-embeds and upserts all chunks under the new model

The `EmbeddingModelSpec.version` field in `embeddings/config.py` is the right anchor point — it needs to be persisted to and read from the index, not just held in env vars.

## Observability

This service exposes a Prometheus `/metrics` endpoint (counter, histogram, in-flight gauge for every HTTP route) via `digibase.metrics.install_metrics`; scraped by the `observability` compose profile per [ADR-0003](../docs/adr/0003-observability-baseline.md).
