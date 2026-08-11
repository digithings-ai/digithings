# Twelve-X "Today" — single-screen daily snapshot (design)

- **Date:** 2026-06-23
- **Status:** Approved design / spec (pre-implementation)
- **Surface:** Olympus FX Research suite, Today tab (`frontend/olympus/{app,components,lib}/twelve-x`)
- **Scope:** **Part A only** — the Today page content redesign (twelve-x frontend files only). Part B (shared subpage top-bar: full-width on wide screens + collapse-to-hamburger on mobile) is a **separate, coordinated** change and is explicitly out of scope here.

## 1. Goal

Make the Today tab a glanceable **daily snapshot** that answers, at a glance, five questions — each section a teaser with a "see more →" pass-through to its full tab:

1. What is today's **trade idea(s)**?
2. What does today's research say (**digest brief**)?
3. What **changed in consensus** today?
4. What **briefs** do we have today?
5. What **events** are today?

**Priority (not strict no-scroll):** the top three — trade ideas, digest brief, consensus delta — are guaranteed **above the fold**; the briefs slideshow and events timeline sit just below.

## 2. Layout — approach "A1"

Capped-width container (~`max-w-[1400px]`, centered; consistent with the existing `SUBPAGE_MAX` content width), two zones:

```
┌───────────────────────────────────────────────────────────┐
│ ① TRADE IDEAS (≈55%, focal+list)   │ ② DIGEST BRIEF (≈45%) │  ← above fold
├───────────────────────────────────────────────────────────┤
│ ③ WHAT CHANGED — consensus movers (full-width strip)       │  ← above fold
├───────────────────────────────────────────────────────────┤  · · · fold · · ·
│ ④ BRIEFS slideshow            │ ⑤ EVENTS — today timeline   │  ← just below
└───────────────────────────────────────────────────────────┘
```

**Responsive (in scope for Part A):** below the `lg` breakpoint the whole page collapses to a **single column in priority order 1 → 2 → 3 → 4 → 5**. The page top-bar/tab-bar responsiveness (full-width, hamburger) is **Part B** and not touched here.

## 3. Sections

### ① Today's trade ideas — focal + list
- **Source:** `fx_trade_ideas_snapshot` for the canonical run_date, ordered by `rank` ascending (1 = strongest). Count is **1…N** (today is 1; design must handle several).
- **Render:** `#1` as a **focal** card (title, pair, direction, central thesis, levels/targets, catalyst, contributing desks). `#2…N` as compact tappable rows below the focal card; each row opens that idea's full detail in the existing slide-over (`BriefPanel`-style).
- **Expand:** an inline **"expand ▾ → confluence reads"** control that reveals the broader directional set from `fx_confluence_snapshot` (the data Olympus shows today).
- **See more →** Intelligence tab.

### ② Digest brief — co-lead
- **Source:** `fx_daily_digest` (`summary`, `key_themes`).
- **Render:** the full summary, **always visible** (never collapsed), with key-theme chips beneath. Sits shoulder-to-shoulder with the trade ideas above the fold.
- **See more:** none — it is shown in full inline. (Theme chips may deep-link into the relevant tab where useful.)

### ③ What changed — consensus
- **Source:** day-over-day deltas computed by the existing pure helper `computeConsensusDeltaSet(series)` over `fx_consensus_snapshot` history (already implemented in `lib/twelve-x/fetch.ts`).
- **Render:** full-width compact strip of biggest movers via the existing `MoversStrip`/`DeltaChip` (e.g., `JPY ▲+0.94 · GBP ▼ · USD ▲`), sign-colored.
- **See more →** Consensus tab.

### ④ Briefs slideshow
- **Source:** `fx_research_history` for the canonical run_date (today's briefs).
- **Order:** `trader_relevance` (high → low), tiebreak by broker-mention count, then newest (`report_date`/`run_date`).
- **Render:** carousel, one brief card visible at a time (◀ ▶ controls + position dots). Each card opens that brief in the slide-over.
- **See more →** the new **Briefs index** (§3.⑥).

### ⑤ Events — today timeline
- **Source:** `fx_economic_calendar` filtered to **today** (local-date of the release instant), with `fx_events_snapshot` for the broker-mention overlay.
- **Render:** compact horizontal timeline, impact-colored (high/medium/low), times in the viewer's local zone (reuse the `eventLocalDateKey`/`hasResolvedTime` helpers already added).
- **See more →** Events tab.

### ⑥ Briefs index (new — slideshow "see more" target)
- A lightweight, full-width **list/grid of today's briefs** (broker, title, relevance, direction tags), each opening the brief slide-over.
- **Reached only via the slideshow "see more"** as a URL-stateful view (e.g., `?view=briefs`), **not a new top-level tab** — this keeps Part A self-contained and avoids adding tab-bar pressure that interacts with Part B. (It can later be promoted to a tab during Part B if desired.)

## 4. Data layer (new / changed)

In `lib/twelve-x/fetch.ts` (+ `types.ts`):

- `getTradeIdeas(runDate): Promise<FxTradeIdeaRow[]>` — reads `fx_trade_ideas_snapshot`, ordered by `rank`. **New row type `FxTradeIdeaRow`** (run_date, rank, title, pair, direction, thesis, catalyst, levels, citations, as_of).
- `getTodayBriefs(runDate): Promise<FxBriefRow[]>` — reads `fx_research_history` for the run_date; client sorts per §3.④ ordering.
- A **today-events selector** — reuse `getUpcomingEvents()` narrowed to today via `eventLocalDateKey`, or add `getTodayEvents(runDate)`.
- Reuse: `computeConsensusDeltaSet`, `getConsensusTimeSeries`, `getIntelligence` (confluence), `resolveCatalyst`, `getBrief`.

## 5. Components (twelve-x only — no shared-shell edits → no conflict risk)

- **`TodayTab.tsx`** — rewritten to the A1 layout.
- New: **`TradeIdeasPanel`** (focal + list + expand-to-confluence), **`DigestBrief`**, **`BriefsSlideshow`**, **`EventsMiniTimeline`**, **`BriefsIndex`** (the see-more view).
- Reuse: `MoversStrip`, `DeltaChip`, `BriefPanel`, `useTwelveX()` context (canonical `runDate`, `crossLink`, `openBrief`).
- `TwelveXClient.tsx` — pass today's data + wire the `?view=briefs` state for the Briefs index; **no tab-bar changes** (Part B).

## 6. Risks & decisions

- **`fx_trade_ideas_snapshot` anon-read (must verify):** Olympus does not currently read this table. To surface the curated ideas client-side it must carry an `anon_read` RLS policy (mirroring the other snapshot tables; created in migration 012). **Verify during planning.** If absent: either add the policy (twelve-x migration — separate change), or **fall back** to deriving the focal idea(s) from `fx_confluence_snapshot` so the page still works.
- **"No scroll"** is interpreted as **priority-above-the-fold** (option c), not strict; the bottom two sections may extend below.
- **Briefs index** is a see-more view, not a tab (decouples from Part B).

## 7. Non-goals (Part A)

- Part B: shared subpage top-bar full-width on wide screens + collapse-to-hamburger on mobile (separate coordinated change).
- Push alerting; global full-text search/export (previously deferred).

## 8. Testing

- Unit tests for the new fetchers/transforms: trade-idea ordering, today-briefs sort (relevance → mentions → newest), today-events filter, and the (existing, tested) consensus-delta helper.
- Render verification via the dev server at desktop (~1440) and mobile (~390) widths: above-the-fold priority holds on desktop; clean single-column stack on mobile; `next build` green; existing `lib/twelve-x` tests stay green.
