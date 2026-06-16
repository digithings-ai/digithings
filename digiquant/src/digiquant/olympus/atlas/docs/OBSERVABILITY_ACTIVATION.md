# Olympus Pillar 2/3 — Activation Checklist (Human Gate)

The hedge-fund-in-a-box overhaul (#726) landed its code across many PRs. The remaining steps
are **operator actions** — apply migrations, flip a flag, enable crons, and run the single
baseline validation. None of this happens automatically; CI never applies migrations, and the
crons + the curated anon view are deliberate human gates.

> **Cost note.** Only the final baseline run spends LLM budget (~$8). Everything else here is
> free: migrations are DDL, the flag is an env var, the attribution/backtest crons are
> deterministic Polars, and the resolver makes ~1 cheap reflector call per due decision (~10/day).
> Do **not** trigger extra baseline/delta runs while validating.

## 1. Apply migrations (manual, in order)

Apply against prod via the Supabase SQL editor or MCP `apply_migration`. All are idempotent.

| Migration | What it adds | Notes |
|-----------|--------------|-------|
| `039_position_risk_fields.sql` | `positions` += stop/target/horizon/conviction/sector_bucket | Advisory display fields. Safe. |
| `040_position_attribution.sql` | `position_attribution` table (anon-read) | Feeds the Attribution tab + the attribution cron. |
| `041_atlas_run_health_view.sql` | **Curated `atlas_run_health` view (anon-read)** | ⚠️ Re-exposes run health that #707 revoked. Owner sign-off required. Exposes status/segment-counts/model/timing **only** — never cost/tokens/error_summary/breakdown. |

Verify after apply:

```sql
select count(*) from position_attribution;          -- table exists (0 rows is fine)
select * from atlas_run_health order by run_date desc limit 3;  -- view returns rows, no spend cols
```

## 2. Flip the per-position risk flag

`OLYMPUS_POSITION_RISK_FIELDS` (read in `hermes/portfolio_materialize.py`) is **off by default**.
To populate the advisory stop/target/horizon/conviction fields, set it on the runs that
materialize the book — add to the `Run baseline` / `Run delta` step env in
`.github/workflows/atlas-baseline.yml` and `atlas-delta.yml`:

```yaml
          OLYMPUS_POSITION_RISK_FIELDS: "true"
```

Until then the Position Risk tab shows its "advisory risk fields not populated" empty state — by
design, not a bug.

## 3. Enable the analytics crons

These workflows ship dormant in the repo; they begin firing once merged to `develop` (and are
runnable now via **workflow_dispatch**). Confirm the referenced secrets exist
(`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`):

| Workflow | Schedule (UTC) | Does | Requires |
|----------|----------------|------|----------|
| `atlas-resolve-decisions.yml` | daily 22:00 | Resolves due `decision_log` rows (alpha + reflection) — closes the learning loop | migration 026 (live); OpenRouter |
| `atlas-attribution.yml` (attribution job) | daily 21:30 | Upserts `position_attribution` for today | **migration 040 applied** |
| `atlas-attribution.yml` (backtest job) | weekly SUN 13:00 | Zero-LLM decision tear sheet → artifact | read-only |

Order matters: apply migration 040 **before** the attribution cron first fires, or its run fails
on a missing table (fail-soft exit 1, noisy but harmless).

## 4. Single baseline validation (the only spend)

After 1–3 are done, run ONE baseline to prove the end-to-end book:

```bash
# via workflow_dispatch on atlas-baseline.yml, or locally:
python -m digiquant.olympus.hermes.chain --run-type baseline --run-date "$(date -u +%F)"
```

Then verify (Supabase row counts > 0 and a spot-check):

- `positions` for the run date is **non-empty** with sized/capped weights (Pillar 2) and, if the
  flag is on, populated `stop_loss_pct`/`conviction`.
- `nav_history`, `theses`, `decision_log` (pending) have rows; a sector document shows real
  breadth/RS numbers (Pillar 1).
- `atlas_run_diagnostics` has a row for the run (Pillar 1B).
- Dashboard `/observability`: Run Health shows the run; after the next 22:00 resolver + 21:30
  attribution, the Decision Scorecard and Attribution tabs populate.

## Rollback

- Crons: disable via the Actions UI or revert the workflow files.
- Flag: unset `OLYMPUS_POSITION_RISK_FIELDS` (existing rows keep their values; new rows write NULL).
- View: `DROP VIEW IF EXISTS public.atlas_run_health;` (re-closes anon run-health).
- Tables 039/040 are additive; leaving them in place is harmless.
