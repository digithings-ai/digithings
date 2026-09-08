# Vectorize cutover runbook

Operator steps for pointing the digithings-stack Cloudflare Container at
Cloudflare Vectorize instead of the container-local Chroma index. See
[`digisearch/ARCHITECTURE.md`](../../digisearch/ARCHITECTURE.md#vectorize-remote-index)
for the backend's implementation details and
[`frontend/digithings-stack-cloudflare/README.md`](../../frontend/digithings-stack-cloudflare/README.md)
for the rest of the stack's deploy flow. This page covers only the
Vectorize-specific slice: creating the indexes, syncing them, and verifying a
sync landed before traffic depends on it.

## Index requirements

- **Dimensions: 384** — the sync (`scripts/vectorize_sync.py`) and the query
  path (`VectorizeBackend.query()`) both embed with `MiniLMEmbedder`
  (`MINILM_MODEL_ID = "all-MiniLM-L6-v2-384"`). An index created with any other
  dimension count will reject every upsert.
- **Metric: cosine** — this is a deployment choice, not something the sync
  script enforces or depends on. `scripts/vectorize_sync.py`'s model-mismatch
  guard (`assert_index_model`) probes with a non-zero unit vector, but the
  probe's validity doesn't depend on the index's metric — nothing in shipped
  code reads or enforces cosine specifically. Create the index with cosine
  anyway, to match what `VectorizeBackend.query()` assumes when interpreting
  similarity scores.
- **Name: must equal `DIGISEARCH_INDEX` / the `DIGI_TENANT_CORPUS_MAP` entry**
  for that tenant, set in
  [`frontend/digithings-stack-cloudflare/wrangler.toml`](../../frontend/digithings-stack-cloudflare/wrangler.toml).
  `_vectorize_backend` (`digisearch/src/digisearch/search/_stub.py`) passes
  `index_name` straight into the Vectorize URL with no translation — a
  mismatched name means every chat query 404s against an index nothing ever
  populated. Today those values are underscore-form: `digithings_docs` and
  `occ_help`.

  **Verified 2026-08-11:** Cloudflare's docs give **advisory** naming guidance
  — [get-started/intro](https://developers.cloudflare.com/vectorize/get-started/intro/)
  states in prose that "a good index name is: a combination of lowercase
  and/or numeric ASCII characters, shorter than 32 characters, starts with a
  letter, and uses dashes (-) instead of spaces" — but no enforced charset or
  regex is published, and there is a real 64-byte length cap that both
  `digithings_docs` and `occ_help` clear. This is not a claim that underscores
  are documented as supported, and it is not a claim the docs are silent on
  the matter — both would be false. Underscore index names are empirically
  accepted: `npx wrangler vectorize create digithings_docs
  --dimensions=384 --metric=cosine` and the same call for `occ_help` both
  succeeded against the live account, and `npx wrangler vectorize list`
  confirms both indexes at 384 dimensions, cosine metric. No rename of
  `DIGISEARCH_INDEX` or the Chroma collection names is needed —
  `digithings_docs` / `occ_help` remain the single canonical name across
  both sides of the pairing, including the hardcoded collection names in
  `frontend/digithings-stack-cloudflare/container/seed_chroma.sh`.

## 0. Prerequisites for running the sync script locally

**Source: Cloudflare D1, not Supabase (#2239).** `scripts/vectorize_sync.py` reads
notes from D1 via `D1Store.list_notes()` defined in
`digivault/src/digivault/d1_store.py` (imported directly — not from
`scripts/d1_sync.py`) — the notes and the vectors have to describe the same
corpus, so `--database` must be the **same** D1 database
`d1_sync.py --prefix <p>` published that prefix into. `CORE_SUPABASE_*` is
not read anywhere on this path any more.

`scripts/vectorize_sync.py` also imports `digivault`, which is not on `sys.path`
from a plain `python3 scripts/vectorize_sync.py` invocation in a clean
checkout — that fails with `ModuleNotFoundError: No module named 'digivault'`.
Set `PYTHONPATH=digivault/src`, or use `uv run` from the repo root (the monorepo
workspace already resolves it). The apply pass (no `--dry-run`) also constructs
`MiniLMEmbedder`, which lazily imports `chromadb` on first `embed()` call — install
digisearch's `[chroma]` extra (or use a venv that already has it) or that call
fails too.

```bash
uv run python scripts/vectorize_sync.py \
  --prefix clients/digithings --index digithings_docs \
  --database <d1-database-id-for-clients/digithings> --dry-run
```

This is the exact form used in the steps below. `--database` and `--index` are two
different Cloudflare products (D1 vs Vectorize) and are **not** interchangeable —
get either one wrong and the sync reads or writes a different corpus than the one
being cut over.

## 1. Create the indexes

```bash
npx wrangler vectorize create digithings_docs --dimensions=384 --metric=cosine
npx wrangler vectorize create occ_help --dimensions=384 --metric=cosine
```

## 2. Sync each corpus — dry-run first, then apply

Run from an operator machine or CI, never inside the Container (the Container
only queries). One prefix per tenant, matching `DIGI_TENANT_CORPUS_MAP`, reading
from the **same D1 database** `d1_sync.py` published that prefix into (see
`docs/superpowers/plans/2026-08-12-agentic-chat-and-digivault-on-d1.md` Task 7 for
the current database ids — `9f1431bf-e79a-4b0f-a67a-bcd040506d87` for
`clients/digithings` and `f587fad6-0a26-4bf4-bdf7-740eac549acd` for
`clients/online-compliance-center` as of the 2026-08-12 backfill):

```bash
# digithings tenant
CLOUDFLARE_ACCOUNT_ID=… CLOUDFLARE_API_TOKEN=… \
  uv run python scripts/vectorize_sync.py --prefix clients/digithings \
  --index digithings_docs --database 9f1431bf-e79a-4b0f-a67a-bcd040506d87 --dry-run

CLOUDFLARE_ACCOUNT_ID=… CLOUDFLARE_API_TOKEN=… \
  uv run python scripts/vectorize_sync.py --prefix clients/digithings \
  --index digithings_docs --database 9f1431bf-e79a-4b0f-a67a-bcd040506d87

# occ tenant
CLOUDFLARE_ACCOUNT_ID=… CLOUDFLARE_API_TOKEN=… \
  uv run python scripts/vectorize_sync.py --prefix clients/online-compliance-center \
  --index occ_help --database f587fad6-0a26-4bf4-bdf7-740eac549acd --dry-run

CLOUDFLARE_ACCOUNT_ID=… CLOUDFLARE_API_TOKEN=… \
  uv run python scripts/vectorize_sync.py --prefix clients/online-compliance-center \
  --index occ_help --database f587fad6-0a26-4bf4-bdf7-740eac549acd
```

`CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN` authorize **both** the D1 read and
the Vectorize write with one credential pair (#2239 credential rename) — the
legacy `VECTORIZE_ACCOUNT_ID`/`VECTORIZE_API_TOKEN` and `D1_ACCOUNT_ID`/
`D1_API_TOKEN` names still work as a fallback, in that order.

The `--dry-run` pass reads and chunks the real notes and reports the vector
count that *would* be upserted — no ONNX inference, no model download, no
network write — so it is safe to run against production D1 data before
committing to the real sync. The apply pass batches chunks across notes into
Vectorize's upsert batch size (1,000) rather than one HTTP request per note, so
a full sync of either tenant should be on the order of a handful of requests,
not one per note.

## 3. Verify the sync landed — before touching any secret

**Do this before step 4, not after.** An earlier revision of this runbook set
the cutover secrets (below) *before* verifying — an operator following the
numbered steps in order could flip live traffic onto an empty or partially
synced index if the Container cold-boots in the gap between "set secrets" and
"confirm the sync landed" (#2239 review: setting the secrets is what activates
Vectorize on next boot, and Cloudflare Containers do sleep and cold-boot
routinely).

### 3a. Wait for async mutation processing (#2236)

Vectorize upserts are **asynchronous**. The upsert API enqueues vectors and
returns a *mutation id* — it does not mean every vector (or its metadata) is
queryable yet. `wrangler vectorize info` exposes `processedUpToMutation` and
`processedUpToDatetime` precisely because there is a lag between "sync script
finished" and "index content is current."

After the apply pass in step 2, note the **`sync_completed_at`** timestamp (and
**`last_mutation_id`**, when printed) that `scripts/vectorize_sync.py` emits on
stderr. Then poll until processing has caught up:

```bash
npx wrangler vectorize info digithings_docs
```

Confirm **`processedUpToDatetime`** is **at or after** the sync's
`sync_completed_at` time. If it is still earlier, wait 30–60 seconds and re-run
`info` — do **not** treat an early query as evidence of failure.

`vectorCount` from `info` often updates quickly, but **per-vector metadata can
lag** (observed during the real cutover: counts looked right while
`segment_label` in query matches was still stale for ~1 minute). A
`vectorCount > 0` check alone is **not** sufficient proof that a re-sync's
content has landed.

### 3b. Query the index directly

Only after 3a passes, query the index and confirm it returns non-zero hits
with the expected metadata:

```bash
npx wrangler vectorize info digithings_docs   # vectorCount should be > 0
npx wrangler vectorize query digithings_docs --vector $(python3 -c 'print(" ".join(["0.1"]*384))') --top-k 3
```

`--vector` is a yargs number **array** — space-separated, unquoted argv words,
one number each — not a single comma-joined string. A quoted
`"0.1,0.1,…"` becomes one argv word; `Number()` on it is `NaN`, wrangler's
coerce step filters `NaN` out, and the query silently runs with a zero-length
vector instead of erroring, which manufactures the exact false-negative this
step exists to catch. Confirm the corrected form actually parses to 384
numbers before relying on it (`... | wc -w` should read `384`).

An empty `matches` array right after a sync that printed a successful upsert
count usually means **processing has not caught up yet** — re-check 3a and
re-query. Only treat empty/stale results as a hard failure once
`processedUpToDatetime` is current and matches still look wrong. Repeat 3a–3b
for `occ_help`.

## 4. Set the two secrets — only once step 3 passed for both indexes

On the `digithings-stack` Worker (same one that runs `wrangler deploy` for the
Container):

```bash
cd frontend/digithings-stack-cloudflare
npx wrangler secret put CLOUDFLARE_ACCOUNT_ID
npx wrangler secret put CLOUDFLARE_API_TOKEN
```

`CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN` are the canonical names (#2239
credential rename) — the same account + token also authorizes D1, so a
deployment that already set the legacy `VECTORIZE_ACCOUNT_ID`/
`VECTORIZE_API_TOKEN` (or `D1_ACCOUNT_ID`/`D1_API_TOKEN`) keeps working via
fallback; set the canonical pair and retire the legacy secrets once verified.

Setting both is what flips the container from Chroma to Vectorize on the next
boot — `entrypoint.sh` computes `DIGI_VECTORIZE_ACTIVE=1` once both resolve to
non-empty (canonical or legacy) and skips the Chroma seed entirely from then on.
This is why step 3 must pass first: there is no staged rollout here, only
"next boot serves from whichever backend has non-empty credentials."

## Known limitations (do not cutover a workflow that depends on either)

- **[#2218](https://github.com/digithings-ai/digithings/issues/2218) — `POST
  /ingest` silently no-ops against Vectorize.** `SegmentAwareChunker` never
  embeds, so chunks reach `VectorizeBackend.add()` with `embedding=None`,
  which filters them out and returns having sent nothing — while `api_ingest`
  still reports HTTP 200 with a nonzero `chunks_created`. Any workflow that
  ingests through this endpoint (rather than `scripts/vectorize_sync.py`) will
  believe it wrote vectors that were never sent.
- **[#2219](https://github.com/digithings-ai/digithings/issues/2219) — no
  query-time filter / workspace isolation.** `VectorizeBackend.query()` never
  reads `Query.filters`, so a `workspace_id` clause that `ChromaBackend` would
  enforce is silently ignored against Vectorize. The current two-tenant
  deployment is safe only because each tenant gets its own index
  (`digithings_docs` / `occ_help`) — isolation is by index selection, not by
  filtering. Do not rely on `workspace_id` filtering within a single Vectorize
  index until this is fixed.
