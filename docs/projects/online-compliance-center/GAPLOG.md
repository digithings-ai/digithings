# OCC client #1 — gap log

Compare-and-gap after wiring digithings.ai/chat/occ. Digi names lowercase.

## Corpus / ingest

| Gap | Status | Notes |
|-----|--------|-------|
| **sitaas crawl approval** | **Lifted by owner decision (2026-08-10)** | Owner (Chris Stefan, chrizefan) authorized the full apply directly in-session, on the basis that `help.online-compliance-center.com` is public documentation with no confidentiality restriction — **not** a written approval received from the OCC client. This is an owner override of the ingest hold, recorded honestly as such rather than represented as client sign-off. If OCC's own terms require separate client notice/approval for automated crawling, that is still outstanding and should be tracked separately. |
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

- Lift ingest hold after crawl approval; run one-shot onboard + `sync_onboard_vault.py` against the **Cloudflare Profile A stack** digisearch/vault (not Mac-only)
- ~~Operator env: add `occ.digithings.ai` to `DIGICHAT_EMBED_HOSTS` / `DIGICHAT_EMBED_TENANTS`~~ — verified on digichat Container (tenant-config returns `slug: occ`); digichat still forwards `X-Digi-Corpus-Index: occ_help` + vault prefix when tenant JSON includes them
- Cloudflare Pages deploy of digithings-web including `/chat/occ`
- Apply digivault Supabase migration for `path_prefix` on `search_architecture_notes` (or rely on oversample+filter / local vault seed until applied)
- ~~`DIGI_TENANT_CORPUS_MAP` on digigraph~~ — set in Profile A stack `wrangler.toml` `[vars]` + local bundle compose default
- Static `digithings_docs` + `occ_help` seeds ship in `frontend/digithings-stack-cloudflare/container/seed/`; oneshot `seed_chroma` ingests both into Chroma **before** digisearch starts (vault `seed-*.md` refreshed on every boot)
- **BLOCKER (2026-08-10):** `graph.digithings.ai` / `key.digithings.ai` custom domains are not live yet (routes commented in stack `wrangler.toml`; healthz unreachable). Do **not** retarget digichat Worker `DIGIGRAPH_INTERNAL_URL` / `DIGIKEY_URL` to those hosts (and never to Mac `*.trycloudflare.com` tunnels) until both healthz probes succeed. Until cutover, CF-hosted OCC RAG against the bundle index cannot be verified end-to-end.

## Dry-run log

