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

## UX / ops deltas

| Date | Area | Observation | Next action |
|---|---|---|---|
| 2026-08-10 | Pipeline | Stage 7 onboard on `develop` (`d6b821a2`): dry-run 71 docs (0 crawl); apply 73 vault notes @ `/tmp/digithings-onboard-vault`; digisearch ~68–73 docs → `digithings_docs` (Compose path prefix `/app/digisearch/onboard`; rate limit 30/min) | Set `DIGISEARCH_INDEX=digithings_docs` on digigraph for chat smoke; throttle ingest in runbook |
| 2026-08-10 | Supabase | `sync_onboard_vault.py --dry-run` parsed 73 notes; **apply skipped** — `CORE_SUPABASE_URL` + `CORE_SUPABASE_SERVICE_KEY` unset in env | Operator apply after secrets set |
| 2026-08-10 | Supabase titles | Legacy `architecture_notes` rows at root vault paths (`digigraph`, `digikey`, …) still use CamelCase titles (`DigiGraph`, …) from `sync_architecture_vault.py`. New `clients/digithings/%` onboard rows use lowercase prose titles. **No bulk rewrite** — legacy rows refresh on cutover re-sync only. |
| 2026-08-10 | digichat | Local `:3005` healthy but `.env.local` points at Foundry/DataTap, not digigraph dogfood tenant | Use digithings operator embed config or retarget local tenant |
| 2026-08-10 | Dual-sink parity | Vault FS + digisearch index populated locally; production digithings.ai still on legacy Supabase corpus until sync | Run sync + redeploy smoke on `/chat` |
| 2026-08-10 | Legacy retirement | Parallel legacy scripts not retired | Cut over after prod sync verified |

## Legacy retirement tracker

| Artifact | Keep until | Done? |
|---|---|---|
| `scripts/sync_architecture_vault.py` | Onboard + `sync_onboard_vault.py` cover vault notes | |
| `docs/projects/digithings-guide/` + `reindex_digithings_guide.py` | digisearch dual-sink verified on dogfood | |

## Blocked on Stage A (human)

- [ ] GHCR `ghcr.io/digithings-ai/{digikey,digigraph,digivault}` pullable from `main`
- [ ] `DIGI_IMAGE_TAG` pin recorded for operator env
- [ ] Profile A GHCR cutover on digithings Tunnel host
