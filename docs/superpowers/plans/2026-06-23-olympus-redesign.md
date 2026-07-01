# Olympus Dashboard Ground-Up Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconceive the Olympus dashboard for the portfolio-owner persona — lead with today's move, NAV underneath, progressive disclosure into the why — collapsing the surface to 4 destinations (Today / Portfolio / Why / System) + Settings on the existing tested data/render layer.

**Architecture:** Reuse the invisible plumbing (`useDashboard()` data contract, snapshot/markdown render, NAV/risk math, conviction scorecard) untouched. Recompose the panels that already work into a new IA and a strict move-led hierarchy. Most route consolidation rides on rails that already exist (a 4-item sidebar, query-param tabs, redirect stubs).

**Tech Stack:** Next.js 16 (`output: 'export'`, `basePath: '/olympus'`), React 19, Tailwind v4 (`@theme` tokens in `app/globals.css`), recharts, lucide-react, `@digithings/design`, `@supabase/supabase-js`, vitest.

**Spec:** `docs/superpowers/specs/2026-06-23-olympus-redesign-design.md`

## Global Constraints

- **Polars/pandas, Pydantic, ruff** rules do not apply here — this is the TypeScript frontend. Match existing code style; line length follows the repo's prettier/eslint config.
- **Tokens only, via `[data-theme]`** — colors come from the custom utilities (`text-fin-blue|green|red|amber`, `bg-bg-primary|secondary|glass`, `border-border-subtle|glow`, `text-text-primary|secondary|muted`, `.glass-card`) defined in `app/globals.css`. Never hardcode hex outside `globals.css`. Display face is Instrument Serif (`--font-display`); numbers are tabular mono.
- **Static export** — no server components with runtime data; everything is client-fetched via `useDashboard()`. No new server routes.
- **Tests** — vitest. Run from `frontend/olympus`: `npm test` (= `vitest run`). Tests live alongside source as `*.test.ts(x)` and render via `renderToStaticMarkup(createElement(Comp, props))` then assert with `toContain`. All currently-passing plumbing tests MUST stay green.
- **Nav labels (verbatim):** `Today`, `Portfolio`, `Why`, `System`, `Settings`. ("Why" is final; not "Research".)
- **Action verbs (verbatim, from `RebalanceAction.action`):** `OPEN`, `ADD`, `TRIM`, `EXIT`, `HOLD`. Direction coloring: OPEN/ADD → `--up`; TRIM/EXIT → `--down`; HOLD → muted.
- **Twelve-X** is cut from the Olympus owner nav (it already renders standalone via `app-frame.tsx`; just ensure nothing links to it).
- **Worktree:** `.claude/worktrees/olympus-redesign`, branch `feat/olympus-redesign`. All paths below are relative to repo root; edit the worktree copies.

## Setup (once, before Phase 1)

The worktree has no `node_modules`. Symlink the main checkout's:

```bash
ln -sfn /Users/chrisstefan/Code/digithings/frontend/olympus/node_modules \
  /Users/chrisstefan/Code/digithings/.claude/worktrees/olympus-redesign/frontend/olympus/node_modules
cd /Users/chrisstefan/Code/digithings/.claude/worktrees/olympus-redesign/frontend/olympus
npm test   # baseline — confirm the existing suite is green before changing anything
```
Expected: all existing tests pass (the "plumbing" baseline).

## File Structure

