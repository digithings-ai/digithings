# DIG-442 review — `/theses/signals` filters a column core `theses` does not have

- **Subject:** PR [#5079](https://github.com/digithings-ai/digithings/pull/5079), commit `695b2c88d` (fix) and `015f6816f` (review response)
- **Reviewer:** fresh-context `general` subagent (not the authoring session), 2026-10-05
- **Verdict:** `APPROVE_WITH_NITS` — 0 blocking, 0 major, 2 minor
- **Reviewed range:** `2d406982a..695b2c88d` (2 files), extended to `015f6816f` (4 files, +46/−6)

## What was reviewed

`/theses/signals` in `apps/dashboard-api/src/routes/portfolio.ts:184` filters core
`theses` on `needs_resolution`:

```ts
const filtered = onlySignals ? rows.rows.filter((r) => r.needs_resolution === true) : rows.rows;
```

`needs_resolution` is not a column of core `theses` and no writer populates it, so the
predicate is false for every real row and the pane is empty against live core. The
fixture covering it supplied the column by hand and asserted one row survived, so the
suite proved a shape core cannot produce — which is precisely why the dead filter
stayed green.

## Findings

### Blocking / major

None.

### Minor

1. **The commit message overstated what the new test pins.** `695b2c88d` claimed
   "Removing or repointing the filter now turns this test red instead of passing
   quietly." The reviewer executed the repointing mutation and it stayed **green**:
   changing the predicate to `r.confidence > 0.9` is also false for both fixture rows,
   so the empty result is unchanged. Only two things are actually pinned — the empty
   shape, and the `as_of: null` tip date — and against a mocked read the test stages
   the causation rather than proving it.
   **Resolution:** addressed in `015f6816f` — the claim in the commit message is now
   scoped to deletion ("Deleting the filter now turns this test red"), with the
   repointing limitation stated explicitly rather than dropped; the `it()` name no
   longer asserts causation ("because"); and the comment block above the test records
   the limit so the next reader does not over-read it.
2. **The fiction was still documented as live work in two other files.**
   `apps/digiquant-app/BLOCKS.md:38` told the next agent to `add GET
   /theses?needs_resolution=`, i.e. to build a query parameter on a column that does
   not exist. `apps/dashboard-api/CONTRACT.md:468` listed `/theses/signals` among live
   routes with no caveat, so a consumer reading the contract had no way to know the
   pane is permanently empty.
   **Resolution:** addressed in `015f6816f`. BLOCKS.md now points at the existing
   `/theses/signals` route and explicitly forbids adding `?needs_resolution=`.
   CONTRACT.md states the route returns an empty book and that consumers must render
   "no signals", not "no theses".

## Reviewer-adopted argument for keeping the filter

The reviewer independently arrived at the reason the dead predicate should be labelled
rather than deleted in this diff, and this is the strongest evidence recorded anywhere
on the ticket for the pending board decision:

`/theses/signals` is catalogued (`access.ts:54`, `CONTRACT.md:468`) and rendered as a
block labelled "Signals to resolve" (`clients/digiquant-tui/src/catalog.ts:141`). If
the filter were simply removed, that block would receive **the entire thesis book**
under a heading that claims it is a short list of items needing attention — a wrong
answer that looks right. An empty pane is wrong but honest. Deletion is therefore not
the neutral option it appears to be, which is why the dead predicate is kept and
labelled in this diff and the choice of semantics is escalated instead.

## Verification performed by the reviewer

- Grepped the writer side for `needs_resolution`: absent from
  `portfolio_materialize.py:212-232`, `portfolio/writers/thesis_io.py:100-153`, and
  `research/supabase_io.py:710-716`.
- Schema: created at `migrations/001_initial_schema.sql:58`, altered by `002`, `003`,
  `025_thesis_daily_fields.sql`, `056_thesis_topic_identity.sql` — none declares
  `needs_resolution`.
- Ran the mutation matrix below by hand.
- Confirmed no lint config governs `apps/dashboard-api`, that the `ARCHITECTURE.md` rule
  does not apply (no behaviour change, no such file), and that nothing else in the
  repo referenced the removed fixture data.

| Mutation | Result |
| --- | --- |
| `const filtered = rows.rows` (filter deleted) | red |
| predicate repointed to `r.status === "CHALLENGED"` | red |
| predicate repointed to `r.confidence > 0.9` (false for both rows) | **green** — the overclaim in finding 1 |
| `mockFetch(() => [])` (read broken) | red on the *control* assertion, not on the empty-shape one |

The last row is the important one: it proves the test cannot pass for the wrong
reason. A broken read fails the `/theses` control before the signals assertion is
reached.

## Author's follow-up verification

The reviewer could not run `tsc --noEmit`: `@cloudflare/workers-types` is absent from
the shared `node_modules` this worktree borrows from the main checkout, so the check is
unavailable in this environment. Pre-existing environment gap, not a defect in this
diff, and not counted as review coverage.

Suite after `015f6816f`: **326 passed / 326, 29 files** (`vitest run` in
`apps/dashboard-api`). `portfolio.ts` is byte-identical to what the reviewer read —
`015f6816f` touches only the test and the two docs.

Live core confirmed independently twice this session: project `rwagjbkvxkdwqmouagad`
returns `ERROR: 42703: column "needs_resolution" does not exist` for
`select needs_resolution, count(*) from theses group by 1`.

## Nit resolutions

| Nit | Action |
| --- | --- |
| 1 — overstated claim | Scoped the commit message to what is pinned; renamed the test; documented the mocked-read limit in-code. |
| 2 — fiction documented as live | BLOCKS.md no longer instructs building the query param; CONTRACT.md carries the caveat plus the rendering rule. |

## Residual risk / follow-ups

- **The decision is still open, and this diff deliberately does not make it.** Card
  `06f90af8` (`request_item_verdicts`, `wake_assignee`) offers four options:
  `status-derived`, `confidence-derived`, `new-column`, `declare-empty`. Whichever the
  board picks, the follow-up is mechanical and the two-line replacement point is
  already marked in `portfolio.ts`.
- **`declare-empty` is cheaper than it looks and safer than it feels.** Because the
  block is labelled "Signals to resolve", it must also *say* the pane is not collected;
  removing the filter alone would light up the whole book.
- **A schema-drift guard test was considered and deliberately deferred.** A test that
  asserts every `.filter(` predicate in the route reads a declared `theses` column
  would have caught this at authoring time. It needs a machine-readable column list to
  compare against, which does not exist yet. Worth raising as its own issue rather than
  bundling into a no-behaviour-change diff.
- **`confidence`-derived signals have a silent blind spot:** 810 of 2635 rows have
  `confidence IS NULL`, 764 of them `ACTIVE`. Any threshold rule needs explicit null
  semantics or it quietly drops three hundred active theses.