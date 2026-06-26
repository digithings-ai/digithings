---
# Portfolio · Theses Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (- [ ]) syntax.

**Goal:** Rebuild Portfolio · Theses (`/portfolio/theses`) as a two-tier research ledger — Market views (conviction cards bound to `confidence`) + Vehicle theses (ticker list, "Unlinked expressions" until linked) — with a trustworthy detail page (claim/conviction/horizon/status header, side-by-side validation/invalidation criteria, F4-joined holdings, slim Pipeline provenance strip), and retire the orphaned `StrategyThesisPanel`.

**Architecture:** This is a **Phase 2** surface that consumes Phase 0 contract outputs (widened `Thesis` type + `mapThesisRow`, `ConvictionMeter`, canonical `AsOfBadge`, `buildPipelineHref`/`stageForDocumentKey`, `reconcileBook`, widened `thesis-id.ts`). Theses already flow to components via `data.portfolio.strategy.theses: Thesis[]` and holdings via `data.positions: Position[]` (each carrying `thesis_ids: string[]`); no new data fetch is added here. We replace the `ThesesTab` calendar/table landing with two calm sections, replace the `ThesisDetailPageInner` 5-table stack with the ledger artifact, and delete `StrategyThesisPanel.tsx` (zero importers — confirmed dead since the redesign removed its mount).

**Tech Stack:** Next.js 16 static export (`output: export`, `basePath /olympus`), React 19, Tailwind v4 (`@theme` tokens, `[data-theme]`), lucide-react, vitest. No recharts on this surface (single-day data; history degrades to one quiet line).

## Global Constraints

- **Static export only** — no server components with runtime data; all data arrives via `useDashboard()` (client context). Routes under `/portfolio/theses/[thesisId]` are pre-rendered via `fetchThesisStaticParams()` — do not add new dynamic route params.
- **Tailwind v4 design tokens, inherited exactly** — dark-first; cyan-phosphor `--accent` `#3DD6C4`; `font-display` (Instrument Serif) for claims/headlines; Geist sans/mono; `glass-card`; `bg-bg-primary`/`bg-bg-secondary`/`bg-bg-glass`; `border-border-subtle`; `text-text-primary`/`text-text-secondary`/`text-text-muted`.
- **F5 token rule (verbatim):** cyan `--accent` `#3DD6C4` for links/chrome/the single conviction encoding/the live-fresh dot only; `fin-green`/`fin-red` **strictly** for signed financial values; `fin-amber` for caution/stale/carried/mixed-regime; **no gradients** beyond the existing faint regime wash; **no decorative numbering**. This surface specifically purges: the gradient panel headers (`bg-gradient-to-br`), the red "Risk radar" gradient (`bg-gradient-to-b from-fin-red/5`), and all `text-fin-blue` link/icon literals (→ `text-accent`).
- **Tests stay green** — 150+ plumbing/page tests must pass. `npm test` runs `vitest run` from `frontend/olympus`. Page-level tests are updated as part of this work.
- **Empty-state discipline** — element-specific calm copy ("tracking from 2026-06-23", "Unlinked expressions"); never an em-dash placeholder, a 1-row table-over-time, or a single-dot chart. History on single-day data collapses to one quiet line, it does not render an empty table.
- **Slop guards** — the conviction meter is the only accent on its row and encodes exactly one quantity (`confidence`); "Link to Pipeline" is contextual (a thesis → ITS provenance day), never a cloned generic button; the two tiers are driven by `thesis_kind`, not stamped symmetry.
- **PM-voice copy (F8)** — no operator strings ("Expand for DB snapshots", "(database)", "No thesis row in the database"). Investor-readable everywhere.
- **Conventional commits** — `feat|fix|refactor|chore(olympus): …`. Every change traces to a GitHub issue; backend dependencies are noted with `Fixes #<N>` placeholders to file.

### Phase 0 contract consumed by this plan (do NOT redefine — these land in Phase 0)

```ts
// lib/types.ts — widened Thesis
export interface Thesis {
  id: string; name: string; vehicle: string | null; invalidation: string | null;
  status: string | null; notes: string | null;
  confidence: number | null;        // 0.0–1.0
  horizon: string | null;
  thesis_kind: string | null;       // 'market' | 'vehicle'
  validation_criteria: string[];
  invalidation_criteria: string[];
  linked_market_thesis_id: string | null;
}
// lib/types.ts — Position gains: conviction?: number | null (1–3), sector_bucket?: string | null, etc.

// lib/thesis-id.ts (widened in Phase 0; strips ^VEHICLE- and uppercases)
export function normalizeThesisId(id: string | null | undefined): string;
export function thesisIdEquals(a: string | null | undefined, b: string | null | undefined): boolean;
export function joinPositionsToThesis<T extends { thesis_ids: string[] }>(
  positions: T[], thesisId: string | null | undefined
): T[];

// components/shared/conviction-meter.tsx (F6)
export function ConvictionMeter(
  { value, max, srLabel }: { value: number; max?: number; srLabel: string }
): JSX.Element;   // unsigned cyan pip meter; max defaults to 3

// components/shared/as-of-badge.tsx (F7 canonical; overview/as-of-badge.tsx re-exports it)
export function AsOfBadge(
  { date, createdAt, now, staleHours }: { date: string | null; createdAt?: string | null; now?: Date; staleHours?: number }
): JSX.Element | null;

// lib/pipeline-links.ts (F2 deep-link grammar)
export type PipelineStage = 'inputs' | 'research' | 'synthesis' | 'selection' | 'decision';
export function buildPipelineHref(
  opts: { date?: string | null; stage?: PipelineStage | null; node?: string | null }
): string;        // → /pipeline?date=…&stage=…&node=<document_key>
export function stageForDocumentKey(documentKey: string): PipelineStage | null;
```

If Phase 0 has not landed when a task starts, the task is **blocked** — do not stub these locally. Verify with `git grep -n "joinPositionsToThesis" lib/thesis-id.ts` and `git grep -n "ConvictionMeter" components/shared/` before starting Task 2.

### Files this plan touches

- **Create:** `lib/theses-ledger.ts` (+ `.test.ts`) — pure split/sort/grouping helpers for the two tiers and detail lookups.
- **Create:** `components/portfolio/theses/MarketViewCard.tsx`, `components/portfolio/theses/VehicleThesisRow.tsx`, `components/portfolio/theses/ThesisCriteriaColumns.tsx`, `components/portfolio/theses/ThesisHoldingsExpressing.tsx`, `components/portfolio/theses/ThesisProvenanceStrip.tsx` — presentational pieces.
- **Rewrite:** `components/portfolio/theses/ThesesPageInner.tsx` (landing), `components/portfolio/theses/ThesisDetailPageInner.tsx` (detail).
- **Modify:** `components/legacy-spa-redirect.tsx` (point `/strategy` no-thesis → theses landing), `lib/portfolio-aggregates.ts` (export book weight per thesis using F4 join, reused by landing).
- **Delete:** `components/portfolio/StrategyThesisPanel.tsx`, `components/portfolio/tabs/ThesesTab.tsx` (landing absorbs it).
- **Test:** `lib/theses-ledger.test.ts`, update existing page tests that import the deleted/rewritten components (grep gate in Task 7).

