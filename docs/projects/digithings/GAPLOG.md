# digithings dogfood — gap log

Compare production chat quality after each onboard / stack deploy.
Plan questionnaire: Stage 8 of
[`2026-08-10-digithings-dogfood-cutover.md`](../../superpowers/plans/2026-08-10-digithings-dogfood-cutover.md).

## Canonical questions (target ≥9/10 grounded)

| # | Question | Hit? | Citation | Notes |
|---|---|---|---|---|
| 1 | What does digigraph orchestrate? | | | |
| 2 | How do I install self-hosted digichat (Profile A)? | | | |
| 3 | Where is digiquant's OpenAPI / run_backtest surface? | | | |
| 4 | Summarize a recent ADR relevant to digichat embed CSP | | | |
| 5 | What does digivault search when DIGIVAULT_ROOT is unset? | | | |
| 6 | digiquant.io marketing: what is the product pitch? | | | |
| 7 | How does docs_onboard dual-sink work? | | | |
| 8 | What scopes does digikey issue for digivault writes? | | | |
| 9 | Where do AGENTS.md non-negotiables live? | | | |
| 10 | Auth on digithings.ai/chat — login wall or ungated embed? | | | |

## UX / ops deltas

| Date | Area | Observation | Next action |
|---|---|---|---|
| | Auth | | |
| | Citations | | |
| | Latency | | |
| | Dual-sink parity | | |
| | Legacy retirement | | |

## Legacy retirement tracker

| Artifact | Keep until | Done? |
|---|---|---|
| `scripts/sync_architecture_vault.py` | Onboard + `sync_onboard_vault.py` cover vault notes | |
| `docs/projects/digithings-guide/` + `reindex_digithings_guide.py` | digisearch dual-sink verified on dogfood | |

## Blocked on Stage A (human)

- [ ] GHCR `ghcr.io/digithings-ai/{digikey,digigraph,digivault}` pullable from `main`
- [ ] `DIGI_IMAGE_TAG` pin recorded for operator env
- [ ] Profile A GHCR cutover on digithings Tunnel host
