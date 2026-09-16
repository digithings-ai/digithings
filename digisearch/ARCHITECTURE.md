# digisearch Architecture

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

digisearch is the centralized RAG (Retrieval-Augmented Generation) and document-search component of the digithings stack. It owns the complete retrieval pipeline: document ingestion, parsing, chunking, embedding, vector indexing, hybrid keyword/vector search, reranking, and result normalization.

### Role in the ecosystem

digisearch is consumed as a **vertical** under digigraph (the hub). digigraph registers digisearch as an orchestrator connector and delegates tool calls to it via HTTP. digisearch may also be reached directly by:

- **digiflow** (Langflow) — via REST or MCP
- **CLI operators** — via the `digisearch` Typer CLI
- **digiclaw MCP clients** — via MCP attachment at `http://127.0.0.1:8765/mcp`
- **Power users** — directly at `http://127.0.0.1:8002`

In the federated hub model (`DIGI_HUB_MODE=federated`), digigraph exposes the `digisearch`, `digisearch_fetch_all`, `web_search`, and optionally `digisearch_research_delegate` tool names to its LLM. The tool schemas and dispatch logic live **entirely in digisearch**, not digigraph — which is the correct separation of concern.

### RAG pipeline

```
Document source
  │
  ▼
ParserRegistry (PDF / DOCX / HTML / Markdown / CSV / plain text)
  │ + OCR fallback (Tesseract / Azure DI / AWS Textract)
  ▼
ChunkerBackend (Chonkie Semantic default / Token / legacy Recursive·Fixed)
  │ via DIGISEARCH_CHUNKER or per-index ``chunker``
  │ + SegmentAwareChunker wrapper on POST /ingest
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
  ├─ VectorizeBackend      (Cloudflare Vectorize v2 REST API, cosine, remote-only)
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

digisearch uses a **backend registry** pattern (`search/_stub.py`). Backends register as callables `(Query, index_name) -> SearchResponse | None`. The router tries them in registration order (Azure first, then Vectorize, then Chroma). Returning `None` means "not configured here; try next." This lets the same codebase serve an Azure-hosted enterprise deployment, a local Chroma-on-disk deployment, or a Cloudflare Vectorize remote-index deployment with zero code changes — only environment variables differ.

The in-memory stub (`DIGISEARCH_ALLOW_STUB=1`) is permanently last and exists for unit tests only. Startup enforcement (`_require_real_search_backend`) prevents the stub from activating in production.

### RetrievalBackend protocol (#402)

Document-level async retrieval is a **separate** swappable seam from the DigiIndex `/query` router. Callers depend on `RetrievalBackend` only; concrete backends register in `retrieval/registry.py` and are selected via `DIGISEARCH_RETRIEVAL_BACKEND`.

```
                    DIGISEARCH_RETRIEVAL_BACKEND
                              │
                              ▼
                    get_retrieval_backend()
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     PgvectorBackend (default)         LightRAGBackend
     DIGISEARCH_DATABASE_URL           DIGISEARCH_RETRIEVAL_BACKEND=lightrag
     + pgvector extension              + Postgres storages / local embeddings
              │                               │
              └───────────────┬───────────────┘
                              ▼
                    index / retrieve / delete / health
```

| Backend | Extra | Notes |
|---------|-------|-------|
| `pgvector` | `digisearch[pgvector]` (`psycopg`) | Default. MiniLM embeddings. In-memory store when no DSN (tests). |
| `lightrag` | `digisearch[lightrag]` | Graph-enhanced upgrade. Embeddings default to Ollama `nomic-embed-text` or `DIGISEARCH_LIGHTRAG_EMBEDDING=minilm` — not OpenAI. |

**Infra note:** production pgvector needs a reachable Postgres with `CREATE EXTENSION vector` and a DSN in `DIGISEARCH_DATABASE_URL` / `DIGISEARCH_PGVECTOR_URL` (human/secrets). This issue does not provision a new database service.

---

## 2. Current Implementation State

As of the March 2026 codebase snapshot, the following modules are implemented and shipped:

| Module | Status | Source |
|--------|--------|--------|
| Core models (`Document`, `Chunk`, `Query`, `Result`, `SearchResponse`, `Segment`) | Implemented | `core/models.py` |
| `DigiSearchConfig` YAML/TOML loader with `${VAR}` substitution | Implemented | `core/config.py` |
| Evidence metadata normalization + Chroma serialization | Implemented | `core/evidence_metadata.py` |
| Standard hit normalization (`normalize_query_hit`) | Implemented | `core/standard_hits.py` |
| OData filter validator (regex allowlist) | Implemented | `core/filter_validator.py` |
| Structured-filter → Chroma `where` translation | Implemented | `core/chroma_where.py` |
| Structured-filter post-application (stub + Chroma) | Implemented | `core/filter_apply.py` |
| `EmbeddingProvider` abstract base | Implemented | `embedding/base.py` |
| `EmbeddingCache` (SQLite-backed) | Implemented | `embedding/cache.py` |
| `BatchEmbedder` (batching + retry) | Implemented | `embedding/batch.py` |
| Embed pipeline factory + `query.mode` helpers | Implemented | `embedding/factory.py` |
| `OpenAIEmbedder` provider | Implemented | `embedding/providers/openai.py` |
| `EmbeddingModelSpec` versioning | Implemented | `embeddings/config.py` |
| `DigiIndex` abstract interface | Implemented | `indexes/base.py` |
| `ChromaBackend` (persistent + in-memory) | Implemented | `indexes/backends/chroma.py` |
| `AzureAISearchBackend` (`query_azure`) | Implemented | `indexes/backends/azure_search.py` |
| `VectorizeBackend` (Cloudflare Vectorize v2 REST) | Implemented | `indexes/backends/vectorize.py` |
| `MiniLMEmbedder` (local ONNX, 384-dim) | Implemented | `embedding/providers/minilm.py` |
| `HippoRAGBackend`, `PageIndexBackend` | Experimental stubs | `indexes/backends/` |
| `HybridSearcher` (RRF fusion) | Implemented | `search/hybrid.py` |
| `Reranker` (Cohere, BGE) | Implemented | `search/reranker.py` |
| `MultiIndexSearcher` | Implemented | `search/multi_index.py` |
| `QueryExpander`, `HyDE` | Implemented | `search/transforms/` |
| Backend router + stub | Implemented | `search/_stub.py` |
| `ParserRegistry` + PDF/DOCX/HTML/MD/CSV/text parsers | Implemented | `ingestion/` |
| OCR providers (Tesseract, Azure DI) | Implemented | `ingestion/ocr/` |
| Chunkers: Chonkie Semantic (default) + Token via `ChunkerBackend`; legacy Fixed/Recursive/Sentence/Sliding/Semantic | Implemented | `chunking/`, `ingestion/chunkers/` |
| `RetrievalBackend` Protocol + `RetrievalResult` | Implemented | `retrieval/backend.py` |
| `PgvectorBackend` (default retrieval) | Implemented | `retrieval/pgvector.py` |
| `LightRAGBackend` (env-selected upgrade) | Implemented | `retrieval/lightrag.py` |
| Retrieval registry (`DIGISEARCH_RETRIEVAL_BACKEND`) | Implemented | `retrieval/registry.py` |
| `FastAPI` server | Implemented | `server.py` |
| MCP server (`FastMCP`) | Implemented | `mcp_server.py` |
| CLI (Typer) | Implemented | `cli.py` |
| Orchestrator tool manifest + dispatch | Implemented | `orchestrator_tools.py` |
| Agent LangGraph pipeline (`plan → retrieve → aggregate`) | Implemented (optional `[agent]` extra) | `agent/pipeline.py` |
| Agent citations helper | Implemented | `agent/citations.py` |
| Crossref discovery | Implemented | `discovery/crossref.py` |
| Bulk ingest worker | **Placeholder** — logs and exits | `ingest_worker.py` |
| Canonical filesystem ingest (`ingest_source` / `ingest_paths`) | Implemented | `pipeline/ingest.py` |
| Embed pipeline factory (`resolve_embedding_pipeline`) | Implemented | `embedding/factory.py` |
| HTTP client helpers | Implemented | `http_client.py` |
| EDGAR dev corpus exporter | Implemented (dev/test) | `dev/edgar_sample_export.py` |

**Critical gap:** The bulk ingest worker (`digisearch-worker`) is a shell — it logs "no queue loop yet" and exits. All production ingest runs synchronously through `POST /ingest` on the query-serving FastAPI process.

---

## 3. API Surface

### REST Endpoints

All paths under the FastAPI app in `server.py`. Base URL: `http://digisearch:8002`.

#### `GET /health` and `GET /healthz`

Public (no auth). Both endpoints are rate-limit-exempt. `/health` returns `{"status": "ok", "service": "digisearch"}` (legacy, kept for back-compat). `/healthz` returns `{"ok": true}` — the preferred liveness probe for load balancers and k8s (see AGENTS.md "Liveness vs status"). Used by Docker healthcheck and digigraph startup dependency.

