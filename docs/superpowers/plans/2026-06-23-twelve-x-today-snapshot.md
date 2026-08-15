# Twelve-X "Today" Snapshot Redesign (Part A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Olympus twelve-x **Today** tab into a single-screen daily snapshot — focal trade idea(s) + always-on digest brief above the fold, a consensus "what changed" strip, then a briefs slideshow + today's-events timeline, each with a "see more →" pass-through, plus a new Briefs index view.

**Architecture:** Pure data helpers + thin Supabase fetchers in `lib/twelve-x/fetch.ts` feed presentational components in `components/twelve-x/`. `TwelveXClient` orchestrates fetching/URL-state; `TodayTab` composes the new section components. All new files are twelve-x-only — no shared-shell edits (that's Part B).

**Tech Stack:** Next.js 16 (App Router, static export, `output: 'export'`, `basePath: '/olympus'`), React 19 (`'use client'`), Tailwind v4, `@supabase/supabase-js` (anon key, RLS), Vitest (unit tests for pure helpers), lucide-react icons.

**Spec:** `docs/superpowers/specs/2026-06-23-twelve-x-today-snapshot-design.md`

## Global Constraints

- Olympus app dir: `frontend/olympus`. All paths below are relative to it.
- Every twelve-x component is a client component — first line `'use client';`.
- Reuse existing tokens/classes: `glass-card`, `text-text-primary/secondary/muted`, `border-border-subtle`, `bg-bg-secondary`, `.fin-green/.fin-red/.fin-amber/.fin-blue`; sign semantics green=bullish/long, red=bearish/short, amber=watch.
- Data access goes through the existing `querySupabase(...)` retry wrapper and the `twelveXSupabase` client; gate every fetcher on `isTwelveXConfigured()` and return `[]`/`null` when unconfigured (match the existing fetchers exactly).
- Canonical run date is already threaded as `runDate` from `TwelveXClient` (digest ?? intelligence ?? latestConsensus). Use it; do not re-resolve per section.
- Do **not** touch `components/subpage-tab-bar.tsx`, `app-frame.tsx`, `sidebar.tsx`, `mobile-app-bar.tsx`, or add a tab to the tab bar (Part B).
- Build/verify needs deps: the worktree has no `node_modules` — symlink from the main checkout before building (see Task 6).
- Pre-existing baseline: `tsc --noEmit` reports 2 errors in `lib/security-headers.test.ts` only — ignore those; your changes must add zero new errors.

---

### Task 1: Data layer — trade ideas, today's briefs, today's events

**Files:**
- Modify: `lib/twelve-x/types.ts` (add `FxTradeIdeaRow`)
- Modify: `lib/twelve-x/fetch.ts` (add `getTradeIdeas`, `getTodayBriefs`, `sortTodayBriefs`, `getTodayEvents`)
- Test: `lib/twelve-x/fetch.test.ts` (add tests for `sortTodayBriefs` + `getTodayEvents` filter)

**Interfaces:**
- Consumes (existing): `querySupabase`, `isTwelveXConfigured`, `twelveXSupabase`, `getUpcomingEvents()`, `eventLocalDateKey(row)`, types `FxBriefRow`, `FxEconomicCalendarRow`, `CurrencyView`, `BRIEF_COLUMNS`, `asCurrencyViews`.
- Produces (later tasks rely on these exact signatures):
  - `interface FxTradeIdeaRow { run_date: string; rank: number; pair: string; direction: string; title: string; thesis: string; catalyst: string; levels: unknown[]; citations: unknown[]; as_of: string; }`
  - `getTradeIdeas(runDate: string): Promise<FxTradeIdeaRow[]>` — ordered by `rank` asc.
  - `getTodayBriefs(runDate: string): Promise<FxBriefRow[]>` — briefs for that run_date, returned already sorted by `sortTodayBriefs`.
  - `sortTodayBriefs(briefs: FxBriefRow[]): FxBriefRow[]` — pure; relevance(high→med→low) → #currency_views desc → report_date desc.
  - `getTodayEvents(): Promise<FxEconomicCalendarRow[]>` — upcoming events filtered to the viewer-local "today".

- [ ] **Step 1: Add the `FxTradeIdeaRow` type.** In `lib/twelve-x/types.ts`, after `ConfluenceCatalyst` (end of file), add:

```typescript
/**
 * `fx_trade_ideas_snapshot` (twelve-x migration 012) — the curated, synthesized
 * actionable trade ideas for a run. PRIMARY KEY (run_date, rank). anon-readable.
 */
export interface FxTradeIdeaRow {
  run_date: string; // date (ISO YYYY-MM-DD)
  rank: number; // int (1 = top)
  pair: string; // e.g. "USD/JPY"
  direction: string; // 'long' | 'short' | ...
  title: string; // e.g. "JPY SHORT — via USD/JPY"
  thesis: string;
  catalyst: string;
  levels: unknown[]; // jsonb array of broker levels/targets
  citations: unknown[]; // jsonb array of TradeIdeaCitation
  as_of: string; // timestamptz (ISO)
}
```

- [ ] **Step 2: Write the failing test for `sortTodayBriefs`.** In `lib/twelve-x/fetch.test.ts`, add (import `sortTodayBriefs` and `FxBriefRow` at the top of the file alongside the existing imports):

```typescript
import { sortTodayBriefs } from './fetch';
import type { FxBriefRow } from './types';

const brief = (over: Partial<FxBriefRow>): FxBriefRow => ({
  run_date: '2026-06-23', source_file: 's.pdf', source_url: null,
  document_title: null, broker_name: 'X', analyst_names: null,
  report_date: '2026-06-23', trader_relevance: 'low', central_thesis: null,
  brief_markdown: null, currency_views: [], risk_events: null,
  macro_themes: null, positioning_signals: null, ...over,
});

describe('sortTodayBriefs', () => {
  it('orders by relevance (high→low), then breadth, then newest report_date', () => {
    const lowOld = brief({ source_file: 'a', trader_relevance: 'low', report_date: '2026-06-20' });
    const highFew = brief({ source_file: 'b', trader_relevance: 'high', currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'high' }] });
    const highMany = brief({ source_file: 'c', trader_relevance: 'high', currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'high' }, { currency: 'EUR', direction: 'bearish', conviction: 'low' }] });
    const medNew = brief({ source_file: 'd', trader_relevance: 'medium', report_date: '2026-06-23' });
    const out = sortTodayBriefs([lowOld, highFew, highMany, medNew]).map((b) => b.source_file);
    expect(out).toEqual(['c', 'b', 'd', 'a']);
  });

  it('is stable and pure (does not mutate input)', () => {
    const input = [brief({ source_file: 'a' }), brief({ source_file: 'b' })];
    const copy = [...input];
    sortTodayBriefs(input);
    expect(input).toEqual(copy);
  });
});
```

- [ ] **Step 3: Run the test, verify it fails.**

Run: `npx --no-install vitest run lib/twelve-x/fetch.test.ts -t sortTodayBriefs`
Expected: FAIL — `sortTodayBriefs is not a function` (not yet exported).

- [ ] **Step 4: Implement `sortTodayBriefs` + the fetchers in `fetch.ts`.** Add near the brief helpers (after `getBrief`, ~line 450). `asCurrencyViews` already exists in this file; reuse it.

```typescript
const _RELEVANCE_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };

/** Pure ordering for the Today briefs slideshow: relevance desc, then breadth
 *  (# of currency_views) desc, then newest report_date desc. Does not mutate. */
export function sortTodayBriefs(briefs: FxBriefRow[]): FxBriefRow[] {
  const rel = (b: FxBriefRow) => _RELEVANCE_RANK[(b.trader_relevance ?? '').toLowerCase()] ?? 0;
  const breadth = (b: FxBriefRow) => asCurrencyViews(b.currency_views).length;
  return [...briefs].sort(
    (a, b) =>
      rel(b) - rel(a) ||
      breadth(b) - breadth(a) ||
      (b.report_date ?? '').localeCompare(a.report_date ?? '')
  );
}

/** Curated trade ideas for a run_date (rank 1 = top). `[]` when unconfigured/empty. */
export async function getTradeIdeas(runDate: string): Promise<FxTradeIdeaRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  if (!runDate) return [];
  const rows = await querySupabase<FxTradeIdeaRow[]>((sb) =>
    sb
      .from('fx_trade_ideas_snapshot')
      .select('run_date, rank, pair, direction, title, thesis, catalyst, levels, citations, as_of')
      .eq('run_date', runDate)
      .order('rank', { ascending: true })
  );
  return rows ?? [];
}

/** Today's research briefs for a run_date, pre-sorted for the slideshow. */
export async function getTodayBriefs(runDate: string): Promise<FxBriefRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  if (!runDate) return [];
  const rows = await querySupabase<FxBriefRow[]>(
    (sb) =>
      sb
        .from('fx_research_history')
        .select(BRIEF_COLUMNS)
        .eq('run_date', runDate)
        .order('report_date', { ascending: false }) as unknown as PromiseLike<{
        data: FxBriefRow[] | null;
        error: unknown;
      }>
  );
  return sortTodayBriefs(rows ?? []);
}

/** Upcoming macro events narrowed to the viewer-local "today". */
export async function getTodayEvents(): Promise<FxEconomicCalendarRow[]> {
  const all = await getUpcomingEvents();
  const todayKey = eventLocalDateKey({ event_datetime_utc: new Date().toISOString(), event_date: '' });
  return all.filter((e) => eventLocalDateKey(e) === todayKey);
}
```

Add `FxTradeIdeaRow` to the `import type { ... } from './types'` block at the top of `fetch.ts`.

- [ ] **Step 5: Write the failing test for `getTodayEvents` filtering.** `getTodayEvents` calls Supabase, so test the *filter* via a thin seam: export a pure helper and test it. Add to `fetch.ts`:

```typescript
/** Pure: keep only rows whose local event date matches `todayKey`. */
export function filterEventsToDay(
  events: FxEconomicCalendarRow[],
  todayKey: string
): FxEconomicCalendarRow[] {
  return events.filter((e) => eventLocalDateKey(e) === todayKey);
}
```

Refactor `getTodayEvents` to use it: `return filterEventsToDay(all, todayKey);`. Then in `fetch.test.ts`:

```typescript
import { filterEventsToDay } from './fetch';
import type { FxEconomicCalendarRow } from './types';

const ev = (over: Partial<FxEconomicCalendarRow>): FxEconomicCalendarRow => ({
  id: 1, external_id: 'e', event_date: '2026-06-23', event_time: null,
  country: 'US', event_name: 'X', category: 'c', impact: 'low',
  actual: null, forecast: null, prior: null, event_datetime_utc: null, ...over,
});

describe('filterEventsToDay', () => {
  it('keeps only events whose local date equals the target key', () => {
    const todayUtc = ev({ id: 1, event_datetime_utc: '2026-06-23T14:30:00Z', event_date: '2026-06-23' });
    const tomorrow = ev({ id: 2, event_datetime_utc: '2026-06-24T14:30:00Z', event_date: '2026-06-24' });
    const allDayToday = ev({ id: 3, event_datetime_utc: null, event_date: '2026-06-23' });
    const key = '2026-06-23';
    const out = filterEventsToDay([todayUtc, tomorrow, allDayToday], key).map((e) => e.id);
    expect(out).toContain(1);
    expect(out).toContain(3);
    expect(out).not.toContain(2);
  });
});
```

(Note: the UTC-instant events resolve via the viewer's local tz; run CI/tests in UTC so `2026-06-23T14:30Z` → `2026-06-23`. This matches the existing `eventLocalDateKey` behavior.)

- [ ] **Step 6: Run the data-layer tests, verify pass.**

Run: `npx --no-install vitest run lib/twelve-x/fetch.test.ts`
Expected: PASS (existing tests + the new `sortTodayBriefs` and `filterEventsToDay` tests). `tsc --noEmit` shows no new errors.

- [ ] **Step 7: Commit.**

```bash
git add lib/twelve-x/types.ts lib/twelve-x/fetch.ts lib/twelve-x/fetch.test.ts
git commit -m "feat(twelve-x): data layer for Today snapshot — trade ideas, today briefs/events"
```

---

### Task 2: `TradeIdeasPanel` + `DigestBrief` components

**Files:**
- Create: `components/twelve-x/TradeIdeasPanel.tsx`
- Create: `components/twelve-x/DigestBrief.tsx`

**Interfaces:**
- Consumes: `FxTradeIdeaRow` (Task 1), `FxConfluenceSnapshotRow` (existing), `useTwelveX()` (existing — `openBrief`, `crossLink`), `FxDailyDigestRow` shape (`{ run_date, summary, key_themes: string[], doc_count, broker_count }`).
- Produces:
  - `TradeIdeasPanel({ ideas, confluence }: { ideas: FxTradeIdeaRow[]; confluence: FxConfluenceSnapshotRow[] })`
  - `DigestBrief({ digest }: { digest: { run_date: string; summary: string; key_themes: string[]; doc_count: number; broker_count: number } | null })`

- [ ] **Step 1: Create `TradeIdeasPanel.tsx`.** Focal `#1` card + compact `#2…N` rows + an expand toggle revealing the confluence reads. Empty state when `ideas` is empty.

```tsx
'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { FxTradeIdeaRow, FxConfluenceSnapshotRow } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';

function dirClass(direction: string): string {
  const d = direction.toLowerCase();
  if (d.includes('long') || d.includes('bull')) return 'text-fin-green';
  if (d.includes('short') || d.includes('bear')) return 'text-fin-red';
  return 'text-text-muted';
}

function firstSource(citations: unknown[]): string | null {
  for (const c of citations) {
    if (c && typeof c === 'object' && typeof (c as Record<string, unknown>).source_file === 'string') {
      return (c as Record<string, unknown>).source_file as string;
    }
  }
  return null;
}

export default function TradeIdeasPanel({
  ideas,
  confluence,
}: {
  ideas: FxTradeIdeaRow[];
  confluence: FxConfluenceSnapshotRow[];
}) {
  const { crossLink, openBrief } = useTwelveX();
  const [expanded, setExpanded] = useState(false);

  if (ideas.length === 0) {
    return (
      <section className="glass-card p-5">
        <header className="mb-2 flex items-baseline gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Today&rsquo;s trade ideas</h2>
        </header>
        <p className="text-sm text-text-muted">No curated trade idea for today yet.</p>
      </section>
    );
  }

  const [top, ...rest] = ideas;
  const topSource = firstSource(top.citations);

  return (
    <section className="glass-card flex flex-col gap-3 p-5">
      <header className="flex items-baseline gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Today&rsquo;s trade ideas</h2>
        <span className="font-mono text-[10px] text-text-muted">· {ideas.length}</span>
        <button
          type="button"
          className="ml-auto text-[11px] text-fin-blue hover:underline"
          onClick={() => crossLink({ kind: 'tab', tab: 'intelligence' })}
        >
          see more →
        </button>
      </header>

      {/* Focal #1 */}
      <button
        type="button"
        className="rounded-lg border border-fin-green/30 bg-fin-green/[0.06] p-4 text-left transition-colors hover:border-fin-blue/50"
        onClick={() => topSource && openBrief(topSource, top.run_date)}
      >
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-text-muted">#1</span>
          <span className="font-semibold text-text-primary">{top.pair}</span>
          <span className={`text-xs font-semibold uppercase ${dirClass(top.direction)}`}>{top.direction}</span>
        </div>
        <p className="mt-1 text-sm text-text-primary">{top.title}</p>
        {top.thesis ? <p className="mt-1 line-clamp-2 text-xs text-text-secondary">{top.thesis}</p> : null}
        {top.catalyst ? <p className="mt-1 text-[11px] text-text-muted">Catalyst: {top.catalyst}</p> : null}
      </button>

      {/* #2…N rows */}
      {rest.map((idea) => {
        const src = firstSource(idea.citations);
        return (
          <button
            key={`${idea.run_date}-${idea.rank}`}
            type="button"
            className="flex items-center gap-2 rounded-md border border-border-subtle px-3 py-2 text-left text-xs transition-colors hover:border-fin-blue/50"
            onClick={() => src && openBrief(src, idea.run_date)}
          >
            <span className="font-mono text-[10px] text-text-muted">#{idea.rank}</span>
            <span className="font-semibold text-text-primary">{idea.pair}</span>
            <span className={`font-semibold uppercase ${dirClass(idea.direction)}`}>{idea.direction}</span>
            <span className="ml-auto truncate text-text-muted">{idea.title}</span>
          </button>
        );
      })}

      {/* Expand → confluence reads */}
      {confluence.length > 0 ? (
        <div>
          <button
            type="button"
            className="flex items-center gap-1 text-[11px] text-text-secondary hover:text-fin-blue"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            {expanded ? 'Hide' : 'Expand'} confluence reads ({confluence.length})
          </button>
          {expanded ? (
            <ul className="mt-2 grid gap-1">
              {confluence.map((c) => (
                <li key={`${c.run_date}-${c.rank}`} className="flex items-center gap-2 rounded-md border border-border-subtle px-3 py-1.5 text-xs">
                  <span className="font-mono text-[10px] text-text-muted">#{c.rank}</span>
                  <span className="font-semibold text-text-primary">{c.currency}</span>
                  <span className={`uppercase ${dirClass(c.direction)}`}>{c.direction}</span>
                  <button
                    type="button"
                    className="ml-auto text-fin-blue hover:underline"
                    onClick={() => crossLink({ kind: 'currency', currency: c.currency })}
                  >
                    trend →
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 2: Create `DigestBrief.tsx`.** Always-on summary + key-theme chips; empty state when no digest.

```tsx
'use client';

import { FileText } from 'lucide-react';

export default function DigestBrief({
  digest,
}: {
  digest: { run_date: string; summary: string; key_themes: string[]; doc_count: number; broker_count: number } | null;
}) {
  if (!digest) {
    return (
      <section className="glass-card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Digest brief</h2>
        <p className="mt-2 text-sm text-text-muted">No digest for today yet.</p>
      </section>
    );
  }
  return (
    <section className="glass-card flex flex-col gap-2 p-5">
      <header className="flex items-baseline gap-2">
        <FileText size={15} className="shrink-0 text-fin-blue" aria-hidden />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Digest brief</h2>
        <span className="ml-auto font-mono text-[10px] text-text-muted">
          {digest.doc_count} docs · {digest.broker_count} brokers
        </span>
      </header>
      <p className="whitespace-pre-line text-sm leading-relaxed text-text-primary">{digest.summary}</p>
      {digest.key_themes.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {digest.key_themes.map((t) => (
            <span key={t} className="rounded-full border border-border-subtle px-2.5 py-0.5 text-[11px] text-text-secondary">
              {t}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 3: Typecheck.**

Run: `npx --no-install tsc --noEmit -p tsconfig.json 2>&1 | grep -E 'TradeIdeasPanel|DigestBrief' || echo CLEAN`
Expected: `CLEAN` (no errors in the two new files).

- [ ] **Step 4: Commit.**

```bash
git add components/twelve-x/TradeIdeasPanel.tsx components/twelve-x/DigestBrief.tsx
git commit -m "feat(twelve-x): TradeIdeasPanel (focal+list+expand) and DigestBrief"
```

---

### Task 3: `BriefsSlideshow` + `EventsMiniTimeline` components

**Files:**
- Create: `components/twelve-x/BriefsSlideshow.tsx`
- Create: `components/twelve-x/EventsMiniTimeline.tsx`

**Interfaces:**
- Consumes: `FxBriefRow`, `FxEconomicCalendarRow` (existing); `useTwelveX()` (`openBrief`, `crossLink`); `hasResolvedTime`, `eventInstant` (existing fetch helpers).
- Produces:
  - `BriefsSlideshow({ briefs, onSeeMore }: { briefs: FxBriefRow[]; onSeeMore: () => void })`
  - `EventsMiniTimeline({ events }: { events: FxEconomicCalendarRow[] })`

- [ ] **Step 1: Create `BriefsSlideshow.tsx`.** One card visible, ◀▶ + dots, opens the brief; "see more" calls `onSeeMore`.

```tsx
'use client';

import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { FxBriefRow } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';

export default function BriefsSlideshow({
  briefs,
  onSeeMore,
}: {
  briefs: FxBriefRow[];
  onSeeMore: () => void;
}) {
  const { openBrief } = useTwelveX();
  const [i, setI] = useState(0);

  if (briefs.length === 0) {
    return (
      <section className="glass-card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Today&rsquo;s briefs</h2>
        <p className="mt-2 text-sm text-text-muted">No research briefs for today yet.</p>
      </section>
    );
  }

  const idx = Math.min(i, briefs.length - 1);
  const b = briefs[idx];
  const go = (d: number) => setI((idx + d + briefs.length) % briefs.length);

  return (
    <section className="glass-card flex flex-col gap-3 p-5">
      <header className="flex items-baseline gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Today&rsquo;s briefs</h2>
        <span className="font-mono text-[10px] text-text-muted">{idx + 1}/{briefs.length}</span>
        <button type="button" className="ml-auto text-[11px] text-fin-blue hover:underline" onClick={onSeeMore}>
          see all →
        </button>
      </header>

      <div className="flex items-center gap-2">
        <button type="button" aria-label="Previous brief" className="rounded-md border border-border-subtle p-1 text-text-muted hover:text-fin-blue" onClick={() => go(-1)}>
          <ChevronLeft size={16} />
        </button>
        <button
          type="button"
          className="min-w-0 flex-1 rounded-lg border border-border-subtle p-3 text-left transition-colors hover:border-fin-blue/50"
          onClick={() => openBrief(b.source_file, b.run_date)}
        >
          <div className="flex items-center gap-2 text-[11px] text-text-muted">
            <span className="font-semibold text-text-secondary">{b.broker_name ?? 'Unknown desk'}</span>
            {b.trader_relevance ? <span className="uppercase">· {b.trader_relevance}</span> : null}
          </div>
          <p className="mt-1 truncate text-sm font-medium text-text-primary">{b.document_title ?? b.source_file}</p>
          {b.central_thesis ? <p className="mt-1 line-clamp-2 text-xs text-text-secondary">{b.central_thesis}</p> : null}
        </button>
        <button type="button" aria-label="Next brief" className="rounded-md border border-border-subtle p-1 text-text-muted hover:text-fin-blue" onClick={() => go(1)}>
          <ChevronRight size={16} />
        </button>
      </div>

      <div className="flex justify-center gap-1">
        {briefs.map((bb, n) => (
          <button
            key={bb.source_file}
            type="button"
            aria-label={`Go to brief ${n + 1}`}
            className={`h-1.5 w-1.5 rounded-full ${n === idx ? 'bg-fin-blue' : 'bg-white/20'}`}
            onClick={() => setI(n)}
          />
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Create `EventsMiniTimeline.tsx`.** Compact today timeline, impact-colored, see more → Events tab.

```tsx
'use client';

import { CalendarClock } from 'lucide-react';
import type { FxEconomicCalendarRow } from '@/lib/twelve-x/types';
import { hasResolvedTime, eventInstant } from '@/lib/twelve-x/fetch';
import { useTwelveX } from './context';

function impactClass(impact: string): string {
  const i = impact.trim().toLowerCase();
  if (i === 'high') return 'bg-fin-red';
  if (i === 'medium') return 'bg-fin-amber';
  return 'bg-text-muted/60';
}

function localTime(e: FxEconomicCalendarRow): string {
  const inst = eventInstant(e);
  if (inst) return inst.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  return e.event_time ?? '—';
}

export default function EventsMiniTimeline({ events }: { events: FxEconomicCalendarRow[] }) {
  const { crossLink } = useTwelveX();
  return (
    <section className="glass-card flex flex-col gap-3 p-5">
      <header className="flex items-baseline gap-2">
        <CalendarClock size={15} className="shrink-0 text-fin-blue" aria-hidden />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Today&rsquo;s events</h2>
        <button type="button" className="ml-auto text-[11px] text-fin-blue hover:underline" onClick={() => crossLink({ kind: 'tab', tab: 'events' })}>
          see more →
        </button>
      </header>
      {events.length === 0 ? (
        <p className="text-sm text-text-muted">No macro events scheduled today.</p>
      ) : (
        <ul className="grid gap-1.5">
          {events.map((e) => (
            <li key={e.id} className="flex items-center gap-2.5 text-xs">
              <span className="w-14 shrink-0 text-right font-mono tabular-nums text-text-secondary">{localTime(e)}</span>
              <span className={`h-2 w-2 shrink-0 rounded-full ${impactClass(e.impact)}`} aria-hidden />
              <span className="font-mono text-[10px] uppercase text-text-muted">{e.country}</span>
              <span className="truncate text-text-primary">{e.event_name}</span>
              {!hasResolvedTime(e) ? <span className="text-text-muted/60" title="venue-local time">≈</span> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Typecheck.**

Run: `npx --no-install tsc --noEmit -p tsconfig.json 2>&1 | grep -E 'BriefsSlideshow|EventsMiniTimeline' || echo CLEAN`
Expected: `CLEAN`.

- [ ] **Step 4: Commit.**

```bash
git add components/twelve-x/BriefsSlideshow.tsx components/twelve-x/EventsMiniTimeline.tsx
git commit -m "feat(twelve-x): BriefsSlideshow and EventsMiniTimeline"
```

---

### Task 4: `BriefsIndex` view

**Files:**
- Create: `components/twelve-x/BriefsIndex.tsx`

**Interfaces:**
- Consumes: `FxBriefRow`; `useTwelveX()` (`openBrief`).
- Produces: `BriefsIndex({ briefs, onBack }: { briefs: FxBriefRow[]; onBack: () => void })`

- [ ] **Step 1: Create `BriefsIndex.tsx`.** Full-width list/grid of today's briefs (already sorted), each opens the brief; a back link to Today.

```tsx
'use client';

import { ArrowLeft } from 'lucide-react';
import type { FxBriefRow } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';

export default function BriefsIndex({ briefs, onBack }: { briefs: FxBriefRow[]; onBack: () => void }) {
  const { openBrief } = useTwelveX();
  return (
    <section className="flex flex-col gap-4">
      <header className="flex items-center gap-3">
        <button type="button" className="flex items-center gap-1 text-xs text-fin-blue hover:underline" onClick={onBack}>
          <ArrowLeft size={14} /> Today
        </button>
        <h2 className="text-base font-semibold text-text-primary">Today&rsquo;s briefs</h2>
        <span className="ml-auto font-mono text-[10px] text-text-muted">{briefs.length}</span>
      </header>
      {briefs.length === 0 ? (
        <div className="glass-card p-10 text-center text-sm text-text-muted">No research briefs for today yet.</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {briefs.map((b) => (
            <button
              key={b.source_file}
              type="button"
              className="glass-card p-4 text-left transition-colors hover:border-fin-blue/50"
              onClick={() => openBrief(b.source_file, b.run_date)}
            >
              <div className="flex items-center gap-2 text-[11px] text-text-muted">
                <span className="font-semibold text-text-secondary">{b.broker_name ?? 'Unknown desk'}</span>
                {b.trader_relevance ? <span className="uppercase">· {b.trader_relevance}</span> : null}
              </div>
              <p className="mt-1 text-sm font-medium text-text-primary">{b.document_title ?? b.source_file}</p>
              {b.central_thesis ? <p className="mt-1 line-clamp-3 text-xs text-text-secondary">{b.central_thesis}</p> : null}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Typecheck + commit.**

Run: `npx --no-install tsc --noEmit -p tsconfig.json 2>&1 | grep BriefsIndex || echo CLEAN` → `CLEAN`
```bash
git add components/twelve-x/BriefsIndex.tsx
git commit -m "feat(twelve-x): BriefsIndex view"
```

---

### Task 5: `TwelveXClient` integration + `TodayTab` rewrite

**Files:**
- Modify: `components/twelve-x/TwelveXClient.tsx` (fetch trade ideas / today briefs / today events; add `?view=briefs` URL state; pass data to `TodayTab`; render `BriefsIndex` when `view==='briefs'`)
- Modify (rewrite): `components/twelve-x/TodayTab.tsx` (A1 layout composing the new sections)

**Interfaces:**
- Consumes: `getTradeIdeas`, `getTodayBriefs`, `getTodayEvents` (Task 1); `TradeIdeasPanel`, `DigestBrief`, `BriefsSlideshow`, `EventsMiniTimeline` (Tasks 2–3); `BriefsIndex` (Task 4); existing `consensusDeltas`, `intelligence` (confluence), `MoversStrip`, `canonicalRunDate`, `TwelveXProvider`/`useTwelveX`.
- Produces: `TodayTab({ digest, tradeIdeas, confluence, deltas, briefs, events, onSeeAllBriefs }: { digest: DigestData; tradeIdeas: FxTradeIdeaRow[]; confluence: FxConfluenceSnapshotRow[]; deltas: ConsensusDeltaSet; briefs: FxBriefRow[]; events: FxEconomicCalendarRow[]; onSeeAllBriefs: () => void })`

- [ ] **Step 1: Extend `TwelveXData` + the load in `TwelveXClient.tsx`.** Add `tradeIdeas`, `todayBriefs`, `todayEvents` to the `TwelveXData` interface; add the three fetchers to the `Promise.all` (they parallelize — no added latency); they need the canonical run_date, so resolve trade ideas/briefs after the digest/intelligence dates are known (fetch them in a second `await` using `canonicalRunDate`, mirroring how `eventOpinions` is already fetched after `opinionsDate`). Concretely, after the existing `Promise.all` and the `opinionsDate`/`eventOpinions` lines:

```typescript
const canonical = intelligence[0]?.run_date ?? digest?.run_date ?? null;
const [tradeIdeas, todayBriefs, todayEvents] = canonical
  ? await Promise.all([getTradeIdeas(canonical), getTodayBriefs(canonical), getTodayEvents()])
  : [[], [], await getTodayEvents()];
```

Add `tradeIdeas`, `todayBriefs`, `todayEvents` to the `setData({...})` call. Add the imports `getTradeIdeas, getTodayBriefs, getTodayEvents` and types `FxTradeIdeaRow` to the existing import blocks.

- [ ] **Step 2: Add `?view=briefs` URL state.** In `TwelveXClient.tsx`:
  - Add state: `const [view, setView] = useState<'briefs' | null>(() => (readParam('view') === 'briefs' ? 'briefs' : null));`
  - Extend `syncUrl(...)` to also accept/serialize `view` (add `if (view) p.set('view', view);` and a `view` parameter, threading it through the existing `setTab`/`openBrief`/etc. callers — pass the current `view`).
  - Add `const openBriefsIndex = useCallback(() => { setView('briefs'); syncUrl(tab, brief, ledgerCcy, 'briefs'); }, [tab, brief, ledgerCcy]);` and `const closeBriefsIndex = useCallback(() => { setView(null); syncUrl(tab, brief, ledgerCcy, null); }, [tab, brief, ledgerCcy]);`

- [ ] **Step 3: Render `BriefsIndex` or `TodayTab`.** In the Today branch of the tab switch, render the index when `view==='briefs'`:

```tsx
) : (
  view === 'briefs' ? (
    <BriefsIndex briefs={data?.todayBriefs ?? []} onBack={closeBriefsIndex} />
  ) : (
    <TodayTab
      digest={data?.digest ?? null}
      tradeIdeas={data?.tradeIdeas ?? []}
      confluence={data?.intelligence ?? []}
      deltas={consensusDeltas}
      briefs={data?.todayBriefs ?? []}
      events={data?.todayEvents ?? []}
      onSeeAllBriefs={openBriefsIndex}
    />
  )
)
```

Import `BriefsIndex` and `TodayTab` (TodayTab already imported). Keep `TwelveXProvider` wrapping unchanged.

- [ ] **Step 4: Rewrite `TodayTab.tsx` to the A1 layout.** Replace the file contents:

```tsx
'use client';

import type {
  FxConfluenceSnapshotRow,
  FxEconomicCalendarRow,
  FxBriefRow,
  FxTradeIdeaRow,
  ConsensusDeltaSet,
} from '@/lib/twelve-x/types';
import TradeIdeasPanel from './TradeIdeasPanel';
import DigestBrief from './DigestBrief';
import BriefsSlideshow from './BriefsSlideshow';
import EventsMiniTimeline from './EventsMiniTimeline';
import MoversStrip from './MoversStrip';
import { useTwelveX } from './context';

type DigestData = { run_date: string; summary: string; key_themes: string[]; doc_count: number; broker_count: number } | null;

export default function TodayTab({
  digest,
  tradeIdeas,
  confluence,
  deltas,
  briefs,
  events,
  onSeeAllBriefs,
}: {
  digest: DigestData;
  tradeIdeas: FxTradeIdeaRow[];
  confluence: FxConfluenceSnapshotRow[];
  deltas: ConsensusDeltaSet;
  briefs: FxBriefRow[];
  events: FxEconomicCalendarRow[];
  onSeeAllBriefs: () => void;
}) {
  const { crossLink } = useTwelveX();
  return (
    <div className="flex flex-col gap-4">
      {/* Above the fold: trade ideas + digest brief co-lead */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_1fr]">
        <TradeIdeasPanel ideas={tradeIdeas} confluence={confluence} />
        <DigestBrief digest={digest} />
      </div>

      {/* What changed in consensus */}
      <section className="glass-card p-4">
        <header className="mb-2 flex items-baseline gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">What changed — consensus</h2>
          <button type="button" className="ml-auto text-[11px] text-fin-blue hover:underline" onClick={() => crossLink({ kind: 'tab', tab: 'consensus' })}>
            see more →
          </button>
        </header>
        {deltas.movers.length > 0 ? (
          <MoversStrip movers={deltas.movers} onSelect={(c) => crossLink({ kind: 'currency', currency: c })} title="" />
        ) : (
          <p className="text-sm text-text-muted">No prior run to compare yet.</p>
        )}
      </section>

      {/* Below the fold: briefs slideshow + today's events */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <BriefsSlideshow briefs={briefs} onSeeMore={onSeeAllBriefs} />
        <EventsMiniTimeline events={events} />
      </div>
    </div>
  );
}
```

(Confirm `MoversStrip` accepts an empty `title` to suppress its own header; if not, pass the default and drop the section's `<h2>`.)

- [ ] **Step 5: Typecheck.**

Run: `npx --no-install tsc --noEmit -p tsconfig.json 2>&1 | grep -E 'twelve-x/(TodayTab|TwelveXClient)' || echo CLEAN`
Expected: `CLEAN`.

- [ ] **Step 6: Commit.**

```bash
git add components/twelve-x/TwelveXClient.tsx components/twelve-x/TodayTab.tsx
git commit -m "feat(twelve-x): compose Today snapshot (A1) + briefs-index view + data wiring"
```

---

### Task 6: Verify — typecheck, lint, tests, build, live render

**Files:** none (verification + fixups only).

- [ ] **Step 1: Make deps available in the worktree.** Symlink from the main checkout (worktrees don't get untracked `node_modules`):

```bash
MAIN=/Users/chrisstefan/Code/digithings
WT=/Users/chrisstefan/Code/digithings/.claude/worktrees/twelve-x-today-redesign
[ -e "$WT/node_modules" ] || ln -s "$MAIN/node_modules" "$WT/node_modules"
[ -e "$WT/frontend/olympus/node_modules" ] || ln -s "$MAIN/frontend/olympus/node_modules" "$WT/frontend/olympus/node_modules"
```

- [ ] **Step 2: Typecheck (no new errors).**

Run (from `frontend/olympus`): `npx --no-install tsc --noEmit -p tsconfig.json 2>&1 | grep -E 'components/twelve-x/|lib/twelve-x/' | grep -v security-headers || echo CLEAN`
Expected: `CLEAN`.

- [ ] **Step 3: Lint twelve-x.**

Run: `npx --no-install eslint components/twelve-x lib/twelve-x`
Expected: exit 0.

- [ ] **Step 4: Unit tests.**

Run: `npx --no-install vitest run lib/twelve-x`
Expected: all pass (existing + new from Task 1).

- [ ] **Step 5: Production build.**

Run (with the twelve-x Supabase env exported as in prior work): `npm run build`
Expected: "Compiled successfully", TypeScript clean, `/twelve-x` prerendered.

- [ ] **Step 6: Live render — desktop & mobile.** Start `npm run dev -p 3210` (env exported), load `http://localhost:3210/olympus/twelve-x/`. Verify at 1440×900: trade ideas + brief co-lead and the consensus strip are above the fold; briefs slideshow + events below; the slideshow ◀▶/dots work; "see all →" opens the Briefs index (`?view=briefs`) and "Today" returns; "expand confluence" toggles. At 390×844: everything stacks single-column in priority order 1→5; no console errors. Capture screenshots.

- [ ] **Step 7: Final commit (if any fixups).**

```bash
git add -A frontend/olympus/components/twelve-x frontend/olympus/lib/twelve-x
git commit -m "fix(twelve-x): Today snapshot render fixups from verification" || echo "nothing to fix"
```

---

## Notes for the implementer

- Trade-idea `citations` carry `source_file` (per `fx_research_history`/`TradeIdeaCitation`); `firstSource()` extracts it to open the brief. If a given idea has no resolvable `source_file`, the card simply isn't clickable (no broken link) — that's intended.
- The Today layout `lg:` breakpoint is the single responsive control for Part A; the tab bar's responsiveness is Part B and must not be touched here.
- `MoversStrip`/`DeltaChip`/`computeConsensusDeltaSet` already exist and are tested; do not reimplement.
