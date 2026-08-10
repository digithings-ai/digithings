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
| 2026-08-10 | Free→BYOK | digichat embed `llmAccess: free_then_byok` + in-chat BYOK on `free_quota_exceeded` (ungated digithings.ai). digigraph typed error + Gemini/Anthropic BYOK spend owned by sibling PR. | Wire dogfood tenant env `llmAccess` + confirm digigraph returns `free_quota_exceeded` |
| 2026-08-10 | Sources UI | `rag_sources` rows showed UUID `doc_id` paths; tool row labeled `rag_sources` / `digithings_docs` | Fixed activity mapper: `source_url` → readable path, `digisearch`/`digivault` labels (#2045) |
| 2026-08-10 | Answer prose | Open WebUI `<details>` tool dumps leaked into assistant text when `DIGICHAT_OPENWEBUI_FORMAT=1` | digichat trace stream: `X-Suppress-Tool-Stream` + strip helper; default OpenWebUI off for dogfood |
| 2026-08-10 | digivault tool | Skill `digivault` omitted from default `skills.enabled`; `DIGIVAULT_URL` empty hid skill even when project YAML had `digivault_url` | `always_retrieve_tools` prefetch + `skills.enabled: [search, digivault]`; compose override sets `DIGIVAULT_URL`; restart digivault after digikey |
| 2026-08-10 | digivault auth | Stale JWKS cache after digikey restart → `invalid_token` on orchestrator routes until `docker compose restart digivault` | Documented in `docker-compose.override.yml`; restart digivault with digikey |

## Legacy retirement tracker

| Artifact | Keep until | Done? |
|---|---|---|
| `scripts/sync_architecture_vault.py` | Onboard + `sync_onboard_vault.py` cover vault notes | |
| `docs/projects/digithings-guide/` + `reindex_digithings_guide.py` | digisearch dual-sink verified on dogfood | |

## Blocked on Stage A (human)

- [ ] GHCR `ghcr.io/digithings-ai/{digikey,digigraph,digivault}` pullable from `main`
- [ ] `DIGI_IMAGE_TAG` pin recorded for operator env
- [ ] Profile A GHCR cutover on digithings Tunnel host
