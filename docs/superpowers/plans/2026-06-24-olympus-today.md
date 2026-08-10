---
# Today (landing) Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (- [ ]) syntax.
**Goal:** Re-ground the Today landing page on the two always-present signals — the read (regime + headline + what-to-watch + tail risks) and the book (reconciled holdings strip with conviction + the day's biggest mover) — and demote the empty-on-baseline rebalance blotter to a one-line status.
**Architecture:** `app/page.tsx` orchestrates four stacked sections. The hero (`MoveHero`) promotes `snapshot.headline` + regime to a serif headline with a quiet confidence chip and a one-line move status. A new "What to watch" band consumes structured `actionable_summary`/`risk_radar` parsed in `lib/snapshot-context.ts` and exposed on `PortfolioStrategy`. A new "The book today" strip consumes the F3 `reconcileBook()` primitive, the F6 `ConvictionMeter`, and surfaces the biggest |day move|. NAV is honest for one point (since-inception only; daily-delta/benchmark gated on ≥2 NAV points). All cross-links use the F2 `buildPipelineHref` grammar.
**Tech Stack:** Next.js 16 static export (`output:export`, `basePath /olympus`), React 19, Tailwind v4 (`@theme` tokens, `[data-theme]`), lucide-react, recharts, Supabase, Vitest.

## Global Constraints
- **Static export only** (`output:export`, `basePath /olympus`): no server components with runtime data, no dynamic route handlers; all data flows through the existing `useDashboard()` client context. SSR in tests is via `renderToStaticMarkup` — components must render deterministically server-side (guard `recharts`/animation behind data-length predicates, exactly as `Sparkline` does at `today-summaries.tsx:37`).
- **Tailwind v4 design tokens, inherited exactly:** dark-first; cyan-phosphor `--accent` #3DD6C4; Instrument Serif `--font-display`; Geist sans/mono; `glass-card`; semantic `text-fin-green`/`text-fin-red`/`text-fin-amber`; `bg-bg-primary`/`bg-bg-secondary`/`bg-bg-glass`; `border-border-subtle`; `text-text-primary`/`text-text-secondary`/`text-text-muted`.
- **Vitest, keep tests green:** 150+ plumbing tests + the page-level tests in `components/today/*.test.tsx` and `app/page.test.ts` must stay green. Page-level tests are updated as part of this work. Run from `frontend/olympus` with `npm test`. Each task that changes behavior writes its failing test first.
- **F5 token rule (verbatim):** cyan `--accent` #3DD6C4 for links/chrome/the single conviction encoding/the live-fresh dot only; `fin-green`/`fin-red` *strictly* for signed financial values; `fin-amber` for caution/stale/carried/mixed-regime; **no gradients** beyond the existing faint regime wash (`REGIME_ACCENT.bg`); **no decorative numbering** unless it encodes the system's own priority (the `actionable_summary.priority` rank IS such an encoding and may be shown). Purge `text-fin-purple` from Today (`why-today.tsx:50`).
- **Empty-state discipline:** every time-series / multi-point element is gated on a data predicate (≥2 NAV points for daily-delta + benchmark) and renders a calm element-specific line or is simply absent — never an em-dash placeholder, a 1-row table, or a single-dot chart. Per-day elements (the read, the book) are the marquee and must carry the page on a baseline single day.
- **Issue linkage:** all commits conventional (`feat|fix|refactor|chore(olympus): …`). This surface consumes Phase 0; backend issues for the underlying data fixes are filed in Phase 0 (weight_pct dedupe, thesis_id canonicalize). No new backend issue originates here.
---

## Phase 0 interfaces this surface consumes (must already be merged)

- `lib/book-reconciliation.ts` → `reconcileBook(positions: Position[], opts?: { investedPct?: number | null }): BookReconciliation` where `BookReconciliation = { rows: ReconciledPosition[]; investedPct; cashPct; grossPct; netPct }` and `ReconciledPosition extends Position { normalizedWeight: number }`. **Single source of truth** for the book strip weights.
- `components/shared/conviction-meter.tsx` → `ConvictionMeter({ value, max = 3, srLabel }): JSX.Element` — UNSIGNED cyan pip meter for `positions.conviction` (1–3).
- `components/shared/as-of-badge.tsx` → `AsOfBadge({ date, createdAt?, now?, staleHours? }): JSX.Element | null` (canonical; `components/overview/as-of-badge.tsx` re-exports it). Today uses the inline-pill (date-only) path.
- `lib/pipeline-links.ts` → `buildPipelineHref({ date?, stage?, node? }): string` → `/pipeline?date=…&stage=…&node=…`. Today uses `buildPipelineHref({ date, node: 'digest' })` for "see the full read."
- `Position` (in `lib/types.ts`) widened with optional `conviction?: number | null` and `sector_bucket?: string | null` (Phase 0 F1). The query mapping at `lib/queries.ts:864` passes them through.

If any of these is missing when this surface starts, STOP — Phase 0 is not complete.

---

## Task 1: Parse structured digest actionables + risks (data layer)

**Files:**
- Modify `lib/snapshot-context.ts` (add two structured parsers below `digestItemsToStrings`, currently ends line 67)
- Modify `lib/types.ts` (add `ActionableItem`/`RiskItem` types; add `actionableItems`/`riskItems` to `PortfolioStrategy` at lines 60–68)
- Modify `lib/queries.ts` (populate the two new strategy fields at lines 1037–1038; extend the `./snapshot-context` import at line 33)
- Test `lib/snapshot-context.test.ts` (create — verify no existing file first; if one exists, append the `describe` blocks)

**Interfaces:**
- Consumes: the raw `daily_snapshots.snapshot` digest JSONB. Live shape verified 2026-06-24: `actionable_summary[]` items are `{ label: string; priority: number; rationale: string }`; `risk_radar[]` items are `{ label: string; trigger: string; horizon_hours: number }`. Items may also be plain strings (legacy) — degrade to a bare label.
- Produces:
  ```ts
  export interface ActionableItem { label: string; priority: number | null; rationale: string | null }
  export interface RiskItem { label: string; trigger: string | null; horizonHours: number | null }
  export function parseActionableItems(items: unknown): ActionableItem[]  // sorted by priority asc, null last
  export function parseRiskItems(items: unknown): RiskItem[]              // input order preserved
  ```
  and on `PortfolioStrategy`: `actionableItems: ActionableItem[]; riskItems: RiskItem[]`.

**Steps:**

- [ ] Write the failing test `lib/snapshot-context.test.ts`:
  ```ts
  import { describe, it, expect } from 'vitest';
  import { parseActionableItems, parseRiskItems } from './snapshot-context';

  describe('parseActionableItems', () => {
    it('maps structured items and sorts by priority ascending (null last)', () => {
      const out = parseActionableItems([
        { label: 'Trim XLI', priority: 2, rationale: 'rolling over' },
        { label: 'Monitor DXY above 120.4', priority: 1, rationale: 'near YTD highs' },
        { label: 'Bare', priority: null, rationale: null },
      ]);
      expect(out.map((a) => a.label)).toEqual(['Monitor DXY above 120.4', 'Trim XLI', 'Bare']);
      expect(out[0]).toEqual({ label: 'Monitor DXY above 120.4', priority: 1, rationale: 'near YTD highs' });
    });
    it('degrades plain-string items and drops empties', () => {
      expect(parseActionableItems(['Hold the book', '', '  '])).toEqual([
        { label: 'Hold the book', priority: null, rationale: null },
      ]);
    });
    it('returns [] for non-array input', () => {
      expect(parseActionableItems(null)).toEqual([]);
      expect(parseActionableItems({})).toEqual([]);
    });
  });

  describe('parseRiskItems', () => {
    it('maps trigger + horizon_hours, preserves order', () => {
      const out = parseRiskItems([
        { label: 'BOJ intervention', trigger: 'USD/JPY break above 162', horizon_hours: 48 },
        { label: 'Tail B', trigger: null, horizon_hours: null },
      ]);
      expect(out).toEqual([
        { label: 'BOJ intervention', trigger: 'USD/JPY break above 162', horizonHours: 48 },
        { label: 'Tail B', trigger: null, horizonHours: null },
      ]);
    });
    it('degrades plain strings and ignores labelless objects', () => {
      expect(parseRiskItems(['liquidity gap', { trigger: 'x' }])).toEqual([
        { label: 'liquidity gap', trigger: null, horizonHours: null },
      ]);
    });
  });
  ```
- [ ] Run `npm test -- snapshot-context` → expect **FAIL** (`parseActionableItems`/`parseRiskItems` not exported).
- [ ] Add the parsers to `lib/snapshot-context.ts` (append after line 67). Add the type import at the top of the file:
  ```ts
  import type { ActionableItem, RiskItem } from './types';
  ```
  ```ts
  /**
   * Structured parse of `actionable_summary` ActionableItem[] (label/priority/rationale),
   * sorted by priority ascending (the pipeline's own ranking — F5-permitted numbering),
   * nulls last. Plain-string entries degrade to a bare label. Non-arrays → [].
   */
  export function parseActionableItems(items: unknown): ActionableItem[] {
    if (!Array.isArray(items)) return [];
    const out: ActionableItem[] = [];
    for (const item of items) {
      if (typeof item === 'string') {
        const t = item.trim();
        if (t) out.push({ label: t, priority: null, rationale: null });
        continue;
      }
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        const o = item as Record<string, unknown>;
        const label = typeof o.label === 'string' ? o.label.trim() : '';
        if (!label) continue;
        out.push({
          label,
          priority: typeof o.priority === 'number' ? o.priority : null,
          rationale: typeof o.rationale === 'string' && o.rationale.trim() ? o.rationale.trim() : null,
        });
      }
    }
    return out.sort((a, b) => {
      if (a.priority == null && b.priority == null) return 0;
      if (a.priority == null) return 1;
      if (b.priority == null) return -1;
      return a.priority - b.priority;
    });
  }

  /**
   * Structured parse of `risk_radar` RiskItem[] (label/trigger/horizon_hours), input order
   * preserved (the pipeline orders by salience). Plain strings degrade to a bare label.
   */
  export function parseRiskItems(items: unknown): RiskItem[] {
    if (!Array.isArray(items)) return [];
    const out: RiskItem[] = [];
    for (const item of items) {
      if (typeof item === 'string') {
        const t = item.trim();
        if (t) out.push({ label: t, trigger: null, horizonHours: null });
        continue;
      }
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        const o = item as Record<string, unknown>;
        const label = typeof o.label === 'string' ? o.label.trim() : '';
        if (!label) continue;
        out.push({
          label,
          trigger: typeof o.trigger === 'string' && o.trigger.trim() ? o.trigger.trim() : null,
          horizonHours: typeof o.horizon_hours === 'number' ? o.horizon_hours : null,
        });
      }
    }
    return out;
  }
  ```
- [ ] Add the types to `lib/types.ts` (above `PortfolioStrategy`, before line 59):
  ```ts
  /** One ranked recommendation from the digest `actionable_summary`. */
  export interface ActionableItem {
    label: string;
    priority: number | null;
    rationale: string | null;
  }

  /** One tail-risk row from the digest `risk_radar`. */
  export interface RiskItem {
    label: string;
    trigger: string | null;
    horizonHours: number | null;
  }
  ```
- [ ] Add the two fields to `PortfolioStrategy` (after `risks: string[];` at line 65):
  ```ts
    actionableItems: ActionableItem[];
    riskItems: RiskItem[];
  ```
- [ ] Wire them in `lib/queries.ts`. Extend the existing `./snapshot-context` import (line 33):
  ```ts
  import {
    digestItemsToStrings,
    extractDigestContextBullets,
    parseActionableItems,
    parseRiskItems,
  } from './snapshot-context';
  ```
  and populate after `risks:` at line 1038:
  ```ts
        actionable: digestItemsToStrings(digest.actionable_summary),
        risks: digestItemsToStrings(digest.risk_radar),
        actionableItems: parseActionableItems(digest.actionable_summary),
        riskItems: parseRiskItems(digest.risk_radar),
  ```
- [ ] Run `npm test -- snapshot-context` → expect **PASS**.
- [ ] Run `npm test` (full suite) and `npm run lint` → expect green. The two new *required* fields on `PortfolioStrategy` will type-error any test that hand-builds a `strategy` literal without `as`. `app/page.test.ts` already casts `as unknown as DashboardData` (line 43) so it is unaffected; if any other test breaks at the type level, add `actionableItems: [], riskItems: []` to its fixture.
- [ ] Commit: `git add -A && git commit -m "feat(olympus): parse structured digest actionables + risks onto strategy"`

---

## Task 2: "What to watch" band — replace `WhyToday` with the read's actionables + tail risks

**Files:**
- Create `components/today/what-to-watch.tsx`
- Test `components/today/what-to-watch.test.tsx`
- Modify `app/page.tsx` (swap `WhyToday` for `WhatToWatch` at lines 11, 160; drop the now-unused `deliberations`/`pmMemoSummary` derivation at lines 110–115)
- Delete `components/today/why-today.tsx` + `components/today/why-today.test.tsx` (orphaned; carry the `text-fin-purple` + `/why` link the redesign removes)

**Interfaces:**
- Consumes: `strategy.actionableItems: ActionableItem[]` and `strategy.riskItems: RiskItem[]` (Task 1); `latestDate: string | null`; `buildPipelineHref` (Phase 0 F2).
- Produces: `WhatToWatch({ actionables, risks, asOfDate }: { actionables: ActionableItem[]; risks: RiskItem[]; asOfDate: string | null }): JSX.Element | null` — renders null only when both arrays are empty.

**Steps:**

- [ ] Write the failing test `components/today/what-to-watch.test.tsx`:
  ```ts
  import { createElement } from 'react';
  import { renderToStaticMarkup } from 'react-dom/server';
  import { describe, it, expect, vi } from 'vitest';

  vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

  import { WhatToWatch } from './what-to-watch';

  const actionables = [
    { label: 'Monitor DXY above 120.4', priority: 1, rationale: 'near YTD highs; pressures EM' },
    { label: 'Trim XLI on weakness', priority: 2, rationale: 'industrials rolling over' },
  ];
  const risks = [
    { label: 'BOJ intervention', trigger: 'USD/JPY break above 162', horizonHours: 48 },
  ];

  describe('WhatToWatch', () => {
    it('renders ranked actionables with rationale and the read deep-link', () => {
      const html = renderToStaticMarkup(
        createElement(WhatToWatch, { actionables, risks, asOfDate: '2026-06-24' })
      );
      expect(html).toContain('Monitor DXY above 120.4');
      expect(html).toContain('near YTD highs');
      expect(html).toContain('BOJ intervention');
      expect(html).toContain('48h'); // horizon
      expect(html).toContain('full read'); // CTA copy
    });
    it('renders only actionables when there are no risks', () => {
      const html = renderToStaticMarkup(
        createElement(WhatToWatch, { actionables, risks: [], asOfDate: null })
      );
      expect(html).toContain('Monitor DXY above 120.4');
      expect(html).not.toContain('Tail risks');
    });
    it('renders nothing when both are empty', () => {
      const html = renderToStaticMarkup(
        createElement(WhatToWatch, { actionables: [], risks: [], asOfDate: null })
      );
      expect(html).toBe('');
    });
  });
  ```
- [ ] Run `npm test -- what-to-watch` → expect **FAIL** (module not found).
- [ ] Create `components/today/what-to-watch.tsx`:
  ```tsx
  'use client';

  import Link from 'next/link';
  import { Eye, AlertTriangle } from 'lucide-react';
  import type { ActionableItem, RiskItem } from '@/lib/types';
  import { buildPipelineHref } from '@/lib/pipeline-links';

  /**
   * "What to watch" — the always-present read distilled into two ranked lists:
   * the digest's `actionable_summary` (priority → rationale) and its `risk_radar`
   * tail risks (trigger + horizon). Replaces the old, usually-empty "Why today"
   * card. Renders nothing only when the read carried neither — never an empty shell.
   * "See the full read" deep-links to the daily digest node in Pipeline (F2).
   */

  export interface WhatToWatchProps {
    actionables: ActionableItem[];
    risks: RiskItem[];
    asOfDate: string | null;
  }

  export function WhatToWatch({ actionables, risks, asOfDate }: WhatToWatchProps) {
    const acts = actionables.slice(0, 3);
    const tails = risks.slice(0, 2);
    if (acts.length === 0 && tails.length === 0) return null;

    return (
      <section className="glass-card px-5 py-4 sm:px-6">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Eye size={14} className="text-text-muted" />
            <h2 className="text-xs font-bold uppercase tracking-widest text-text-muted">
              What to watch
            </h2>
          </div>
          <Link
            href={buildPipelineHref({ date: asOfDate, node: 'digest' })}
            className="text-[10px] font-medium text-accent hover:underline"
          >
            see the full read →
          </Link>
        </div>

        {acts.length > 0 ? (
          <ol className="space-y-2.5">
            {acts.map((a, i) => (
              <li key={`${a.label}-${i}`} className="flex gap-3">
                <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-border-subtle font-mono text-[11px] tabular-nums text-text-muted">
                  {a.priority ?? i + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium leading-snug text-text-primary">{a.label}</p>
                  {a.rationale ? (
                    <p className="mt-0.5 text-xs leading-snug text-text-secondary">{a.rationale}</p>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        ) : null}

        {tails.length > 0 ? (
          <div className="mt-4 border-t border-border-subtle pt-3">
            <div className="mb-2 flex items-center gap-2">
              <AlertTriangle size={12} className="text-fin-amber" />
              <h3 className="text-[10px] font-bold uppercase tracking-widest text-text-muted">
                Tail risks
              </h3>
            </div>
            <ul className="space-y-2">
              {tails.map((r, i) => (
                <li key={`${r.label}-${i}`} className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm leading-snug text-text-secondary">
                      <span className="font-medium text-text-primary">{r.label}</span>
                      {r.trigger ? <span className="text-text-muted"> — {r.trigger}</span> : null}
                    </p>
                  </div>
                  {r.horizonHours != null ? (
                    <span className="shrink-0 font-mono text-[10px] tabular-nums text-fin-amber">
                      {r.horizonHours}h
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    );
  }
  ```
- [ ] Run `npm test -- what-to-watch` → expect **PASS**.
- [ ] In `app/page.tsx`: replace the import (line 11) `import { WhyToday } from '@/components/today/why-today';` with `import { WhatToWatch } from '@/components/today/what-to-watch';`. Remove the `deliberations` filter (lines 110–113) and `pmMemoSummary` (line 115) — Today no longer surfaces the debate roll-up. Keep `pipe`, `rebalanceActions`, and `rationaleByTicker` (the hero still uses them). Replace the `<WhyToday … />` block (line 160) with:
  ```tsx
        <WhatToWatch
          actionables={strategy.actionableItems ?? []}
          risks={strategy.riskItems ?? []}
          asOfDate={latestDate}
        />
  ```
- [ ] Delete the orphaned files: `git rm components/today/why-today.tsx components/today/why-today.test.tsx`
- [ ] Run `grep -rn "why-today" --include='*.tsx' --include='*.ts' .` → expect no remaining importers; if any non-test importer exists, STOP and reconcile.
- [ ] Run `npm test` + `npm run lint` → expect green.
- [ ] Commit: `git add -A && git commit -m "feat(olympus): Today 'What to watch' band from the digest read; retire Why-today card"`

---

## Task 3: Re-ground the hero on the read; demote the move; honest NAV

**Files:**
- Modify `components/today/move-hero.tsx` (props + render; lines 69–152)
- Modify `components/today/move-hero.test.tsx`
- Modify `app/page.tsx` (NAV derivation lines 132–140 + the `<MoveHero>` call lines 144–158)

**Interfaces:**
- Consumes (new `MoveHeroProps` additions): `headline: string | null` (from `strategy.summary`, which is `String(regime.summary ?? digest.headline ?? '')` at `queries.ts:1036`); `confidence: number | null` (from `strategy.theses[0].confidence` — `Thesis.confidence` is Phase 0 F1; theses are confidence-desc ordered, live top = 0.8). Reworked `MoveHeroNav`: `{ index; sincePct; sinceDate; dailyPct; benchTicker; excessPct }` where `sincePct = (latest/first − 1)·100` (always shown when `index != null`); `dailyPct`/`benchTicker`/`excessPct` render only when present (the ≥2-point gate lives in `page.tsx`).
- Produces: a hero that leads with regime + headline as the marquee, a quiet confidence chip, a one-line move status, and an honest NAV line.

**Steps:**

- [ ] Update `components/today/move-hero.test.tsx`. Replace the `navOk` fixture and the three cases:
  ```ts
  const navOk = {
    index: 98.6,
    sincePct: -0.7,
    sinceDate: '2026-06-23',
    dailyPct: -0.7,
    benchTicker: 'SPY',
    excessPct: 4.2,
  };

  describe('MoveHero', () => {
    it('leads with the regime headline and shows the demoted move + honest NAV', () => {
      const html = renderToStaticMarkup(
        createElement(MoveHero, {
          regime: 'Risk-Off Consolidation',
          regimeLabel: 'caution',
          headline: 'Mixed signals persist as tech leads equities and USD strengthens.',
          confidence: 0.7,
          asOf: '2026-06-24',
          runType: 'delta',
          actions: [{ ticker: 'NVDA', current_pct: 8, recommended_pct: 6, action: 'TRIM' }],
          nav: navOk,
        })
      );
      expect(html).toContain('Mixed signals persist'); // headline is the marquee
      expect(html).toContain('Risk-Off Consolidation');
      expect(html).toContain('0.7'); // confidence chip
      expect(html).toContain('98.6'); // NAV index
      expect(html).toContain('since inception'); // honest since-inception clause
      expect(html).toContain('1 change today'); // demoted move status (1 non-HOLD action)
    });

    it('shows a HOLD-day move status as holding the book', () => {
      const html = renderToStaticMarkup(
        createElement(MoveHero, {
          regime: 'Broadening Rally',
          regimeLabel: 'bullish',
          headline: 'Breadth improves; defensives lag.',
          confidence: 0.8,
          asOf: '2026-06-21',
          runType: 'delta',
          actions: [{ ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' }],
          nav: navOk,
        })
      );
      expect(html).toContain('No rebalance today — holding the book');
    });

    it('omits the daily-delta clause when there is only one NAV point', () => {
      const html = renderToStaticMarkup(
        createElement(MoveHero, {
          regime: 'Risk-Off Consolidation',
          regimeLabel: 'caution',
          headline: 'Quiet tape.',
          confidence: null,
          asOf: '2026-06-23',
          runType: null,
          actions: [],
          nav: { index: 99.3, sincePct: -0.7, sinceDate: '2026-06-23', dailyPct: null, benchTicker: null, excessPct: null },
        })
      );
      expect(html).toContain('since inception');
      expect(html).not.toContain('today'); // no daily-delta clause
    });
  });
  ```
- [ ] Run `npm test -- move-hero` → expect **FAIL**.
- [ ] Rework `components/today/move-hero.tsx`. Replace `MoveHeroNav` (lines 69–75):
  ```ts
  export interface MoveHeroNav {
    index: number | null;
    sincePct: number | null;
    sinceDate: string | null;
    dailyPct: number | null;
    benchTicker: string | null;
    excessPct: number | null;
  }
  ```
  Add to `MoveHeroProps` (after `regimeLabel: string;` at line 79):
  ```ts
    headline: string | null;
    confidence: number | null;
  ```
  Update the destructure (lines 92–100) to include `headline, confidence`. Replace the computed-vars block (lines 101–105) with:
  ```ts
    const accent = REGIME_ACCENT[regimeLabel] ?? REGIME_ACCENT.neutral;
    const changeCount = actions.filter((a) => {
      const k = (a.action || '').trim().toUpperCase();
      return k !== 'HOLD' && !(k === 'EXIT' && (a.current_pct ?? 0) === 0);
    }).length;
    const moveStatus =
      changeCount === 0
        ? 'No rebalance today — holding the book'
        : `${changeCount} change${changeCount === 1 ? '' : 's'} today`;
    const sinceColor =
      nav.sincePct == null ? 'text-text-muted' : nav.sincePct >= 0 ? 'text-fin-green' : 'text-fin-red';
    const dailyColor =
      nav.dailyPct == null ? 'text-text-muted' : nav.dailyPct >= 0 ? 'text-fin-green' : 'text-fin-red';
    const excessColor =
      nav.excessPct == null ? 'text-text-muted' : nav.excessPct >= 0 ? 'text-fin-green' : 'text-fin-red';
  ```
  Keep the regime ribbon header (lines 110–127, including `<AsOfBadge date={asOf} />` and the regime-label `Badge`). Replace the hero block (lines 129–148) with:
  ```tsx
          {/* THE READ — the marquee */}
          <p className="mt-4 text-[11px] font-bold uppercase tracking-widest text-text-muted">
            Today · {asOf ?? '—'}
          </p>
          <h1 className="font-display text-3xl sm:text-4xl leading-tight tracking-tight mt-1 text-text-primary">
            {headline ?? regime}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {confidence != null ? (
              <span className="rounded-md border border-border-subtle px-2 py-0.5 font-mono text-[11px] tabular-nums text-text-secondary">
                {confidence.toFixed(1)} confidence
              </span>
            ) : null}
            <span className="text-xs text-text-secondary">{regime}</span>
          </div>

          {/* The move — demoted to a one-line status */}
          {changeCount === 0 ? (
            <p className="mt-4 text-sm text-text-secondary">{moveStatus}</p>
          ) : (
            <details className="mt-4">
              <summary className="cursor-pointer text-sm text-text-secondary marker:text-text-muted">
                {moveStatus}
              </summary>
              <div className="mt-3">
                <TodayActionsPanel actions={actions} rationaleByTicker={rationaleByTicker} bare />
              </div>
            </details>
          )}

          {/* NAV status line — honest for one point */}
          <div className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-sm tabular-nums">
            <span className="text-[11px] uppercase tracking-widest text-text-muted">NAV</span>
            <span className="text-base font-semibold text-text-primary">
              {nav.index == null ? '—' : nav.index.toFixed(1)}
            </span>
            {nav.sincePct != null ? (
              <span className={sinceColor}>
                {signedPct(nav.sincePct)} since inception
                {nav.sinceDate ? <span className="text-text-muted"> ({nav.sinceDate})</span> : null}
              </span>
            ) : null}
            {nav.dailyPct != null ? (
              <span className={dailyColor}>{signedPct(nav.dailyPct, ' today')}</span>
            ) : null}
            {nav.benchTicker && nav.excessPct != null ? (
              <span className={excessColor}>
                {signedPct(nav.excessPct)} vs {nav.benchTicker}
              </span>
            ) : null}
          </div>
  ```
  The existing `signedPct` helper (lines 87–90) is reused unchanged. Verify no remaining reference to the old single-`dailyPct` NAV path or to `nav.daily`.
- [ ] Run `npm test -- move-hero` → expect **PASS**.
- [ ] Update `app/page.tsx`. Replace the `navIndex`/`dailyRet` block (lines 132–140) with:
  ```tsx
    const navSnaps = portfolio.snapshots ?? [];
    const navIndex = navSnaps.length ? navSnaps[navSnaps.length - 1].nav : null;
    const navFirst = navSnaps.length ? navSnaps[0].nav : null;
    const sincePct =
      navIndex != null && navFirst != null && navFirst > 0
        ? (navIndex / navFirst - 1) * 100
        : null;
    const sinceDate = navSnaps.length ? navSnaps[0].date : null;
    // Daily delta + benchmark are gated on ≥2 NAV points (empty-state discipline).
    const dailyRet =
      navSnaps.length >= 2
        ? ((navSnaps[navSnaps.length - 1].nav - navSnaps[navSnaps.length - 2].nav) /
            navSnaps[navSnaps.length - 2].nav) *
          100
        : null;
  ```
  (`navSparkData` at line 133 is still consumed by `TodaySummaries` in the current tree; it is removed in Task 5 along with that consumer — do not delete it here.) Update the `<MoveHero>` call (lines 144–158):
  ```tsx
        <MoveHero
          regime={strategy.regime}
          regimeLabel={regimeLabel}
          headline={strategy.summary || null}
          confidence={strategy.theses?.[0]?.confidence ?? null}
          asOf={latestDate}
          runType={runTypeLabel}
          actions={rebalanceActions}
          rationaleByTicker={rationaleByTicker}
          nav={{
            index: navIndex,
            sincePct,
            sinceDate,
            dailyPct: dailyRet,
            benchTicker: benchmarkBlurb?.ticker ?? null,
            excessPct: benchmarkBlurb?.excessPct ?? null,
          }}
        />
  ```
  `strategy.theses[0].confidence` requires `Thesis.confidence` (Phase 0 F1). If absent on the type when this runs, STOP — Phase 0 F1 is incomplete.
- [ ] Run `npm test -- "page|move-hero"` and `npm run lint`. `move-hero` must be green. `app/page.test.ts` is reworked end-to-end in Task 6 — leave it untouched here unless it errors at the **type** level (e.g. missing `confidence` on the fixture thesis); if so, add `confidence: 0.8` to the fixture thesis and `actionableItems: [], riskItems: []` to the fixture strategy now, but defer assertion changes to Task 6.
- [ ] Commit: `git add -A && git commit -m "feat(olympus): re-ground Today hero on the read; demote move; honest since-inception NAV"`

---

## Task 4: "The book today" strip — reconciled weights, conviction pips, biggest mover

**Files:**
- Create `components/today/book-strip.tsx`
- Test `components/today/book-strip.test.tsx`
- Modify `app/page.tsx` (mount `BookStrip` after `<WhatToWatch>`; add import)

**Interfaces:**
- Consumes: `Position[]` (with `conviction?`, `sector_bucket?`, `day_change_pct?` — verified live: EWT −5.64%, IJR conviction 3); `reconcileBook(positions, { investedPct }): BookReconciliation` (Phase 0 F3); `ConvictionMeter` (Phase 0 F6); `data.server_portfolio_metrics.invested_pct` (`ServerPortfolioMetrics.invested_pct`, `types.ts:165`) as the reconciliation basis.
- Produces: `BookStrip({ positions, investedPct, asOfDate }: { positions: Position[]; investedPct: number | null; asOfDate: string | null }): JSX.Element` — an Invested/Cash header from `reconcileBook` + held rows (ticker · normalized weight · conviction pips · day move) sorted by `|day move|` desc, biggest mover leading. CASH lives in the header, not as a row.

**Steps:**

- [ ] Write the failing test `components/today/book-strip.test.tsx`:
  ```ts
  import { createElement } from 'react';
  import { renderToStaticMarkup } from 'react-dom/server';
  import { describe, it, expect, vi } from 'vitest';

  vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

  import { BookStrip } from './book-strip';
  import type { Position } from '@/lib/types';

  function pos(p: Partial<Position> & { ticker: string }): Position {
    return {
      ticker: p.ticker, name: p.ticker, type: 'LONG', weight_actual: p.weight_actual ?? 10,
      current_price: null, entry_price: null, entry_date: null, rationale: '',
      thesis_ids: [], category: '', pm_notes: '', stats: {},
      conviction: p.conviction ?? null, day_change_pct: p.day_change_pct ?? null,
      sector_bucket: p.sector_bucket ?? null,
    } as Position;
  }

  describe('BookStrip', () => {
    const positions = [
      pos({ ticker: 'UUP', weight_actual: 40, conviction: 2, day_change_pct: 0.32 }),
      pos({ ticker: 'EWT', weight_actual: 10, conviction: 3, day_change_pct: -5.64 }),
      pos({ ticker: 'CASH', weight_actual: 25 }),
    ];
    it('shows the Invested/Cash header and leads with the biggest mover', () => {
      const html = renderToStaticMarkup(
        createElement(BookStrip, { positions, investedPct: 75, asOfDate: '2026-06-24' })
      );
      expect(html).toContain('Invested');
      expect(html).toContain('Cash');
      expect(html).toContain('EWT'); // biggest |move|
      expect(html).toContain('-5.6'); // its day move
      expect(html).toContain('All holdings'); // CTA to /portfolio
      // CASH is a header figure, not a list row
      expect(html.indexOf('EWT')).toBeLessThan(html.indexOf('UUP'));
    });
    it('renders an empty-state line when there are no held positions', () => {
      const html = renderToStaticMarkup(
        createElement(BookStrip, { positions: [pos({ ticker: 'CASH', weight_actual: 100 })], investedPct: 0, asOfDate: null })
      );
      expect(html).toContain('No positions held yet');
    });
  });
  ```
- [ ] Run `npm test -- book-strip` → expect **FAIL** (module not found).
- [ ] Create `components/today/book-strip.tsx`:
  ```tsx
  'use client';

  import Link from 'next/link';
  import { Wallet } from 'lucide-react';
  import type { Position } from '@/lib/types';
  import { reconcileBook } from '@/lib/book-reconciliation';
  import { ConvictionMeter } from '@/components/shared/conviction-meter';

  /**
   * "The book today" — a compact holdings strip on the F3 reconciled weight basis
   * (Invested / Cash header, normalized per-row weights summing to 100%). Each held
   * row shows ticker · normalized weight · conviction pips (F6) · day move; rows are
   * sorted by |day move| so the day's biggest mover leads. CASH lives in the header,
   * never as a metric-less row. Links to the full Holdings surface (/portfolio).
   */

  export interface BookStripProps {
    positions: Position[];
    investedPct: number | null;
    asOfDate: string | null;
  }

  export function BookStrip({ positions, investedPct }: BookStripProps) {
    const { rows, investedPct: invested, cashPct } = reconcileBook(positions, { investedPct });
    const held = rows
      .filter((r) => r.ticker.toUpperCase() !== 'CASH')
      .sort((a, b) => Math.abs(b.day_change_pct ?? 0) - Math.abs(a.day_change_pct ?? 0));

    return (
      <section className="glass-card px-5 py-4 sm:px-6">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Wallet size={14} className="text-text-muted" />
            <h2 className="text-xs font-bold uppercase tracking-widest text-text-muted">
              The book today
            </h2>
          </div>
          <Link href="/portfolio" className="text-[10px] font-medium text-accent hover:underline">
            All holdings →
          </Link>
        </div>

        {/* Reconciled Invested / Cash header (F3) */}
        <div className="mb-3 flex gap-6 font-mono text-xs tabular-nums">
          <span className="text-text-secondary">
            Invested <span className="text-text-primary">{invested.toFixed(0)}%</span>
          </span>
          <span className="text-text-secondary">
            Cash <span className="text-text-primary">{cashPct.toFixed(0)}%</span>
          </span>
        </div>

        {held.length === 0 ? (
          <p className="text-sm text-text-muted">No positions held yet — the book is all cash.</p>
        ) : (
          <ul className="divide-y divide-border-subtle/60">
            {held.map((r, i) => {
              const dc = r.day_change_pct;
              const dcColor =
                dc == null ? 'text-text-muted' : dc >= 0 ? 'text-fin-green' : 'text-fin-red';
              return (
                <li key={`${r.ticker}-${i}`} className="flex items-center gap-3 py-2">
                  <span className="w-12 shrink-0 font-mono text-xs font-bold text-text-primary">
                    {r.ticker}
                  </span>
                  <span className="w-12 shrink-0 font-mono text-xs tabular-nums text-text-secondary">
                    {r.normalizedWeight.toFixed(1)}%
                  </span>
                  <span className="shrink-0">
                    {r.conviction != null ? (
                      <ConvictionMeter value={r.conviction} srLabel={`${r.ticker} conviction`} />
                    ) : null}
                  </span>
                  <span className={`ml-auto shrink-0 font-mono text-xs tabular-nums ${dcColor}`}>
                    {dc == null ? '—' : `${dc > 0 ? '+' : ''}${dc.toFixed(1)}%`}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    );
  }
  ```
  Note: `asOfDate` is accepted on the props for symmetry with the other bands and a future per-row Pipeline deep-link, but is intentionally unused in this pass. Destructure only `{ positions, investedPct }` in the function body so the repo's `no-unused-vars` lint does not flag it (props type still documents the contract). Verify with `npm run lint`; if the prop-type itself trips a rule, drop `asOfDate` from `BookStripProps` and the page call.
- [ ] Run `npm test -- book-strip` → expect **PASS**.
- [ ] Mount in `app/page.tsx` after the `<WhatToWatch …/>` block, and add the import near line 12 (`import { BookStrip } from '@/components/today/book-strip';`):
  ```tsx
        <BookStrip
          positions={positions}
          investedPct={data.server_portfolio_metrics?.invested_pct ?? null}
          asOfDate={latestDate}
        />
  ```
- [ ] Run `npm test -- "book-strip|page"` + `npm run lint` → expect green.
- [ ] Commit: `git add -A && git commit -m "feat(olympus): Today 'book today' strip on reconciled weights with conviction + biggest mover"`

---

## Task 5: Doorways — retire "How I'm doing", repoint links to the F2 grammar + shared freshness

**Files:**
- Modify `components/today/today-summaries.tsx` (drop the perf doorway + sparkline; repoint CTAs to F2 + cyan)
- Modify `components/today/today-summaries.test.tsx`
- Modify `app/page.tsx` (drop `navSparkData` + `riskMetrics` + their imports; trim `TodaySummaries` props)
- Modify `components/today/move-hero.tsx` (import `AsOfBadge` from the F7 canonical path)

**Interfaces:**
- Consumes: `Position[]`, `Thesis[]`, `strategy.summary`; `buildPipelineHref` (F2); the canonical `AsOfBadge` (F7).
- Produces: a trimmed `TodaySummaries` with three doorways — The read (→ Pipeline digest node), Holdings (→ /portfolio), Theses (→ /portfolio?tab=theses). The performance doorway is retired until time-series exists.

**Steps:**

- [ ] Update `components/today/today-summaries.test.tsx`. Rewrite both cases to drop `navSpark`/`excessPct`/`sharpe` and assert three doorways:
  ```ts
  describe('TodaySummaries', () => {
    it('renders the three quiet doorway cards with their content', () => {
      const html = renderToStaticMarkup(
        createElement(TodaySummaries, {
          positions: [{ ticker: 'NVDA', name: 'NVIDIA', weight_actual: 6.1, weight_delta: -2 }],
          theses: [{ id: 'T1', name: 'AI capex supercycle', status: 'confirmed' }],
          readSummary: 'Risk-off consolidation; rotating into defensives.',
          asOfDate: '2026-06-24',
        })
      );
      expect(html).toContain('The read');
      expect(html).toContain('Holdings');
      expect(html).toContain('Theses');
      expect(html).toContain('NVDA');
      expect(html).toContain('AI capex supercycle');
      expect(html).toContain('Risk-off consolidation');
      expect(html).not.toContain("How I'"); // performance doorway retired
    });

    it('handles an empty book without crashing', () => {
      const html = renderToStaticMarkup(
        createElement(TodaySummaries, {
          positions: [], theses: [], readSummary: null, asOfDate: null,
        })
      );
      expect(html).toContain('Holdings');
      expect(html).toContain('Theses');
    });
  });
  ```
- [ ] Run `npm test -- today-summaries` → expect **FAIL**.
- [ ] Edit `components/today/today-summaries.tsx`:
  - Delete the `Sparkline` component (lines 37–58). From the imports: drop `LineChart, Line, ResponsiveContainer, YAxis` (line 5) and `TrendingUp` (line 6); keep `BookOpen, Wallet, Shield` and the `ElementType` import (used by `Doorway`).
  - Add `import { buildPipelineHref } from '@/lib/pipeline-links';` near the top.
  - Replace `TodaySummariesProps` (lines 27–35) with:
    ```ts
    export interface TodaySummariesProps {
      positions: TodayHolding[];
      theses: TodayThesis[];
      /** The digest headline (`strategy.summary`) — the read doorway's teaser. */
      readSummary: string | null;
      /** Run date — keys the read doorway's Pipeline deep-link (F2). */
      asOfDate: string | null;
    }
    ```
  - Change the grid `sm:grid-cols-2` (line 110) → `sm:grid-cols-3` and remove the entire "How I'm doing" `Doorway` (lines 111–125).
  - Repoint "The read" doorway (line 128): `href={buildPipelineHref({ date: asOfDate, node: 'digest' })}`; keep `cta="Read"` and `icon={BookOpen}`.
  - Holdings (`href="/portfolio"`) and Theses (`href="/portfolio?tab=theses"`) hrefs are unchanged.
  - In the `Doorway` helper, change the CTA color `text-fin-blue` (line 91) → `text-accent` (F5).
  - Update the destructure (lines 98–105) to `{ positions, theses, readSummary, asOfDate }`.
- [ ] Run `npm test -- today-summaries` → expect **PASS**.
- [ ] Update `app/page.tsx`:
  - Remove `navSparkData` (line 133), `riskMetrics` (lines 75–79), and the `computeEffectivePortfolioRiskMetrics` import (line 9) — all were exclusive to the retired perf doorway. **Keep** `benchmarkBlurb` + its helpers (`pickBenchmarkTicker`/`inceptionVsBenchmark`/`DASHBOARD_BENCHMARK_TICKERS`/`BenchmarkHistoryMap`/`NavChartPoint`) — the hero still reads `benchmarkBlurb?.ticker`/`.excessPct`.
  - Update the `<TodaySummaries>` call (lines 162–169):
    ```tsx
        <TodaySummaries
          positions={positions}
          theses={strategy.theses ?? []}
          readSummary={strategy.summary ?? null}
          asOfDate={latestDate}
        />
    ```
  - Confirm cleanup: `grep -n "riskMetrics\|navSparkData\|computeEffectivePortfolioRiskMetrics" app/page.tsx` returns nothing.
- [ ] Switch the hero's freshness pill to the F7 canonical component: in `components/today/move-hero.tsx` change `import { AsOfBadge } from '@/components/overview/as-of-badge';` → `import { AsOfBadge } from '@/components/shared/as-of-badge';`. Leave the `<AsOfBadge date={asOf} />` call as-is (the canonical signature accepts `date` with optional `createdAt`/`now`/`staleHours`).
- [ ] Run `grep -rn "fin-blue\|fin-purple" components/today` → only the regime-accent `fin-blue` tints inside `REGIME_ACCENT.neutral` (move-hero) may remain (those are a regime accent, not a link — allowed by F5). No `fin-purple` may remain.
- [ ] Run `npm test` (full suite) + `npm run lint` → expect green.
- [ ] Commit: `git add -A && git commit -m "refactor(olympus): trim Today doorways to read/holdings/theses; F2 deep-links + F7 freshness"`

---

## Task 6: Page integration test — the four sections on a baseline day

**Files:**
- Modify `app/page.test.ts` (rework `makeData` + assertions for the new section set)

**Interfaces:**
- Consumes: the full `app/page.tsx` composition (hero + What-to-watch + Book + doorways) after Tasks 1–5.
- Produces: a green page-level test pinning the new behavior (read marquee, demoted move, honest NAV, what-to-watch rows, book biggest mover, three doorways, no perf doorway).

**Steps:**

- [ ] Rework `app/page.test.ts`. Replace `makeData` (lines 14–44):
  ```ts
  function makeData(actions: Action[]): DashboardData {
    return {
      portfolio: {
        meta: { last_updated: '2026-06-24', latest_snapshot_run_type: 'delta' },
        strategy: {
          regime: 'Risk-Off Consolidation',
          regime_label: 'caution',
          summary: 'Mixed signals persist as tech leads equities and USD strengthens.',
          actionable: [],
          risks: [],
          actionableItems: [
            { label: 'Monitor DXY above 120.4', priority: 1, rationale: 'near YTD highs' },
          ],
          riskItems: [
            { label: 'BOJ intervention', trigger: 'USD/JPY break above 162', horizonHours: 48 },
          ],
          theses: [{ id: 'T1', name: 'AI capex supercycle', status: 'ACTIVE', vehicle: null, confidence: 0.8 }],
          next_review: 'Daily',
        },
        snapshots: [
          { date: '2026-06-23', nav: 99.32 },
          { date: '2026-06-24', nav: 98.64 },
        ],
      },
      positions: [
        { ticker: 'EWT', name: 'EWT', weight_actual: 10, conviction: 3, day_change_pct: -5.64 },
        { ticker: 'UUP', name: 'UUP', weight_actual: 40, conviction: 2, day_change_pct: 0.32 },
        { ticker: 'CASH', name: 'CASH', weight_actual: 25 },
      ],
      portfolio_management: { rebalance_actions: actions },
      pipeline_observability: {},
      benchmarks: {
        SPY: { history: [{ date: '2026-06-23', price: 500 }, { date: '2026-06-24', price: 498 }] },
      },
      server_portfolio_metrics: { invested_pct: 75 },
    } as unknown as DashboardData;
  }
  ```
- [ ] Replace the `describe` block (lines 46–76):
  ```ts
  describe('Today (Overview) page', () => {
    it('leads with the read, demotes the move, and shows honest NAV + all bands', () => {
      useDashboardMock.mockReturnValue({
        data: makeData([{ ticker: 'NVDA', current_pct: 8, recommended_pct: 6, action: 'TRIM' }]),
        loading: false,
        error: null,
      });
      const html = renderToStaticMarkup(createElement(OverviewPage));
      expect(html).toContain('Mixed signals persist'); // read marquee
      expect(html).toContain('since inception'); // honest NAV
      expect(html).toContain('1 change today'); // demoted move
      expect(html).toContain('Monitor DXY above 120.4'); // what to watch
      expect(html).toContain('BOJ intervention');
      expect(html).toContain('Invested'); // book strip reconciled header
      expect(html).toContain('EWT');
      expect(html).toContain('-5.6'); // biggest mover
      for (const label of ['The read', 'Holdings', 'Theses']) expect(html).toContain(label);
      expect(html).not.toContain("How I'"); // perf doorway retired
    });

    it('shows the holding-the-book status on a no-change day', () => {
      useDashboardMock.mockReturnValue({
        data: makeData([{ ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' }]),
        loading: false,
        error: null,
      });
      const html = renderToStaticMarkup(createElement(OverviewPage));
      expect(html).toContain('No rebalance today — holding the book');
    });

    it('keeps the localized regime accent, not a full-page wash', () => {
      useDashboardMock.mockReturnValue({ data: makeData([]), loading: false, error: null });
      const html = renderToStaticMarkup(createElement(OverviewPage));
      expect(html).not.toContain('inset_0_0_140px');
    });
  });
  ```
- [ ] Run `npm test -- app/page` → expect **PASS** (depends on Tasks 1–5 merged).
- [ ] Run the full suite `npm test` + `npm run lint` → expect green across the repo (150+ plumbing tests untouched).
- [ ] Commit: `git add -A && git commit -m "test(olympus): pin Today page on the read+book composition (baseline day)"`

---

## Done criteria

- [ ] Today leads with the regime headline (`snapshot.headline` via `strategy.summary`), a quiet confidence chip, and a one-line move status reading "No rebalance today — holding the book" on baseline days; non-empty days disclose the blotter behind a `<details>`.
- [ ] NAV shows `index → since-inception %` honestly on one point; daily-delta and `vs <bench>` clauses appear only with ≥2 NAV points.
- [ ] "What to watch" renders the ranked `actionable_summary` (priority → rationale) + `risk_radar` tail risks (trigger + `Nh` horizon); "see the full read →" deep-links to `/pipeline?...&node=digest` via `buildPipelineHref` (F2).
- [ ] "The book today" reconciles to Invested/Cash via `reconcileBook` (F3), shows per-row conviction pips (F6), sorts by |day move|, surfaces EWT −5.6% as the biggest mover, and puts CASH in the header (not a row).
- [ ] Doorways are three (read/holdings/theses); "How I'm doing" retired; CTAs use cyan `text-accent`; no `text-fin-purple`/link-`text-fin-blue` literals remain in `components/today`.
- [ ] `npm test` and `npm run lint` green from `frontend/olympus`.
