# digiquant app (`/app`) client-grade visual review — shared notes

Ticket: DIG-3320. Scope: REVIEW ONLY — no fixes here. Others: append entries
below using the same finding format. Do not edit other authors' rows; add new
rows with your initials and date.

- Target: local app http://localhost:4020/app/ (Brief desk, `apps/digiquant-web`,
  served via `scripts/preview_surfaces.sh`: `next dev -p 4020` in
  `apps/digiquant-web`, data API proxied at `/official-api/*`).
- Build under review: worktree at develop `e2cfea9cf8` (13 Oct 2026). No code
  changes on this branch except this notes file + screenshots.
- Passes: brief (`/app/`), portfolio (`/app/portfolio/`), pipeline
  (`/app/pipeline/`), strategies (`/app/strategies/`), each snapshotted settled
  (after `loading…` resolves) via browser a11y snapshot + full-page screenshot.
  Sub-pages (`/portfolio/holdings|attribution|ledger|tearsheet|theses`,
  `/strategies/detail|deploy`, `/tools/*`, `/settings`) NOT yet passed — open
  for a follow-up run.

## Historical replay setup

- Most recent fully healthy pipeline day: **run 2026-09-28** — `status ok`,
  `ok 13 / carried 13 / failed 0`, `type delta`, config `deepseek-v4-flash`
  (seen in the brief "Run health" box and the pipeline "Run health" box).
- How to switch the historical replay on: **there is no replay switch.** Measured
  in source: `components/desk/read-block.ts` `readOfficial(route, kind)` fetches
  `${officialApiBase()}${route}` with no date/`as_of` parameter, and every desk
  page (`brief.tsx`, `portfolio.tsx`, `pipeline.tsx`, `strategies.tsx`) calls it
  with fixed routes. No env var, query param, or flag selects a run date. The
  review therefore ran against **live reads** (mixed dates, see R-02). A real
  replay (pin every block to one run date) is itself a fix item (R-01).
- Data freshness at review time (13 Oct 2026 evening): book reads `as of
  2026-09-28` (11 trading days old), live marks `quote 2026-10-09`, NAV tip
  `2026-10-12`, run narrative `2026-08-28` (37 trading days old).

## Finding format

Each entry: page · element · category · severity (blocker/major/minor/nit) ·
screenshot · suggested fix.

## Findings — cross-page

- R-01 · all pages · historical replay · behavior · major ·
  `screenshots/docs-review-brief.png` · Suggested fix: add a run-date pin
  (e.g. `?run=` query param or desk-level date selector) threaded through
  `readOfficial` so every block on the page reads one run; default to the most
  recent healthy run. Until then every page mixes dates (see B-03, L-02).
- R-02 · all pages · per-box stale/warn footers · UI/design · major ·
  `screenshots/docs-review-brief.png`, `docs-review-pipeline.png` · Suggested
  fix (per Chris concern 1): replace every per-box `N trading days old · stale`
  footer with ONE compact page-level indicator at the top right
  (`stale · Nd`, worst box wins, tooltip lists per-box ages). Brief shows 4
  stale + 1 warn footers; pipeline shows 5 stale footers; strategies 1 warn.
- R-03 · all pages · `loading…` per-box skeleton · loading · minor ·
  `screenshots/docs-review-portfolio.png` (loading) vs
  `docs-review-portfolio-settled.png` (settled) · Suggested fix: keep, but add
  a page-level loading state so the page does not read as broken for ~4 s;
  portfolio boxes resolve at visibly different times (envelope renders stub
  sentence first, siblings stream in later).
- R-04 · all pages · sidebar nav · UI · minor · all screenshots · Suggested
  fix: nothing broken, but `[wip]`/`[soon]` tags on strategies/tools routes are
  developer status leaking into a client surface; gate the links by entitlement
  or move them under a single "Preview" section.

## Findings — brief (`/app/`)

- B-01 · brief · "Brief · scoreboard" box · data alignment/empty box · major ·
  `screenshots/docs-review-brief.png` · Box body is one sentence: "The official
  API returned a stub envelope, not a house-book read." A whole tile carrying a
  plumbing error string is not client-grade. Suggested fix: collapse stub boxes
  to a one-line notice row, or hide the tile and surface the count in the
  page-level indicator (R-02).
