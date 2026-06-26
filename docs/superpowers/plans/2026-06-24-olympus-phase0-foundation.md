---
# Phase 0 — Foundation Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (- [ ]) syntax.
**Goal:** Land every cross-surface prerequisite — widened data layer, the Why→Pipeline IA rename, the weight_pct/thesis_id correctness fixes, the F5 token rule, the shared conviction/freshness components, the copy sweep, and the locked deep-link grammar — so Phases 1–3 build on an honest, non-conflicting foundation.
**Architecture:** Pure `frontend/olympus` work (Next.js 16 static export, `basePath /olympus`). The data layer (`lib/queries.ts` + `lib/types.ts` + `lib/database.types.ts`) stops dropping live DB columns; the shell (`lib/nav.ts`, `components/sidebar.tsx`, `command-palette.tsx`, `legacy-spa-redirect.tsx`) renames Why→Pipeline behind a query-param deep-link helper; new pure-presentational shared components (`ConvictionMeter`, `SignedConvictionBadge`, the F7 `AsOfBadge` upgrade) live under `components/shared/`.
**Tech Stack:** React 19, TypeScript, Tailwind v4 (`@theme` tokens, `[data-theme]`), lucide-react, recharts, `@supabase/supabase-js`, vitest.

## Global Constraints
- **Static export only.** `output: 'export'`, `basePath: '/olympus'`. No server actions, no route handlers, no runtime env reads beyond `NEXT_PUBLIC_*`. Every new route must be statically renderable.
- **Tailwind v4 tokens, inherited exactly.** dark-first; cyan-phosphor `--accent` #3DD6C4; Instrument Serif `--font-display`; Geist sans/mono; `glass-card`; semantic `text-fin-green`/`text-fin-red`/`text-fin-amber`; `bg-bg-primary`/`bg-bg-secondary`/`bg-bg-glass`; `border-border-subtle`; `text-text-primary`/`text-text-secondary`/`text-text-muted`. `--color-fin-blue` and `--color-fin-purple` are both already aliased to `--accent` (cyan) in `app/globals.css:31,35` — do not "fix" the alias; purge the *off-palette literals* instead.
- **Vitest, from `frontend/olympus`.** Run `npm run test -- <path>` (or `npx vitest run <path>`). 150+ plumbing tests + page-level tests MUST stay green. Page-level tests are updated *as part of* the task that changes their surface.
- **The F5 token rule (verbatim, applied everywhere):** cyan `--accent` #3DD6C4 for links/chrome/the single conviction encoding/the live-fresh dot only; `fin-green`/`fin-red` *strictly* for signed financial values; `fin-amber` for caution/stale/carried/mixed-regime; **no gradients** beyond the existing faint regime wash; **no decorative numbering** unless it encodes the system's own priority.
- **Empty-state discipline:** time-series elements gate on a data predicate and render a calm element-specific line — never an em-dash placeholder, a 1-row "table over time," or a single-dot chart. Per-day elements are the marquee.
- **Issue linkage:** every commit traces to a GitHub issue. Frontend Phase 0 work lands under the redesign tracking issue; four backend issues are filed (see Task 12) and referenced as `Fixes #<N>` placeholders where the durable fix lives backend-side.
- **No hand-editing `.claude/`** generated agent surface. Not relevant to this plan (all work is under `frontend/olympus`), noted for completeness.

---

## Grounding notes (verified against live DB + real files on 2026-06-24)

- **`positions` table already carries** `conviction`, `stop_loss_pct`, `target_pct_gain`, `horizon_days`, `sector_bucket` in `lib/database.types.ts:44-49` — but the `Position` domain type (`lib/types.ts:24-47`) and the mapping (`lib/queries.ts:864-915`) drop all of them. `positions` is fetched with `select('*')` (`queries.ts:462`), so **no select change is needed** — only the type + mapping.
- **`theses` live columns** (verified): `id, date, thesis_id, name, vehicle, invalidation, status, notes, created_at, updated_at, confidence (numeric), validation_criteria (jsonb), invalidation_criteria (jsonb), horizon (text), thesis_kind (text), linked_market_thesis_id (text)`. `theses` is fetched with `select('*')` (`queries.ts:463`) — again **no select change needed**, only `database.types.ts` + the `Thesis` type + the `queries.ts:648-655` mapping.
- **`atlas_run_diagnostics` is NOT in `database.types.ts`** — only the stripping `atlas_run_health` view (`database.types.ts:243-259`). Live columns (verified): `run_id, run_type, run_date, model, status, started_at, finished_at, duration_s, llm_calls, prompt_tokens, completion_tokens, total_tokens, search_calls, sources_used, grounding_ok, grounding_failed, est_cost_usd, segments_total, segments_ok, segments_carried, segments_failed, error_summary, breakdown (jsonb), created_at`. Live data: 3 rows — baseline 2026-06-23 `ok` ($0.616, 1.64M tokens, 39% cached, 163 LLM calls, 31/31 grounding), baseline 2026-06-23 `failed` ($0, the failed-then-recovered pair), delta 2026-06-24 `degraded`. `breakdown.cached_tokens` and `breakdown.by_kind.chat.cached_tokens` carry the cache-hit story; `breakdown.phase{1..5}_outputs` carry `{ok, failed, carried}` for the per-phase health strip.
- **`Settings Docs hotfix is ALREADY applied** in `components/settings-content.tsx:29` (`href="/system"`, label "How it works") — commit `004ac495` is in the log and reflected in the file. Task 11 therefore only adds a *regression guard test* and verifies no stray `/architecture` href remains in user-facing components (the only `architecture` hits are the `routeActive` legacy-absorb regex in `sidebar.tsx:44`, a redirect, and prose comments — all correct).
- **`AsOfBadge` exists** (`components/overview/as-of-badge.tsx`) but derives staleness from the *date string alone* and ignores `lib/snapshot-staleness.ts`. F7 upgrades it to optionally consume a `created_at` timestamp via `isStale`/`formatAge`, and relocates it to `components/shared/` as the single canonical component.
- **The command palette manages its own `open` state** via a global Cmd+K listener; nothing outside can open it. The visible search pill (F2) requires lifting an `openCommandPalette()` action into `app-shell-context.tsx`.
- **`/pipeline` route does not exist;** `/why` route still renders `WhyClient`. Per spec the placeholder `/pipeline` **redirects to `/why`** so nav never 404s until the Pipeline surface build lands.

---

## Task 1: Widen `database.types.ts` — add `atlas_run_diagnostics` + the six `theses` columns

**Files:** Modify `frontend/olympus/lib/database.types.ts` (theses Row 54-67; Views block 235-260) / Test: none (type-only; covered by `tsc`).
**Interfaces:** Produces `TableRow<'atlas_run_diagnostics'>` and the widened `TableRow<'theses'>` (consumed by Tasks 2, 4, and Phase-1 System / Phase-2 Theses).

- [ ] Add the six live columns to the `theses` Row in `lib/database.types.ts` (after `notes` on line 63, before the closing of `Row`):

```ts
      theses: {
        Row: {
          id: string;
          date: string;
          thesis_id: string;
          name: string;
          vehicle: string | null;
          invalidation: string | null;
          status: string | null;
          notes: string | null;
          created_at?: string | null;
          updated_at?: string | null;
          // Widened (#redesign F1): live columns the old mapping dropped.
          confidence?: number | null;            // numeric 0.0–1.0
          horizon?: string | null;               // e.g. "3-6mo"
          thesis_kind?: string | null;           // 'market' | 'vehicle'
          validation_criteria?: Json | null;     // jsonb string[]
          invalidation_criteria?: Json | null;   // jsonb string[]
          linked_market_thesis_id?: string | null;
        };
        Insert: Omit<Database['public']['Tables']['theses']['Row'], 'id'> & { id?: string };
        Update: Partial<Database['public']['Tables']['theses']['Insert']>;
      };
```

- [ ] Add `atlas_run_diagnostics` as a **Table** (it is a base table, not a view) in the `Tables` block, after `position_attribution` (before line 234 `};` that closes `Tables`):

```ts
      atlas_run_diagnostics: {
        Row: {
          run_id: string;
          run_type: string | null;
          run_date: string | null;
          model: string | null;
          status: string | null;
          started_at: string | null;
          finished_at: string | null;
          duration_s: number | null;
          llm_calls: number | null;
          prompt_tokens: number | null;
          completion_tokens: number | null;
          total_tokens: number | null;
          search_calls: number | null;
          sources_used: number | null;
          grounding_ok: number | null;
          grounding_failed: number | null;
          est_cost_usd: number | null;
          segments_total: number | null;
          segments_ok: number | null;
          segments_carried: number | null;
          segments_failed: number | null;
          error_summary: string | null;
          breakdown: Json | null;
          created_at: string | null;
        };
        Insert: Database['public']['Tables']['atlas_run_diagnostics']['Row'];
        Update: Partial<Database['public']['Tables']['atlas_run_diagnostics']['Row']>;
      };
