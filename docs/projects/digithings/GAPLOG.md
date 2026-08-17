# digithings dogfood — gap log

Compare production chat quality after each onboard / stack deploy.
Plan questionnaire: Stage 8 of
[`2026-08-10-digithings-dogfood-cutover.md`](../../superpowers/plans/2026-08-10-digithings-dogfood-cutover.md).

## Canonical questions (target ≥9/10 grounded)

| # | Question | Hit? | Citation | Notes |
|---|---|---|---|---|
| 1 | What does digigraph orchestrate? | Y (digisearch) | `repo://digithings/ARCHITECTURE.md` | Local `digithings_docs` query 2026-08-10 |
| 2 | How do I install self-hosted digichat (Profile A)? | | | Not smoke-tested in chat |
| 3 | Where is digiquant's OpenAPI / run_backtest surface? | | | Not smoke-tested in chat |
| 4 | Summarize a recent ADR relevant to digichat embed CSP | | | Not smoke-tested in chat |
| 5 | What does digivault search when DIGIVAULT_ROOT is unset? | Y (digisearch) | `repo://digithings/digivault/ARCHITECTURE.md` | Local digisearch query 2026-08-10 |
| 6 | digiquant.io marketing: what is the product pitch? | | | |
| 7 | How does docs_onboard dual-sink work? | | | |
| 8 | What scopes does digikey issue for digivault writes? | | | |
| 9 | Where do AGENTS.md non-negotiables live? | | | |
| 10 | Auth on digithings.ai/chat — login wall or ungated embed? | | | |
| 11 | How is digithings chat built? / same product as customers get? | Y (digisearch + digivault) | `docs/projects/digithings/SHOWCASE.md`, `digigraph/ARCHITECTURE.md` | Local smoke 2026-08-10 — `always_retrieve_tools` + digivault skill; restart digivault after digikey rotation |

## UX / ops deltas