- B-02 · brief · "Live marks · snapshot" header stats · data alignment · minor
  · `screenshots/docs-review-brief.png` · `marks market_api quote 2026-10-09 vs
  mark 0.00% day 0.00% since -0.63% excess -5.64% overlay false`. Two 0.00%
  values side by side with no labels distinguishing them; `overlay false` is
  raw API vocabulary. Suggested fix: label each figure (vs-mark/day/since/
  excess) and drop internal flags from the header line.
- B-03 · brief · mixed as-of dates on one page · data alignment · major ·
  `screenshots/docs-review-brief.png` · Live marks `2026-10-09` beside Decision/
  Signals/Run-health `2026-09-28` (11 trading days old) and Book movers
  `2026-10-12` (1 day old). One page reads three different "nows". Suggested
  fix: R-01 (single run-date pin); until then, order boxes by date or badge the
  odd one out.
- B-04 · brief · "Decision" box · behavior/text-only · minor ·
  `screenshots/docs-review-brief.png` · 11-day-old hold thesis truncated mid-word
  (`macroeco…`) with no expand affordance visible in the snapshot. Suggested
  fix: clamp with a real "Read more" expander; never truncate mid-word.
- B-05 · brief · "Signals to resolve" table · design/text-only · major ·
  `screenshots/docs-review-brief.png` · Seven full-sentence thesis titles as raw
  text rows (`+2 cols · +13 rows`); no severity/direction badge, no sparkline —
  a text dump where a visualization belongs (Chris concern 7). Suggested fix:
  one row per signal with side badge + 1-line summary + expand.
- B-06 · brief · "What could break the view" box · empty box · major ·
  `screenshots/docs-review-brief.png` · Body is "This read returned no values."
  (Chris concern 6). Suggested fix: when a read is legitimately empty, render
  "No break risks flagged for this run" + the run date, or hide the tile.
- B-07 · brief · "Book · movers" DAY column · data alignment · minor ·
  `screenshots/docs-review-brief.png` · Every row `DAY —` while UNREALIZED
  carries values (+1.88% … +18.80%). A whole column of em-dashes. Suggested
  fix: drop the DAY column until the feed provides it, or fill it.
- B-08 · brief · "Run health" internals · UI · nit ·
  `screenshots/docs-review-brief.png` · `config deepseek-v4-flash`, `ok 13
  carried 13 failed 0` — model id and pipeline counters are operator detail on
  a client page. Suggested fix: keep status + date, move model/counters to a
  tooltip or the pipeline page.

## Findings — portfolio (`/app/portfolio/`)

- P-01 · portfolio · "Portfolio · envelope" box · data alignment/empty box ·
  blocker · `screenshots/docs-review-portfolio-settled.png` · Top tile renders
  the stub sentence ("…stub envelope, not a house-book read") while sibling
  tiles below render real stored data. Measured payload cause: `/portfolio`
  returns `book_as_of 2026-09-28` + `nav_tip 2026-10-12` with
  `contract: legacy_estimate` in one envelope — book and NAV disagree by 14
  days inside a single response. Suggested fix: split the envelope (book read
  vs NAV read) so one stale half cannot blank the whole tile; never let the
  lead tile be the empty one.
- P-02 · portfolio · "Exposure · sleeve" + "Book · movers" · duplicated
  information · major · `screenshots/docs-review-portfolio-settled.png` · Both
  tiles source `core:positions+instruments` on the same page (Chris concern 3).
  Suggested fix: merge into one positions tile or differentiate (sleeve
  aggregates vs position movers).
- P-03 · portfolio · weight decimals · design · minor ·
  `screenshots/docs-review-portfolio-settled.png` (API: `weight_pct 29.9733`,
  `nav 101.392684`) · 4–6 decimals on weights/NAV. Suggested fix (Chris
  concern 5): 2 decimals for %, 2 for NAV on client tiles (full precision in
  tooltip/export only).
- P-04 · portfolio · NAV series / drawdown charts · design · minor · NOT
  VERIFIED this pass — boxes were still resolving at snapshot time. Suggested
  fix: follow-up pass must check Chris concern 4 (charts fill containers) on
  `/portfolio/`, `/portfolio/tearsheet`, `/portfolio/performance`.

## Findings — pipeline (`/app/pipeline/`)

- L-01 · pipeline · per-box stale footers · UI · major (same as R-02) ·
  `screenshots/docs-review-pipeline.png` · Five `11 trading days old · stale`
  footers plus a `37 trading days old · stale` outlier. See R-02.