```

- [ ] Run the type check: `cd frontend/olympus && npx tsc --noEmit` — expect PASS (no new errors; the additions are purely additive optional fields + a new table key).
- [ ] Commit: `git commit -am "chore(olympus): widen database.types for theses columns + atlas_run_diagnostics"`

---

## Task 2: Widen the `Thesis` + `Position` domain types and add the diagnostics type

**Files:** Modify `frontend/olympus/lib/types.ts` (Position 24-47; Thesis 50-57; new `AtlasRunDiagnostics` type) / Test: `frontend/olympus/lib/types.test.ts` (new — a compile-shape assertion).
**Interfaces:** Consumes widened `TableRow<'theses'>`, `TableRow<'positions'>`, `TableRow<'atlas_run_diagnostics'>` (Task 1). Produces the widened `Thesis`, `Position`, and new `AtlasRunDiagnostics` exported types (consumed by Task 3 mapping + Phases 1–3).

- [ ] Write the failing shape test `lib/types.test.ts`:

```ts
import { describe, it, expectTypeOf } from 'vitest';
import type { Thesis, Position, AtlasRunDiagnostics } from './types';

describe('widened domain types (F1)', () => {
  it('Thesis carries the six widened fields', () => {
    expectTypeOf<Thesis>().toHaveProperty('confidence');
    expectTypeOf<Thesis>().toHaveProperty('horizon');
    expectTypeOf<Thesis>().toHaveProperty('thesis_kind');
    expectTypeOf<Thesis>().toHaveProperty('validation_criteria');
    expectTypeOf<Thesis>().toHaveProperty('invalidation_criteria');
    expectTypeOf<Thesis>().toHaveProperty('linked_market_thesis_id');
  });
  it('Position carries conviction + risk envelope', () => {
    expectTypeOf<Position>().toHaveProperty('conviction');
    expectTypeOf<Position>().toHaveProperty('stop_loss_pct');
    expectTypeOf<Position>().toHaveProperty('target_pct_gain');
    expectTypeOf<Position>().toHaveProperty('horizon_days');
    expectTypeOf<Position>().toHaveProperty('sector_bucket');
  });
  it('AtlasRunDiagnostics carries run economics', () => {
    expectTypeOf<AtlasRunDiagnostics>().toHaveProperty('est_cost_usd');
    expectTypeOf<AtlasRunDiagnostics>().toHaveProperty('cached_tokens');
  });
});
```

- [ ] Run it: `npx vitest run lib/types.test.ts` — expect FAIL (`AtlasRunDiagnostics` not exported; properties missing).
- [ ] Extend `Thesis` in `lib/types.ts` (replace lines 49-57):

```ts
/** Active investment thesis as returned to components. */
export interface Thesis {
  id: string;
  name: string;
  vehicle: string | null;
  invalidation: string | null;
  status: string | null;
  notes: string | null;
  // Widened (F1) — the richest DB columns, previously dropped in the mapping.
  /** Conviction strength 0.0–1.0; drives the cyan ConvictionMeter on the thesis card. */
  confidence: number | null;
  horizon: string | null;
  /** 'market' | 'vehicle' — splits the two-tier Theses ledger. */
  thesis_kind: string | null;
  /** "What confirms this" — structured evidence rows. */
  validation_criteria: string[];
  /** "What breaks this" — structured evidence rows. */
  invalidation_criteria: string[];
  /** For vehicle theses: the market view they express (null until backend populates). */
  linked_market_thesis_id: string | null;
}
```

- [ ] Extend `Position` in `lib/types.ts` (add to the interface body before the closing `}` on line 47):

```ts
  /** Unsigned per-position conviction 1–3 (cyan pip meter). */
  conviction?: number | null;
  /** Advisory risk envelope (migration 039); null on ungraded rows. */
  stop_loss_pct?: number | null;
  target_pct_gain?: number | null;
  horizon_days?: number | null;
  /** Grouping bucket for the Holdings sector grouping. */
  sector_bucket?: string | null;
```

- [ ] Add the diagnostics domain type to `lib/types.ts` (after the `ServerPortfolioMetrics` block, ~line 167):

```ts
/**
 * A single Atlas run's economics + health, read directly from
 * `atlas_run_diagnostics` (NOT the stripping `atlas_run_health` view) per D3.
 * `cached_tokens` is lifted out of the `breakdown` jsonb for convenience.
 */
export interface AtlasRunDiagnostics {
  run_id: string;
  run_type: string | null;
  run_date: string | null;
  model: string | null;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_s: number | null;
  llm_calls: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cached_tokens: number | null;
  search_calls: number | null;
  grounding_ok: number | null;
  grounding_failed: number | null;
  est_cost_usd: number | null;
  segments_total: number | null;
  segments_ok: number | null;
  segments_carried: number | null;
  segments_failed: number | null;
  error_summary: string | null;
  /** Phase health `{phaseN_outputs: {ok, failed, carried}}` + `by_kind` cost split. */
  breakdown: Record<string, unknown> | null;
  created_at: string | null;
}
```

- [ ] Run it: `npx vitest run lib/types.test.ts` — expect PASS.
- [ ] Commit: `git commit -am "feat(olympus): widen Thesis/Position domain types + add AtlasRunDiagnostics (F1)"`

---

## Task 3: Widen the `queries.ts` mappings + add the `fetchAtlasRunDiagnostics` direct read

**Files:** Modify `frontend/olympus/lib/queries.ts` (thesis mapping 648-655; position mapping 864-915; new exported `fetchAtlasRunDiagnostics` near `fetchObservabilityData`-style readers) / Test: `frontend/olympus/lib/queries-widening.test.ts` (new — pure-mapping units).
**Interfaces:** Consumes widened types (Task 2). Produces:
- `mapThesisRow(row: TableRow<'theses'>): Thesis` (exported pure fn — testable without Supabase)
- `mapPositionConviction` folded into the existing position map (no new export; conviction etc. flow through the `Position[]` mapping)
- `fetchAtlasRunDiagnostics(): Promise<AtlasRunDiagnostics[]>` (exported; consumed by Phase-1 System)

- [ ] Add a pure thesis mapper + jsonb-array coercion helper near the top of `queries.ts` (after the imports, before `querySupabase`):

```ts
/** Coerce a jsonb column that should be a string[] into one, tolerating null/non-arrays. */
function asStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => String(x)).filter((s) => s.length > 0);
}

/** Map a raw `theses` row to the widened domain `Thesis` (F1). Pure — unit-testable. */
export function mapThesisRow(t: TableRow<'theses'>): Thesis {
  return {
    id: t.thesis_id,
    name: t.name,
    vehicle: t.vehicle,
    invalidation: t.invalidation,
    status: t.status,
    notes: t.notes,
    confidence: t.confidence ?? null,
    horizon: t.horizon ?? null,
    thesis_kind: t.thesis_kind ?? null,
    validation_criteria: asStringArray(t.validation_criteria),
    invalidation_criteria: asStringArray(t.invalidation_criteria),
    linked_market_thesis_id: t.linked_market_thesis_id ?? null,
  };
}
```

- [ ] Replace the inline thesis map at `queries.ts:648-655` with the shared mapper:

```ts
  const theses: Thesis[] = currentTheses.map(mapThesisRow);
```

- [ ] Add the five widened fields to the `Position` mapping at `queries.ts:864-915` (add inside the mapped object, alongside `metrics_as_of` near line 914):

```ts
    metrics_as_of: p.metrics_as_of ?? null,
    conviction: p.conviction ?? null,
    stop_loss_pct: p.stop_loss_pct ?? null,
    target_pct_gain: p.target_pct_gain ?? null,
    horizon_days: p.horizon_days ?? null,
    sector_bucket: p.sector_bucket ?? null,
```

> Note: the digest-only fallback row literal at `queries.ts:756-771` (the `effectiveCurrentPositions` synthesis) does not set these new fields; they are optional and resolve to `null` via the `?? null` reads above. No change needed there.

- [ ] Add the direct diagnostics reader. Place it after `fetchObservabilityData`'s sibling readers — co-locate in `lib/observability-queries.ts` instead of `queries.ts` to keep the main bundle lean (it mirrors `fetchObservabilityData`'s fail-soft pattern). Add to `lib/observability-queries.ts`:

```ts
import type { AtlasRunDiagnostics } from './types';

