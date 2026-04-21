# Atlas — Deployment & Scheduling

This document covers the GitHub Actions schedulers that drive the Atlas
research pipeline, the secrets they need, how to test locally, and the
rollback / monitoring procedures.

Companion workflows (in `.github/workflows/`):

| Workflow | Trigger | Command | Timeout |
| --- | --- | --- | --- |
| `atlas-baseline.yml` | `cron '0 12 * * SAT'` + `workflow_dispatch` | `python -m digiquant_atlas.graph --run-type baseline --run-date <today>` | 120 min |
| `atlas-delta.yml` | `cron '0 12 * * MON-FRI'` + `workflow_dispatch` | `python -m digiquant_atlas.graph --run-type delta --auto-baseline --run-date <today>` | 45 min |
| `atlas-monthly.yml` | `cron '0 14 28-31 * *'` + last-weekday guard | `python -m digiquant_atlas.graph --run-type monthly --run-date <today>` | 60 min |
| `atlas-graph-ci.yml` | `push` / `pull_request` touching `apps/digiquant-atlas/**` | unit tests + ruff + `actionlint` | 15 min |

## Required repo secrets

Set once per repository — the schedulers reference them by name. Prefer
GitHub **environment** secrets (`environment: atlas-prod`) when you're
ready to gate production runs behind a reviewer.

```bash
gh secret set SUPABASE_URL                 --body "https://<project>.supabase.co"
gh secret set SUPABASE_SERVICE_ROLE_KEY    --body "<service-role-key>"   # server-side only, never ship to frontend
gh secret set LITELLM_PROXY_API_KEY        --body "<litellm-key>"        # LiteLLM proxy bearer
gh secret set OPENAI_API_KEY               --body "<openai-key>"         # BYOK fallback / override
```

Verify:

```bash
gh secret list | grep -E 'SUPABASE|LITELLM|OPENAI'
```

Rotation: re-run `gh secret set <NAME>` with a new value; in-flight runs
keep their copy, new runs pick up the rotated secret.

## Testing a workflow

### Manual `workflow_dispatch` (recommended for first-time validation)

Trigger a dry-run delta (compiles the graph, prints a JSON summary, makes
no LLM calls):

```bash
gh workflow run atlas-delta.yml \
  --ref task/219-w1d-atlas-schedulers \
  -f run_date=2026-04-20 \
  -f dry_run=true
```

Watch the run:

```bash
gh run watch --exit-status
```

Baseline dry-run on the same branch:

```bash
gh workflow run atlas-baseline.yml \
  --ref task/219-w1d-atlas-schedulers \
  -f run_date=2026-04-20 \
  -f dry_run=true
```

### `act` (fully local, optional)

```bash
brew install act
act -W .github/workflows/atlas-delta.yml \
    -j run \
    --secret-file .secrets \
    -e <(echo '{"inputs":{"run_date":"2026-04-20","dry_run":"true"}}')
```

`act` is best-effort — macOS/Linux container differences occasionally
surface issues that don't appear on GitHub-hosted runners. Treat `act`
as a fast pre-check, not a substitute for a real `workflow_dispatch`.

### `actionlint` (static check, pre-push)

```bash
brew install actionlint
actionlint .github/workflows/atlas-*.yml
```

CI also runs `actionlint` on every PR that touches Atlas workflows (see
`atlas-graph-ci.yml`).

## Rollback plan

A run can fail in two shapes:

1. **Crashed fast** (import error, schema mismatch, missing secret). No
   partial writes. Remediation: re-run the workflow once the fix is
   merged, or revert the offending commit and let the next cron tick.
2. **Crashed mid-pipeline** (half-written `documents`, a stray
   `daily_snapshots` row). Atlas writes are idempotent per `(date,
   document_key)` — re-running the same `run_date` will overwrite the
   partial row. If rollback is still required:

   ```bash
   # Point at a Supabase read-replica / staging DB first to verify.
   python3 apps/digiquant-atlas/scripts/validate_db_first.py \
     --date <run-date> --mode full
   ```

   To purge a bad run:

   ```sql
   -- Run against Supabase via the service role.
   DELETE FROM daily_snapshots WHERE date = '<run-date>' AND run_type = '<type>';
   DELETE FROM documents       WHERE date = '<run-date>' AND created_at > '<run-started-at>';
   ```

   Then re-trigger the same workflow via `workflow_dispatch` with the
   original `run_date`.

3. **Scheduler is the problem** (bad cron, runaway cost): disable the
   workflow from the Actions UI (`Disable workflow`) or via CLI:

   ```bash
   gh workflow disable atlas-delta.yml
   ```

   Keep it disabled until the triggering issue is resolved. `gh workflow
   enable atlas-delta.yml` to resume.

## Failure issue convention

Each scheduler opens (or comments on) an issue titled
`atlas-<kind>-failure-YYYY-MM-DD` on failure, with the last 200 log
lines attached. Close the issue manually after remediation; the next
successful run will not auto-close it.

## Cost monitoring

Cost telemetry is owned by Atlas **Phase 9** (see
`src/digiquant_atlas/phases/phase9_evolution.py`). Each run emits
per-phase token counts + USD estimates into the `evolution` document.

Recommended weekly check:

```bash
python3 apps/digiquant-atlas/scripts/fetch_research_library.py \
  --category evolution --limit 10
```

Flag runs where `phase9.cost_usd` exceeds the rolling 4-week median by
more than 3x — that's usually a triage miss (delta behaving like
baseline) or a cache-control regression.

The broader observability story (Prometheus + DigiSmith spans, PR
quality gate, BYOK override) is documented in
`docs/agents/GUARDRAILS.md` and `digismith/`.

## Changing the schedule

Cron strings live at the top of each workflow. UTC always. Remember:

- Anthropic's API is busiest 16:00–22:00 UTC (US afternoon). The 12:00
  UTC slots are chosen for capacity + latency.
- Monthly runs use a `28-31 * *` window plus a shell guard that only
  fires on the last weekday of the month — per-platform `date` flags
  differ, so the guard uses a single POSIX-friendly calculation.

After edits, re-run `actionlint` and trigger a `workflow_dispatch`
dry-run to validate the new schedule hasn't broken wiring.
