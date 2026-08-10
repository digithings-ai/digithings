# Client ops pipelines

Offline, multi-client workflows that live under `scripts/` with per-client
manifests under `docs/projects/<client>/` (or private `projects/`). These are
**not** Digi peer modules.

| Pipeline | Parent script | Purpose | Sinks |
|---|---|---|---|
| **Client docs onboard** | `scripts/docs_onboard/run_onboard.py` | Website URL → docs-focused crawl → PDFs → store | digivault and/or digisearch |
| **digithings.ai corpus CI** | `.github/workflows/docs-onboard-digithings.yml` | On `main` doc changes: onboard → `sync_onboard_vault.py` | Supabase `architecture_notes` (vault); digisearch operator-side |
| *(later)* digiquant research ingest | TBD | Separate entry for quant research corpora | digisearch / vault as designed |

## Module roles

- **digifetch** — fetch/scrape transport
- **digisearch** — parse, OCR, chunk, embed, index
- **digivault** — notes, graph, MCP/agent over notes (local search when `DIGIVAULT_ROOT` set)

## Related

- Runbook: [`docs/digichat/CLIENT-DOCS-ONBOARD.md`](../digichat/CLIENT-DOCS-ONBOARD.md)
- Plan: [`docs/superpowers/plans/2026-08-09-digichat-corpus-ingest.md`](../superpowers/plans/2026-08-09-digichat-corpus-ingest.md)
- Fit: [`docs/architecture/digichat-self-host-picks-fit.md`](../architecture/digichat-self-host-picks-fit.md)