const RUN_DIAGNOSTICS_LIMIT = 30;

/** Lift cached_tokens out of the breakdown jsonb (top-level or by_kind.chat). */
function cachedTokensOf(breakdown: unknown): number | null {
  if (!breakdown || typeof breakdown !== 'object') return null;
  const b = breakdown as Record<string, unknown>;
  if (typeof b.cached_tokens === 'number') return b.cached_tokens;
  const byKind = b.by_kind as Record<string, unknown> | undefined;
  const chat = byKind?.chat as Record<string, unknown> | undefined;
  return typeof chat?.cached_tokens === 'number' ? chat.cached_tokens : null;
}

/**
 * Read run economics directly from `atlas_run_diagnostics` (D3) — cost, tokens,
 * cache-hit, grounding, per-phase breakdown — bypassing the stripping
 * `atlas_run_health` view. Fail-soft: empty array on missing source / RLS deny.
 */
export async function fetchAtlasRunDiagnostics(): Promise<AtlasRunDiagnostics[]> {
  const res = await safeSelect<TableRow<'atlas_run_diagnostics'>>('atlas_run_diagnostics', (sb) =>
    sb
      .from('atlas_run_diagnostics')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(RUN_DIAGNOSTICS_LIMIT)
  );
  return res.rows.map((r) => ({
    run_id: r.run_id,
    run_type: r.run_type,
    run_date: r.run_date,
    model: r.model,
    status: r.status,
    started_at: r.started_at,
    finished_at: r.finished_at,
    duration_s: r.duration_s,
    llm_calls: r.llm_calls,
    prompt_tokens: r.prompt_tokens,
    completion_tokens: r.completion_tokens,
    total_tokens: r.total_tokens,
    cached_tokens: cachedTokensOf(r.breakdown),
    search_calls: r.search_calls,
    grounding_ok: r.grounding_ok,
    grounding_failed: r.grounding_failed,
    est_cost_usd: r.est_cost_usd,
    segments_total: r.segments_total,
    segments_ok: r.segments_ok,
    segments_carried: r.segments_carried,
    segments_failed: r.segments_failed,
    error_summary: r.error_summary,
    breakdown: (r.breakdown ?? null) as Record<string, unknown> | null,
    created_at: r.created_at,
  }));
}
```

> `safeSelect`, `supabase`, `TableRow`, and `isSupabaseConfigured` are already imported in `observability-queries.ts:14-15`. Add the `AtlasRunDiagnostics` import.

- [ ] Write the failing mapping test `lib/queries-widening.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { mapThesisRow } from './queries';
import type { TableRow } from './database.types';

const row = (over: Partial<TableRow<'theses'>> = {}): TableRow<'theses'> => ({
  id: 'u', date: '2026-06-23', thesis_id: 'MT1', name: 'Small caps', vehicle: null,
  invalidation: null, status: 'ACTIVE', notes: null,
  ...over,
});

describe('mapThesisRow (F1)', () => {
  it('lifts confidence/horizon/kind/criteria/linked id', () => {
    const t = mapThesisRow(row({
      confidence: 0.72, horizon: '3-6mo', thesis_kind: 'market',
      validation_criteria: ['breadth widens', 'rates ease'] as unknown as TableRow<'theses'>['validation_criteria'],
      invalidation_criteria: ['credit blows out'] as unknown as TableRow<'theses'>['invalidation_criteria'],
      linked_market_thesis_id: null,
    }));
    expect(t.confidence).toBe(0.72);
    expect(t.horizon).toBe('3-6mo');
    expect(t.thesis_kind).toBe('market');
    expect(t.validation_criteria).toEqual(['breadth widens', 'rates ease']);
    expect(t.invalidation_criteria).toEqual(['credit blows out']);
  });
  it('coerces missing/non-array jsonb criteria to []', () => {
    const t = mapThesisRow(row());
    expect(t.validation_criteria).toEqual([]);
    expect(t.invalidation_criteria).toEqual([]);
    expect(t.confidence).toBeNull();
  });
});
```

- [ ] Run it: `npx vitest run lib/queries-widening.test.ts` — expect PASS (the implementation above ships in the same commit; if you TDD strictly, write the test before adding `mapThesisRow` and watch it FAIL on the missing export first).
- [ ] Run the full lib suite to confirm no regression: `npx vitest run lib/` — expect PASS.
- [ ] Commit: `git commit -am "feat(olympus): widen queries mappings + fetchAtlasRunDiagnostics direct read (F1, D3)"`

---

## Task 4: F4 — `thesis_id` join normalization helper + dedupe usage

**Files:** Modify `frontend/olympus/lib/thesis-id.ts` / Test: `frontend/olympus/lib/thesis-id.test.ts` (extend if present, else create).
**Interfaces:** Consumes nothing. Produces `joinPositionsToThesis(positions, thesisId)` and the documented `normalizeThesisId` contract (consumed by Phase-2 Theses "holdings expressing this thesis", Holdings→thesis links, Today's book strip).

**Problem (verified):** `positions.thesis_id` holds lowercase vehicle tickers (`ewt`, `ijr`) while `theses.thesis_id` holds `vehicle-ewt` / `MT1`. The existing `normalizeThesisId` only upper-cases — it will NOT match `EWT` to `VEHICLE-EWT`. The interim normalization must strip the `vehicle-` prefix and compare on the bare ticker.

- [ ] Write the failing test `lib/thesis-id.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { thesisIdEquals, joinPositionsToThesis } from './thesis-id';

describe('thesis_id join normalization (F4)', () => {
  it('matches a lowercase position ticker to a vehicle- prefixed thesis id', () => {
    expect(thesisIdEquals('ewt', 'vehicle-ewt')).toBe(true);
    expect(thesisIdEquals('IJR', 'vehicle-ijr')).toBe(true);
  });
  it('still matches identical ids and rejects genuine mismatches', () => {
    expect(thesisIdEquals('MT1', 'MT1')).toBe(true);
    expect(thesisIdEquals('ewt', 'MT1')).toBe(false);
    expect(thesisIdEquals(null, 'MT1')).toBe(false);
  });
  it('joinPositionsToThesis selects positions expressing a thesis', () => {
    const positions = [
      { ticker: 'EWT', thesis_ids: ['ewt'] },
      { ticker: 'IJR', thesis_ids: ['ijr'] },
    ];
    const out = joinPositionsToThesis(positions, 'vehicle-ewt');
    expect(out.map((p) => p.ticker)).toEqual(['EWT']);
  });
});
```

- [ ] Run it: `npx vitest run lib/thesis-id.test.ts` — expect FAIL (`vehicle-ewt` !== `EWT` under the upper-case-only normalizer; `joinPositionsToThesis` undefined).
- [ ] Rewrite `lib/thesis-id.ts`:

```ts
/**
 * Interim, clearly-labelled query-layer normalization (F4). Durable fix is
 * upstream (canonicalize `positions.thesis_id` to match `theses.thesis_id` —
 * backend issue). Until then: bare-ticker compare so a position keyed `ewt`
 * matches a thesis keyed `vehicle-ewt`, and case is irrelevant.
 */
export function normalizeThesisId(id: string | null | undefined): string {
  return String(id ?? '')
    .trim()
    .toUpperCase()
    .replace(/^VEHICLE-/, '');
}

export function thesisIdEquals(a: string | null | undefined, b: string | null | undefined): boolean {
  const left = normalizeThesisId(a);
  const right = normalizeThesisId(b);
  return Boolean(left && right && left === right);
}

/** Positions whose thesis_ids express `thesisId` under the normalized join. */
export function joinPositionsToThesis<T extends { thesis_ids: string[] }>(
  positions: T[],
  thesisId: string | null | undefined
): T[] {
  if (!thesisId) return [];
  return positions.filter((p) => p.thesis_ids.some((id) => thesisIdEquals(id, thesisId)));
}
```

- [ ] Run it: `npx vitest run lib/thesis-id.test.ts` — expect PASS.
- [ ] Confirm no existing caller of `thesisIdEquals` regresses: `grep -rn thesisIdEquals lib components` then `npx vitest run lib/ components/` — expect PASS (the change only *widens* what matches; `MT1`/`MT1` style exact matches are preserved).
- [ ] Commit: `git commit -am "fix(olympus): normalize thesis_id join across vehicle- prefix + case (F4 interim)"`

---

## Task 5: F3 — book-reconciliation primitive (weight_pct dedupe → 100%)

**Files:** Create `frontend/olympus/lib/book-reconciliation.ts` / Test: `frontend/olympus/lib/book-reconciliation.test.ts`.
**Interfaces:** Consumes `Position[]` (Task 2) and `NavChartPoint`/`ServerPortfolioMetrics` cash/invested. Produces:
- `reconcileBook(positions: Position[], opts?: { investedPct?: number | null }): BookReconciliation`
- `interface BookReconciliation { rows: ReconciledPosition[]; investedPct: number; cashPct: number; grossPct: number; netPct: number; }`
- `interface ReconciledPosition extends Position { normalizedWeight: number }`

(consumed by Holdings header strip, Today's book strip, Theses exposure rollups — the single source of truth so no surface ever prints a raw 150% headline.)

**Problem (verified D1):** raw `positions.weight_pct` rows overlap across category buckets and sum to ~150%. The primitive dedupes by ticker (keeping the max weight per ticker, since duplicates are double-counted category memberships of the *same* holding), then normalizes the held book to `investedPct` (from `nav_history`/`portfolio_metrics` when present, else the deduped sum capped at 100), with cash = 100 − invested.

- [ ] Write the failing test `lib/book-reconciliation.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { reconcileBook } from './book-reconciliation';
import type { Position } from './types';

