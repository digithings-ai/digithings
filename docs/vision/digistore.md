---
title: DigiStore
type: module
status: reviewed
created: 2026-04-19
tags:
  - roadmap
  - storage
relevance:
  - digivault
---
# DigiStore

> The storage abstraction layer — one interface for every backend, from SQLite to Supabase to S3.

**What it is:** DigiStore is the unified storage abstraction layer for the DigiThings ecosystem. Every module that needs to persist data does so through DigiStore — which means the underlying storage backend can change without touching application code. DigiStore sits beneath DigiSearch (which indexes its contents) and above every specific storage technology.

**The problem:** AI applications typically couple directly to specific storage solutions — Postgres queries hardcoded, S3 calls scattered through services, vector store SDK calls mixed into business logic. When requirements change (different client, different scale, different region), the coupling makes migration expensive. DigiStore decouples storage intent from storage implementation.

**Architecture — one interface, multiple backends:**
- SQLite: local development, zero setup, no services required
- Postgres (Supabase, Neon with auto-scaling): production relational storage
- S3 / MinIO: file and blob storage (research documents, exports, strategy files). MinIO runs in Docker locally and is S3-API-compatible for cloud deployment.
- pgvector: vector storage embedded in Postgres/Supabase — no separate vector DB required for simpler use cases
- Extensible: new backends added via config, not code changes

**Local dev docker stack:** SQLite + MinIO + local Postgres — full suite, zero cloud dependency.
**Production:** Supabase (primary) + S3-compatible cloud storage.

**What gets stored where:**
- Research documents, strategy exports, large artifacts → S3/MinIO
- Structured data (thesis, portfolio weights, backtest results, user profiles, investment preferences) → Postgres/Supabase
- Conversations, session artifacts, caches → SQLite (local) or Postgres (production)

**Relationship to OpenBB:** OpenBB is the data retrieval layer (fetches live data from ~100 sources). DigiStore persists, caches, and serves what OpenBB retrieves. DigiStore does not replace OpenBB — it wraps it.

**Current state:** Exists as a thin session/dataset cache inside DigiGraph (Digistore). Expanded scope defined but not yet implemented as a standalone module.

**12-month roadmap:**
- Standalone DigiStore module with clean backend registry
- Full Supabase integration (strategies, research library, user profiles, Atlas data)
- MinIO/S3 integration for file storage
- OpenBB integration as the data retrieval layer
- Dockerized local dev stack (SQLite + MinIO + Postgres)

**Open source vs. proprietary:** Entirely open. Storage infrastructure is a commodity — no proprietary components.
