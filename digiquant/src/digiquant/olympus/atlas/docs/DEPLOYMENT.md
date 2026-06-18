# Atlas — Deployment & Scheduling

This document covers the GitHub Actions schedulers that drive the Atlas
research pipeline, the secrets they need, how to test locally, and the
rollback / monitoring procedures.

Companion workflows (in `.github/workflows/`):

A single workflow, `olympus.yml`, drives all scheduled research runs. Its
`resolve` job picks the run type from the trigger; the `run` job executes the
unified Atlas+Hermes pipeline via `python -m digiquant.olympus.hermes.chain`.

| Workflow | Trigger | Resolves to | Timeout |
| --- | --- | --- | --- |
| `olympus.yml` | `cron '0 12 * * MON-SAT'` | Saturday -> `baseline`, weekday -> `delta` (`--auto-baseline`) | 240 min |
| `olympus.yml` | `cron '0 14 28-31 * *'` | `monthly` (gated to the last weekday of the month) | 240 min |
| `olympus.yml` | `workflow_dispatch` | explicit `run_type` input, or `auto` to infer by day | 240 min |
| `atlas-graph-ci.yml` | `push` / `pull_request` touching `digiquant/src/digiquant/olympus/{atlas,hermes}/**`, `tests/dq/{atlas,hermes}/**`, or `olympus.yml` | unit tests + ruff + `actionlint` | 15 min |

Non-secret tunables (OpenRouter routing, analyst cap, feature flags,
checkpointer, tracing) live in `.github/olympus-pipeline.yml` and are loaded
into `$GITHUB_ENV` by the "Load pipeline configuration" step.

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

The delta scheduler invokes `--auto-baseline`, which resolves the most
recent `research_baseline_manifest` document from Supabase. **Before the
first weekday delta can succeed, a baseline run must have landed at
least one manifest.** If you trigger the delta first, it raises
`SystemExit("--auto-baseline could not resolve a baseline date …")`
and the failure-issue step fires.

Bootstrap a fresh environment in this order:

```bash
# 1. Set secrets (see above).
# 2. Kick a baseline manually — wait for it to succeed before delta schedules.
gh workflow run olympus.yml \
  -f run_type=baseline \
  -f run_date="$(date -u +%Y-%m-%d)"
gh run watch --exit-status

# 3. Verify a baseline manifest exists in Supabase:
python3 digiquant/scripts/atlas/fetch_research_library.py \
  --category research_baseline_manifest --limit 1

# 4. Delta can now schedule safely; the next 12:00 UTC Mon-Fri tick will run.
```

## Testing a workflow

### Manual `workflow_dispatch` (recommended for first-time validation)

Trigger a dry-run delta (compiles the graph, prints a JSON summary, makes
no LLM calls):

```bash
gh workflow run olympus.yml \
  -f run_type=delta \
  -f run_date=2026-04-20 \
  -f dry_run=true
```

Watch the run:

```bash
gh run watch --exit-status
```

Baseline dry-run:

```bash
gh workflow run olympus.yml \
  -f run_type=baseline \
  -f run_date=2026-04-20 \
  -f dry_run=true
```

### `act` (fully local, optional)

```bash
brew install act
act -W .github/workflows/olympus.yml \
    -j run \
    --secret-file .secrets \
    -e <(echo '{"inputs":{"run_type":"delta","run_date":"2026-04-20","dry_run":"true"}}')
```

`act` is best-effort — macOS/Linux container differences occasionally
surface issues that don't appear on GitHub-hosted runners. Treat `act`
as a fast pre-check, not a substitute for a real `workflow_dispatch`.

### `actionlint` (static check, pre-push)

```bash
brew install actionlint
actionlint .github/workflows/olympus.yml
```

CI also runs `actionlint` on every PR that touches the Olympus workflow (see
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
   python3 digiquant/scripts/atlas/validate_db_first.py \
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
   gh workflow disable olympus.yml
   ```

   Keep it disabled until the triggering issue is resolved. `gh workflow
   enable olympus.yml` to resume.

## Failure issue convention

The pipeline opens (or comments on) a single rolling issue titled
`olympus-<kind>-failure` (no date in the title), with the failing run's
date, run URL, and last 200 log lines appended as a new comment. That
way consecutive daily failures stack in one place instead of spamming
one issue per day. Close the issue manually after remediation; the next
successful run will not auto-close it, and a later failure will reopen /
reuse the same title.

## Cost monitoring

Cost telemetry is owned by Atlas **Phase 9** (see
`src/digiquant_atlas/phases/phase9_evolution.py`). Each run emits
per-phase token counts + USD estimates into the `evolution` document.

Recommended weekly check:

```bash
python3 digiquant/scripts/atlas/fetch_research_library.py \
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
- Monthly runs use a `28-31 * *` window plus a `guard` job that only
  proceeds on the **last weekday of the month**. The guard walks
  tomorrow through end-of-month and proceeds only if no later weekday
  remains in the current calendar month. That correctly covers the
  case where the last calendar day falls on a Sat/Sun (we run on the
  preceding Fri) and 28/29-day Februaries. Pass `force_monthly=true` via
  `workflow_dispatch` to skip the guard for manual backfills.

After edits, re-run `actionlint` and trigger a `workflow_dispatch`
dry-run to validate the new schedule hasn't broken wiring.
