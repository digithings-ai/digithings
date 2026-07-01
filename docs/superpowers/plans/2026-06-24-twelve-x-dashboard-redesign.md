# Twelve-X Dashboard Redesign — Implementation Plan

> **For agentic workers:** the **visual + behavioral spec is the frozen demo** at
> `docs/superpowers/specs/2026-06-24-twelve-x-redesign-visual-spec.html` (open it; every
> component's exact look, interaction, and math is there). This plan maps that demo onto the
> real Next.js components. Use **TDD**. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rework the Olympus twelve-x dashboard (Today, Consensus, Intelligence, Events, Matrix; remove Ledger) to the demo-validated design: a "Consensus average" chart, a rich Consensus data table, a 3-tier Intelligence "why" panel, multi-view Events with a horizontal Gantt timeline, and Today as a balanced single screen.

**Architecture:** Pure data derivations in a new `lib/twelve-x/consensus-derive.ts`; three reusable presentational components (`ConsensusScoreBars`, `EventsTimeline`, and the consensus chart) built first as standalone tested units, then integrated surface-by-surface. No backend changes (the consensus-history backfill is already done in the twelve-x producer; Olympus only reads).

**Tech Stack:** Next.js 16 App Router (`output: 'export'`, `basePath:'/olympus'`), React 19 client components, Tailwind v4 (CSS-first `@theme`, stock breakpoints), lucide-react, recharts (already a dep), Vitest 4 (`node` env, **no jsdom/RTL** — `react-dom/server` `renderToStaticMarkup`).

## Global Constraints

- **Naming:** the smoothed consensus is **"Consensus average"** — never "5-day moving average"/"MA" in user-facing copy. Window = **last 5 runs** (run-based, not calendar), implicit.
- **Consensus score** is `[-2,+2]` (`fx_consensus_snapshot.score`, `timeframe='medium'`, `weighted=true`). Divergent bar: zero-center, `width = min(1,|score|/2)*50%` of a half-track, green-right (bull) / red-left (bear). Bands: `|s|>=1.25` strong, `>=0.35` lean (`STRONG_BAND=1.25`, `LEAN_BAND=0.35`, `SCORE_MAX=2`).
- **Tests:** Vitest `node` env, `renderToStaticMarkup` only (pattern: `components/overview/as-of-badge.test.tsx`). Pure helpers unit-tested directly.
- **Gates per PR:** `next build` green, `tsc` + `eslint` clean (twelve-x + shell), full vitest green, `make score` ≥ thresholds (Sec ≥8, Quality ≥8, Opt ≥7, Acc ≥9).
- **Each phase = its own `task/<N>-slug` branch → PR into develop**, `Fixes #<phase-issue>` in the body.

## Known carry-over bug (fix in Phase 4)

- **Timeline body overlap:** lane-packing prevents *time* overlaps, but a card whose label is wider than its duration-derived width can visually overrun its slot. Fix in `EventsTimeline`: clamp card width to `max(durationWidth, labelMinWidth)` AND truncate/ellipsize the label to the card width so the body never exceeds the card box; re-pack lanes using the *rendered* width (max of duration and min) so neighbours don't collide.

## File map

**Create:**
- `lib/twelve-x/consensus-derive.ts` — pure consensus-average derivations (+ test)
- `lib/twelve-x/consensus-bar.ts` — extracted bar constants/helpers (SCORE_MAX, bands, `scoreColorClass`, `scoreLabel`, `currencyColor`) (+ test)
- `components/twelve-x/ConsensusScoreBars.tsx` — shared divergent bar + multi-marker variant (+ test)
- `components/twelve-x/EventsTimeline.tsx` — reusable horizontal Gantt timeline (+ test)
- `components/twelve-x/TodayConsensusChart.tsx` — "Consensus average" chart + legend + Proposed/Current toggle (+ test)
- `components/twelve-x/ConsensusDataTable.tsx` — rich sortable table, selectable avg window, vs-avg flag, filters (+ test)
- `components/twelve-x/IntelligenceWhyPanel.tsx` — 3-tier why drill-down (+ test)
- `components/twelve-x/EventsCalendar.tsx` — month-grid calendar view (+ test)

**Modify:** `lib/twelve-x/types.ts`, `lib/twelve-x/fetch.ts`, `components/twelve-x/{TodayTab,ConsensusTab,IntelligenceTab,EventsTab,BriefPanel,TwelveXClient}.tsx`.
**Remove:** `components/twelve-x/LedgerTab.tsx` (+ its nav/route; provenance folds into Intelligence Tier 3).
**Keep:** `MoversStrip.tsx`, `DeltaChip.tsx` (still used by ConsensusTab; only the Today usage of MoversStrip is dropped).

---

## Phase 1 (PR1) — Foundation: derivations + reusable bars + timeline

Builds **new files only** (no edits to shared files) → low-risk, internally parallelizable.

### Task 1.1 — `consensus-derive.ts`
**Produces:**
- `consensusAverageAt(series: {score:number}[], i: number, window=5): number|null` — mean of `series[max(0,i-window+1)..i].score`; `null` if `i<0`. (Matches demo `maAt`.)
- `consensusAverageSeries(series, window=5): (number|null)[]`
- `latestConsensusAverages(series): { avgNow, actualNow, avgYesterday, avgAgo, momentum }` per currency — `avgNow=avgAt(last)`, `actualNow=series[last].score`, `avgYesterday=avgAt(last-1)`, `avgAgo=avgAt(last-5)`, `momentum=actualNow-avgNow`.
- [ ] **Test (write first, run red):** `consensusAverageAt` over `<5`-length series (partial mean), exactly 5, skipped indices, `i<0`→null; non-finite score handling; `momentum` sign. → **Implement** → green → commit.

### Task 1.2 — `consensus-bar.ts` (extract from ConsensusTab:21-57)
**Produces:** `SCORE_MAX=2`, `STRONG_BAND=1.25`, `LEAN_BAND=0.35`, `scoreColorClass(s)`, `scoreLabel(s)`, `currencyColor(ccy)`, `barFillPct(s)= min(1,|s|/2)*50`, `tickPct(v)=50+clamp(v,-2,2)/2*50`.
- [ ] Test band boundaries (1.25, 0.35, sign), `barFillPct`/`tickPct` math → implement → commit.

### Task 1.3 — `ConsensusScoreBars.tsx`
**Consumes:** `consensus-bar.ts`. **Produces:** `<ConsensusScoreBar value markers? />` where `markers: {value:number; kind:'actual'|'prior'|'ago'|'baseline'; label:string}[]`; renders the zero-center divergent track + fill + legend-coded ticks (demo `divergentBarMulti` / `.dbar-*` recipe). Single-value mode (no markers) = the plain bar used by the table/intelligence.
- [ ] Test (`renderToStaticMarkup`): bull→`bull` fill class & width; bear→`bear`; markers render at `tickPct` positions with kind classes; no markers → just the bar.

### Task 1.4 — `EventsTimeline.tsx`
**Produces:** `<EventsTimeline events mode='single'|'multi' day? />`. Horizontal Gantt: cards at start time, width `=pxPerHour*durationHours` **clamped to a label-min**, greedy lane-packing on *rendered* width, taller lanes (~46px), single-day fit-to-width / multi-day scroll + Day|Hour scale. **Fixes the body-overlap bug** (see Known bug). Inline SVG/CSS axis.
- [ ] Test pure lane-packer (overlapping intervals → distinct lanes; clamped width feeds packing) and `dayWindow`/position math.

**Gate PR1:** build/tsc/eslint/vitest/score. PR title `feat(olympus): twelve-x consensus-average derivations + reusable score-bars & timeline`.

---

## Phase 2 (PR2) — Today page

### Task 2.1 — `TodayConsensusChart.tsx`
**Consumes:** `consensus-derive`, `ConsensusScoreBars`. **Produces:** `<TodayConsensusChart series />` — title "Consensus average"; per-G10 row = `<ConsensusScoreBar value={avgNow} markers=[actual,yesterday,ago] />` + value + momentum ▲/▼; legend (avg bar / today's actual / yesterday's avg / 5-days-ago avg / ▲▼ = actual-vs-average); `Proposed | Current` toggle (Current = the old movers cards). Empty-state guard. Demo §"Consensus average".
- [ ] Test: renders 10 rows, legend keys present, title, Proposed default; markers present.

### Task 2.2 — `TodayTab.tsx` layout
Co-lead row (Trade ideas + Digest) → `today-mid` 2-col (TodayConsensusChart ~1.5fr + Broker briefs ~1fr, `align-items:stretch`, briefs `flex:1; overflow-y:auto`) → full-width `<EventsTimeline mode='single' day={today}>` section. Remove the old MoversStrip usage + compact events tile.
- [ ] Test: TodayConsensusChart + briefs list + EventsTimeline present; no MoversStrip; consensus & briefs columns height-matched markup.
**Gate + PR** `Fixes #<p2>`.

---

## Phase 3 (PR3) — Consensus page

### Task 3.1 — `ConsensusDataTable.tsx`
Sortable G10 table: Ccy | `<ConsensusScoreBar>` | Consensus | Δ prior | **Avg (selectable window 3/5/10/20, recomputed live)** | **vs Avg (▲/▼ above/below)** | Conf% | Agree% | Signal. Filter chips (All/Bullish/Bearish/Strong). Sort via clickable headers. Demo §Consensus Table.
- [ ] Test: pure `sortRows`/`avgWindow`/`vsAvg` helpers; renders headers + rows; window change recomputes Avg.

### Task 3.2 — `ConsensusTab.tsx` reorg
`Table | Charts` sub-nav (Table default). Table = ConsensusDataTable. Charts = score-over-time line chart with **`Raw | Average`** toggle (Average = `consensusAverageSeries`) + position-split, side-by-side ≥1024px. Refactor bottom bars → `ConsensusScoreBars`. Remove the old standalone latest-table.
- [ ] Test: sub-nav present, Table default; Average toggle swaps series; one table only.
**Gate + PR** `Fixes #<p3>`.

---

## Phase 4 (PR4) — Events page (+ timeline bug fix)

### Task 4.1 — `EventsCalendar.tsx` (month grid, clickable days → day detail).
### Task 4.2 — `EventsTab.tsx`: `List | Timeline | Calendar` switcher (List grouped-by-day default, reuse existing grouping; Timeline = `<EventsTimeline mode='multi'>`; Calendar = EventsCalendar). Surface `prior` next to Fcst/Act (already fetched; add to select if missing in `getUpcomingEvents`).
- [ ] Test: switcher present; List grouped-by-day; Timeline renders the Gantt; `prior` shown. Confirm the **body-overlap fix** from 1.4 holds (lane width ≥ label width, label truncates).
**Gate + PR** `Fixes #<p4>`.

---

## Phase 5 (PR5) — Intelligence 3-tier "why" panel

### Task 5.1 — `types.ts` + `fetch.ts`
**Produces:** `getIntelligenceWhy(runDate?)` joining (per run_date+currency): `fx_confluence_snapshot` (score + `components` jsonb: consensus_strength, event_alignment, recency, breadth, n_brokers, days_to_catalyst, timeframe) + matching `fx_consensus_snapshot` decomposition (score/confidence/agreement/tilt/n_eff/n_brokers/n_views/*_pct) + supporting desks from `fx_relevance_ledger` (broker, classification active|confirmed|invalidated|superseded, relevance, conviction, reason, evidence quote). Types in `types.ts`.
- [ ] Test the pure join/shape (mock rows → assembled `IntelligenceWhy`).

### Task 5.2 — `IntelligenceWhyPanel.tsx` + `IntelligenceTab.tsx`
Confluence cards → expand to **Tier 1** score waterfall (`0.50·consensus_strength + 0.30·event_alignment·recency + 0.20·breadth = score`), **Tier 2** consensus decomposition (`<ConsensusScoreBar>` + conf/agree/tilt + bull/neutral/watch/bear split bar), **Tier 3** supporting desks (classification badge + relevance + reason + verbatim quote). One-liner labeled "synthesized — would require generation". **Caveat:** do NOT show w_time/w_event as independently meaningful (constant=1.0). Demo §Intelligence.
- [ ] Test: tiers render; waterfall weights 0.50/0.30/0.20; classification badges; synthesized label present.
**Gate + PR** `Fixes #<p5>`.

---

## Phase 6 (PR6) — Matrix side-pane fix + Ledger removal

### Task 6.1 — `BriefPanel.tsx`: render `central_thesis` through `<SafeMarkdown>` (currently a raw `<p>` at ~line 165) so thesis formatting is consistent across brokers.
- [ ] Test: central_thesis goes through the markdown renderer (markup contains the prose container, not a bare `<p>` of raw text).
### Task 6.2 — Remove `LedgerTab.tsx`; drop its tab/route from `TwelveXClient.tsx`; final tab set = Today, Consensus, Intelligence, Matrix, Events. (Provenance already lives in Intelligence Tier 3 from Phase 5.)
- [ ] Test: tab set has no Ledger; the five tabs route correctly.
**Gate + PR** `Fixes #<p6>`.

---

## Sequencing

PR1 (new files) → PR2 (Today) ∥ PR3 (Consensus) ∥ PR4 (Events) can follow PR1 in parallel review *but* are built sequentially to avoid `TwelveXClient.tsx` conflicts → PR5 (Intelligence, adds fetchers) → PR6 (Matrix+Ledger, finalizes tab set). Each lands on develop before the next builds on it.
