# CORE_POSTGRES_URI secret rename runbook (#3979)

Operator runbook for the shared production Postgres URI that the four pipeline
workflows read. The canonical name is the **repository secret `CORE_POSTGRES_URI`**.
The pre-#3860 names were `DIGI_CHECKPOINTER_POSTGRES_URI` (checkpointer,
archiver, db-migrate, pipeline) and `MARKET_DATA_POSTGRES_URI` (backfill /
refresh — **never created**, #3860). Both are retired; `CORE_POSTGRES_URI` is the
only name any consumer reads.

This replaces the earlier stub. It exists because the rename is a two-part job:
the **code/workflow side is landed**, and the **GitHub Settings side is a human
action** that cannot be done from a PR.

## 1. Exact GitHub Settings path

Web UI (repo admin required):

> `https://github.com/digithings-ai/digithings/settings/secrets/actions`
> → **Repository secrets** → `CORE_POSTGRES_URI`

Do **not** scope it to the `production` environment. `db-migrate` runs under
`environment: production`, and an environment secret of the same name
**overrides** the repository secret for that one job (GitHub resolves
environment secrets first). The other three workflows have no environment and
read the repository secret only. Setting it once at repo level makes all four
jobs agree.

Equivalent CLI (value never echoed):

```bash
gh secret set CORE_POSTGRES_URI --repo digithings-ai/digithings --body "<prod-postgres-uri>"
gh secret delete DIGI_CHECKPOINTER_POSTGRES_URI --repo digithings-ai/digithings   # legacy, when present
gh secret list --repo digithings-ai/digithings
gh secret list --repo digithings-ai/digithings --env production   # must NOT contain CORE_POSTGRES_URI
```

The DB URI carries a password, so it is only ever read from the secret: it is
never written into a workflow, an `.env.example`, or this doc.

## 2. What the four consumers read

Every consumer reads the single canonical name:

```yaml
${{ secrets.CORE_POSTGRES_URI }}
```

| Workflow (`name:`) | Job | Step that consumes it | Env var exposed | Missing/empty URI behaviour |
|---|---|---|---|---|
| `db-migrate.yml` (`db-migrate`) | `migrate` | `Apply pending migrations (atomic, ledger-gated)` | `DB_URI` | **Hard-fails**: `::error::CORE_POSTGRES_URI secret is empty` + `exit 1` (`db-migrate.yml:115`) |
| `pipeline-checkpoint-archive.yml` (`Pipeline: checkpoint archive`) | `archive` | `Archive checkpoint payloads older than 1 day` | `CORE_POSTGRES_URI` | **Fails closed**: `checkpoint_archive.main` prints `missing direct Postgres URI; set CORE_POSTGRES_URI` and returns `2` (`digiquant/src/digiquant/ops/checkpoint_archive.py:947-949`) |
| `pipeline-market-data-refresh.yml` (`market-data-refresh`) | `refresh` | `uv run … scripts/refresh_market_data_r2.py --manifest-out …` | `CORE_POSTGRES_URI` | **Fails closed**: `SystemExit: set --postgres-uri or $CORE_POSTGRES_URI (direct-PG only)` (`scripts/refresh_market_data_r2.py:1078-1079`) |
| `pipeline-digiquant.yml` (`Pipeline: digiquant research`) | `run` | `Run digiquant research pipeline` | `CORE_POSTGRES_URI` | **Silently degrades**: `_acquire_checkpointer()` catches the failure, logs `checkpointer unavailable (…); running without resume`, and runs the book **uncheckpointed** (`digiquant/src/digiquant/portfolio/chain.py:165-181`) |

The silent-degrade path in `pipeline-digiquant` is live because
`.github/digiquant-pipeline.yml:44` sets `DIGI_CHECKPOINTER: postgres`, and the
`Load pipeline configuration` step appends it to `$GITHUB_ENV`. So a missing URI
does not fail that job; the run simply cannot resume from the last completed
node (`--resume-run-id` becomes a no-op). That is the failure that is easiest to
miss and the reason this doc names the job log line to look for.

## 3. Code side already done vs Settings side

Do not re-file a code fix. The rename history is:

| Landed | PR | What it did |
|---|---|---|
| 2026-09-11 | #3860 | Renamed the workflow references to `secrets.CORE_POSTGRES_URI` (refs only; the repo secret was not renamed). |
| 2026-09-11 | #3989 (`task/3979`) | Mechanical code + workflow rename to `CORE_POSTGRES_URI`; tests updated first. Operator note at the time: create `CORE_POSTGRES_URI`, delete `DIGI_CHECKPOINTER_POSTGRES_URI` post-promotion. |
| 2026-09-13 | #3979 follow-up | Added a transitional `secrets.CORE_POSTGRES_URI \|\| secrets.DIGI_CHECKPOINTER_POSTGRES_URI \|\| secrets.MARKET_DATA_POSTGRES_URI` fallback because the repo secret had not yet been renamed. `db-migrate` still failed loudly if none was set. |
| 2026-09-17 | #4317 | Collapsed the dead alias fallbacks back to `secrets.CORE_POSTGRES_URI` — dead because the canonical secret exists and the legacy name was removed. |

**Remaining work is Settings-side only:** confirm `CORE_POSTGRES_URI` holds the
production URI, confirm the legacy name is absent, and run each workflow once to
prove it (§4). No repository file needs to change to complete #3979.

### Live state read (2026-09-18)

Read-only checks, values never printed:

```bash
$ gh secret list --repo digithings-ai/digithings | grep -E 'CORE_POSTGRES_URI|DIGI_CHECKPOINTER_POSTGRES_URI|MARKET_DATA_POSTGRES_URI'
CORE_POSTGRES_URI        2026-09-11T00:35:34Z

$ gh secret list --repo digithings-ai/digithings --env production
D1_DATABASE_MAP          2026-08-12T16:21:53Z
```

As of that read the canonical repository secret **exists** and neither legacy
name is present. If a fresh read disagrees (a reset repo, a new org, a
per-environment override), follow §1 and re-verify with §4 — the runbook is
written so either state lands correctly.

## 4. Verify success (exact job/step and expected output)

Trigger each workflow after the secret is in place. `db-migrate` and the
checkpoint archive are the two cheapest provers; both need the URI to be
non-empty to pass.

```bash
# Cheapest direct prover: the archiver returns 2 without the URI.
gh workflow run pipeline-checkpoint-archive.yml --repo digithings-ai/digithings
gh run watch --repo digithings-ai/digithings

# db-migrate (production environment approval required; no migrations pending is fine)
gh workflow run db-migrate.yml --repo digithings-ai/digithings
gh run watch --repo digithings-ai/digithings

# Market data refresh (direct-PG registry insert)
gh workflow run pipeline-market-data-refresh.yml --repo digithings-ai/digithings

# digiquant research (full run exercises the postgres checkpointer)
gh workflow run pipeline-digiquant.yml --repo digithings-ai/digithings
```

| Workflow | Proof of success |
|---|---|
| `checkpoint-archive` | Job `archive` succeeds (exit 0) and step `Archive checkpoint payloads older than 1 day` prints `archived …`; manifests artifact uploaded. If it instead prints `missing direct Postgres URI; set CORE_POSTGRES_URI`, the secret is absent/empty. |
| `db-migrate` | Job `migrate` succeeds; step prints `Done: applied N pending migration(s); skipped M already in the ledger.` An empty URI fails before this with `::error::CORE_POSTGRES_URI secret is empty`. |
| `market-data-refresh` | Job `refresh` succeeds; no `set --postgres-uri or $CORE_POSTGRES_URI` on stderr. |
| `pipeline-digiquant` | Job `run` succeeds **and** the run log does **not** contain `checkpointer unavailable` / `running without resume`. That warning is the silent-degrade tell; if present, the URI did not arrive. |

After all four pass, delete the retired `DIGI_CHECKPOINTER_POSTGRES_URI`
repository secret (if a fresh `gh secret list` still shows it) and close #3979.

## 5. Rollback

The rename is name-only; the value is unchanged. If a consumer regresses after
the switch, restore the previous name without touching values:

```bash
# Re-add the legacy name with the same production URI, so pre-#3979 readers work again.
gh secret set DIGI_CHECKPOINTER_POSTGRES_URI --repo digithings-ai/digithings --body "<prod-postgres-uri>"
```

That is a temporary bridge only: current code reads `CORE_POSTGRES_URI`, so leave
`CORE_POSTGRES_URI` in place and treat the legacy name as a second copy for any
older workflow ref. Do **not** roll back by reverting the #4317 alias collapse —
re-landing dead `||` fallbacks would hide a genuinely empty secret again. The
durable fix is always one canonical name.

## See also

- [`docs/ops/SECRETS_INVENTORY.md`](SECRETS_INVENTORY.md) — evidence base, risk ids, `CORE_POSTGRES_URI` row.
- [`docs/ops/SECRETS_ROTATION.md`](SECRETS_ROTATION.md) — rotation procedure for the value.
- `digigraph/ARCHITECTURE.md` and `digiquant/src/digiquant/portfolio/chain.py` — what the URI controls (LangGraph `PostgresSaver` / resume).
