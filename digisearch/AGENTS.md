# Agent Guide: DigiSearch

## Purpose

DigiSearch is the centralized RAG and document-search vertical. It owns the complete retrieval pipeline: ingest → parse → chunk → embed → index → query → rerank, and exposes that pipeline via HTTP REST, MCP, CLI, and the orchestrator-tool manifest that DigiGraph consumes.

---

## Read First

In this order, before writing any code:

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — full pipeline, API surface, data models, backend strategy, security analysis
2. [`../AGENTS.md`](../AGENTS.md) — non-negotiable stack-wide rules
3. [`../ROADMAP.md`](../ROADMAP.md) — do not add new index backends beyond Chroma/Azure without Phase 2 sign-off
4. [`../docs/agent-backlog/INDEX.md`](../docs/agent-backlog/INDEX.md) — current task queue

---

## Pre-Flight Checklist

Before making any change to `digisearch/`:

- [ ] Read the `ARCHITECTURE.md` section for the area you're touching (ingestion, embedding, search, server, MCP)
- [ ] Run `pytest tests/ -m unit -k "digisearch" -v` — passes before and after
- [ ] Run `ruff check digisearch/ && ruff format --check digisearch/` — zero errors
- [ ] Confirm no `import pandas` anywhere (Polars-only; DigiSearch has no Nautilus boundary exception)
- [ ] Confirm `DIGISEARCH_ALLOW_STUB=1` is never set in production code paths
- [ ] Confirm `GET /azure_status` stays behind `digisearch:query` via `DigiAuthMiddleware` (not public)
- [ ] Confirm any new ingest path validates the `source` path before opening it (no path traversal)

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **Backend registry only**: New index backends must register via `search/_stub.py` returning `None` when not configured. Never add `if backend == "x":` dispatch logic directly in the query path.
- **No production stub**: `DIGISEARCH_ALLOW_STUB=1` is for unit tests only. `_require_real_search_backend()` enforces this at startup — do not bypass it.
- **Entity naming**: Class and model names drop the `Digi` prefix: `Document`, `Chunk`, `Query`, `Result` — not `DigiDocument`. Follow this for all new models.
- **Structured filters over raw OData**: New query callers must use `filters: list[dict]` not raw `filter: str`. Raw OData requires `allow_raw_filter` flag and is only safe for trusted internal callers.
- **Ingest source is a filesystem path**: `POST /ingest` `source` field is a server-side path. Never accept a raw URL in this field without implementing URL fetch + sandboxing first.
- **Scope enforcement**: All new endpoints require the appropriate `digisearch:query` or `digisearch:ingest` scope via DigiKey middleware.
- **No full doc bodies in spans**: DigiSmith trace attributes must not carry raw document text or chunk content.
- **bulk ingest worker is a stub**: `ingest_worker.py` logs and exits. Do not add a queue consumer there until Phase 2 is scoped.

---

## Test Commands

```bash
# Unit tests (no stack required)
pytest tests/ -m unit -k "digisearch" -v

# Single test file
pytest tests/digisearch/test_search.py -v

# Full unit suite
make test-unit

# Lint
ruff check digisearch/ && ruff format --check digisearch/

# Stack smoke test (requires make up)
curl -s http://localhost:8002/health

# CLI ingest smoke test (stub backend)
DIGISEARCH_ALLOW_STUB=1 digisearch ingest --index test digisearch/devdata/edgar_sample/

# CLI query smoke test
DIGISEARCH_ALLOW_STUB=1 digisearch query --index test --text "revenue growth"
```

---


---

## More

Extension patterns, anti-patterns, and integration boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc when changing interfaces or behavior.
