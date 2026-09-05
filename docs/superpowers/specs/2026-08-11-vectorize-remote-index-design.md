# Vectorize as digisearch's remote vector index (production Cloudflare stack)

**Date:** 2026-08-11
**Status:** Approved (design), not yet implemented
**Supersedes for production:** the container-local Chroma seeding path in
`frontend/digithings-stack-cloudflare/container/seed_chroma.sh`

## Problem

Production runs digisearch inside a Cloudflare Container, which keeps its
corpus in a container-local Chroma directory at `/data/chroma`, seeded at boot
from markdown baked into the image.

**Cloudflare Container disk is ephemeral.** Per
[platform details](https://developers.cloudflare.com/containers/platform-details/):
*"All disk is ephemeral. When a Container instance goes to sleep, the next time
it is started, it will have a fresh disk as defined by its container image."*
Persistent volumes do not exist (snapshots are "coming soon"; FUSE-to-R2 is
documented as not SSD-like performance). `sleepAfter = "2h"`
(`frontend/digithings-stack-cloudflare/src/index.ts`), so cold boots are routine.

Consequences of the current design:

1. **The whole corpus is re-parsed, re-chunked, and re-embedded on every cold
   boot.** With the content-aware chunking work (#2153) that is 1,526 chunks
   across both corpora — the expensive part of every wake.
2. **The corpus must ship inside the image**, which forces a choice between
   committing a client's documents to git (rejected by the owner: *"the corpus
   should not be saved to git, only to the container"*) and a gitignored
   generated directory that makes the image unreproducible from the repo.
3. **Production cannot be verified to serve what was tested.** The corpus is
   re-derived at boot rather than being the artifact that was validated. This
   already caused a silently invalid live test: the first production run
   reported 0% segmented chunks because the container was running a stale image
   (see `docs/projects/digithings/GAPLOG.md`, 2026-08-11).
4. `SEED_VER` markers under `$CHROMA_PATH` are load-bearing in the seed scripts
   but can never persist, because the disk they live on is wiped on sleep.

## Decision

Move the production vector index **out of the container** to Cloudflare
Vectorize. The container becomes stateless for retrieval: it queries a remote
index and never ingests.

Chroma remains the default for local development and tests — this adds a
backend, it does not remove one.

## Verified constraints (retrieved 2026-08-11, not from memory)

| Fact | Value | Source |
|---|---|---|
| REST API exists (not Workers-binding-only) | `POST /accounts/{account_id}/vectorize/v2/indexes/{name}/upsert` (ndjson) and `.../query` (JSON) | [Vectorize API](https://developers.cloudflare.com/api/resources/vectorize/subresources/indexes/) |
| Auth | `Authorization: Bearer <API token>` | same |
| Max dimensions | 1536 | [limits](https://developers.cloudflare.com/vectorize/platform/limits/) |
| Metadata per vector | 10 KiB | limits |
| Metadata **indexes** per Vectorize index | 10, each indexing ≤ 64 bytes per vector | limits |
| topK with metadata | ≤ 50 | limits |
| Batch upsert (HTTP API) | 5,000 vectors | limits |
| Indexes per account (free) | 100 | limits |
| Free tier | 5M stored vector dimensions; 30M queried dimensions/month; no paid Workers plan required | [pricing](https://developers.cloudflare.com/vectorize/platform/pricing/) |

**Fit:** 1,526 chunks × 384 dims (MiniLM) = **~586K stored dimensions** against
a 5M free allowance. 30M queried dims/month ≈ **~78,000 queries/month** free.
Both corpora fit the free tier with roughly 8x headroom on storage.

## Decisions taken (owner-confirmed 2026-08-11)

1. **Embeddings: local MiniLM, 384 dimensions.** The same model already
   validated and already present in the image. Upsert and query must use the
   same model — this is the invariant that makes the index usable at all.
   Workers AI (`bge-base`, 768 dims) was considered and rejected for now: it
   adds a per-query network dependency and latency for no correctness gain.
2. **Two separate Vectorize indexes**, not one index with namespaces:
   `digithings_docs` and `occ_help` (underscore form is canonical — verified
   live; hyphenated names in earlier drafts were wrong). Isolation is then
   structural — an OCC query physically cannot reach digithings vectors —
   rather than depending on every call site passing the right namespace. Maps
   1:1 onto the existing `DIGI_TENANT_CORPUS_MAP`. The free tier allows 100
   indexes, so this costs nothing.
3. **Corpus source: Supabase**, not a re-crawl. `architecture_notes` already
   holds the verified 1,279 + 328 notes. Deterministic, and it avoids
   re-crawling a client's help centre on every corpus rebuild.

## Design

### New backend

`digisearch/src/digisearch/indexes/backends/vectorize.py` — `VectorizeBackend(DigiIndex)`,
alongside the existing `chroma.py` and `azure_search.py`. It implements the
existing `DigiIndex` ABC (`digisearch/src/digisearch/indexes/base.py`):
`add`, `query`, `delete`, `update`, `list_collections`, `snapshot`.

- `add` / `update` → `POST .../upsert` with an ndjson body, batched at ≤ 1,000
  vectors per request (below the 5,000 HTTP cap, to stay well inside the 100 MB
  upload limit).
- `query` → `POST .../query` with `{vector, topK, returnMetadata}`; maps the
  response back into `list[Result]`.
- `delete` → the v2 delete-by-ids endpoint.
- `snapshot` → raises `NotImplementedError`; Vectorize is the system of record
  and is not exported this way. (`DigiIndex` requires the method; failing loudly
  is better than pretending.)
- `list_collections` → lists indexes for the account.

Config via env, matching the existing backend-selection style:
`VECTORIZE_ACCOUNT_ID`, `VECTORIZE_API_TOKEN`, and `VECTORIZE_INDEX_PREFIX`
(optional, so dev/staging indexes can coexist in one account).

### Metadata mapping

Chunk metadata is carried on the vector's `metadata` object (10 KiB budget,
ample). Of these, only fields we actually filter on become **metadata indexes**
(max 10, each ≤ 64 bytes indexed per vector):

- **Indexed (filterable):** `doc_id`, `page_class`, `client`.
- **Returned only (not indexed):** `source_url`, `segment_label`,
  `segment_index`, `chunk_index`.

`segment_label` is deliberately not indexed: heading breadcrumbs such as
`heading:digiquant Architecture > Atlas + Hermes Sub-graphs > Hermes (thesis-aware portfolio loop)`
exceed the 64-byte indexed cap. It is still returned in full for citations,
which is what it is for.

### Backend selection

`digisearch/src/digisearch/search/_stub.py` constructs backends at three sites
(lines 64, 189, 206). Selection precedence becomes:

1. `VECTORIZE_ACCOUNT_ID` + `VECTORIZE_API_TOKEN` set → `VectorizeBackend`
2. else `CHROMA_HOST` set → remote Chroma
3. else `CHROMA_PATH` set → local Chroma (today's default; unchanged for dev)
4. else stub (tests only)

`server.py`'s `_require_real_search_backend()` and the `backend` field on
`QueryResponse` (currently `azure_ai_search | chroma | stub`) gain `vectorize`.

### Ingest — host-side, from Supabase

New `scripts/vectorize_sync.py`:

1. Read notes from Supabase `architecture_notes`, filtered by `vault_path`
   prefix (`clients/digithings/`, `clients/online-compliance-center/`).
2. Reconstruct chunks using the **same** `SegmentAwareChunker` +
   `heading_segments` path production retrieval assumes, so the index matches
   the pipeline that was validated.
3. Embed with local MiniLM (384).
4. Upsert to the corresponding Vectorize index in ≤1,000-vector batches.

This runs on an operator machine or in CI — never in the container. Production
only queries.

### Production container changes

`frontend/digithings-stack-cloudflare/`:

- `src/index.ts`: add `VECTORIZE_ACCOUNT_ID` / `VECTORIZE_API_TOKEN` to the
  container `envVars` whitelist and the `Env` interface. **This is required** —
  the whitelist is explicit, so a `wrangler secret put` alone would never reach
  the container (the same trap that blocks the Supabase path today).
- `container/entrypoint.sh`: only export `CHROMA_PATH` when Vectorize is not
  configured, so the local-Chroma branch is not selected in production.
- `container/supervisor/supervisord.conf`: the `seed_chroma` oneshot becomes a
  no-op when Vectorize is configured. `start_digisearch.sh`'s marker wait is
  skipped on that path.
- The baked `container/seed/` corpus stays for local/offline use but stops
  being production's source of truth.

## Non-goals

- **Removing Chroma.** It remains the local-dev and test backend, and the
  `seed_chroma.sh` path stays functional for offline work.
- **Migrating digivault.** *(Superseded — true when written, false since #2239.)*
  This spec covered the vector half only, on the assumption that keyword/vault
  search would keep reading Supabase (`architecture_notes`) indefinitely.
  That is no longer the case: `docs/superpowers/specs/2026-08-12-agentic-chat-and-digivault-on-d1-design.md`
  gave digivault its own Cloudflare D1-backed corpus, and `digivault_search_notes`
  now prefers D1 when configured, falls back to the local filesystem vault when
  `DIGIVAULT_ROOT` is set, and only reaches Supabase as the last resort (see
  digivault/ARCHITECTURE.md's search-precedence section). This spec's vector-index
  decisions above are unaffected; only this non-goal's premise is superseded.
- **Workers AI embeddings.** Reconsider only if the local model becomes a
  cold-boot cost worth removing.
- **Auth for hosted Chroma.** `ChromaBackend` still cannot send auth headers;
  irrelevant once Vectorize is the remote backend.

## Testing

- `VectorizeBackend` unit tests with an injected HTTP transport (no network),
  following the existing dependency-injection style in `tests/scripts/docs_onboard/`:
  upsert batching at the 1,000 boundary, query response → `list[Result]`
  mapping, metadata round-trip, and error propagation on a non-2xx.
- Backend-selection precedence test: Vectorize wins over `CHROMA_HOST` and
  `CHROMA_PATH` when configured; Chroma still selected when it is not
  (backward-compatibility guard).
- `scripts/vectorize_sync.py` unit test with a stub Supabase reader and a
  recording upserter, asserting chunk counts and that the two corpora go to
  their own indexes.
- One **live** integration check, run manually against the real account before
  cutover: upsert a small fixture index, query it, assert the segment metadata
  round-trips, then delete the fixture index.

## Risks

- **A wrong-dimension or wrong-model upsert silently degrades retrieval**
  rather than erroring. Mitigation: record the embedding model id in every
  vector's metadata and have `vectorize_sync.py` refuse to upsert into an index
  whose existing vectors report a different model.
- **API token scope.** Needs Vectorize edit on one account. It reaches the
  container via `envVars`, so it is a production secret with write access to
  the index — query-only would be safer for the container if Cloudflare
  supports a read-scoped token; check at implementation time and prefer it.
- **Free-tier ceiling is on stored dimensions, not documents.** 8x headroom
  today, but a 10x corpus growth crosses it. Cheap beyond that ($0.05 per 100M
  stored dims), but worth a note in the runbook.
- **Vectorize outage = empty results, not an error**, unless handled. The
  backend must surface a query failure as a 5xx rather than returning zero hits,
  which would look to a user like "the docs don't mention that."
