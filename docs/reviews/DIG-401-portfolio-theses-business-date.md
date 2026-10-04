# DIG-401 review — age the portfolio theses pane off the business date

- **Subject:** PR [#5062](https://github.com/digithings-ai/digithings/pull/5062), commit `999810f3` (fix) and `38fd8d8d` (review response)
- **Reviewer:** fresh-context `general` subagent (not the authoring session), 2026-10-04
- **Verdict:** `APPROVE_WITH_NITS` — 0 blocking, 5 non-blocking
- **Reviewed range:** `ae5a3ea9..999810f3` (2 files, +73/−10)

## What was reviewed

`/portfolio/theses` in `apps/dashboard-api/src/routes/portfolio.ts` aged the pane off
`theses.updated_at` — a row write timestamp — instead of `theses.date`, the business
date the book was struck on. Because `theses` keeps one row per thesis per date, an
unfiltered read repeated every thesis across dates and inflated every count. The fix
switches to the shared `maxThesisDate` / `rowsAtDate` helpers introduced by DIG-354, so
this pane and `/rates/theses` now share one mapper.

## Findings

### Blocking

None.

### Non-blocking

1. **Overstated mutation coverage in the commit message** (`999810f3`). It claimed
   "switching the field back to `updated_at` kills 5 tests". That figure came from a
   narrower mutation where the three pre-existing tests fail only because `tip`
   resolves to `null` and the envelope comes back empty (`expected undefined`), not
   because they detect the aging defect. Against the real pre-fix route, 2 tests
   caught it.
   **Resolution:** addressed in `38fd8d8d` rather than by softening the claim — see
   "Nit resolutions" below.
2. **The `tip === null` path was unpinned** (`portfolio.ts:178-186`). Unreachable in
   core (`theses.date` is `NOT NULL`, `migrations/001_initial_schema.sql:60`) but
   coherent: null tip → `[]` → `as_of: null`, HTTP 200. `fx.test.ts` has the same gap,
   so this was a shared hole, not a regression.
   **Resolution:** fixed in `38fd8d8d`.
3. **Fixture `date` fields asserted nothing** (`portfolio.test.ts:35,36,54,56,67`). The
   three fixtures gained `date: "2026-09-28"` in `999810f3` so `rowsAtDate(rows, null)`
   would not return `[]`. Honest values — the vehicle `date` is load-bearing for the
   vehicle filter to keep `GLD` — and no original assertion was removed, but each was
   inert.
   **Resolution:** fixed in `38fd8d8d`.
4. **Self-contradicting comment** (`portfolio.test.ts:78`, copied from `fx.test.ts:89`):
   "`thesis_vehicles` must be matched first: it does not contain 'theses'." The
   parenthetical argues the ordering is unnecessary. Branch order is irrelevant either
   way.
   **Resolution:** comment dropped in `38fd8d8d`.
5. **Row order inside one date is DB-dependent** (`portfolio.ts:173`). `order=date.desc`
   has no secondary sort key, so `data.theses` order within a date is whatever
   PostgREST returns. The new test's `toEqual(["uuid-t1","uuid-t2"])` passes because the
   mock returns rows in that order; it pins the filter, which is the point, but is not a
   determinism guarantee.
   **Resolution:** not changed — accepted, noted here so a future reader does not read
   the assertion as an ordering contract.

## Verification performed by the reviewer

- `git show 999810f3 --stat` — 2 files, no lockfile, no new deps, no unrelated changes.
- `npm --prefix apps/dashboard-api test` — 325 passed / 325, 29 files.
- `npx tsc --noEmit` in `apps/dashboard-api` — clean.
- Grepped `portfolio.ts` for `updated_at` / `as_of`: zero hits in the theses path;
  `maxDate` still live at `:107,194,195,251,344` (not dead); no unused imports.
- Schema: `migrations/024_thesis_deliberation_first_class.sql:18-34` —
  `thesis_vehicles(date date NOT NULL, …, PRIMARY KEY (date, thesis_id, ticker), FOREIGN KEY (date, thesis_id) REFERENCES theses (date, thesis_id) ON DELETE CASCADE)`.
  The FK means a vehicle row cannot exist without its same-date parent, so filtering
  vehicles to the tip can never orphan or cross-join.
- Writer side: `thesis_io.py:197-251` and `portfolio_materialize.py:199-241` write the
  parent and child rows on the same `date_str`.

## Author's follow-up verification

The reviewer was read-only and could not execute the mutation itself, so it inferred the
test count. Executed directly, in the worktree:

| Mutation | Result |
| --- | --- |
| Full pre-fix `portfolio.ts` (`999810f3^`) vs original tests | 2 failed |
| Narrow mutation (only the `tip` line reverted, `rowsAtDate` kept) | 5 failed — 3 by the `null`-tip path |
| Full pre-fix `portfolio.ts` vs strengthened tests (`38fd8d8d`) | **4 failed, all for the right reason** |

Suite after `38fd8d8d`: 326 passed / 326, 29 files. `tsc --noEmit` clean.
`portfolio.ts` is byte-identical to what the reviewer read — the follow-up commit
touches only the test file.

## Nit resolutions

| Nit | Action |
| --- | --- |
| 1 — overstated claim | Not softened; made true. `38fd8d8d` asserts `as_of` in the first envelope test so its fixture `date` is load-bearing, and pins the `tip === null` path. The original figure's failure mode is recorded in that commit message. |
| 2 — `tip === null` unpinned | Added `theses without a dated row returns an empty book and a null as_of`. |
| 3 — inert fixture dates | Added `expect(res.as_of).toBe("2026-09-28")` to the envelope test. |
| 4 — self-contradicting comment | Dropped. |
| 5 — row order | Accepted as-is, documented above. |

## Residual risk / follow-ups

- **Vehicles at the tip date vs carry-forward — reachable divergence.** The FK prevents
  orphans, but `thesis_io.py:236-238` swallows per-ticker upsert failures with a warning
  and `portfolio_materialize.py:182-183` calls vehicle writes "best-effort enrichment
  and never block the book". On such a day a tip-date thesis renders `vehicles: []` in
  the Worker pane while the Next dashboard's Theses tab still shows a ticker, because
  `apps/dashboard/lib/thesis-story.ts:8-11` deliberately carries forward the latest
  mapping ≤ anchor date. That is the more coherent "one date book" semantics the ticket
  asks for, but it is a visible cross-surface difference worth a human eyeballing
  `/portfolio/theses` and the web Theses tab side by side after deploy.
- **The same class of bug is still live in `/dossier/{ticker}`** (`portfolio.ts:355-371`):
  it reads `theses` and `thesis_vehicles` with `select=*&limit=…`, no `order`, no date
  filter, and `.find()`s the first match in arbitrary date order. Out of scope for
  DIG-401, but the dossier pane will now disagree with the Theses pane beside it.
- `needs_resolution` (the `/theses/signals` filter, `portfolio.ts:177`) appears in no
  migration in the repo, so against real core data that pane is likely always empty.
  Pre-existing, untouched by this diff.