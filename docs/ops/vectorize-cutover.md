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
- **Metric: cosine** — `scripts/vectorize_sync.py`'s model-mismatch guard
  (`assert_index_model`) probes with a unit vector on the assumption the index
  is a cosine index; a different metric is unsupported.
- **Name: must equal `DIGISEARCH_INDEX` / the `DIGI_TENANT_CORPUS_MAP` entry**
  for that tenant, set in
  [`frontend/digithings-stack-cloudflare/wrangler.toml`](../../frontend/digithings-stack-cloudflare/wrangler.toml).
  `_vectorize_backend` (`digisearch/src/digisearch/search/_stub.py`) passes
  `index_name` straight into the Vectorize URL with no translation — a
  mismatched name means every chat query 404s against an index nothing ever
  populated. Today those values are underscore-form: `digithings_docs` and
  `occ_help`.

  **Verified 2026-08-11:** Cloudflare's own Vectorize docs only ever *show*
  kebab-case index names
  ([best-practices/create-indexes](https://developers.cloudflare.com/vectorize/best-practices/create-indexes/),
  [get-started/intro](https://developers.cloudflare.com/vectorize/get-started/intro/))
  — that's convention, not a documented constraint, and this is not a claim
  that underscores are documented as supported. Underscore index names are
  empirically accepted: `npx wrangler vectorize create digithings_docs
  --dimensions=384 --metric=cosine` and the same call for `occ_help` both
  succeeded against the live account, and `npx wrangler vectorize list`
  confirms both indexes at 384 dimensions, cosine metric. No rename of
  `DIGISEARCH_INDEX` or the Chroma collection names is needed —
  `digithings_docs` / `occ_help` remain the single canonical name across
  both sides of the pairing, including the hardcoded collection names in
  `frontend/digithings-stack-cloudflare/container/seed_chroma.sh`.

## 1. Create the indexes

```bash
npx wrangler vectorize create digithings_docs --dimensions=384 --metric=cosine
npx wrangler vectorize create occ_help --dimensions=384 --metric=cosine
```

## 2. Set the two secrets

On the `digithings-stack` Worker (same one that runs `wrangler deploy` for the
Container):

```bash
cd frontend/digithings-stack-cloudflare
npx wrangler secret put VECTORIZE_ACCOUNT_ID
npx wrangler secret put VECTORIZE_API_TOKEN
```

Setting both is what flips the container from Chroma to Vectorize on the next
boot — `entrypoint.sh` computes `DIGI_VECTORIZE_ACTIVE=1` once both are
non-empty and skips the Chroma seed entirely from then on.

## 3. Sync each corpus — dry-run first, then apply

Run from an operator machine or CI, never inside the Container (the Container
only queries). One prefix per tenant, matching `DIGI_TENANT_CORPUS_MAP`:

```bash
# digithings tenant
CORE_SUPABASE_URL=… CORE_SUPABASE_ANON_KEY=… \
  python3 scripts/vectorize_sync.py --prefix clients/digithings --index digithings_docs --dry-run

CORE_SUPABASE_URL=… CORE_SUPABASE_ANON_KEY=… \
  VECTORIZE_ACCOUNT_ID=… VECTORIZE_API_TOKEN=… \
  python3 scripts/vectorize_sync.py --prefix clients/digithings --index digithings_docs

# occ tenant
CORE_SUPABASE_URL=… CORE_SUPABASE_ANON_KEY=… \
  python3 scripts/vectorize_sync.py --prefix clients/online-compliance-center --index occ_help --dry-run

CORE_SUPABASE_URL=… CORE_SUPABASE_ANON_KEY=… \
  VECTORIZE_ACCOUNT_ID=… VECTORIZE_API_TOKEN=… \
  python3 scripts/vectorize_sync.py --prefix clients/online-compliance-center --index occ_help
```

The `--dry-run` pass reads and chunks the real notes and reports the vector
count that *would* be upserted — no ONNX inference, no model download, no
network write — so it is safe to run against production Supabase data before
committing to the real sync. The apply pass batches chunks across notes into
Vectorize's upsert batch size (1,000) rather than one HTTP request per note, so
a full sync of either tenant should be on the order of a handful of requests,
not one per note.

## 4. Verify the sync landed — before flipping traffic

Do this **before** setting the two secrets on the live Worker (step 2) if you
want a true pre-cutover check, or immediately after step 3 either way — query
the index directly and confirm it returns non-zero hits:

```bash
npx wrangler vectorize info digithings_docs   # vectorCount should be > 0
npx wrangler vectorize query digithings_docs --vector "$(python3 -c 'print(",".join(["0.1"]*384))')" --top-k 3
```

An empty `matches` array, or `vectorCount: 0` from `info`, means the sync did
not land — do not proceed to cutover. Repeat for `occ_help`.

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