const pos = (ticker: string, weight_actual: number): Position => ({
  ticker, name: ticker, type: 'LONG', weight_actual,
  current_price: null, entry_price: null, entry_date: null,
  rationale: '', thesis_ids: [], category: 'equity', pm_notes: '', stats: {},
});

describe('reconcileBook (F3)', () => {
  it('dedupes a ticker double-counted across buckets (keeps max), normalizes to investedPct', () => {
    // Same EWT counted twice (e.g. "equity" + "international") + IJR → raw sum 150.
    const positions = [pos('EWT', 50), pos('EWT', 50), pos('IJR', 50)];
    const { rows, investedPct, cashPct } = reconcileBook(positions, { investedPct: 75 });
    expect(rows.map((r) => r.ticker)).toEqual(['EWT', 'IJR']);
    // Deduped held = 100 (EWT 50 + IJR 50); normalized to investedPct 75 → 37.5 each.
    expect(rows.find((r) => r.ticker === 'EWT')!.normalizedWeight).toBeCloseTo(37.5, 3);
    expect(investedPct).toBe(75);
    expect(cashPct).toBe(25);
    const sum = rows.reduce((s, r) => s + r.normalizedWeight, 0) + cashPct;
    expect(sum).toBeCloseTo(100, 3);
  });
  it('falls back to the deduped held sum (capped 100) when investedPct is absent', () => {
    const { investedPct, cashPct } = reconcileBook([pos('EWT', 40), pos('IJR', 40)]);
    expect(investedPct).toBe(80);
    expect(cashPct).toBe(20);
  });
  it('never reports a >100% book even on a raw 150% input', () => {
    const { investedPct, cashPct } = reconcileBook([pos('A', 60), pos('B', 60), pos('C', 30)], { investedPct: null });
    expect(investedPct).toBeLessThanOrEqual(100);
    expect(cashPct).toBeGreaterThanOrEqual(0);
    expect(investedPct + cashPct).toBeCloseTo(100, 3);
  });
});
```

- [ ] Run it: `npx vitest run lib/book-reconciliation.test.ts` — expect FAIL (module does not exist).
- [ ] Implement `lib/book-reconciliation.ts`:

```ts
import type { Position } from './types';

export interface ReconciledPosition extends Position {
  /** Weight normalized so held + cash = 100% (F3 single source of truth). */
  normalizedWeight: number;
}

export interface BookReconciliation {
  rows: ReconciledPosition[];
  investedPct: number;
  cashPct: number;
  /** Sum of |weights| — equals investedPct until the book is ever levered. */
  grossPct: number;
  /** Long − short — equals investedPct in a long-only book. */
  netPct: number;
}

/**
 * Dedupe overlapping/double-counted `weight_pct` rows and normalize the held
 * book so held + cash = 100% (D1 / F3). Duplicates are the same holding listed
 * under multiple category buckets, so we keep the max weight per ticker.
 *
 * `investedPct` (from nav_history / portfolio_metrics) is the authoritative
 * cash split when known; otherwise we fall back to the deduped held sum capped
 * at 100. Cash is always 100 − investedPct. Never returns a >100% book.
 */
export function reconcileBook(
  positions: Position[],
  opts: { investedPct?: number | null } = {}
): BookReconciliation {
  const byTicker = new Map<string, Position>();
  for (const p of positions) {
    const prev = byTicker.get(p.ticker);
    if (!prev || (p.weight_actual ?? 0) > (prev.weight_actual ?? 0)) {
      byTicker.set(p.ticker, p);
    }
  }
  const deduped = [...byTicker.values()];
  const heldSum = deduped.reduce((s, p) => s + (p.weight_actual ?? 0), 0);

  const invested =
    opts.investedPct != null && opts.investedPct >= 0
      ? Math.min(100, opts.investedPct)
      : Math.min(100, heldSum);
  const cashPct = Math.max(0, 100 - invested);

  // Scale deduped weights to the invested envelope (so they sum to investedPct).
  const scale = heldSum > 0 ? invested / heldSum : 0;
  const rows: ReconciledPosition[] = deduped.map((p) => ({
    ...p,
    normalizedWeight: (p.weight_actual ?? 0) * scale,
  }));

  const grossPct = rows.reduce((s, r) => s + Math.abs(r.normalizedWeight), 0);
  const netPct = rows.reduce(
    (s, r) => s + (r.type === 'SHORT' ? -r.normalizedWeight : r.normalizedWeight),
    0
  );
  return { rows, investedPct: invested, cashPct, grossPct, netPct };
}
```

- [ ] Run it: `npx vitest run lib/book-reconciliation.test.ts` — expect PASS.
- [ ] Commit: `git commit -am "feat(olympus): book-reconciliation primitive — dedupe weight_pct to 100% (F3, D1)"`

---

## Task 6: F2a — the locked deep-link helper `lib/pipeline-links.ts`

**Files:** Create `frontend/olympus/lib/pipeline-links.ts` / Test: `frontend/olympus/lib/pipeline-links.test.ts`.
**Interfaces:** Produces the LOCKED grammar consumed by six callers (command palette, Today doorways, Theses provenance, Holdings linkage, Documents redirects, System links):
- `buildPipelineHref(opts: { date?: string | null; stage?: PipelineStage | null; node?: string | null }): string`
- `type PipelineStage = 'inputs' | 'research' | 'synthesis' | 'selection' | 'decision'`
- `STAGE_FOR_DOCUMENT_KEY: (documentKey: string) => PipelineStage | null` (maps a `document_key` to its stage so callers can pass a node and get the stage for free)

- [ ] Write the failing test `lib/pipeline-links.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { buildPipelineHref, stageForDocumentKey } from './pipeline-links';

describe('buildPipelineHref (LOCKED deep-link grammar)', () => {
  it('emits /pipeline?date=&stage=&node= keyed off document_key', () => {
    expect(buildPipelineHref({ date: '2026-06-23', stage: 'selection', node: 'analyst/IJR' }))
      .toBe('/pipeline?date=2026-06-23&stage=selection&node=analyst%2FIJR');
  });
  it('omits empty params and url-encodes the node key', () => {
    expect(buildPipelineHref({ date: '2026-06-23', node: 'digest' }))
      .toBe('/pipeline?date=2026-06-23&node=digest');
    expect(buildPipelineHref({})).toBe('/pipeline');
  });
  it('infers stage from a document_key when the caller has none', () => {
    expect(stageForDocumentKey('digest')).toBe('synthesis');
    expect(stageForDocumentKey('analyst/IJR')).toBe('selection');
    expect(stageForDocumentKey('deliberation/EWT')).toBe('selection');
    expect(stageForDocumentKey('pm-rebalance')).toBe('selection');
    expect(stageForDocumentKey('sector-energy')).toBe('research');
    expect(stageForDocumentKey('commit-run/28041585974')).toBe('decision');
    expect(stageForDocumentKey('unknown-thing')).toBeNull();
  });
});
```

- [ ] Run it: `npx vitest run lib/pipeline-links.test.ts` — expect FAIL (module does not exist).
- [ ] Implement `lib/pipeline-links.ts`:

```ts
/**
 * LOCKED deep-link grammar for the Pipeline hub (Surface 1).
 * `/pipeline?date=YYYY-MM-DD&stage=<stage>&node=<document_key>`
 * "open day D, expand stage S, focus node N." Keyed off `document_key`, NOT the
 * legacy `path` field. Six consumers depend on this exact shape; do not drift.
 */
export type PipelineStage = 'inputs' | 'research' | 'synthesis' | 'selection' | 'decision';

