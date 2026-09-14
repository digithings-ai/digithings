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

Missing either variable fails the whole book run — the 2026-09-14 incident
(#4028) died with `ServiceAuthError: DIGIQUANT_DIGIKEY_API_KEY is not set`,
skipping portfolio and leaving no book (`book_materialized=false`).

## Required GitHub configuration

| Name | Kind | Value |
|------|------|-------|
| `DIGIKEY_URL` | Actions **variable** | Deployed digikey base URL. Optional — the workflow defaults to `https://key.digithings.ai` (see [ADR-0018](../adr/0018-digichat-path-routing.md)). Set it only for a staging/self-hosted digikey. |
| `DIGIQUANT_DIGIKEY_API_KEY` | Actions **secret** | digikey service API key (`dgk_live_...`) scoped `digisearch:query`, kind `standard`. |

Both are consumed at the `run` job level in `pipeline-digiquant.yml`, so every
step of the pipeline job (provider preflight, chain, artifact upload, outcome
report) sees them.

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
2. (Only if not using the default) Settings → Secrets and variables → Actions
   → **Variables** → name `DIGIKEY_URL`, value = the digikey base URL,
   e.g. `https://key.digithings.ai`.
3. Re-run the workflow (`gh workflow run "Pipeline: digiquant research"`) or
   wait for the next cron, and confirm the run no longer logs
   `DIGIQUANT_DIGIKEY_API_KEY is not set`.

Do **not** use `--kind dev_global` in production: `dev_global` keys carry
wildcard scopes and require `DIGIKEY_ALLOW_DEV_GLOBAL=1` (local development
only).

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
pipelines — `pipeline-digiquant-backfill.yml`, `pipeline-digiquant-prices.yml`,
`pipeline-research-metrics.yml` — never call `get_service_jwt()` and do not
need either variable.