**New files:**
- `frontend/olympus/lib/nav.ts` — canonical 4-destination nav array (single source for sidebar + mobile bar).
- `frontend/olympus/lib/nav.test.ts` — asserts the owner spine.
- `frontend/olympus/components/today/move-hero.tsx` — the move-led hero (regime ribbon + THE MOVE + NAV status). Recomposes `TodayActionsPanel` + `AsOfBadge`.
- `frontend/olympus/components/today/move-hero.test.tsx`
- `frontend/olympus/components/today/why-today.tsx` — inline level-2 disclosure (deliberation net-stance + PM memo summary + "full debate →").
- `frontend/olympus/components/today/today-summaries.tsx` — the four quiet doorway cards (How I'm doing · The read · Holdings · Theses).
- `frontend/olympus/app/why/page.tsx`, `frontend/olympus/app/system/page.tsx` — new destinations.

**Modified files:**
- `frontend/olympus/components/sidebar.tsx` — consume `lib/nav.ts`; visually demote System.
- `frontend/olympus/components/mobile-app-bar.tsx` — consume `lib/nav.ts`.
- `frontend/olympus/app/page.tsx` — rebuilt Today (hero + 4 summaries; remove page-ambient wash and the 11-panel stack).
- `frontend/olympus/app/portfolio/*` — tabs → Holdings · Theses · Performance; conviction scorecard moves into Performance.
- `frontend/olympus/app/research/page.tsx` → becomes redirect to `/why`; reasoning moves to `app/why/`.
- `frontend/olympus/app/observability/page.tsx` → becomes redirect to `/system`; ops content moves to `app/system/` (Run health + How Olympus works), scorecard removed.
- `frontend/olympus/app/architecture/page.tsx` — content folds into System's "How Olympus works" (keep the P0 rewrite).
- Page-level tests for each touched route.

**Untouched (tested plumbing — do not edit):** `lib/dashboard-context.tsx`, `lib/queries.ts`, `lib/supabase.ts`, `lib/snapshot-*.ts`, `lib/render-*.ts`, `lib/decision-scorecard.ts`, `lib/portfolio-risk-metrics.ts`, `lib/performance-series.ts`, `lib/position-*.ts`, `lib/portfolio-aggregates.ts`, `lib/thesis-*.ts`, `components/SafeMarkdown.tsx`, `components/ui.tsx`.

---

## Phase 1 — Nav shell & IA remap

**Outcome:** A navigable 4-destination skeleton (Today / Portfolio / Why / System), System visually demoted, mobile bar in parity, old routes redirecting. Independently shippable.

### Task 1.1: Canonical nav module

**Files:**
- Create: `frontend/olympus/lib/nav.ts`
- Test: `frontend/olympus/lib/nav.test.ts`

**Interfaces:**
- Produces: `export interface NavItem { href: string; label: string; icon: ElementType<{ size?: number }>; demoted?: boolean }` and `export const NAV: NavItem[]`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/olympus/lib/nav.test.ts
import { describe, it, expect } from 'vitest';
import { NAV } from './nav';

describe('NAV', () => {
  it('is the 4-destination owner spine, in order', () => {
    expect(NAV.map((n) => n.href)).toEqual(['/', '/portfolio', '/why', '/system']);
    expect(NAV.map((n) => n.label)).toEqual(['Today', 'Portfolio', 'Why', 'System']);
  });

  it('demotes only System', () => {
    expect(NAV.filter((n) => n.demoted).map((n) => n.href)).toEqual(['/system']);
  });

  it('gives every item an icon', () => {
    expect(NAV.every((n) => typeof n.icon === 'function' || typeof n.icon === 'object')).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/olympus && npx vitest run lib/nav.test.ts`
Expected: FAIL — `Cannot find module './nav'`.

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/olympus/lib/nav.ts
import type { ElementType } from 'react';
import { LayoutDashboard, PieChart, BookOpen, Activity } from 'lucide-react';

export interface NavItem {
  href: string;
  label: string;
  icon: ElementType<{ size?: number }>;
  /** System is the demoted operator footnote — pinned bottom, muted. */
  demoted?: boolean;
}

/** The portfolio-owner spine: glance → why → full, four destinations. */
export const NAV: NavItem[] = [
  { href: '/', label: 'Today', icon: LayoutDashboard },
  { href: '/portfolio', label: 'Portfolio', icon: PieChart },
  { href: '/why', label: 'Why', icon: BookOpen },
  { href: '/system', label: 'System', icon: Activity, demoted: true },
];
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/olympus && npx vitest run lib/nav.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/olympus/lib/nav.ts frontend/olympus/lib/nav.test.ts
git commit -m "feat(olympus): canonical 4-destination nav module"
```

### Task 1.2: Sidebar consumes canonical nav + demotes System

**Files:**
- Modify: `frontend/olympus/components/sidebar.tsx` (replace the inline `NAV` at lines ~12–23 with an import from `lib/nav`)
- Test: `frontend/olympus/components/sidebar.test.tsx`

**Interfaces:**
- Consumes: `NAV` from `lib/nav.ts`.

- [ ] **Step 1: Write the failing test** — assert the sidebar renders all four labels and that System carries a demotion marker (e.g. a `data-demoted="true"` attribute / muted class). Use `renderToStaticMarkup`. Mock `next/navigation`'s `usePathname` to return `'/'`.

```tsx
// frontend/olympus/components/sidebar.test.tsx
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

import { Sidebar } from './sidebar';

describe('Sidebar', () => {
  it('renders the four owner destinations', () => {
    const html = renderToStaticMarkup(createElement(Sidebar));
    for (const label of ['Today', 'Portfolio', 'Why', 'System']) {
      expect(html).toContain(label);
    }
  });

  it('marks System as demoted', () => {
    const html = renderToStaticMarkup(createElement(Sidebar));
    expect(html).toMatch(/data-demoted="true"[^>]*>[^<]*|System/);
  });
});
```

- [ ] **Step 2: Run to verify it fails** (`npx vitest run components/sidebar.test.tsx`) — expect FAIL (labels "Why"/"System" not present yet; export name may differ — adjust the import to the real export discovered in the file).

- [ ] **Step 3: Implement** — delete the inline `NAV` literal; `import { NAV } from '@/lib/nav';`. In the render, when `item.demoted`, add `data-demoted="true"` and the muted/bottom-pinned classes (e.g. wrap demoted items in a bottom-aligned group with `text-text-muted`). Keep the existing active-link logic.

- [ ] **Step 4: Run to verify it passes.**

- [ ] **Step 5: Commit** — `feat(olympus): sidebar uses canonical nav; demote System`.

### Task 1.3: Mobile app bar consumes canonical nav

**Files:**
- Modify: `frontend/olympus/components/mobile-app-bar.tsx`
- Test: `frontend/olympus/components/mobile-app-bar.test.tsx`

- [ ] **Step 1:** Failing test — renders the four destinations (same pattern as 1.2, mocking `usePathname`).
- [ ] **Step 2:** Verify fails.
- [ ] **Step 3:** Replace its nav source with `import { NAV } from '@/lib/nav'`. Keep the bottom-bar layout; render all four (System included — on mobile it is a normal bottom-bar item, demotion is desktop-only).
- [ ] **Step 4:** Verify passes.
- [ ] **Step 5:** Commit — `feat(olympus): mobile bar uses canonical nav`.

### Task 1.4: New `/why` and `/system` destinations + back-compat redirects

**Files:**
- Create: `frontend/olympus/app/why/page.tsx`, `frontend/olympus/app/system/page.tsx`
- Modify: `frontend/olympus/app/research/page.tsx` → redirect to `/why`; `frontend/olympus/app/observability/page.tsx` → redirect to `/system`
- Modify: `frontend/olympus/app/library/page.tsx` redirect target → `/why` (currently `/research`)
- Test: `frontend/olympus/app/why/page.test.tsx`, `frontend/olympus/app/system/page.test.tsx`

**Interfaces:**
- For Phase 1, `/why` renders the existing research client and `/system` renders the existing observability content unchanged (their internal reorganization is Phases 4 & 5). This keeps the skeleton navigable end-to-end after Phase 1.

- [ ] **Step 1:** Inspect the existing redirect stubs (`app/performance/page.tsx`) to copy the exact redirect idiom used in this codebase (static-export-safe client redirect). Mirror it for `research`→`/why`, `observability`→`/system`, and retarget `library`→`/why`.
- [ ] **Step 2:** Create `app/why/page.tsx` rendering the current research client component; `app/system/page.tsx` rendering the current observability content. (Move, not duplicate, in Phases 4/5; for now import-and-render is fine.)
- [ ] **Step 3:** Tests assert each new page renders a recognizable heading and that the build's route manifest includes `/why` and `/system`.
- [ ] **Step 4:** `npm test` green.
- [ ] **Step 5:** Commit — `feat(olympus): add /why and /system; redirect old routes`.

### Task 1.5: Verify Twelve-X is unlinked + Phase-1 gate

- [ ] **Step 1:** Grep for links to `/twelve-x` outside `app/twelve-x/**` and `app-frame.tsx`: `rg "twelve-x" frontend/olympus --glob '!**/twelve-x/**'`. Expected: only `app-frame.tsx`'s standalone-route check. If any nav link exists, remove it.
- [ ] **Step 2:** Full suite + production build:
  ```bash
  cd frontend/olympus && npm test && npm run build
  ```
  Expected: tests green; `next build` static-export succeeds; `/why` and `/system` in output, old routes emit redirects.
- [ ] **Step 3:** Commit any cleanup — `chore(olympus): confirm twelve-x unlinked from owner nav`.

---

## Phase 2 — Today (the move-led hero)

**Outcome:** `app/page.tsx` becomes one hero + four quiet summaries; the 11-panel stack and full-page regime wash are gone. Highest-value phase.

> Component APIs (verified): `TodayActionsPanel({ actions: RebalanceAction[]; rationaleByTicker?: Record<string,string> })` already renders empty ("No rebalance proposed"), all-HOLD ("No changes proposed" / "N positions held"), and change rows with `+Npp` deltas and EXIT-before-ADD ordering. `AsOfBadge({ date })`. `DeliberationsStrip({ transcripts, riskDebate })`. `MorningBriefPanel()` (no props). `HeldTickerPricesPanel({ positions })`. Data via `useDashboard()`.

### Task 2.1: `MoveHero` — regime ribbon + THE MOVE + NAV status

**Files:**
- Create: `frontend/olympus/components/today/move-hero.tsx`
- Test: `frontend/olympus/components/today/move-hero.test.tsx`

**Interfaces:**
- Produces: `export function MoveHero(props: { regime: string; regimeLabel: string; asOf: string | null; runType: string | null; actions: RebalanceAction[]; rationaleByTicker?: Record<string,string>; nav: { index: number | null; dailyPct: number | null; benchTicker: string | null; excessPct: number | null; sinceDate: string | null } }): JSX.Element`
- Consumes: `TodayActionsPanel`, `AsOfBadge`, `formatPct`/`pnlColor` from `components/ui`.

- [ ] **Step 1: Write the failing test** (assertions, real):

```tsx
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { MoveHero } from './move-hero';

const navOk = { index: 104.2, dailyPct: 0.3, benchTicker: 'SPY', excessPct: 4.2, sinceDate: '2026-04-12' };

describe('MoveHero', () => {
  it('leads with the move on an action day', () => {
    const html = renderToStaticMarkup(createElement(MoveHero, {
      regime: 'Risk-Off Consolidation', regimeLabel: 'neutral', asOf: '2026-06-20', runType: 'delta',
      actions: [{ ticker: 'NVDA', current_pct: 8, recommended_pct: 6, action: 'TRIM' }],
      nav: navOk,
    }));
    expect(html).toContain('NVDA');
    expect(html).toContain('TRIM');
    expect(html).toContain('104.2');         // NAV index in status line
    expect(html).toContain('SPY');
  });

  it('is never empty on a HOLD day', () => {
    const html = renderToStaticMarkup(createElement(MoveHero, {
      regime: 'Broadening Rally', regimeLabel: 'bullish', asOf: '2026-06-21', runType: 'delta',
      actions: [{ ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' }],
      nav: navOk,
    }));
    expect(html).toContain('No changes proposed'); // from TodayActionsPanel
    expect(html).toContain('104.2');
  });
});
```

- [ ] **Step 2:** Verify fails (module missing).
- [ ] **Step 3:** Implement `MoveHero`: a single `.glass-card` block carrying the regime accent. Top row = regime label + `AsOfBadge` + run-type badge (quiet). Hero = `"Today"` in `font-display` (Instrument Serif) display size, then `<TodayActionsPanel actions={actions} rationaleByTicker={rationaleByTicker} />` restyled as the focal element. Bottom = NAV status line: `NAV {index} · {dailyPct >=0?'+':''}{dailyPct}% today · {excessPct} vs {benchTicker} since {sinceDate}` using `formatPct`/`pnlColor`. Regime accent localized to this card only (no page-level ambient).
- [ ] **Step 4:** Verify passes.
- [ ] **Step 5:** Commit — `feat(olympus): MoveHero — regime ribbon + move + NAV status`.

### Task 2.2: `WhyToday` — inline level-2 disclosure

**Files:**
- Create: `frontend/olympus/components/today/why-today.tsx` + test.

**Interfaces:**
- Produces: `export function WhyToday(props: { deliberations: PipelineTickerDoc[]; pmMemoSummary: string | null }): JSX.Element | null` — renders a compact "Why today" card with net-stance summary + PM memo line + a `Link` to `/why` ("full debate →"). Returns `null` when there is neither a deliberation nor a memo.

- [ ] **Step 1:** Failing test — given one deliberation with a `net_stance`, the card renders the stance text and a link with href containing `/why`; given empty inputs, renders nothing (`expect(html).toBe('')`).
- [ ] **Step 2:** Verify fails.
- [ ] **Step 3:** Implement using the same `net_stance` extraction the current overview uses (filter transcripts whose `payload.net_stance` is a string). Summarize, don't dump the transcript.
- [ ] **Step 4:** Verify passes.
- [ ] **Step 5:** Commit — `feat(olympus): WhyToday inline disclosure`.

### Task 2.3: `TodaySummaries` — the four doorway cards

**Files:**
- Create: `frontend/olympus/components/today/today-summaries.tsx` + test.

**Interfaces:**
- Produces: `export function TodaySummaries(props: { navSpark: number[]; excessPct: number|null; sharpe: number|null; positions: Position[]; theses: ThesisRow[] }): JSX.Element` — a responsive grid of four quiet cards: **How I'm doing** (compact NAV sparkline + excess/Sharpe → links `/portfolio?tab=performance`), **The read** (`<MorningBriefPanel />` in summary mode → links `/why`), **Holdings** (top ~6 positions w/ weight+Δ → `/portfolio`), **Theses** (status dots → `/portfolio?tab=theses`).

- [ ] **Step 1:** Failing test — renders the four section labels ("How I'm doing", "The read", "Holdings", "Theses") and a link to `/portfolio?tab=performance`.
- [ ] **Step 2:** Verify fails.
- [ ] **Step 3:** Implement. Reuse the existing inline `StatSparkline` (extract it from `app/page.tsx` into this module or `components/ui`). Keep each card hairline/quiet — no full visual weight.
- [ ] **Step 4:** Verify passes.
- [ ] **Step 5:** Commit — `feat(olympus): Today summary doorways`.

### Task 2.4: Assemble the new `Today` page

**Files:**
- Modify: `frontend/olympus/app/page.tsx` (replace the 11-panel body)
- Modify/Create: `frontend/olympus/app/page.test.tsx`

- [ ] **Step 1:** Write/extend the page test: on an action day the move appears above the NAV index in source order (`html.indexOf('TRIM') < html.indexOf('104') `-style ordering check using stable text), the four summary labels are present, and the old full-page ambient class (e.g. `REGIME_PAGE_AMBIENT` output) is absent. Add a HOLD-day assertion.
- [ ] **Step 2:** Verify fails (page still renders old layout).
- [ ] **Step 3:** Rebuild `OverviewPage`: keep the existing `useDashboard()` + `useMemo` data prep (regime, `dailyRet`, `inceptionVsBenchmark`, `navSparkData`, `rationaleByTicker`, deliberations filter). Render `<MoveHero/> <WhyToday/> <TodaySummaries/>` and nothing else. Delete `REGIME_PAGE_AMBIENT` and the page-level ambient wrapper; delete the inline KPI strip, the standalone positions table, `DecisionTrailPanel`, `HeldTickerPricesPanel`, the benchmark blurb card, and the standalone thesis table (their content now lives in the hero, summaries, or deep surfaces). Keep the `loading`/`error` branches (swap loader for layout-shaped skeleton in Phase 6).
- [ ] **Step 4:** `npm test` green; visually confirm via build.
- [ ] **Step 5:** Commit — `feat(olympus): rebuild Today as move-led hero + summaries`.

### Task 2.5: Phase-2 gate

- [ ] Run `npm test && npm run build`. Expected: green + static export OK.
- [ ] Manual/Playwright check (carry to Phase 6 QA): hero is the focal element; HOLD day shows "No changes proposed"; no page-wide color wash.

---

## Phase 3 — Portfolio (the book): Holdings · Theses · Performance

**Outcome:** Portfolio's tabs become Holdings / Theses / Performance; `/portfolio/theses` folds into the Theses tab (the `[thesisId]` detail route stays); the conviction scorecard moves here.

- [ ] **Task 3.1 — Audit & map tabs.** Read `app/portfolio/*` and `lib/portfolio-url-state.ts` (current `PortfolioTabId = allocations|performance|analysis|activity`). Produce the mapping in the PR description: `allocations → Holdings`, `performance → Performance`, `analysis`/`activity` content folded into Holdings drilldown + Theses. Update `portfolio-url-state.ts` canonical IDs to `holdings | theses | performance` with legacy aliases (`allocations|summary → holdings`, `analysis|history → theses`, `activity → holdings`). **Test:** extend `lib/portfolio-url-state.test.ts` to assert the new canonical IDs and that every legacy alias resolves. Commit.
- [ ] **Task 3.2 — Holdings tab.** Full positions table (ticker, weight, Δweight, served thesis, NAV contribution) with row → per-position drilldown reusing `position-drilldown`, `position-events`, `position-contribution-series`, `position-first-entry`, `portfolio-research-links`. **Test:** renders a known position's ticker + its thesis link; drilldown reveals event log. Commit.
- [ ] **Task 3.3 — Theses tab.** Move the `/portfolio/theses` tracker into the Theses tab (claim, vehicle, status). Keep `/portfolio/theses/[thesisId]` detail. Convert `app/portfolio/theses/page.tsx` to redirect to `/portfolio?tab=theses`. **Test:** Theses tab lists a thesis with its status; `[thesisId]` still renders. Commit.
- [ ] **Task 3.4 — Performance tab + Decision quality.** Keep `PerformanceChartWorkspace`. Add a **Decision quality** block using `lib/decision-scorecard.ts` (`buildDecisionScorecard` over resolved `decision_log` rows from the dashboard data) showing per-bucket mean alpha + a "calibrated ✓/✗" flag. **Test:** given fixture decisions, the block renders bucket alphas and the calibration verdict. Commit.
- [ ] **Task 3.5 — Gate.** `npm test && npm run build` green; commit any fixups.

## Phase 4 — Why (the reasoning): The read · Deliberations · Documents

**Outcome:** `/why` gains three tabs ordered synthesized → raw; absorbs research + library.

- [ ] **Task 4.1 — Tab scaffold.** Give `app/why/page.tsx` three tabs (`read | deliberations | documents`) via the local-state + `SubpageStickyTabBar` pattern (mirror `app/observability/page.tsx`). **Test:** the three tab labels render; default tab is "The read". Commit.
- [ ] **Task 4.2 — The read.** Render the digest via `render-digest-from-snapshot` + `SafeMarkdown`, structured: regime snapshot + `actionable_summary` + `risk_radar` first, deeper sections (alt-data, institutional, asset-class, US equities, thesis tracker, recommendations) as expandable sections. Surface `segment_freshness` badges (today vs baseline). **Test:** leads with the regime/actionable content; a freshness badge appears. Commit.
- [ ] **Task 4.3 — Deliberations.** Render bull/bear (`render-pipeline-payloads`), risk debate, PM memo with net stance + conviction; sort today's-decision debates first. **Test:** a transcript with `net_stance` renders; today's date sorts above older. Commit.
- [ ] **Task 4.4 — Documents.** Move the current research "library" view here; categorized/filterable via `research-doc-categorize`, `library-doc-tier`, `research-manifest`. **Test:** a known doc appears under its category. Commit.
- [ ] **Task 4.5 — Gate.** `npm test && npm run build`; ensure `/research` and `/library` redirect to `/why`. Commit.

## Phase 5 — System (the demoted footnote): Run health · How Olympus works

**Outcome:** `/system` carries operator essentials only; deep ops panels and the scorecard are gone (scorecard now in Portfolio).

- [ ] **Task 5.1 — Run health.** From `app/observability` keep only: last-run status/time, data freshness (`snapshot-staleness`), `atlas_run_diagnostics` summary. Drop/hide per-phase cost & routing-internals panels behind a collapsed "diagnostics" `<details>`. **Remove the conviction scorecard** (moved in Phase 3). **Test:** run-health renders last-run + freshness; scorecard text absent. Commit.
- [ ] **Task 5.2 — How Olympus works.** Fold the `app/architecture/page.tsx` explainer (the P0 rewrite — Atlas A0–A8, Hermes H1–H9, cadence, grounding, routing, persistence) into a System tab/section. Convert `app/architecture/page.tsx` to redirect to `/system` (or keep as a deep link the System section embeds). Update `app/architecture/page.test.ts` accordingly. **Test:** System shows "How Olympus works" with `hermes/phases/h9_commit_run.py` and without `Monthly Synthesis`. Commit.
- [ ] **Task 5.3 — Gate.** `npm test && npm run build`; `/observability` redirects to `/system`. Commit.

## Phase 6 — Visual language, states, mobile QA (cross-cutting)

**Outcome:** the "one bold thing" hero treatment, first-class states, verified mobile/dark/light parity.

- [ ] **Task 6.1 — Hero typography & color discipline.** "Today" in `font-display` display size; action verbs in heavy tabular mono colored by direction (OPEN/ADD `--up`, TRIM/EXIT `--down`, HOLD muted); confirm regime accent is localized to `MoveHero` and the old `REGIME_PAGE_AMBIENT` is fully removed. **Test:** verb elements carry the direction class; no ambient class in `page.tsx` output. Commit.
- [ ] **Task 6.2 — States.** Layout-shaped skeletons for Today/Portfolio/Why (replace bare `AtlasLoader` on data pages); "No changes today" as a designed empty hero state (already via TodayActionsPanel — verify styling); plain in-voice error with a retry affordance; "as of {last run}" freshness on Today. **Test:** error branch renders a retry control; skeleton renders during loading. Commit.
- [ ] **Task 6.3 — Mobile & a11y QA.** Validate at 375px (hero stays hero, summary pairs stack, tables → card rows, bottom bar thumb-reachable) and confirm `prefers-reduced-motion` disables the entrance stagger. Use Playwright (own browser) computed-style checks in dark + light: tokens resolve (`--accent` = `#3DD6C4` dark / `#0E8C7F` light), serif applies to the hero, no horizontal scroll at 375px. Record findings; fix regressions. Commit.
- [ ] **Task 6.4 — Final gate.** Full `npm test` (all plumbing + new page tests green), `npm run build` static export clean, `make score` on staged changes meets the gate (Security ≥8, Quality ≥8, Optimization ≥7, Accuracy ≥9). Open PR `feat/olympus-redesign → develop`.

---

## Self-Review (against the spec)

- **Spec §1 IA** → Phase 1 (nav remap, /why, /system, redirects, Twelve-X unlinked). ✓
- **Spec §2 Today** → Phase 2 (MoveHero, WhyToday, TodaySummaries, page rebuild; HOLD-day covered by 2.1/2.4). ✓
- **Spec §3 Portfolio** → Phase 3 (Holdings/Theses/Performance + decision-quality move). ✓
- **Spec §3 Why** → Phase 4 (read/deliberations/documents). ✓
- **Spec §4 System/Settings/shell** → Phase 5 (run health + how-it-works) and Phase 1 (shell). Settings unchanged (no task needed — correct). ✓
- **Spec §5 Visual language** → Phase 6 (hero treatment, color discipline, states, mobile). ✓
- **Spec §6 Reuse/recompose/build/cut** → "Untouched plumbing" list + per-phase recompose tasks + redirect/cut tasks. ✓
- **Spec success criteria** → Phase 2 (above-the-fold move), Phase 1 (≤1 tap), Phase 5 (ops demoted), Phase 6 (dark/light/mobile/reduced-motion), Phase 6.4 (tests green + score gate). ✓
- **Placeholder scan:** Phases 1–2 carry full step-level code/tests. Phases 3–6 are task-level with explicit per-task acceptance tests and exact file/lib references; full step code is written at the start of each phase against then-current APIs (deliberate — avoids speculative JSX, per the codebase-follows-patterns rule). No "TBD"/"handle edge cases" placeholders.
- **Type consistency:** `RebalanceAction` fields and verbs match the verified type; `NavItem` shape consistent across 1.1–1.3; `PortfolioTabId` rename (3.1) is the single source consumed by 3.2–3.4.