export function buildPipelineHref(opts: {
  date?: string | null;
  stage?: PipelineStage | null;
  node?: string | null;
}): string {
  const p = new URLSearchParams();
  if (opts.date) p.set('date', opts.date);
  if (opts.stage) p.set('stage', opts.stage);
  if (opts.node) p.set('node', opts.node);
  const qs = p.toString();
  return qs ? `/pipeline?${qs}` : '/pipeline';
}

/** Map a `document_key` to the stage that owns it (per the spec topology table). */
export function stageForDocumentKey(documentKey: string): PipelineStage | null {
  const k = documentKey.toLowerCase();
  if (k === 'digest') return 'synthesis';
  if (k.startsWith('analyst/') || k.startsWith('deliberation/')) return 'selection';
  if (k === 'pm-direction-memo' || k === 'pm-rebalance' || k === 'risk-debate') return 'selection';
  if (k.startsWith('commit-run/')) return 'decision';
  if (
    k.startsWith('alt-') ||
    k.startsWith('inst-') ||
    k.startsWith('sector-') ||
    k === 'macro' ||
    ['bonds', 'commodities', 'forex', 'crypto', 'equity', 'international'].includes(k)
  ) {
    return 'research';
  }
  if (k === 'preflight' || k.startsWith('market-data')) return 'inputs';
  return null;
}
```

- [ ] Run it: `npx vitest run lib/pipeline-links.test.ts` — expect PASS.
- [ ] Commit: `git commit -am "feat(olympus): locked /pipeline deep-link helper (F2, six consumers)"`

---

## Task 7: F2b — the `/pipeline` placeholder route + `nav.ts` flip + sidebar `routeActive`

**Files:** Create `frontend/olympus/app/pipeline/page.tsx`; Modify `frontend/olympus/lib/nav.ts`, `frontend/olympus/components/sidebar.tsx` (routeActive 31-46) / Test: `frontend/olympus/lib/nav.test.ts`, `frontend/olympus/components/sidebar.test.tsx`.
**Interfaces:** Consumes nothing new. Produces the live `/pipeline` nav target. **Must land in one commit** so nav never points at a 404.

- [ ] Create the `/pipeline` placeholder route. Per spec, until the Pipeline surface build lands, `/pipeline` redirects to `/why` rather than 404. Write `app/pipeline/page.tsx`:

```tsx
'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import AtlasLoader from '@/components/AtlasLoader';

/**
 * Placeholder for the Pipeline hub (Surface 1, separate locked build). Until
 * that build lands, /pipeline redirects to the legacy /why surface so the
 * renamed nav target never 404s. Replaced wholesale by the Pipeline canvas.
 */
export default function PipelinePage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/why');
  }, [router]);
  return <AtlasLoader />;
}
```

- [ ] Update the failing nav test FIRST `lib/nav.test.ts` (replace the two `toEqual` assertions):

```ts
  it('is the 4-destination owner spine, in order', () => {
    expect(NAV.map((n) => n.href)).toEqual(['/', '/portfolio', '/pipeline', '/system']);
    expect(NAV.map((n) => n.label)).toEqual(['Today', 'Portfolio', 'Pipeline', 'System']);
  });
```

- [ ] Run it: `npx vitest run lib/nav.test.ts` — expect FAIL (nav still ships `/why` / `Why`).
- [ ] Flip `lib/nav.ts` — change the import (drop `BookOpen`, add `GitBranch`) and the third NAV entry:

```ts
import { LayoutDashboard, PieChart, GitBranch, Activity } from 'lucide-react';
```
```ts
  { href: '/pipeline', label: 'Pipeline', icon: GitBranch },
```

- [ ] Run it: `npx vitest run lib/nav.test.ts` — expect PASS.
- [ ] Update the failing sidebar test `components/sidebar.test.tsx` — replace the `Why` references in the three assertions:

```ts
  it('renders the four owner destinations', () => {
    const html = renderToStaticMarkup(createElement(Sidebar));
    for (const label of ['Today', 'Portfolio', 'Pipeline', 'System']) {
      expect(html).toContain(label);
    }
  });
```
```ts
  it('pins System last — demoted to the bottom of the nav', () => {
    const html = renderToStaticMarkup(createElement(Sidebar));
    expect(html.indexOf('System')).toBeGreaterThan(html.indexOf('Today'));
    expect(html.indexOf('System')).toBeGreaterThan(html.indexOf('Pipeline'));
  });
```
```ts
  it('no longer shows the legacy labels', () => {
    const html = renderToStaticMarkup(createElement(Sidebar));
    expect(html).not.toContain('Overview');
    expect(html).not.toContain('Observability');
    expect(html).not.toContain('Why');
  });
```

- [ ] Run it: `npx vitest run components/sidebar.test.tsx` — expect FAIL (sidebar still renders "Why" via NAV; and the `/why` `routeActive` branch is stale).
- [ ] Rewrite the `/why` branch in `components/sidebar.tsx:31-38` into a `/pipeline` branch that also absorbs the legacy `/why`, `/research`, `/library` prefixes (leave `/portfolio` and `/system` branches untouched):

```ts
  if (href === '/pipeline') {
    // Pipeline replaces Why; absorbs the legacy /why, /research, /library routes.
    return (
      /\/pipeline(\/|$)/.test(pathname) ||
      /\/why(\/|$)/.test(pathname) ||
      /\/research(\/|$)/.test(pathname) ||
      /\/library(\/|$)/.test(pathname)
    );
  }
```

- [ ] Run it: `npx vitest run components/sidebar.test.tsx lib/nav.test.ts` — expect PASS.
- [ ] Verify the static build still exports cleanly with the new route: `npx next build` — expect PASS (the `/pipeline` route exports as a client-redirect page).
- [ ] Commit: `git commit -am "refactor(olympus): rename Why→Pipeline in nav + routeActive + /pipeline route (F2)"`

---

## Task 8: F2c — command palette re-authored to Pipeline-native commands + cross-day doc search

**Files:** Modify `frontend/olympus/components/command-palette.tsx` (items 45-130) / Test: `frontend/olympus/components/command-palette.test.tsx` (new — pure item-builder unit via an extracted helper).
**Interfaces:** Consumes `buildPipelineHref` + `stageForDocumentKey` (Task 6). Produces the re-pointed palette items; extracts `buildCommandItems(data)` as a pure exported fn so it is testable without the React tree (the palette's dynamic thesis + recent-run blocks are the palette's best feature — keep them).

- [ ] Replace the three "Why —" base entries (`command-palette.tsx:71-91`, the `go-read` / `go-delib` / `go-docs` items) with Pipeline-native commands using the locked grammar. New entries:

```tsx
      {
        id: 'go-pipeline',
        title: 'Pipeline — the daily graph',
        hint: 'Research → deliberation → decision',
        href: '/pipeline',
        icon: GitBranch,
      },
      {
        id: 'go-pipeline-read',
        title: 'Pipeline — the read',
        hint: "Today's digest node",
        href: buildPipelineHref({ node: 'digest', stage: 'synthesis' }),
        icon: Newspaper,
      },
      {
        id: 'go-pipeline-delib',
        title: 'Pipeline — deliberations',
        hint: 'PM ⇄ analyst debates',
        href: buildPipelineHref({ stage: 'selection' }),
        icon: Brain,
      },
```

- [ ] Update the imports in `command-palette.tsx`: drop `BookOpen`, add `GitBranch`; add `import { buildPipelineHref, stageForDocumentKey } from '@/lib/pipeline-links';`.
- [ ] Re-point `recentDateItems` (`command-palette.tsx:117-127`) to the Pipeline grammar keyed off `document_key='digest'` (the palette currently builds a legacy `/why?tab=daily&date=…&docKey=…` href):

```tsx
    const recentDateItems: CmdItem[] = recentDates.map((date) => ({
      id: `date-${date}`,
      title: `Pipeline — ${date}`,
      hint: 'Jump to that run',
      href: buildPipelineHref({ date, node: 'digest', stage: 'synthesis' }),
      icon: Newspaper,
    }));
```

- [ ] Add the cross-day document search block (Surface 6 seed — typing a ticker/segment surfaces matching docs across available dates, deep-linking to the Pipeline node). After `recentDateItems`, before the `return`:

```tsx
    // Cross-day discovery (Surface 6): every research/analyst/deliberation doc
    // becomes a palette hit that deep-links to its Pipeline node. Degrades to 1 day.
    const docItems: CmdItem[] = docs
      .filter((d) => stageForDocumentKey(d.path) !== null && d.path !== 'digest')
      .slice(0, 200)
      .map((d) => ({
        id: `doc-${d.date}-${d.path}`,
        title: `${d.title || d.path}`,
        hint: `${d.date} · ${d.path}`,
        href: buildPipelineHref({
          date: d.date,
          stage: stageForDocumentKey(d.path) ?? undefined,
          node: d.path,
        }),
        icon: Newspaper,
      }));

    return [...base, ...thesisItems, ...recentDateItems, ...docItems];
