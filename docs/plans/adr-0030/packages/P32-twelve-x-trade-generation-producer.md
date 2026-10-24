# P3.2 — Confirm new twelve-x trade ideas use medium or long

**Lane:** Needs a GitHub token that can read `digithings-ai/twelve-x`, then stronger review. Stop on HTTP 404.

**Parent:** #4762.

## Goal

Find where `fx_trade_ideas_snapshot.timeframe` is assigned. Document it. If new rows are already written as `medium` or `long`, add a test that the literal set stays that pair. If the writer emits a free string such as `1-3M`, leave the writer alone and comment the assignment site on this issue. Do not backfill and do not map `1-3M` onto `medium`.

## Non-goals

- Do not add a Supabase column.
- Do not change the two-pass strategist, rank order, or level repair (side, minimum reward-to-risk, band).
- Do not emit `OrderIntent` rows or call a broker.
- Do not default missing timeframes to `medium`.

## Step 0 — access gate

```bash
gh api repos/digithings-ai/twelve-x --jq .full_name
```

404 or 403: comment the status code and stop. Do not create `nodes/trade_ideas.py` because an upload was named that. Search only after the API returns the repo.

## What the hub already says (do not contradict it)

From `apps/dashboard/lib/twelve-x/types.ts`:

- Consensus rows use `timeframe: 'medium' | 'long'`.
- `FxTradeIdeaRow.timeframe` is optional `string`. Comment in the type: rows published before the identity rollout have no timeframe.
- Confluence components carry `timeframe: string | null` (free string, display).

From `HowItWorksTab.tsx` step 05 and 06: ideas are synthesized, then levels are attached. That logic stays. This package does not re-tune it.

Digiquant side already classifies free strings as display-only (`split_timeframe`, P3.1). A producer that still writes `1-3M` remains compatible. Forcing a rewrite would be a recommendation-policy change.

## Steps after the access gate

1. `rg -n "fx_trade_ideas_snapshot|timeframe" ` in the producer. Read the assignment. Record file and line in the issue comment.
2. If the assigned values are only `medium` and `long`, add a unit test that fails when a new literal is introduced. Do not change the assignment.
3. If values include anything else, or the field is omitted:
   - Do not edit the writer.
   - Comment: the raw value, the file path, and the sentence "left unchanged; digiquant `classify_fx_trade_idea_row` treats this as display-only."
   - Close the PR with no code change, or do not open one.
4. Confirm the publisher does not import an execution client or write `order_intents`. If it does, stop and escalate. Do not "fix" it in this package.
5. Do not edit workflow cron schedules.

## Acceptance checklist

- [ ] Step 0 succeeded, or the issue has a 404/403 comment and zero code.
- [ ] The assignment site is named with path and line.
- [ ] No backfill, no new column, no mapping of free strings onto `medium`.
- [ ] Level-repair and strategist code have an empty diff.
- [ ] No broker client and no `DIGIQUANT_EXECUTION_ROUTING`.
- [ ] Schedules untouched.

## Dependencies

- Blocked by: P3.1 and twelve-x read access.
- Unblocks: nothing. Execution opt-in stays unfiled.

## Out of scope / do not touch

- `digiquant/brokers/**`, `digiquant.execution`, house schedules, #4761.
- Pair allow/deny, risk-style directives, watchlist steering.
- Moving this package under `digiquant/`.
- twelve-x Supabase merge into `core`.
- Secrets, Prime Market credentials, `config.py` values.
