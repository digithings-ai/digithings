# DIG-441 — `/dossier/{ticker}` thesis + vehicle dating

- **Subject**: commit `8292347a3`, `fix(dashboard-api): age the dossier thesis and vehicles off the business date` (PR #5066)
- **Reviewer**: fresh-context `general` subagent, session `ses_ef723b4a8ffeMiS6CiF2i1z1sC` (did not write the code)
- **Verdict**: `CHANGES_REQUESTED` on first pass (1 blocking, all prose); `APPROVE` after the follow-up commit
- **Reviewed range**: `782e681ca..8292347a3` plus the follow-up commit
- **Author**: Platform (`d80f78b8-9685-48c6-b9d2-665ecdffa6d3`)

## What was reviewed

`dossier()` in `apps/dashboard-api/src/routes/portfolio.ts` (the `GET /dossier/{ticker}` handler) and
four new tests in `apps/dashboard-api/src/routes/portfolio.test.ts`.

The defect: the handler read `theses` with `select=*&limit=500` — no `order`, no date filter — and
`.find()`-ed the first match, so it could resolve a thesis from a stale date. `vehicleIds` was built
from `thesis_id` but matched against `str(r.id) ?? str(r.thesis_id)`, where `id` is a `uuid`, so the
vehicle set never matched. Vehicles were never narrowed to a date.

The fix applies the idiom the sibling panes already use (`/theses` at `portfolio.ts:173-186`,
`/rates/theses` at `fx.ts:378-399`): `order=date.desc` on both reads, `maxThesisDate` to find the
tip, `rowsAtDate` to hold theses and vehicles at that one date, join on `thesis_id`. The response
body and `as_of` are unchanged.

The reviewer was asked for five things: correctness against both siblings and any path left
unconstrained; truthfulness of every schema claim in the new docblock (a wrong or overstated claim
treated as blocking); whether each of the four tests goes red for its own defect or is inert; whether
the response contract moved and what the `DossierDrawer` consumer sees; and anything not asked.

## Findings

### Blocking

**B1 — `portfolio.ts:351`, a literally false schema claim.** The docblock opened "both tables carry
one row per `(date, thesis_id)`". That is true of `theses` and false of `thesis_vehicles`, whose
`PRIMARY KEY (date, thesis_id, ticker)` — quoted one clause later in the same sentence — allows
several rows per `(date, thesis_id)`.

Verified:

```
$ sed -n '58,69p' digiquant/supabase/migrations/001_initial_schema.sql   # UNIQUE(date, thesis_id)
$ sed -n '18,34p' digiquant/supabase/migrations/024_thesis_deliberation_first_class.sql
    31:   PRIMARY KEY (date, thesis_id, ticker),
```

This mattered beyond pedantry: vehicle multiplicity at one date is the reason `rowsAtDate` is
applied separately to each side and the reason `vehicleIds` is a `Set` of thesis ids. A maintainer
reading the head clause would conclude the vehicle read is one-to-one and simplify the `Set` away —
the exact regression the docblock exists to prevent.

**Fixed.** Reworded to state each table's own key, and noted why that makes the vehicle side a `Set`.

### Non-blocking

| # | Finding | Disposition |
|---|---|---|
| N1 | `theses` has **no** `ticker` column in any of the 135 migrations (the ticker-ish column is `vehicle`), so `str(r.ticker)` on a thesis row cannot fire against live data. The reviewer showed by probe that resolution therefore rides entirely on `thesis_vehicles`, and `thesis_io.py:236-238` swallows vehicle-upsert failures — so on such a day the drawer says "no thesis" while `theses.vehicle` reads the ticker. Pre-existing, not a regression. | Test comment corrected so it no longer implies a production ticker fallback. Behaviour change → follow-up. |
| N2 | `order=date.desc` was **entirely untested** — the mocks ignore the query string, so deleting the order from both reads left all 15 tests green, despite the order being the load-bearing part of the fix. | **Fixed** — added the URL assertion test. |
| N3 | `as_of` and `provenance.tip_date` still derive from `positions`, not the thesis `tip`, so the envelope does not surface the fix and understates payload freshness. Both siblings send `tip`. | Not changed — that would move the response contract, outside this ticket. Documented in the docblock. |
| N4 | `documents` is read as `select=*&limit=200` with no order or date filter, in the same function — the same defect class. `risks()` too. | Out of scope per the ticket. → follow-up. |
| N5 | "so the narrow is safe" overstates what the FK proves. The FK rules out cross-joining a vehicle to another date's thesis; it says nothing about vehicles *existing* at the tip. | **Fixed** — wording corrected and the best-effort caveat added. |
| N6 | The `updated_at` clause described duplication across dates, but aging by `updated_at` fails the *other* way: a no-op `UPDATE` on a stale-date row makes it look newest. | **Fixed** — rewording. |
| N7 | `/portfolio/theses` is not a route in this app; the route is `/theses`. `/portfolio/theses` is a digiquant-tui client page. | **Fixed** — renamed. |
| N8 | Migration citations were bare relative paths that do not resolve from `apps/dashboard-api/src/routes/`, and carried no line numbers. | **Fixed** — repo-relative paths plus line ranges. |
| N9 | "the route's entire subrequest budget" asserted an enforced ceiling that no document in the repo defines. The count is real; the constraint is invented. | **Fixed** — restated as a count, not a budget. |
| N10 | `limit=500`/`limit=2000` with `select=*` pull jsonb nobody reads. Pre-existing. | → follow-up. |
| N11 | No review artifact shipped with the commit. | This file. |

The reviewer found **no scope creep**: two files, no new dependencies, no new routes, no contract drift.

## Verification performed by the reviewer

Green baseline in a clean worktree: `vitest run` → 29 files / 330 tests; `tsc --noEmit` clean.

Red proof by swapping the pre-fix `portfolio.ts` (`git show 782e681ca:…`) into a throwaway
`/tmp` worktree. All four claimed actuals confirmed exactly:

| # | Test | Confirmed failure against pre-fix code |
|---|---|---|
| 1 | newest date, not arbitrary | `{id:"uuid-gold-stale", name:"Gold", state:"EXITED"}` — the true arbitrary-date symptom |
| 2 | join on `thesis_id`, not uuid `id` | `undefined` |
| 3 | vehicles at newest date | `["gold-bid-old","gold-bid"]` |
| 4 | no dated row withholds both | `["gold-bid"]` |

Orthogonality proven by targeted mutation rather than inspection: reverting **only** the join failed
tests 1 and 2 (3 and 4 passed); reverting **only** the date narrowing failed tests 1, 3 and 4 (2
passed); reverting **only** `order=date.desc` failed nothing. That last one is N2.

Schema census across the migrations, including an exhaustive sweep of every `ALTER TABLE theses`
(only 003 / 025 / 056, all adding columns, none adding `ticker`), the `thesis_vehicles` FK never
dropped by any migration, and an independent confirmation from a live `ON CONFLICT (date, thesis_id)`
in `056:86`.

Consumer check: the `ok(...)` payload keys and `as_of` are byte-identical pre/post;
`blocks-portfolio.tsx` is untouched and `type Dossier` still matches. On the pre-existing
"`vehicles` echoes thesis ids while the UI labels it `Vehicles`" nit: **identical in kind, better in
content, narrower** — still thesis slugs, but only the tip's rather than every date's.

The reviewer verified both worktrees were byte-clean at the end, and left its throwaway worktree in
place for inspection.

## Author's follow-up verification

Every finding was checked with a command before being actioned or refuted.

| Mutation | Expected | Observed |
|---|---|---|
| Strip `order=date.desc` from the two **dossier** reads | new test goes red | **1 failed / 15 passed**, failure precisely on `expect(theses).toContain("order=date.desc")` |
| Strip `order=date.desc` from the two **`/theses` sibling** reads | (accidental first attempt) | **16 passed** — the sibling's ordering is also untagged; DIG-401 territory |

Note the first row was initially run against the wrong pair of reads: the sibling and the dossier use
identical query strings, so a non-global substitution hit `/theses` first. Re-scoped to the
`dossier` function it behaved as intended.

`theses` having no `ticker` column (N1) was re-verified independently rather than taken on trust:

```
$ for f in $(grep -rl "ALTER TABLE theses" digiquant/supabase/migrations/); do \
    grep -n -A20 "ALTER TABLE theses" "$f" | grep -i ticker; done
   (no output — no migration adds it)
```

After the fixes: `vitest run` → **29 files, 331 tests passing**; `tsc --noEmit` → **exit 0**.

## Nit resolutions

| Nit | Action |
|---|---|
| B1 false schema claim | Fixed — each table's own key stated; `Set` rationale added |
| N1 misleading test comment | Fixed — comment now says no live row carries that column |
| N2 order untested | Fixed — test added and proven red under mutation |
| N3 `as_of` not the thesis tip | Documented, not changed — would move the contract |
| N4 `documents` undated | Out of scope — follow-up |
| N5 "the narrow is safe" overstated | Fixed — narrowed to what the FK proves, caveat added |
| N6 `updated_at` failure mode garbled | Fixed |
| N7 `/portfolio/theses` not a route | Fixed — `/theses` |
| N8 migration paths unresolvable | Fixed — repo-relative, with line ranges |
| N9 invented "subrequest budget" | Fixed — restated as a count |
| N10 row caps / `select=*` | Pre-existing — follow-up |
| N11 no review artifact | This file |

## Residual risk / follow-ups

1. **Vehicle writes are best-effort, so the tip date can have no mapping.** `thesis_io.py:236-238`
   logs and continues when the `thesis_vehicles` upsert fails, and `portfolio_materialize.py:182-183`
   states vehicle writes "never block the book". Where the tip-date mapping is missing, this fix now
   withholds the dossier thesis where it previously showed a stale one — a correctness improvement,
   but the drawer will read "no thesis for this ticker" on those days. Same class DIG-401 recorded.
2. **No live `theses.ticker`, so resolution rides `thesis_vehicles` entirely** (N1). The column that
   does carry the ticker is `vehicle`, and it is never read. Worth a ticket to decide whether the
   resolver should fall back to `str(r.vehicle)`.
3. **`documents` is still an unordered all-time slice** in the same function (N4). The ticket's
   justification for excluding it — that the other three reads "already pass an explicit filter and
   order" — is inaccurate for `documents`.
4. **`as_of` does not carry the thesis date** (N3), so the fix is invisible in the envelope.
5. **No CI workflow runs the dashboard-api suite.** `apps/dashboard-api` is its own npm workspace
   with its own `test` and `typecheck`, but the only `dashboard-api` reference in `.github/workflows/`
   is the path filter at `ci.yml:192`; `test-dashboard.yml` runs `--workspace dashboard`, whose vitest
   `include` never reaches it. Every green check on PR #5066 is therefore unrelated to these 331
   tests. Pre-existing; wants its own ticket.
6. **The sibling `/theses` route's `order=date.desc` is untested** — found by accident when a
   mutation hit it instead of the dossier reads and all 16 tests stayed green. DIG-401 territory.