```
(replace the existing `return [...base, ...thesisItems, ...recentDateItems];` on line 129.)

- [ ] Keep the dynamic thesis block (`command-palette.tsx:108-114`) unchanged — it remains a deep link to the thesis detail route, which is correct (`/portfolio/theses/{id}`).
- [ ] Extract the item-builder into a testable pure fn. At the top of the file, lift the `useMemo` body into `export function buildCommandItems(data: ReturnType<typeof useDashboard>['data']): CmdItem[]`, then call it from the memo: `const items = useMemo(() => buildCommandItems(data), [data]);`. Write the failing test `components/command-palette.test.tsx`:

```ts
import { describe, it, expect } from 'vitest';
import { buildCommandItems } from './command-palette';

const data = {
  portfolio: { strategy: { theses: [{ id: 'MT1', name: 'Small caps' }] } },
  docs: [
    { date: '2026-06-23', title: 'Digest', path: 'digest' },
    { date: '2026-06-23', title: 'IJR analyst', path: 'analyst/IJR' },
    { date: '2026-06-22', title: 'Energy sector', path: 'sector-energy' },
  ],
} as unknown as Parameters<typeof buildCommandItems>[0];

describe('buildCommandItems (F2 palette)', () => {
  it('ships no legacy Why entries and points the read at the Pipeline grammar', () => {
    const items = buildCommandItems(data);
    expect(items.some((i) => i.title.startsWith('Why'))).toBe(false);
    const read = items.find((i) => i.id === 'go-pipeline-read')!;
    expect(read.href).toContain('/pipeline?');
    expect(read.href).toContain('node=digest');
  });
  it('surfaces cross-day docs as Pipeline node deep links, excluding digest', () => {
    const items = buildCommandItems(data);
    const ijr = items.find((i) => i.id === 'doc-2026-06-23-analyst/IJR')!;
    expect(ijr.href).toBe('/pipeline?date=2026-06-23&stage=selection&node=analyst%2FIJR');
    expect(items.some((i) => i.id === 'doc-2026-06-23-digest')).toBe(false);
  });
});
```

- [ ] Run it: `npx vitest run components/command-palette.test.tsx` — expect FAIL first (legacy entries / no `buildCommandItems` export), then PASS after the edits above.
- [ ] Commit: `git commit -am "refactor(olympus): re-author command palette to Pipeline grammar + cross-day doc search (F2)"`

---

## Task 9: F2d — legacy redirects re-pointed + visible ⌘K search pill

**Files:** Modify `frontend/olympus/components/legacy-spa-redirect.tsx` (Library 11-35, Strategy 37-60, Research 73-92), `frontend/olympus/components/app-shell-context.tsx`, `frontend/olympus/components/command-palette.tsx`, `frontend/olympus/components/sidebar.tsx` (header), `frontend/olympus/components/mobile-app-bar.tsx` / Test: `frontend/olympus/components/legacy-spa-redirect.test.tsx` (extend if present, else create the redirect-target assertions).
**Interfaces:** Consumes `buildPipelineHref` (Task 6) + `openCommandPalette` (new, this task). Produces `commandPaletteOpen` / `openCommandPalette()` / `closeCommandPalette()` on the app-shell context.

- [ ] Re-point the three Why-targeting redirects in `legacy-spa-redirect.tsx`. `LibraryToWhyInner` (lines 16-24) → Pipeline node grammar:

```tsx
  useEffect(() => {
    const date = searchParams.get('date');
    const docKey = searchParams.get('docKey');
    router.replace(
      buildPipelineHref({ date, node: docKey, stage: docKey ? stageForDocumentKey(docKey) ?? undefined : undefined })
    );
  }, [router, searchParams]);
```
add `import { buildPipelineHref, stageForDocumentKey } from '@/lib/pipeline-links';` at the top.

- [ ] `StrategyToAnalysisInner` (line 48) — the thesis branch stays (`/portfolio/theses/{thesis}` is correct); replace the deliberations fallback `router.replace('/why?why=deliberations')` with:

```tsx
    router.replace(buildPipelineHref({ stage: 'selection' }));
```

- [ ] `ResearchToWhyInner` (lines 78-81) — repoint to `/pipeline`, preserving a `date` param when present:

```tsx
  useEffect(() => {
    const date = searchParams.get('date');
    router.replace(buildPipelineHref({ date }));
  }, [router, searchParams]);
```
> Leave `PerformanceToPortfolio`, `ObservabilityToSystem`, `Architecture ToSystem`, and `ThesesHubToPortfolio` redirects untouched — verified correct.

- [ ] Lift palette-open into `app-shell-context.tsx`. Add to `AppShellContextValue` (after `toggleMobileNav`):

```ts
  commandPaletteOpen: boolean;
  openCommandPalette: () => void;
  closeCommandPalette: () => void;
```
Add state + callbacks in `AppShellProvider`:

```ts
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const openCommandPalette = useCallback(() => setCommandPaletteOpen(true), []);
  const closeCommandPalette = useCallback(() => setCommandPaletteOpen(false), []);
```
and add `commandPaletteOpen, openCommandPalette, closeCommandPalette` to the `value` memo + its dependency array.

- [ ] Wire the palette to the context. In `command-palette.tsx`, replace the local `const [open, setOpen] = useState(false);` with the shared state:

```tsx
  const { commandPaletteOpen: open, openCommandPalette, closeCommandPalette } = useAppShell();
```
(import `useAppShell`). Replace `setOpen(true)`/`setOpen(false)`/`setOpen((o) => !o)` call sites accordingly: the Cmd+K handler uses `open ? closeCommandPalette() : openCommandPalette()`; the close button + escape + backdrop + `onNavigate` use `closeCommandPalette()`.

- [ ] Add the visible search pill to the **sidebar header** (`sidebar.tsx`), inside the expanded header block after the brand `<div>` (line 122 area). Use `useAppShell().openCommandPalette`:

```tsx
            <button
              type="button"
              onClick={openCommandPalette}
              className="hidden md:flex items-center gap-2 mx-6 mb-1 rounded-lg border border-border-subtle px-3 py-1.5 text-xs text-text-muted hover:text-text-secondary hover:bg-white/[0.03] transition-colors"
              aria-label="Search"
            >
              <Search size={14} className="shrink-0" />
              <span className="flex-1 text-left">Search…</span>
              <kbd className="font-mono text-[10px] text-text-muted">⌘K</kbd>
            </button>
```
(import `Search` from `lucide-react` and destructure `openCommandPalette` from `useAppShell()` in the sidebar). Place it in the nav region so it is hidden when collapsed.

- [ ] Add the mobile Search button in `mobile-app-bar.tsx` — replace the empty `<div className="h-9 w-9 shrink-0" aria-hidden />` (line 33) with a real button:

```tsx
        <button
          type="button"
          onClick={openCommandPalette}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border-subtle text-text-primary hover:bg-white/[0.06]"
          aria-label="Search"
        >
          <Search size={20} strokeWidth={2} />
        </button>
```
(import `Search` from `lucide-react`; destructure `openCommandPalette` from `useAppShell()`).

- [ ] Write/extend the redirect test `components/legacy-spa-redirect.test.tsx` asserting the three re-pointed targets resolve to `/pipeline...` (mock `next/navigation` `useRouter().replace` and `useSearchParams`, render each redirect component, assert `replace` called with a `/pipeline` href). If a redirect test file does not exist, create it following the `sidebar.test.tsx` mocking pattern.
- [ ] Run it: `npx vitest run components/legacy-spa-redirect.test.tsx components/command-palette.test.tsx` — expect PASS.
- [ ] Verify the static build: `npx next build` — expect PASS.
- [ ] Commit: `git commit -am "refactor(olympus): re-point Why redirects to Pipeline + visible ⌘K search pill (F2)"`

---

## Task 10: F6 — shared `ConvictionMeter` + `SignedConvictionBadge` components

**Files:** Create `frontend/olympus/components/shared/conviction-meter.tsx`, `frontend/olympus/components/shared/signed-conviction-badge.tsx` / Test: `frontend/olympus/components/shared/conviction.test.tsx`.
**Interfaces:** Pure-presentational. Produces (consumed identically by Holdings, Theses, Performance):
- `ConvictionMeter({ value, max?, srLabel }: { value: number; max?: number; srLabel: string }): JSX.Element` — cyan pip/dot meter for UNSIGNED strength. Used for `positions.conviction` (1–3, integer pips) and `theses.confidence` (0.0–1.0 → filled fraction). Caller passes integers with `max=3` for positions, or pre-scales confidence to a 0–`max` value.
- `SignedConvictionBadge({ value }: { value: number }): JSX.Element` — signed `+N`/`−N` badge (fin-green for ≥0, fin-red for <0) for `decision_log.conviction`. **Domain is −5..+5** (`decision_log.conviction` → `AnalystPayload.conviction_score`, `ge=-5 le=5`, per `lib/decision-scorecard.ts`); render any signed int, **do NOT clamp** to ±3. The ONLY accent on its row.

These encode three *different* real quantities (slop guard): unsigned per-row strength (meter, cyan) vs signed stance (badge, fin-green/red). Each instance must be the only accent on its row.

- [ ] Write the failing test `components/shared/conviction.test.tsx`:

```ts
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { ConvictionMeter } from './conviction-meter';
import { SignedConvictionBadge } from './signed-conviction-badge';

