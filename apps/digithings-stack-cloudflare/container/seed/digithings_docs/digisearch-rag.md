# digisearch RAG retrieval (seed)

How document search works on Profile A. Distinct from digikey auth and digivault
notes.

## Pipeline

ingest → parse markdown → recursive chunk (≈512 tokens) → embed → Chroma index
→ hybrid / vector query → ranked chunks

## Indexes on digithings.ai/chat

| Index | Tenant |
|---|---|
| `digithings_docs` | digithings (default chat) |
| `occ_help` | Online Compliance Center (`/chat/occ`) |

Indexes are isolated collections under `CHROMA_PATH`. Queries never cross
collections unless the hub passes a different `index_name`.

## Chunk metadata

Ingested chunks should carry `source` / `path` / `title` so Sources citations are
readable file paths, not opaque UUIDs.

## What this note does not cover

JWT issuance, vault wikilinks, or NautilusTrader strategy backtests.
