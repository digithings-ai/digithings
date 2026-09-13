# CORE_POSTGRES_URI secret rename (#3979)

The shared production Postgres URI for the pipeline workflows is the
`CORE_POSTGRES_URI` repository secret. #3860 renamed the workflow references
(and the env var the application reads) from the legacy names, but the GitHub
Actions secret in repo Settings was never renamed — so those jobs can read an
empty value. `db-migrate` hard-fails on an empty URI; the other pipelines
degrade.

## Operator action (required)

1. Settings → Secrets and variables → Actions → **New repository secret**.
2. Name `CORE_POSTGRES_URI`; value = the production Postgres URI currently
   stored under `DIGI_CHECKPOINTER_POSTGRES_URI`.
3. Confirm one run of each workflow below, then delete the legacy secret.

`MARKET_DATA_POSTGRES_URI` was never created (#3860), so only
`DIGI_CHECKPOINTER_POSTGRES_URI` is expected to exist.

## Transitional fallback

Until the secret is renamed, every consumer accepts the new name or either
legacy name:

```yaml
${{ secrets.CORE_POSTGRES_URI || secrets.DIGI_CHECKPOINTER_POSTGRES_URI || secrets.MARKET_DATA_POSTGRES_URI }}
```

| Workflow | Env var exposed to the job |
|----------|----------------------------|
| `db-migrate.yml` | `DB_URI` (read by the shell) |
| `pipeline-checkpoint-archive.yml` | `CORE_POSTGRES_URI` |
| `pipeline-digiquant.yml` | `CORE_POSTGRES_URI` |
| `pipeline-market-data-refresh.yml` | `CORE_POSTGRES_URI` |

The fallback is **transitional (#3979)** — remove it once the repo secret is
renamed. `db-migrate` keeps hard-failing when none of the three names resolves
to a value. Application code reads only `CORE_POSTGRES_URI` and is unaffected.
