# Review — PR #4956 (commit a1816064c)

- Reviewer: subagent (fresh-context focused review)
- Subject: digithings-ai/digithings#4956, branch `task/4756-feat-zammad---semantic-ticket-search-ove`, commit `a1816064c` on top of `origin/module/digisearch`
- Scope: multilingual ticket search deploy — query fan-out, backfill hardening, sibling-track port, stack image extra, runbook
- Verdict: **Approve — no blocking issues.** All six focus areas verified against file content; findings are low-severity polish. Offline tests pass (see §6).

## Severity counts

- High: 0 · Medium: 0 · Low: 4 · Info/nit: 3

## Verified correct (no finding)

- **Rerank applied exactly once.** Single-index: `query_index` → `_maybe_rerank(_query_single_index(...))` (`digisearch/src/digisearch/search/_stub.py:336-337`); per-index helper returns unrereanked (`:240-241`, `:273`, `:292`, `:323`). Multi-index merges then reranks once (`:347-349`). Refactor preserves prior single-index semantics (old `_maybe_rerank` call sites moved verbatim into `_query_single_index`).
- **Empty-segment handling.** `names` stripped/filtered, fallback `["default"]` (`:334-335`); `"a,, ,"` collapses to the single-index path. `None`/`""`/whitespace all route to `"default"` via `str(index_name or "default")`.
- **RRF rank handling.** Unset `Result.rank` falls back to position+1 (`:226`); dedupe by `chunk.id` keeps first-seen chunk/source_doc and sums RRF scores (`:227-231`); merged ranks reassigned sequentially with RRF-sum scores (`:233-236`). Tie order is stable (insertion order). Pinned by `tests/ds/test_multi_index_query.py:74-99`.
- **Error propagation per index (fail-closed).** Verified by execution against worktree source: a `SearchBackendError` raised for one fan-out leg propagates out of `query_index` and aborts the merge (no partial answer from the surviving corpus). `SearchBackendError`/`VectorizeBackendError` intentionally subclass plain `Exception` (`digisearch/src/digisearch/indexes/backends/backend_errors.py:19`, `vectorize_errors.py:19`), so the `_BACKEND_ERRORS` catch in `_query_single_index` (`_stub.py:246`) cannot swallow them. Matches the docstring claim (`:329-332`).
- **`normalize_query_hit` / agent pipeline safe with `backend="multi"`.** `normalize_query_hit` is per-`Result` and never reads `SearchResponse.backend` (`digisearch/src/digisearch/core/standard_hits.py:36-46`). `QueryResponse.backend` and agent state are free `str | None` (`digisearch/src/digisearch/server.py:450-453`, `core/models.py:96`, `agent/pipeline_models.py:40,64`); pipeline passes it through opaquely (`agent/pipeline.py:77`).
- **Fail-loud provider check.** Unset → pinned + restored via try/finally (`scripts/index_occ_tickets.py:214-216,228-234`); conflicting preset → `SystemExit` before any env mutation (`:217-227`, env provably untouched — pinned by `tests/ds/test_multilingual_embedder.py:331-332`); `dry_run`/empty returns before any provider/env code (`:193-194`); unresolvable preset → `SystemExit` (`:220-221`). Env-var alias `"multi"` (valid per `digisearch/src/digisearch/embedding/factory.py:124`) also passes the `isinstance` check.
- **Stamp-verification routing mirror.** Vectorize credential triple matches `route_add_chunks` (`scripts/index_occ_tickets.py:259-261` vs `_stub.py:369-370`); Chroma construction (`persist_path` + `chroma_host` + `int(port)`, `:273-281`) mirrors `_chroma_backend` (`_stub.py:161-168`). `ChromaBackend` re-export of `EmbeddingModelMismatchError` works (`digisearch/src/digisearch/indexes/backends/chroma.py:17`).
- **Ported files clean.** No `zammad_tickets`/`is_internal` stale refs anywhere under `scripts/` (grep clean). `eval.py` keys (`query`, `expected_ticket_ids`) match the gold file shape; `download_multilingual_model.py` imports all exist (`multilingual.py:22-33`); gold file parses as 28 de/en pairs.
- **Provider wraps + counter.** Download/load errors wrapped with actionable messages naming the pre-warm script and `DIGISEARCH_MULTILINGUAL_MODEL_DIR` (`multilingual.py:112-118,149-154`, chained `from exc`). Truncation counted pre-cap per encoding (`:168-171`) and added only after successful embed (`:213`), so failed embeds don't inflate the diagnostic. float32 pooling is normalization-preserving; embedder suite passes.

