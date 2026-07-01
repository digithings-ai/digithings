---
# Portfolio · Holdings Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (- [ ]) syntax.
**Goal:** Turn the Holdings table from a 150%-summing, conviction-blind grid into a conviction-first, decision-aware positions view that reconciles to 100%, deep-links each row to its Pipeline node, and absorbs the relocated Position-risk diagnostics.
**Architecture:** Holdings consumes the Phase 0 primitives — `reconcileBook` (F3 normalized weights + Invested/Cash strip), `ConvictionMeter`/`SignedConvictionBadge` (F6), `buildPipelineHref` (F2 deep-links). A new client-side `decision_log` fetch (reusing `fetchObservabilityData`) supplies the held-position decision badge and the "Proposed by the pipeline" shelf. The table re-tokenizes off blue/purple to cyan (F5), drops empty Name/Category columns, groups rows by `sector_bucket`, and renders a `stop ↔ target / Nd` risk micro-cell. `PositionRiskTab` is retired from System; its data lives inline in the table.
**Tech Stack:** Next.js 16 static export (`output:export`, `basePath /olympus`), React 19, Tailwind v4 `@theme` tokens + `[data-theme]`, recharts (existing drilldown only), lucide-react, vitest.

## Global Constraints
- **Static export only.** No server components, no runtime API routes, no `dynamic = 'force-dynamic'`. All data arrives via the existing client `getFullDashboardData()` (dashboard context) or a fail-soft client fetch (`fetchObservabilityData`). New reads must work under anon-key + RLS and fail-soft to an empty state.
- **Tailwind v4 tokens only.** Use the design tokens verbatim: `--accent` cyan `#3DD6C4` for links/chrome/the single conviction encoding/the live-fresh dot only; `text-fin-green`/`text-fin-red` strictly for signed financial values; `text-fin-amber` for caution/stale/carried/mixed; `bg-bg-primary`/`bg-bg-secondary`/`bg-bg-glass`; `border-border-subtle`; `text-text-primary`/`text-text-secondary`/`text-text-muted`; `glass-card`; `font-display` (Instrument Serif) for headline numerals only; `font-mono`/`tabular-nums` for figures.
- **The F5 token rule (verbatim, applied to this surface):** purge Holdings' off-palette literals — the `rgba(59,130,246,…)` weight-bar background in `AllocationsPositionsTable.tsx` and the `#a78bfa` drilldown price line + `rgb(59,130,246)` weight area/gradient in `PositionDrilldown.tsx` (and the `text-fin-blue`/`#38bdf8` ADD-event accents). Replace with cyan `--accent` (interactive/structural) and semantic fin-green/red (signed values) only. No gradients beyond the existing faint wash. No new decorative color.
- **Empty-state discipline.** Time-series elements gate on a data predicate (≥2 sleeve dates) and render a calm element-specific line — never an em-dash placeholder, a 1-row "table over time," or a single-dot chart. Per-day elements (the positions table, the book strip, the risk cells) are the marquee and must carry the surface on a single baseline day. The target-vs-current column stays hidden until a rebalance payload exists but shows a quiet "no target book yet" affordance, not silent absence. `SleeveHistorySection` collapses to an empty-state on single-day data.
- **Keep tests green.** Run `cd frontend/olympus && pnpm test` (`vitest run`) — 150+ plumbing + page-level tests must stay green. Page-level tests are updated as part of the work where behavior changes. Follow existing eslint/prettier conventions (ruff is Python-only).
- **Slop guard.** The conviction pip meter and the signed decision badge each encode a *different real quantity* (unsigned per-position strength 1–3 vs signed stance −5..+5) and must each be the only accent on their cell. The Pipeline link is contextual per row (a position → ITS decision node), never a cloned generic "View in Pipeline" button.
- **Issue linkage.** Each commit traces to a GitHub issue. Holdings ships correct on the F3/F4 query-layer interim today; it tightens when backend issues #1 (`weight_pct` seeding) and #3 (`thesis_id` canonicalization) land. Use a `task/<N>-slug` branch or `Fixes #<N>` — placeholders flagged inline.
---

## Phase 0 dependencies (consumed, not defined here)

This plan assumes the Phase 0 plan (`2026-06-24-olympus-phase0-foundation.md`) has landed these EXACT surfaces. If executing before Phase 0, that work blocks this surface.

- `lib/book-reconciliation.ts` → `reconcileBook(positions: Position[], opts?: { investedPct?: number | null }): BookReconciliation`; `ReconciledPosition extends Position { normalizedWeight: number }`; `BookReconciliation { rows: ReconciledPosition[]; investedPct: number; cashPct: number; grossPct: number; netPct: number }`.
- `lib/pipeline-links.ts` → `buildPipelineHref({ date?, stage?, node? }): string`; `stageForDocumentKey(key): PipelineStage | null`; type `PipelineStage = 'inputs'|'research'|'synthesis'|'selection'|'decision'`.
- `components/shared/conviction-meter.tsx` → `ConvictionMeter({ value, max?, srLabel })`.
- `components/shared/signed-conviction-badge.tsx` → `SignedConvictionBadge({ value })`.
- `lib/types.ts` `Position` widened with optional `conviction?: number | null`, `stop_loss_pct?: number | null`, `target_pct_gain?: number | null`, `horizon_days?: number | null`, `sector_bucket?: string | null`, populated by the F1 query-layer mapping in `lib/queries.ts`.
- `lib/thesis-id.ts` → `normalizeThesisId`, `thesisIdEquals`, `joinPositionsToThesis` (F4 interim normalization; already present in-repo).

**Grounded facts the steps rely on:** `decision_log.conviction` is the **−5..+5** scale (per `lib/decision-scorecard.ts` header — NOT 0..5 nor −2..+3); `stance` is a lowercase string (`'buy'`/`'hold'`/`'sell'`/`'bullish'`/…). `positions` table already carries `conviction`/`stop_loss_pct`/`target_pct_gain`/`horizon_days`/`sector_bucket` (`lib/database.types.ts:43-49`). The portfolio page does **not** receive `decision_log` in the dashboard bundle (`DashboardData` has no decisions field), so it must be fetched via `fetchObservabilityData()` (fail-soft). `ReconciledPosition extends Position`, so it is type-assignable wherever a `Position` is expected (e.g. `PositionDrilldown`).

---

### Task 1: Book-reconciliation header strip on Holdings

**Files:**
- Create: `frontend/olympus/components/portfolio/BookReconciliationStrip.tsx`
- Test: `frontend/olympus/components/portfolio/BookReconciliationStrip.test.tsx`

**Interfaces:**
- Consumes (Phase 0): `BookReconciliation { rows: ReconciledPosition[]; investedPct: number; cashPct: number; grossPct: number; netPct: number }`.
- Produces: `BookReconciliationStrip({ reconciliation, asOfDate }: { reconciliation: BookReconciliation; asOfDate: string | null }): JSX.Element` — used by `AllocationsTab` (Task 6).

