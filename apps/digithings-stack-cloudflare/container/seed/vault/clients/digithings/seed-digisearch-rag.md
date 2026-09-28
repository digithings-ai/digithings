---
title: digisearch Chroma RAG
tags: [digithings, seed, digisearch, rag]
---

# digisearch Chroma RAG

Pipeline: parse → chunk (~512) → embed → named Chroma collection → query.

Indexes: `digithings_docs` (default chat), `occ_help` (OCC tenant). Collections
are isolated under `CHROMA_PATH`. Chunk metadata should include `source` / `path`
/ `title` for readable Sources citations.