| Date | Command | Result |
|------|---------|--------|
| 2026-08-10 | `DOCS_ONBOARD_DRY_RUN_CRAWL=1 … run_onboard.py --dry-run` | `pages_seen=32`, `docs_kept=30`, `skipped=2`; workdir had **8 HTML** + **22 PDFs**. Sinks skipped (`vault_notes=0`, `search_docs=0`). Full apply still **HOLD** pending crawl approval. |
| 2026-08-10 | Full apply, hold lifted by owner decision (see above) | Same crawl (`pages_seen=32`, `docs_kept=30`). Apply: **28 vault notes** written locally (2 fewer than `docs_kept`, no errors — not yet root-caused, likely a naming collision on write; worth checking if this recurs on re-run), **28 docs posted** to digisearch index `occ_help` (paced client-side under the ingest rate limit). Chroma `occ_help` confirmed at **629 chunks**. `sync_onboard_vault.py --apply` synced **28/28 notes** to production Supabase `architecture_notes` (verified via REST count). Production Profile A stack still ships the original 4 curated `occ_help` seed stubs — **not yet refreshed** with this corpus (see prod cutover section above). |
| 2026-08-11 | Content-aware chunking live run (#2153) | Re-ingested with PDF page segmentation. digisearch `occ_help`: **291 chunks / 28 sources / 28 doc_ids** (1:1), **89% carry `segment_label`, all of kind `page:`** — real per-page segmentation of the policy PDFs — mean 905 / median 664 chars, **max 2000, zero over the ceiling**. digivault: **328 per-segment notes + hubs** (was 28 flat notes); Supabase verified at **328** rows for `clients/online-compliance-center/`. Retrieval spot-check on a compliance-archive question returned `page:13`, `page:24`, `page:14` of `Admin Guide_Compliance Archiv_OCC_EN.pdf` — page-level citation, which was impossible before (pages were flattened into one string pre-#2153). |
| 2026-08-16 | Read-only crawl audit + direct production Supabase diff (no apply) | Confirmed crawl reaches 100% of the live site's pages and linked PDFs (24 linked, 22 real + 2 dead links traced to a stale `Updates & Wartung` changelog entry). **Correction to same-day earlier entry:** the initially-reported "33 vs 30, drift, re-run recommended" was an invalid comparison (crawl+static vs. crawl-only baseline); a direct URL-level diff against production's actual 328 rows / 28 `source_url`s shows **zero drift** for all crawl-derived content — production exactly matches the live site. **Real gap found instead:** the 3 static repo docs (`manual-docs.yaml`) are correctly configured and pipeline-ready but were never ingested — `static_sources:` was added to `onboard.yaml` (`727d41dc9`) on 2026-08-13, two days after the last apply (2026-08-11), so no apply has run since they existed. Fix: re-run the one-shot apply (no code/manifest change needed). Full detail: [`AUDIT-CORPUS-BILINGUAL.md`](AUDIT-CORPUS-BILINGUAL.md). |
| 2026-08-16 | Apply, `--skip-crawl` (static docs only), owner-authorized ("Yes, run it") | Closed the gap found earlier same day. Ran `run_onboard.py --skip-crawl` against throwaway Docker instances of digikey/digisearch sharing the **real** production named volumes (`digikey_data`, `digithings_digisearch_chroma`) — chosen specifically so this write lands in production, not a stub. Two infra bugs found and fixed en route (both are Docker/pipeline plumbing, not manifest or content issues): (1) `docker compose run --name` doesn't register the compose service-name network alias without `--use-aliases`, which broke digisearch→digikey JWKS resolution (401); (2) digisearch's `/ingest` reads the `source` path off its own container filesystem and validates it's under `DIGISEARCH_INGEST_ROOT` — fixed by bind-mounting the host scratch dir into the container at an identical path. Result: `docs_kept=3`, `vault_notes=117`, `search_docs=3`, `static_files=3`, zero errors. **Verified additive-only, two ways:** digisearch `occ_help` Chroma collection went **291→427 chunks, 28→31 doc_ids** (+136 chunks / +3 doc_ids, all 3 new doc_ids are exactly the 3 `repo://online-compliance-center/...` sources, checked via a read-only `chromadb.PersistentClient` count/get against the real persist path — not the stub `/indexes/{name}` endpoint, which only reflects the in-memory test backend). Supabase `architecture_notes` under `clients/online-compliance-center/` went **328→445 rows** (328 pre-existing crawl-derived rows confirmed untouched by direct REST count; +117 new rows all carry a `repo://` `source_url`), synced via `sync_onboard_vault.py` (dry-run checked first, then real). Bundle stack (`digichat-profile-a-bundle-digithings-stack-1`) was never touched; all temporary containers (`occ-onboard-digikey`, `occ-onboard-digisearch`, and the `digikey` service's `digi-digikey-blocklist-redis` dependency, none of which existed before this run) were stopped/removed afterward. **Residual, non-blocking:** the one-shot `digikey` API key issued for this run (scope `digisearch:ingest` only) is still valid in the `digikey_data` volume — no `DIGIKEY_ADMIN_TOKEN` is configured locally to call the `/v1/admin/keys/{id}/revoke` endpoint, so it wasn't revoked; narrow blast radius (ingest-only, cannot read data or issue keys). Corpus is now current per `AUDIT-CORPUS-BILINGUAL.md`'s net recommendation — no further apply needed until help-center content changes. |