**Steps:**
- [ ] Write failing test `BookReconciliationStrip.test.tsx`:
  ```tsx
  import { createElement } from 'react';
  import { renderToStaticMarkup } from 'react-dom/server';
  import { describe, it, expect } from 'vitest';
  import BookReconciliationStrip from './BookReconciliationStrip';
  import type { BookReconciliation } from '@/lib/book-reconciliation';

  const recon: BookReconciliation = { rows: [], investedPct: 75, cashPct: 25, grossPct: 75, netPct: 75 };

  describe('BookReconciliationStrip', () => {
    it('renders invested and cash that sum to 100', () => {
      const html = renderToStaticMarkup(
        createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: '2026-06-23' })
      );
      expect(html).toContain('Invested');
      expect(html).toContain('75.0%');
      expect(html).toContain('Cash');
      expect(html).toContain('25.0%');
      expect(html).toContain('2026-06-23');
    });

    it('omits the gross/net clause when unlevered (gross === invested)', () => {
      const html = renderToStaticMarkup(
        createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: null })
      );
      expect(html).not.toContain('Gross');
      expect(html).not.toContain('Net');
    });
  });
  ```
- [ ] Run `cd frontend/olympus && pnpm test BookReconciliationStrip` — expect FAIL (module not found).
- [ ] Implement `BookReconciliationStrip.tsx`:
  ```tsx
  'use client';

  import type { BookReconciliation } from '@/lib/book-reconciliation';

  /**
   * The single weight headline for Holdings (F3). Held positions + cash = 100%.
   * Gross/Net only render when the book is levered (gross !== invested) — today it
   * is unlevered, so the strip stays a clean two-tile Invested / Cash readout.
   */
  export default function BookReconciliationStrip({
    reconciliation,
    asOfDate,
  }: {
    reconciliation: BookReconciliation;
    asOfDate: string | null;
  }) {
    const { investedPct, cashPct, grossPct, netPct } = reconciliation;
    const levered =
      Math.abs(grossPct - investedPct) > 0.05 || Math.abs(netPct - investedPct) > 0.05;
    return (
      <div className="glass-card flex flex-wrap items-center justify-between gap-x-8 gap-y-3 px-4 py-4 md:px-6">
        <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-text-muted">Invested</p>
            <p className="mt-0.5 font-mono text-2xl tabular-nums text-text-primary">
              {investedPct.toFixed(1)}%
            </p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wider text-text-muted">Cash</p>
            <p className="mt-0.5 font-mono text-2xl tabular-nums text-text-secondary">
              {cashPct.toFixed(1)}%
            </p>
          </div>
          {levered && (
            <>
              <div>
                <p className="text-[11px] uppercase tracking-wider text-text-muted">Gross</p>
                <p className="mt-0.5 font-mono text-2xl tabular-nums text-text-primary">
                  {grossPct.toFixed(1)}%
                </p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wider text-text-muted">Net</p>
                <p className="mt-0.5 font-mono text-2xl tabular-nums text-text-primary">
                  {netPct.toFixed(1)}%
                </p>
              </div>
            </>
          )}
        </div>
        {asOfDate && <p className="font-mono text-xs text-text-muted">as of {asOfDate}</p>}
      </div>
    );
  }
  ```
- [ ] Run `cd frontend/olympus && pnpm test BookReconciliationStrip` — expect PASS.
- [ ] Commit: `git add -A && git commit -m "feat(olympus): book-reconciliation strip for Holdings (F3)"`

---

### Task 2: Risk-envelope micro-cell (stop ↔ target + horizon)

**Files:**
- Create: `frontend/olympus/components/portfolio/RiskEnvelopeCell.tsx`
- Test: `frontend/olympus/components/portfolio/RiskEnvelopeCell.test.tsx`

**Interfaces:**
- Consumes (Phase 0 widened `Position`): `stop_loss_pct?: number | null`, `target_pct_gain?: number | null`, `horizon_days?: number | null`. Semantics ported verbatim from `components/observability/PositionRiskTab.tsx` (stop = downside %, target = upside % gain, horizon = days; advisory display fields derived from ATR + conviction — NOT orders, never sent to any broker).
- Produces: `RiskEnvelopeCell({ stopLossPct, targetPctGain, horizonDays }: { stopLossPct: number | null | undefined; targetPctGain: number | null | undefined; horizonDays: number | null | undefined }): JSX.Element` — used by the table row (Task 4).

**Steps:**
- [ ] Write failing test `RiskEnvelopeCell.test.tsx`:
  ```tsx
  import { createElement } from 'react';
  import { renderToStaticMarkup } from 'react-dom/server';
  import { describe, it, expect } from 'vitest';
  import RiskEnvelopeCell from './RiskEnvelopeCell';

  describe('RiskEnvelopeCell', () => {
    it('renders stop, target, and horizon when populated', () => {
      const html = renderToStaticMarkup(
        createElement(RiskEnvelopeCell, { stopLossPct: -8, targetPctGain: 15, horizonDays: 30 })
      );
      expect(html).toContain('-8.0%');
      expect(html).toContain('+15.0%');
      expect(html).toContain('30d');
    });

    it('renders a quiet placeholder when no risk fields are set', () => {
      const html = renderToStaticMarkup(
        createElement(RiskEnvelopeCell, { stopLossPct: null, targetPctGain: null, horizonDays: null })
      );
      expect(html).toContain('—');
      expect(html).not.toContain('%');
    });
  });
  ```
- [ ] Run `cd frontend/olympus && pnpm test RiskEnvelopeCell` — expect FAIL.
- [ ] Implement `RiskEnvelopeCell.tsx`:
  ```tsx
  'use client';

  /**
   * Advisory risk envelope (relocated from System's PositionRiskTab). stop_loss_pct is a
   * downside %, target_pct_gain an upside % gain, horizon_days the holding window. These are
   * display-only — NOT orders, never sent to any broker (the book is paper-only).
   */
  export default function RiskEnvelopeCell({
    stopLossPct,
    targetPctGain,
    horizonDays,
  }: {
    stopLossPct: number | null | undefined;
    targetPctGain: number | null | undefined;
    horizonDays: number | null | undefined;
  }) {
    const hasStop = stopLossPct != null;
    const hasTarget = targetPctGain != null;
    const hasHorizon = horizonDays != null;
    if (!hasStop && !hasTarget && !hasHorizon) {
      return <span className="text-text-muted">—</span>;
    }
    // Position the entry (0%) tick proportionally between the stop and target ends.
    const down = hasStop ? Math.abs(stopLossPct as number) : 0;
    const up = hasTarget ? Math.abs(targetPctGain as number) : 0;
    const span = down + up;
    const entryPct = span > 0 ? (down / span) * 100 : 50;
    return (
      <div className="flex items-center justify-end gap-2">
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-2 font-mono text-[11px] tabular-nums">
            <span className={hasStop ? 'text-fin-red' : 'text-text-muted'}>
              {hasStop
                ? `${(stopLossPct as number) >= 0 ? '+' : ''}${(stopLossPct as number).toFixed(1)}%`
                : '—'}
            </span>
            <span className="text-text-muted">↔</span>
            <span className={hasTarget ? 'text-fin-green' : 'text-text-muted'}>
              {hasTarget ? `+${(targetPctGain as number).toFixed(1)}%` : '—'}
            </span>
          </div>
          {(hasStop || hasTarget) && (
            <div className="relative h-1 w-24 rounded-full bg-bg-secondary">
              <div className="absolute inset-y-0 left-0 w-1/2 rounded-l-full bg-fin-red/40" />
              <div className="absolute inset-y-0 right-0 w-1/2 rounded-r-full bg-fin-green/40" />
              <div
                className="absolute -top-0.5 h-2 w-0.5 bg-[var(--accent)]"
                style={{ left: `${entryPct}%` }}
                aria-hidden
              />
            </div>
          )}
        </div>
        {hasHorizon && (
          <span className="rounded border border-fin-amber/30 bg-fin-amber/10 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-fin-amber">
            {horizonDays}d
          </span>
        )}
      </div>
    );
  }
  ```
