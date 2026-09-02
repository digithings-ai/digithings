# Atlas — Deployment & Scheduling

This document covers the GitHub Actions scheduler that drives the Olympus daily pipeline,
the secrets it needs, how to test locally, and rollback / monitoring procedures.

Companion workflows (in `.github/workflows/`):

A single workflow, `pipeline-digiquant.yml`, drives all scheduled research + portfolio runs. The
`resolve` job sets `refresh_scope` (Sunday → `all`, weekdays → `none`); the `run` job
executes the unified Atlas+Hermes pipeline via
`python -m digiquant.portfolio.chain --cadence daily`.

| Workflow | Trigger | `refresh_scope` | Timeout |
| --- | --- | --- | --- |
| `pipeline-digiquant.yml` | `cron '17 9/10/11/12 * * *'` (off-peak UTC retries) | Sunday → `all`; else `none` | 240 min |
| `pipeline-digiquant.yml` | `repository_dispatch` `olympus-daily` | same as schedule | 240 min |
| `pipeline-digiquant.yml` | `workflow_dispatch` | `none` \| `all` \| `segments` \| `hermes` \| `digest` \| `beliefs` | 240 min |
| Kairos cron check (spec) | `cron '15 12 * * *'` — copy `docs/agent-backlog/kairos-tenancy/execution-cron-check.workflow.yml` onto a `chore/`/`feat/` branch; never `--execute`/`--all`/`hermes.chain` | n/a (probe) | 10 min |
| `test-research-graph.yml` | `push` / `pull_request` touching `digiquant/src/digiquant/olympus/{atlas,hermes}/**`, `tests/dq/{atlas,hermes}/**`, or `pipeline-digiquant.yml` | unit tests + ruff | 15 min |
| `ci.yml` → `actionlint` job | `push` / `pull_request` touching `.github/workflows/**` | `actionlint` over **every** workflow | 5 min |