describe('ConvictionMeter (F6 unsigned cyan)', () => {
  it('renders `value` filled pips out of `max` with an sr-only label', () => {
    const html = renderToStaticMarkup(
      createElement(ConvictionMeter, { value: 2, max: 3, srLabel: 'Conviction 2 of 3' })
    );
    expect((html.match(/data-filled="true"/g) ?? []).length).toBe(2);
    expect((html.match(/data-filled="false"/g) ?? []).length).toBe(1);
    expect(html).toContain('Conviction 2 of 3');
  });
});

describe('SignedConvictionBadge (F6 signed)', () => {
  it('prefixes a sign and is the fin-green/red semantic only', () => {
    expect(renderToStaticMarkup(createElement(SignedConvictionBadge, { value: 3 }))).toContain('+3');
    expect(renderToStaticMarkup(createElement(SignedConvictionBadge, { value: 3 }))).toContain('text-fin-green');
    expect(renderToStaticMarkup(createElement(SignedConvictionBadge, { value: -2 }))).toContain('−2');
    expect(renderToStaticMarkup(createElement(SignedConvictionBadge, { value: -2 }))).toContain('text-fin-red');
  });
});
```

- [ ] Run it: `npx vitest run components/shared/conviction.test.tsx` — expect FAIL (modules do not exist).
- [ ] Implement `components/shared/conviction-meter.tsx`:

```tsx
/**
 * F6 — the single canonical UNSIGNED conviction encoding: a cyan pip/dot meter.
 * Used for `positions.conviction` (1–3 integer pips, max=3) and pre-scaled
 * `theses.confidence`. Cyan `--accent` is the ONLY color here (F5): filled pips
 * are accent, empty pips are border-subtle. Must be the only accent on its row.
 */
export function ConvictionMeter({
  value,
  max = 3,
  srLabel,
}: {
  value: number;
  max?: number;
  srLabel: string;
}) {
  const filled = Math.max(0, Math.min(max, Math.round(value)));
  return (
    <span className="inline-flex items-center gap-1" role="img" aria-label={srLabel}>
      {Array.from({ length: max }).map((_, i) => {
        const isFilled = i < filled;
        return (
          <span
            key={i}
            data-filled={isFilled ? 'true' : 'false'}
            className={`h-1.5 w-1.5 rounded-full ${
              isFilled ? 'bg-fin-blue' : 'bg-border-subtle'
            }`}
          />
        );
      })}
      <span className="sr-only">{srLabel}</span>
    </span>
  );
}
```
> `bg-fin-blue` resolves to `--accent` (cyan) per `globals.css:31` — this is the single conviction encoding the F5 rule permits.

- [ ] Implement `components/shared/signed-conviction-badge.tsx`:

```tsx
/**
 * F6 — the SIGNED stance badge: `decision_log.conviction` (−5..+5; maps to
 * AnalystPayload.conviction_score, ge=-5 le=5 — render any signed int, do NOT clamp).
 * fin-green for a positive/neutral stance, fin-red for negative — the strict
 * signed-financial-value semantic (F5). The only accent on its row.
 */
