# Task: Post-mortem — Track B (portfolio) + GitHub backlog

**Before anything else:** read [`../PROJECT.md`](../PROJECT.md).

## When

Run **after** Track B close-out for `RUN_DATE`: [`portfolio-pm-rebalance.md`](portfolio-pm-rebalance.md) steps are complete and `rebalance_decision` / positions / `run_db_first` are in good shape for the date.

## Objective

Record a structured **`pipeline_review`** for the portfolio track, validate, publish to Supabase, and optionally sync **GitHub Issues** for findings marked `github_issue_candidate`.

## Steps

1. **Deterministic validation**

   ```bash
   python3 scripts/validate_db_first.py --date RUN_DATE --mode pm
   ```

   Use `--mode full` if you want the same checks as a full close-out.

2. **Author `pipeline_review` JSON** for `meta.track: "portfolio"`:
   - Fill `body.validation_summary` (commands, failures).
   - Add `body.findings[]` with unique `dedupe_key` values; set `github_issue_candidate` selectively.
   - Schema: [`templates/schemas/pipeline-review.schema.json`](../../templates/schemas/pipeline-review.schema.json).

3. **Validate + publish**

   ```bash
   python3 scripts/validate_artifact.py - < pipeline-review-portfolio.json
   python3 scripts/publish_document.py \
     --payload pipeline-review-portfolio.json \
     --document-key pipeline-review/portfolio/RUN_DATE.json \
     --title "Pipeline review (portfolio) RUN_DATE" \
     --category rollup \
     --doc-type-label "Pipeline Review" \
     --date RUN_DATE
   ```

4. **GitHub Issues** (authenticated `gh`; labels: [`docs/ops/GITHUB_PIPELINE_LABELS.md`](../../docs/ops/GITHUB_PIPELINE_LABELS.md)):

   ```bash
   python3 scripts/pipeline_review_to_github.py --date RUN_DATE --track portfolio --dry-run
   python3 scripts/pipeline_review_to_github.py --date RUN_DATE --track portfolio
   ```

## Who fills the JSON (v1)

Human or agent explicitly composes the JSON. LLM assist for semantic sections is optional later.

## Related

- [`docs/agentic/EVOLUTION_GITHUB_IMPLEMENTATION_PLAN.md`](../../docs/agentic/EVOLUTION_GITHUB_IMPLEMENTATION_PLAN.md)