**Gap:** Does not probe backend connectivity. A backend can be offline and both endpoints return 200. See [Redesign Recommendations](#12-redesign-recommendations).

#### `GET /azure_status`

Returns Azure AI Search configuration and reachability status. Calls `get_document_count()` to verify the connection. Requires `digisearch:query` scope via `DigiAuthMiddleware` (`digikey.integrations.service_middleware.digisearch_path_scopes`).

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
| `mode` | `str` | `keyword` \| `vector` \| `hybrid` (validated). Backend capability hint — see [query.mode semantics](#querymode-semantics) |
| `filter` | `str?` | Raw OData — rejected (HTTP 400) unless the index config sets `allow_raw_filter: true` |
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

Response includes `backend` field: `vectorize` | `azure_ai_search` | `chroma` | `stub`.

#### `POST /ingest`

Auth required (`digisearch:ingest` scope). Rate limited: 30 req/min per IP.

```
Request:  IngestRequest { source: str, index_name: str, doc_type: str?, metadata: dict? }
Response: IngestResponse { doc_id, chunks_created, index_name, status }
```

Ingest pipeline: delegated to `digisearch.pipeline.ingest.ingest_source`
(parse → sidecar YAML → merge metadata → chunk via `get_ingest_chunker` /
`SegmentAwareChunker` → **embed** via
`EmbeddingCache → BatchEmbedder → EmbeddingProvider` from
`embedding.factory.resolve_embedding_pipeline` → `route_add_chunks`).
Pass an explicit `embedding_provider=` to override; set `DIGISEARCH_EMBED=0` to
skip the pipeline-level step (backends may still embed). Explicit provider
config that cannot load raises — never a silent no-op. Chunker selection (no
code change): `DIGISEARCH_CHUNKER=semantic|token|recursive|fixed`, or per-index
YAML `chunker:` via `DigiSearchConfig`.

**Critical gap:** `source` is a **filesystem path** on the server. The caller must ensure the path is accessible from inside the container. URL ingest is a separate, SSRF-guarded route — `POST /ingest/url`, below.

#### `POST /ingest/url`

Auth required (`digisearch:ingest` scope; the `/ingest` path prefix covers this
route). One URL per request.

```
Request:  IngestUrlRequest { source_url: str, index_name: str = "default", metadata: dict? }
Response: UrlIngestResult { doc_id, chunks_created, index_name, source_url, final_url, extractor }
```

`pipeline/url_ingest.py` validates with digifetch's `validate_fetch_url` (SSRF
guard; operator hatch `DIGISEARCH_FETCH_ALLOWED_HOSTS`), fetches via
`HttpFetcher`, extracts markdown (`web_search.extractor`: trafilatura →
readability), stages it as a temp `page.md`, and delegates to the same
`pipeline.ingest.ingest_source` filesystem path. `text/*` and
`application/xhtml+xml` only. Error mapping: blocked/malformed URL → 400,
download too large → 413, unsupported content type → 415, empty extract → 422,
other ingest failures → their `IngestError.http_status`.

#### query.mode semantics

`Query.mode` / `QueryRequest.mode` is retained as a **validated capability hint**
(`keyword` | `vector` | `hybrid`). Invalid values are rejected (HTTP 400 /
CLI exit 2).

| Backend | Behavior |
|---------|----------|
| Chroma / Vectorize / stub | ANN (or substring for stub) only. `keyword` and `hybrid` **coerce to `vector`**; the server logs `requested_mode` → `effective_mode`. |
| Azure AI Search | Text BM25 (`query_type=simple`, or `semantic` when the index config names a semantic configuration). Native Azure vector / hybrid query types are **not** selected from `mode` today — Azure still runs keyword/semantic text search for all three values. |

This matches the historical passthrough contract without removing the field from
OpenAPI / MCP / CLI. Callers that need true BM25+vector fusion on Chroma must
wait for a higher-level `HybridSearcher` wire-up (out of scope here).

#### `GET /indexes`

Lists stub index names. Only meaningful when `DIGISEARCH_ALLOW_STUB=1`.

#### `GET /indexes/{name}`

Returns chunk count for named stub index.

#### `DELETE /indexes/{name}/documents/{doc_id}`

Returns HTTP 501. Per-document delete is not implemented.

#### `POST /v1/orchestrator_tools`

Auth required (`digisearch:query` scope). Rate limited: 30 req/min.

Returns OpenAI-style tool definitions for digigraph orchestration. Accepts optional `index_config` body to specialize tool schemas (filterable_fields, facetable_fields, result_metadata_fields).

Returns the tool manifest (the Phase C monitor and Phase D webset tools are
unconditional — the OSS legs need no key):
- `digisearch` — standard search with pagination
- `digisearch_fetch_all` — auto-paginating fetch of full result sets
- `web_search` — public web search (searxng→ddgs, fetch + extract enriched; #3853)
- `digisearch_monitors_trigger` — run one watch turn now (`watch_id`, optional `mode`; #4065)
- `digisearch_monitors_runs` — page one watch's run history (`watch_id`, `limit`, `cursor`; #4065)
- `digisearch_websets_create` — create a verified + enriched dataset, async (`query`, `count`, `criteria`, `enrichments`, `verification_mode`; #4066)
- `digisearch_websets_get` — webset status + verified/pending/rejected counts (`webset_id`; #4066)
- `digisearch_websets_add_search` — attach a follow-up search generation (`webset_id`, `query`, `count`; #4066)
- `digisearch_websets_list_items` — page items newest-first (`webset_id`, `verification`, `limit`, `cursor`; #4066)
- `digisearch_websets_events` — tail the append-only event log oldest-first (`webset_id`, `after`, `limit`; #4066)
- `digisearch_websets_export` — export verified items as CSV/JSON (`webset_id`, `format`; #4066)
- `digisearch_research_delegate` — composite research turn (only when `digisearch[agent]` is installed)
- `digisearch_web_search` — EXA live web search (only when `EXA_API_KEY` is set)

The webset entries are advertised unconditionally because the OSS verify/enrich
path has no key gate; `create`/`get`/`items`/`events` are also available over MCP
under the unprefixed `websets_*` names (see § MCP Tools). The two `#4066` halves
are wired as three parts (R12): the `TOOL_DIGISEARCH_WEBSETS_*` constants +
`ORCHESTRATOR_TOOL_NAMES`, the manifest entries above, and the
`if tool == "digisearch_websets_…"` dispatch branches in
`api_orchestrator_invoke` — a manifest entry without the dispatch branch is a
400 `Unknown orchestrator tool` at invoke time.

#### `POST /v1/orchestrator_invoke`

Auth required (`digisearch:query` scope). Rate limited: 10 req/min.

Dispatches one named tool: `digisearch`, `digisearch_fetch_all`, `digisearch_research_delegate`, `web_search`, or the monitor/webset tools above. The hub calls this to execute search without importing digisearch Python code directly. Webset dispatch failures are `ok=false` with the stable code in `error` (`code: message`) — never a 4xx — so a missing webset or invalid criteria stays readable to the hub.

#### `POST /v1/research_turn`

Auth required. Rate limited: 10 req/min.

Directly invokes the internal LangGraph pipeline (`plan → retrieve → aggregate`, or the web branch `plan → web_retrieve → web_aggregate` when `source` is `web`/`auto`). Requires `digisearch[agent]` install. Returns `{service, error, trace, query, index_name, total, backend, results, rag_sources, formatted_context, web_output, cost_dollars, usage}` — the three web fields are `null` on the corpus path.

Request: `ResearchTurnRequest {user_message, index_name, top_k, mode, filter?, filters?, session_id?, workspace_id?, source ("corpus"|"web"|"auto", default "corpus"), effort ("fast"|"thorough", default "fast"), output_schema?, cited_top_n?}`. Raw `filter` is rejected (HTTP 400) unless the index config sets `allow_raw_filter: true`. When `workspace_id` is set it is injected as a mandatory `workspace_id eq …` structured filter into the retrieve step, identical to `POST /query` (#3909).

##### Web research branch (OSS synthesis, #4064 Phase B)

`source="web"|"auto"` is an explicit opt-in: only those turns run the web
branch, and `source` defaults to `"corpus"`. The corpus path is untouched and
keeps its tool-only posture, so the #3859 "grounding is tool-only — no
synthesis-model traffic on web-grounded segments" policy remains in force for
every existing caller (including the digigraph delegate default); it is
**superseded only for explicitly requested web turns** (R5). No new port and
no new service: the branch rides `POST /v1/research_turn`, MCP
`digisearch_research_turn` (`source`/`effort` only — `output_schema` is
deferred, R7) and the orchestrator `digisearch_research_delegate` manifest
(`source`/`effort`/`output_schema`).

```
web_retrieve    search_web (landed searxng→ddgs failover) → fetch_markdown
                (never ingest_url: fetched pages are never indexed, R3) →
                chunk (get_document_chunker) → BM25 filter (optional) →
                BGE rerank → cited hits [{url,title,snippet,score,engine}]
                + cited pages stored on the state (web_pages)
web_aggregate   digillm synthesis over the cited pages handed back in
                (pages= seam — never a second search/fetch/rank round)
                  markdown path    grounded_answer → answer with inline [n]
                  structured path  structured_synthesis → json_schema wrapper
                                   {content:<output_schema>, grounding:[…]}
                                   → verify_grounding
                → WebSearchData envelope + TurnUsage
```

- **Envelope split (R1):** retrieval rows stay the landed
  `WebSearchResponse`/`WebSearchResult` (`{url,title,snippet,score,engine}`);
  the synthesis envelope is the landed `web_exa.WebSearchData`
  (`{results, output, search_type, cost_dollars}`). Synthesis returns
  `(WebSearchData, TurnUsage)` tuples — usage never rides `model_extra`.
- **`WebSearchData` interchange (EXA stays a drop-in paid alternative):**

| `WebSearchData` field | EXA (`/v1/digisearch_web_search`) | OSS web branch (#4064) |
|-----------------------|-----------------------------------|------------------------|
| `results` | EXA hits (`{title,url,highlights[]/text,…}`) | cited web hits `{title,url,snippet,score,engine}` (`snippet`, never `highlights`) |
| `output` | `{text, structured, grounding}` | markdown: `{text}`; structured: `{content, grounding[{field,citations[{url,title,excerpt}],confidence}], text}` |
| `search_type` | `instant`\|`fast`\|`auto`\|`deep-lite`\|`deep`\|`deep-reasoning` | `web-fast` \| `web-thorough` |
| `cost_dollars` | metered dollars (e.g. `{total: 0.012}`) | `{total: 0.0, provider: "web-oss", breakdown, note}` — advisory-only |

  `format_web_results` renders EXA `highlights`/`text`; OSS `snippet` rows
  therefore degrade to Title/URL-only lines (never a crash), which is why the
  turn's `formatted_context` is built directly from the hits instead.
- **Turn output:** `backend="web-oss"`; `results` are the normalized cited
  hits with `metadata.evidence_tier="External"`; `rag_sources` are built
  through `_web_hit_to_rag_row()` so the corpus citation shape stays intact;
  `formatted_context` is numbered `[n] url — title — snippet` lines built
  directly — NOT via `format_web_results`, which renders Title/URL-only for
  OSS `snippet` keys (no `highlights`/`text` keys). The new response fields
  `web_output`, `cost_dollars`, `usage` are declared on `ResearchTurnOutput`
  and are `null` on the corpus path (R10).
- **Insufficient sources:** when synthesis returns no usable `[n]` citation,
  `grounded_answer` answers with the literal `insufficient sources` plus the
  numbered source list; `verify_grounding` keeps an entry whose citations do
  not point at the retrieved set, flagged `confidence="unverified"`.
- **Effort presets** (`WebResearchConfig`; R9 — an explicit request
  `cited_top_n` wins over the preset, and `live_top_n` is search intent
  clamped to the landed `max_results` bound of 10):

| Effort | `live_top_n` | `fetch_top_n` | `cited_top_n` |
|--------|--------------|---------------|---------------|
| `fast` (default) | 8 | 5 | 5 |
| `thorough` | 20 | 10 | 8 |

- **Accounting keys (advisory-only, T2/T5):** `usage` is
  `TurnUsage{searches, pages_fetched, pages_cited, llm_calls, search_ms,
  fetch_ms, rerank_ms, synthesis_ms, total_ms}`; `cost_dollars` is
  `{total: 0.0, provider: "web-oss", breakdown{searches, pages_fetched,
  llm_calls}, note}` and `WebSearchData.search_type` is `"web-<effort>"`.
  **`total` MUST NOT drive budget/routing gates alone** — OSS synthesis has
  no metered per-call dollar cost and LLM spend is metered in digillm
  telemetry, never folded in (the `note` says exactly that).
- **Ops notes:** `DIGISEARCH_SYNTHESIS_MODEL` must be set to a digillm model
  id or every web turn fails hard with `WebResearchError` (never an uncited
  answer). The branch requires the `[rerank]` extra (sentence-transformers
  BGE); the default `get_document_chunker()` semantic path additionally
  requires `[ingestion]` (`chonkie[semantic]`). Either missing raises
  `WebResearchError`. `DIGISEARCH_RERANK_ENABLED` does **not** gate the web
  branch — it gates `query_index()`'s rerank only (#2441) — and the branch
  hardcodes `Reranker(provider="bge", strict=True)`, so
  `DIGISEARCH_RERANK_PROVIDER` does not change it.
- **Single retrieval round (`pages=` seam, #4084):** a web turn runs exactly
  one search/fetch/rank round. `node_web_retrieve` does the retrieval and
  stores the cited pages on the turn state (`web_pages`, serialized
  `FetchedPage` dicts); `node_web_aggregate` rebuilds them and passes them
  through the synthesis monoliths' optional `pages=` argument, which skips
  `_live`/`_fetch`/`_rank` entirely (standalone callers that omit `pages` keep
  the live retrieval loop). `usage` therefore counts only what ran: the
  retrieval round's `searches=1`/`pages_fetched`, `pages_cited` from the cited
  set, and the synthesis `llm_calls` — nothing double-counted or dropped.
  Because `results`/`formatted_context` and the answer's `[n]` numbering are
  built from the same ranked set, they stay aligned (the pre-#4084 divergence
  note no longer applies).
- **Eval:** `tests/ds/test_web_eval_live.py` runs `grounded_answer` plus one
  `structured_synthesis` per `RESEARCH_CASES` case (extended landed module
  `digisearch/tests/web_search_eval_cases.py`), mocked offline by default;
  the shared `DIGISEARCH_WEB_SEARCH_LIVE=1` gate runs the live-sampled leg
  and prints p50 stage ms + citation coverage. Live dollar/latency numbers
  are single-key, single-day scaffolding anchors — never SLO constants.

Phase B live verification record (2026-09-15, #4064 Task 6 — not measured,
prerequisites absent in this env):

- Live legs: **not measurable here.** `DIGISEARCH_WEB_SEARCH_LIVE=1 pytest
  tests/ds/test_web_eval_live.py -k live -x` reached the real network on the
  ddgs fallback (no searxng sidecar: `127.0.0.1:8080` connection refused)
  and fetched/extracted live pages (trafilatura), then failed hard —
  correctly — at `_rank`: `WebResearchError: web chunking is unavailable:
  chonkie[semantic] is required`. `sentence-transformers` (`[rerank]`) and
  `DIGISEARCH_SYNTHESIS_MODEL` (+ any digillm provider key) are also absent
  in this env. Prerequisites cannot be installed into the shared venv, so
  fast/thorough p50 and citation coverage remain unmeasured; re-run the gate
  in a provisioned env and record date/key tier before writing any SLO from
  the numbers.
- Offline evidence on this branch: `pytest tests/ds/test_web_eval_live.py -v`
  → 4 passed, 2 skipped (live legs), zero `Traceback`. All 12 research cases
  produce line-cited answers, cited structured fields, and full
  `usage`/`cost_dollars` envelopes.
- EXA-paid path untouched: `POST /v1/digisearch_web_search` stays EXA-gated
  (no `EXA_API_KEY` ⇒ 503 / disabled string); `tests/ds/test_web_exa.py`
  passes on this branch.

#### `POST /v1/web_search`

Auth required (`digisearch:query` scope via the default `digisearch_path_scopes` fallthrough). Rate limited: 30 req/min (default bucket).

Proprietary web search (#3853). Request `WebSearchRequest {query, include_domains (max 5), exclude_domains (max 20), max_results (1–10, default 4), recency_days (1–365, default 7; mapped onto provider recency filters — searxng day/month/year with a week mapping to month — omitted when null)}`; response `WebSearchResponse {query, results [{url, title, snippet, score, engine}], provider}`. `run_web_search` tries the searxng sidecar first, fails over to embedded ddgs (`DIGISEARCH_WEB_SEARCH_BACKEND=auto|searxng|ddgs`, sidecar URL from `DIGISEARCH_SEARXNG_URL`), then enriches up to `fetch_max_pages` (default 3) hits by fetching via composed digifetch (`HttpFetcher` + `with_retry` + `RateLimiter`) and extracting markdown (trafilatura primary with `favor_precision` + `deduplicate`, readability fallback). The fetch is SSRF-guarded by digifetch (#3934): http/https only, internal/metadata addresses refused, and every redirect hop re-validated (no auto-follow) with the operator `DIGISEARCH_FETCH_ALLOWED_HOSTS` allowlist as the explicit escape hatch. Fetch/extract failures keep the original search snippet — enrichment never fails the response. Provider failures (429 / 5xx / connection / timeout) are soft in-envelope errors (#4192): HTTP 200 `WebSearchErrorResponse {ok: false, error, retryable, status_code}` (`status_code` null when the provider exposed none; a ddgs rate limit maps to 429) — never a 500. `retryable`/`status_code` surface throttling distinctly so callers can back off; the orchestrator `web_search` tool mirrors the same hints on `OrchestratorInvokeResponse`. No new port: served by the existing digisearch HTTP app.

#### Optional EXA live web search (`digisearch/web_exa.py`)

Thin wrapper over the EXA neural web-search API (https://exa.ai) — an *alternative*
retrieval path for the live web, never mixed into owned-corpus results. **Dormant by
default:** every entry point fails closed without `EXA_API_KEY` (503 / disabled string /
`ok=False`). No new dependencies (`httpx` only); no env reads at import time.

| Surface | Shape |
|---------|-------|
| `POST /v1/digisearch_web_search` | `search_type` instant\|fast\|auto\|deep-lite\|deep\|deep-reasoning, `category`, `contents_text`, `output_schema`, `system_prompt` → `WebSearchData{results, output, search_type, cost_dollars}` (mounted here — not `/v1/web_search` — because the first-party search above owns that route) |
| `POST /v1/web_contents` | Known-URL fetch (`text`/`highlights`/`summary`) |
| `POST /v1/web_answer` | Grounded answer with citations |
| Orchestrator `digisearch_web_search` | Advertised in the manifest only when `EXA_API_KEY` is set; dispatched via `POST /v1/orchestrator_invoke` |
| MCP `digisearch_web_search` | `query`, `search_type`, `num_results`, `category`, `offset` → formatted text. `offset` pages the recall set (client-side slice of one enlarged window, `numResults = offset + num_results`, because EXA `POST /search` has no offset); cap `EXA_MAX_RESULTS` = 100 pinned by the monitors 1-100 bound; a page reaching past the cap errors explicitly (never a silent truncated page) and a page past the query's result count returns an explicit empty page (#4234) |

Auth: same `digisearch:query` scope via `DigiAuthMiddleware` (default path rule; no digikey change).

#### Phase C monitors (`/v1/monitors`, #4065)

Scheduled web-search watches: create a watch (query + schedule + dedup rule +
delivery config), let the runner recall and dedup results, then read the
canonical run history or receive delivery. One store, one runner, one envelope —
the recall leg is `digisearch.web_exa.exa_search` whenever `EXA_API_KEY` is
configured and the OSS seam otherwise, and the `backend` a watch declares is
recorded on each of its runs. Monitors are off end-to-end for the `datatap`
workspace: create/update reject it and the tick skips it.

##### Monitor HTTP routes

All routes below are auth-gated through the local `_digisearch_path_scopes`
wrapper, which delegates everything except the webhook back to the landed
`digisearch_path_scopes` — the monitor paths hit its `digisearch:query`
fallthrough, so CRUD is **not** `digisearch:ingest` (R1, no digikey change).
Rate limits are per-IP (R10): CRUD and runs 30/min, trigger / tick / exa_webhook
10/min.

| Method + path | Success | Error codes | Notes |
|----------------|---------|-------------|-------|
| `POST /v1/monitors` | 201 `{"watch": …, "delivery_secret": …}` | config codes (422), `exa_schedule_unsupported` / `exa_webhook_target_missing` (422), `exa_webhook_secret_missing` / `exa_monitor_id_missing` / `exa_api_error` (502) | Validated before persistence; the one-time secret is in this response only (R8). `backend="exa"` is provisioned remote-first (#4184): the remote monitor is created first (interval period mapped exactly; a webhook delivery target is required), its one-time `webhookSecret` becomes the watch secret, and the watch is persisted with `exa_monitor_id` only after EXA answered — nothing is stored when provisioning fails, and a local persist failure compensates by deleting the remote |
| `GET /v1/monitors` | 200 `{"watches": [...]}` | — | Optional `?workspace_id=` filter |
| `GET /v1/monitors/{watch_id}` | 200 `Watch` | `watch_not_found` (404) | Never returns the secret |
| `PATCH /v1/monitors/{watch_id}` | 200 `Watch`, or `{"watch": …, "delivery_secret": …}` when rotating | `watch_not_found` (404), `validation_error` / config codes (422), `watch_backend_immutable` (409), `monitor_exa_monitor_id_immutable` (409), `exa_secret_rotate_unsupported` (409) | Partial patch; merging is top-level (a nested object replaces the whole nested object). `backend` is create-time only: a patch naming a different value is refused 409 `watch_backend_immutable` (a same-value `backend` is a no-op), closing both the `oss→exa` claim-without-monitor and the `exa→oss` orphan direction. `exa_monitor_id` is server-owned too: a patch naming a different value — including `null` — is refused 409 `monitor_exa_monitor_id_immutable` (a same-value `exa_monitor_id` is a no-op), so the stored remote link cannot be cleared to bypass the DELETE teardown nor replaced with another watch's id to aim it elsewhere. Rotation is refused for any watch backed by a remote EXA monitor — `backend="exa"` or a non-null `exa_monitor_id` — because its secret is EXA's per-monitor `webhookSecret`, so a locally minted replacement would break signature verification; re-create the watch to rotate |
| `DELETE /v1/monitors/{watch_id}` | 200 `{"deleted": watch_id}` | `watch_not_found` (404) | A `backend="exa"` watch carrying an `exa_monitor_id` first tears its remote monitor down best-effort (`delete_exa_monitor`); a remote failure is logged and swallowed so the local delete still succeeds. OSS watches make no adapter call. Runs are retained |
| `POST /v1/monitors/{watch_id}/trigger` | 201 `MonitorRun` | `watch_not_found` (404) | Body `{"mode": "manual"\|"poll"}` (default `manual`); a failed turn still returns its persisted `status="failed"` run rather than a 5xx |
| `GET /v1/monitors/{watch_id}/runs` | 200 `{"runs": [...], "next_cursor": …}` | `run_not_found` (404, unknown cursor) | `limit` 1–100 (default 20); `cursor` is the last `run_id` of the previous page |
| `GET /v1/monitors/{watch_id}/runs/{run_id}` | 200 `MonitorRun` | `run_not_found` (404) | — |
| `POST /v1/monitors/tick` | 200 `{"runs": [...]}` | — | Runs every due + enabled watch once (digiclaw wake-up clock, §4.8) |
| `POST /v1/monitors/exa_webhook` | 201 `MonitorRun` (200 `{"acknowledged": true}` for a non-terminal delivery; 200 stored run for a duplicate delivery) | `exa_bad_signature` (401), `exa_payload_invalid` (400/422), `exa_monitor_id_missing` (422), `watch_not_found` (404), `watch_backend_mismatch` (409) | Auth-exempt but per-watch-secret-gated: the delivery's `exa-signature` (`t=<unix>,v1=<hex>`, `HMAC-SHA256(per-monitor webhookSecret, f"{t}.{body}")`, ±300 s) is verified with the resolved watch's stored secret (`get_delivery_secret`); a valid signature translates the nested event envelope through the live-pinned (#4123) EXA adapter and persists the canonical run (watch resolved by `data.monitorId` → `exa_monitor_id`, datatap excluded). Any parseable non-terminal run status (`running`, `cancelled`, `queued`, …) acks without a run row — EXA retries non-2xx indefinitely; a redelivered terminal run answers 200 with the stored run, never 409 |

| Error code | HTTP | Raised by |
|------------|------|-----------|
| `datatap_monitors_disabled` | 422 | `workspace_id="datatap"` on create/update (tick also skips it) |
| `timezone_unknown` | 422 | `schedule.timezone` does not resolve via `ZoneInfo` |
| `invalid_cron` | 422 | `digiclaw.cron.parse_cron` rejects the 5-field expression |
| `webhook_url_required` / `slack_url_required` | 422 | Non-`poll` delivery with no targets, or a webhook/slack target with no URL |
| `webhook_url_private` / `slack_url_private` | 422 | Target URL is not https, carries userinfo, or resolves (or fails to resolve) to a non-global address |
| `validation_error` | 422 | `PATCH` body fails `Watch` re-validation |
| `watch_not_found` / `run_not_found` | 404 | Unknown watch, run, or pagination cursor |
| `run_exists` | 409 | Duplicate `run_id` (store-level; internal) |
| `exa_bad_signature` | 401 | Missing watch delivery secret, missing `exa-signature`, malformed/stale/future `t`, or HMAC mismatch — fail closed |
| `exa_payload_invalid` | 400/422 | Webhook body is not valid JSON (400), not a JSON object (422), or is not the pinned nested event envelope / carries a missing-or-blank run `status` or a malformed `data.output.results` container (422) |
| `exa_monitor_id_missing` | 422 / 502 | Webhook route: the nested run has no `monitorId` — the target watch cannot be resolved (422). EXA watch create: the remote answer carried no `id`, so the watch cannot be linked (502, nothing persisted) |
| `exa_run_status_unknown` | — (adapter) | `exa_run_to_monitor_run` called directly with a non-terminal run status; the webhook route acks every parseable non-terminal status 200 without persisting, so it never reaches translation |
| `exa_schedule_unsupported` | 422 | EXA watch create: `schedule.mode="cron"` (EXA interval triggers cannot express a cron), or `interval_seconds` not exactly divisible by 86400/3600/60 — EXA periods are exact units (`"1d"`/`"1h"`/`"1m"`) only, never rounded |
| `exa_webhook_target_missing` | 422 | EXA watch create: no delivery target of kind `webhook` with a non-blank URL — EXA returns a `webhookSecret` only for a webhook-bound monitor |
| `watch_backend_immutable` | 409 | `PATCH` naming a `backend` different from the watch's current one — the backend is fixed at create (a same-value `backend` is a no-op); delete and re-create the watch to change it |
| `monitor_exa_monitor_id_immutable` | 409 | `PATCH` naming an `exa_monitor_id` different from the watch's current one — including a `null` clear or another watch's id — the remote-monitor link is server-owned and fixed at provisioning (a same-value `exa_monitor_id` is a no-op); delete and re-create the watch to change it |
| `exa_secret_rotate_unsupported` | 409 | `PATCH {"rotate_delivery_secret": true}` on a watch backed by a remote EXA monitor (`backend="exa"` or a non-null `exa_monitor_id`) — its secret is EXA's per-monitor `webhookSecret`; re-create the watch to rotate |
| `exa_webhook_secret_missing` | 502 | EXA watch create: the remote answer carried no non-blank `webhookSecret`; the just-created remote monitor is best-effort deleted and nothing is persisted |
| `exa_api_error` | 502 | EXA watch create: any `ExaAdapterError` other than `exa_request_invalid` (upstream/transport/key failure); the watch is not persisted |
| `exa_request_invalid` | 422 | EXA watch create: local caller input the adapter rejects (blank query/schedule). Every other adapter failure maps to 502 `exa_api_error` |
| `watch_backend_mismatch` | 409 | The webhook-resolved watch is not `backend="exa"` (misconfiguration; nothing persisted) |
| `exa_not_configured` | — (adapter; 502 `exa_api_error` at watch create) | EXA adapter create/delete: no explicit key and no `EXA_API_KEY` — the EXA monitor backend is disabled (never a silent OSS fallback) |
| `exa_tier_gated` | — (adapter; 502 `exa_api_error` at watch create) | EXA adapter create/delete: EXA answered 401/403 (paywall / unauthorized key tier) — fail closed |

Custom codes ride the shared digibase envelope — read `body["error"]["code"]`,
never a top-level `body["code"]`. Validation messages are EXA-identical:
`[webhook]: Required`, `[webhook.url]: Webhook URL cannot point to localhost,
.local domains, or private IP addresses`.

**EXA live pin (#4123, observed 2026-09-16, real key).** The monitors family is
reachable on the operator's key tier (no 401/403 on create/list/get/trigger/
runs/delete; the Websets family stays Pro-gated). Pinned remote shapes: create
is `POST /monitors` with `{"search": {"query"}, "trigger": {"type": "interval",
"period": "1d"}, "webhook": {"url"}}` → 201 with the created document plus a
one-time 32-char `webhookSecret` (list/get omit it); list is `{"data",
"hasMore", "nextCursor"}`; trigger → 200 `{"triggered": true}`; runs are
paginated run objects (`id/monitorId/status/output/failReason/startedAt/
completedAt/failedAt/cancelledAt/durationMs/createdAt/updatedAt`); delete →
200 with the monitor object (not 204). Webhook deliveries are the NESTED
envelope `{"id": "event_…", "object": "event", "type":
"monitor.run.created" | "monitor.run.completed", "data": {<RUN>},
"createdAt": …}` — the run lives under `data`, there is no `newResults` key on
the wire, and non-terminal events are delivered (hence the 200 ack).
Completed-run `output` is `{"results": [...], "content": "<answer with [n]
markers>", "grounding": [...]}`; a terminal `completed` run maps
`results_all = results_new = output.results` (empty ⇒ `no_change`). The
signature is `exa-signature: t=<unix>,v1=<hex>` with `v1 =
HMAC-SHA256(webhookSecret, f"{t}.{body}")` (Stripe-style, live-verified 4/4),
so verification needs the watch's stored per-monitor secret — there is no
shared static secret. EXA's own URL validator additionally rejects reserved
documentation domains (`https://example.com/...` → 400 `[webhook.url]: …
localhost, .local domains, or private IP addresses`; `https://httpbin.org/post`
is accepted); the stricter local `validate_delivery` SSRF gate is unchanged —
EXA's extra rule is theirs. Evidence: `.superpowers/sdd/4123-exa-shape-pin/
{spike-output-3,signature-check}.txt`.

**Secret contract (R8).** Create returns the per-watch delivery secret once as
`{"watch": …, "delivery_secret": …}`; on the OSS path it is a server-minted
`secrets.token_hex(32)`, and on the EXA path it is EXA's one-time per-monitor
`webhookSecret`, captured by the remote-first create (#4184). `PATCH
{"rotate_delivery_secret": true}` mints a fresh one in the same shape and
rotates only on the literal `true` (truthy strings/numbers do not); rotation is
refused 409 `exa_secret_rotate_unsupported` for any watch backed by a remote
monitor (`backend="exa"` or a non-null `exa_monitor_id`), whose secret must keep
matching EXA's signature — re-create the watch to rotate. The
secret lives in a dedicated nullable `secret` column, never in the watch body,
so `GET`/list reads and stored run bodies are secret-free.

**EXA provisioning (#4184).** `POST /v1/monitors` with `backend="exa"` goes
through `monitors/provisioning.py` and is remote-first + fail-closed: the
schedule must be an interval whose seconds are exactly divisible by
86400/3600/60 (→ `"Nd"`/`"Nh"`/`"Nm"`; a cron or inexact interval is 422
`exa_schedule_unsupported`), the watch must carry a webhook delivery target
(422 `exa_webhook_target_missing` — EXA returns a `webhookSecret` only for a
webhook-bound monitor), and `create_exa_monitor` runs before anything local is
written. A remote answer without a non-blank `webhookSecret` (502
`exa_webhook_secret_missing`) or `id` (502 `exa_monitor_id_missing`), and any
other adapter failure (502 `exa_api_error`; `exa_request_invalid` stays 422),
persists nothing and best-effort deletes the just-created remote monitor; a
local persist failure also deletes the remote monitor before the original error
is re-raised, so a broken store cannot orphan a monitor. The stored watch
carries `exa_monitor_id`, and the inbound webhook verifies against the remote
secret with no out-of-band `set_delivery_secret` step.

**Backend transitions (#4196).** The backend is create-time only: `PATCH
/v1/monitors/{watch_id}` naming a `backend` different from the watch's current
one is 409 `watch_backend_immutable`, so an `exa` watch can never be flipped
into a local watch that orphans its remote monitor and an OSS watch can never
claim `backend="exa"` without a remote monitor behind it. `exa_monitor_id` is
server-owned alongside it: a `PATCH` naming a different value (including
`null`, or another watch's id) is 409 `monitor_exa_monitor_id_immutable`, so
the DELETE teardown below can be neither skipped by clearing the link nor aimed
at another watch's remote monitor; a same-value `exa_monitor_id` is a no-op.
The rotation guard is keyed on remote presence (`backend="exa"` **or** a
non-null `exa_monitor_id`), so even a misconfigured watch — an `exa_monitor_id`
left on an OSS row — cannot mint a local secret that no longer matches EXA's
signature. `DELETE
/v1/monitors/{watch_id}` tears the remote monitor down best-effort first
(`delete_exa_monitor` with the stored id; failures `logger.warning`-logged and
swallowed), then deletes the local row — the response stays `{"deleted":
watch_id}` and OSS watches make no adapter call.

**Delivery (R13).** Fan-out happens only for `status="ok"` runs whose watch
delivery mode is not `poll`. Webhook/slack targets receive the exact
`MonitorRun` JSON body with `X-digi-signature: sha256=<hmac_sha256(secret,
body)>`; retries are 2 attempts with linear backoff (`0.5s`) and only transport
errors, 5xx, and 429 are retried — any other 4xx is definitive after one
attempt. Email targets go over the `DIGISEARCH_SMTP_*` relay (STARTTLS verified;
login never crosses a cleartext connection). Every target yields exactly one
`DeliveryReceipt` (`{target_kind, ok, status_code?, error?}`); receipts are
returned to the caller and **not** persisted — the run log is append-only, so
stored runs keep `delivery=[]`. A delivery-enabled watch whose stored secret is
`None` fails loudly (`error="delivery_secret_missing"`, `results_all=[]` so
undelivered content never enters dedup memory) instead of skipping delivery.

**Recall path.** The runner calls the Phase B shallow recall directly
in-process (no loopback HTTP, no bearer token — R2): EXA when configured, else
`search_web` with `recency_days=None` (R5 — no silent 7-day rolling window) and
`max_results=min(num_results, 10)` (R6); the OSS leg is adapted to the canonical
`WebSearchData` payload via `_oss_response_to_data`, and the run's
`query_snapshot` records the effective `num_results` plus
`num_results_clamped_from` when the clamp applied. Storage, dedup, and tick
semantics are in §5.

#### Phase D websets (`/v1/websets`, #4066)

Async-first verified + enriched dataset building. A caller submits a query +
1-5 natural-language verification criteria + up to 10 typed enrichments; the
runner recalls candidates through the landed Phase A seam (`search_web`, query
diversification — no paging), verifies every candidate against every rule
(`fetch_markdown` page text; `llm` or offline `rules` mode), enriches admitted
items field-by-field with per-field citations, and appends events until the
webset reaches `idle`. Every route is thin over the T6 service facade
(`digisearch.websets.service`) — no pipeline logic lives in `server.py`.

**Async lifecycle.** No endpoint blocks on the build: `POST /v1/websets` and
the refresh routes return 202 and schedule the pass on the shared driver's
lifespan `asyncio.TaskGroup` (`websets/driver.py`; registry `WEBSET_TASKS`,
done-callback per run; a bare `asyncio.create_task` is never used). Both serving
entrypoints carry the same driver lifespan — the FastAPI app lifespan
(`server._lifespan`, after its backend gate) and the FastMCP server lifespan
(`mcp_server.mcp`) — so an MCP-only deployment drives its own runs (#4170).
The install window is first entry to last exit within one process,
reference-counted across concurrent lifespan invocations (#4189): FastMCP on
streamable-http (digisearch's only transport) enters the lifespan once per
client session, so overlapping sessions share the one install — installed on
the first entry, torn down on the last exit; a later window reinstalls and
re-runs the startup resume. A session's exit neither nulls the `set_scheduler`
seam nor cancels another still-active session's runs. The install guard is a
per-running-loop lock (#4202): sequential windows on fresh event loops each
install, resume, and tear down cleanly, while entering a window while an
install is active on a different loop raises `RuntimeError`. The driver installs
the scheduler on the service facade at startup (`set_scheduler`), re-schedules
the startup-resume union
(websets still `running` ∪ websets holding a non-terminal `running` search;
once per install window, not per session) as registry-tracked runs under each
webset's persisted `verification_mode`, and on shutdown undoes the seam first
and then cancels every tracked run/backfill.
`Webset.status` never goes backwards: `idle` is
sticky after the first completion, and a refresh (`add_search` /
`trigger_monitor`) runs as a new `WebsetSearch` generation observed through the
new row + events. Terminal `cancelled`/`failed` websets refuse new searches,
enrichments, and monitor triggers with `webset_terminal` (409) — a running
search appended to a terminal webset could never settle and would be
re-selected by startup resume forever.

`verification_mode` (`llm` default | `rules`) is persisted on the webset and
each search generation: `add_search` and `trigger_monitor` inherit it, so a
`rules` webset never silently switches to `llm` on a refresh. The runner's
backfill generations (`add_enrichment`) persist the inherited mode too, so a
backfill cannot reset a `rules` webset to the model default.

**Scheduled tick driver (#4221).** Each install window also runs one tick task
inside the driver's `asyncio.TaskGroup` (`WEBSET_TICK_SECONDS`, 60s default):
every pass re-reads every monitor (`store.list_all_monitors`) and refreshes
each due, unpaused monitor through the same `websets_service.trigger_monitor`
path the manual route uses — a new `WebsetSearch` generation inheriting the
persisted `verification_mode`. Due-selection is in-process schedule state owned
by the install window: `last_tick` per `(webset_id, monitor_id)`, anchored at
the first post-install sighting (a restart re-anchors every cadence instead of
stampeding refreshes), and a monitor is skipped while its webset already has a
run in `WEBSET_TASKS` (dedupe with manual triggers and prior ticks). A failed
refresh is contained per monitor (`WebsetServiceError` and broad exceptions are
logged, the pass continues and `last_tick` still moves so a doomed refresh
retries at the monitor's interval), a store that cannot be opened skips the
pass (the startup resume's tolerance), and teardown ends the loop promptly when
the stop event is set. Offline callers install no driver, so nothing ticks
there and refreshes stay explicit.
`PATCH /v1/websets/{webset_id}/monitors/{monitor_id}` flips the monitor's
`paused` flag (`{"paused": true|false}`, unknown keys rejected); a paused
monitor is skipped by the tick only — the manual trigger route still refreshes
it on demand.

**Library-only in v1.** The enricher's cross-page company merge
(`merge_company_entities` / `reconcile_funding_history` in `websets/enrich.py`)
and the spec's targeted second extraction pass (a re-fetch or follow-up
`search_web` when a field is still unresolved) have no runner caller: the
runner drives single-page `enrich_item` on the one already-fetched
`fetch_markdown` text, so a `company_profile` is built from its own item page
only and an unresolved field is not re-attempted on a second page in v1.

**Webhook delivery is wired.** `POST /v1/websets/{webset_id}/webhooks`
registers a signed target; the single event writer (`websets/events.py`
`append_event`) fans every stored event out to the webset's active, subscribed
`WebhookConfig` entries (`deliver_webhook`) after the append — one POST of
`{event, webset_id, delivered_at}` signed with the shared Phase C core
(byte-identical `X-digi-signature`), 3 attempts with the pinned 5s/25s
backoff, 429/5xx retried and any other 4xx final. Delivery state lives in the
`webhook_deliveries` ledger keyed `(webhook_id, event_id)`: per-target
failures become recorded `failed` rows and never raise out of the append path,
and the ledger turns a duplicate re-append into a no-op (no second POST).
`verify_webhook_signature` is a public helper (rotation-overlap acceptance)
for webhook consumers; it deliberately has no production caller.

**Automated re-delivery is wired (#4226).** The shared driver runs a second
scheduled task next to the tick loop: one pass per `WEBSET_REDELIVERY_SECONDS`
(300s) reads the failed, due ledger rows
(`store.list_due_webhook_deliveries` — `ok=0`, not exhausted, `next_attempt_at`
NULL or elapsed) and re-attempts each through `events.redeliver_webhook`, which
rebuilds the same `{event, webset_id, delivered_at}` body from the stored event
and reuses the one-shot POST core (3 in-call attempts, 5s/25s backoff) — always
signing with the webhook's **current** secret, so a retry after rotation lands
inside the 24h previous-secret overlap. Retries are bounded:
`_WEBHOOK_REDELIVERY_ATTEMPTS = 5` timed re-deliveries stepping the pinned
`(300, 1800, 7200, 21600)`-second ladder — the cap sits one past its four
rungs, so each wait schedules (5m, 30m, 2h, then 6h) and the fifth failure
exhausts the row (`next_attempt_at = NULL`) ≈8h35m after the first, which the
due selector never offers again — the ledger keeps a terminal failed row. A
webhook that is inactive or no longer subscribed, or a webhook/event that is
gone, is exhausted once with no POST; a
missing secret records the fail-closed `webhook_secret_missing` outcome. Success
flips the same ledger row `ok=True` (no new event append, no extra POST outside
the bounded retry). Rows are processed serially with a per-pass in-flight guard,
per-row faults are contained, and nothing re-delivers without an installed
driver. `deliver_webhook`'s one-shot semantics are unchanged: a recorded
terminal failure stays final for the append path; re-delivery is this loop
explicitly driving failed rows.

##### Webset HTTP routes

All routes are auth-gated through `DigiAuthMiddleware`; the paths hit the
landed `digisearch_path_scopes` `digisearch:query` fallthrough (no digikey
change), and errors use the shared `digibase.errors` envelope — read
`body["error"]["code"]`, never a top-level `body["code"]`. Rate limits are
per-IP via the two-tier mechanism: `/v1/websets` is an exact 10/min static;
the parameterized paths are matched most-specific-first (creation/refresh
10/min, reads/pause 30/min). `POST`+`GET` on one path share that path's budget
(`/monitors` is 10/min for both).

| Method + path | Success | Error codes | Notes |
|----------------|---------|-------------|-------|
| `POST /v1/websets` | 202 `Webset` | `invalid_criteria`, `invalid_verification_mode`, `datatap_websets_disabled` (422), `enrichment_limit_exceeded` (400) | Body `{query, count 1-100, criteria, enrichments, verification_mode, workspace_id}`; the supplied criteria are required (0 or >5 → `invalid_criteria`) |
| `GET /v1/websets/{webset_id}` | 200 `Webset` | `webset_not_found` (404) | Includes search generations + enrichment defs |
| `POST /v1/websets/{webset_id}/searches` | 202 `WebsetSearch` | `webset_not_found` (404), `webset_terminal` (409), `invalid_criteria` (422) | Missing criteria inherit the webset's |
| `GET /v1/websets/{webset_id}/items` | 200 `{"items", "next_cursor"}` | `webset_not_found` (404), `cursor_not_found` (404) | NEWEST-first; `cursor` = previous page's last item id; `verification` filter `verified\|rejected\|pending` |
| `POST /v1/websets/{webset_id}/enrichments` | 201 `EnrichmentDef` | `webset_not_found` (404), `webset_terminal` (409), `enrichment_limit_exceeded` (400) | Max 10 active; the attach schedules the backfill drain |
| `DELETE /v1/websets/{webset_id}/enrichments/{enrichment_id}` | 204 | `webset_not_found` / `enrichment_not_found` (404) | Already-resolved item values are retained |
| `POST /v1/websets/{webset_id}/monitors` | 201 `WebsetMonitor` | `webset_not_found` (404), `webhook_url_required` / `webhook_url_private` (422) | Tick-driven v1: `interval_seconds` ≥ 60 is the cadence the shared driver's tick loop honors (`paused` defaults `false`) |
| `GET /v1/websets/{webset_id}/monitors` | 200 `{"monitors": [...]}` | `webset_not_found` (404) | Newest-created first; the body carries `paused` |
| `PATCH /v1/websets/{webset_id}/monitors/{monitor_id}` | 200 `WebsetMonitor` | `webset_not_found` / `monitor_not_found` (404), `validation_error` (422) | Body `{"paused": true\|false}` (`extra="forbid"`); the tick driver skips a paused monitor, the manual trigger route does not |
| `POST /v1/websets/{webset_id}/monitors/{monitor_id}/trigger` | 202 `Webset` | `webset_not_found` / `monitor_not_found` (404), `webset_terminal` (409) | Manual refresh; the shared driver's tick loop calls this same service path |
| `GET /v1/websets/{webset_id}/events` | 200 `{"events", "next_cursor"}` | `webset_not_found` (404), `cursor_not_found` (404) | OLDEST-first append-only tail; `after` = last seen event id |
| `POST /v1/websets/{webset_id}/webhooks` | 201 `WebhookConfig` | `webset_not_found` (404), `webhook_url_required` / `webhook_url_private` / `validation_error` (422) | Secret-once: the server-generated secret is in this response; there is no read route. An unknown `events` kind maps to the 422 `validation_error` envelope, never a 500 |
| `POST /v1/websets/{webset_id}/webhooks/{webhook_id}/rotate` | 200 `WebhookConfig` | `webset_not_found` / `webhook_not_found` (404) | New secret + 24h `previous_expires_at` overlap |
| `POST /v1/websets/{webset_id}/cancel` | 200 `Webset` | `webset_not_found` (404) | Settles non-terminal searches `cancelled`; an already-`idle` webset stays `idle` (sticky) |
| `GET /v1/websets/{webset_id}/export?format=csv\|json` | 200 file (`text/csv` / `application/json`) | `webset_not_found` (404), `validation_error` (422, unknown format) | Verified items only; CSV via polars, JSON keeps per-field citations |

Store-internal invariant codes (`webset_not_settled`, `transition_invalid`,
`invalid_event_kind`, `invalid_webhook_delivery`, `event_not_stored`,
`webhook_id_required`) and the T5b ledger receipt code `webhook_secret_missing`
are never surfaced: the service facade maps them to a generic 500
`internal_error` (logged server-side with the original code).

**Store home.** `DIGISEARCH_WEBSETS_DB` → `{DIGI_WORKSPACE}/.digisearch/websets.sqlite3`
→ `./.digisearch/websets.sqlite3` (cwd fallback), resolved per request by
`websets.store.get_store`; one thread-bound `sqlite3` connection per store,
WAL + `busy_timeout=5000`, no in-process lock. The digillm model ids for
`llm`-mode verification/enrichment come from `DIGISEARCH_VERIFY_MODEL` /
`DIGISEARCH_ENRICH_MODEL` (unset ⇒ verification settles `rejected`, fail
closed; enrichment settles `unresolved`).

**EXA shim (dormant).** `websets/providers/exa_websets.py` is the paid
alternative: dormant without `EXA_API_KEY` and **not wired** into the
HTTP/MCP/orchestrator surfaces (the OSS path always runs, `backend="oss"`). It
translates create/read/refresh into `POST /websets`, `GET /websets/{id}`,
`POST /websets/{id}/searches` (base `https://api.exa.ai/websets/v0`) and maps
EXA's Pro-plan 401 to `ExaWebsetsProRequiredError(ExaError)`. Request/response
shapes are recorded in the module docstring; live Pro-key validation and
end-to-end wiring remain deferred (the vendored free-tier 401 fixture keeps
key-less CI green). Re-validating the translation against a Pro-tier key is a
**human precondition**: it requires a Pro key, has **not** been performed, and
the Phase D live record does not claim it (tracked by the #4123 live-pin
precedent).

**Deferred (explicitly out of v1).** Recall paging
(count is reached by query diversification, `max_results ≤ 10` per call) and
EXA-websets live validation + wiring (Pro key; tracked by the #4123 live-pin
precedent).

**MCP driving is wired (#4170).** Both entrypoints carry the shared
`websets/driver.py` lifespan: the FastAPI app lifespan installs it for the HTTP
serving window, and the FastMCP server lifespan (`mcp_server.mcp`) installs it
per process (stdio) or across concurrent MCP client sessions (streamable-http),
so a webset created or refreshed through the standalone MCP tools is driven
in-process through the same service facade, runner, and per-process
`WEBSET_TASKS` registry (HTTP and MCP processes stay independent). The install
is reference-counted (#4189): the first entry installs the scheduler and runs
the startup resume, later concurrent entries only bump the depth, and the last
exit tears the seam down and cancels tracked runs — one session closing never
uninstalls or cancels another session's runs.

**Phase D live verification record (2026-09-15, #4066 Task 8 — not measured,
live stack absent in this env):**

- Live leg: **not measurable here.** `DIGISEARCH_WEBSETS_LIVE=1 pytest
  tests/ds/test_websets_live.py -m unit -k live -x` fails at the harness's own
  prerequisite gate, which asserts exactly `DIGISEARCH_VERIFY_MODEL` /
  `DIGISEARCH_ENRICH_MODEL` (both unset). Separately confirmed in this env: no
  digillm provider key, no searxng sidecar (`127.0.0.1:8080` connection
  refused), and no digisearch HTTP process (`:8002`). With the model ids unset,
  verification settles every item `rejected` and enrichment settles every field
  `unresolved` (fail-closed), so a gated run here would measure nothing — the
  harness refuses it rather than recording a vacuous pass.
- How to measure: provision a search backend + `DIGISEARCH_VERIFY_MODEL` /
  `DIGISEARCH_ENRICH_MODEL` + a provider key, then run the gated command above.
  It drives the service/runner path in-process (`service.create_webset` +
  `run_webset_async`; assertions read `service.get_webset` / `list_events` /
  `list_items` / `export_webset` — not the HTTP poll surface) for the brief's
  5-count company webset
  (`query="agtech robotics startups Series A 2024-2026"`, 2 criteria, 3
  enrichments incl. `company_profile`), asserts the event multiset +
  `webset.idle`-last (never an exact sequence), records the live-vs-s5 funding
  deltas, and writes the CSV export into the pytest tmp dir. Append the printed
  JSON + date/key tier here before quoting any number — single-day scaffolding
  anchors, never SLOs.
- Measured in this env: the ECB daily feed was re-fetched (2026-09-15) and
  still served `reference_date 2026-09-15` with all 29 rates identical, so
  `tests/ds/fixtures/websets/fx_ecb_snapshot.json` is unchanged (provenance
  note updated in the fixture README). The vendored s5 company sample and the
  Pro-tier 401 fixture were NOT re-validated against live EXA (no key; the
  Pro-key re-validation is a human precondition, § EXA shim above).
- Offline evidence on this branch: `pytest tests/ds/test_websets_live.py -m unit
  -v` → 5 passed, 1 skipped (the gated live leg), zero `Traceback`; the wider
  `pytest tests/ds -m unit` → 897 passed, 6 skipped, 13 failed — all 13 the
  pre-existing `chonkie` env failures (`test_chonkie_chunking.py`,
  `test_research_ingest.py`), unrelated to this record.

### MCP Tools

MCP server runs on port 8765 via `FastMCP` (`mcp_server.py`). Transport: streamable HTTP.

| Tool | Description | Optional |
|------|-------------|----------|
| `digisearch_query` | Search documents; returns formatted string of hits with score and content preview | No |
| `web_search` | Search the public web; returns JSON `WebSearchResponse` (#3853) | Yes (`digisearch[web-search]`) |
| `digisearch_research_turn` | Composite research turn (plan → retrieve → aggregate, or the #4064 web branch with `source=web\|auto`) with citations; `source`/`effort` passthrough (`output_schema` deferred, R7) | Yes (`digisearch[agent]`) |
| `digisearch_web_search` | Live web search via EXA; disabled message without `EXA_API_KEY` | Yes (`EXA_API_KEY`) |
| `monitors_create_watch` | Create a scheduled web-search watch (`schedule_cron` or `interval_seconds` ≥ 60; cron wins when both); returns `{watch, delivery_secret}` JSON — the secret appears here only | No |
| `monitors_list_watches` | List watches newest-updated first as `{"watches": [...]}` JSON | No |
| `monitors_trigger_watch` | Run one watch turn now (`mode` `manual`\|`poll`); returns the JSON `MonitorRun`, failed turns included | No |
| `monitors_get_runs` | List stored runs newest-first as `{"runs", "next_cursor"}` JSON | No |
| `websets_create` | Create a verified + enriched dataset (`query`, `count`, `criteria_json`, `enrichments_json`); returns `{id, object, status}` JSON immediately | No |
| `websets_get` | One webset's status/search generations + `{verified, pending, rejected}` counts as JSON | No |
| `websets_add_search` | Attach a follow-up search generation (`webset_id`, `query`, `count`); returns `{id, object, status}` | No |
| `websets_list_items` | Compact item text newest-first (`webset_id`, `verification`, `limit`, `cursor`) | No |
| `websets_events` | Compact event tail oldest-first (`webset_id`, `after`, `limit`) | No |
| `websets_export` | CSV/JSON export text for verified items (caps at 200 rows in chat) | No |

The four monitor tools share the HTTP API's store/runner and its
`watch_config_error` create gate (a watch whose cron could not parse would raise
inside `is_due` at tick time, where per-watch failures are isolated and would
otherwise vanish). Without a reachable monitor store they return the fail-closed
`digisearch monitors are disabled (monitor store is unavailable).` string; the
create tool maps the non-`poll` delivery modes it cannot configure targets for
to the same validation string the HTTP API would return.

The six `websets_*` tools are **unprefixed** (R10; the orchestrator manifest
keeps `digisearch_websets_*`) and wrap the same T6 service facade the HTTP
routes use, with the same fail-closed disabled string when the webset store
cannot be opened. They are the deliberate v1 chat surface: enrichment
add/remove, webhook secrets, monitors, and cancel stay HTTP-only operator ops.
The FastMCP instance carries the shared driver lifespan
(`websets/driver.py`), so these tools drive their own runs without an HTTP
process (#4170) — one reference-counted per-process install shared by
concurrent streamable-http MCP client sessions (stdio: the process), torn down
on the last exit (#4189). See § Phase D websets for the async lifecycle.

Tool parameters for `digisearch_query`: `text`, `index_name`, `top_k`, `mode`.

The `digisearch mcp` CLI builds a real `DigiSearch` client first
(`DigiSearchConfig.from_config` when `--config` is passed, else
`DigiSearchConfig.from_env()`), wires it via `create_mcp_with_indexes(client)`,
then calls `run_mcp`. `run_mcp` fails loud through the shared
`backend_require.require_real_search_backend()` gate — the same precedence the
HTTP startup gate enforces (Cloudflare `CLOUDFLARE_ACCOUNT_ID` +
`CLOUDFLARE_API_TOKEN` with legacy `VECTORIZE_*` / `D1_*` fallback → Azure →
Chroma → `RuntimeError`), so without a backend and without
`DIGISEARCH_ALLOW_STUB=1` the command exits non-zero instead of serving stub
results. The stub fallback stays unit-tests-only: never set
`DIGISEARCH_ALLOW_STUB` in production code paths, images, compose files,
supervisord programs, or wrangler vars. Port resolves from `--port`, else
`DIGISEARCH_MCP_PORT`, else `8765`; host from `DIGISEARCH_MCP_HOST`, else
`127.0.0.1` (loopback-only). In the cloudflare stack the server runs as the
`digisearch-mcp` supervisord program (priority 45, after digisearch HTTP seed
wait, before litellm) with no public route — reachable only from inside the
container.

### CLI Commands

Entry point: `digisearch` (Typer). All defined in `cli.py`.

| Command | Description |
|---------|-------------|
| `digisearch ingest --index <name> <path>` | Ingest file or directory via `pipeline.ingest.ingest_source` |
| `digisearch ingest-batch --index <name> <dir>` | Batch-ingest all supported files under a directory |
| `digisearch discover-crossref <doi>` | Fetch Crossref metadata and print YAML sidecar snippet |
| `digisearch query --index <name> --text <q>` | Run search query and print ranked results |
| `digisearch serve [--config <path>] [--port 8002]` | Start HTTP API server (uvicorn) |
| `digisearch mcp [--port 8765]` | Start MCP server (real backend only; fails loud without one; port also via `DIGISEARCH_MCP_PORT`) |
| `digisearch index build --config <path>` | Build/re-index (stub — prints guidance) |
| `digisearch index inspect --index <name>` | Inspect stub index chunk counts |

**Note:** CLI and HTTP ingest both call `digisearch.pipeline.ingest.ingest_source`
(batch via `ingest_paths`). That path writes through `route_add_chunks` —
Chroma when `CHROMA_PATH` / `CHROMA_HOST` is set (Profile A seed), otherwise the
in-memory stub only when `DIGISEARCH_ALLOW_STUB=1`. Optional `embedding_provider`
on the pipeline embeds chunks before the backend write. Chunk metadata always
inherits `Document.source` as `source` / `path` / `source_url` (plus a basename
`title` when missing) via `merge_document_metadata_into_chunks` so citation UIs
are not UUID-only.

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
├── chunks: list[Chunk]        # populated after chunking
└── segments: list[Segment]    # structural units (PDF page, md section); empty = unstructured
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
└── workspace_id: str?         # tenant isolation; enforced by backends, fail-closed when unsupported
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
└── backend: str?              # "vectorize" | "azure_ai_search" | "chroma" | "stub"
```

### Standard JSON hit shape

`normalize_query_hit()` in `core/standard_hits.py` converts `Result` to the portable dict shape that all consumers (digigraph, digichat, MCP) depend on:

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

#### Segmentation

`Document.segments` is an opt-in structural overlay. `ingestion/segmenters/heading.py`
splits markdown text at ATX heading boundaries (`#`/`##`/`###` — any level up to
`max_split_level`, default 3) into breadcrumb-labeled `Segment`s, and returns `[]` when
no qualifying heading is present.

On digisearch's own ingest path (`ParserRegistry` → `parse()`), two parsers populate
`Document.segments`:

- `PDFParser` emits one segment per page (`page:12`).
- `MarkdownParser` runs its content through `heading_segments()` (`heading:Title >
  Section`).

`HTMLParser` does **not** populate segments: it extracts plain text via BeautifulSoup's
`get_text()`, which discards all tag structure, so no ATX heading markers survive for
`heading_segments()` to find — running it over that output would always return `[]`.
Everything else (CSV, DOCX, short plaintext, headingless markdown) also leaves
`segments` empty and behaves exactly as before.

Separately, the `scripts/docs_onboard/` vault-writing pipeline (not digisearch's ingest
path) applies `heading_segments()` itself to `html_to_markdown()` output and to
OpenAPI-derived markdown — see that package's own docs, not this one.

`SegmentAwareChunker` chunks within segments and never across them: a segment at or
under `DEFAULT_CHUNK_CHARS` (2000 chars ≈ 512 tokens) becomes exactly one chunk;
only oversized segments are sub-split by the inner chunker. Every chunk carries
`segment_label` and `segment_index` in its metadata so citations can name the page
or section.

---

## 5. Internal Architecture

### Module structure

```
digisearch/src/digisearch/
│
├── server.py                  # FastAPI app: HTTP endpoints, rate limiting, correlation IDs
├── backend_require.py         # Shared real-backend gate (HTTP startup + MCP run_mcp)
├── mcp_server.py              # FastMCP: MCP tool server (port 8765)
├── orchestrator_tools.py      # OpenAI-style tool manifest for digigraph orchestration
├── cli.py                     # Typer CLI (digisearch) — thin wrapper over pipeline.ingest
├── pipeline/
│   └── ingest.py              # Canonical filesystem ingest (HTTP + CLI + tests)
├── ingest_worker.py           # Bulk ingest placeholder (not implemented)
├── http_client.py             # HTTP client helpers for callers (query_digisearch, format_results_table)
├── client.py                  # digisearch Python client
│
├── core/
│   ├── models.py              # Document, Chunk, Query, Result, SearchResponse, Segment
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
│   ├── factory.py             # resolve_embedding_pipeline + query.mode helpers
│   └── providers/
│       ├── openai.py          # OpenAIEmbedder (others: azure_openai, cohere, huggingface, ollama)
│       └── minilm.py          # MiniLMEmbedder (local ONNX, 384-dim; Vectorize's default embedder)
│
├── embeddings/
│   └── config.py              # EmbeddingModelSpec (model_id, dimensions, version)
│
├── indexes/
│   ├── base.py                # DigiIndex ABC (add, query, delete, update, list_collections, snapshot)
│   └── backends/
│       ├── chroma.py          # ChromaBackend (cosine HNSW, persistent or in-memory)
│       ├── azure_search.py    # AzureAISearchBackend (query_azure, _build_odata_filter)
│       ├── vectorize.py       # VectorizeBackend (Cloudflare Vectorize v2 REST API)
│       ├── vectorize_errors.py # VectorizeBackendError (isolated so it survives a broken vectorize.py import)
│       └── faiss.py           # FAISSBackend (stub — not registered for production)
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
├── chunking/                  # ChunkerBackend Protocol + Chonkie wrappers + factory
│   ├── backend.py             # ChunkerBackend Protocol (chunk(text) -> list[Chunk])
│   ├── chonkie_semantic.py    # ChonkieSemanticChunker (default for long docs)
│   ├── chonkie_token.py       # ChonkieTokenChunker (short news/alerts)
│   ├── document_adapter.py    # BackendDocumentChunker (text backend → Document Chunker)
│   └── factory.py             # DIGISEARCH_CHUNKER / per-index selection
│
├── retrieval/                 # RetrievalBackend Protocol (#402) — document-level async swap
│   ├── backend.py             # RetrievalBackend Protocol + RetrievalResult
│   ├── pgvector.py            # PgvectorBackend (default; Postgres + pgvector / in-memory tests)
│   ├── lightrag.py            # LightRAGBackend (graph upgrade; DIGISEARCH_RETRIEVAL_BACKEND=lightrag)
│   └── registry.py            # BACKENDS + get_retrieval_backend() env factory
│
├── ingestion/
│   ├── base.py                # Parser ABC
│   ├── registry.py            # ParserRegistry (extension/MIME detection)
│   ├── parsers/               # pdf, docx, html, markdown, csv, plaintext
│   ├── ocr/                   # base, tesseract, azure_di
│   └── chunkers/              # legacy: base, fixed, recursive, sentence, sliding_window, semantic
│                              # + segment_aware wrapper used by POST /ingest
│
├── agent/
│   ├── pipeline.py            # LangGraph: plan → retrieve → aggregate | web_retrieve → web_aggregate
│   ├── web_branch.py          # web-branch nodes + resolve_web_config() (#4064)
│   └── citations.py           # rag_sources_from_hits()
│
├── discovery/
│   └── crossref.py            # DOI → EvidenceMetadata via Crossref REST API
│
├── web_search/                # Proprietary web search (#3853, [web-search] extra)
│   ├── models.py              # WebSearchRequest / WebSearchResponse / WebSearchResult
│   ├── searxng_provider.py    # Primary: loopback searxng sidecar (/search?format=json)
│   ├── ddgs_provider.py       # Fallback: embedded ddgs scrape (zero infra)
│   ├── extractor.py           # fetch HTML → markdown (trafilatura, readability fallback)
│   ├── citation.py            # Citation{url,title,excerpt} + normalize_url() (#4064 Task 0)
│   ├── fetch.py               # fetch_markdown(): digifetch + extractor, never indexes (#4064 Task 0)
│   └── service.py             # run_web_search / search_web: searxng→ddgs failover + enrich
│
├── web/                       # Phase B web research branch (#4064; [agent] + [rerank])
│   ├── retrieve.py            # sole web_search adaptation seam (never ingest_url)
│   ├── answer.py              # grounded_answer: Perplexica loop + inline [n] citations
│   ├── structured.py          # structured_synthesis + verify_grounding
│   ├── grounding_models.py    # WebResearchConfig / EFFORT_PRESETS / TurnUsage / TurnCost
│   └── accounting.py          # pure stage-ms + advisory cost helpers
│
├── monitors/                  # Phase C scheduled web-search monitors (#4065)
│   ├── models.py              # Watch / MonitorRun envelopes + schedule/dedup/delivery config
│   ├── store.py               # SQLite watch/run persistence, dedup memory, delivery-secret column
│   ├── dedup.py               # normalize_url-keyed fingerprint dedup (new/changed/unchanged)
│   ├── runner.py              # one watch turn + due-tick + in-process recall seam
│   ├── delivery.py            # validate_delivery gate + webhook/slack/email fan-out receipts
│   ├── exa_adapter.py         # live-pinned (#4123) EXA monitor adapter: nested event-envelope
│                              # run translation (exa_run_to_monitor_run), per-monitor secret
│                              # verification (verify_exa_signature), create/delete helpers
│   ├── provisioning.py        # (#4184) create_watch_provisioned: oss local mint / exa
│                              # remote-first create (exact period mapping, remote
│                              # webhookSecret + monitor id, best-effort compensation)
│   └── validation.py          # shared create/update config gate (datatap, timezone, cron, delivery)
│
└── dev/
    └── edgar_sample_export.py # EDGAR-CORPUS slice exporter (dev/test only)
```

### Lazy package surface and install extras

`digisearch/__init__.py` is **lazy** ([PEP 562](https://peps.python.org/pep-0562/)
module `__getattr__`). The package top level imports nothing heavy at
`import digisearch` time — the public client surface is resolved on first
attribute access via a `_LAZY = {name: module}` table:

| Public name | Resolved from |
|-------------|---------------|
| `digisearch` | `digisearch.client` |
| `Chunk`, `Document`, `Query`, `Result`, `Segment` | `digisearch.core.models` |

**Contract (do not regress):**

- `from digisearch import digisearch` (and `Chunk`/`Document`/`Query`/`Result`)
  keeps working — `__getattr__` imports the backing module on demand and caches
  the result in module `globals()`, so the cost is paid at most once.
- Importing a **leaf submodule** (e.g. `digisearch.ingestion.parsers.pdf` or
  `digisearch.ingestion.registry`) must **not** import `digisearch.client` nor
  the `[server]` stack (`fastapi`, `uvicorn`, `mcp`, `typer`, `digikey`). The
  parser import chain is deliberately light: `pdf.py → core.models +
  ingestion.base` (no `[server]` stack). The parser's own third-party dep
  (pdfplumber/pymupdf) is **try-imported at module scope** (guarded by
  `try/except ImportError`), so the module imports cleanly even when the dep is
  absent and becomes *functional* only once `[ingestion]` is installed.
- `__all__`, `__getattr__`, and `__dir__` are all defined; a `TYPE_CHECKING`
  block re-imports the names so static type-checkers and IDEs still resolve
  them. Any name **not** in `_LAZY` raises `AttributeError` as usual.
- Enforced by `tests/ds/test_parsers.py::test_*_imports_without_server_stack`,
  which import the parser in a **fresh subprocess** and assert the forbidden
  modules are absent from `sys.modules` (a subprocess is required so sibling
  tests that load the server stack don't pollute the measurement).

#### Install extras

The base install is intentionally **light** — only what the importable library
core needs. The HTTP/MCP/CLI service stack and the parser deps are extras:

| Extra | Adds | Needed by |
|-------|------|-----------|
| _(base)_ | `polars`, `pydantic`, `pyyaml`, `httpx`, `digibase` | core models/config/client, parser import chain |
| `[server]` | `fastapi`, `uvicorn[standard]`, `mcp`, `typer`, `digikey`, `python-json-logger` | `server.py`, `mcp_server.py`, `cli.py`, `digisearch.logging`, digikey auth middleware |
| `[ingestion]` | `beautifulsoup4`, `python-docx`, `pdfplumber`, `chardet`, `chonkie[semantic]` | functional parsers (html/docx/pdf/plaintext) + Chonkie Semantic/Token chunkers; `polars` for the CSV parser is already in base |
| `[chroma]` | `chromadb` | Chroma backend |
| `[azure]` | `azure-search-documents`, `azure-core` | Azure AI Search backend |
| `[embedding]` | `openai` | OpenAI embedder |
| `[rerank]` | `sentence-transformers` | BGE cross-encoder (`Reranker` provider=`bge`); kept separate from `[embedding]` so OpenAI-only installs stay light (#2441) |
| `[agent]` | `langgraph` | research-turn graph (§11) |
| `[web-search]` | `digifetch`, `ddgs`, `trafilatura`, `readability-lxml`, `markdownify` | proprietary web search: searxng sidecar (httpx, base only) + ddgs fallback + digifetch fetch → trafilatura/readability extract enrichment (§3 `POST /v1/web_search`; #3853) |
| `[dev]` | `[server]` + `[ingestion]` + pytest/ruff/langgraph | CI + local dev (so every dev install exercises and pip-audits the full shipped surface) |

The **running service** installs `digisearch[server,ingestion,azure,chroma,web-search]`
(see [Docker](#10-docker-and-mcp-composition)) so it retains every dependency it
relied on before the split (the service additionally now ships pdfplumber for
PDF ingest, which the old `[azure,chroma]`-only image lacked, plus the
`[web-search]` stack for `POST /v1/web_search`). The image COPY/installs the
`digifetch` workspace sibling exactly like `digibase`/`digikey` (its
`pyproject.toml` + `ARCHITECTURE.md` readme + `src`, then `uv pip install -e`),
which is what satisfies the `[web-search]` extra's `digifetch>=0.1.0` pin at
build time. `[web-search]` rides `all` like every other feature extra, but stays
out of `[dev]`: `dev` is `[server]` + `[ingestion]` only (same as
`[azure]`/`[chroma]`/`[agent]`), so local installs stay light and CI exercises
the extra explicitly. A consumer that
only wants a parser can `pip install digisearch[ingestion]` without dragging in
the server stack.

### Pluggable backend pattern

The backend registry in `search/_stub.py` uses a simple callable list pattern:

```
_backends: list[Callable[[Query, str], SearchResponse | None]]

register_backend(fn) → appends fn to _backends

query_index(query, index_name):
  for backend in _backends:
    resp = backend(query, index_name)
    if resp is not None:
      return _maybe_rerank(query, resp)  # DIGISEARCH_RERANK_ENABLED, off by default
  # fall through to stub or empty (also through _maybe_rerank)
```

When `DIGISEARCH_RERANK_ENABLED` is truthy and `Query.skip_rerank` is false, `_maybe_rerank` runs `Reranker` over `resp.results` with `top_n=query.top_k` before returning. Provider defaults to `bge` (`BAAI/bge-reranker-v2-m3` via `[rerank]` / sentence-transformers); override with `DIGISEARCH_RERANK_PROVIDER=cohere` (already-multilingual `rerank-multilingual-v3.0`). `digisearch_fetch_all` sets `skip_rerank=True` on every page because it shares `run_query` → `query_index` with single-shot `/query` — reordering a partial page would break exhaustive pagination (#2441 / ADR-0025 Phase 4).

Azure is registered first (preferred), then Vectorize, then Chroma, stub last. Adding a new backend requires only calling `register_backend()` at import time. There is no configuration-driven selection — the first configured backend wins.

**Fail-loud backends:** Azure (first) and Chroma (last) are optional local backends, but once one is *configured* a serving failure must not be silently answered from a different corpus. A failing `query_azure()` / `ChromaBackend.query()` now raises `SearchBackendError` (`indexes/backends/backend_errors.py`); `_stub.py`'s `_azure_backend` / `_chroma_backend` wrappers re-raise instead of returning `None`, and `SearchBackendError` is deliberately absent from `_BACKEND_ERRORS`, so `query_index` cannot swallow it and fall through (#3909). Only the "not configured" and optional-dependency-`ImportError` paths still return `None` so the router continues. Vectorize has the same contract via its own `VectorizeBackendError` — see below. A healthy backend with no matches still returns an empty result (not an error).

#### Vectorize (remote index)

`indexes/backends/vectorize.py` implements `DigiIndex` over the Cloudflare
Vectorize v2 REST API. `search/_stub.py`'s `_vectorize_backend` activates it
ahead of Chroma whenever `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` are
both set (non-empty after `.strip()`) — canonical names shared with D1
(#2239 credential rename: same Cloudflare account + token authorizes both);
each falls back to the legacy `VECTORIZE_ACCOUNT_ID`/`VECTORIZE_API_TOKEN`,
then `D1_ACCOUNT_ID`/`D1_API_TOKEN`, names when unset (`_first_env`), so the
rename is zero-downtime. This is what the production Cloudflare Container uses
(`cloudflare/digithings-stack-cloudflare/container/` unsets `CHROMA_PATH` and
skips the Chroma seed once Vectorize is configured).

It exists because Cloudflare Container disk is ephemeral: a container-local
Chroma index has to be rebuilt from scratch on every cold boot. With Vectorize
the container holds no corpus at all and only issues queries against the
remote index that `scripts/vectorize_sync.py` maintains from an operator
machine or CI.

Two operational notes. First, upsert and query share one embedding model:
`scripts/vectorize_sync.py` embeds with an explicit `MiniLMEmbedder()`, and
`VectorizeBackend.query()` falls back to the same class (`MINILM_MODEL_ID =
"all-MiniLM-L6-v2-384"`, 384 dimensions) as its process-wide default embedder
whenever no `embedding_provider` is injected and `Query.embedding` is absent —
this is also the model `ChromaBackend` embeds with internally, so a Chroma-built
and a Vectorize-built index over the same corpus are directly comparable. The
default-embedder singleton is initialised under a `threading.Lock` (double-checked
locking) so concurrent first queries construct at most one ONNX load per process.
The `embedding_model` stamp in vector metadata and the mismatch guard
(`assert_index_model()`, which probes one existing vector before a sync and
refuses to upsert under a different model) both live in `vectorize_sync.py`,
not in `VectorizeBackend` itself — a chunk added through the generic
`POST /ingest` → `route_add_chunks` path is not stamped or checked this way.

Second, a Vectorize failure propagates rather than collapsing into an empty
result — the same fail-loud contract Chroma/Azure now follow via
`SearchBackendError` (#3909). `VectorizeBackend.query()` raises a plain
`RuntimeError` on an HTTP error status or an HTTP-200-with-`success: false`
body; `_vectorize_backend` then wraps *any* exception from that call —
including an `ImportError` while importing `VectorizeBackend` itself — as
`VectorizeBackendError` (defined in `vectorize_errors.py`, a separate module so
the type stays importable even when `vectorize.py`'s own import fails).
`VectorizeBackendError` is deliberately absent from `query_index()`'s
`_BACKEND_ERRORS` tuple, so it is never swallowed and never falls through to
Chroma: for a remote index, a silent empty result is indistinguishable to a
user from "the docs do not mention that."

Chunk text rides in vector metadata (`content`), because Vectorize returns
only ids, scores and metadata on query — there is no document store behind
this backend to reconstruct it from.

Third, the index name is not a free choice. `_stub.py`'s `_vectorize_backend`
passes digisearch's `index_name` straight into the Vectorize URL with no
translation, so the Vectorize index **must be named exactly** what the
digisearch server for that tenant is configured with — `DIGISEARCH_INDEX` /
the `DIGI_TENANT_CORPUS_MAP` entry, both set in
`cloudflare/digithings-stack-cloudflare/wrangler.toml`. Today that value is
underscore-form (`digithings_docs`, `occ_help`) to match the hardcoded Chroma
collection names in `container/seed_chroma.sh` — renaming either side without
renaming the other breaks that pairing outright.

**Verified 2026-08-11:** Cloudflare's docs give **advisory** naming guidance
— [get-started/intro](https://developers.cloudflare.com/vectorize/get-started/intro/)
states in prose that "a good index name is: a combination of lowercase
and/or numeric ASCII characters, shorter than 32 characters, starts with a
letter, and uses dashes (-) instead of spaces" — but no enforced charset or
regex is published, and there is a real 64-byte length cap that both
`digithings_docs` and `occ_help` clear. This is not a claim that underscores
are documented as supported, and it is not a claim the docs are silent on
the matter — both would be false. Empirically, underscore index
names are accepted: `npx wrangler vectorize create digithings_docs
--dimensions=384 --metric=cosine` and the equivalent call for `occ_help` both
succeeded against the live account, and `npx wrangler vectorize list` shows
both indexes at 384 dimensions, cosine metric. No rename of
`DIGISEARCH_INDEX`, the corpus map, or the Chroma collection names is
needed — `digithings_docs` / `occ_help` remain the single canonical name on
both sides of the pairing.

Fourth, `VectorizeBackend.query()` clamps `top_k` to `MAX_TOP_K` (50) and logs
a warning when it does, but a caller paging through results with `page_size >
50` (e.g. `digisearch_fetch_all`, see §Orchestrator dispatch pattern below)
sees a short page and — for every other backend — correctly reads that as "no
more results." Against Vectorize it is ambiguous: the page really might be the
last one, or it might just be capped at 50. `api_orchestrator_invoke` sets
`OrchestratorFetchAllData.possibly_truncated=True` when it detects this
pattern so the caller can tell the two apart; it does not implement real
pagination against Vectorize (that needs `Query.skip` support the backend
does not have — a design decision, not fixed here).

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

**Important:** The `HybridSearcher` class is not what the production server actually uses. The server delegates to `query_index()` which calls the registered backends (Azure, Vectorize, or Chroma) directly. Azure supports native hybrid (BM25 + vector) internally but digisearch does not yet map `mode` onto Azure vector query types. Neither Chroma nor Vectorize supports BM25 natively — the `HybridSearcher` would need to be wired at a higher level for hybrid on either. Validated `mode` values are accepted on the public API; Chroma/Vectorize/stub **coerce** `keyword`/`hybrid` to vector-only ANN and log the coercion (see [query.mode semantics](#querymode-semantics)).

### Orchestrator dispatch pattern

digigraph registers digisearch via `POST /v1/orchestrator_tools`. When an LLM calls one of the tool names, digigraph calls `POST /v1/orchestrator_invoke` with `{tool, arguments, default_index_name}`. The dispatch code in `server.py` (`api_orchestrator_invoke`) maps tool names to internal query logic. This means:

- Tool schemas are owned and versioned by digisearch
- digigraph has no search logic — it is a pass-through hub
- `digisearch_fetch_all` performs server-side pagination in a while loop (page size 500) and returns the full collected set in a single response, which can be very large

### Phase C monitors (#4065)

`digisearch/src/digisearch/monitors/` is an orchestration layer over the Phase B
web-search seams — no provider, extractor, embedding, or ranking code is added.
One-line responsibilities:

| File | Responsibility |
|------|----------------|
| `monitors/models.py` | `Watch` / `MonitorRun` envelopes + `WatchSchedule` / `DedupRule` / `DeliveryConfig` / `DeliveryTarget` / `DeliveryReceipt`; `extra="forbid"`; EXA-bounded `num_results` (1–100); `interval_seconds ≥ 60` |
| `monitors/store.py` | SQLite persistence (watches + runs), ULID ids, run pagination, the delivery-secret column, dedup-memory recomputation |
| `monitors/dedup.py` | Huginn / changedetection.io-style memory: `normalize_url` keys + content fingerprints, reimplemented on stdlib (`hashlib` + `difflib`) — no embeddings, no network |
| `monitors/runner.py` | One watch turn (`run_watch`), the scheduler entry (`tick_due_watches`), due evaluation (`is_due`), and the `deliver` seam |
| `monitors/delivery.py` | `validate_delivery` create/update gate + webhook/slack/email fan-out with per-target receipts |
| `monitors/validation.py` | The shared create/update decision (`watch_config_error`) used by both the HTTP and MCP surfaces |
| `monitors/provisioning.py` | (#4184) `create_watch_provisioned`: the OSS path keeps the local secret mint byte-for-byte; `backend="exa"` is remote-first (exact interval period mapping, webhook target required, EXA's `webhookSecret` + monitor id required, best-effort remote delete on any later failure) |

**Storage.** One SQLite file (`sqlite3` stdlib), resolved explicit path →
`DIGISEARCH_MONITORS_DB` → `{DIGI_WORKSPACE}/.digisearch/monitors.sqlite3` →
`./.digisearch/monitors.sqlite3` (cwd fallback for host/test runs). WAL journal
mode plus a 5s busy timeout let the HTTP process and the digiclaw tick process
share the file; connections are thread-bound, so `get_monitor_store()` opens one
store per request thread (`server.py`) and the MCP tools open one per call.

| Table | Columns | Notes |
|-------|---------|-------|
| `watches` | `watch_id` PK, `body` JSON, `updated_at`, `workspace_id`, `secret` | `body` is the full `Watch` document (model evolution without migrations); `secret` is the nullable per-watch delivery secret, never in `body` |
| `runs` | `run_id` PK, `watch_id`, `status`, `trigger`, `started_at`, `finished_at`, `body` | Append-only; indexed `(watch_id, started_at DESC)` |

Runs are retained after their watch is deleted: `append_run` does not require the
watch row, so a turn that started before a delete still lands. Timestamps in the
queryable columns are fixed-width UTC ISO strings (lexicographic order matches
chronological order); `created_at`/`updated_at` are server-assigned and cannot be
patched. Fresh databases get the `secret` column from the schema; pre-R8
databases are upgraded in `__init__` with a guarded `ALTER TABLE`, and a failed
upgrade propagates rather than leaving a half-migrated store.

**Dedup.** Three rules over the `seen` map (`normalize_url(url) → fingerprint` —
`normalize_url` is the landed Phase B citation identity, imported, never
redefined):

1. An unseen URL is `new`.
2. A seen URL is `unchanged` under `match="url"` (content ignored); under
   `match="url_content"` it is `unchanged` when its fingerprint equals the
   memory and reported `changed` (a survivor, i.e. new content) when it does not.
3. Under `match="url_content"`, an unseen URL whose title is a near-duplicate
   (`difflib.SequenceMatcher` ratio ≥ `similarity_threshold`, default 0.9) of a
   seen title collapses to `unchanged`.

`dedup_stats` keys are exactly `seen`, `new`, `changed`, `unchanged` (`seen`
counts current results whose normalized URL was already in memory; collapsed
near-duplicates land in `unchanged`). A fingerprint is
`"<normalized title>\x1f<sha256 hexdigest>"` — sha256 over
`title.strip().lower()` + `"\n"` + whitespace-collapsed text, with the normalized
title riding along so the near-duplicate leg can compare a new title against
previously seen titles (otherwise the memory is opaque digests only). Seen-memory
writers MUST recompute values with the public `result_fingerprint` (shared
extraction order `text` → EXA `highlights` → `snippet`) or `highlights`-only /
`snippet`-only results would compare unequal and report `changed` on every run.
Fingerprints are not a stored column: `MonitorStore.seen_fingerprints` merges the
raw `results_all` payloads of the newest 10 runs (newest-first, most recent
observation of a URL wins) and recomputes them. A secret-missing failed run
persists `results_all=[]`, so undelivered content never advances this memory and
is re-detected (and fails loudly again) on the next run.

**Tick semantics.** `tick_due_watches` evaluates every enabled watch with
`is_due` and runs the due ones with `trigger="schedule"`, isolating per-watch
failures: a recall failure contributes its persisted `status="failed"` run, an
unexpected error is logged without aborting the tick. `is_due` owns all timezone
conversion (naive `now` is UTC; wall clock evaluated in `schedule.timezone`) and
imports the cron grammar from `digiclaw.cron` (`parse_cron` +
`CronExpression.matches`) — never a copy. Cron fires once per matching minute (a
previous start inside the same minute suppresses the second fire); interval fires
when `last_run_at + interval_seconds <= now`, and a missing `last_run_at` means
due. Failed runs count as a cadence tick, so a failing watch retries on its
schedule rather than on every 60s wake-up. Datatap-scoped watches are skipped
outright (datatap stays OFF end-to-end).

**Fail-hard semantics.** A recall exception persists `status="failed"` with
`error=str(exc)` and re-raises `MonitorRunError` carrying the persisted `run_id`;
the HTTP trigger route returns that stored run (201) instead of masking it with a
5xx, while the digiclaw helper counts it as `failed`. `no_change` runs persist
and never deliver.

### Phase D websets (#4066)

`digisearch/src/digisearch/websets/` is the async verify + enrich layer over the
Phase A recall/fetch seams and the Phase B structured-output path — same
no-new-provider discipline as Phase C. One-line responsibilities:

| File | Responsibility |
|------|----------------|
| `websets/models.py` | `Webset` / `WebsetSearch` / `WebsetItem` / `EnrichmentDef` / `EnrichedField` / `CompanyEntity` / `WebsetMonitor` / `WebhookConfig` / `WebsetEvent`; shared `Citation` imported, never redefined; `verification_mode` persisted on webset + search |
| `websets/store.py` | SQLite persistence (websets/searches/items/enrichments/monitors/webhooks/webhook_deliveries/events), `ws_/wss_/wsi_/wse_/wsm_` + uuid4-hex ids, cursor pagination, the append-only `(webset_id, dedup_key)` event log, the `(webhook_id, event_id)` delivery ledger with its `attempts`/`next_attempt_at` re-delivery state (`update_webhook_delivery`, `list_due_webhook_deliveries`, #4226) |
| `websets/verify.py` | `verify_item` (llm + offline rules modes) and the fail-closed settlement of still-pending items at candidate-pass end |
| `websets/enrich.py` | `enrich_item` (8 typed fields, per-field citations), funding reconciliation (ECB snapshot), entity merge, `company_profile_field` |
| `websets/runner.py` | `AsyncioRunner` (semaphore 4, per-item containment, semaphore-aware cancellation), `run_webset_async`, `backfill_enrichment`, `schedule_webset_task` + `WEBSET_TASKS` |
| `websets/driver.py` | Shared in-process driver (`webset_task_lifespan`, `WebsetTaskScheduler`): installs the scheduler seam per install window (first entry to last exit), reference-counted across concurrent invocations — first entry installs + runs the startup-resume union, last exit cancels tracked runs/backfills, and a later window reinstalls + re-resumes; concurrent HTTP/MCP sessions share one install (#4170/#4189); carried by both the FastAPI and FastMCP lifespans; runs the scheduled tick loop (`WEBSET_TICK_SECONDS`, in-process `last_tick`) and the webhook re-delivery loop (`WEBSET_REDELIVERY_SECONDS`, due failed ledger rows) in the same TaskGroup (#4221, #4226) |
| `websets/events.py` | Event emit helpers, the shared Phase C signing core, `append_event` fan-out through `deliver_webhook` (3 attempts, 5s/25s) + ledger recording, `redeliver_webhook` (bounded 5-attempt re-drive stepping the full pinned 5m/30m/2h/6h ladder, current-secret signing, #4226), public `verify_webhook_signature` |
| `websets/export.py` | `export_json` (per-field citations) and `export_csv` (polars) |
| `websets/service.py` | The sync facade the HTTP/MCP/orchestrator surfaces call (create/get/items/counts/add_search/add_enrichment/remove/monitors/webhooks/events/cancel/export) + the scheduler seam |
| `websets/providers/exa_websets.py` | Dormant EXA Pro shim: OSS⇄EXA translation for create/read/refresh, `ExaWebsetsProRequiredError(ExaError)` |

**Storage.** One SQLite file (`sqlite3` stdlib) resolved
`DIGISEARCH_WEBSETS_DB` → `{DIGI_WORKSPACE}/.digisearch/websets.sqlite3` →
`./.digisearch/websets.sqlite3`, WAL + 5s busy timeout, one thread-bound
connection per store instance (constructed per request/worker thread — no
in-process lock). `websets`/`searches` keep `status` (and the webset
`workspace_id`) as real columns for the resume selector and workspace filters;
the JSON `body` is the model document, so `verification_mode` persists with the
row. Events are append-only with a UNIQUE `(webset_id, dedup_key)` index
(INSERT-or-ignore, generation-scoped keys) so a resumed pass cannot duplicate an
event while a new `add_search`/backfill/`trigger_monitor` generation can
legitimately re-emit terminal events. Item `verification` and the enrichment
names are real columns for filtered listing.

**Execution model.** The shared driver (`websets/driver.py`) owns one
`asyncio.TaskGroup` + `WEBSET_TASKS` per process install window, reference-counted
across concurrent lifespan invocations — installed by the HTTP lifespan (one
serving window) and the FastMCP lifespan (MCP client sessions on
streamable-http, process on stdio) alike (#4170/#4189); the service facade
schedules through the `set_scheduler` seam (no bare `asyncio.create_task`, no
awaiting a run inline) and all store I/O inside the runner crosses through one
dedicated worker thread (the store is thread-bound). Startup resume, the
terminal-status gate, `verification_mode` threading, and the deferred items are
documented in § Phase D websets.

---

## 6. Security Analysis

### digikey JWT auth scopes

digisearch uses `DigiAuthMiddleware` from `digikey.integrations.service_middleware`. The middleware validates digikey JWTs and enforces path-to-scope mappings defined in `digisearch_path_scopes`.

| Endpoint | Required scope |
|----------|---------------|
| `POST /query` | `digisearch:query` |
| `POST /ingest` | `digisearch:ingest` |
| `POST /ingest/url` | `digisearch:ingest` |
| `POST /v1/orchestrator_tools` | `digisearch:query` |
| `POST /v1/orchestrator_invoke` | `digisearch:query` |
| `POST /v1/research_turn` | `digisearch:query` |
| `POST /v1/monitors`, `GET /v1/monitors`, `GET\|PATCH\|DELETE /v1/monitors/{watch_id}` | `digisearch:query` (landed fallthrough — CRUD is not `digisearch:ingest`) |
| `POST /v1/monitors/{watch_id}/trigger`, `GET /v1/monitors/{watch_id}/runs[/{run_id}]` | `digisearch:query` |
| `POST /v1/monitors/tick` | `digisearch:query` (digiclaw service JWT) |
| `POST /v1/monitors/exa_webhook` | **Auth-exempt** (local `_digisearch_path_scopes` exemption); the watch's stored per-monitor secret is verified in the handler against `exa-signature` (`t=<unix>,v1=<hex>`, `HMAC-SHA256(secret, f"{t}.{body}")`, ±300 s) — 401 `exa_bad_signature` when missing/unverifiable |
| `GET /health` | Public |
| `GET /azure_status` | `digisearch:query` |
| `GET /indexes`, `GET /indexes/{name}` | (unclear — not in server auth logic) |

**Gap:** `GET /azure_status` still returns reachability detail to any caller with `digisearch:query`; consider restricting to internal networks or a dedicated ops scope.

### Monitor delivery egress and the EXA webhook exemption

Monitors add digisearch's only **outbound** data path beyond search/embedding
calls: a non-`poll` watch POSTs the run body (query text and result URLs) to
operator-configured webhook/slack/email targets. Guardrails (R13/R8): targets are
validated at create/update (`validate_delivery`) to be https, userinfo-free, and
resolve to global addresses only — an unresolvable host is rejected because it
cannot be proven public. At delivery time httpx resolves the target again,
redirects are never followed, and the per-watch secret is stripped from receipt
error text together with the target URL. The create-time check leaves a
DNS-rebinding window acknowledged in `runner.py`; verified TLS plus the
no-redirect rule bound it. Delivered bodies are signed with `X-digi-signature:
sha256=<hmac_sha256(secret, body)>` so receivers can verify authenticity without
this service reaching back out.

`POST /v1/monitors/exa_webhook` is the one auth-exempt route in the service: EXA
holds no digikey JWT, so each delivery authenticates with the WATCH's stored
per-monitor secret (the one-time `webhookSecret` from EXA's create response,
persisted with `MonitorStore.set_delivery_secret`) against the live-pinned
`exa-signature: t=<unix>,v1=<hex>` header (`HMAC-SHA256(secret,
f"{t}.{body}")`, ±300 s). There is deliberately no static shared-secret
fallback; the check is mandatory and fail-closed (a missing stored secret, a
missing header, a malformed/stale/future `t`, or a mismatch ⇒ 401), and the
presented value is never logged or echoed. A valid signature translates the
NESTED event envelope through the live-pinned (#4123) Task 8c EXA adapter:
`data.monitorId` resolves the watch by `exa_monitor_id` (datatap excluded;
`watch_not_found` otherwise, `watch_backend_mismatch` when the watch is not
`backend="exa"`), deliveries whose run status is non-terminal (`running`,
`cancelled`, `queued`, or any future parseable status that is neither
`completed` nor `failed`/`error`) are acked 200 without a run row (EXA retries
non-2xx indefinitely, so an unknown-status rejection was an endless retry
loop), and a redelivered terminal run answers 200 with the stored
run (never 409 — EXA retries non-2xx). Untranslatable payloads are rejected
(`exa_payload_invalid` / `exa_monitor_id_missing`)
rather than accepted as empty.

### Multi-tenant isolation

When `workspace_id` is set on `POST /query`, the server injects a mandatory structured filter clause (`workspace_id eq …`) into `Query.filters`. Chroma and stub backends apply this at query time. Azure translates it to OData, and additionally **fails closed**: if `workspace_id` is not in the index's `filterable_fields` allowlist, `AzureWorkspaceFilterError` is raised (a type deliberately absent from `search/_stub.py`'s `_BACKEND_ERRORS`, so it propagates rather than falling through to another backend). The raw-OData branch (`allow_raw_filter`) ANDs the mandatory workspace clause into the raw filter instead of bypassing structured scoping, and results are post-filtered with `chunk_matches_workspace` as defense-in-depth (#3883). **Vectorize does not translate filters yet** — `VectorizeBackend.query()` still sends only `{vector, topK, returnMetadata, returnValues}`, but if `Query.filters` is non-empty or `workspace_id` is set it now raises `VectorizeBackendError` instead of silently returning unscoped matches (#2219). Production corpora that isolate by separate per-corpus indexes keep querying without filters.

Callers omitting `workspace_id` receive unscoped results (single-tenant default). Multi-tenant deployments should require `workspace_id` at the BFF layer.

The research path is scoped the same way (#3909): `POST /v1/research_turn`, the `digisearch_research_delegate` orchestrator tool, and the `digisearch_research_turn` MCP tool all accept `workspace_id`, carry it on `ResearchTurnState`, and inject the mandatory `workspace_id eq …` clause in the retrieve step.

### Filter injection risks

**Raw OData path:** `POST /query`, `POST /v1/research_turn`, and the orchestrator invoke paths that feed them reject a raw `filter` (HTTP 400) when the configured index does not set `allow_raw_filter: true` (#3909); previously only the Azure backend re-gated it. When enabled, `filter_validator.py` applies:

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

CORS is installed via the shared `digibase.cors.install_cors(app, service="digisearch")` helper. Allowlist precedence: `DIGISEARCH_CORS_ORIGINS` → `DIGI_CORS_ORIGINS` → legacy `DIGI_ALLOWED_ORIGINS`, defaulting to **empty** (most restrictive) when unset. Production deployments must explicitly set one of these. See `SECURITY.md` §"CORS policy".

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

For Azure AI Search, the service uses its own internal hybrid ranking. The digisearch `mode` parameter maps to `query_type="simple"` in all cases — there is no `"semantic"` or `"vector"` query type being set. This means Azure's BM25 is always active and digisearch does not currently unlock Azure's native vector search or semantic ranker modes.

### Embedding cache hit rates

The `EmbeddingCache` logs hit rates at INFO level. For a cold corpus, hit rate is 0%. For repeated ingest of an unchanged corpus, hit rate approaches 100%. The cache is most valuable during development iteration (re-ingesting a modified corpus where most chunks are unchanged).

Hit rate degrades when:
- Different chunkers are used on the same documents (different chunk boundaries → different text → cache miss)
- Chunks are slightly modified between runs (e.g. whitespace normalization changes)
- The cache is not mounted persistently in Docker (ephemeral container restarts)

### Chunking strategy impact on retrieval quality

The default ingest chunker is **Chonkie SemanticChunker** (`DIGISEARCH_CHUNKER=semantic`), selected via `digisearch.chunking.factory.get_ingest_chunker`. It groups sentences by embedding similarity (optional skip-window merge ≈ legacy SDPM) so financial reasoning context survives chunk boundaries. Legacy `RecursiveChunker(chunk_size=2000, chunk_overlap=250)` remains available as `DIGISEARCH_CHUNKER=recursive` for rollbacks and characterization tests.

Impact considerations:

- **Too small (< 128 tokens):** chunks lose context; recall suffers on paraphrase queries
- **Too large (> 1024 tokens):** chunks dilute relevance scores; precision suffers
- **Zero overlap (token chunker):** boundary queries that span chunks miss evidence
- **Token chunker (`DIGISEARCH_CHUNKER=token`):** fast fixed windows — prefer for short news/alerts
- **Semantic chunker (default):** embedding-based boundary detection; first call may download the potion Model2Vec weights; ingest cost higher than recursive/token

For SEC filings (EDGAR corpus) and research/earnings transcripts, keep the semantic default. Use `token` for brief wires where semantic similarity adds little value.

### Reranker latency tradeoff

`Reranker` runs as a second-pass over the initial candidate set. When constructed without an explicit `top_n`, it no longer silently caps at 5 — callers (including `query_index`) pass `top_n=query.top_k`. Cost:

- **Cohere Rerank API:** ~200–500ms per call, network-dependent
- **BGE local (`BAAI/bge-reranker-v2-m3` via sentence-transformers `CrossEncoder`):** ~50–200ms for a batch of 10 candidates on CPU; ~10ms on GPU
- Model load on first call adds several seconds for BGE

Wiring is gated by `DIGISEARCH_RERANK_ENABLED` (default off) inside `query_index()` (#2441 / ADR-0025 Phase 4). With the flag unset, output is unchanged. `digisearch_fetch_all` sets `Query.skip_rerank=True` so partial pages are never reordered even when the flag is on.

### Index backends (production inventory)

**Production:** Chroma (local persistent or HTTP), Azure AI Search, and Cloudflare Vectorize (`VectorizeBackend`) — the production Cloudflare Container runs Vectorize exclusively (Chroma is unset once remote-index credentials resolve: canonical `CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN`, then legacy `VECTORIZE_ACCOUNT_ID`/`VECTORIZE_API_TOKEN`, then `D1_ACCOUNT_ID`/`D1_API_TOKEN` as a supported fallback for the same account/token pair); Docker Compose deployments still default to Chroma.

**Not in production:** `FAISSBackend` (`indexes/backends/faiss.py`) and `PineconeBackend` are unregistered stubs — do not enable without a new ADR and registry wiring.

For corpora beyond ~1M chunks, prefer Azure AI Search; Chroma is appropriate for single-tenant workloads up to roughly 500K–1M chunks (see §8 scaling notes above).

---

## 9. Integration Points

### Orchestrator tools contract with digigraph

digigraph calls digisearch via two HTTP routes:

1. `POST /v1/orchestrator_tools` — fetches tool schemas, optionally specializing them with index metadata (filterable fields, facetable fields, result columns, complex field structures). The hub caches these and presents them to the LLM.

2. `POST /v1/orchestrator_invoke` — dispatches tool execution. The hub passes `{tool, arguments, default_index_name}` and receives `{ok, service, tool, data}`.

The contract is versioned by `{"tools": [...], "version": 1}` in the tools response. digigraph should treat unknown tool names from `/v1/orchestrator_tools` gracefully.

`DIGISEARCH_INDEX` env on digigraph controls the default index name. When `DIGI_HUB_MODE=federated`, digigraph registers digisearch as a connector tool that the LLM can call directly.

### digiclaw MCP attachment

digiclaw may attach to the digisearch MCP server at `http://127.0.0.1:8765/mcp` (loopback, `digisearch-mcp` Docker profile). Tools available: `digisearch_query`, `web_search` (when `[web-search]` is installed), `digisearch_research_turn` (when `[agent]` is installed).

MCP clients (Langflow, IDE tools) attach to the same server. There is no per-client auth on the MCP server itself — access control is purely at network level (loopback binding).

### digiclaw monitor tick (#4065)

The heartbeat profile's `web-watch-tick` agent (`digiclaw/agents/web-watch-tick.yaml`,
continuous 60s) drives scheduled watches through
`digiclaw/src/digiclaw/monitors_tick.py::run_due_monitors`, which POSTs
`{DIGISEARCH_URL}/v1/monitors/tick` (compose: `http://digisearch:8002`) with a
digikey service JWT minted by the landed
`digibase.service_auth.get_service_jwt(key_env="DIGICLAW_DIGIKEY_API_KEY",
digikey_url_env="DIGIKEY_URL", scopes=("digisearch:query",))`. Transport and
auth failures raise, so the scheduler records the agent's `last_error` (never a
silent successful tick) and `digiclaw schedule tick` prints the failed outcome.
The route calls `tick_due_watches` directly (the route itself is the tick);
per-watch failures come back inside the `{"runs": [...]}` payload and are
counted by the digiclaw helper as `failed`. Compose wiring and the
poll-vs-public-webhook ops choice are in §10.

### digiflow integration

digiflow (Langflow) connects at `http://digisearch:8002` (HTTP) or MCP. Standard `POST /query` with `format=table` for display-ready results. digiflow can also import the `digisearch` Python client directly if running in the same process.

### Sidecar YAML metadata loading

At ingest time (both `POST /ingest` and CLI `digisearch ingest`), digisearch looks for a sidecar file at `{stem}.yaml` or `{stem}.yml` next to the source file. The sidecar `metadata:` block (or flat normative keys at root) is loaded first, then merged with parser-extracted metadata, then with the request body `metadata` field. The request body wins on conflicts.

This allows a document corpus to be annotated with evidence tier, DOI, venue, and tags without embedding metadata in the document itself.

### `DIGI_EXTRACT_STRATEGY_AFTER_DOCUMENT_RAG`

When `DIGI_EXTRACT_STRATEGY_AFTER_DOCUMENT_RAG=1` is set on digigraph, digigraph performs structured extraction of `strategy_name` and `symbols` after receiving RAG context from digisearch. This is a digigraph concern — digisearch is unaware of it.

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

### searxng + valkey sidecar (#3853)

The `searxng` service (`searxng/searxng`) is loopback-only on the host (`127.0.0.1:8080`) with config at `config/searxng/settings.yml` (`search.formats: [html, json]`, engine allowlist). `valkey` backs its limiter. digisearch reaches it in-container via `DIGISEARCH_SEARXNG_URL=http://searxng:8080`. No new digisearch port: `POST /v1/web_search`, MCP `web_search`, and orchestrator `web_search` all ride the existing apps.

Rollout ops: single flag `DIGISEARCH_WEB_SEARCH_BACKEND=auto|searxng|ddgs` (default `auto`); a down sidecar or a ddgs 403/CAPTCHA fails over to the next backend, and the digigraph `web` skill stays corpus-only unless the session opts in (#3420) — fail-closed to corpus-only at every layer. Engine allowlist is `wikipedia, duckduckgo, bing, mojeek`; `search.formats` must keep `json` (the provider calls `/search?format=json`). `server.secret_key` ships as a dev-only placeholder — rotate before exposing beyond loopback. Upstream scrapers break without notice: `compose pull searxng` weekly, and watch per-engine 403/CAPTCHA rates as the early signal; grounding stays tool-only for the default corpus path (#3859), with the Phase B exception that an explicitly requested `source=web|auto` research turn runs OSS synthesis (see §3 `POST /v1/research_turn` web branch, #4064). Eval: `digisearch/tests/test_web_search_eval.py` (20 queries across news/macro/docs/earnings, mocked offline; live sampling behind `DIGISEARCH_WEB_SEARCH_LIVE=1` with p50 fetch+extract < 5s) plus `tests/ds/test_web_eval_live.py` (Phase B research-turn cases, mocked offline; same live gate). Known limitation: digiquant→hub calls carry the Task-1 service JWT (bearer threads via `ToolContext.state["digi_bearer"]`); legs without a token fail closed with `DashboardWebSearchError`, never silently ungrounded.

Live verification record (2026-09-11, #3859 Task 10 — honest not-measured + what remains):

- Sidecar: `docker compose up -d searxng valkey` exited 0; `digi-searxng` and
  `digi-searxng-valkey` both `Up (healthy)`. But every `GET /search` variant
  returns HTTP 429 `Too Many Requests` with zero rows: plain GET, GET with
  browser UA, GET with `X-Forwarded-For`/`X-Real-IP`, the provider-identical
  param set (`q/pageno/language/safesearch`), POST with form fields, first
  request after `docker compose restart searxng`, and first request after
  `valkey-cli flushdb`. `/` and `/healthz` return 200, so only the search
  plane is blocked. Container log shows `server.limiter: true` (from
  `config/searxng/settings.yml`) combined with `missing config file:
  /etc/searxng/limiter.toml` plus `X-Forwarded-For nor X-Real-IP header is
  set!` — the stock limiter denies search outright in this environment, with
  or without forwarding headers. No repo change made for this; unblocking
  needs an owner decision (ship a `limiter.toml`, or set `limiter: false` for
  the loopback-only sidecar — either is a config change with review).
- Image digest pin: `searxng/searxng:latest` resolved 2026-09-11 to image ID
  `2fb0fa85096f`, digest `sha256:2fb0fa85096fe6df5c3ab98ecb4d6e0ee2ef66b8fb96ce6fce0f75b51c4bd90a`
  (searxng `2026.9.10-931fd9787`). `server.secret_key` is still the dev-only
  placeholder — rotate before exposing beyond loopback (unchanged).
  Owner decision (#3871): searxng floats on latest — the digest above is a
  recorded observation, not an enforced pin; enforcing a digest pin is a
  networked ops follow-up (owner-side).
- Eval live leg: skipped-with-reason (gate: sidecar must return rows; it
  returns 429, so no p50/quality measured). Supplementary offline evidence on
  this branch: `pytest digisearch/tests/test_web_search_eval.py -v` → 3
  passed, 3 skipped (live leg behind `DIGISEARCH_WEB_SEARCH_LIVE=1`; two
  extractor legs skip — `trafilatura` from the `[web-search]` extra is not
  installed in this env), zero `Traceback`. p50 fetch+extract < 5s and
  quality sampling remain unmeasured until the limiter is resolved.
- Pipeline e2e: blocked — `DIGIQUANT_DIGIKEY_API_KEY` is absent from both the
  environment and `.env`. Owner unblock (plan Task 8 ops note): `python -m
  digikey.cli issue-key --tenant digiquant-pipeline --label pipeline --scopes
  digisearch:query --kind standard`, then store as `DIGIQUANT_DIGIKEY_API_KEY`
  in `.env` + compose passthrough. Offline fail-closed evidence instead (all
  on this branch, zero `Traceback`): `test_web_search_service.py` +
  `test_web_search_mcp_config.py` → 10 passed (bad-backend raises
  `WebSearchConfigError`, MCP returns a clean `[web_search unavailable:]`
  message); `tests/ds/test_orchestrator_invoke.py` bad-backend legs → 2
  passed (`ok: False` on orchestrator invoke, HTTP 503 on `POST
  /v1/web_search`); `tests/dq/research/data/test_web_grounding.py` → 14
  passed (`DashboardWebSearchError` on empty/tool-error/blank-summary,
  service-JWT bearer threading, `ServiceAuthError` propagation).
- Browser checks: not attempted — `frontend/digichat/.env.local` is absent
  and the full stack (digigraph/digisearch on this branch) is not running, so
  a bare `next dev` could not exercise web-cite paths. Remains: baseline
  `/embed` zero-click check (web cites without toggle) + datatap embed check
  (no toggle, no web cites) against a running stack.
- Gemini traffic delta: not measured (no live run yet) — record after the
  live eval + pipeline e2e above go green.

### Environment variables reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `CHROMA_PATH` | _(unset)_ | Path to persistent Chroma data directory; activates Chroma backend |
| `CHROMA_HOST` | _(unset)_ | Chroma HTTP server host; activates Chroma backend (remote mode) |
| `CLOUDFLARE_ACCOUNT_ID` | _(unset)_ | Cloudflare account id owning both the Vectorize indexes and the D1 databases (canonical, #2239 credential rename); with `CLOUDFLARE_API_TOKEN`, activates Vectorize and takes priority over Chroma. Falls back to legacy `VECTORIZE_ACCOUNT_ID`, then `D1_ACCOUNT_ID`, when unset. |
| `CLOUDFLARE_API_TOKEN` | _(unset)_ | Cloudflare API token for the Vectorize v2 REST API (same token also authorizes D1). Falls back to legacy `VECTORIZE_API_TOKEN`, then `D1_API_TOKEN`, when unset. |
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
| `DIGISEARCH_RETRIEVAL_BACKEND` | `pgvector` | `pgvector` \| `lightrag` — document-level RetrievalBackend (#402) |
| `DIGISEARCH_DATABASE_URL` | _(unset)_ | Postgres DSN for PgvectorBackend / LightRAG PG storage |
| `DIGISEARCH_PGVECTOR_URL` | _(unset)_ | Optional alias; wins over `DIGISEARCH_DATABASE_URL` |
| `DIGISEARCH_LIGHTRAG_EMBEDDING` | `ollama` | `ollama` (nomic-embed-text) \| `minilm` (local ONNX) |
| `DIGISEARCH_LIGHTRAG_WORKING_DIR` | `.lightrag` | LightRAG working directory |
| `DIGISEARCH_RERANK_ENABLED` | `0` | When truthy, `query_index()` runs `Reranker` over results (`top_n=query.top_k`); off by default (#2441). Does **not** gate the Phase B web branch, which always requires the `[rerank]` extra (#4064) |
| `DIGISEARCH_RERANK_PROVIDER` | `bge` | `bge` (`BAAI/bge-reranker-v2-m3`) or `cohere` (`rerank-multilingual-v3.0`) when rerank is enabled |
| `DIGISEARCH_WEB_SEARCH_BACKEND` | `auto` | `auto` (searxng→ddgs failover) \| `searxng` \| `ddgs` (#3853) |
| `DIGISEARCH_SEARXNG_URL` | `http://127.0.0.1:8080` | searxng sidecar base URL (compose sets `http://searxng:8080` in-container; #3853) |
| `DIGISEARCH_FETCH_ALLOWED_HOSTS` | _(unset)_ | Comma-separated operator-trusted hostnames exempted from the digifetch SSRF address refusal (e.g. an egress proxy). Also accepted per-call via `WebSearchConfig.fetch_allowed_hosts`; passed to `HttpFetcher(allowed_hosts=…)` (#3934) |
| `DIGISEARCH_WEB_SEARCH_LIVE` | _(unset)_ | Set `1` to run the live-sampled legs of `digisearch/tests/test_web_search_eval.py` (provider suite, real backends, p50 fetch+extract < 5s) and `tests/ds/test_web_eval_live.py` (Phase B research-turn cases, p50 stage ms + citation coverage scaffolding, never SLOs); default runs fully mocked offline (#3853, #4064) |
| `DIGISEARCH_WEBSETS_LIVE` | _(unset)_ | Set `1` to run the live leg of `tests/ds/test_websets_live.py` (real searxng/ddgs recall + digillm verify/enrich; prints the Phase D record — timings, event multiset, s5 funding deltas, CSV shape — never SLOs); also needs `DIGISEARCH_VERIFY_MODEL`/`DIGISEARCH_ENRICH_MODEL` + a provider key; default runs fully offline (#4066) |
| `DIGISEARCH_WEBSETS_DB` | _(unset)_ | Explicit SQLite path for the Phase D webset store; wins over the `DIGI_WORKSPACE` default and the cwd fallback (#4066) |
| `DIGISEARCH_VERIFY_MODEL` | _(unset)_ | digillm model id for `llm`-mode webset verification; unset ⇒ verification settles `rejected` (fail closed, never admitted) (#4066) |
| `DIGISEARCH_ENRICH_MODEL` | _(unset)_ | digillm model id for webset enrichment; unset ⇒ every field settles `unresolved` (fail closed, never guessed) (#4066) |
| `DIGISEARCH_SYNTHESIS_MODEL` | _(unset)_ | digillm model id for Phase B web-research synthesis (`source=web\|auto` turns only). Unset ⇒ every web turn fails hard with `WebResearchError`, never an uncited answer; no new port/service (#4064) |
| `DIGISEARCH_CACHE_PATH` | `.digisearch_embed_cache.db` | SQLite embedding cache path |
| `DIGISEARCH_EMBED` | `1` (on when unset) | Set `0` to skip pipeline-level embed on ingest |
| `DIGISEARCH_EMBEDDING_PROVIDER` | _(unset)_ | `minilm` \| `openai` — explicit provider (fails loud if unloadable) |
| `DIGISEARCH_EMBED_CACHE` | `1` | Wrap BatchEmbedder in EmbeddingCache |
| `DIGISEARCH_EMBED_BATCH_SIZE` | `100` | BatchEmbedder batch size |
| `DIGISEARCH_EMBEDDING_MODEL` | _(unset)_ | Active embedding model id (OpenAI model or versioning) |
| `DIGISEARCH_EMBEDDING_DIM` | `1536` | Vector dimension for versioning |
| `DIGISEARCH_EMBEDDING_VERSION` | `1` | Logical version for index migration |
| `OPENAI_API_KEY` | _(unset)_ | OpenAI API key for OpenAIEmbedder |
| `COHERE_API_KEY` | _(unset)_ | Cohere key for CohereEmbedder / CohereReranker |
| `DIGI_CORS_ORIGINS` / `DIGISEARCH_CORS_ORIGINS` | (empty) | Comma-separated CORS allowed origins; legacy `DIGI_ALLOWED_ORIGINS` still honored |
| `DIGI_DISABLE_RATE_LIMIT` | `0` | Disable per-IP rate limiting (testing) |
| `DIGIKEY_JWKS_URL` | _(required)_ | digikey JWKS endpoint for JWT validation |
| `DIGIKEY_ISSUER` | _(required)_ | JWT issuer |
| `DIGIKEY_AUDIENCE` | _(required)_ | JWT audience |
| `DIGI_WORKSPACE` | _(unset)_ | Workspace root; with no `DIGISEARCH_MONITORS_DB`, the monitor store resolves to `{DIGI_WORKSPACE}/.digisearch/monitors.sqlite3` (#4065) |
| `DIGISEARCH_MONITORS_DB` | _(unset)_ | Explicit SQLite path for the Phase C monitor store; wins over the `DIGI_WORKSPACE` default and the cwd fallback (#4065) |
| `DIGISEARCH_SMTP_HOST` | _(unset)_ | SMTP relay host for monitor email delivery; unset (or no usable from-address) ⇒ `smtp_not_configured` receipt |
| `DIGISEARCH_SMTP_PORT` | `587` | SMTP relay port; a non-numeric value is treated as unconfigured |
| `DIGISEARCH_SMTP_USER` | _(unset)_ | SMTP username; login happens only over STARTTLS, else `smtp_tls_unavailable` when credentials are set |
| `DIGISEARCH_SMTP_PASS` | _(unset)_ | SMTP password; treat as sensitive — receipt redaction (`_redacted_error`) strips the per-watch delivery secret and target URL today, not this value |
| `DIGISEARCH_SMTP_FROM` | falls back to `DIGISEARCH_SMTP_USER` | From address for monitor email delivery; host + from must both resolve or email is a failed receipt |

### Phase C monitors ops record (#4065)

Compose persistence: the digisearch service sets `DIGI_WORKSPACE=/data/monitors`
and mounts the `digisearch_monitors` named volume at the same path, so the store
lives at `/data/monitors/.digisearch/monitors.sqlite3` and monitor history plus
dedup memory survive container recreate:

```yaml
    environment:
      - DIGI_WORKSPACE=/data/monitors
    volumes:
      - digisearch_monitors:/data/monitors
```

The heartbeat service is the scheduler side: `DIGISEARCH_URL=http://digisearch:8002`,
`DIGICLAW_AGENTS_DIR=/workspace/digiclaw/agents` (the read-only repo mount; the
image ships no `agents/`), `DIGICLAW_SCHEDULER_STATE=/state/scheduler_state.json`
on the `digiclaw_state` volume, and the bootstrap-then-loops command — `digiclaw
schedule start web-watch-tick || exit 1` (idempotent when already running; `||
exit 1` catches only real bootstrap failures), the preserved 1800s heartbeat in
the background, and the 60s tick loop in the foreground. See
`digiclaw/ARCHITECTURE.md` §3 for the tick caller.

Tunnel-or-poll: local development uses delivery mode `poll` plus the manual
`POST /v1/monitors/{watch_id}/trigger`, which needs no inbound path and is the
portable loop that works on both the `oss` and `exa` backends. Public webhooks
require digisearch to be reachable from the internet; expose it via Cloudflare
Tunnel or Tailscale per `SECURITY.md` (never a public port), with webhook/slack
targets validated as public https URLs at create/update and re-resolved at
delivery time. The inbound EXA result webhook authenticates with the watch's
stored per-monitor secret (EXA's one-time `webhookSecret`, captured at
`POST /v1/monitors` create for `backend="exa"` watches — #4184 — and never
rotatable locally: `PATCH {"rotate_delivery_secret": true}` is refused 409 for
them), verified as the `exa-signature` `t.body`
HMAC (#4123); a valid signature translates the nested payload via the
live-pinned Task 8c adapter and persists the run to the monitor store, while
any parseable non-terminal status is acked without persisting. The remote-first
create persists the `webhookSecret` itself, so no out-of-band
`MonitorStore.set_delivery_secret` step is needed for watches created through
the HTTP route. Poll + manual trigger remains the portable route for EXA-backed
watches.

### MCP server startup

The MCP server is started via `digisearch mcp --port 8765` (CLI) or the `digisearch-mcp` Docker profile. Default transport: streamable HTTP. The server runs `FastMCP("digisearch")` from the `mcp` package.

In the current implementation, `_digisearch_client` is only set by calling `create_mcp_with_indexes(client)` explicitly. The `mcp_server.py` module-level setup does not call this automatically — tools fall back to the stub unless caller code wires the client at startup.

---

## 11. Phase 2+ Gaps and Roadmap

### Internal agent graph (`[agent]` extra)

The `digisearch[agent]` optional extra installs `langgraph` and enables:

- `digisearch_research_turn` MCP tool
- `digisearch_research_delegate` orchestrator tool
- `POST /v1/research_turn` REST endpoint
- The `agent/pipeline.py` LangGraph: `plan → retrieve → aggregate` (corpus) and `plan → web_retrieve → web_aggregate` (Phase B web branch, `source=web|auto`; #4064)

The corpus graph is still minimal: `node_plan` validates input, `node_retrieve` calls `query_index`, `node_aggregate` formats results and extracts citations. There is no query reformulation, no multi-step retrieval, and no LLM calls on the corpus path. The Phase B web branch (`source=web|auto` → `web_retrieve → web_aggregate`) adds live OSS retrieval plus digillm synthesis with inline citations — see §3 `POST /v1/research_turn` (#4064). The `[agent]` label is justified by that web path; the corpus path remains the minimal chain above.

**Roadmap:** A full research-turn graph would include LLM-based query decomposition, sub-query expansion, result deduplication, evidence gap detection, and iterative retrieval.

### Multi-tenant enforcement

`workspace_id` exists in the data model. Enforcement status per backend:

- **Chroma:** route to a named collection per workspace (`{workspace_id}_{index_name}`) or inject `{"workspace_id": workspace_id}` as a mandatory `where` clause
- **Azure:** inject an OData filter clause `(workspace_id eq '{workspace_id}')` for all queries
- **Vectorize:** `VectorizeBackend.query()` raises `VectorizeBackendError` when filters / `workspace_id` are present (#2219 fail-loud). Full fix: translate `Query.filters` into Vectorize metadata `filter`, register filterable fields as metadata indexes at index creation, or keep routing to a per-workspace index and omit filters
- **Stub:** filter post-retrieval by `chunk.metadata.get("workspace_id")`

The research path (`POST /v1/research_turn`, orchestrator `digisearch_research_delegate`, MCP `digisearch_research_turn`) applies the same server-side `workspace_id` injection as `POST /query` (#3909).

Without this, `workspace_id` is decorative on backends that neither filter nor fail closed.

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

`Reranker` is wired into `query_index()` behind `DIGISEARCH_RERANK_ENABLED` (default off). BGE uses `BAAI/bge-reranker-v2-m3` (install `digisearch[rerank]`); Cohere stays on `rerank-multilingual-v3.0`. Failures log a warning naming the provider and fall back to the original order. `Query.skip_rerank` / `QueryRequest.skip_rerank` suppress the pass for `digisearch_fetch_all` pages that share the same `run_query` → `query_index` chain.

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

**Problem:** `GET /health` always returns 200 regardless of backend state. digigraph and monitoring cannot distinguish "service up but backend offline" from "fully healthy."

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

**Status (Chroma, #2437):** Implemented for the Chroma backend. `ChromaBackend`
writes `embedding_model_id`, `embedding_dimensions`, and `embedding_version` into
collection metadata (on create and stamped on first `add` for legacy
collections). Construction against an existing collection whose stored
`embedding_model_id` differs from the active provider raises before any
query/add. Azure / Vectorize still rely on their own guards
(`scripts/vectorize_sync.py` `assert_index_model` probes per-vector metadata).

**Problem (historical):** When the embedding model changes (e.g. from
`text-embedding-3-small` to `text-embedding-3-large`), vectors in the index are
incompatible. There was no mechanism to detect this or trigger a re-index. The
`EmbeddingModelSpec` version string was tracked but not enforced at query time.

**Remaining:**

1. Persist the same three fields on Azure index document schema
2. Optionally gate mismatch with `DIGISEARCH_STRICT_VERSION_CHECK=1` for soft vs hard fail
3. Provide a `digisearch index reembed --index <name>` CLI command that re-embeds and upserts all chunks under the new model

The `EmbeddingModelSpec.version` field in `embeddings/config.py` remains the
env-config anchor; Chroma now also persists the active provider's identity on
the collection itself.

## Observability

This service exposes a Prometheus `/metrics` endpoint (counter, histogram, in-flight gauge for every HTTP route) via `digibase.metrics.install_metrics`; scraped by the `observability` compose profile per [ADR-0003](../docs/adr/0003-observability-baseline.md).

### Structured logging (#215)

All digisearch entrypoints (`server.py`, `mcp_server.py`, `ingest_worker.py`) call `digisearch.logging.configure_logging()` at startup. The helper installs a `python-json-logger` stream handler on the root logger that renames `asctime`/`levelname` to `timestamp`/`level`, stamps every record with `service="digisearch"`, and attaches the `RequestIdLogFilter` from `digibase.http` (#213) so `request_id` is always present (defaults to `"-"` outside a request).

Every record emitted by a digisearch hot path includes the following JSON keys:

| Key | Source |
| --- | --- |
| `timestamp` | `%(asctime)s` (ISO-ish) |
| `level` | `INFO` / `WARNING` / `ERROR` |
| `service` | always `"digisearch"` |
| `request_id` | `X-Request-ID` ContextVar or `"-"` |
| `operation` | call-site `extra={"operation": ...}` |
| `duration_ms` | call-site, integer milliseconds |
| `outcome` | `"ok"` or `"error"` |
| `name` | logger name (module path) |
| `message` | human-readable summary — never raw user query or doc body |

Log level is controlled by the `DIGI_LOG_LEVEL` env var (default `INFO`). `configure_logging()` is idempotent.

Hot paths that emit one operation-level record per call:

- `digisearch.search._stub.query_index` (`operation=query_index`)
- `digisearch.search.hybrid.HybridSearcher.search` (`hybrid_search`)
- `digisearch.search.keyword.BM25Searcher.search` (`bm25_search`) / `TFIDFSearcher.search` (`tfidf_search`)
- `digisearch.search.vector.VectorSearcher.search` (`vector_search`)
- `digisearch.ingestion.parsers.markdown.MarkdownParser.parse` (`parse_markdown`)
- `digisearch.ingestion.parsers.plaintext.PlainTextParser.parse` (`parse_plaintext`)
- `digisearch.ingestion.chunkers.fixed.FixedSizeChunker.chunk` (`chunk_fixed`)
- `digisearch.ingestion.chunkers.recursive.RecursiveChunker.chunk` (`chunk_recursive`)
- `digisearch.embedding.batch.BatchEmbedder.embed` (`embed_batch`)
- `digisearch.indexes.backends.chroma.ChromaBackend.{add,query}` (`chroma_index`, `chroma_query`)
- `digisearch.indexes.backends.azure_search.query_azure` (`azure_query`)

**Privacy rule:** INFO-level records must not contain raw user queries, document bodies, or chunk content — only metadata (doc id, chunk count, vector dim, result count, `top_k`, etc). Errors log at WARNING/ERROR with `exc_info`.

## Input Validation Posture

All HTTP request bodies are typed with Pydantic v2 models using `ConfigDict(extra="forbid")`, which rejects unknown fields with HTTP 422 at the framework boundary. Shared validation-error shape lives in `digibase.errors`.
