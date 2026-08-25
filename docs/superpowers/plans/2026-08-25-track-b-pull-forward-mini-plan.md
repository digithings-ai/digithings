# Mini-plan: Track B pull-forward (ProfileConfig / corpus / planner shadow)

**Status:** unblocked — Track A (#2422 + seed lots #2589/#2595) complete; WP3 on develop via #2603. First package filed as #2609.  
**Parent:** #1950 · metaplan Progress 2026-08-25 · vision brief

## Packages (file issues when starting)

1. **ProfileConfig (DB)** — versioned Pydantic + table; pin at preflight; drives universe/risk/themes/budgets; does **not** fork the digithings-owned house run.
2. **WP12-class shared corpus** — tenant-agnostic keys `theme:` / `asset:` / `segment:`; house writes default; profile may request publish-if-missing.
3. **WP13 shadow AttentionPlan** — extend `edit_mode`; planner cannot expand H4 or rewrite H7/H8; UI shows refresh reasons (#1945).

## Parallel with

- Track A: #2422 labeling → seed `holding_lots` → remove `--no-ledger` → WP3
- Track C: #1945 glass-box surfaces consuming WP1 + labeled events

## Anti-goals

- Graph forks / `run_type` topology
- Live broker cutover without human gate
- Enforcing planner before WP1 reconcile + shadow quality