## Findings

### Low

1. **Duplicate Dockerfile rebuild marker number** — `Dockerfile.digithings-stack-cloudflare:133` already defines "Rebuild marker v11 (2026-09-19)" (bing/mojeek) and `:122` is at v13, but the new entry at `:140` is also labeled "v11 (2026-10-01)". Should be v14. Comment-only (the content change still alters the hash so wrangler rebuilds), but it breaks the monotonic convention and makes the next bump ambiguous.
2. **`backend="multi"` omissions downstream of the fan-out** —
   - `QueryResponse.backend` description enumerates `vectorize | azure_ai_search | chroma | stub` (`server.py:450-453`); same staleness in `SearchResponse.backend` docstring (`core/models.py:95`). Field types accept `"multi"`, so runtime-safe, docs-inaccurate.
   - `effective_query_mode("hybrid", "multi")` returns `"hybrid"` (verified by execution) because `"multi"` is not in `_VECTOR_ONLY_BACKENDS` (`embedding/factory.py:30,52-63`), so fan-out queries skip the vector-coercion log line that each single-index leg would emit. Cosmetic (effective mode is log-only, not returned), but the mode label is marginally misleading for a vector-only execution.
3. **`_verify_collection_model` converts only the mismatch error** (`scripts/index_occ_tickets.py:273-283`). A malformed `CHROMA_PORT` (`int(port_raw)` ValueError at `:280`), connection failure, or missing dep propagates as a raw traceback instead of the script's clean `zammad error:` `SystemExit`. Still fails loud (non-zero exit), just inconsistent UX with the fail-loud handling two dozen lines above.
4. **`compute_recall` hardcodes the `"recall@5"` key** (`scripts/zammad_mcp/eval.py:16`) while `k` is a parameter — calling with any other `k` returns a mislabeled score. Either key the label off `k` or fix `k=5` without the parameter.

### Info / nits

5. **`truncated_texts` is cumulative on the process-wide singleton** (`multilingual.py:213`; reported at `scripts/index_occ_tickets.py:235` via `get_default_multilingual_embedder()`). A second `backfill()` in the same process reports lifetime truncations, not per-run. Diagnostic-only; fine for a one-shot script.
6. **Merged response drops `facets`/`total_count`** (`_stub.py:348-349`). Irrelevant for chroma/vectorize/stub legs (always `None`), but a future Azure leg in a fan-out would silently lose `include_total_count`. Consider summing or documenting.
7. **Nits:** `tests/scripts/test_zammad_semantic_eval.py` defines `RECALL_BAR = 0.8` but nothing asserts it (live gate is manual per README — fine, the constant just implies otherwise); `tests/scripts/data/zammad_semantic_gold.json` lacks a trailing newline; `scripts/download_multilingual_model.py` has no offline test pin (necessarily network-bound — acceptable, noting the gap).

## Test evidence (executed)

- `tests/ds/test_multi_index_query.py` (7 tests) + `tests/scripts/test_zammad_semantic_eval.py` (3 tests): **10 passed**, offline, ~0.06s.
- `tests/ds/test_multilingual_embedder.py` (9 tests incl. new conflicting-preset refusal): **9 passed**, offline, ~0.18s.
- Manual probes (worktree source via `PYTHONPATH=digisearch/src` — note plain `python3` resolves a stale installed copy at `/Users/chrisstefan/Code/digithings/digisearch/...`, so unqualified reproductions test the wrong code): fail-closed propagation confirmed (`SearchBackendError: boom` surfaces); `effective_query_mode('hybrid','multi') == 'hybrid'` confirmed.
