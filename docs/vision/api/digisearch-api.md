---
title: "digisearch — API reference"
type: reference
status: generated
created: 2026-06-29
tags:
  - api
  - core
relevance:
  - digisearch
---
# digisearch — API reference

> Production RAG without a stack rewrite when you switch vector DB.

**Role:** Vector retrieval · multi-backend · **Tier:** core

## Overview
One client over Chroma or Azure AI Search, with backend-neutral entities so you swap engines without touching business code.

Dense, sparse, and hybrid retrieval are first-class; BeautifulSoup and pdfplumber handle ingest, Polars throughout.

## Authentication
All query/ingest routes require a digikey JWT carrying the matching scope.

- `digisearch:query` — /query, /v1/research_turn, orchestrator routes, /indexes/*
- `digisearch:ingest` — /ingest

## Run locally
```bash
docker compose up -d digisearch
```

```bash
uvicorn digisearch.server:app
```

MCP: `digisearch mcp   (FastMCP streamable-http: digisearch_query, digisearch_research_turn)`

## Configuration
- `CHROMA_PATH`: Persistent Chroma directory (activates the Chroma backend).
- `AZURE_SEARCH_ENDPOINT`: Azure AI Search endpoint (alternative backend).
- `AZURE_SEARCH_API_KEY`: Azure AI Search key.
- `OPENAI_API_KEY`: Embeddings provider key.
- `DIGIKEY_JWKS_URL` — required: JWT public-key endpoint.

## Endpoints

Base URL: `$DIGISEARCH_URL` (the service URL from docker-compose.yml).

### POST /query
Hybrid / keyword / vector search over an index.

auth: digisearch:query · rate: 10/min/IP

Request:
- `text` (string) — required: Query text.
- `index_name` (string): Target index (default "default").
- `top_k` (integer): Results to return, 1–100 (default 10).
- `mode` (string): "keyword" | "vector" | "hybrid" (default hybrid).
- `filters` ({field,op,value}[]): Structured metadata filters.

Response:
- `results` (object[]): Normalized hits (chunk_id, doc_id, score, content, metadata).
- `total` (integer): Total matches.
- `backend` (string): "chroma" | "azure_ai_search" | "stub".

```bash
curl -X POST $DIGISEARCH_URL/query \
  -H "Authorization: Bearer $JWT" -H "content-type: application/json" \
  -d '{"text":"momentum factor","index_name":"default","top_k":5}'
```

```python
r = httpx.post(
    f"{os.environ['DIGISEARCH_URL']}/query",
    headers={"Authorization": f"Bearer {os.environ['DIGI_JWT']}"},
    json={"text": "momentum factor", "top_k": 5},
)
for hit in r.json()["results"]:
    print(hit["score"], hit["content"][:80])
```

### POST /ingest
Ingest a document (parse → chunk → embed → index).

auth: digisearch:ingest · rate: 30/min/IP

Request:
- `source` (string) — required: Server-side path to the document.
- `index_name` (string): Target index.
- `doc_type` (string): pdf | html | docx | markdown | csv | plaintext.
- `metadata` (object): Evidence metadata (tier, venue, tags, …).

Response example:
```json
{ "doc_id": "...", "chunks_created": 12, "index_name": "default", "status": "ok" }
```

### POST /v1/research_turn
Composite research turn (plan → retrieve → aggregate) with citations.

auth: digisearch:query · rate: 10/min/IP · requires the digisearch[agent] extra

## MCP tools
- `digisearch_query` — Search documents; returns formatted hits with score + preview.
- `digisearch_research_turn` — Composite research turn with citations (needs digisearch[agent]).

## Stack
Chroma, OpenAI, BeautifulSoup, pdfplumber, LangGraph, FastAPI

## Related
digigraph, digistore, digibase

## Links
- [Source](https://github.com/digithings-ai)

See also [[digisearch]].