**Removed (historical):** separate `atlas-baseline.yml` / `atlas-delta.yml` /
`atlas-monthly.yml` and `run_type=baseline|delta|monthly` cron semantics — superseded by
one daily graph ([#930](https://github.com/digithings-ai/digithings/issues/930)).

Non-secret tunables (OpenRouter routing, analyst cap, feature flags,
checkpointer, tracing) live in `.github/digiquant-pipeline.yml` and are loaded
into `$GITHUB_ENV` by the "Load pipeline configuration" step.

## Olympus environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLYMPUS_MODEL_TIER` | `cheap` | Routes LLM nodes via `config/digiquant_models.yaml` (`cheap` \| `balanced` \| `quality`) — cost lever, alongside edit-mode (see [Cost monitoring](#cost-monitoring)) |
| `OLYMPUS_STALE_FULL_DAYS` | `7` | Prior gap > N calendar days → `full` rewrite instead of `edit` |
| `OLYMPUS_BELIEFS_BACKLOG` | `20` | Additional trigger for a **full** beliefs rewrite when unfolded `decision_log` rows exceed the threshold. House runs already publish a **daily short fold**. |
| `ATLAS_MAX_ANALYSTS` | `30` (`.github/digiquant-pipeline.yml`) | Caps H4/H5/H6 fan-out width — enforced for the first time by #1767. Held tickers always survive (#936) and are the only sanctioned overshoot; thesis vehicles are prioritised *within* the cap, not exempt from it. `0` = uncapped |

Operator full refresh: `workflow_dispatch` with `refresh_scope=all` or CLI
`--refresh-scope all` — not a separate graph or cron.

## Required repo secrets

Set once per repository — the schedulers reference them by name. Prefer
GitHub **environment** secrets (`environment: atlas-prod`) when you're
ready to gate production runs behind a reviewer.

**Always pipe secret values via stdin** (`--body-file -`) — `--body "<value>"`
leaks the raw secret into your shell history, process list, and any
terminal recording.

```bash
# URLs are non-secret but use the same convention for consistency.
printf 'https://<project>.supabase.co' | gh secret set SUPABASE_URL --body-file -

# Paste the service-role JWT when prompted, then Ctrl-D:
gh secret set SUPABASE_SERVICE_ROLE_KEY --body-file -   # server-side only, never ship to frontend
gh secret set LITELLM_PROXY_API_KEY     --body-file -   # LiteLLM proxy bearer
gh secret set OPENAI_API_KEY            --body-file -   # BYOK fallback / override
```

If you already have the value in a file (for example, a 1Password export),
pass the path directly: `gh secret set OPENAI_API_KEY --body-file ~/openai.key`.
Delete the file immediately after.

Verify:

```bash
gh secret list | grep -E 'SUPABASE|LITELLM|OPENAI'
```

Rotation: re-run `gh secret set <NAME> --body-file -` with a new value;
in-flight runs keep their copy, new runs pick up the rotated secret.

## Bootstrap (first-run)

On a fresh Supabase project, the first daily run uses `full` mode for all artifacts
(no prior materialized rows). Trigger manually:

```bash
gh workflow run pipeline-digiquant.yml \
  -f refresh_scope=all \
  -f run_date="$(date -u +%Y-%m-%d)"
gh run watch --exit-status
```

Verify research landed:

```bash
python3 digiquant/scripts/research/fetch_research_library.py \
  --category digest --limit 1
```

Subsequent weekday cron ticks use `refresh_scope=none` and edit-mode continuity.

## Testing a workflow

### Manual `workflow_dispatch` (recommended for first-time validation)

Dry-run (compiles the graph, prints a JSON summary, no LLM calls / no writes):

```bash
gh workflow run pipeline-digiquant.yml \
  -f refresh_scope=none \
  -f run_date=2026-04-20 \
  -f dry_run=true
```

Watch the run:

```bash
gh run watch --exit-status
```

Operator full-refresh dry-run:

```bash
gh workflow run pipeline-digiquant.yml \
  -f refresh_scope=all \
  -f run_date=2026-04-20 \
  -f dry_run=true
```

Beliefs-only run:

```bash
gh workflow run pipeline-digiquant.yml \
  -f refresh_scope=beliefs \
  -f run_date=2026-04-20
```

### `act` (fully local, optional)

```bash
brew install act
act -W .github/workflows/pipeline-digiquant.yml \
    -j run \
    --secret-file .secrets \
    -e <(echo '{"inputs":{"refresh_scope":"none","run_date":"2026-04-20","dry_run":"true"}}')
```

`act` is best-effort — treat as a fast pre-check, not a substitute for real `workflow_dispatch`.

### `actionlint` (static check, pre-push)

```bash
brew install actionlint shellcheck
actionlint                                    # every workflow, repo-wide
actionlint .github/workflows/pipeline-digiquant.yml   # just this one
```

Bare `actionlint` is the form CI runs and the one to trust before pushing — it
picks up `.github/actionlint.yaml` (the suppression rules) automatically, so a
local run and the `actionlint` job in `ci.yml` agree. Install `shellcheck` too:
without it actionlint silently skips the `run:` block checks, which is where
most real findings come from. CI pins both (actionlint `1.7.12`, shellcheck
`0.11.0`), and `brew` currently matches — see
[CI_CONVENTIONS.md](../../../../../../docs/agents/CI_CONVENTIONS.md) for why the
shellcheck version in particular is part of the gate's contract.

CI runs it on every PR touching `.github/workflows/**`, via the `actionlint` job
in `ci.yml` (gated by the `workflows` filter in `scripts/ci_paths.yaml`). It used
to live in `test-research-graph.yml` pinned to `pipeline-digiquant.yml` alone; that
job is gone, since it left every other workflow unlinted and was itself skipped
on workflow-only PRs.

## Rollback plan

A run can fail in two shapes:

1. **Crashed fast** (import error, schema mismatch, missing secret). No
   partial writes. Remediation: re-run the workflow once the fix is
   merged, or revert the offending commit and let the next cron tick.
2. **Crashed mid-pipeline** (half-written `documents`, a stray
   `daily_snapshots` row). Atlas/Hermes writes are idempotent per `(date,
   document_key)` / `source_run_id` — re-running the same `run_date` will
   overwrite partial rows. If rollback is still required:

   ```bash
   python3 digiquant/scripts/research/validate_db_first.py \
     --date <run-date> --mode full
   ```

   To purge a bad run:

   ```sql
   DELETE FROM daily_snapshots WHERE date = '<run-date>';
   DELETE FROM documents       WHERE date = '<run-date>' AND created_at > '<run-started-at>';
   ```

   Then re-trigger via `workflow_dispatch` with the original `run_date`.

3. **Scheduler is the problem** (bad cron, runaway cost): disable the
   workflow from the Actions UI or `gh workflow disable pipeline-digiquant.yml`.

## Failure issue convention

The pipeline opens (or comments on) a single rolling issue titled
`olympus-<kind>-failure`, with the failing run's date, run URL, and last 200 log lines.

## Cost monitoring

Per-run token counts land in `atlas_run_diagnostics` via `digiquant.research.diagnostics`
(LLM usage snapshot from `digigraph.usage`). Target **≤20 LLM calls** on a quiet day
(re-baselined after thesis-first H1–H9 wiring).

Flag runs where call count exceeds the rolling 4-week median by more than 3x — usually
a triage miss (everything `full` instead of `skip`/`edit`) or a cache-control regression.

Quiet-day cost is controlled by `OLYMPUS_MODEL_TIER` + edit-mode — not graph forks.

## Changing the schedule

Cron strings: `17 9/10/11/12 * * *` UTC in `pipeline-digiquant.yml` (off-peak
minute, hourly retries; later slots skip after a success). After edits, re-run
`actionlint`. Do not `workflow_dispatch` the house pipeline from an agent.

External watchdog (optional, beats GitHub `schedule` lag): a Cloudflare Cron
Trigger or ops runner POSTs `repository_dispatch` with `event_type=olympus-daily`.
That is not `workflow_dispatch` and does not count as house-proof for #3391
until a **schedule** success lands. Example:

```bash
gh api repos/digithings-ai/digithings/dispatches \
  -f event_type=olympus-daily
```