export function SignedConvictionBadge({ value }: { value: number }) {
  const sign = value < 0 ? '−' : '+';
  const tone = value < 0 ? 'text-fin-red border-fin-red/35' : 'text-fin-green border-fin-green/35';
  return (
    <span
      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums ${tone}`}
    >
      {sign}
      {Math.abs(value)}
    </span>
  );
}
```

- [ ] Run it: `npx vitest run components/shared/conviction.test.tsx` — expect PASS.
- [ ] Commit: `git commit -am "feat(olympus): shared ConvictionMeter + SignedConvictionBadge (F6)"`

---

## Task 11: F7 — canonical `AsOfBadge` (relocate to shared, consume snapshot-staleness) + Settings Docs hotfix guard

**Files:** Create `frontend/olympus/components/shared/as-of-badge.tsx`; Modify `frontend/olympus/components/overview/as-of-badge.tsx` (re-export shim) / Test: `frontend/olympus/components/shared/as-of-badge.test.tsx`, extend `frontend/olympus/components/settings-content.test.tsx`.
**Interfaces:** Consumes `isStale` / `formatAge` from `lib/snapshot-staleness.ts` (existing). Produces the single canonical `AsOfBadge` (consumed by Settings canonical Status block, Today inline pill, System freshness banner — Phases 1/8).

`AsOfBadge` today (in `components/overview/as-of-badge.tsx`) derives staleness from the date string alone and ignores `snapshot-staleness.ts`. F7 makes it the single component, optionally consuming a `created_at` timestamp for true age, while preserving the date-only fast path so existing callers don't break.

- [ ] Write the failing test `components/shared/as-of-badge.test.tsx`:

```ts
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/components/ui', () => ({
  Badge: (p: { children?: unknown; className?: string }) =>
    createElement('span', { 'data-badge': true, className: p.className }, p.children as never),
}));

import { AsOfBadge } from './as-of-badge';

const now = new Date('2026-06-24T16:00:00Z');

describe('AsOfBadge (F7 canonical)', () => {
  it('shows a fresh inline pill for a same/prev-day date (date-only path)', () => {
    const html = renderToStaticMarkup(createElement(AsOfBadge, { date: '2026-06-23', now }));
    expect(html).toContain('as of Jun 23');
    expect(html).not.toContain('stale');
  });
  it('marks stale + shows formatAge when a createdAt > threshold is given', () => {
    const html = renderToStaticMarkup(
      createElement(AsOfBadge, { date: '2026-06-20', createdAt: '2026-06-20T16:00:00Z', now })
    );
    expect(html).toContain('stale');
    expect(html).toContain('4d ago');
  });
});
```

- [ ] Run it: `npx vitest run components/shared/as-of-badge.test.tsx` — expect FAIL (module does not exist).
- [ ] Implement `components/shared/as-of-badge.tsx` (upgrades the existing logic; adds the optional `createdAt` timestamp path via `snapshot-staleness`):

```tsx
'use client';

import { Badge } from '@/components/ui';
import { isStale, formatAge, DEFAULT_SNAPSHOT_STALENESS_HOURS } from '@/lib/snapshot-staleness';

/**
 * F7 — the single freshness component. Two presentations from one source:
 * Settings/System render the labelled Status block; Today renders a glanceable
 * inline pill. When `createdAt` (daily_snapshots.created_at, UTC) is supplied we
 * use the true-age `isStale`/`formatAge` path; otherwise we fall back to the
 * date-only "today or yesterday is fresh" window the snapshot fetch uses.
 */
export function AsOfBadge({
  date,
  createdAt,
  now,
  staleHours = DEFAULT_SNAPSHOT_STALENESS_HOURS,
}: {
  date: string | null;
  createdAt?: string | null;
  now?: Date;
  staleHours?: number;
}) {
  if (!date) return null;
  const ref = now ?? new Date();

  let stale: boolean;
  let agePart = '';
  if (createdAt) {
    stale = isStale(createdAt, staleHours, ref);
    const age = formatAge(createdAt, ref);
    agePart = age ? ` · ${age}` : '';
  } else {
    const yesterday = new Date(ref);
    yesterday.setUTCDate(yesterday.getUTCDate() - 1);
    stale = date < yesterday.toISOString().slice(0, 10);
  }

  const label = `as of ${formatAsOf(date)}${agePart}`;
  if (stale) {
    return (
      <Badge variant="amber" className="font-mono">
        {label} · stale
      </Badge>
    );
  }
  return <span className="font-mono text-[10px] text-text-muted tracking-wide">{label}</span>;
}

/** "2026-06-13" → "Jun 13". Falls back to the raw string on a parse miss. */
function formatAsOf(date: string): string {
  const m = date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return date;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mi = Number(m[2]) - 1;
  if (mi < 0 || mi > 11) return date;
  return `${months[mi]} ${Number(m[3])}`;
}
```

- [ ] Convert `components/overview/as-of-badge.tsx` into a re-export shim so existing importers (the regime hero) keep working without churn:

```tsx
export { AsOfBadge } from '@/components/shared/as-of-badge';
```
Then `grep -rn "overview/as-of-badge" components app` and confirm every importer still type-checks (the new prop set is a superset; `{ date, now }` callers are unaffected).

- [ ] Run it: `npx vitest run components/shared/as-of-badge.test.tsx` — expect PASS.
- [ ] **Settings Docs hotfix guard.** The hotfix is already applied in `settings-content.tsx:29` (`href="/system"`). Add a regression guard to `components/settings-content.test.tsx` so it can never silently revert:

```ts
  it('points Docs at /system, never the retired /architecture', () => {
    const html = render();
    expect(html).toContain('href="/system"');
    expect(html).not.toContain('/architecture');
  });
```

- [ ] Run it: `npx vitest run components/settings-content.test.tsx` — expect PASS.
- [ ] Verify no stray `/architecture` href remains in user-facing components: `grep -rn '"/architecture"\|href=./architecture' components app` — expect no matches (only the `routeActive` absorb-regex + redirect + prose comments mention "architecture", which are correct).
- [ ] Commit: `git commit -am "feat(olympus): canonical AsOfBadge via snapshot-staleness + Settings Docs hotfix guard (F7)"`

---

## Task 12: F5 token-hygiene purge + F8 copy-voice sweep + backend issue filing

**Files:** Modify `frontend/olympus/components/portfolio/AllocationsPositionsTable.tsx:123`, `frontend/olympus/components/portfolio/PositionDrilldown.tsx:336`, `frontend/olympus/components/today/why-today.tsx`, `frontend/olympus/components/why/deliberations-tab.tsx`, `frontend/olympus/components/portfolio/tabs/PerformanceTab.tsx` / Test: covered by the surface page tests staying green + a lint guard.
**Interfaces:** None produced — this is a hygiene sweep that establishes the F5/F8 baseline the per-surface tasks inherit. Per-surface owners apply the *same* rule to their own components in Phases 1–3; this task removes the cross-cutting literals that exist *today* and would otherwise conflict if touched per-surface.

> Scope discipline: F5/F8 are "one rule applied verbatim everywhere." Phase 0 purges only the literals that already exist on shared/today/holdings code so the rule is demonstrably enforced from day one; deep per-surface restyling belongs to that surface's phase task. Do not redesign these components here — only swap off-palette literals for tokens and fix operator-voice strings that are not the surface owner's responsibility.

- [ ] Purge the raw-blue weight-bar literal in `AllocationsPositionsTable.tsx:123`. Replace the `rgba(59,130,246,0.16)` linear-gradient with a token-driven bar using `color-mix` against `--color-fin-blue` (cyan):

```tsx
              const bar = `linear-gradient(90deg, color-mix(in srgb, var(--color-fin-blue) 16%, transparent) 0%, color-mix(in srgb, var(--color-fin-blue) 16%, transparent) ${pctOfMax}%, rgba(255,255,255,0) ${pctOfMax}%)`;
```

- [ ] Purge the `#a78bfa` drilldown line in `PositionDrilldown.tsx:336` — replace `stroke="#a78bfa"` with the cyan accent token:

```tsx
                  stroke="var(--color-fin-blue)"
```

- [ ] Purge `text-fin-purple` everywhere it is a literal class. `grep -rn "text-fin-purple" components` → `today/why-today.tsx`, `why/deliberations-tab.tsx`, `portfolio/tabs/PerformanceTab.tsx`. Replace each `text-fin-purple` occurrence with `text-fin-blue` (both alias `--accent`; the rename removes the dead "purple encodes nothing" literal so the F5 rule reads true in the source). Use a scoped replace per file (do NOT global-replace across the repo — confirm each is a chrome/link/accent use, not a financial value):

```
sed-equivalent: in each of the three files, `text-fin-purple` → `text-fin-blue`
```
Apply via Edit per occurrence so each is reviewed in context.

- [ ] F8 copy sweep — fix the operator-voice strings that are NOT a single surface owner's job. The deep per-surface copy (Theses "Expand for DB snapshots", System file paths/CLI flags, Documents "No files found") is owned by those phase tasks; Phase 0 only fixes any operator-voice string in shared/today chrome touched above. Re-grep after the token edits: `grep -rn "(database)\|No files found\|migration 041" components/today components/shared` — fix any hit found to product voice; if none, note "no shared-scope F8 hits — per-surface copy deferred to phase tasks."

- [ ] Add a lightweight lint guard so the purged literals cannot creep back. Create `frontend/olympus/lib/token-hygiene.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    const p = join(dir, e);
    if (e === 'node_modules' || e === '.next') continue;
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|css)$/.test(e)) out.push(p);
  }
  return out;
}

describe('F5 token hygiene', () => {
  const files = walk(join(__dirname, '..', 'components'));
  it('no text-fin-purple literal survives in components', () => {
    const offenders = files.filter((f) => readFileSync(f, 'utf8').includes('text-fin-purple'));
    expect(offenders).toEqual([]);
  });
  it('no #a78bfa or raw rgba(59,130,246) literal survives in components', () => {
    const offenders = files.filter((f) => {
      const s = readFileSync(f, 'utf8');
      return s.includes('#a78bfa') || s.includes('rgba(59,130,246') || s.includes('rgba(59, 130, 246');
    });
    expect(offenders).toEqual([]);
  });
});
```
> Note: this guard scopes to `components/` only (the `globals.css:35` `--color-fin-purple` *alias definition* legitimately remains as a back-compat token; only the literal *class usages* are purged). The `rgba(59,130,246,0.12)`/`0.08` recharts fills in `performance-chart-workspace.tsx`/`PositionContributionChart.tsx`/`PositionPriceChart.tsx`/`DeltaDaySummary.tsx` are owned by Phase-3 Performance + Phase-2 Documents tasks — extend the guard's offender match to those files in those phases, not here, to avoid breaking untouched surfaces. The guard above intentionally matches only the two literals Phase 0 purges from Holdings (the table bar) + the drilldown line; widen it per-phase.

- [ ] Run it: `npx vitest run lib/token-hygiene.test.ts` — expect PASS after the purges.
- [ ] Run the full suite to confirm nothing regressed: `npx vitest run` — expect PASS (150+ tests green).
- [ ] **File the four backend issues** (the durable fixes live backend-side; reference as `Fixes #<N>` placeholders here). Use `gh issue create` against the backlog (the `digithings-ai` org project), one per item, each labelled `backend`/`digiquant`:
  1. `weight_pct` seeding fix — dedupe overlapping category rows so position weights + cash reconcile to 100% (D1). Frontend interim: `lib/book-reconciliation.ts` (Task 5).
  2. `backtest-seed` — seed `nav_history` (≥2 points) + a resolved `decision_log` batch so time-series surfaces populate for demos (D2). Program-level data-ops task; unblocks Phase 3 Performance.
  3. Canonicalize `positions.thesis_id` to match `theses.thesis_id` (F4 durable fix). Frontend interim: `lib/thesis-id.ts` (Task 4).
  4. Populate `theses.linked_market_thesis_id` so the market→vehicle thesis hierarchy has live data (Phase 2 Theses two-tier fallback depends on it).

  Record the four issue numbers in the redesign tracking issue and back-reference them in the commit body below as `Refs #<N1> #<N2> #<N3> #<N4>`.

- [ ] Commit: `git commit -am "refactor(olympus): purge off-palette literals + F5 hygiene guard (F5/F8)$(printf '\n\nRefs #<weight_pct> #<backtest-seed> #<thesis_id> #<linked_market_thesis_id>')"` (substitute the real issue numbers).

---

## Done criteria (Phase 0 exit)

- [ ] `npx vitest run` green from `frontend/olympus` (150+ plumbing + page tests + the new Phase-0 tests).
- [ ] `npx tsc --noEmit` clean.
- [ ] `npx next build` exports cleanly (the `/pipeline` route is reachable, nav has no 404).
- [ ] The Phase-0 contract surface is exported and importable: `mapThesisRow`, `fetchAtlasRunDiagnostics`, `reconcileBook`, `joinPositionsToThesis`, `buildPipelineHref`/`stageForDocumentKey`, `ConvictionMeter`/`SignedConvictionBadge`, the canonical `AsOfBadge`, widened `Thesis`/`Position`/`AtlasRunDiagnostics`.
- [ ] Four backend issues filed and referenced.
