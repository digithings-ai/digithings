# Review: PR #4946 — multilingual ticket index + occ_tickets backfill

- Reviewer: subagent (fresh-context review)
- Subject: PR #4946, commit `76629ec18` on top of `origin/module/digisearch`
- Scope: 7 files — `digisearch/src/digisearch/embedding/providers/multilingual.py` (new),
  `digisearch/src/digisearch/embedding/factory.py`, `digisearch/pyproject.toml`,
  `digisearch/ARCHITECTURE.md`, `scripts/index_occ_tickets.py` (new),
  `scripts/zammad_mcp/README.md`, `tests/ds/test_multilingual_embedder.py` (new)
- Verification: read all changed files in full; traced `index_chunks` →
  `route_add_chunks` (`digisearch/src/digisearch/search/_stub.py:308`) →
  `ChromaBackend.add/query` (`digisearch/src/digisearch/indexes/backends/chroma.py:181,240`);
  ran `python3 -m pytest tests/ds/test_multilingual_embedder.py` (5 passed, ~0.03s, no network).

## Verdict: needs-changes

One load-bearing defect (F1): the documented happy path writes multilingual vectors
into a collection the backend labels as MiniLM, and queries against it embed with the
wrong model unless the operator guesses an undocumented env var. F2 is a real (small)
functional bug. The rest are lows/nits.

## Findings

### High

**F1 (high) — backfill never pins `DIGISEARCH_EMBEDDING_PROVIDER`, so the backend stamps the wrong model id and queries embed in the wrong space.**
`scripts/index_occ_tickets.py:196-197` passes the multilingual provider only to
`index_chunks` (which correctly fills `chunk.embedding` via `apply_embeddings`,
`digisearch/src/digisearch/pipeline/ingest.py:73-99`). But `index_chunks` then calls
`route_add_chunks`, which constructs `ChromaBackend(embedding_provider=_resolved_embedding_provider())`
(`_stub.py:329,343,362`), and that resolves from env/config with default `minilm`
(`factory.py:230-236`). `ChromaBackend.add` upserts the precomputed multilingual vectors
as-is (`chroma.py:198-202`) yet asserts/stamps collection metadata with the *backend's*
provider (`chroma.py:186,211`). On a fresh `occ_tickets` collection under the README's
documented command (`scripts/zammad_mcp/README.md` usage block, no env var mentioned),
the collection gets stamped `embedding_model_id=all-MiniLM-L6-v2-384` while holding
multilingual vectors — the exact false-compatibility labeling `_stamp_collection_metadata`
is designed to prevent (`chroma.py:162-170`). Worse, query time embeds with MiniLM
(`chroma.py:266`) against multilingual doc vectors: same 384-dim, cosine, no error —
silently wrong retrieval, defeating the PR's purpose. And if the operator later reruns
*with* the env var set, `_assert_collection_model` (`chroma.py:124-142`) raises a
confusing mismatch on an index whose vectors were always multilingual.
Fix: `os.environ.setdefault("DIGISEARCH_EMBEDDING_PROVIDER", "multilingual")` in
`backfill()` before indexing, and document the var in the README usage block.

### Medium

**F2 (medium) — `--snapshot-date` is silently ignored for chunk metadata.**
`backfill()` accepts `snapshot_date` (`index_occ_tickets.py:140-144`), declares
`global SNAPSHOT_DATE` (`:147`) but never assigns it; `build_ticket_chunks` stamps
the module-global `SNAPSHOT_DATE` (`:107`), while the summary reports the parameter
(`:187`). So `--snapshot-date 2026-11-01` prints `[snapshot 2026-11-01]` while every
chunk still carries `2026-10-01`. Fix: assign the global or thread the parameter
through to `build_ticket_chunks`.

### Low

**F3 (low) — ONNX positional fallback swaps mask/type-id order and clobbers good mappings.**
`multilingual.py:173-182`: the name-mapped branch pairs correctly, but when
`len(feed) < len(names)` the whole feed is replaced positionally with
`ordered = [feed_ids, feed_types, feed_mask]`, i.e. position 1 = token_type_ids,
position 2 = attention_mask — the reverse of the conventional ONNX export order
`[input_ids, attention_mask, token_type_ids]`. On any model with renamed inputs this
silently feeds the mask as type ids and vice versa. Also discards entries that *did*
match by name. Suggest mapping known names first and only guessing unknowns.