| Date | Area | Observation | Next action |
|---|---|---|---|
| 2026-08-10 | CI | Added `docs-onboard-digithings.yml`: push/`workflow_dispatch` on `main` → dry-run + vault→Supabase apply (`CORE_SUPABASE_*`, `production` env). digisearch dual-sink still operator/legacy (no remote FS ingest from Actions) | Confirm first green apply after promote to `main`; wire digisearch when remote ingest exists |
| 2026-08-10 | Pipeline | Stage 7 onboard on `develop` (`d6b821a2`): dry-run 71 docs (0 crawl); apply 73 vault notes @ `/tmp/digithings-onboard-vault`; digisearch ~68–73 docs → `digithings_docs` (Compose path prefix `/app/digisearch/onboard`; rate limit 30/min) | Set `DIGISEARCH_INDEX=digithings_docs` on digigraph for chat smoke; throttle ingest in runbook |
| 2026-08-10 | Supabase | `sync_onboard_vault.py --dry-run` parsed 73 notes; **apply skipped** — `CORE_SUPABASE_URL` + `CORE_SUPABASE_SERVICE_KEY` unset in env | Operator apply after secrets set |
| 2026-08-10 | Supabase titles | Normalized 15 legacy root `architecture_notes` titles (`DigiGraph` → `digigraph`, `DigiThings — Ecosystem Overview` → `digithings — Ecosystem Overview`, …) via core Supabase MCP; slugs unchanged (already lowercase). `clients/digithings/%` onboard rows were already lowercase. |
| 2026-08-10 | digichat | Local `:3005` healthy but `.env.local` points at Foundry/DataTap, not digigraph dogfood tenant | Use digithings operator embed config or retarget local tenant |
| 2026-08-10 | Dual-sink parity | Vault FS + digisearch index populated locally; production digithings.ai still on legacy Supabase corpus until sync | Run sync + redeploy smoke on `/chat` |
| 2026-08-10 | Showcase | Added `SHOWCASE.md` + `digiproject.yaml` / `config/dogfood-digiproject.yaml` for self-aware chat | Re-ingest on operator after merge |
| 2026-08-10 | Free→BYOK | digichat embed `llmAccess: free_then_byok` + in-chat BYOK on `free_quota_exceeded` (ungated digithings.ai). digigraph typed error + Gemini/Anthropic BYOK spend landed in #2048. | Wire dogfood tenant env `llmAccess` + confirm digigraph returns `free_quota_exceeded` |
| 2026-08-10 | LLM mode | `llm_mode` is policy-only (no `model_modes.yaml` `free:` product pin). Dogfood + OCC set `agents.llm.model` explicitly; free without pin errors with set agents.llm / DIGI_LLM_MODEL | Keep operator pin current when OpenRouter retires `:free` slugs |
| 2026-08-10 | Sources UI | `rag_sources` rows showed UUID `doc_id` paths; tool row labeled `rag_sources` / `digithings_docs` | Fixed activity mapper: `source_url` → readable path, `digisearch`/`digivault` labels (#2045) |
| 2026-08-10 | Answer prose | Open WebUI `<details>` / `<thinking>` still leaked: digichat uses the project-mode model id (pre-#2426 rename) which auto-enabled OpenWebUI format with no opt-out; suppress skipped tools but not thinking | digigraph: suppress + `X-Response-Format: plain` opt out; digichat defaults OpenWebUI off and always sends plain on dogfood stream |
| 2026-08-10 | digivault tool | Skill `digivault` omitted from default `skills.enabled`; `DIGIVAULT_URL` empty hid skill even when project YAML had `digivault_url` | `always_retrieve_tools` prefetch + `skills.enabled: [search, digivault]`; compose override sets `DIGIVAULT_URL`; restart digivault after digikey |
| 2026-08-10 | digivault auth | Stale JWKS cache after digikey restart → `invalid_token` on orchestrator routes until `docker compose restart digivault` | Operator: restart digivault with digikey after JWKS rotation (local override file is gitignored) |
| 2026-08-10 | **Full apply (this run)** | `run_onboard.py --dry-run` with real network access: `pages_seen=33` (up from the earlier 18-page partial), `docs_kept=84` (10 crawled + 67 repo + 7 openapi). Full apply: 84 vault notes written locally (`--vault-root`, bypassing digivault HTTP auth which the API-writer path needs a `--digivault-token` for), 84 docs posted to digisearch (`digithings_docs`, paced client-side under the 30/60s `/ingest` rate limit — no repo change made for this, see note below). `sync_onboard_vault.py --apply` synced **84/84 notes** to production Supabase `architecture_notes` (verified via REST count). Same run repeated for OCC (see `online-compliance-center/GAPLOG.md`). | Production Profile A stack (`frontend/digithings-stack-cloudflare`) still ships the original 7/4 curated seed stubs baked into the container image — **not yet refreshed** with this corpus. Bake-vs-live-dual-sink decision (per #2118 acceptance criteria) is still open; this run populated the local dev digisearch/digivault stack + Supabase, not the Cloudflare container's own Chroma volume. |
| 2026-08-11 | **Correction: digisearch chunk count was wrong** | The "6799 chunks" reported above was contaminated: re-running `run_onboard.py` three times against the **same `--workdir`** (debugging unrelated auth/mount errors) silently re-ingested every source with fresh `doc_id`s each time — no clear/dedupe of workspace state between invocations (filed as [#2138](https://github.com/digithings-ai/digithings/issues/2138), distinct from the Chroma-`add()`-vs-`upsert()` issue tracked as #2122). Verified in Chroma: 275 distinct `doc_id`s for only 85 `source_url`s before the fix. Wiped `digithings_docs` and re-ingested once, from a fresh workdir, confirmed **exactly 84 `doc_id`s for 84 sources** (1:1, zero duplicates) at **1998 chunks total** — avg ~23.8 chunks/doc, in line with OCC's 629 chunks / 28 docs ≈ 22.5 chunks/doc. The original 6799-vs-629 disparity that prompted this check was almost entirely the duplication bug, not a real content-size difference. Vault/Supabase notes (84/28) were never affected — `sync_onboard_vault.py` upserts by `vault_path`, so reruns overwrite rather than duplicate. | None — this row supersedes the chunk count in the row above; #2138 tracks hardening `run_onboard.py` against workdir reuse. |
| 2026-08-11 | **Widened marketing prefixes + re-ingest** | `docs_path_prefixes` widened (#2144, #2145) to include digithings.ai customer-facing pages `/about`, `/quality`, `/security`, `/services`, `/team` (verified against live nav via `curl`; digithings.ai/digiquant.io block WebFetch/browser bot detection). digiquant.io's `/olympus` and `/strategies` deliberately excluded — live interactive tools, not static content. Single clean re-ingest (crawl + vault + digisearch, one process, verified no concurrent runs): `docs_kept` **84 → 89** (+5, exactly the new prefixes), `digithings_docs` **89 doc_ids for 89 sources** (1:1, zero duplicates), **2068 chunks total**. `sync_onboard_vault.py --apply` synced **89/89 notes** to production Supabase (verified). | Chunking/vault-storage architecture review in progress (page/section-aware segmentation instead of flat 512-char chunking) — see `docs/superpowers/specs/` once written. Production Profile A stack still not refreshed with any of this corpus (unchanged from the row above). |

| 2026-08-11 | **Content-aware chunking live run (#2153)** | Segmentation shipped and re-ingested on the real corpus. digisearch `digithings_docs`: **1235 chunks / 89 sources / 89 doc_ids** (1:1, no duplicates), **96% of chunks carry `segment_label`** (heading breadcrumbs), mean 786 / median 614 chars, **max 2000, zero over the ceiling** (was: 2127 chunks, 0% labelled, max 9419, 28 over). digivault: **1279 per-segment notes + hub notes** from 89 docs (was 89 flat notes). Supabase `architecture_notes` synced and verified at **1279** rows for `clients/digithings/`. Retrieval spot-check returns informative heading breadcrumbs on JWT/Atlas queries. | **A container image rebuild is required to ship this** — the live test initially produced 0% segmented chunks because `docker compose up` reuses the baked image; only `docker compose build` picked up the new code. The production Cloudflare Profile A stack bakes digisearch the same way, so its image must be rebuilt/redeployed, not just merged. |

## Legacy retirement tracker

| Artifact | Keep until | Done? |
|---|---|---|
| `scripts/sync_architecture_vault.py` | Onboard + `sync_onboard_vault.py` cover vault notes | |
| `docs/projects/digithings-guide/` + `reindex_digithings_guide.py` | digisearch dual-sink verified on dogfood | |

## Blocked on Stage A (human)

- [ ] GHCR `ghcr.io/digithings-ai/{digikey,digigraph,digivault}` pullable from `main`
- [ ] `DIGI_IMAGE_TAG` pin recorded for operator env
- [ ] Profile A GHCR cutover on digithings Tunnel host