- [ ] Run `cd frontend/olympus && pnpm test RiskEnvelopeCell` — expect PASS.
- [ ] Commit: `git add -A && git commit -m "feat(olympus): risk-envelope micro-cell, relocated from System"`

---

### Task 3: Decision-aware holdings helpers (latest / proposed / node)

**Files:**
- Create: `frontend/olympus/lib/holdings-decisions.ts`
- Test: `frontend/olympus/lib/holdings-decisions.test.ts`

**Interfaces:**
- Consumes: `TableRow<'decision_log'>` rows (`{ ticker; run_date; stance; conviction: number | null; status; thesis; … }`) from `fetchObservabilityData().decisions`. `decision_log.conviction` is the −5..+5 scale; `stance` is a lowercase string.
- Produces:
  ```ts
  export type DecisionLogRow = TableRow<'decision_log'>;
  export interface ProposedDecision { ticker: string; conviction: number | null; stance: string | null; runDate: string | null; node: string }
  export function decisionNodeFor(ticker: string): string;                                  // 'analyst/{TICKER}'
  export function latestDecisionByTicker(decisions: DecisionLogRow[]): Map<string, DecisionLogRow>;
  export function proposedNotHeld(decisions: DecisionLogRow[], heldTickers: Set<string>): ProposedDecision[];
  ```
  Used by the table (Task 4), the shelf (Task 5), and the tab (Task 6).

**Steps:**
- [ ] Write failing test `holdings-decisions.test.ts`:
  ```ts
  import { describe, it, expect } from 'vitest';
  import { latestDecisionByTicker, proposedNotHeld, decisionNodeFor } from './holdings-decisions';

  const d = (over: Partial<{ ticker: string; run_date: string; stance: string; conviction: number | null; status: string }>) =>
    ({
      id: '1', run_id: 'r', ticker: 'X', run_date: '2026-06-23', stance: 'buy', conviction: 3,
      status: 'pending', thesis: null, benchmark: 'SPY', holding_days: 30, actual_return: null,
      alpha: null, reflection: null, resolved_at: null, created_at: null, ...over,
    });

  describe('holdings-decisions', () => {
    it('keeps only the most recent decision per ticker', () => {
      const m = latestDecisionByTicker([
        d({ ticker: 'NVDA', run_date: '2026-06-20', conviction: 1 }),
        d({ ticker: 'NVDA', run_date: '2026-06-23', conviction: 4 }),
      ] as never);
      expect(m.get('NVDA')?.conviction).toBe(4);
    });

    it('returns decision tickers not in the held set, latest-first by run_date', () => {
      const out = proposedNotHeld(
        [
          d({ ticker: 'IWM', run_date: '2026-06-23', conviction: 2 }),
          d({ ticker: 'NVDA', run_date: '2026-06-23', conviction: 4 }),
        ] as never,
        new Set(['NVDA'])
      );
      expect(out.map((p) => p.ticker)).toEqual(['IWM']);
    });

    it('builds an analyst node key for the Pipeline deep-link', () => {
      expect(decisionNodeFor('qqq')).toBe('analyst/QQQ');
    });
  });
  ```
- [ ] Run `cd frontend/olympus && pnpm test holdings-decisions` — expect FAIL.
- [ ] Implement `holdings-decisions.ts`:
  ```ts
  import type { TableRow } from '@/lib/database.types';

  export type DecisionLogRow = TableRow<'decision_log'>;

  export interface ProposedDecision {
    ticker: string;
    conviction: number | null;
    stance: string | null;
    runDate: string | null;
    node: string;
  }

  /** The Pipeline node (document_key) that explains a ticker's decision: its analyst memo. */
  export function decisionNodeFor(ticker: string): string {
    return `analyst/${ticker.toUpperCase()}`;
  }

  /** Most-recent decision per ticker, keyed by uppercase ticker (latest run_date wins). */
  export function latestDecisionByTicker(decisions: DecisionLogRow[]): Map<string, DecisionLogRow> {
    const m = new Map<string, DecisionLogRow>();
    for (const dec of decisions) {
      const t = String(dec.ticker || '').toUpperCase();
      if (!t) continue;
      const prev = m.get(t);
      if (!prev || String(dec.run_date || '') > String(prev.run_date || '')) m.set(t, dec);
    }
    return m;
  }

  /** Decision tickers the book does NOT hold — the "Proposed by the pipeline" shelf. */
  export function proposedNotHeld(
    decisions: DecisionLogRow[],
    heldTickers: Set<string>
  ): ProposedDecision[] {
    const held = new Set([...heldTickers].map((t) => t.toUpperCase()));
    const latest = latestDecisionByTicker(decisions);
    const out: ProposedDecision[] = [];
    for (const [ticker, dec] of latest) {
      if (held.has(ticker)) continue;
      out.push({
        ticker,
        conviction: dec.conviction,
        stance: dec.stance ?? null,
        runDate: dec.run_date ?? null,
        node: decisionNodeFor(ticker),
      });
    }
    return out.sort(
      (a, b) =>
        String(b.runDate || '').localeCompare(String(a.runDate || '')) ||
        a.ticker.localeCompare(b.ticker)
    );
  }
  ```
- [ ] Run `cd frontend/olympus && pnpm test holdings-decisions` — expect PASS.
- [ ] Commit: `git add -A && git commit -m "feat(olympus): decision-aware holdings helpers (latest/proposed/node)"`

---

### Task 4: Rebuild AllocationsPositionsTable — conviction-first, decision-aware, grouped by sector, re-tokenized

**Files:**
- Modify: `frontend/olympus/components/portfolio/AllocationsPositionsTable.tsx` (full rework of the prop contract, header, body, row; lines 16–219. Keep the former-positions logic at 32–67 with the additive-field defaults below.)
- Test: `frontend/olympus/components/portfolio/AllocationsPositionsTable.test.tsx` (new)

