# Task: Research — daily delta (Track A)

**Before anything else:** read [`../PROJECT.md`](../PROJECT.md).

## Objective

**Positioning-blind** **delta** research for the run date (Mon–Sat or any intra-week / high-frequency slot). Use `"run_type": "delta"` unless you are intentionally doing a baseline-class run.

**Do not** read `config/preferences.md`, `config/investment-profile.md`, or `config/portfolio.json`. Track A is strictly research — no portfolio weights, no opportunity screening, no thesis-to-vehicle mapping.

**Output contract:**

| Artifact | document_key pattern | Schema |
|----------|---------------------|--------|
| Per-segment delta docs | `deltas/{SEGMENT}.delta.md` (one per changed segment) | Phase 6 of `skills/daily-delta/SKILL.md` |
| Materialized digest snapshot | `digest` | `templates/digest-snapshot-schema.json` (research-only: no `portfolio` block required) |
| Supabase snapshot row | `daily_snapshots` for `RUN_DATE` | same schema |

**Final step (mandatory):** after per-segment delta documents are published, **compile the research-only digest** for `RUN_DATE` via Phase 7B. **Do not** run Phase 7C–7D (portfolio monitor / PM) — those belong in [`portfolio-pm-rebalance.md`](portfolio-pm-rebalance.md).

## Steps

1. `pip install -r requirements.txt` if needed; set `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`.
2. Follow [`skills/daily-delta/SKILL.md`](../../skills/daily-delta/SKILL.md) **Phases 1–6** (triage, segment analysis, per-segment delta documents). Publish one `document_delta` per segment (status `updated` or `skipped` with reason) under `deltas/{SEGMENT}.delta.md`. Do **not** publish a single aggregated `research_delta` blob in place of per-segment docs.
3. Optionally run the fold/changelog step:
   ```bash
   python3 scripts/fold_document_deltas.py --date RUN_DATE
   ```
4. Follow [`skills/daily-delta/SKILL.md`](../../skills/daily-delta/SKILL.md) **Phase 7B** (delta-request JSON + `materialize_snapshot.py`) to publish `documents.digest` and `daily_snapshots` for `RUN_DATE`. The digest snapshot must **not** include `portfolio`, `portfolio_recs`, or any Track B PM artifacts — it is a research-only document.
5. Validate:
   ```bash
   python3 scripts/validate_artifact.py - <<'EOF'
   <paste digest snapshot JSON>
   EOF
   python3 scripts/run_db_first.py --skip-execute --validate-mode research --date RUN_DATE
   python3 scripts/validate_pipeline_step.py --date RUN_DATE --step research_closeout
   ```

**Prompt helper:** [`scripts/cowork-research-prompt.txt`](../../scripts/cowork-research-prompt.txt)
