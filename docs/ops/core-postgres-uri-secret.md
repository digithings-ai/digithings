# CORE_POSTGRES_URI secret rename (#3979)

The shared production Postgres URI for the pipeline workflows is the
`CORE_POSTGRES_URI` repository secret. #3860 renamed the workflow references
(and the env var the application reads) from the legacy names; `CORE_POSTGRES_URI`
is now the only name any consumer reads. `db-migrate` hard-fails on an empty URI;
the other pipelines degrade.

## Operator action (required)

1. Settings → Secrets and variables → Actions — confirm the repository secret
   `CORE_POSTGRES_URI` holds the production Postgres URI.
2. Confirm one run of each workflow below, then delete the retired
   `DIGI_CHECKPOINTER_POSTGRES_URI` secret (`MARKET_DATA_POSTGRES_URI` was never
   created — #3860).

## Consumer reference

Every consumer reads the single canonical name:

```yaml
${{ secrets.CORE_POSTGRES_URI }}
```

| Workflow | Env var exposed to the job |
|----------|----------------------------|
| `db-migrate.yml` | `DB_URI` (read by the shell) |
| `pipeline-checkpoint-archive.yml` | `CORE_POSTGRES_URI` |
| `pipeline-digiquant.yml` | `CORE_POSTGRES_URI` |
| `pipeline-market-data-refresh.yml` | `CORE_POSTGRES_URI` |

`db-migrate` keeps hard-failing when `CORE_POSTGRES_URI` is empty. Application
code reads only `CORE_POSTGRES_URI` and is unaffected.
