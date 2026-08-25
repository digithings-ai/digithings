# Mini-plan: Track B pull-forward (ProfileConfig / corpus / planner shadow)

**Status:** ProfileConfig (#2609 / #2611) + WP12-class corpus (#2613 / #2614) on develop via promote #2615. WP13 shadow in progress as #2616.  
**Parent:** #1950 · metaplan Progress 2026-08-25 · vision brief

## Packages (file issues when starting)

1. **ProfileConfig (DB)** — ✅ #2609 / PR #2611 (promoted #2612): versioned Pydantic + table; pin at preflight; drives universe/risk/themes/budgets; does **not** fork the digithings-owned house run.
2. **WP12-class shared corpus** — ✅ #2613 / PR #2614 (promoted #2615): tenant-agnostic keys `theme:` / `asset:` / `segment:`; house writes default; profile may request publish-if-missing.
3. **WP13 shadow AttentionPlan** — #2616: extend `edit_mode` via `attention_plan.plan_attention_shadow`; planner cannot expand H4 or rewrite H7/H8; refresh reasons for #1945 UI (shadow only, no enforce).

## Parallel with

- Track A: #2422 labeling → seed `holding_lots` → remove `--no-ledger` → WP3
- Track C: #1945 glass-box surfaces consuming WP1 + labeled events

## Anti-goals

- Graph forks / `run_type` topology
- Live broker cutover without human gate
- Enforcing planner before WP1 reconcile + shadow quality