All component/lib paths below are under `frontend/olympus/`.

---

## Task 1: Ledger helpers — split tiers, sort, link, book weight

Pure functions that drive the two-tier landing and the detail joins. No React. TDD.

**Files:**
- Create: `frontend/olympus/lib/theses-ledger.ts`
- Test: `frontend/olympus/lib/theses-ledger.test.ts`

**Interfaces:**
- Consumes: `Thesis` (widened, Phase 0 `lib/types.ts`); `thesisIdEquals`, `normalizeThesisId` (Phase 0 `lib/thesis-id.ts`).
- Produces:
  - `splitTheses(theses: Thesis[]): { market: Thesis[]; vehicle: Thesis[] }` — explicit `thesis_kind === 'vehicle'` → vehicle; everything else (incl. `null`/`'market'`/unknown) → market, so a ledger never hides a thesis.
  - `sortByConfidenceDesc(theses: Thesis[]): Thesis[]` — desc by `confidence`; nulls last; stable by `name`.
  - `groupVehicleTheses(vehicle: Thesis[], market: Thesis[]): VehicleThesisGroup[]` where `VehicleThesisGroup = { marketId: string | null; marketName: string | null; theses: Thesis[] }` — groups vehicle theses by `linked_market_thesis_id`; matched groups carry parent `name` and sort by parent confidence desc; unmatched/`null` land in a trailing group with `marketId: null` (rendered "Unlinked expressions").
  - `findThesisById(theses: Thesis[], id: string): Thesis | null` — `thesisIdEquals`-based lookup.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/olympus/lib/theses-ledger.test.ts
import { describe, expect, it } from 'vitest';
import { splitTheses, sortByConfidenceDesc, groupVehicleTheses, findThesisById } from './theses-ledger';
import type { Thesis } from './types';

function mk(p: Partial<Thesis>): Thesis {
  return {
    id: 'X', name: 'X', vehicle: null, invalidation: null, status: 'ACTIVE', notes: null,
    confidence: null, horizon: null, thesis_kind: null,
    validation_criteria: [], invalidation_criteria: [], linked_market_thesis_id: null,
    ...p,
  };
}

describe('splitTheses', () => {
  it('routes vehicle kind to vehicle, everything else to market', () => {
    const out = splitTheses([
      mk({ id: 'MT1', thesis_kind: 'market' }),
      mk({ id: 'vehicle-ewt', thesis_kind: 'vehicle' }),
      mk({ id: 'LEGACY', thesis_kind: null }),
    ]);
    expect(out.market.map((t) => t.id)).toEqual(['MT1', 'LEGACY']);
    expect(out.vehicle.map((t) => t.id)).toEqual(['vehicle-ewt']);
  });
});

describe('sortByConfidenceDesc', () => {
  it('orders by confidence desc, nulls last, stable by name', () => {
    const out = sortByConfidenceDesc([
      mk({ id: 'a', name: 'Apple', confidence: 0.4 }),
      mk({ id: 'b', name: 'Beta', confidence: null }),
      mk({ id: 'c', name: 'Cobalt', confidence: 0.9 }),
      mk({ id: 'd', name: 'Delta', confidence: null }),
    ]);
    expect(out.map((t) => t.id)).toEqual(['c', 'a', 'b', 'd']);
  });
});

describe('groupVehicleTheses', () => {
  const market = [
    mk({ id: 'MT1', name: 'AI capex', confidence: 0.9 }),
    mk({ id: 'MT2', name: 'EM rotation', confidence: 0.5 }),
  ];
  it('groups vehicles under their linked market thesis, parents sorted by confidence desc', () => {
    const vehicle = [
      mk({ id: 'vehicle-ewt', thesis_kind: 'vehicle', linked_market_thesis_id: 'MT2' }),
      mk({ id: 'vehicle-nvda', thesis_kind: 'vehicle', linked_market_thesis_id: 'MT1' }),
    ];
    const groups = groupVehicleTheses(vehicle, market);
    expect(groups.map((g) => g.marketId)).toEqual(['MT1', 'MT2']);
    expect(groups[0].marketName).toBe('AI capex');
    expect(groups[0].theses.map((t) => t.id)).toEqual(['vehicle-nvda']);
  });
  it('places unmatched and null-link vehicles in a trailing unlinked group', () => {
    const vehicle = [
      mk({ id: 'vehicle-ijr', thesis_kind: 'vehicle', linked_market_thesis_id: null }),
      mk({ id: 'vehicle-gone', thesis_kind: 'vehicle', linked_market_thesis_id: 'MISSING' }),
      mk({ id: 'vehicle-nvda', thesis_kind: 'vehicle', linked_market_thesis_id: 'MT1' }),
    ];
    const groups = groupVehicleTheses(vehicle, market);
    const last = groups[groups.length - 1];
    expect(last.marketId).toBeNull();
    expect(last.theses.map((t) => t.id).sort()).toEqual(['vehicle-gone', 'vehicle-ijr']);
  });
});

