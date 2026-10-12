# Review — PR #4732: fix(twelve-x): fall back to carried episodes when today's idea board is empty

- reviewer: in-session fresh-context review (subagent, no prior repo context; local checkout untouched per task constraints — all evidence via `gh pr diff` / `gh api`)
- subject: digithings-ai/digithings#4732, base `develop`, head `fix/trade-ideas-board-row-read`, merge commit `3fd36a635f94193a039dc2ebf9c9d8e886c9ce6c` (merged 2026-09-29)
- verdict: **APPROVE-WITH-MINORS**
- severity counts: Critical 0 / Important 0 / Minor 2 / Trivia (file-only) 4
- scope: this PR's diff only — `apps/dashboard/lib/twelve-x/fetch.ts`, `apps/dashboard/lib/twelve-x/fetch.test.ts`, `apps/dashboard/lib/twelve-x/types.ts`. Promotion, writer repo, and everything else out of scope.

## What the change does

`getTradeIdeas(runDate)` read the board by exact `run_date` match. A continued episode is written back to its origin `run_date`, so carried ideas vanished from "today's trade ideas". When the exact-date query returns zero rows, the PR adds a fallback: newest-refresh-first select over `run_date <= board` (over-fetch 50), anchor "today's publish" to the max `as_of` in code with a board-day-start guard, keep rows within a 15-minute batch window of that max, dedupe to one row per episode by `idea_id` (axis fallback for pre-identity rows), cap at 10. `getTradeIdeaArchive` reuses the shared column list; `FxTradeIdeaRow` gains optional `idea_id` / `timeframe`. Seven new tests pin the fallback shape.

## Verification performed (commands run)

- `gh pr view 4732 --json ...` — title, base/head, merge sha, file list confirmed.
- `gh pr diff 4732` — full diff read (3 files, +248/−11).
- Fetched merged file contents via `gh api .../contents/...?ref=3fd36a6...` for `fetch.ts` (lines 525–700), `types.ts` (405–435), plus `querySupabase` (lines 68–100), `TradeIdeasPanel.tsx` consumer (`const [top, ...rest] = ideas`), and `IdeaCardsIndex.tsx`.
- Cross-repo check: `digithings-ai/twelve-x` PR #215 diff (writer now dual-publishes carried episodes under origin + today board keys sharing one `idea_id`) and migration `033_trade_idea_identity.sql` (adds `idea_id uuid`, `timeframe text` to `fx_trade_ideas_snapshot`) — confirms the selected columns exist and the fallback's dedupe key matches the writer's identity scheme.
- Tests were NOT executed locally (task constraint forbids using the local checkout, which sits on an unrelated stale branch). Test assertions were verified by reading the mock (`responses` queue consumed in order, `eq`/`lte`/`order`/`limit` recorders) against each new case. Suite result (58/58 claimed in follow-up commit message; body evidence shows an earlier 55-test run) is taken from the author's record, not independently reproduced — recorded as unverified below.

## Findings

