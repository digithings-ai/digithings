---
type: quickstart
title: digisearch Quickstart
description: Run digisearch stub ingest and query smokes via CLI, verify health, and run the unit suite.
tags: [digisearch, quickstart]
sources:
  - id: openwiki-source-d16d9586117b95e03b7f1549
    resource: repo://digisearch/AGENTS.md
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# digisearch Quickstart

digisearch (port 8002) retrieval works against real backends (Chroma,
Azure, Vectorize) in production. For a zero-dependency smoke, the
in-memory stub backend covers CLI and unit flows — **test-only, never
production** (`_require_real_search_backend` enforces this at startup).

## 1. Stub smokes

```bash
DIGISEARCH_ALLOW_STUB=1 digisearch ingest --index test digisearch/devdata/edgar_sample/
DIGISEARCH_ALLOW_STUB=1 digisearch query --index test --text "revenue growth"
```

## 2. Service and tests

```bash
make stack-local     # digisearch on :8002 (or make up)
curl -s http://localhost:8002/health
pytest tests/ -m unit -k "digisearch" -v
pytest -m unit -k chunking -v
ruff check digisearch/ && ruff format --check digisearch/
```

Production needs a real backend: `CHROMA_PATH` for Chroma,
`AZURE_SEARCH_*` for Azure, plus an embedding provider key.

## Where next

- [digisearch Architecture](/openwiki/digisearch/architecture.md) —
  pipeline, backends, vertical role.
- [digisearch Ingest and Index](/openwiki/digisearch/ingest-and-index.md) —
  parsing, chunking, embeddings.
- [digisearch Query and Operations](/openwiki/digisearch/query-and-operations.md) —
  retrieval, scopes, container.
