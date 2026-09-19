---
type: behavior-guide
title: digisearch Ingest and Index
description: digisearch ingest pipeline — parsing, chunker selection, embeddings with cache, index writes, URL ingest, and monitors integration.
tags: [digisearch, ingest, chunking, embeddings]
sources:
  - id: openwiki-source-d16d9586117b95e03b7f1549
    resource: repo://digisearch/AGENTS.md
  - id: openwiki-source-a355745b35b360f29c006f68
    resource: repo://digisearch/src/digisearch/chunking/factory.py
  - id: openwiki-source-c6b86c2d5bee963efea641a7
    resource: repo://digisearch/src/digisearch/embedding/batch.py
  - id: openwiki-source-b230342b440603a7430466cc
    resource: repo://digisearch/src/digisearch/embedding/cache.py
generated: { by: "openwiki/0.5.0", at: "2026-09-19T12:20:11.463Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-19T12:20:11.463Z
---

# digisearch Ingest and Index

Ingest turns a server-side filesystem path or a remote URL into indexed chunks
with embeddings. Every stage is config-selected through factories — new
parsers register in the `ParserRegistry`, new chunkers go through the
chunking factory, and embedding providers resolve through the embedding
factory, never hardcoded into ingest paths.

## Ingest entry points

Two distinct entry points exist, enforced by AGENTS.md rules:

- **Filesystem ingest** (`pipeline/ingest.py` `ingest_source` / `ingest_paths`)
  accepts a validated server-side path — `POST /ingest`, the Typer CLI, and
  tests all call this single canonical function. No raw URLs are accepted.

- **URL ingest** (`pipeline/url_ingest.py` `ingest_url`) is the separate,
  SSRF-guarded path behind `POST /ingest/url` and `CLI ingest-url`. It
  fetches through `digifetch` (`validate_fetch_url` + `HttpFetcher`),
  extracts markdown via `trafilatura`, stages it as `page.md` in a `0o700`
  temp directory, and delegates to the same `ingest_source` filesystem path.

  The fetcher is owned per-call (closed in a `finally` block) and reuses the
  `web_search` timeout when configured. Unsupported content types are
  rejected fail-closed (text/\* and `application/xhtml+xml` only).

The bulk ingest worker (`ingest_worker.py`, the `digisearch-worker` console
script) **logs and exits** — it is a Phase 2 placeholder. No queue consumer
runs there today.

## Parsing

`ingestion/registry.py` `ParserRegistry` auto-selects a parser by file
extension. All parsers except `PlainTextParser` are lazily imported — a
missing dependency (e.g. no `pdfplumber`) causes that parser to be skipped
at registration time rather than crashing the registry:

- **PDF**: `PDFParser` (OCR fallback via Tesseract / Azure DI / AWS Textract
  when available)
- **DOCX**: `DocxParser`
- **HTML**: `HTMLParser`
- **Markdown**: `MarkdownParser`
- **CSV**: `CSVParser`
- **Plain text**: `PlainTextParser` (always available, universal fallback)

Sidecar YAML metadata files (`.yaml` / `.yml` next to the source) are merged
into the document metadata before chunking. Request-body metadata wins over
both sidecar and parser-discovered metadata.

### Path validation

For `POST /ingest`, `enforce_ingest_root=True` activates path containment
via `digisearch.ingest_paths.resolve_ingest_source`:

1. Resolve `DIGISEARCH_INGEST_ROOT` (defaults to cwd).
2. Resolve the source path (relative paths are joined under the root).
3. Reject with `ingest_source_rejected` / HTTP 400 if the resolved path
   escapes the root.

The CLI passes `enforce_ingest_root=False` and uses `Path.resolve()` directly.

## Chunker selection

`chunking/factory.py` resolves one key through a four-tier precedence chain:

```
explicit name → per-index config chunker: → DIGISEARCH_CHUNKER → "semantic"
```

### Three entry points

| Entry point | Returns | Purpose |
|---|---|---|
| `get_chunker_backend()` | `ChonkieSemanticChunker` (default) or `ChonkieTokenChunker` | Raw text-splitting backends |
| `get_document_chunker()` | `Chunker` (backend + legacy `recursive` / `fixed`) | Document-level chunking for research payloads; no segment wrapper |
| `get_ingest_chunker()` | `SegmentAwareChunker` wrapping a document chunker | Default ingest pipeline — structural segments never cross chunk boundaries |

### Aliases

- **Semantic**: `semantic`, `chonkie`, `chonkie_semantic`, `chonkie-semantic`
- **Token**: `token`, `chonkie_token`, `chonkie-token`
- **Legacy rollback**: `recursive` (→ `RecursiveChunker`), `fixed` (→ `FixedSizeChunker(chunk_size=512)`)

Unknown names raise `ValueError`. Unknown names that aren't legacy fall
through to `BackendDocumentChunker(get_chunker_backend(key))`, which will
raise if the name isn't a recognized backend alias.

### Caching

Three process-level caches (`_backend_cache`, `_document_chunker_cache`,
`_ingest_chunker_cache`) reuse backends across `POST /ingest` calls —
Chonkie `SemanticChunker` construction loads embedding weights (~200 ms+
after first download). `clear_chunker_cache()` drops all caches (used by
tests that monkeypatch constructors).

### Chunking strategy

| When | Chunker | How |
|---|---|---|
| SEC filings, research reports, earnings transcripts, long docs | **semantic** (default) | `DIGISEARCH_CHUNKER=semantic` or omit |
| Short news wires / alerts where latency matters | **token** | `DIGISEARCH_CHUNKER=token` |
| Rollback / characterization | `recursive` / `fixed` | Same env var |

## Embeddings

The embedding pipeline is assembled by
`digisearch.embedding.factory.resolve_embedding_pipeline` and produces the
layered stack:

```
EmbeddingCache → BatchEmbedder → EmbeddingProvider (minilm / openai)
```

`DIGISEARCH_EMBED=0` (or `false`/`no`) disables the pipeline-level embed
step — backends may still embed via their own injected providers. When unset,
embedding defaults to **on**. An explicit provider config that cannot be
loaded raises `EmbeddingConfigError` — never a silent no-op.

### Provider selection

Resolution order:

1. `DIGISEARCH_EMBEDDING_PROVIDER` env var (+ optional `DIGISEARCH_EMBEDDING_MODEL`)
2. Non-empty `embedding:` block in `DigiSearchConfig` (`DIGISEARCH_CONFIG_PATH`)
3. Default `minilm` when a vector backend (Chroma / Vectorize / stub) is configured

Supported providers:

- **minilm** (aliases: `local`, `onnx`): `all-MiniLM-L6-v2` (384-dim) via
  chromadb's bundled ONNX runtime. A process-wide singleton
  (`get_default_minilm_embedder()`) is shared by Chroma/Vectorize
  construction sites.
- **openai** (alias: `oai`): `text-embedding-3-small` by default, overridable
  via `DIGISEARCH_EMBEDDING_MODEL`. Requires `OPENAI_API_KEY`.

`resolve_backend_embedding_provider()` returns the raw provider (no cache
wrap) for Chroma/Vectorize construction, using the same env/config resolution
so query-time and ingest-time models stay aligned.

### BatchEmbedder

`BatchEmbedder` wraps the underlying provider with batching (default 100,
configurable via `DIGISEARCH_EMBED_BATCH_SIZE`), exponential-backoff retry
(max 3 attempts with configurable delay), and structured logging. It retries
on `OSError`, `RuntimeError`, `TimeoutError`, `ValueError`, and `TypeError`.

### EmbeddingCache

`EmbeddingCache` wraps the provider with a SQLite-backed content-hash cache
at `DIGISEARCH_CACHE_PATH` (default `.digisearch_embed_cache.db`). Cache keys
are `sha256(model_namespace\0text)`, making them **model-namespaced** — a
model swap automatically invalidates all prior hits.

A single batched `SELECT ... WHERE hash IN (...)` query retrieves cached
embeddings, then the provider computes only the missing vectors. The cache is
**enabled by default**; set `DIGISEARCH_EMBED_CACHE=0` to bypass it.

### Partial-batch refusal

`pipeline/ingest.py` `apply_embeddings()` rejects partial batches:

- If only some chunks carry embeddings → `ingest_embed_partial` error
  (all or none required).
- If the embedder returns a vector count mismatch → `ingest_embed_mismatch`.
- `EmbeddingCache.embed()` verifies every position is filled after
  computation; any gap raises `ValueError`.

## Index writes

### Backend routing

`index_chunks` in `pipeline/ingest.py` resolves the embedding pipeline (if
`auto_embed` and no explicit provider), applies embeddings, then delegates to
`route_add_chunks` in `search/_stub.py`:

```
Vectorize → Chroma (HTTP host) → Chroma (filesystem path) → stub → RuntimeError
```

| Backend | Condition | Return |
|---|---|---|
| Vectorize | `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` | `"vectorize"` |
| Chroma (host) | `CHROMA_HOST` without `CHROMA_PATH` | `"chroma"` |
| Chroma (path) | `CHROMA_PATH` | `"chroma"` |
| Stub | `DIGISEARCH_ALLOW_STUB=1` (tests only) | `"stub"` |
| None | No backend configured | `RuntimeError` |

Every `ChromaBackend` construction passes an explicit `embedding_provider`
via `_resolved_embedding_provider()` → `resolve_backend_embedding_provider()`
— the Chroma client's bundled ONNX embedding path is never relied upon.

### Ingest source flow

`ingest_source` runs the full sequence:

1. **Resolve path** (with optional `DIGISEARCH_INGEST_ROOT` containment)
2. **Parse** via `ParserRegistry`
3. **Merge sidecar YAML** + request-body metadata (request wins)
4. **Chunk** via `get_ingest_chunker` (segment-aware wrapper)
5. **Index** via `index_chunks` (auto-resolves embed pipeline unless
   `DIGISEARCH_EMBED=0` or explicit `embedding_provider` passed)
6. Return `IngestResult(doc_id, chunks_created, index_name, backend, source)`

Runtime errors from the backend are wrapped in `IngestError` with stable
codes: `ingest_backend_unavailable` (HTTP 503), `ingest_dependency_missing`
(503), or generic `ingest_failed` (503). `ingest_source_not_found` returns
HTTP 404.

`ingest_paths` batch-walks every supported file under a list of paths,
skipping errors by default (`skip_errors=True`), and returns
`(total_chunks, results)`.

### Research pipeline

Research flat payloads use `research_ingest.py` — they call
`get_document_chunker()` (no segment wrapper, stable research chunk ids) but
share `index_chunks` for the final backend write. The `RuntimeError`
contract from `route_add_chunks` propagates unchanged to research callers.

## Monitoring integration

Phase C monitors (`digisearch.monitors`) run scheduled web-search watches
that recall, deduplicate, persist, and deliver results. Monitors do **not**
directly call the chunk/embed/index pipeline.

The C→D bridge (`monitors.runner.handoff`) connects monitor runs to the
websets subsystem: an `ok` run on a watch carrying a `bridge` config opens
one search generation on the target webset via `websets.service.handoff_from_watch`
— an in-process call, not loopback HTTP. The websets store's
`(watch_id, run_id, webset_id)` ledger makes repeat deliveries idempotent.

`POST /v1/monitors/tick` drives the scheduler pass (`tick_due_watches`),
evaluating every enabled watch (cron or interval) and running due ones with
isolated per-watch failure handling.

## Configuration summary

| Variable | Purpose |
|---|---|
| `DIGISEARCH_CHUNKER` | Chunker backend: `semantic` (default) or `token` |
| `DIGISEARCH_INGEST_ROOT` | Filesystem jail for `POST /ingest` sources |
| `DIGISEARCH_EMBED` | `0`/`false`/`no` disables pipeline-level embedding |
| `DIGISEARCH_EMBEDDING_PROVIDER` | Provider: `minilm`, `openai` |
| `DIGISEARCH_EMBEDDING_MODEL` | Override model (e.g. `text-embedding-3-large`) |
| `DIGISEARCH_EMBED_BATCH_SIZE` | Batch size (default 100) |
| `DIGISEARCH_EMBED_CACHE` | `0` to bypass `EmbeddingCache` (enabled by default) |
| `DIGISEARCH_CACHE_PATH` | SQLite cache file (default `.digisearch_embed_cache.db`) |
| `DIGISEARCH_ALLOW_STUB` | `1` enables in-memory stub backend (tests only) |
| `DIGISEARCH_CONFIG_PATH` | YAML config with per-index `chunker:` and `embedding:` blocks |
