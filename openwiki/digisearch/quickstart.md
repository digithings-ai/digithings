---
type: quickstart
title: digisearch Quickstart
description: Start digisearch, run a stub ingest and query, verify the service, use web search, exercise monitors, and run unit gates.
tags: [digisearch, quickstart]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
sources:
  - id: openwiki-source-d16d9586117b95e03b7f1549
    resource: repo://digisearch/AGENTS.md
  - id: openwiki-source-0739fb1c67fa358e627b1663
    resource: repo://digisearch/ARCHITECTURE.md
  - id: openwiki-source-ec6eff750c51e74f78a18b5a
    resource: repo://digisearch/src/digisearch/monitors/models.py
  - id: openwiki-source-8639f2733ed2c02f7d26be5f
    resource: repo://digisearch/src/digisearch/server.py
  - id: openwiki-source-bf31cd1636fadced6e4ffd4b
    resource: repo://digisearch/src/digisearch/web_search/models.py
  - id: openwiki-source-d3acfa4b3c50187846c59e90
    resource: repo://digisearch/src/digisearch/web_search/service.py
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
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
make stack-local # digisearch on :8002 (or make up)
curl -s http://localhost:8002/health
pytest tests/ -m unit -k "digisearch" -v
pytest -m unit -k chunking -v
ruff check digisearch/ && ruff format --check digisearch/
```

Production needs a real backend: `CHROMA_PATH` for Chroma,
`AZURE_SEARCH_*` for Azure, plus an embedding provider key.

## 3. Web search

First-party web search (SearXNG with DuckDuckGo fallback, plus
fetch+extract enrichment) is live on `POST /v1/web_search` and the
MCP `web_search` tool. Both require `digisearch[web-search]`.

```bash
# Install the web-search extra
pip install -e "digisearch[web-search]"

# Quick search (auto: searxng → ddgs fallback)
curl -s -X POST http://localhost:8002/v1/web_search \
  -H 'Content-Type: application/json' \
  -d '{"query":"etf flows"}'

# For a SearXNG sidecar, point it at the searxng container
export DIGISEARCH_SEARXNG_URL=http://127.0.0.1:8080

# Explicitly lock to one provider (fail closed, no fallthrough)
export DIGISEARCH_WEB_SEARCH_BACKEND=ddgs
curl -s -X POST http://localhost:8002/v1/web_search \
  -H 'Content-Type: application/json' \
  -d '{"query":"etf flows","max_results":5}'
```

Backend selectors (`DIGISEARCH_WEB_SEARCH_BACKEND`): `auto` tries
searxng first then ddgs; an explicit `searxng`/`ddgs` runs only that
backend and never falls through. Provider failures return HTTP 200
with a soft `{ok: false, error, retryable, status_code}` envelope.

The MCP server also exposes `web_search(query, include_domains,
exclude_domains, max_results)` — same underlying pipeline, same
extra requirement.

## 4. Monitors

Scheduled web-search watches (`/v1/monitors`) run at intervals or on
cron and persist deduped runs. Monitor state lives in
`{DIGI_WORKSPACE}/.digisearch/monitors.sqlite3`.

```bash
# Create a watch: poll every hour, dedup by url_content
curl -s -X POST http://localhost:8002/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"ETF flows hourly",
    "query":"biggest ETF flows this week",
    "schedule":{"mode":"interval","interval_seconds":3600},
    "delivery":{"mode":"poll"},
    "num_results":8
  }'

# List watches
curl -s http://localhost:8002/v1/monitors

# Trigger one watch now (manual mode)
curl -s -X POST http://localhost:8002/v1/monitors/<watch_id>/trigger \
  -H 'Content-Type: application/json' \
  -d '{"mode":"manual"}'

# Read run history (newest-first, cursor-paginated)
curl -s http://localhost:8002/v1/monitors/<watch_id>/runs?limit=5

# Tick all due + enabled watches (digiclaw wake-up clock)
curl -s -X POST http://localhost:8002/v1/monitors/tick
```

Each run captures `results_new` (post-dedup), `dedup_stats`, and the
provider snapshot. Watches default to the OSS search seam; set
`"backend":"exa"` plus `EXA_API_KEY` for the EXA paid path, which
provisions a remote monitor, returns a delivery secret, and receives
results through the `POST /v1/monitors/exa_webhook` route.

## Where next

- [digisearch Architecture](/openwiki/digisearch/architecture.md) —
  pipeline, backends, vertical role.
- [digisearch Ingest and Index](/openwiki/digisearch/ingest-and-index.md) —
  parsing, chunking, embeddings.
- [digisearch Query and Operations](/openwiki/digisearch/query-and-operations.md) —
  retrieval, scopes, monitors, websets, container.