- L-02 · pipeline · "Run narrative: Atlas Daily Digest 2026-08-28" · data
  alignment · major · `screenshots/docs-review-pipeline.png` · Narrative is
  dated 2026-08-28 (37 trading days old) while the run it narrates is
  2026-09-28. A narrative five weeks older than its run. Suggested fix: pin
  narrative to the run date (R-01) or badge it as last-available.
- L-03 · pipeline · "Artifact ledger" STAGE column · duplicated information ·
  minor · `screenshots/docs-review-pipeline.png` · All 7 visible rows read
  `delta`. A column with one value is not a column. Suggested fix: drop the
  column or show stage variety (collect/research/decide/publish).
- L-04 · pipeline · "Graph · nodes" TO column · data alignment · minor ·
  `screenshots/docs-review-pipeline.png` · Every row `TO —`. Same shape as
  B-07. Suggested fix: drop or fill.
- L-05 · pipeline · "Call trace" CALLS column + durations · data alignment ·
  minor · `screenshots/docs-review-pipeline.png` · CALLS all `—`; durations mix
  `1.07 / 59.53 / 0 / 1.05 / 1.11 / 104.97 / 0` (bare `0` with no unit).
  Suggested fix: drop CALLS until instrumented; render `0` as `0.00 s` or `—`
  consistently.
- L-06 · pipeline · "Node document: Commit Run 2026-09-28" · behavior · nit ·
  `screenshots/docs-review-pipeline.png` · Title-only tile; unclear whether it
  opens. Suggested fix: make the open affordance explicit (`[enter] open`
  hint exists on Run health only).

## Findings — strategies (`/app/strategies/`)

- S-01 · strategies · "My deployments: No deployments yet." · empty box ·
  major · `screenshots/docs-review-strategies.png` · A full tile for an empty
  state on a client page. Suggested fix: replace with a one-line empty state +
  CTA ("Browse the catalog"), or hide until a first deployment exists.
- S-02 · strategies · summary "soon Deploy is not built yet." · text-only ·
  minor · `screenshots/docs-review-strategies.png` · Status prose (`catalog 4 /
  deployable 4 / last run 2026-10-09`) ends in a `soon` sentence. Suggested
  fix: keep the numbers, drop the prose tail or make it a badge.
- S-03 · strategies · Catalog table · design · nit ·
  `screenshots/docs-review-strategies.png` · Columns ID/STRATEGY/FAMILY/
  UNIVERSE/CADENCE/TARGETS/STATUS/DEPLOY read well; CADENCE shows `—` for
  `BTC-SDCA` (only row sampled). Suggested fix: sample all 4 rows next pass;
  fill or drop CADENCE if systematically empty.

## Prioritized fix list (for ticket handoff; fixes go to follow-ups, NOT this ticket)

1. P-01 envelope split (blocker — lead tile empty while data exists below).
2. R-01 single run-date pin (unblocks honest "as of" everywhere; precondition
   for B-03, L-02).
3. R-02 page-level stale indicator (Chris concern 1; retires ~10 repeated
   footers).
4. B-01/B-06/S-01 stub/empty tiles → one-line notices (concerns 6).
5. B-05 signal rows → badged rows, not a text dump (concern 7).
6. P-02 merge the duplicated positions tiles (concern 3).
7. P-03/L-05 decimal + unit trim (concern 5).
8. B-07/L-04/L-03/B-02 dead columns + raw vocabulary (concerns 2, 3).
9. Follow-up pass: sub-pages + P-04 chart-fill check (concern 4) + full
   strategies catalog sample.

## Pass log

- 13 Oct 2026 evening (Code Reviewer): passes 1–2 over brief/portfolio/
  pipeline/strategies, settled snapshots, screenshots in `screenshots/`.
  Open: sub-pages, chart-fill verification, keyboard/route/loading/animation
  sweep (press `?`, `d`, `[enter]/[tab]` affordances), second reviewer pass.
- 13 Oct 2026 (board routing, Chris): implementation follow-ups owned outside
  this ticket — DIG-3322 (tools routes + financial digichat), DIG-3323
  (functional settings). The tools/settings observations in this file (R-04
  and the open follow-up pass) route to those tickets after consolidation;
  this ticket stays review-only and takes no fix.