### Minor 1 — Fallback board has no rank tiebreak, so display order is arbitrary within one publish
- `apps/dashboard/lib/twelve-x/fetch.ts:680` — fallback orders by `as_of` descending only, no secondary key.
- `apps/dashboard/lib/twelve-x/fetch.ts:690` — result returned in that order (post-dedupe), not rank order.
- Consumer renders array order as rank order: `apps/dashboard/components/twelve-x/TradeIdeasPanel.tsx` does `const [top, ...rest] = ideas` with focal chrome documented as "the top-ranked idea".
- Mechanism: the writer passes a single `as_of` per publish (`snapshot_publish.py`: `_trade_idea_row(idea, rank, run_date, as_of=as_of)`), so every row in one publish batch shares an identical `as_of`. `ORDER BY as_of DESC` ties across the whole batch, and Postgres returns tied rows in unspecified order. The unit mock returns array order, masking this. On fallback days the focal #1 pick and the `slice(0, 10)` cut are therefore arbitrary rather than rank-driven.
- Why Minor, not blocking: read-only display order on a fallback path that fires only on empty-board days (and going forward the writer's dual-publish in twelve-x#215 makes the exact-date query hit, so the fallback is a rare backstop). Content is correct; only presentation order is affected. No data loss, no trading path.
- Suggested fix: `.order('as_of', { ascending: false }).order('rank', { ascending: true })` on the fallback query.

### Minor 2 — Docstring/test prose claims run-attribution the code does not implement
- `apps/dashboard/lib/twelve-x/fetch.ts:685` — guard is `latestMs < Date.parse(`${runDate}T00:00:00.000Z`)`, i.e. "some publish landed at/after the board's UTC midnight". Nothing ties a publish to a board run: `run_date` on fallback rows is the origin date, and `as_of` carries no run label.
- Consequence: a late 28th publish landing 29th 00:10Z satisfies the 29th board's guard (00:10 >= 29th 00:00), so the 29th board shows the 28th's rows — contradicting the docstring ("yesterday's rows can never satisfy today's board by clock accident", lines ~655–660) and the test comment at `apps/dashboard/lib/twelve-x/fetch.test.ts:318` ("off the 29th's until the 29th publishes for real"). Only the 28th side is tested; the 29th side is asserted in prose, not pinned.
- Why Minor: the code behavior is arguably the *desired* one (an episode refreshed 10 minutes prior is live; an empty 29th board would be worse), so this is a prose/intent mismatch, not a data bug. Fix by softening the docstring/test comment to describe the actual guarantee ("a publish landed since the board date began") and optionally adding a test pinning the 29th-side behavior either way.

## Trivia (file-only, not in PR comment)

1. PR body Accuracy §5 says errors "fall back to `[]`". Verified `fetch.ts:68–100`: `querySupabase` returns `[]` only for null-data-without-error; genuine errors exhaust retries and rethrow, and `getTradeIdeas` has no try/catch. Pre-existing semantics, body wording only.
2. Malformed `runDate` (non-empty, unparsable): `Date.parse(`${runDate}T00:00:00.000Z`)` is NaN, `latestMs < NaN` is false, so the guard passes and the fallback may return rows where the old code returned `[]`/error. Negligible — callers pass real board dates.
3. If `recent[0].as_of` is unparseable while older rows are valid, `!Number.isFinite(latestMs)` returns `[]` for the whole fallback. Non-issue in practice (`as_of` is set per publish), noted for completeness.
4. Fallback rows render with their origin `run_date` (`TradeIdeasPanel` derives `boardDate` from `ideas[0]?.run_date`; `IdeaCardsIndex` shows `{row.runDate} #{row.rank}`). Reasonable for carried ideas (shows provenance), just noting the "today" board will display an older date chip.

## Explicitly checked, no issue

- Security: read-only anon select; column list is a compile-time constant (`fetch.ts:606`); no routes/auth/secrets/trading paths. No human-gate trigger.
- Stale-exclusion: day-start guard + 15-minute batch window correctly exclude closed episodes and no-publish days (pinned by tests at `fetch.test.ts:302`, `:365`).
- Dedupe-then-slice (`fetch.ts:690`): cap applies post-dedupe, so twins cannot eat board slots; over-fetch 50 is ample against a board cap of 10.
- `lte('run_date', runDate)` upper bound prevents future boards leaking in.
- Deploy-order risk (selecting new columns): cleared — twelve-x migration 033 adds both columns and the already-merged writer PR #215 reads/writes `idea_id`, so the columns are live where the writer operates; author's "column is live in prod" claim is corroborated.
- `timeframe` in the select + dedupe axis fallback: dedupe keys on real values for post-rollout rows, documented degradation only for pre-identity NULL rows.
- Archive reuse of the shared column list is purely additive; PK `(run_date, rank)` untouched.

## Unverified (stated plainly per policy)

- Test suite not run locally (constraint: no local checkout use). `fetch.test.ts` assertions verified by reading mock + cases; pass/fail status relies on author evidence.
- Writer-side single-`as_of`-per-publish confirmed by reading twelve-x#215's diff context (`_trade_idea_row(..., as_of=as_of)` in `snapshot_publish.py` hunk); full writer file not fetched.
- Prod Supabase project migration state not directly inspected; inferred via writer dependency as above.