describe('findThesisById', () => {
  it('matches via normalized thesis-id equality (vehicle- prefix tolerant)', () => {
    const found = findThesisById([mk({ id: 'vehicle-ewt', name: 'EWT' })], 'ewt');
    expect(found?.id).toBe('vehicle-ewt');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/olympus && npx vitest run lib/theses-ledger.test.ts`
Expected: FAIL — `Failed to resolve import "./theses-ledger"`.

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/olympus/lib/theses-ledger.ts
import { thesisIdEquals } from './thesis-id';
import type { Thesis } from './types';

/** Two-tier split: explicit 'vehicle' kind → vehicle; everything else → market (never hide a thesis). */
export function splitTheses(theses: Thesis[]): { market: Thesis[]; vehicle: Thesis[] } {
  const market: Thesis[] = [];
  const vehicle: Thesis[] = [];
  for (const t of theses) {
    if ((t.thesis_kind ?? '').toLowerCase() === 'vehicle') vehicle.push(t);
    else market.push(t);
  }
  return { market, vehicle };
}

/** Confidence descending; null confidence sorted last; ties broken by name for stability. */
export function sortByConfidenceDesc(theses: Thesis[]): Thesis[] {
  return [...theses].sort((a, b) => {
    const ca = a.confidence;
    const cb = b.confidence;
    if (ca == null && cb == null) return a.name.localeCompare(b.name);
    if (ca == null) return 1;
    if (cb == null) return -1;
    if (cb !== ca) return cb - ca;
    return a.name.localeCompare(b.name);
  });
}

export interface VehicleThesisGroup {
  marketId: string | null;
  marketName: string | null;
  theses: Thesis[];
}

/** Group vehicle theses under their linked market thesis; unmatched/null land in a trailing unlinked group. */
export function groupVehicleTheses(vehicle: Thesis[], market: Thesis[]): VehicleThesisGroup[] {
  const sortedMarket = sortByConfidenceDesc(market);
  const linked = new Map<string, Thesis[]>();
  const unlinked: Thesis[] = [];
  for (const v of vehicle) {
    const parent = v.linked_market_thesis_id
      ? sortedMarket.find((m) => thesisIdEquals(m.id, v.linked_market_thesis_id)) ?? null
      : null;
    if (!parent) {
      unlinked.push(v);
      continue;
    }
    if (!linked.has(parent.id)) linked.set(parent.id, []);
    linked.get(parent.id)!.push(v);
  }
  const groups: VehicleThesisGroup[] = [];
  for (const m of sortedMarket) {
    const rows = linked.get(m.id);
    if (rows && rows.length) {
      groups.push({ marketId: m.id, marketName: m.name, theses: rows });
    }
  }
  if (unlinked.length) {
    groups.push({ marketId: null, marketName: null, theses: unlinked });
  }
  return groups;
}

/** Normalized-id lookup (tolerant of `vehicle-`/case differences via thesisIdEquals). */
export function findThesisById(theses: Thesis[], id: string): Thesis | null {
  return theses.find((t) => thesisIdEquals(t.id, id)) ?? null;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/olympus && npx vitest run lib/theses-ledger.test.ts`
Expected: PASS — 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/olympus/lib/theses-ledger.ts frontend/olympus/lib/theses-ledger.test.ts
git commit -m "feat(olympus): theses-ledger tier split + grouping helpers"
```

---

## Task 2: Book-weight-per-thesis primitive (F4 join + market rollup)

Theses landing shows "the book weight it drives" per view. The existing `aggregateWeightByThesis` (in `lib/portfolio-aggregates.ts:117`) buckets `weight_actual` by `thesis_ids` keyed on `normalizeThesisId`. Per the F4 contract, `normalizeThesisId` is widened in Phase 0 to strip `^VEHICLE-`, so `positions.thesis_id='ewt'` and `theses.thesis_id='vehicle-ewt'` collapse to one key — the existing aggregate becomes correct **for free**. This task adds a tested wrapper that resolves a `Thesis` to its book weight, rolling a market view up over its linked vehicle theses (holdings are usually tagged at the vehicle level).

**Files:**
- Modify: `frontend/olympus/lib/portfolio-aggregates.ts` (append only)
- Test: `frontend/olympus/lib/theses-ledger.test.ts` (extend — same module concern)

**Interfaces:**
- Consumes: `aggregateWeightByThesis(positions: Pick<Position,'weight_actual'|'thesis_ids'>[]): Map<string, number>` (existing `lib/portfolio-aggregates.ts:117`); `normalizeThesisId`, `thesisIdEquals` (already imported at `portfolio-aggregates.ts:2`); `Thesis` (already imported at `:3`).
- Produces (in `portfolio-aggregates.ts`):
  - `bookWeightForThesis(thesis: Thesis, weightByThesisId: Map<string, number>, allTheses: Thesis[]): number` — vehicle thesis → its own bucket; market thesis → its own bucket plus the summed weight of every vehicle thesis whose `linked_market_thesis_id` equals it.

- [ ] **Step 1: Write the failing test (append to theses-ledger.test.ts)**

```ts
// append to frontend/olympus/lib/theses-ledger.test.ts
import { aggregateWeightByThesis, bookWeightForThesis } from './portfolio-aggregates';

describe('bookWeightForThesis', () => {
  const all = [
    mk({ id: 'MT1', thesis_kind: 'market' }),
    mk({ id: 'vehicle-nvda', thesis_kind: 'vehicle', linked_market_thesis_id: 'MT1' }),
    mk({ id: 'vehicle-ewt', thesis_kind: 'vehicle', linked_market_thesis_id: null }),
  ];
  const weightByThesisId = aggregateWeightByThesis([
    { weight_actual: 30, thesis_ids: ['vehicle-nvda'] },
    { weight_actual: 12, thesis_ids: ['vehicle-ewt'] },
    { weight_actual: 8, thesis_ids: ['MT1'] },
  ]);

  it('a vehicle thesis reports its own bucket weight', () => {
    const v = all.find((t) => t.id === 'vehicle-nvda')!;
    expect(bookWeightForThesis(v, weightByThesisId, all)).toBeCloseTo(30, 5);
  });

  it('a market thesis rolls up its own weight plus its linked vehicles', () => {
    const m = all.find((t) => t.id === 'MT1')!;
    // MT1 direct 8 + vehicle-nvda 30 = 38
    expect(bookWeightForThesis(m, weightByThesisId, all)).toBeCloseTo(38, 5);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/olympus && npx vitest run lib/theses-ledger.test.ts`
Expected: FAIL — `bookWeightForThesis is not a function` / import unresolved.

- [ ] **Step 3: Write minimal implementation (append to portfolio-aggregates.ts)**

`portfolio-aggregates.ts` already imports `normalizeThesisId`, `thesisIdEquals` (line 2) and `Thesis` (line 3 — `import type { Position, PositionHistoryRow, Thesis } from './types';`). Do **not** add duplicate imports; only append the function:

```ts
// append to frontend/olympus/lib/portfolio-aggregates.ts (existing imports already cover Thesis/thesisIdEquals/normalizeThesisId)

/**
 * Book weight a single thesis drives, using the F4-normalized weightByThesisId map.
 * Vehicle thesis → its own bucket. Market thesis → its own bucket plus every linked
 * vehicle thesis's bucket (holdings are usually tagged at the vehicle level).
 */
export function bookWeightForThesis(
  thesis: Thesis,
  weightByThesisId: Map<string, number>,
  allTheses: Thesis[]
): number {
  let total = weightByThesisId.get(normalizeThesisId(thesis.id)) ?? 0;
  if ((thesis.thesis_kind ?? '').toLowerCase() !== 'vehicle') {
    for (const t of allTheses) {
      if ((t.thesis_kind ?? '').toLowerCase() !== 'vehicle') continue;
      if (thesisIdEquals(t.linked_market_thesis_id, thesis.id)) {
        total += weightByThesisId.get(normalizeThesisId(t.id)) ?? 0;
      }
    }
  }
  return total;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/olympus && npx vitest run lib/theses-ledger.test.ts`
Expected: PASS — 7 tests pass (5 from Task 1 + 2 here).

- [ ] **Step 5: Commit**

```bash
git add frontend/olympus/lib/portfolio-aggregates.ts frontend/olympus/lib/theses-ledger.test.ts
git commit -m "feat(olympus): bookWeightForThesis rollup over F4-normalized join"
```

---

## Task 3: MarketViewCard + VehicleThesisRow (presentational)

Two presentational pieces for the landing. Pure JSX, no test cycle, real code only.

**Files:**
- Create: `frontend/olympus/components/portfolio/theses/MarketViewCard.tsx`
- Create: `frontend/olympus/components/portfolio/theses/VehicleThesisRow.tsx`

**Interfaces:**
- Consumes: `Thesis` (Phase 0); `ConvictionMeter` (Phase 0 `components/shared/conviction-meter.tsx`).
- Produces:
  - `MarketViewCard({ thesis, bookWeightPct, href }: { thesis: Thesis; bookWeightPct: number; href: string }): JSX.Element`
  - `VehicleThesisRow({ thesis, bookWeightPct, href }: { thesis: Thesis; bookWeightPct: number; href: string }): JSX.Element`

A `confidence` of 0.0–1.0 maps to a 4-pip cyan meter via `Math.round(confidence * 4)` so 0.7 shows 3/4 pips. `CONFIDENCE_PIPS = 4` is reused identically in Tasks 3 and 6.

- [ ] **Step 1: Write MarketViewCard**

```tsx
// frontend/olympus/components/portfolio/theses/MarketViewCard.tsx
'use client';

import Link from 'next/link';
import type { Thesis } from '@/lib/types';
import { ConvictionMeter } from '@/components/shared/conviction-meter';

const CONFIDENCE_PIPS = 4;

function confidenceToPips(confidence: number | null): number {
  if (confidence == null) return 0;
  return Math.max(0, Math.min(CONFIDENCE_PIPS, Math.round(confidence * CONFIDENCE_PIPS)));
}

function isNonActive(status: string | null): boolean {
  const s = (status ?? '').toLowerCase();
  return Boolean(s) && !s.includes('active');
}

export function MarketViewCard({
  thesis,
  bookWeightPct,
  href,
}: {
  thesis: Thesis;
  bookWeightPct: number;
  href: string;
}) {
  const pips = confidenceToPips(thesis.confidence);
  const confidenceLabel =
    thesis.confidence != null ? `${Math.round(thesis.confidence * 100)}% confidence` : 'Confidence not set';

  return (
    <Link
      href={href}
      className="group glass-card block p-5 transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
    >
      <div className="flex items-start justify-between gap-4">
        <h3 className="font-display text-xl leading-snug text-text-primary group-hover:text-white">
          {thesis.name}
        </h3>
        {isNonActive(thesis.status) ? (
          <span className="shrink-0 rounded-full border border-fin-amber/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-fin-amber">
            {thesis.status}
          </span>
        ) : null}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
        <div className="flex items-center gap-2">
          <ConvictionMeter value={pips} max={CONFIDENCE_PIPS} srLabel={confidenceLabel} />
          <span className="text-xs text-text-muted tabular-nums">{confidenceLabel}</span>
        </div>
        {thesis.horizon ? (
          <span className="rounded-md border border-border-subtle px-2 py-0.5 text-[11px] text-text-secondary">
            {thesis.horizon}
          </span>
        ) : null}
        <span className="ml-auto text-sm text-text-secondary">
          <span className="text-text-muted">drives </span>
          <span className="font-mono font-semibold tabular-nums text-text-primary">
            {bookWeightPct.toFixed(1)}%
          </span>
          <span className="text-text-muted"> of the book</span>
        </span>
      </div>
    </Link>
  );
}
```

- [ ] **Step 2: Write VehicleThesisRow**

```tsx
// frontend/olympus/components/portfolio/theses/VehicleThesisRow.tsx
'use client';

import Link from 'next/link';
import type { Thesis } from '@/lib/types';
import { ConvictionMeter } from '@/components/shared/conviction-meter';

const CONFIDENCE_PIPS = 4;

function confidenceToPips(confidence: number | null): number {
  if (confidence == null) return 0;
  return Math.max(0, Math.min(CONFIDENCE_PIPS, Math.round(confidence * CONFIDENCE_PIPS)));
}

export function VehicleThesisRow({
  thesis,
  bookWeightPct,
  href,
}: {
  thesis: Thesis;
  bookWeightPct: number;
  href: string;
}) {
  const pips = confidenceToPips(thesis.confidence);
  const confidenceLabel =
    thesis.confidence != null ? `${Math.round(thesis.confidence * 100)}% confidence` : 'Confidence not set';

  return (
    <Link
      href={href}
      className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
    >
      {thesis.vehicle ? (
        <span className="w-16 shrink-0 font-mono text-sm font-semibold text-text-primary">
          {thesis.vehicle}
        </span>
      ) : null}
      <span className="min-w-0 flex-1 truncate text-sm text-text-secondary" title={thesis.name}>
        {thesis.name}
      </span>
      <ConvictionMeter value={pips} max={CONFIDENCE_PIPS} srLabel={confidenceLabel} />
      <span className="w-16 shrink-0 text-right font-mono text-sm tabular-nums text-text-primary">
        {bookWeightPct.toFixed(1)}%
      </span>
    </Link>
  );
}
```

- [ ] **Step 3: Type-check the two new files**

Run: `cd frontend/olympus && npx tsc --noEmit`
Expected: PASS — no errors (the files compile against Phase 0 types/components).

- [ ] **Step 4: Commit**

```bash
git add frontend/olympus/components/portfolio/theses/MarketViewCard.tsx frontend/olympus/components/portfolio/theses/VehicleThesisRow.tsx
git commit -m "feat(olympus): MarketViewCard + VehicleThesisRow conviction tiles"
```

---

## Task 4: Rewrite the Theses landing (ThesesPageInner)

Replace the calendar/`ThesesTab` landing with two calm sections: **Market views** (conviction cards, confidence desc) and **Vehicle theses** (grouped by linked market view; "Unlinked expressions" trailing group). History collapses to one quiet "tracking from {firstDate}" line. Delete `ThesesTab.tsx`.

**Files:**
- Rewrite: `frontend/olympus/components/portfolio/theses/ThesesPageInner.tsx`
- Delete: `frontend/olympus/components/portfolio/tabs/ThesesTab.tsx`

**Interfaces:**
- Consumes: `useDashboard()` → `data.portfolio.strategy.theses: Thesis[]`, `data.positions: Position[]` (`weight_actual`, `thesis_ids`), `data.position_history: { date }[]`, `data.portfolio.meta.last_updated`; `splitTheses`, `sortByConfidenceDesc`, `groupVehicleTheses` (Task 1); `aggregateWeightByThesis`, `bookWeightForThesis` (Task 2); `MarketViewCard`, `VehicleThesisRow` (Task 3); `PortfolioSectionNav` (existing, `active="theses"`), `SUBPAGE_MAX` (existing = `'max-w-[1600px] mx-auto w-full px-4 md:px-6'`), `AtlasLoader` (existing).
- Produces: the `/portfolio/theses` landing body. Detail href: `/portfolio/theses/${encodeURIComponent(thesis.id)}` (existing static-param route).

- [ ] **Step 1: Rewrite ThesesPageInner.tsx**

```tsx
// frontend/olympus/components/portfolio/theses/ThesesPageInner.tsx
'use client';

import { useMemo } from 'react';
import { useDashboard } from '@/lib/dashboard-context';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import AtlasLoader from '@/components/AtlasLoader';
import { MarketViewCard } from '@/components/portfolio/theses/MarketViewCard';
import { VehicleThesisRow } from '@/components/portfolio/theses/VehicleThesisRow';
import { splitTheses, sortByConfidenceDesc, groupVehicleTheses } from '@/lib/theses-ledger';
import { aggregateWeightByThesis, bookWeightForThesis } from '@/lib/portfolio-aggregates';

function thesisHref(id: string): string {
  return `/portfolio/theses/${encodeURIComponent(id)}`;
}

export default function ThesesPageInner() {
  const { data, loading, error } = useDashboard();

  const theses = useMemo(() => data?.portfolio?.strategy?.theses ?? [], [data]);
  const positions = useMemo(() => data?.positions ?? [], [data]);
  const trackingSince = useMemo(() => {
    const dates = (data?.position_history ?? []).map((r) => r.date).filter(Boolean).sort();
    return dates[0] ?? data?.portfolio?.meta?.last_updated ?? null;
  }, [data]);

  const weightByThesisId = useMemo(
    () =>
      aggregateWeightByThesis(
        positions.map((p) => ({ weight_actual: p.weight_actual, thesis_ids: p.thesis_ids }))
      ),
    [positions]
  );

  const { market, vehicle } = useMemo(() => splitTheses(theses), [theses]);
  const marketSorted = useMemo(() => sortByConfidenceDesc(market), [market]);
  const vehicleGroups = useMemo(() => groupVehicleTheses(vehicle, market), [vehicle, market]);

  if (loading) return <AtlasLoader />;
  if (error || !data)
    return (
      <div className="flex items-center justify-center h-screen text-fin-red">
        {error || 'Failed to load'}
      </div>
    );

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="theses" />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-12 py-6 md:py-8`}>
        {/* Market views */}
        <section className="space-y-4">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="font-display text-2xl text-text-primary">Market views</h2>
            <p className="text-xs text-text-muted">Ordered by conviction</p>
          </div>
          {marketSorted.length === 0 ? (
            <div className="glass-card p-6 text-sm text-text-muted">
              No market views recorded yet.
            </div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {marketSorted.map((t) => (
                <MarketViewCard
                  key={t.id}
                  thesis={t}
                  bookWeightPct={bookWeightForThesis(t, weightByThesisId, theses)}
                  href={thesisHref(t.id)}
                />
              ))}
            </div>
          )}
        </section>

        {/* Vehicle theses */}
        <section className="space-y-4">
          <h2 className="font-display text-2xl text-text-primary">Vehicle theses</h2>
          {vehicleGroups.length === 0 ? (
            <div className="glass-card p-6 text-sm text-text-muted">
              No single-name theses recorded yet.
            </div>
          ) : (
            <div className="space-y-6">
              {vehicleGroups.map((group) => (
                <div key={group.marketId ?? '_unlinked'} className="space-y-2">
                  <div className="flex items-baseline gap-2 px-1">
                    <h3 className="text-sm font-semibold text-text-secondary">
                      {group.marketName ?? 'Unlinked expressions'}
                    </h3>
                    {group.marketId === null ? (
                      <span className="text-xs text-text-muted">not yet tied to a market view</span>
                    ) : (
                      <span className="text-xs text-text-muted">expresses this view</span>
                    )}
                  </div>
                  <div className="glass-card divide-y divide-border-subtle overflow-hidden p-0">
                    {group.theses.map((t) => (
                      <VehicleThesisRow
                        key={t.id}
                        thesis={t}
                        bookWeightPct={bookWeightForThesis(t, weightByThesisId, theses)}
                        href={thesisHref(t.id)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* History — one quiet line on single-day data */}
        {trackingSince ? (
          <p className="text-xs text-text-muted">
            Tracking theses from <span className="font-mono">{trackingSince}</span>.
          </p>
        ) : null}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Delete the retired ThesesTab**

```bash
git rm frontend/olympus/components/portfolio/tabs/ThesesTab.tsx
```

- [ ] **Step 3: Verify no dangling ThesesTab importers + type-check**

Run: `cd frontend/olympus && git grep -n "tabs/ThesesTab" -- '*.tsx' '*.ts' | grep -v node_modules`
Expected: no output (`ThesesPageInner` was the only importer).

Run: `cd frontend/olympus && npx tsc --noEmit`
Expected: PASS — no errors.

- [ ] **Step 4: Run the full suite**

Run: `cd frontend/olympus && npm test`
Expected: PASS, except any test asserting old `ThesesTab` copy — note it; fix in Task 7 (do not patch inline now).

- [ ] **Step 5: Commit**

```bash
git add frontend/olympus/components/portfolio/theses/ThesesPageInner.tsx
git commit -m "refactor(olympus): two-tier theses landing (market views + vehicle theses)"
```

---

## Task 5: Detail building blocks — criteria columns, holdings, provenance

Three presentational pieces for the detail page. Pure JSX. No test cycle, real code only.

**Files:**
- Create: `frontend/olympus/components/portfolio/theses/ThesisCriteriaColumns.tsx`
- Create: `frontend/olympus/components/portfolio/theses/ThesisHoldingsExpressing.tsx`
- Create: `frontend/olympus/components/portfolio/theses/ThesisProvenanceStrip.tsx`

**Interfaces:**
- Consumes: `Position` (Phase 0); `buildPipelineHref`, `stageForDocumentKey` (Phase 0 `lib/pipeline-links.ts`); `ConvictionMeter` (Phase 0); lucide `Check`, `X`, `ArrowUpRight`.
- Produces:
  - `ThesisCriteriaColumns({ validation, invalidation }: { validation: string[]; invalidation: string[] }): JSX.Element`
  - `ThesisHoldingsExpressing({ positions }: { positions: Position[] }): JSX.Element` — positions pre-filtered by the caller (Task 6).
  - `ThesisProvenanceStrip({ date, documentKey }: { date: string | null; documentKey: string }): JSX.Element` — one contextual Pipeline link; never renders markdown.

- [ ] **Step 1: Write ThesisCriteriaColumns**

"What confirms this" uses `fin-green`, "What breaks this" uses `fin-red` — these encode a directional financial judgment of the thesis (confirm/break), permitted under F5. Per-column element-specific empty-state.

```tsx
// frontend/olympus/components/portfolio/theses/ThesisCriteriaColumns.tsx
'use client';

import { Check, X } from 'lucide-react';

function CriteriaList({
  title,
  items,
  tone,
  emptyLabel,
}: {
  title: string;
  items: string[];
  tone: 'confirm' | 'break';
  emptyLabel: string;
}) {
  const accent = tone === 'confirm' ? 'text-fin-green' : 'text-fin-red';
  const Icon = tone === 'confirm' ? Check : X;
  return (
    <div className="glass-card p-5">
      <h3 className="mb-4 text-sm font-semibold text-text-primary">{title}</h3>
      {items.length === 0 ? (
        <p className="text-xs text-text-muted">{emptyLabel}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-3 text-sm leading-relaxed text-text-secondary">
              <Icon size={15} className={`mt-0.5 shrink-0 ${accent}`} aria-hidden />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ThesisCriteriaColumns({
  validation,
  invalidation,
}: {
  validation: string[];
  invalidation: string[];
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <CriteriaList
        title="What confirms this"
        items={validation}
        tone="confirm"
        emptyLabel="No confirmation criteria recorded for this thesis yet."
      />
      <CriteriaList
        title="What breaks this"
        items={invalidation}
        tone="break"
        emptyLabel="No invalidation criteria recorded for this thesis yet."
      />
    </div>
  );
}
```

- [ ] **Step 2: Write ThesisHoldingsExpressing**

```tsx
// frontend/olympus/components/portfolio/theses/ThesisHoldingsExpressing.tsx
'use client';

import Link from 'next/link';
import type { Position } from '@/lib/types';
import { ConvictionMeter } from '@/components/shared/conviction-meter';

export function ThesisHoldingsExpressing({ positions }: { positions: Position[] }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
        Holdings expressing this thesis
      </h2>
      {positions.length === 0 ? (
        <p className="text-sm text-text-muted">No current holdings are tagged to this thesis.</p>
      ) : (
        <div className="glass-card divide-y divide-border-subtle overflow-hidden p-0">
          {positions.map((p) => (
            <Link
              key={p.ticker}
              href={`/portfolio?ticker=${encodeURIComponent(p.ticker)}`}
              className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
            >
              <span className="w-16 shrink-0 font-mono text-sm font-semibold text-text-primary">
                {p.ticker}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm text-text-secondary" title={p.name}>
                {p.name}
              </span>
              {p.conviction != null ? (
                <ConvictionMeter value={p.conviction} max={3} srLabel={`conviction ${p.conviction} of 3`} />
              ) : null}
              <span className="w-16 shrink-0 text-right font-mono text-sm tabular-nums text-text-primary">
                {p.weight_actual.toFixed(1)}%
              </span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Write ThesisProvenanceStrip**

```tsx
// frontend/olympus/components/portfolio/theses/ThesisProvenanceStrip.tsx
'use client';

import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { buildPipelineHref, stageForDocumentKey } from '@/lib/pipeline-links';

export function ThesisProvenanceStrip({
  date,
  documentKey,
}: {
  date: string | null;
  documentKey: string;
}) {
  if (!date) return null;
  const stage = stageForDocumentKey(documentKey);
  const href = buildPipelineHref({ date, stage, node: documentKey });
  return (
    <section className="flex flex-wrap items-center gap-2 border-t border-border-subtle pt-4 text-sm">
      <span className="text-text-muted">Provenance</span>
      <span className="font-mono text-xs text-text-secondary">{date}</span>
      <Link href={href} className="ml-auto inline-flex items-center gap-1 text-accent hover:underline">
        Open the pipeline day
        <ArrowUpRight size={14} aria-hidden />
      </Link>
    </section>
  );
}
```

- [ ] **Step 4: Type-check**

Run: `cd frontend/olympus && npx tsc --noEmit`
Expected: PASS — no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/olympus/components/portfolio/theses/ThesisCriteriaColumns.tsx frontend/olympus/components/portfolio/theses/ThesisHoldingsExpressing.tsx frontend/olympus/components/portfolio/theses/ThesisProvenanceStrip.tsx
git commit -m "feat(olympus): thesis-detail building blocks (criteria/holdings/provenance)"
```

---

## Task 6: Rewrite the Theses detail (ThesisDetailPageInner)

Replace the 5-table stack with the ledger artifact: claim/conviction/horizon/status header (serif claim, one cyan conviction meter, horizon chip, status only when non-ACTIVE, an `AsOfBadge`), two criteria columns, "Holdings expressing this thesis" via the F4 join, and the slim Provenance strip. `_unlinked` keeps its honest note + holdings. No DB-snapshot tables, no markdown re-render, no network thesis-history fetch.

**Files:**
- Rewrite: `frontend/olympus/components/portfolio/theses/ThesisDetailPageInner.tsx`

**Interfaces:**
- Consumes: `useDashboard()` → `data.portfolio.strategy.theses: Thesis[]`, `data.positions: Position[]`, `data.portfolio.meta.last_updated`; `findThesisById` (Task 1); `joinPositionsToThesis` (Phase 0 `lib/thesis-id.ts`); `ConvictionMeter`, `AsOfBadge` (Phase 0); `ThesisCriteriaColumns`, `ThesisHoldingsExpressing`, `ThesisProvenanceStrip` (Task 5); `PortfolioSectionNav`, `SUBPAGE_MAX`, `AtlasLoader` (existing). `CONFIDENCE_PIPS = 4` matches Task 3.
- Produces: the `/portfolio/theses/[thesisId]` detail body. Provenance `documentKey` = `'digest'` (the day's thesis-bearing node; `stageForDocumentKey('digest')` → `'synthesis'`).

- [ ] **Step 1: Rewrite ThesisDetailPageInner.tsx**

```tsx
// frontend/olympus/components/portfolio/theses/ThesisDetailPageInner.tsx
'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { useDashboard } from '@/lib/dashboard-context';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import AtlasLoader from '@/components/AtlasLoader';
import { ConvictionMeter } from '@/components/shared/conviction-meter';
import { AsOfBadge } from '@/components/shared/as-of-badge';
import { ThesisCriteriaColumns } from '@/components/portfolio/theses/ThesisCriteriaColumns';
import { ThesisHoldingsExpressing } from '@/components/portfolio/theses/ThesisHoldingsExpressing';
import { ThesisProvenanceStrip } from '@/components/portfolio/theses/ThesisProvenanceStrip';
import { findThesisById } from '@/lib/theses-ledger';
import { joinPositionsToThesis } from '@/lib/thesis-id';

const CONFIDENCE_PIPS = 4;

function confidenceToPips(confidence: number | null): number {
  if (confidence == null) return 0;
  return Math.max(0, Math.min(CONFIDENCE_PIPS, Math.round(confidence * CONFIDENCE_PIPS)));
}

function isNonActive(status: string | null): boolean {
  const s = (status ?? '').toLowerCase();
  return Boolean(s) && !s.includes('active');
}

export default function ThesisDetailPageInner({ thesisId }: { thesisId: string }) {
  const { data, loading, error } = useDashboard();

  const theses = useMemo(() => data?.portfolio?.strategy?.theses ?? [], [data]);
  const positions = useMemo(() => data?.positions ?? [], [data]);
  const lastUpdated = data?.portfolio?.meta?.last_updated ?? null;

  const thesis = useMemo(
    () => (thesisId === '_unlinked' ? null : findThesisById(theses, thesisId)),
    [theses, thesisId]
  );

  const expressingPositions = useMemo(() => {
    if (thesisId === '_unlinked') {
      return positions.filter((p) => !p.thesis_ids || p.thesis_ids.length === 0);
    }
    return joinPositionsToThesis(positions, thesisId);
  }, [positions, thesisId]);

  if (loading) return <AtlasLoader />;
  if (error || !data)
    return (
      <div className="flex items-center justify-center min-h-[40vh] text-fin-red">
        {error || 'Failed to load'}
      </div>
    );

  if (thesisId !== '_unlinked' && !thesis) {
    return (
      <div className="flex min-h-full flex-col">
        <PortfolioSectionNav active="theses" />
        <div className={`${SUBPAGE_MAX} space-y-4 py-8`}>
          <Link
            href="/portfolio/theses"
            className="inline-flex items-center gap-2 text-sm text-accent hover:underline"
          >
            <ArrowLeft size={16} /> Back to Theses
          </Link>
          <p className="text-text-muted">
            We don&apos;t have a thesis on record for <span className="font-mono">{thesisId}</span>.
          </p>
        </div>
      </div>
    );
  }

  // _unlinked branch — honest grouping note + the holdings list.
  if (thesisId === '_unlinked') {
    return (
      <div className="flex min-h-full flex-col">
        <PortfolioSectionNav active="theses" />
        <div className={`${SUBPAGE_MAX} flex-1 space-y-8 py-6 md:py-8`}>
          <div className="space-y-3">
            <Link
              href="/portfolio/theses"
              className="inline-flex items-center gap-2 text-sm text-accent hover:underline"
            >
              <ArrowLeft size={16} /> Back to Theses
            </Link>
            <h1 className="font-display text-2xl text-text-primary">Unlinked expressions</h1>
            <p className="max-w-2xl text-sm leading-relaxed text-text-secondary">
              These holdings aren&apos;t yet tied to a named thesis. They&apos;ll roll up under a
              market view once the link is recorded.
            </p>
          </div>
          <ThesisHoldingsExpressing positions={expressingPositions} />
        </div>
      </div>
    );
  }

  const t = thesis!;
  const pips = confidenceToPips(t.confidence);
  const confidenceLabel =
    t.confidence != null ? `${Math.round(t.confidence * 100)}% confidence` : 'Confidence not set';

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="theses" />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-8 py-6 md:py-8`}>
        {/* Header — claim / conviction / horizon / status */}
        <div className="space-y-4">
          <Link
            href="/portfolio/theses"
            className="inline-flex items-center gap-2 text-sm text-accent hover:underline"
          >
            <ArrowLeft size={16} /> Back to Theses
          </Link>

          <div className="flex flex-wrap items-start justify-between gap-4">
            <h1 className="font-display text-3xl leading-tight text-text-primary">{t.name}</h1>
            <AsOfBadge date={lastUpdated} />
          </div>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <div className="flex items-center gap-2">
              <ConvictionMeter value={pips} max={CONFIDENCE_PIPS} srLabel={confidenceLabel} />
              <span className="text-xs text-text-muted tabular-nums">{confidenceLabel}</span>
            </div>
            {t.horizon ? (
              <span className="rounded-md border border-border-subtle px-2 py-0.5 text-[11px] text-text-secondary">
                {t.horizon}
              </span>
            ) : null}
            {t.vehicle ? (
              <span className="font-mono text-xs text-text-secondary">{t.vehicle}</span>
            ) : null}
            {isNonActive(t.status) ? (
              <span className="rounded-full border border-fin-amber/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-fin-amber">
                {t.status}
              </span>
            ) : null}
          </div>

          {t.notes ? (
            <p className="max-w-3xl text-sm leading-relaxed text-text-secondary">{t.notes}</p>
          ) : null}
        </div>

        {/* Two criteria columns — the credibility win */}
        <ThesisCriteriaColumns
          validation={t.validation_criteria}
          invalidation={t.invalidation_criteria}
        />

        {/* Holdings expressing this thesis (F4 join) */}
        <ThesisHoldingsExpressing positions={expressingPositions} />

        {/* Slim provenance strip → Pipeline day (never re-renders markdown) */}
        <ThesisProvenanceStrip date={lastUpdated} documentKey="digest" />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend/olympus && npx tsc --noEmit`
Expected: PASS — no errors.

- [ ] **Step 3: Verify dropped query helpers are not orphaned elsewhere**

The rewrite drops `getThesisHistoryById`, `aggregateThesisWeightsByDate`, `aggregateUnlinkedWeightsByDate`, `collectThesisRelatedDocLinks` from this page. They remain exported from `queries.ts` (harmless); do **not** delete them — out of scope.

Run: `cd frontend/olympus && git grep -n "getThesisHistoryById\|collectThesisRelatedDocLinks" -- '*.tsx' '*.ts' | grep -v node_modules | grep -v "lib/queries.ts"`
Expected: no references in this plan's rewritten files; any remaining references are in untouched files (fine).

- [ ] **Step 4: Run the full suite**

Run: `cd frontend/olympus && npm test`
Expected: PASS, except tests asserting old detail-page copy (fixed in Task 7).

- [ ] **Step 5: Commit**

```bash
git add frontend/olympus/components/portfolio/theses/ThesisDetailPageInner.tsx
git commit -m "refactor(olympus): theses detail as research-ledger artifact (criteria/holdings/provenance)"
```

---

## Task 7: Retire StrategyThesisPanel + reconcile redirects + page tests

Delete the orphaned `StrategyThesisPanel.tsx` (zero importers), point the `/strategy` no-thesis redirect at the canonical theses landing, and update tests so the suite stays green.

**Files:**
- Delete: `frontend/olympus/components/portfolio/StrategyThesisPanel.tsx`
- Modify: `frontend/olympus/components/legacy-spa-redirect.tsx` (the `/strategy` no-thesis branch)
- Test: update any failing tests surfaced by `npm test`

**Interfaces:**
- Consumes: nothing new.
- Produces: a green suite; `/strategy` (no `?thesis=`) → `/portfolio/theses`.

- [ ] **Step 1: Confirm StrategyThesisPanel is dead, then delete it**

Run: `cd frontend/olympus && git grep -n "StrategyThesisPanel" -- '*.tsx' '*.ts' | grep -v node_modules | grep -v "components/portfolio/StrategyThesisPanel.tsx"`
Expected: no output (no importers).

```bash
git rm frontend/olympus/components/portfolio/StrategyThesisPanel.tsx
```

(`StrategyThesisPanel` imports `renderDocumentMarkdownFromPayload`, which has other importers in `lib/queries.ts` and `lib/render-document-from-payload.ts` — deleting the panel does not orphan it.)

- [ ] **Step 2: Re-point the `/strategy` no-thesis redirect**

In `frontend/olympus/components/legacy-spa-redirect.tsx`, `StrategyToAnalysisInner` currently sends the no-thesis case to `/portfolio?tab=analysis`. Change only the final `router.replace`:

```tsx
// frontend/olympus/components/legacy-spa-redirect.tsx — inside StrategyToAnalysisInner useEffect
    const thesis = searchParams.get('thesis');
    if (thesis) {
      router.replace(`/portfolio/theses/${encodeURIComponent(thesis)}`);
      return;
    }
    router.replace('/portfolio/theses');
```

(Old line was `router.replace('/portfolio?tab=analysis');`.)

- [ ] **Step 3: Run the suite and locate failures**

Run: `cd frontend/olympus && npm test`
Expected: identify FAILs.

Run: `cd frontend/olympus && git grep -ln "ThesesTab\|StrategyThesisPanel\|tab=analysis" -- '*.test.ts' '*.test.tsx' | grep -v node_modules`
Expected: the list of test files needing updates.

- [ ] **Step 4: Update the failing tests to the new behavior**

For each failing test:
- A test importing the deleted `ThesesTab`/`StrategyThesisPanel`: delete the test file if its whole subject is the removed component; otherwise repoint imports/assertions at the new `ThesesPageInner`/`ThesisDetailPageInner` rendering (assert on copy "Market views" / "Vehicle theses" / "Unlinked expressions" / "What confirms this" / "What breaks this" / "Holdings expressing this thesis").
- The `legacy-spa-redirect` test asserting the no-thesis `/strategy` target: change expected from `/portfolio?tab=analysis` to `/portfolio/theses`.

Use the existing render style: `renderToStaticMarkup(createElement(...))` for pure components (see `components/overview/as-of-badge.test.tsx`); for context-bound pages, reuse the established `useDashboard` mock harness — find it via `git grep -l useDashboard -- '*.test.tsx'`. Do not invent a new harness.

- [ ] **Step 5: Re-run the full suite + lint + types until green**

Run: `cd frontend/olympus && npm test`
Expected: PASS — all green.

Run: `cd frontend/olympus && npx eslint . && npx tsc --noEmit`
Expected: PASS — lint + types clean.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/olympus/components frontend/olympus/lib
git commit -m "refactor(olympus): retire StrategyThesisPanel, route /strategy to theses ledger, update tests"
```

---

## Backend issues to file (note as `Fixes #<N>` in the relevant PR body)

1. **Canonicalize `positions.thesis_id`** to match `theses.thesis_id` (F4 durable fix). Interim handled by the widened `normalizeThesisId`; the durable fix removes the normalization crutch. — `Fixes #<thesis-id-canonicalize>`
2. **Populate `linked_market_thesis_id`** so the market→vehicle hierarchy has live data; until then `groupVehicleTheses` renders everything under "Unlinked expressions" (honest fallback already built). — `Fixes #<linked-market-thesis-id>`

(The `weight_pct` dedupe and `backtest-seed` backend issues are owned by Phase 0 / Phase 3, not this surface.)

---

## Self-review notes

- **Spec coverage:** Market views as conviction cards ordered by confidence desc (Tasks 3+4); Vehicle theses ticker list with "Unlinked expressions" group (Tasks 1 `groupVehicleTheses` + 4); detail header claim/conviction/horizon/status (Task 6); two criteria columns confirms/breaks (Tasks 5+6); "Holdings expressing this thesis" via F4 join (Tasks 5 + 6 `joinPositionsToThesis`); slim Provenance strip → Pipeline day, never re-rendering markdown (Task 5); history → one quiet line (Task 4); retire `StrategyThesisPanel` + route Analysis (Task 7); reuse F6 `ConvictionMeter` + F8 voice throughout; F5 token purge of gradients/blue (Global Constraints + every component uses `text-accent`/`fin-*`, no gradients). All covered.
- **No placeholders:** every code step is complete and grounded in real files (`SUBPAGE_MAX`, `data.portfolio.strategy.theses`, `data.positions`, `PortfolioSectionNav active="theses"`, the existing `aggregateWeightByThesis`).
- **Type consistency:** `confidenceToPips` + `CONFIDENCE_PIPS = 4` identical across MarketViewCard, VehicleThesisRow, ThesisDetailPageInner; `bookWeightForThesis(thesis, weightByThesisId, allTheses)` signature matches between Task 2 and Task 4 callers; `splitTheses`/`sortByConfidenceDesc`/`groupVehicleTheses`/`findThesisById` signatures match between Task 1 and Tasks 4/6.
- **Dependency gate:** Tasks 2–6 are blocked until Phase 0 lands the widened `Thesis`/`Position` types, widened `thesis-id.ts` (`joinPositionsToThesis`), `components/shared/conviction-meter.tsx`, `components/shared/as-of-badge.tsx`, `lib/pipeline-links.ts`. Task 1 needs only the widened `Thesis` type + `thesisIdEquals`.
