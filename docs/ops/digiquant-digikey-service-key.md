# digiquant pipeline digikey service key (#4028)

The daily `Pipeline: digiquant research` job (`.github/workflows/pipeline-digiquant.yml`)
runs web grounding, which is **default-ON since #3870**: for `live_search`
segments, `digiquant/src/digiquant/research/data/web_grounding.py`
`_pipeline_bearer()` mints a digikey service JWT via
`digibase.service_auth.get_service_jwt()`:

- reads the raw key from `DIGIQUANT_DIGIKEY_API_KEY` (env)
- reads the digikey base URL from `DIGIKEY_URL` (env)
- exchanges them at `POST {DIGIKEY_URL}/v1/oauth/token` with
  `grant_type=api_key` and `requested_scopes=["digisearch:query"]`
- caches the short-lived JWT in-process (no persistence)
- sends the tool call to `{DIGISEARCH_URL}/v1/orchestrator_invoke` (digigraph's
  `web_search` tool → `tool_common._digisearch_service_base()`, which fails loud
  when the URL is unset)

Missing configuration fails the whole book run — the 2026-09-14 incident
(#4028) died with `ServiceAuthError: DIGIQUANT_DIGIKEY_API_KEY is not set`,
skipping portfolio and leaving no book (`book_materialized=false`); an unset
`DIGISEARCH_URL` raises instead of answering ungrounded.

`DIGISEARCH_URL` must point at a reachable digisearch. On GitHub Actions that is
the hosted route `https://search.digithings.ai` (default), declared as a
custom-domain `[[routes]]` entry in
`cloudflare/digithings-stack-cloudflare/wrangler.toml` (#4063 — new external
route, owner-approved). `http://digisearch:8002` is compose-only and does not
resolve from CI. The route is not anonymous: digisearch's `DigiAuthMiddleware`
requires the `digisearch:query` JWT for `POST /v1/orchestrator_invoke`. The
auth-exempt set is the shared service allowlist — `/health`, `/healthz`,
`/metrics`, `/docs`, `/redoc`, `/openapi.json`, plus OPTIONS preflights (CORS
enforced separately) — and, host-agnostically at the Worker edge, `/_stack/meta`,
`/v1/market/tickers|closes`, and `/_stack/key/*` (proxied to digikey).

## Required GitHub configuration

| Name | Kind | Value |
|------|------|-------|
| `DIGIKEY_URL` | Actions **variable** | Deployed digikey base URL. Optional — the workflow defaults to `https://key.digithings.ai` (see [ADR-0018](../adr/0018-digichat-path-routing.md)). Set it only for a staging/self-hosted digikey. |
| `DIGISEARCH_URL` | Actions **variable** | Hosted digisearch base URL. Optional — the workflow defaults to `https://search.digithings.ai` (stack Worker route, #4063). Set it only for a staging/self-hosted digisearch. |
| `DIGIQUANT_DIGIKEY_API_KEY` | Actions **secret** | digikey service API key (`dgk_live_...`) scoped `digisearch:query`, kind `standard`. |

All three are consumed at the `run` job level in `pipeline-digiquant.yml`, so
every step of the pipeline job (provider preflight, chain, artifact upload,
outcome report) sees them.

## Operator action — mint the key

Run against the **deployed digikey database** (the same `DIGIKEY_DATABASE_URL`
used by the digikey service). The CLI prints the raw key exactly once:

```bash
export DIGIKEY_DATABASE_URL="<deployed digikey database URL>"
python -m digikey.cli issue-key \
  --tenant default \
  --label digiquant-pipeline-web-grounding \
  --scopes digisearch:query \
  --kind standard
```

Then:

1. Settings → Secrets and variables → Actions → **New repository secret**
   → name `DIGIQUANT_DIGIKEY_API_KEY`, value = the printed `dgk_live_...` key.
2. (Only if not using the defaults) Settings → Secrets and variables → Actions
   → **Variables** → `DIGIKEY_URL` (digikey base, default
   `https://key.digithings.ai`) and/or `DIGISEARCH_URL` (digisearch base,
   default `https://search.digithings.ai`).
3. Re-run the workflow (`gh workflow run "Pipeline: digiquant research"`) or
   wait for the next cron, and confirm the run no longer logs
   `DIGIQUANT_DIGIKEY_API_KEY is not set`.

Do **not** use `--kind dev_global` in production: `dev_global` keys carry
wildcard scopes and require `DIGIKEY_ALLOW_DEV_GLOBAL=1` (local development
only).

## The key store must be durable (#4080)

The mint above writes into whatever `DIGIKEY_DATABASE_URL` the deployed digikey
is using. When that is the SQLite fallback, the key lives on the Cloudflare
Container's ephemeral `/data` disk: a deploy that replaces the instance wipes it,
and the next run 401s at `/v1/oauth/token` (`ServiceAuthError: digikey exchange
failed`) even though the secret is unchanged and freshly minted keys still work.
That was 2026-09-15 (run 34999170506) — the key was fine, its storage was not.

Point digikey at durable Postgres (see the
[stack README](../../cloudflare/digithings-stack-cloudflare/README.md)), then
**re-mint in the same change**: switching databases does not migrate keys out of
the old SQLite store, so the previous secret stops resolving. digikey logs a
startup warning while the store is SQLite; `DIGIKEY_REQUIRE_DURABLE_DB=1` turns
that warning into a fail-closed startup error.

## Rotation

1. Mint a new key with the same command and label (e.g. suffix the label with
   the date).
2. Update the `DIGIQUANT_DIGIKEY_API_KEY` secret to the new value.
3. Revoke the old key through the digikey admin/DB path used for key
   management; confirm the next run is green.
4. `digibase.service_auth.clear_service_jwt_cache()` clears the process-local
   token cache — not needed on GitHub Actions (fresh process per run), only
   relevant if a long-lived process is rotating mid-flight.

## Scope

Only `pipeline-digiquant.yml` runs the grounding code path (the research graph
and beliefs distillation inside `digiquant.portfolio.chain`). The deterministic
pipelines — `pipeline-digiquant-prices.yml`,
`pipeline-research-metrics.yml` — never call `get_service_jwt()` and do not
need these variables.
