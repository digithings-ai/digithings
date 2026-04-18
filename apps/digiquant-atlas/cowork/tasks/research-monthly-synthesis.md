# Task: Research — monthly synthesis

**Before anything else:** read [`../PROJECT.md`](../PROJECT.md).

## Objective

Month-end **long-horizon** synthesis: roll baselines + deltas + weekly artifacts into one **`monthly_digest`** JSON, then **publish to Supabase**. Do **not** rely on committed `data/agent-cache/` paths.

Schedule on the **last trading day of the month** or the first session after month-end, per operator preference.

## Steps

1. `pip install -r requirements.txt` if needed; set `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`.
2. Follow [`skills/monthly-synthesis/SKILL.md`](../../skills/monthly-synthesis/SKILL.md) through Phase 5, using **DB-first** context from `daily_snapshots` and `documents` as the skill describes.
3. Build the full `monthly_digest` object (schema: `templates/schemas/monthly-digest.schema.json`). **`date`** = month-ending calendar date (YYYY-MM-DD).
4. Validate and publish (stdin preferred):

   ```bash
   python3 scripts/validate_artifact.py - <<'EOF'
   { ... monthly_digest JSON ... }
   EOF
   python3 scripts/publish_document.py \
     --payload - \
     --document-key monthly/YYYY-MM.json \
     --title "Monthly synthesis" \
     --category rollup \
     --doc-type-label "Monthly Summary"
   ```

   Replace `YYYY-MM` (e.g. `2026-04`).

5. Optional full ETL: `python3 scripts/update_tearsheet.py` (optional disk mirror only).

**Scaffold helper:** [`scripts/monthly-rollup.sh`](../../scripts/monthly-rollup.sh) prints a **local** stub for editing; still end with validate + `publish_document.py` to Supabase (pipe the final JSON with `--payload -`).
