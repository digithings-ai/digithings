# Task: Research — per-document deltas + fold (Track B)

**Before anything else:** read [`../PROJECT.md`](../PROJECT.md).

## Objective

Run **Phase 6** of [`skills/daily-delta/SKILL.md`](../../skills/daily-delta/SKILL.md) only: load the week’s **`research_baseline_manifest`**, publish one validated **`document_delta`** per manifest line (skipped or updated), then **fold** into materialized research JSON and **`research_changelog`**.

This task **does not** replace the digest **`delta-request.json`** / `materialize_snapshot` pass — schedule a follow-up digest delta or combine with [`portfolio-pm-rebalance.md`](portfolio-pm-rebalance.md) when you need the full day closed out.

## Preconditions

- Supabase credentials (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`).
- A **`research_baseline_manifest`** row for the current week (usually published on Sunday baseline).
- Prior calendar day has **materialized** `documents` rows for each `target_document_key` you will update (or accept fold warnings for missing priors).

## Steps

1. `pip install -r requirements.txt` if needed.
2. Follow **Phase 6** in [`skills/daily-delta/SKILL.md`](../../skills/daily-delta/SKILL.md) (Steps 6.1–6.3).
3. Run:

   ```bash
   python3 scripts/fold_document_deltas.py --date YYYY-MM-DD
   ```

4. Optional: `python3 scripts/validate_db_first.py --date YYYY-MM-DD --mode research` (passes if digest or `research_delta` or new research artifacts exist for the date).

## Outputs

- One or more `document-deltas/…` rows on `documents` for the run date.
- Folded full JSON rows per `target_document_key` (today’s date).
- `research-changelog/YYYY-MM-DD.json` unless fold was run with `--skip-changelog`.