**Interfaces:**
- Consumes: `ReconciledPosition[]` (Phase 0), `ConvictionMeter` + `SignedConvictionBadge` (Phase 0), `RiskEnvelopeCell` (Task 2), `buildPipelineHref` (Phase 0), widened `Position.sector_bucket`/`conviction`/`stop_loss_pct`/`target_pct_gain`/`horizon_days`/`day_change_pct`/`unrealized_pnl_pct`.
- Produces: a new prop contract on the default export:
  ```ts
  AllocationsPositionsTable(props: {
    reconciliation: BookReconciliation;                       // F3 rows + headline
    positionHistory: PositionHistoryRow[];
    positionEvents: DashboardPositionEvent[];
    thesisById: Map<string, Thesis>;
    lastUpdated: string | null;
    decisionByTicker: Map<string, TableRow<'decision_log'>>;  // from Task 3
  })
  ```
  (Replaces the old `positions: Position[]` prop with `reconciliation` + `decisionByTicker`; `AllocationsTab` is updated in Task 6.)

**Steps:**
- [ ] Write failing test `AllocationsPositionsTable.test.tsx`:
  ```tsx
  import { createElement } from 'react';
  import { renderToStaticMarkup } from 'react-dom/server';
  import { describe, it, expect } from 'vitest';
  import AllocationsPositionsTable from './AllocationsPositionsTable';
  import type { BookReconciliation, ReconciledPosition } from '@/lib/book-reconciliation';
  import type { Thesis } from '@/lib/types';
  import type { TableRow } from '@/lib/database.types';

  function pos(over: Partial<ReconciledPosition>): ReconciledPosition {
    return {
      ticker: 'NVDA', name: 'NVIDIA', type: 'LONG', weight_actual: 30, weight_target: null,
      weight_delta: null, current_price: 100, entry_price: 90, entry_date: null, rationale: '',
      thesis_ids: [], category: 'equity', pm_notes: '', stats: {}, normalizedWeight: 22.5,
      conviction: 3, sector_bucket: 'Technology', stop_loss_pct: -8, target_pct_gain: 15,
      horizon_days: 30, day_change_pct: 1.2, unrealized_pnl_pct: 11.1, ...over,
    };
  }
  const recon = (rows: ReconciledPosition[]): BookReconciliation => ({
    rows, investedPct: 75, cashPct: 25, grossPct: 75, netPct: 75,
  });
  const decision = () =>
    ({ ticker: 'NVDA', run_date: '2026-06-23', stance: 'buy', conviction: 4, status: 'pending' } as unknown as TableRow<'decision_log'>);
  const baseProps = {
    positionHistory: [], positionEvents: [], thesisById: new Map<string, Thesis>(),
    lastUpdated: '2026-06-23', decisionByTicker: new Map<string, TableRow<'decision_log'>>(),
  };

  describe('AllocationsPositionsTable', () => {
    it('renders normalized weights (not raw 150%-summing weight_actual)', () => {
      const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
        ...baseProps, reconciliation: recon([pos({ normalizedWeight: 22.5 })]),
      }));
      expect(html).toContain('22.5%');
      expect(html).not.toContain('30.0%');
    });

    it('groups rows under their sector_bucket header', () => {
      const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
        ...baseProps, reconciliation: recon([pos({ ticker: 'NVDA', sector_bucket: 'Technology' })]),
      }));
      expect(html).toContain('Technology');
    });

    it('drops the Name and Category column headers', () => {
      const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
        ...baseProps, reconciliation: recon([pos({})]),
      }));
      expect(html).not.toContain('>Name<');
      expect(html).not.toContain('>Category<');
    });

    it('shows a signed decision badge for a held position with a decision', () => {
      const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
        ...baseProps, reconciliation: recon([pos({ ticker: 'NVDA' })]),
        decisionByTicker: new Map([['NVDA', decision()]]),
      }));
      expect(html).toContain('+4');
      expect(html).toContain('/pipeline?'); // contextual deep-link
    });

    it('uses no off-palette blue/purple literals', () => {
      const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
        ...baseProps, reconciliation: recon([pos({})]),
      }));
      expect(html).not.toContain('59,130,246');
      expect(html).not.toContain('a78bfa');
    });
  });
  ```
