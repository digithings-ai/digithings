# DigiSearch — Spec

**Port:** 8002  
**Role:** RAG pipeline — document ingest, chunking, embedding, vector search, and orchestrator tool surface.

## Capabilities

- Document ingest with chunking and embedding (`/ingest`)
- Semantic vector search (`/query`)
- Index management (`/indexes/*`)
- Azure AI Search integration (status at `/azure_status`)
- Orchestrator tool endpoints for digigraph (`/v1/orchestrator_tools`)
- Research turn handling (`/v1/research_turn`)

## Invariants

- Polars for all tabular data; no pandas
- Pydantic v2 request/response models
- Vector store operations are idempotent — re-ingesting the same document replaces the existing embedding
- `/healthz` is auth-exempt, no downstream checks

## Public API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ingest` | Ingest and embed documents |
| POST | `/query` | Semantic search |
| GET | `/indexes` | List indexes |
| POST | `/indexes` | Create index |
| DELETE | `/indexes/{name}` | Delete index |
| GET | `/azure_status` | Azure AI Search connectivity |
| POST | `/v1/orchestrator_tools` | Tool surface for digigraph |
| POST | `/v1/research_turn` | Single research turn |
| GET | `/healthz` | Liveness probe |

## Extension Pattern

Add new retrieval strategies as pluggable retriever classes registered in the retriever registry. Never hard-code retrieval logic in the FastAPI route handlers.
