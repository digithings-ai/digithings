# Online Compliance Center — client #1

**Target (not live until Pages deploy + crawl apply):** ungated OCC help assistant at
`https://digithings.ai/chat/occ` — same digichat + Profile A stack as digithings
dogfood (client #0), grounded on the OCC help-center corpus only. Code for the
route and corpus routing is on `develop`; production URL is 404 until cutover.
Full ingest remains **HOLD** (dry-run only — see GAPLOG).

Digi product names are always lowercase in prose.

## Locked decisions

| Topic | Decision |
|---|---|
| Chat UI | **digithings.ai/chat/occ** — no separate OCC chat hostname |
| Embed virtual host | `occ.digithings.ai` (registry key only; no DNS required) |
| Tenant slug | `occ` (digichat / digikey); manifest `client: online-compliance-center` |
| Crawl host | `help.online-compliance-center.com` only (no demo/portal) |
| Sinks | Dual-sink: digivault + digisearch |
| digisearch index | `occ_help` |
| Vault / Supabase | Same `architecture_notes` table; path prefix `clients/online-compliance-center/…` |
| Auth | Ungated embed; operator may set `llmAccess: free_then_byok` (on develop via #2048) |
| digiproject | `llm_mode: free`; research prompt for OCC help corpus |
| Corpus cadence | **One-shot** for the demo — static until content changes; no crawl CI |

Plan: [`docs/superpowers/plans/2026-08-10-occ-client-chat.md`](../../superpowers/plans/2026-08-10-occ-client-chat.md).

## Supabase storage choice

**Same table + path prefix** (not a new table). digithings dogfood uses
`public.architecture_notes` with paths under `clients/digithings/…`. OCC rows use
`clients/online-compliance-center/…`. digivault FTS accepts optional `path_prefix`
so OCC chat does not surface digithings notes.

## Tree

```text
docs/projects/online-compliance-center/
  README.md
  SCOPE.md
  GAPLOG.md
  digiproject.yaml
  onboard.yaml
  indexes/
    occ_help.yaml
```

## Routing

```text
digithings.ai/chat      → embed host digithings.ai     → tenant digithings → digithings_docs
digithings.ai/chat/occ  → embed host occ.digithings.ai → tenant occ       → occ_help
```

## Embed (operator env)

```bash
DIGICHAT_REQUIRE_ROOT_AUTH=0
DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai,occ.digithings.ai
DIGICHAT_EMBED_TENANTS='{"digithings.ai":{"slug":"digithings","aliases":["www.digithings.ai"],"gateMode":"ungated","showByok":true,"showStatusBar":true,"layout":"page","activityDetail":"full","attribution":false,"token":"<schema-required>","backend":{"type":"digigraph"}},"occ.digithings.ai":{"slug":"occ","gateMode":"ungated","showByok":true,"showStatusBar":true,"layout":"page","activityDetail":"full","title":"OCC help assistant","welcome":"Ask about Online Compliance Center policies, procedures, and help articles.","attribution":false,"token":"<schema-required>","backend":{"type":"digigraph","digisearchIndex":"occ_help","vaultPathPrefix":"clients/online-compliance-center"}}}'
```

Optional digigraph fallback map (when headers are absent):

```bash
DIGI_TENANT_CORPUS_MAP='{"occ":{"digisearchIndex":"occ_help","vaultPathPrefix":"clients/online-compliance-center"},"digithings":{"digisearchIndex":"digithings_docs","vaultPathPrefix":"clients/digithings"}}'
```

## digigraph project config

Committed snippet for OCC research prompt / free tier:

```bash
export DIGI_PROJECT_CONFIG=docs/projects/online-compliance-center/digiproject.yaml
# or keep digithings digiproject and rely on DIGI_TENANT_CORPUS_MAP + corpus headers
```

For a **shared** digigraph process serving both `/chat` and `/chat/occ`, keep the
digithings digiproject (or any default) and rely on per-request corpus headers /
`DIGI_TENANT_CORPUS_MAP` for index + vault prefix. Use the OCC digiproject when
running an OCC-only demo stack.

## One-shot onboard (operator)

**Ingest hold:** `onboard.yaml` still carries the legal crawl hold until sitaas
written approval. For local/demo only, dry-run is always safe; full apply requires
lifting the hold (see `GAPLOG.md`).

Dry-run (no sinks; skip live crawl by default):

```bash
source .venv/bin/activate
python scripts/docs_onboard/run_onboard.py \
  --manifest docs/projects/online-compliance-center/onboard.yaml \
  --workdir /tmp/occ-onboard \
  --dry-run
```

Apply (after crawl approval + secrets + digivault/digisearch):

```bash
export DIGIVAULT_URL="${DIGIVAULT_URL:-http://127.0.0.1:8004}"
export DIGISEARCH_URL="${DIGISEARCH_URL:-http://127.0.0.1:8002}"
export DIGIKEY_URL="${DIGIKEY_URL:-http://127.0.0.1:8005}"

python scripts/docs_onboard/run_onboard.py \
  --manifest docs/projects/online-compliance-center/onboard.yaml \
  --workdir /tmp/occ-onboard \
  --digivault-url "$DIGIVAULT_URL" \
  --sinks vault,search \
  --api-key "$DIGISEARCH_SEED_API_KEY"

python scripts/sync_onboard_vault.py \
  --vault /tmp/occ-onboard-vault \
  --dry-run   # then drop --dry-run with CORE_SUPABASE_* set
```

Re-run only when help-center content changes. Corpus stays static for the demo.

## Local chat smoke

```bash
# digichat with OCC tenant in DIGICHAT_EMBED_TENANTS (see above)
open "http://127.0.0.1:3000/embed?host=occ.digithings.ai&layout=page"
# or digithings-web Pages shell:
# NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=http://127.0.0.1:3000 → /chat/occ
```

## Related

- Scope: [`SCOPE.md`](SCOPE.md)
- Gap log: [`GAPLOG.md`](GAPLOG.md)
- Corpus audit (crawl completeness + EN/DE bilingual coverage): [`AUDIT-CORPUS-BILINGUAL.md`](AUDIT-CORPUS-BILINGUAL.md)
- Runbook: [`docs/digichat/CLIENT-DOCS-ONBOARD.md`](../../digichat/CLIENT-DOCS-ONBOARD.md)
- Dogfood pattern: [`docs/projects/digithings/README.md`](../digithings/README.md)