- [ ] Run `cd frontend/olympus && pnpm test AllocationsPositionsTable` — expect FAIL (props mismatch / behavior).
- [ ] Rework `AllocationsPositionsTable.tsx`. Concretely:
  - Imports: add `import { ConvictionMeter } from '@/components/shared/conviction-meter';`, `import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';`, `import RiskEnvelopeCell from '@/components/portfolio/RiskEnvelopeCell';`, `import { buildPipelineHref } from '@/lib/pipeline-links';`, `import type { BookReconciliation, ReconciledPosition } from '@/lib/book-reconciliation';`, `import type { TableRow } from '@/lib/database.types';`, `import { ExternalLink } from 'lucide-react';`. Keep `pnlColor` from `@/components/ui`; drop the `Badge` import (ticker becomes a plain span) and the `formatAllocationCategory` import (Category column dropped).
  - Replace the prop block + sort (lines 16–30):
    ```tsx
    export default function AllocationsPositionsTable(props: {
      reconciliation: BookReconciliation;
      positionHistory: PositionHistoryRow[];
      positionEvents: DashboardPositionEvent[];
      thesisById: Map<string, Thesis>;
      lastUpdated: string | null;
      decisionByTicker: Map<string, TableRow<'decision_log'>>;
    }) {
      const { reconciliation, positionHistory, positionEvents, thesisById, lastUpdated, decisionByTicker } = props;
      const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
      const [showInactive, setShowInactive] = useState(false);

      // Conviction-first within each sector; ties broken by normalized weight.
      const sorted = useMemo(
        () => [...reconciliation.rows].sort(
          (a, b) => (b.conviction ?? 0) - (a.conviction ?? 0) || b.normalizedWeight - a.normalizedWeight
        ),
        [reconciliation.rows]
      );
    ```
  - In the former-positions `inactive` map (lines 46–61) extend the synthesized object with the additive fields so it satisfies `ReconciledPosition`: add `normalizedWeight: 0, conviction: null, stop_loss_pct: null, target_pct_gain: null, horizon_days: null, sector_bucket: null` and type the array as `ReconciledPosition[]`.
  - `maxWeight` over normalized weight: `const maxWeight = sorted.length ? Math.max(...sorted.map((p) => p.normalizedWeight)) : 0;`
  - Group by sector (after `allRows`):
    ```tsx
    const grouped = useMemo(() => {
      const m = new Map<string, ReconciledPosition[]>();
      for (const p of sorted) {
        const key = p.sector_bucket ?? 'Unclassified';
        const arr = m.get(key) ?? [];
        arr.push(p);
        m.set(key, arr);
      }
      return [...m.entries()].sort(
        (a, b) =>
          b[1].reduce((s, p) => s + p.normalizedWeight, 0) -
          a[1].reduce((s, p) => s + p.normalizedWeight, 0)
      );
    }, [sorted]);
    ```
  - `hasTargets` keeps the existing guard (`sorted.some((p) => p.weight_target != null)`). Set `colCount` to the exact number of `<th>` rendered (no targets: 9 — Ticker, Weight, Conviction, Day, Unrealized, Risk, Thesis, Decision, chevron; with targets: 11). Render a single quiet affordance below the table when `!hasTargets`: `<p className="px-4 py-3 text-xs text-text-muted md:px-6">No target book yet — runs without a PM rebalance leave targets unset.</p>`.
  - New header row (drop Name + Category; add Conviction, Day, Unrealized, Risk, Decision):
    ```tsx
    <tr className="text-text-muted text-xs uppercase tracking-wider">
      <th className="pl-2 pr-2 py-3 text-left md:pl-4">Ticker</th>
      <th className="px-2 py-3 text-right md:px-3">Weight</th>
      <th className="px-2 py-3 text-center md:px-3">Conviction</th>
      <th className="hidden px-3 py-3 text-right md:table-cell">Day</th>
      <th className="hidden px-3 py-3 text-right md:table-cell">Unrealized</th>
      <th className="hidden px-3 py-3 text-right lg:table-cell">Risk (stop ↔ target)</th>
      {hasTargets && (
        <>
          <th className="hidden px-3 py-3 text-right md:table-cell">Target</th>
          <th className="hidden px-3 py-3 text-right md:table-cell">Δ vs target</th>
        </>
      )}
      <th className="hidden max-w-[200px] px-3 py-3 text-left xl:table-cell">Thesis</th>
      <th className="px-2 py-3 text-center md:px-3">Decision</th>
      <th className="w-8 px-2 py-3 md:px-3" />
    </tr>
    ```
  - Body: iterate `grouped`, emitting a sector header row then the position rows:
    ```tsx
    {grouped.map(([sector, rows]) => (
      <Fragment key={sector}>
        <tr className="bg-bg-secondary/60">
          <td colSpan={colCount} className="px-2 py-2 text-[11px] font-semibold uppercase tracking-wider text-text-secondary md:px-4">
            {sector}
            <span className="ml-2 font-mono text-text-muted">
              {rows.reduce((s, p) => s + p.normalizedWeight, 0).toFixed(1)}%
            </span>
          </td>
        </tr>
        {rows.map((p) => { /* row below */ })}
      </Fragment>
    ))}
    ```
  - Per-row (drop the `style={{ backgroundImage: bar … }}` rgba background entirely):
    ```tsx
    const isExpanded = expandedTicker === p.ticker;
    const pctOfMax = maxWeight > 0 ? (p.normalizedWeight / maxWeight) * 100 : 0;
    const vsTarget =
      hasTargets && p.weight_target != null ? p.normalizedWeight - p.weight_target : null;
    const dec = decisionByTicker.get(p.ticker.toUpperCase());
    return (
      <Fragment key={p.ticker}>
        <tr
          onClick={() => setExpandedTicker(isExpanded ? null : p.ticker)}
          className={`cursor-pointer transition-colors hover:bg-white/[0.03] ${isExpanded ? 'bg-white/[0.02]' : ''}`}
        >
          <td className="pl-2 pr-2 py-3 md:pl-4">
            <span className="font-mono font-semibold text-text-primary">{p.ticker}</span>
          </td>
          <td className="px-2 py-3 text-right md:px-3">
            <div className="flex items-center justify-end gap-2">
              <span className="font-mono tabular-nums font-medium">{p.normalizedWeight.toFixed(1)}%</span>
              <span className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-bg-secondary md:inline-block" aria-hidden>
                <span className="block h-full rounded-full bg-[var(--accent)]/40" style={{ width: `${pctOfMax}%` }} />
              </span>
            </div>
          </td>
          <td className="px-2 py-3 text-center md:px-3">
            {p.conviction != null ? (
              <div className="flex justify-center">
                <ConvictionMeter value={Math.min(3, Math.max(1, p.conviction))} max={3} srLabel={`${p.ticker} conviction`} />
              </div>
            ) : (
              <span className="text-text-muted">—</span>
            )}
          </td>
          <td className={`hidden px-3 py-3 text-right font-mono tabular-nums text-xs md:table-cell ${pnlColor(p.day_change_pct)}`}>
            {p.day_change_pct != null ? `${p.day_change_pct >= 0 ? '+' : ''}${p.day_change_pct.toFixed(1)}%` : '—'}
          </td>
          <td className={`hidden px-3 py-3 text-right font-mono tabular-nums text-xs md:table-cell ${pnlColor(p.unrealized_pnl_pct)}`}>
            {p.unrealized_pnl_pct != null ? `${p.unrealized_pnl_pct >= 0 ? '+' : ''}${p.unrealized_pnl_pct.toFixed(1)}%` : '—'}
          </td>
          <td className="hidden px-3 py-3 lg:table-cell">
            <RiskEnvelopeCell stopLossPct={p.stop_loss_pct} targetPctGain={p.target_pct_gain} horizonDays={p.horizon_days} />
          </td>
          {hasTargets && (
            <>
              <td className="hidden px-3 py-3 text-right font-mono tabular-nums text-xs text-text-secondary md:table-cell">
                {p.weight_target != null ? `${p.weight_target.toFixed(1)}%` : '—'}
              </td>
              <td className={`hidden px-3 py-3 text-right font-mono tabular-nums text-xs md:table-cell ${
                vsTarget != null && Math.abs(vsTarget) >= 0.05 ? pnlColor(-vsTarget) : 'text-text-muted'
              }`}>
                {vsTarget != null && Math.abs(vsTarget) >= 0.05
                  ? `${vsTarget > 0 ? '+' : ''}${vsTarget.toFixed(1)}pp`
                  : '—'}
              </td>
            </>
          )}
          <td className="hidden max-w-[200px] px-3 py-3 text-xs text-text-secondary xl:table-cell">
            {thesisNames(p.thesis_ids, thesisById)}
          </td>
          <td className="px-2 py-3 text-center md:px-3">
            {dec && dec.conviction != null ? (
              <a
                href={buildPipelineHref({ date: dec.run_date, stage: 'selection', node: `analyst/${p.ticker.toUpperCase()}` })}
                onClick={(e) => e.stopPropagation()}
                className="inline-flex items-center gap-1 text-[var(--accent)] hover:underline"
                title={`Open ${p.ticker} decision in Pipeline`}
              >
                <SignedConvictionBadge value={dec.conviction} />
                <ExternalLink size={12} aria-hidden />
              </a>
            ) : (
              <span className="text-text-muted">—</span>
            )}
          </td>
          <td className="px-2 py-3 text-text-muted md:px-3">{isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</td>
        </tr>
        {isExpanded && (
          <tr className="bg-white/[0.02]">
            <td colSpan={colCount} className="px-4 py-5 md:px-6 md:py-6">
              <PositionDrilldown key={p.ticker} position={p} positionHistory={positionHistory} positionEvents={positionEvents} thesisById={thesisById} asOfDate={lastUpdated} mode="allocations" />
            </td>
          </tr>
        )}
      </Fragment>
    );
    ```
  - Replace the empty-state guard `positions.length === 0` (line 207) with `reconciliation.rows.length === 0`.
  - Re-tokenize the header checkbox `accent-fin-blue` (line 89) to `accent-[var(--accent)]`.
