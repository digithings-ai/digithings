# Review — PR #4962: select multilingual provider by model id, no aliases

- Reviewer: subagent (read-only review)
- Subject: digithings-ai/digithings#4962, branch `task/4756-feat-zammad---semantic-ticket-search-ove`, commit `412118813` on top of `origin/module/digisearch`
- Scope: `digisearch/src/digisearch/embedding/factory.py`, `scripts/index_occ_tickets.py`, `tests/ds/test_multilingual_embedder.py`, `tests/ds/test_chunkers.py` (fingerprint only), `scripts/zammad_mcp/README.md`, `digisearch/ARCHITECTURE.md`
- Verdict: **Approve — no blocking findings.** All six check areas pass; one low-severity coverage note + two info notes below.

## Severity counts

- High: 0 | Medium: 0 | Low: 1 | Info: 2

## Checks

### (1) Factory branch — PASS
- Case-insensitive match with strip: `digisearch/src/digisearch/embedding/factory.py:128` — `if name.strip().lower() == "xenova/paraphrase-multilingual-minilm-l12-v2":`. Upstream resolution already lowercases env/config values (`factory.py:105`, `factory.py:114`), so mixed-case env values also resolve.
- No alias remnants in factory: old tuple `("multilingual", "multi", "paraphrase-multilingual", "minilm-multi")` is gone from `factory.py`; the only remaining occurrence is the intentional rejection test (`tests/ds/test_multilingual_embedder.py:62`).
- Conflicting model value rejected: `factory.py:134-138` raises `EmbeddingConfigError(f"embedding provider {name!r} ships a single model ({MULTILINGUAL_MODEL_ID!r}); got model {model!r}")` when `DIGISEARCH_EMBEDDING_MODEL` differs (case-insensitive compare against canonical constant).
- Error message accurate: `factory.py:150-153` — `unknown embedding provider {name!r}; expected minilm, openai, or a model id (e.g. 'Xenova/paraphrase-multilingual-MiniLM-L12-v2')`. Example id matches canonical `MULTILINGUAL_MODEL_ID = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"` (`digisearch/src/digisearch/embedding/providers/multilingual.py:22`).

### (2) No remaining old-alias provider references — PASS
- No live `EMBEDDING_PROVIDER=multilingual` / `="multilingual"` assignment in source, scripts, docs, or tests (grep over `DIGISEARCH_EMBEDDING_PROVIDER` confirms; only historical `review-4946.md:42`, `review-4956.md:19` and the `test_chunkers.py:329` history comment mention the old value).
- Old aliases now fail loud: `test_multilingual_embedder.py:59-64` pins that all four aliases raise `EmbeddingConfigError: unknown embedding provider`. Consequence for backfill presets: a stale `=multilingual` preset now raises at resolve (`scripts/index_occ_tickets.py:220-223` → `SystemExit "cannot resolve embedding provider"`) instead of the `isinstance` path — still fail-loud, no silent wrong-stamp.

### (3) Backfill pin / verify / fail-loud consistent with model id — PASS
- Pin uses constant, not literal: `scripts/index_occ_tickets.py:218` — `os.environ["DIGISEARCH_EMBEDDING_PROVIDER"] = MULTILINGUAL_MODEL_ID` (imported `scripts/index_occ_tickets.py:202-203`).
- Conflicting preset aborts before mutation with model-id message: `scripts/index_occ_tickets.py:224-229` (`refusing to index ... not {MULTILINGUAL_MODEL_ID!r}; ... set it to {MULTILINGUAL_MODEL_ID!r}`).
- Unresolvable preset aborts: `scripts/index_occ_tickets.py:220-223`.
- Scoped + restored: `try/finally` `scripts/index_occ_tickets.py:230-236` (pop on pin path, restore on preset path); dry-run/empty returns before any env code (`scripts/index_occ_tickets.py:195-196`).
- Post-write verify re-opens Chroma with the multilingual provider and fails loud on stamp mismatch: `scripts/index_occ_tickets.py:243-290`.

### (4) Docs consistent — PASS
- `digisearch/ARCHITECTURE.md:2134` — provider row now `minilm | openai | model id (Xenova/...)`.
- `scripts/index_occ_tickets.py:9-10`, `:142-143`, `:211-215` — module/backfill docstrings pin to the model id.
- `scripts/zammad_mcp/README.md:137-138`, `:155-157`, `:164-165` — pin, fan-out, and rescrape runbook all name the model id; `occ_help`/`occ_tickets` warnings retained (`README.md:141-143`, `:157-159`).

### (5) Fingerprint re-record legitimate — PASS (verified by execution)
- `tests/ds/test_chunkers.py:335-336` documents "Hashes only (count still 127) re-recorded for #4756 (model-id provider value in ARCHITECTURE.md)".
- Recomputed locally: chunk count 127 == recorded 127; all chunks ≤2000; 0 hash mismatches against recorded list (`test_chunkers.py:343`, `:345-346`, assertion list `:347-473`).
- Diff shows exactly one hash changed at that position (`9f90d4fc05b96535` → `9c818ae221f9e5fd`, `test_chunkers.py:461`), consistent with the single provider-row edit in `ARCHITECTURE.md`.

### (6) Tests pin the new behavior — PASS
- Literal-to-constant lock: `tests/ds/test_multilingual_embedder.py:52` — `assert MULTILINGUAL_MODEL_ID.lower() == "xenova/paraphrase-multilingual-minilm-l12-v2"`, guarding the factory literal (`factory.py:128`) against drift.
- Canonical + lowercase build paths: `test_multilingual_embedder.py:53-56` (`_build_raw_provider(MULTILINGUAL_MODEL_ID, None)` and `.lower()` both → `MultilingualEmbedder`).
- Alias rejection: `test_multilingual_embedder.py:59-64` (all four old aliases → `unknown embedding provider`).
- Pipeline + backfill pin/restore/conflict: `test_multilingual_embedder.py:67-77` (env model id → pipeline unwraps to `MultilingualEmbedder`), `:311-314` (backend saw `MULTILINGUAL_MODEL_ID` constant), `:315-316` + `:260` (no env leakage), `:349-353` (conflicting `minilm` preset → `SystemExit "refusing to index"`, env untouched).

## Findings

- [Low] Conflicting-`DIGISEARCH_EMBEDDING_MODEL` branch untested. `factory.py:134-138` (provider=model-id + mismatched model → `EmbeddingConfigError`) has no direct test; the suite pins alias rejection and the literal lock but never calls e.g. `_build_raw_provider(MULTILINGUAL_MODEL_ID, "other")`. Suggest a 3-line test asserting the raise. Not blocking — branch is straight-line and message-verified by reading.
- [Info] Error message lists only `minilm, openai` though factory also accepts `local/onnx` (`factory.py:120`) and `oai` (`factory.py:140`). Pre-existing pattern (old message also omitted sub-aliases); documented values are accurate.
- [Info] Case/whitespace coverage is by code, not by test: `factory.py:105,128` handle `.strip().lower()`, but tests only exercise canonical and `.lower()` (`test_multilingual_embedder.py:53-56`), not padded/mixed-case input. Trivially holds; no action needed.
