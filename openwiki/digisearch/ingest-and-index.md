---
type: behavior-guide
title: digisearch Ingest and Index
description: digisearch ingest behavior — parsing, chunker selection, embeddings with cache, and index writes.
tags: [digisearch, ingest, chunking, embeddings]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-d16d9586117b95e03b7f1549
    resource: repo://digisearch/AGENTS.md
  - id: openwiki-source-a355745b35b360f29c006f68
    resource: repo://digisearch/src/digisearch/chunking/factory.py
  - id: openwiki-source-c6b86c2d5bee963efea641a7
    resource: repo://digisearch/src/digisearch/embedding/batch.py
  - id: openwiki-source-b230342b440603a7430466cc
    resource: repo://digisearch/src/digisearch/embedding/cache.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digisearch Ingest and Index

Ingest turns a server-side filesystem path into indexed chunks with
embeddings. Every stage is config-selected through factories — new
parsers register in the `ParserRegistry`, new chunkers go through the
chunking factory, never hardcoded into ingest paths.

## Parsing

`ingestion/parsers/` (behind `registry.py`) handles PDF, DOCX, HTML,
Markdown, CSV, and plain text, with OCR fallback (Tesseract / Azure DI /
AWS Textract) and sidecar YAML metadata merge. `POST /ingest`'s `source`
is a **server-side path**, validated before opening (no traversal, no
raw URLs without a fetch sandbox).

## Chunker selection

`chunking/factory.py` resolves one key — explicit name → per-index
`chunker:` → `DIGISEARCH_CHUNKER` → default `semantic` — through three
entry points:

- `get_chunker_backend()` — `ChonkieSemanticChunker` (default) or
  `ChonkieTokenChunker`; unknown names raise `ValueError`.
- `get_document_chunker()` — backend plus legacy `recursive`/`fixed`
  names for rollback and characterization.
- `get_ingest_chunker()` — the ingest default: `SegmentAwareChunker`
  wrapping the selected backend so structural segments never cross chunk
  boundaries; research flat payloads use the document chunker without the
  segment wrapper.

Backends cache per key. Use `token` for short news-wire latency,
`semantic` (default) for long filings and reports.

## Embeddings

`BatchEmbedder` batches texts to the configured `EmbeddingProvider`
(OpenAI / Azure / Cohere / HuggingFace / Ollama) fronted by
`EmbeddingCache` (SQLite, model-namespaced, content-hashed) so re-ingests
don't re-pay. Partial batches raise — supplied vectors are never silently
discarded.

## Index writes

`DigiIndex.add()` persists chunks + embeddings to the configured backend.
The bulk `ingest_worker.py` is a stub (logs and exits) until Phase 2 —
no queue consumer there.
