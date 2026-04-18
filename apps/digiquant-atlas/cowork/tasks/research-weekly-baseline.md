# Task: Research — weekly baseline (Track A)

**Before anything else:** read [`../PROJECT.md`](../PROJECT.md).

## Objective

**Positioning-blind** research for the **baseline anchor** (typically **Sunday** / weekly open). Full segment scope vs `baseline_date`; set `"run_type": "baseline"` in the payload when you publish a full-scope run for that anchor. Prefer **building on** prior `research_delta` rows in Supabase for that week (carry-forward, append-first, selective rewrites) rather than rewriting every segment from scratch when nothing material changed.

**Do not** read `config/preferences.md`, `config/investment-profile.md`, or `config/portfolio.json`.

**Final step (mandatory):** the run must produce the **digest** — the **single research overview** that synthesizes all sub-segments (`documents` `digest` + materialized `daily_snapshots` for `RUN_DATE`). That synthesis is **research**, not portfolio work.

## Steps

1. `pip install -r requirements.txt` if needed; set `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`.
2. Follow [`skills/weekly-baseline/SKILL.md`](../../skills/weekly-baseline/SKILL.md) through the full pipeline (orchestrator phases including **Phase 7 — master synthesis / digest**), so **`digest`** and **`daily_snapshots`** for `RUN_DATE` are published. The digest is the **last deliverable** of this task.
3. `python3 scripts/run_db_first.py --skip-execute --validate-mode research` (add `--date YYYY-MM-DD` if not today).
4. `python3 scripts/validate_pipeline_step.py --date RUN_DATE --step research_closeout` — confirms **`digest`** + **`daily_snapshots.snapshot`** match [`templates/digest-snapshot-schema.json`](../../templates/digest-snapshot-schema.json) (requires `pip install jsonschema`).

**Prompt helper:** [`scripts/cowork-research-prompt.txt`](../../scripts/cowork-research-prompt.txt)

**Portfolio (Track B):** run [`portfolio-pm-rebalance.md`](portfolio-pm-rebalance.md) **only after** this task has published `digest` for the same date — the PM task **reads** the digest; it does not compile it.
