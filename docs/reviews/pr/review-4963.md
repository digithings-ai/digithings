# Review — PR #4963 (commit e395c1859, `task/4756-feat-zammad---semantic-ticket-search-ove`)

- Reviewer: subagent (read-only review)
- Subject: PR digithings-ai/digithings#4963 — "feat(occ): wire multilingual provider + fan-out tenant into stack deploy" (1 commit on top of `origin/module/digisearch`)
- Verdict: **Request changes** — F1 breaks the repo's own corpus-map drift gate (`scripts/check_tenant_corpus_map.py` exits 1); F2–F3 leave stale tests that no longer pin what they claim.
- Severity counts: High 1 · Medium 2 · Low 3

## F1 (high) — `index.ts` fallback tenant map not updated; drift gate red

- `apps/digithings-stack-cloudflare/src/index.ts:131-133`: `??` fallback still has `"occ":{"digisearchIndex":"occ_help",…}` (single index) plus the OLD prompt (`customer emails stay masked`, `internal ticket notes are never shown`, `Ticket questions go to the read-only zammad tools … not the document corpus`).
- `apps/digithings-stack-cloudflare/wrangler.toml:293` and `infra/digichat-release/compose.profile-a-bundle.override.yml:6` were both updated to `"digisearchIndex":"occ_help,occ_tickets"` with the new TWO-places/demo-mode prompt.
- Proof — the repo's own checker fails:
  `python3 scripts/check_tenant_corpus_map.py` → exit 1, `index.ts[occ].digisearchIndex: 'occ_help' != embed 'occ_help,occ_tickets'`.
- Impact: any path with `DIGI_TENANT_CORPUS_MAP` unset uses the code fallback → old docs-only corpus + a prompt that contradicts the new `occ_tickets` index (masking claims vs demo-mode full names/emails). Fix: copy the wrangler/compose `occ` entry (index pair + prompt) into the `index.ts:131-133` fallback. (Prompt text itself is not diffed by the checker — only index/prefix — but shipping the stale prompt is the user-visible half of the bug.)

## F2 (medium) — corpus-parity pin test still pins the old map

- `tests/dg/test_tenant_corpus_parity.py:30-38`: `_RAW_MAP` / `_EXPECTED` still pin `"occ":{"digisearchIndex":"occ_help",…}`, while its docstring claims the string is "verbatim from" the production files — no longer true after this PR. The test is self-contained so it stays green while production drifts; update `_RAW_MAP` and `_EXPECTED` to the `occ_help,occ_tickets` pair. (Pre-existing nit: docstring cites `override.yml:11`, which is the `DIGICHAT_EMBED_TENANTS` line; the corpus map is line 6.)

## F3 (medium) — dry-run test is stale: dead patch, false docstring + unacknowledged behavior change

- `tests/scripts/test_vectorize_sync.py:440-487` (`test_dry_run_makes_zero_embed_calls`): imports `digisearch.embedding.providers.minilm` (`:450`) and patches `MiniLMEmbedder` (`:476`), which the new `main()` never constructs — dead patch. The docstring "must not construct … the embedder" is contradicted by `scripts/vectorize_sync.py:423` (resolver now runs even for `--dry-run`). The test passes only because resolution is lazy and `embed()` is never called. Re-point the patch at `digisearch.embedding.factory.resolve_backend_embedding_provider`.
- Behavior change worth stating in the PR: `--dry-run` now requires a loadable provider (e.g. `DIGISEARCH_EMBEDDING_PROVIDER=openai` without `OPENAI_API_KEY`, or an unknown id, raises `EmbeddingConfigError` even though nothing is embedded). Previously dry-run touched no provider at all.
- Comment overclaim at `scripts/vectorize_sync.py:421-422` ("so the reported stamp is always the real one"): dry-run prints only the count (`:444`); the `model_id` stamp lands in `Chunk` metadata (`:244`) that the dry-run `_CountingSink` (`:397-407`) discards. Real effect is fail-fast provider validation, not a reported stamp. Reword or print the resolved `model_id` in dry-run output.