**F4 (low) — "every visible ticket" is silently capped at 500.**
Docstring (`index_occ_tickets.py:3-4`) claims all visible tickets, but
`client.list_tickets()` defaults to `MAX_REPORT_TICKETS = 500`
(`scripts/zammad_mcp/client.py:22,502-509`). Instances with >500 tickets get a
truncated snapshot; the summary (`tickets_scanned`) reports the capped count with no
truncation signal. Note the cap or surface it.

**F5 (low) — `--max-tickets 0` (or negative) silently indexes 1 ticket.**
`index_occ_tickets.py:158`: `tickets[: max(1, max_tickets)]`. A `0` cap should mean
"none" (or be rejected), not one.

### Nits

**F6 (nit) — `if not content: continue` is unreachable; docstring overclaims.**
`index_occ_tickets.py:91-102`: `header` is always non-empty, so `content` is never
empty and "one Chunk per non-empty article" (`:73` docstring) is vacuous — empty-body
articles still produce header-only chunks. Either filter on `body` or fix the docstring.

**F7 (nit) — `_text` duplicates `formatting._field`.**
`index_occ_tickets.py:32-42` vs `scripts/zammad_mcp/formatting.py:88-99`: identical
dict-key list and `"-"` rule. Reuse the existing helper.

**F8 (nit) — `numpy` imported but not declared.**
`multilingual.py:142` does `import numpy as np`, but the new
`embedding-multilingual` extra (`digisearch/pyproject.toml:51`) lists only
`onnxruntime/tokenizers/huggingface_hub` — numpy arrives transitively via onnxruntime.
Add an explicit floor to the extra.

**F9 (nit) — stale parenthetical in factory error message.**
`factory.py:140-143`: `"(new providers are out of scope for the wire-embed task)"`
is self-contradicted by this PR, which adds a new provider two lines above (`:124`).

**F10 (nit) — ONNX math and `backfill()` are untested.**
The 5 tests pin factory wiring, singleton sharing, and chunk metadata — all offline
(verified: suite passes in ~0.03s, constructor is lazy, `embed_fn` stub avoids
`snapshot_download`). But `_embed_onnx` pooling/normalization/feed logic
(`multilingual.py:141-191`) and the whole `backfill()` failure/dry-run path have zero
coverage; both are testable offline with a fake session/tokenizer and a stubbed
`ZammadClient`. Given F1 lives exactly on the untested path, one backfill test with
`DIGISEARCH_EMBEDDING_PROVIDER` unset would have caught it.

## Confirmed correct (no findings)

- Pool/pad/normalize math: name-based input mapping, pad-id lookup with fallback,
  mask-zero padding, mean-pool over non-pad tokens with `clip(min=1.0)`, zero-norm
  guard (`multilingual.py:159-191`). Truncation slices ids/mask/type-ids consistently;
  `max(1, ...)` guards degenerate caps (`:68`).
- Thread safety: double-checked locking in `_load` (`:122-139`) and module-level
  singleton lock (`:194-201`); ORT `run` is thread-safe for concurrent inference.
- Factory branch (`factory.py:124-129,141`): no shadowing of `minilm` aliases; error
  message updated; ARCHITECTURE provider table + `DIGISEARCH_EMBEDDING_PROVIDER` docs
  consistent.
- pyproject: `>=`-floor style matches file conventions; extra included in `all`
  (`digisearch/pyproject.toml:97`); `dev` correctly untouched (it carries neither
  `embedding` nor `chroma` today).
- Backfill GET-only discipline: only `list_tickets`/`get_articles`/`resolve_user`,
  all via `self._get` (`client.py:403,497,515`); script itself makes no HTTP calls.
- Chroma-safety: `_clean_metadata` drops `None`, orders the `bool`-before-`int` check
  correctly, stringifies the rest (`index_occ_tickets.py:53-65`).
- Chunk id/doc_id uniqueness holds on the backfill path (id-less tickets are skipped,
  `:163-166`); per-ticket article enumeration makes reruns idempotent overwrites.
- Dry-run returns before any indexing import (`:190-191`).
- `ChromaBackend` model-id stamp/assert guards exist (`chroma.py:100-110,124-142`),
  which is precisely what makes F1's mislabeling stick.
- Out of scope by design (noted, no change asked): ADR-0025 (Proposed) names a
  different model (`gte-multilingual-base`, 768-dim) for the `occ_help` cutover; this
  PR targets a separate demo `occ_tickets` index, so the divergence is acceptable but
  should stay explicit — do not query `occ_tickets` with the `occ_help` provider or
  vice versa.

## Severity counts

- High: 1 (F1)
- Medium: 1 (F2)
- Low: 3 (F3–F5)
- Nits: 5 (F6–F10)
- Total: 10
