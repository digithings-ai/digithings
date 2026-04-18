# Task: Post-mortem — Track A (research) + GitHub backlog

**Before anything else:** read [`../PROJECT.md`](../PROJECT.md).

## When

Run **after** research close-out for `RUN_DATE`: published **`digest`** and `daily_snapshots` for Track A are complete (see [`research-daily-delta.md`](research-daily-delta.md) or [`research-weekly-baseline.md`](research-weekly-baseline.md)).

## Objective

Record a structured **`pipeline_review`** for the research track, validate, publish to Supabase, and optionally sync **GitHub Issues** for findings marked `github_issue_candidate`.

## Steps

1. **Deterministic validation** (adjust flags to match what you published):

   ```bash
   python3 scripts/validate_db_first.py --date RUN_DATE --mode research
   ```

2. **Author `pipeline_review` JSON** for `meta.track: "research"`:
   - Fill `body.validation_summary` with what ran (`commands_run`) and any failures.
   - Add `body.findings[]` with unique `dedupe_key` per row; set `github_issue_candidate: true` only for items you want as Issues.
   - See [`templates/schemas/pipeline-review.schema.json`](../../templates/schemas/pipeline-review.schema.json).

3. **Validate + publish**

   ```bash
   python3 scripts/validate_artifact.py - < pipeline-review-research.json
   python3 scripts/publish_document.py \
     --payload pipeline-review-research.json \
     --document-key pipeline-review/research/RUN_DATE.json \
     --title "Pipeline review (research) RUN_DATE" \
     --category rollup \
     --doc-type-label "Pipeline Review" \
     --date RUN_DATE
   ```

   Use **`--payload -`** with stdin if you prefer not to write a local file.

4. **GitHub Issues** (requires authenticated [`gh`](https://cli.github.com/); labels documented in [`docs/ops/GITHUB_PIPELINE_LABELS.md`](../../docs/ops/GITHUB_PIPELINE_LABELS.md)):

   ```bash
   python3 scripts/pipeline_review_to_github.py --date RUN_DATE --track research --dry-run
   python3 scripts/pipeline_review_to_github.py --date RUN_DATE --track research
   ```

## Who fills the JSON (v1)

Human or agent explicitly composes the JSON from the session. Optional LLM assist for narrative fields is a later refinement.

## Related

- [`docs/agentic/EVOLUTION_GITHUB_IMPLEMENTATION_PLAN.md`](../../docs/agentic/EVOLUTION_GITHUB_IMPLEMENTATION_PLAN.md)
- [`RUNBOOK.md`](../../RUNBOOK.md) — pipeline review keys