- [ ] Run `cd frontend/olympus && pnpm test AllocationsPositionsTable` — expect PASS.
- [ ] Run `cd frontend/olympus && pnpm test` — only `AllocationsTab` consumes this component (updated in Task 6); the full suite is otherwise unaffected at this point — expect green except the not-yet-updated `AllocationsTab` call site (typecheck only fails at build, not vitest). Proceed.
- [ ] Commit: `git add -A && git commit -m "refactor(olympus): conviction-first decision-aware holdings table (F3/F5/F6)"`

---

### Task 5: "Proposed by the pipeline" shelf

**Files:**
- Create: `frontend/olympus/components/portfolio/ProposedByPipelineShelf.tsx`
- Test: `frontend/olympus/components/portfolio/ProposedByPipelineShelf.test.tsx`

**Interfaces:**
- Consumes: `ProposedDecision[]` (Task 3), `SignedConvictionBadge` (Phase 0), `buildPipelineHref` (Phase 0).
- Produces: `ProposedByPipelineShelf({ proposed }: { proposed: ProposedDecision[] }): JSX.Element | null` — used by `AllocationsTab` (Task 6). Returns `null` when empty (per slop-guard: some elements are simply absent, not narrating emptiness).

**Steps:**
- [ ] Write failing test `ProposedByPipelineShelf.test.tsx`:
  ```tsx
  import { createElement } from 'react';
  import { renderToStaticMarkup } from 'react-dom/server';
  import { describe, it, expect } from 'vitest';
  import ProposedByPipelineShelf from './ProposedByPipelineShelf';
  import type { ProposedDecision } from '@/lib/holdings-decisions';

  const p = (over: Partial<ProposedDecision>): ProposedDecision => ({
    ticker: 'IWM', conviction: 2, stance: 'buy', runDate: '2026-06-23', node: 'analyst/IWM', ...over,
  });

  describe('ProposedByPipelineShelf', () => {
    it('lists not-held decision tickers with a deep-link', () => {
      const html = renderToStaticMarkup(createElement(ProposedByPipelineShelf, {
        proposed: [p({}), p({ ticker: 'QQQ', node: 'analyst/QQQ' })],
      }));
      expect(html).toContain('Proposed by the pipeline');
      expect(html).toContain('IWM');
      expect(html).toContain('QQQ');
      expect(html).toContain('/pipeline?');
    });

    it('renders nothing when there is nothing proposed', () => {
      const html = renderToStaticMarkup(createElement(ProposedByPipelineShelf, { proposed: [] }));
      expect(html).toBe('');
    });
  });
  ```
- [ ] Run `cd frontend/olympus && pnpm test ProposedByPipelineShelf` — expect FAIL.
- [ ] Implement `ProposedByPipelineShelf.tsx`:
  ```tsx
  'use client';

  import { ExternalLink } from 'lucide-react';
  import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
  import { buildPipelineHref } from '@/lib/pipeline-links';
  import type { ProposedDecision } from '@/lib/holdings-decisions';

  /**
   * Decision-log tickers the book does NOT hold — the pipeline's standing suggestions.
   * Each row deep-links to its analyst node in Pipeline. Absent (null) when empty.
   */
  export default function ProposedByPipelineShelf({ proposed }: { proposed: ProposedDecision[] }) {
    if (!proposed.length) return null;
    return (
      <section className="glass-card p-0 overflow-hidden">
        <div className="border-b border-border-subtle bg-bg-secondary px-4 py-3 md:px-6">
          <h3 className="text-sm font-semibold text-text-primary">Proposed by the pipeline</h3>
          <p className="mt-0.5 text-xs text-text-muted">
            Decisions on tickers the book does not hold — open the analyst memo to see why.
          </p>
        </div>
        <ul className="divide-y divide-border-subtle">
          {proposed.map((d) => (
            <li key={d.ticker} className="flex items-center justify-between gap-3 px-4 py-3 md:px-6">
              <div className="flex items-center gap-3">
                <span className="font-mono font-semibold text-text-primary">{d.ticker}</span>
                {d.conviction != null && <SignedConvictionBadge value={d.conviction} />}
                {d.stance && <span className="text-xs capitalize text-text-muted">{d.stance}</span>}
              </div>
              <a
                href={buildPipelineHref({ date: d.runDate, stage: 'selection', node: d.node })}
                className="inline-flex items-center gap-1 text-xs text-[var(--accent)] hover:underline"
              >
                Open in Pipeline
                <ExternalLink size={12} aria-hidden />
              </a>
            </li>
          ))}
        </ul>
      </section>
    );
  }
  ```
- [ ] Run `cd frontend/olympus && pnpm test ProposedByPipelineShelf` — expect PASS.
- [ ] Commit: `git add -A && git commit -m "feat(olympus): proposed-by-pipeline shelf for not-held decision tickers"`

---

### Task 6: Wire reconciliation + decisions through AllocationsTab and the portfolio shell

**Files:**
- Modify: `frontend/olympus/components/portfolio/tabs/AllocationsTab.tsx`
- Modify: `frontend/olympus/components/portfolio/PortfolioShellInner.tsx` (fetch decisions; source `investedPct`; thread the new props)
- Test: `frontend/olympus/components/portfolio/tabs/AllocationsTab.test.tsx` (new)

**Interfaces:**
- Consumes: `reconcileBook` (Phase 0), `fetchObservabilityData` (`lib/observability-queries.ts` → `{ decisions: TableRow<'decision_log'>[]; … }`), `latestDecisionByTicker` + `proposedNotHeld` (Task 3), `DashboardData.server_portfolio_metrics?.invested_pct` (`ServerPortfolioMetrics`) as `opts.investedPct`.
- Produces: `AllocationsTab` owns the reconciliation + decision plumbing; `PortfolioShellInner` passes `positions`, `investedPct`, and the fetched `decisions` down.

**Steps:**
- [ ] Write failing test `AllocationsTab.test.tsx` (inject `decisions` directly to avoid the network):
  ```tsx
  import { createElement } from 'react';
  import { renderToStaticMarkup } from 'react-dom/server';
  import { describe, it, expect } from 'vitest';
  import AllocationsTab from './AllocationsTab';
  import type { Position, Thesis } from '@/lib/types';
  import type { TableRow } from '@/lib/database.types';

  const position = (over: Partial<Position>): Position => ({
    ticker: 'NVDA', name: 'NVIDIA', type: 'LONG', weight_actual: 30, weight_target: null,
    weight_delta: null, current_price: 100, entry_price: 90, entry_date: null, rationale: '',
    thesis_ids: [], category: 'equity', pm_notes: '', stats: {}, conviction: 3,
    sector_bucket: 'Technology', ...over,
  });

  const base = {
    lastUpdated: '2026-06-23',
    positions: [position({ ticker: 'NVDA' }), position({ ticker: 'EWT', sector_bucket: 'International' })],
    investedPct: 75,
    decisions: [{ ticker: 'IWM', run_date: '2026-06-23', stance: 'buy', conviction: 2, status: 'pending' } as unknown as TableRow<'decision_log'>],
    positionHistory: [], positionEvents: [], thesisById: new Map<string, Thesis>(),
    effHistoryDate: '2026-06-23', onSelectHistoryDate: () => {}, onClearHistoryDate: () => {},
    showHistoryDateBanner: false, dateParam: null, historyMode: 'ticker' as const,
    setHistoryMode: () => {}, sleeveData: [], sleeveKeys: [], formatSleeveKey: (k: string) => k,
  };

  describe('AllocationsTab', () => {
    it('renders the reconciliation strip with normalized invested/cash', () => {
      const html = renderToStaticMarkup(createElement(AllocationsTab, base));
      expect(html).toContain('Invested');
      expect(html).toContain('75.0%');
      expect(html).toContain('Cash');
    });

    it('renders the proposed-by-pipeline shelf for not-held decision tickers', () => {
      const html = renderToStaticMarkup(createElement(AllocationsTab, base));
      expect(html).toContain('Proposed by the pipeline');
      expect(html).toContain('IWM');
    });
  });
  ```
