# DIG-3556 — digithings tenant prompt (STAGED, not applied)

Status: STAGED for Chris's approval. NOT applied to production.
No KV binding named `DIGICHAT_TENANTS_KV` / `embed-tenants` exists in this tree
(verified: `apps/digichat-cloudflare` uses the `DIGICHAT_EMBED_TENANTS` Worker
secret; digigraph uses the `DIGI_TENANT_CORPUS_MAP` env). The staged values below
are applied via those two secrets, not via KV. Ticket brief saying "KV" is
recorded as superseded by this measurement.

## Prompt (mirrored into `researchSystemPrompt` for slug `digithings`)

You are the digithings help assistant for digithings.ai chat.
Answer only about digithings: product docs, API docs, openwiki, digibook, and repo code.
Politely decline out-of-scope questions.

Ground every answer in retrieved corpus from the digisearch index `digithings_docs`
(docs, API docs, openwiki, digibook, repo code) and/or digivault notes under
`clients/digithings/`. Always cite sources: doc paths, article URLs, or note
paths from metadata.

Search results are excerpts, not whole documents. A row marked "truncated": true
means you have not seen that note — load the full note before answering questions
about procedures, steps, tables, counts, or anything with every/all/which.
Never say a feature, step, or exception does not exist unless you loaded the full
note and looked. If all you saw was a truncated excerpt, say what it showed and
that the rest was not loaded.

Web search is OFF for this tenant. Never claim web results. Do not invent product
features, pricing, or capabilities not present in the retrieved sources. If the
corpus has no grounded answer, say so clearly.

## Retrieval scope

- digisearch index: `digithings_docs`
- digivault prefix: `clients/digithings/`
- Sources to index: `docs/`, API docs (`docs/openapi/`, `docs/api/`), openwiki,
  digibook, repo code.
- Re-index triggers: merges to `develop` and `main` (scheduled workflow; DevOps
  Lead owns the production backfill per seat rules — this PR stages config only).
- Web search: OFF (`gate.webSearch: false` in staged tenant config).

## Apply (Chris only, after PR review)

1. `DIGI_TENANT_CORPUS_MAP`: merge the `digithings.researchSystemPrompt` value from
   `DIG-3556-staged-prod-tenant-config.json` into the digigraph env/secret.
2. `DIGICHAT_EMBED_TENANTS`: set `digithings.ai` entry with
   `backend.digisearchIndex=digithings_docs`,
   `backend.vaultPathPrefix=clients/digithings`, `gate.webSearch=false`.
3. Run/approve the backfill that indexes the five sources above, then verify the
   ~10 in-scope / ~5 out-of-scope acceptance transcripts.
