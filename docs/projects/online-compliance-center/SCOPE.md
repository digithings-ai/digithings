# Online Compliance Center — docs_onboard scoping

Condensed research for the offline [`docs_onboard`](../../digichat/CLIENT-DOCS-ONBOARD.md) pipeline. **Do not run live ingest** until digithings dogfood sign-off and explicit client crawl approval (see manifest comment).

## Executive verdict

**Go with gaps.** The public help center is a small, server-rendered Joomla site suitable for a first vault + digisearch corpus. Gaps (YouTube e-learning, accordion HTML quality, rate limits, classification tuning, broken sitemap) are acceptable for a dry-run and operator review before production ingest.

## Hosts

| Host | Role | v1 |
|------|------|-----|
| `help.online-compliance-center.com` | Primary crawl — Joomla help center | **In scope** |
| `demo.online-compliance-center.com` | React SPA mock / product demo | Out of scope |
| `portal.online-compliance-center.com` | Authenticated customer portal | Out of scope |

Marketing / corporate site inclusion is an **open question** (see below).

## Information architecture (help center)

- **CMS:** Joomla, server-rendered HTML (no client-side router on help).
- **Routes:** Many pages use `/index.php` path prefixes (allowlist in manifest).
- **Content types:** FAQ pages with accordion UI (~42 accordions), direct PDF links, sparse static HTML paths.
- **Out of scope on help:** Embedded YouTube e-learning (~14 videos) — not ingested as page bodies in v1.

## Volume (reconnaissance)

| Asset | Approx. count |
|-------|----------------|
| Distinct HTML paths | ~10 |
| Direct PDFs | ~24 |
| FAQ accordions | ~42 |
| YouTube (e-learning) | ~14 (out of scope v1) |

Sample PDFs inspected carry **text layers**; digisearch OCR remains a fallback (`DIGISEARCH_OCR_ENABLED`), not the default path.

## Sinks and index

- **Sinks:** `vault` + `search` (Profile A grounding: digivault notes + digisearch index).
- **Proposed digisearch index name:** `occ_help` (confirm with sitaas / tenant naming).
- **Vault layout:** `clients/online-compliance-center` under `DIGIVAULT_ROOT`.

## Manifest strategy

- **Seed:** `https://help.online-compliance-center.com/`
- **allowed_hosts:** help host only (no demo, portal, or YouTube domains).
- **docs_path_prefixes:** Joomla `/index.php` doc routes (see `onboard.yaml`).
- **skip_path_prefixes:** kontakt, admin, api, and other non-doc Joomla surfaces.

Draft manifest: [`onboard.yaml`](./onboard.yaml).

## Known gaps (pipeline / content)

1. **YouTube e-learning** — linked from help but not crawlable as stable HTML; needs a separate policy (exclude v1).
2. **Accordion markdown quality** — FAQ content may need post-process or manual curation for clean vault notes.
3. **Rate limiting** — not wired in `scrape_site`; polite delays / caps should be verified before production crawl.
4. **Classification** — `docs_path_prefixes` may need tuning after a dry-run sitemap/link graph.
5. **Sitemap** — help sitemap returned **HTTP 500** during recon; rely on BFS from seed + known PDF URLs until fixed.

## Dry-run plan (no production ingest)

1. Load manifest; run `scrape_site` only into a disposable workdir; confirm page count and hosts stay on help.
2. Run `classify_pages` + `fetch_docs`; inspect accordion HTML and PDF text extraction.
3. Optionally `write_vault_notes` to a temp `DIGIVAULT_ROOT`; spot-check note titles and source URLs.
4. **Defer** `write_search_index` / `run_onboard.py` full ingest until dogfood sign-off and client approval.
5. File follow-up tasks for gaps (rate limit, classification, sitemap, e-learning policy).

## Open questions (human / sitaas)

| # | Question |
|---|----------|
| 1 | **Crawl permission** — written approval to index `help.online-compliance-center.com`? |
| 2 | **Tenant / index name** — is `occ_help` correct for digisearch + digikey scoping? |
| 3 | **E-learning** — exclude YouTube only, or ingest transcripts/metadata later? |
| 4 | **Battlecards** — OK to include internal/sales battlecard PDFs if linked from help? |
| 5 | **Refresh cadence** — one-shot onboard vs scheduled re-crawl? |
| 6 | **Marketing site** — include `online-compliance-center.com` (non-help) in a later phase? |

## References

- Operator runbook: [`docs/digichat/CLIENT-DOCS-ONBOARD.md`](../../digichat/CLIENT-DOCS-ONBOARD.md)
- Example manifest shape: [`docs/projects/example-docs-client/onboard.yaml`](../example-docs-client/onboard.yaml)