- [ ] Run `cd frontend/olympus && pnpm test tabs/AllocationsTab` — expect FAIL.
- [ ] Rewrite `AllocationsTab.tsx` (new prop contract + internal reconciliation):
  ```tsx
  'use client';

  import { useMemo } from 'react';
  import type { DashboardPositionEvent, Position, PositionHistoryRow, Thesis } from '@/lib/types';
  import type { TableRow } from '@/lib/database.types';
  import type { SleeveStackMode } from '@/lib/portfolio-aggregates';
  import { reconcileBook } from '@/lib/book-reconciliation';
  import { latestDecisionByTicker, proposedNotHeld } from '@/lib/holdings-decisions';
  import AllocationsPositionsTable from '@/components/portfolio/AllocationsPositionsTable';
  import BookReconciliationStrip from '@/components/portfolio/BookReconciliationStrip';
  import ProposedByPipelineShelf from '@/components/portfolio/ProposedByPipelineShelf';
  import SleeveHistorySection from '@/components/portfolio/SleeveHistorySection';

  export default function AllocationsTab(props: {
    lastUpdated: string | null;
    positions: Position[];
    investedPct: number | null;
    decisions: TableRow<'decision_log'>[];
    positionHistory: PositionHistoryRow[];
    positionEvents: DashboardPositionEvent[];
    thesisById: Map<string, Thesis>;
    effHistoryDate: string | null;
    onSelectHistoryDate: (iso: string) => void;
    onClearHistoryDate: () => void;
    showHistoryDateBanner: boolean;
    dateParam: string | null;
    historyMode: SleeveStackMode;
    setHistoryMode: (m: SleeveStackMode) => void;
    sleeveData: Array<Record<string, number | string>>;
    sleeveKeys: string[];
    formatSleeveKey: (k: string) => string;
  }) {
    const {
      lastUpdated, positions, investedPct, decisions, positionHistory, positionEvents,
      thesisById, effHistoryDate, onSelectHistoryDate, onClearHistoryDate,
      showHistoryDateBanner, dateParam, historyMode, setHistoryMode,
      sleeveData, sleeveKeys, formatSleeveKey,
    } = props;

    const reconciliation = useMemo(() => reconcileBook(positions, { investedPct }), [positions, investedPct]);
    const decisionByTicker = useMemo(() => latestDecisionByTicker(decisions), [decisions]);
    const heldTickers = useMemo(
      () => new Set(reconciliation.rows.map((p) => p.ticker.toUpperCase())),
      [reconciliation.rows]
    );
    const proposed = useMemo(() => proposedNotHeld(decisions, heldTickers), [decisions, heldTickers]);

    return (
      <div className="space-y-10">
        <BookReconciliationStrip reconciliation={reconciliation} asOfDate={lastUpdated} />
        <AllocationsPositionsTable
          reconciliation={reconciliation}
          positionHistory={positionHistory}
          positionEvents={positionEvents}
          thesisById={thesisById}
          lastUpdated={lastUpdated}
          decisionByTicker={decisionByTicker}
        />
        <ProposedByPipelineShelf proposed={proposed} />
        <SleeveHistorySection
          historyMode={historyMode}
          setHistoryMode={setHistoryMode}
          sleeveData={sleeveData}
          sleeveKeys={sleeveKeys}
          formatSleeveKey={formatSleeveKey}
          effHistoryDate={effHistoryDate}
          onSelectHistoryDate={onSelectHistoryDate}
          showHistoryDateBanner={showHistoryDateBanner}
          dateParam={dateParam}
          onClearHistoryDate={onClearHistoryDate}
        />
      </div>
    );
  }
  ```
- [ ] Update `PortfolioShellInner.tsx`:
  - Add imports: `import { fetchObservabilityData } from '@/lib/observability-queries';` and add `TableRow` to the `database.types` import (`import type { TableRow } from '@/lib/database.types';`).
  - After the `positions` memo (line 61) add:
    ```tsx
    const investedPct = data?.server_portfolio_metrics?.invested_pct ?? null;
    const [decisions, setDecisions] = useState<TableRow<'decision_log'>[]>([]);
    useEffect(() => {
      let alive = true;
      fetchObservabilityData()
        .then((d) => { if (alive) setDecisions(d.decisions); })
        .catch(() => { if (alive) setDecisions([]); }); // fail-soft: shelf + badges simply absent
      return () => { alive = false; };
    }, []);
    ```
    (`useState`/`useEffect` are already imported at line 3.)
  - In the `tab === 'holdings'` render block (lines 238–254) add two props to `<AllocationsTab … />`: `investedPct={investedPct}` and `decisions={decisions}`. Keep `positions={positions}` and all existing props.
- [ ] Run `cd frontend/olympus && pnpm test tabs/AllocationsTab` — expect PASS.
- [ ] Run `cd frontend/olympus && pnpm test` — full suite green (`PortfolioSectionNav`, `portfolio-aggregates`, `portfolio-url-state`, `DecisionQuality`, the new Holdings suites).
- [ ] Commit: `git add -A && git commit -m "feat(olympus): wire book reconciliation + decisions into Holdings tab"`

---

### Task 7: Re-tokenize PositionDrilldown (F5) + collapse SleeveHistorySection on single-day data

**Files:**
- Modify: `frontend/olympus/components/portfolio/PositionDrilldown.tsx` (lines 42–56 marker colors; 194–196 window-button active class; 275–276 gradient stops; 327 area stroke; 337 line stroke)
- Modify: `frontend/olympus/components/portfolio/SleeveHistorySection.tsx` (lines 41/48/55 mode buttons; line 62 banner; chart gate)
- Test: `frontend/olympus/components/portfolio/SleeveHistorySection.test.tsx` (new)

**Interfaces:**
- Consumes: `sleeveData` (`Array<Record<string, number | string>>`) already passed by `AllocationsTab`. Single-day predicate = `sleeveData.length < 2`.
- Produces: no new exported symbols; behavioral + token change only.

