# OCC client #1 — gap log

Compare-and-gap after wiring digithings.ai/chat/occ. Digi names lowercase.

## Corpus / ingest

| Gap | Status | Notes |
|-----|--------|-------|
| **sitaas crawl approval** | **HOLD** | Manifest ingest hold remains. Do not silently crawl production help content without written approval. Local `--dry-run` is allowed; full apply waits on human sign-off (SCOPE open Q1). |
| One-shot static corpus | Open | Demo expects a single onboard apply; no scheduled crawl CI. Re-run only if help content changes. |
| Sitemap HTTP 500 | Known | BFS from seed + PDF link extraction (SCOPE). |
| Accordion markdown quality | Open | FAQ HTML may need post-process after first dry-run review. |
| YouTube e-learning (~14) | Deferred | Out of scope v1. |
| Rate limits on scrape_site | Open | Verify polite delays before production re-crawl. |
| Battlecards | Open | Exclude unless linked from help and explicitly approved. |

## Storage

| Choice | Decision |
|--------|----------|
| Supabase table | **Reuse `architecture_notes`** with path prefix `clients/online-compliance-center/` (same as digithings dogfood pattern). Not a new table. |
| digisearch | Index `occ_help` |

## Routing / isolation

| Gap | Status | Notes |
|-----|--------|-------|
| Per-tenant digisearch index | Landed (#2051) | Headers `X-Digi-Corpus-Index` + `DIGI_TENANT_CORPUS_MAP`; wire operator env |
| digivault path_prefix | Landed (#2051) | Tool arg + local/Supabase filter; RPC optional path_prefix when migration 068 applied |
| Shared digigraph digiproject | Documented | OCC digiproject for OCC-only stacks; shared stack uses corpus map/headers |
| free_then_byok on develop | Landed (#2048) | Operator JSON may include `llmAccess: free_then_byok`; ungated works without it |

## Prod cutover still needed

- Lift ingest hold after crawl approval; run one-shot onboard + `sync_onboard_vault.py`
- Operator env: add `occ.digithings.ai` to `DIGICHAT_EMBED_HOSTS` / `DIGICHAT_EMBED_TENANTS`
- Cloudflare Pages deploy of digithings-web including `/chat/occ`
- Apply digivault Supabase migration for `path_prefix` on `search_architecture_notes` (or rely on oversample+filter until applied)
- Optional: `DIGI_TENANT_CORPUS_MAP` on digigraph for defense in depth

## Dry-run log

| Date | Command | Result |
|------|---------|--------|
| 2026-08-10 | `DOCS_ONBOARD_DRY_RUN_CRAWL=1 … run_onboard.py --dry-run` | `pages_seen=32`, `docs_kept=30`, `skipped=2`; workdir had **8 HTML** + **22 PDFs**. Sinks skipped (`vault_notes=0`, `search_docs=0`). Full apply still **HOLD** pending crawl approval. |
