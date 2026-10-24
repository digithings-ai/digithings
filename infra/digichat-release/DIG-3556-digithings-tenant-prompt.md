# DIG-3556 — digithings tenant prompt (STAGED, not applied)

Status: STAGED for Chris's approval. NOT applied to production.
The digichat Worker binds a Workers KV namespace as `DIGICHAT_TENANTS_KV`
(`apps/digichat-cloudflare/wrangler.toml`) and keeps the tenant registry copy
under the KV key `embed-tenants`, next to the `DIGICHAT_EMBED_TENANTS` Worker
secret; digigraph uses the `DIGI_TENANT_CORPUS_MAP` env. The staged values
below are applied by the compose, which writes the KV key, then the Worker
secret, then recycles the container. Ticket brief saying "KV" is recorded as
superseded by this measurement.

## Prompt (mirrored into `researchSystemPrompt` for slug `digithings`)

You are the digithings help assistant for digithings.ai chat. Answer questions about digithings: the products, the docs, and how the stack fits together. Use the docs and vault notes you retrieve, and cite the path or URL. Web search is on. Use it when the corpus does not cover the question, and say when an answer comes from the web. Do not invent features, pricing, or capabilities. If you do not have a grounded answer, say so. Politely decline questions that are not about digithings.

## Retrieval scope

- digisearch index: `digithings_docs`
- digivault prefix: `clients/digithings/`
- Sources to index: `docs/`, API docs (`docs/openapi/`, `docs/api/`), openwiki,
  digibook, repo code.
- Re-index triggers: merges to `develop` and `main` (scheduled workflow; DevOps
  Lead owns the production backfill per seat rules — this PR stages config only).
- Web search: on, matching live digithings.ai (`gate.webSearch: true`).

## Apply (Chris only, after PR review)

The staged file is an **overlay**, not the registry. It carries no tenant token
and no MCP rows. The registry is composed at apply time from the host secret
store, so a tenant can never be dropped by applying a repository file.

1. `DIGI_TENANT_CORPUS_MAP`: merge the `digithings.researchSystemPrompt` value from
   `DIG-3556-staged-prod-tenant-config.json` into the digigraph env/secret.
2. `DIGICHAT_EMBED_TENANTS`: compose the overlay onto the live registry, write
   the result to the digichat Worker, and recycle the container so it reads the
   new registry at boot:

   ```sh
   python3 scripts/digichat_tenant_registry.py apply \
     --live-from ~/.config/digithings/secrets/digichat-embed-tenants.deploy.json \
     --overlay infra/digichat-release/DIG-3556-staged-prod-tenant-config.json
   ```

   Run the same command with `compose` instead of `apply` first: it prints the
   plan, the tenants, and the changed paths, and it writes nothing.
3. Run/approve the backfill that indexes the five sources above, then verify the
   ~10 in-scope / ~5 out-of-scope acceptance transcripts.

The same short prompt is in the local compose override, `wrangler.toml`, and the
`index.ts` fallback. `tests/scripts/test_check_tenant_corpus_map.py` pins all three
to agree. Applying the staged overlay to live KV is still a human step: this
change does not call the registry apply.