**Steps:**
- [ ] Re-tokenize `PositionDrilldown.tsx` (presentational; no test cycle — verified by grep at the end):
  - Line 337 price `Line` `stroke="#a78bfa"` → `stroke="var(--accent)"`.
  - Lines 275–276 gradient `stopColor="rgb(59,130,246)"` (both stops) → `stopColor="var(--accent)"`.
  - Line 327 weight `Area` `stroke="rgb(59,130,246)"` → `stroke="var(--accent)"`.
  - Lines 194–196 active window-button `bg-fin-blue/20 text-fin-blue border-fin-blue/40` → `bg-[var(--accent)]/15 text-[var(--accent)] border-[var(--accent)]/40`.
  - Line 45 `eventMarkerColor` ADD branch `return '#38bdf8';` → `return 'var(--accent)';`; line 53 `eventLabelClass` ADD branch `return 'text-fin-blue';` → `return 'text-[var(--accent)]';`. Leave OPEN/EXIT/TRIM (green/red/amber) — they encode signed/caution semantics and stay.
- [ ] Write failing test `SleeveHistorySection.test.tsx`:
  ```tsx
  import { createElement } from 'react';
  import { renderToStaticMarkup } from 'react-dom/server';
  import { describe, it, expect } from 'vitest';
  import SleeveHistorySection from './SleeveHistorySection';

  const base = {
    historyMode: 'ticker' as const, setHistoryMode: () => {}, sleeveKeys: ['NVDA'],
    formatSleeveKey: (k: string) => k, effHistoryDate: '2026-06-23',
    onSelectHistoryDate: () => {}, showHistoryDateBanner: false, dateParam: null,
    onClearHistoryDate: () => {},
  };

  describe('SleeveHistorySection', () => {
    it('collapses to an element-specific empty state on single-day data', () => {
      const html = renderToStaticMarkup(createElement(SleeveHistorySection, {
        ...base, sleeveData: [{ date: '2026-06-23', NVDA: 30 }],
      }));
      expect(html).toContain('Sleeve history builds daily');
      expect(html).not.toContain('Sleeve weights stacked over time');
    });

    it('renders the stacked chart when ≥2 dates exist', () => {
      const html = renderToStaticMarkup(createElement(SleeveHistorySection, {
        ...base, sleeveData: [{ date: '2026-06-23', NVDA: 30 }, { date: '2026-06-24', NVDA: 31 }],
      }));
      expect(html).toContain('Sleeve weights stacked over time');
    });
  });
  ```
- [ ] Run `cd frontend/olympus && pnpm test SleeveHistorySection` — expect FAIL.
- [ ] Update `SleeveHistorySection.tsx`: re-tokenize the three mode buttons (lines 41/48/55) `bg-fin-blue/20 text-fin-blue` → `bg-[var(--accent)]/15 text-[var(--accent)]`, and the date banner (line 62) `border-fin-blue/30 bg-fin-blue/10` → `border-[var(--accent)]/30 bg-[var(--accent)]/10`. Then gate the chart on `sleeveData.length >= 2`:
  ```tsx
  const enoughHistory = sleeveData.length >= 2;
  // …replace the chart <div> (lines 76–84) with:
  {enoughHistory ? (
    <div className="h-[380px]" aria-label="Sleeve weights stacked over time">
      <SleeveStackedChart
        data={sleeveData}
        keys={sleeveKeys}
        formatKey={formatSleeveKey}
        selectedDate={effHistoryDate}
        onChartDateSelect={onSelectHistoryDate}
      />
    </div>
  ) : (
    <p className="py-8 text-center text-sm text-text-muted">
      Sleeve history builds daily — one snapshot so far. The stacked weight chart appears once a second day is recorded.
    </p>
  )}
  ```
- [ ] Run `cd frontend/olympus && pnpm test SleeveHistorySection` — expect PASS.
- [ ] Verify F5 purge: `cd frontend/olympus && grep -RnE "59,130,246|a78bfa|38bdf8|fin-blue" components/portfolio/` — expect NO matches in `AllocationsPositionsTable.tsx`, `PositionDrilldown.tsx`, `SleeveHistorySection.tsx`. (If `SleeveStackedChart` or other untouched files match, leave them — they are out of this surface's F5 target set.)
- [ ] Commit: `git add -A && git commit -m "refactor(olympus): re-tokenize Holdings charts to cyan + sleeve empty-state (F5)"`

---

### Task 8: Retire PositionRiskTab from System (diagnostics now live on Holdings)

**Files:**
- Modify: the observability/System tab host that mounts `PositionRiskTab` (locate the mount; the System surface is `components/system/how-olympus-works.tsx` plus the observability route components in `components/observability/`).
- Delete: `frontend/olympus/components/observability/PositionRiskTab.tsx` (and its test if one exists)
- Test: update whichever System/observability test references the Position-risk tab.

**Interfaces:**
- Consumes: nothing new. Removal only; the data it showed (`stop_loss_pct`/`target_pct_gain`/`horizon_days`/`conviction`) now renders inline in the Holdings table (Task 4 `RiskEnvelopeCell` + `ConvictionMeter`).

**Steps:**
- [ ] Locate the mount + tab registration: `cd frontend/olympus && grep -RnE "PositionRiskTab|Position risk|position-risk|'risk'|\"risk\"" components/ app/ --include='*.tsx' --include='*.ts'`.
- [ ] Remove the import, the tab-key/label entry, and the `<PositionRiskTab … />` render from the observability tab host. Leave `AttributionTab` untouched (it relocates to Performance in the Phase-3 plan, not here).
- [ ] Delete `components/observability/PositionRiskTab.tsx`. If `PositionRiskTab.test.tsx` exists, delete it; otherwise update the host tab test to drop the Position-risk assertion (and any tab-enum exhaustiveness list).
- [ ] Run `cd frontend/olympus && pnpm test` — expect green (no remaining import of the deleted module).
- [ ] Commit: `git add -A && git commit -m "refactor(olympus): retire System Position-risk tab (relocated to Holdings)"`

---

### Task 9: Full-suite verification + lint

**Files:** none (verification only).

**Steps:**
- [ ] Run `cd frontend/olympus && pnpm test` — entire vitest suite green.
- [ ] Run the project's TS lint/format (per `package.json`; e.g. `pnpm lint` if defined, else `npx eslint . && npx prettier --check .`). Fix any introduced violations.
- [ ] Run `cd frontend/olympus && npx tsc --noEmit` (or the project typecheck script) — no type errors from the new props/imports (verify the `AllocationsTab` call site in `PortfolioShellInner` matches the new contract).
- [ ] Manual gate (per `/score` before PR): confirm the F5 grep is clean; the per-row normalized weights sum (within sectors) to the strip's invested %; the shelf is absent (not empty-narrating) when no not-held decisions exist; each Pipeline link targets `analyst/{TICKER}` for ITS row; the conviction pip meter and signed badge are the only accents on their cells.
- [ ] No commit. Open the PR on a `task/<N>-slug` branch (file the Holdings tracking issue if none exists) or include `Fixes #<N>` in the body. Reference backend deps in the PR body: `weight_pct` seeding (issue #1) and `thesis_id` canonicalization (issue #3) from the Phase-0 backend issue list — Holdings ships correct on the F3/F4 query-layer interim today and tightens when those land.