## F4 (low) — guard-dimensions parity not asserted

- `tests/scripts/test_vectorize_sync.py:266-299`: `_CustomProvider.dimensions` is 123, but `_fake_assert_index_model` captures only `model_id`, never `dimensions` — a regressed hardcoded `dimensions=384` in the `assert_index_model` call (`scripts/vectorize_sync.py:429`) would still pass. Capture and assert `dimensions == 123`. (Implementation itself is correct: same-object `model_id` → `:429` guard and `:436` stamp, `embedder.dimensions` → guard.)

## F5 (low) — bundle example env still single-index

- `infra/digichat-release/.env.profile-a-bundle.example:37` (`DIGICHAT_EMBED_TENANTS` occ backend `occ_help`) and `:52` (`DIGI_TENANT_CORPUS_MAP` single `occ_help`) contradict the updated override in the same bundle. If operators copy-paste from the example, they deploy the old behavior. Update both to the pair (and the new prompt if the example carries one — check).

## F6 (low/question) — `occ-embed.yaml` MCP default still singular

- `apps/digichat/config/examples/occ-embed.yaml:38` backend is now `occ_help,occ_tickets`, but the MCP `digisearch` server default at `:75` is still `index_name: occ_help`. Comma fan-out is supported end-to-end (`digisearch/src/digisearch/search/_stub.py:326-349`, used by `digisearch/src/digisearch/server.py:681`), so the pair would work there too. If docs-only default is intentional, note why; otherwise update to the pair.

## Verified OK (checked, no finding)

- **Model-id consistency**: `index.ts:130` and `wrangler.toml:283` both exactly `Xenova/paraphrase-multilingual-MiniLM-L12-v2`, matching `MULTILINGUAL_MODEL_ID` (`digisearch/src/digisearch/embedding/providers/multilingual.py:30`); `Env` type extended (`index.ts:400`); no other container allowlist needs the var (no `DIGISEARCH_*` refs under `container/`).
- **`getattr` fallback correct**: `OpenAIEmbedder` exposes `.model`, not `.model_id` (`providers/openai.py:19`); MiniLM/Multilingual expose `.model_id`; `resolve_backend_embedding_provider` returns the raw unwrapped provider (`factory.py:201-214`), so the `model_id`-then-`model` chain (`vectorize_sync.py:424-427`) resolves on all three; OpenAI `dimensions` needs no client.
- **Test rewrites faithful** (non-dry-run): factory-resolver patch correctly replaces the `MINILM_MODEL_ID` patch; `_Credential_capturing` stub provider correct; `MiniLMEmbedder→object` patch removal correct (no remaining reference in `main`); `_FakeVectorizeBackend` reformat behavior-identical. Suite: 28/28 pass.
- **Tenant JSON validity**: wrangler map parsed via `tomllib`+`json`, compose maps via `yaml`+`json` — all valid; `occ` pair present, `digithings` entry byte-identical (`digithings_docs`/`clients/digithings`); new prompt coherent (TWO places, demo-mode full names/emails, `[internal]` tagging; no `stay masked` / `never shown` leftovers; `\n` + `\u2014` decode cleanly through both TOML-basic-string and YAML-single-quote layers).
- **`occ-embed.yaml`**: valid YAML, pair at `:38`.
- **Fan-out is live, not cosmetic**: comma split + RRF merge + fail-closed per index (`_stub.py:334-349`).
- **Other `occ_help` singles** (READMEs, `container/seed_*`, `entrypoint.sh`, `supervisord.conf`, `docs/…`, unit-test fixtures in `apps/digichat`, `tests/dg/test_api.py`, `test_corpus_routing.py`) are docs/seeds/fixtures — out of scope except F2/F5 above.
