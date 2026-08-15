---
# System (How it works) Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (- [ ]) syntax.
**Goal:** Reframe the System surface (`/system`) around one question — "is it running, is it healthy, what does it cost, and how does it work?" — by replacing the duplicated phase tables / file-path map with a two-zone surface: a glanceable live-status hero (freshness banner, run-economics tiles, failed→recovered timeline, per-phase health strip) over a demoted, de-duplicated "how it works" reference, while relocating Attribution → Performance and Position-risk → Holdings.
**Architecture:** A new `/system` route renders `<SystemPage>` (client). Zone 1 reads `atlas_run_diagnostics` directly via the Phase-0 `fetchAtlasRunDiagnostics()` (cost/tokens/cache/grounding + `breakdown` jsonb), deriving freshness with `AsOfBadge`, a failed→recovered episode grouper, and a per-phase health strip parsed from `breakdown.phaseN_outputs`. Zone 2 is static prose + a single "What a run persists" table + a deep-link to Pipeline, with CLI flags behind an `<OperatorControls>` disclosure. The legacy `/architecture` route becomes a client redirect to `/system`; the legacy `/observability` route keeps only the Decision Scorecard (Attribution/Position-risk tabs are removed there, relocated to their owning surfaces in Phase 3 / Holdings).
**Tech Stack:** Next.js 16 static export (`output:export`, `basePath /olympus`), React 19, Tailwind v4 (`@theme` tokens, `[data-theme]`), lucide-react, vitest (node env, `renderToStaticMarkup` for component tests).
## Global Constraints
- **Static export only** — `output: 'export'`, `basePath: '/olympus'`. No server actions, no dynamic route handlers, no runtime `fetch` of HTML. Everything is a client component reading Supabase from the browser.
- **Tailwind v4 tokens only** — use `@theme` tokens (`bg-bg-primary/secondary/glass`, `text-text-primary/secondary/muted`, `border-border-subtle`, `text-fin-green/red/amber`, `--accent #3DD6C4`). `glass-card` for panels; Instrument Serif (`font-display`) for marquee headlines; Geist sans/mono for body/tabular.
- **F5 token rule (verbatim):** cyan `--accent` #3DD6C4 for links / chrome / the single conviction encoding / the live-fresh dot only; `fin-green`/`fin-red` *strictly* for signed financial values; `fin-amber` for caution / stale / carried / mixed-regime / degraded; **no gradients** beyond the existing faint regime wash; **no decorative numbering** unless it encodes the system's own priority. System currently ships three color-coded card families (`fin-blue`/`fin-purple`/`fin-green` per cadence/phase/agent) and `border-${t.color}` template strings — all must be purged.
- **Empty-state discipline:** every zone element is gated on a real data predicate (≥1 diagnostics row for economics; ≥2 grouped episodes for a timeline; `breakdown.phaseN_outputs` present for the health strip). Each renders a calm, *element-specific* line ("No runs recorded yet", "history builds from the first run") — never an em-dash placeholder, a 1-row "table over time", or a single-dot chart. Some elements are simply absent rather than narrating emptiness.
- **F8 operator-voice → PM-voice:** no file paths, no CLI flags, no raw 30-row run lists as hero content. Engine internals (model routing, run cadence flags) live behind ONE collapsed "Operator controls" disclosure. Fix the stale/false "migration 041 pending / requires owner sign-off" copy — the diagnostics read is live.
- **vitest stays green:** the repo has 150+ plumbing tests plus page-level tests that MUST stay green. Run `npm test` from `frontend/olympus`. Logic (episode grouping, phase-strip parsing, economics formatting) is TDD'd with `renderToStaticMarkup`/pure-function tests in node env (no DOM, no jsdom). Pure-presentational JSX (prose, persistence table) may skip the test cycle.
- **Traceability:** every commit is conventional `feat|fix|refactor|chore(olympus): …`. This surface consumes Phase-0 outputs (`fetchAtlasRunDiagnostics`, `AsOfBadge`, `buildPipelineHref`, the `/system` nav entry); it does not redefine them. Backend issue #2 (`backtest-seed`) and the stale-copy provenance are noted inline.

---

## Consumed from Phase 0 (do not redefine — cite, import, use)

| Symbol | Module | Used by |
|---|---|---|
| `fetchAtlasRunDiagnostics(): Promise<AtlasRunDiagnostics[]>` | `lib/observability-queries.ts` | Task 2 (page loader) |
| `AtlasRunDiagnostics` interface (incl. `cached_tokens` lifted from `breakdown`, `breakdown: Record<string, unknown> \| null`) | `lib/types.ts` | Tasks 3–6 |
| `AsOfBadge({ date, createdAt?, now?, staleHours? })` | `components/shared/as-of-badge.tsx` (canonical) | Task 3 (freshness banner) |
| `buildPipelineHref({ date?, stage?, node? })` | `lib/pipeline-links.ts` | Task 7 ("See the full graph → Pipeline") |
| `/system` nav entry + `routeActive` `/system` branch | `lib/nav.ts`, `components/sidebar.tsx` | Task 1 (route lands under it) |

> **Sequencing note.** This plan is Phase 1. If executed before Phase 0 lands, Task 0 (below) provides thin local stubs so the surface compiles and tests run; the stubs are deleted the moment Phase 0 merges. **Prefer running this after Phase 0.** Every task that imports a Phase-0 symbol imports it from the contract path above — never copies its body.

---

### Task 0: (conditional) Phase-0 stub guard — skip if Phase 0 has merged

**Files:** Verify-only; create stubs **only if absent**.
**Interfaces:** Produces nothing new — guarantees the Phase-0 contract symbols resolve.

- [ ] Run the presence check; if every symbol exists, **skip this task entirely** and go to Task 1:
  ```bash
  cd frontend/olympus
  grep -q "fetchAtlasRunDiagnostics" lib/observability-queries.ts \
    && grep -q "export interface AtlasRunDiagnostics" lib/types.ts \
    && test -f components/shared/as-of-badge.tsx \
    && test -f lib/pipeline-links.ts \
    && grep -q "'/system'" lib/nav.ts \
    && echo "PHASE0_PRESENT" || echo "PHASE0_MISSING"
  ```
- [ ] If `PHASE0_MISSING`: **STOP and coordinate** — Phase 0 is the documented prerequisite and owns these files. Do not author competing versions of `fetchAtlasRunDiagnostics`, `AsOfBadge`, `buildPipelineHref`, or the nav flip; they are shared by six consumers and would conflict. Re-run after Phase 0 merges. (No commit.)

---

### Task 1: Land the `/system` route as the System surface entry point

**Files:**
- Create `frontend/olympus/app/system/page.tsx` (route shell → renders `<SystemPage>`)
- Create `frontend/olympus/components/system/system-page.tsx` (the client surface; filled across Tasks 2–8)
- Modify `frontend/olympus/app/architecture/page.tsx` (replace the old phase-table page with a redirect to `/system`)
**Interfaces:**
- Consumes: `/system` nav entry (Phase 0, Task 0 verified).
- Produces: `<SystemPage>` default export (`components/system/system-page.tsx`); the `/system` route.

- [ ] Create the route shell `app/system/page.tsx`:
  ```tsx
  import SystemPage from '@/components/system/system-page';

  export default function Page() {
    return <SystemPage />;
  }
  ```
- [ ] Create the surface skeleton `components/system/system-page.tsx` (Zone 1 / Zone 2 scaffold; the loader + zones land in later tasks). Mirror the existing subpage layout container used by `app/architecture/page.tsx` and `app/observability/page.tsx`:
  ```tsx
  'use client';

  import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';

  export default function SystemPage() {
    return (
      <div className={`${SUBPAGE_MAX} space-y-8 py-4 md:py-6`}>
        <header className="space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">
            System
          </p>
          <h1 className="font-display text-3xl tracking-tight text-text-primary sm:text-4xl">
            How Olympus works
          </h1>
          <p className="max-w-3xl text-sm leading-relaxed text-text-secondary">
            Is it running, is it healthy, what does it cost, and how does it work?
          </p>
        </header>
        {/* Zone 1 — Live status (Tasks 3–6) */}
        {/* Zone 2 — How it works (Tasks 7–8) */}
      </div>
    );
  }
  ```
- [ ] Convert the legacy `app/architecture/page.tsx` to a client redirect (the old phase-table content is deleted — it duplicates Pipeline per the spec). Replace the entire file body with:
  ```tsx
  'use client';

  import { useEffect } from 'react';
  import { useRouter } from 'next/navigation';

  // The old "Atlas Architecture" page duplicated Pipeline (phase tables + file-path map).
  // System (/system) replaces it; this keeps any bookmarked /architecture link alive.
  export default function ArchitectureRedirect() {
    const router = useRouter();
    useEffect(() => {
      router.replace('/system');
    }, [router]);
    return null;
  }
  ```
- [ ] Verify the build and lint compile:
  ```bash
  cd frontend/olympus && npm run lint && npx tsc --noEmit
  ```
  Expected: PASS (no unused imports; old `Layers/Clock/Zap/Bot/Database/Globe`, `Badge`, `SUBPAGE_MAX` heavy page gone).
- [ ] Commit:
  ```bash
  git add app/system/page.tsx components/system/system-page.tsx app/architecture/page.tsx
  git commit -m "feat(olympus): add /system route, redirect legacy /architecture to it"
  ```

---

### Task 2: Wire the diagnostics loader into SystemPage

**Files:**
- Modify `frontend/olympus/components/system/system-page.tsx`
- Test `frontend/olympus/components/system/system-page.test.tsx`
**Interfaces:**
- Consumes: `fetchAtlasRunDiagnostics(): Promise<AtlasRunDiagnostics[]>` (`lib/observability-queries.ts`), `AtlasRunDiagnostics` (`lib/types.ts`), `AtlasLoader` (`@/components/AtlasLoader`), `EmptyState` (`@/components/observability/shared`).
- Produces: `diagnostics: AtlasRunDiagnostics[]` state passed down to Zone-1 sub-components.

- [ ] Write the failing test `components/system/system-page.test.tsx`. The loader is async/effect-driven, so this test asserts the **empty-data branch** rendered synchronously by a thin presentational `SystemStatus` helper we extract; assert the page header + empty banner copy. (Use `renderToStaticMarkup`, node env.)
  ```tsx
  import { createElement } from 'react';
  import { renderToStaticMarkup } from 'react-dom/server';
  import { describe, expect, it } from 'vitest';
  import { SystemStatus } from './system-page';
  import type { AtlasRunDiagnostics } from '@/lib/types';

  function render(diagnostics: AtlasRunDiagnostics[]): string {
    return renderToStaticMarkup(createElement(SystemStatus, { diagnostics }));
  }

  describe('SystemStatus — empty', () => {
    it('shows "No runs recorded yet" when there are no diagnostics', () => {
      const html = render([]);
      expect(html).toContain('No runs recorded yet');
    });
  });
  ```
- [ ] Run it — expect FAIL (`SystemStatus` is not exported yet):
  ```bash
  cd frontend/olympus && npm test -- system-page
  ```
- [ ] In `components/system/system-page.tsx`, add the loader and the exported `SystemStatus` shell (sub-zones are stubs filled by later tasks; the empty branch is real now):
  ```tsx
  'use client';

  import { useEffect, useState } from 'react';
  import AtlasLoader from '@/components/AtlasLoader';
  import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
  import { EmptyState } from '@/components/observability/shared';
  import { fetchAtlasRunDiagnostics } from '@/lib/observability-queries';
  import type { AtlasRunDiagnostics } from '@/lib/types';

  /** Zone 1 — live status. Pure in its props so it is unit-testable. */
  export function SystemStatus({ diagnostics }: { diagnostics: AtlasRunDiagnostics[] }) {
    if (!diagnostics.length) {
      return (
        <EmptyState
          title="No runs recorded yet"
          message="The pipeline writes a diagnostics row at the end of each Atlas/Hermes run. Once a baseline or delta run completes, its status, cost, and segment health appear here."
        />
      );
    }
    return (
      <div className="flex flex-col gap-6">
        {/* FreshnessBanner — Task 3 */}
        {/* RunEconomicsRow — Task 4 */}
        {/* RunHealthTimeline — Task 5 */}
        {/* PerPhaseHealthStrip — Task 6 */}
      </div>
    );
  }
  ```
- [ ] Replace the `SystemPage` default export body to fetch + branch on loading/error/data, reusing the established effect pattern from `app/observability/page.tsx`:
  ```tsx
  export default function SystemPage() {
    const [diagnostics, setDiagnostics] = useState<AtlasRunDiagnostics[] | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
      let alive = true;
      fetchAtlasRunDiagnostics()
        .then((d) => alive && setDiagnostics(d))
        .catch(() => alive && setDiagnostics([])) // fetch is fail-soft; treat a throw as empty
        .finally(() => alive && setLoading(false));
      return () => {
        alive = false;
      };
    }, []);

    return (
      <div className={`${SUBPAGE_MAX} space-y-8 py-4 md:py-6`}>
        <header className="space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">
            System
          </p>
          <h1 className="font-display text-3xl tracking-tight text-text-primary sm:text-4xl">
            How Olympus works
          </h1>
          <p className="max-w-3xl text-sm leading-relaxed text-text-secondary">
            Is it running, is it healthy, what does it cost, and how does it work?
          </p>
        </header>

        {loading ? <AtlasLoader fullScreen={false} /> : <SystemStatus diagnostics={diagnostics ?? []} />}

        {/* Zone 2 — How it works (Tasks 7–8) */}
      </div>
    );
  }
  ```
- [ ] Run the test — expect PASS:
  ```bash
  cd frontend/olympus && npm test -- system-page
  ```
- [ ] Commit:
  ```bash
  git add components/system/system-page.tsx components/system/system-page.test.tsx
  git commit -m "feat(olympus): wire atlas_run_diagnostics loader into /system"
  ```

---

### Task 3: Zone 1 — Freshness banner (F7)

**Files:**
- Create `frontend/olympus/components/system/freshness-banner.tsx`
- Test `frontend/olympus/components/system/freshness-banner.test.tsx`
- Modify `frontend/olympus/components/system/system-page.tsx` (mount in `SystemStatus`)
**Interfaces:**
- Consumes: `AtlasRunDiagnostics` (`lib/types.ts`); `AsOfBadge({ date, createdAt?, now?, staleHours? })` (`components/shared/as-of-badge.tsx`).
- Produces: `FreshnessBanner({ latest }: { latest: AtlasRunDiagnostics })`; helper `latestSuccessfulRun(diagnostics): AtlasRunDiagnostics | null`.

**Grounding:** the canonical "fresh" episode is run `28041585974` (`status:'ok'`, `run_date:'2026-06-23'`, `run_type:'baseline'`, `finished_at:'2026-06-23 16:58:51Z'`, `segments_ok/total = 27/27`). The banner narrates the **last successful** run, not merely the newest row (the newest may be `failed`/`degraded`).

- [ ] Write the failing test `components/system/freshness-banner.test.tsx`:
  ```tsx
  import { createElement } from 'react';
  import { renderToStaticMarkup } from 'react-dom/server';
  import { describe, expect, it } from 'vitest';
  import { FreshnessBanner, latestSuccessfulRun } from './freshness-banner';
  import type { AtlasRunDiagnostics } from '@/lib/types';

  function diag(o: Partial<AtlasRunDiagnostics>): AtlasRunDiagnostics {
    return {
      run_id: 'r', run_type: 'baseline', run_date: '2026-06-23', model: null, status: 'ok',
      started_at: null, finished_at: '2026-06-23T16:58:51Z', duration_s: null,
      llm_calls: null, prompt_tokens: null, completion_tokens: null, total_tokens: null,
      cached_tokens: null, search_calls: null, grounding_ok: null, grounding_failed: null,
      est_cost_usd: null, segments_total: 27, segments_ok: 27, segments_carried: 0,
      segments_failed: 0, error_summary: null, breakdown: null, created_at: '2026-06-23T16:58:51Z',
      ...o,
    };
  }

  describe('latestSuccessfulRun', () => {
    it('skips a newer failed row and returns the ok run', () => {
      const rows = [diag({ run_id: 'fail', status: 'failed', created_at: '2026-06-23T17:10:00Z' }), diag({ run_id: 'ok' })];
      expect(latestSuccessfulRun(rows)?.run_id).toBe('ok');
    });
    it('returns null when no run succeeded', () => {
      expect(latestSuccessfulRun([diag({ status: 'failed' })])).toBeNull();
    });
  });

  describe('FreshnessBanner', () => {
    it('narrates last successful run with run type and segment count', () => {
      const html = renderToStaticMarkup(createElement(FreshnessBanner, { latest: diag({}) }));
      expect(html).toContain('Last successful run');
      expect(html).toContain('baseline');
      expect(html).toContain('27/27');
    });
  });
  ```
- [ ] Run — expect FAIL (module missing):
  ```bash
  cd frontend/olympus && npm test -- freshness-banner
  ```
- [ ] Create `components/system/freshness-banner.tsx`. `AsOfBadge` carries the stale/age treatment (F7); the banner supplies the prose. `latestSuccessfulRun` matches a status of ok/success/complete (mirror `RunHealthTab`'s `statusColor` ok-words):
  ```tsx
  'use client';

  import { AsOfBadge } from '@/components/shared/as-of-badge';
  import type { AtlasRunDiagnostics } from '@/lib/types';

  function isOk(status: string | null): boolean {
    const s = (status ?? '').toLowerCase();
    return s.includes('ok') || s.includes('success') || s === 'complete' || s === 'completed';
  }

  /** Most-recent run whose status reads as success (diagnostics are newest-first from the query). */
  export function latestSuccessfulRun(diagnostics: AtlasRunDiagnostics[]): AtlasRunDiagnostics | null {
    return diagnostics.find((d) => isOk(d.status)) ?? null;
  }

  export function FreshnessBanner({ latest }: { latest: AtlasRunDiagnostics }) {
    const segs =
      latest.segments_total != null
        ? `${latest.segments_ok ?? 0}/${latest.segments_total} segments`
        : null;
    return (
      <div className="glass-card flex flex-wrap items-center gap-x-3 gap-y-1 p-4">
        <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-[var(--accent)]" aria-hidden />
        <span className="text-sm text-text-primary">
          Last successful run{' '}
          <span className="font-medium">{latest.run_date ?? '—'}</span>
          {latest.run_type ? <span className="text-text-secondary"> · {latest.run_type}</span> : null}
          {segs ? <span className="text-text-secondary"> · {segs}</span> : null}
        </span>
        <AsOfBadge date={latest.run_date} createdAt={latest.created_at} />
      </div>
    );
  }
  ```
- [ ] Mount it in `SystemStatus` (above the economics row). The `SystemStatus` already guards `diagnostics.length`; compute the successful run and, when none succeeded, show an amber "no successful run yet" line (the per-row failures still render in the timeline, Task 5):
  ```tsx
  // inside SystemStatus, replace the {/* FreshnessBanner — Task 3 */} comment:
  {(() => {
    const ok = latestSuccessfulRun(diagnostics);
    return ok ? (
      <FreshnessBanner latest={ok} />
    ) : (
      <div className="glass-card p-4 text-sm text-fin-amber">
        No successful run yet — the most recent attempts did not complete. See the timeline below.
      </div>
    );
  })()}
  ```
  Add the import at the top of `system-page.tsx`:
  ```tsx
  import { FreshnessBanner, latestSuccessfulRun } from './freshness-banner';
  ```
- [ ] Run — expect PASS:
  ```bash
  cd frontend/olympus && npm test -- freshness-banner system-page
  ```
- [ ] Commit:
  ```bash
  git add components/system/freshness-banner.tsx components/system/freshness-banner.test.tsx components/system/system-page.tsx
  git commit -m "feat(olympus): add System freshness banner (F7) reading last successful run"
  ```

---

### Task 4: Zone 1 — Run-economics row (D3, the differentiator)

**Files:**
- Create `frontend/olympus/components/system/run-economics-row.tsx`
- Test `frontend/olympus/components/system/run-economics-row.test.tsx`
- Modify `frontend/olympus/components/system/system-page.tsx` (mount)
**Interfaces:**
- Consumes: `AtlasRunDiagnostics` (`lib/types.ts`); `StatTile` (`@/components/observability/shared`).
- Produces: `RunEconomicsRow({ latest })`; pure helpers `formatUsd(n)`, `formatTokens(n)`, `cacheHitPct(latest)`.

**Grounding:** `est_cost_usd` and `total_tokens` are real columns; `cached_tokens` is **lifted from `breakdown` by the Phase-0 query** (top-level `breakdown.cached_tokens`, or `breakdown.by_kind.chat.cached_tokens`) — the component reads `latest.cached_tokens` (already lifted), never re-parses `breakdown`. Live baseline target from the spec: `$0.62/run · 1.64M tokens (39% cached) · 163 LLM calls · grounding 31/31`. (Current rows have moved on — e.g. `$1.50`, 4.87M tokens, 41.6% cached, 343 calls — so the test fixtures use the spec's anchor values to lock the formatting, not live values.)

- [ ] Write the failing test `components/system/run-economics-row.test.tsx`:
  ```tsx
  import { describe, expect, it } from 'vitest';
  import { formatUsd, formatTokens, cacheHitPct } from './run-economics-row';
  import type { AtlasRunDiagnostics } from '@/lib/types';

  function diag(o: Partial<AtlasRunDiagnostics>): AtlasRunDiagnostics {
    return {
      run_id: 'r', run_type: 'baseline', run_date: '2026-06-23', model: null, status: 'ok',
      started_at: null, finished_at: null, duration_s: null, llm_calls: 163,
      prompt_tokens: null, completion_tokens: null, total_tokens: 1_640_000, cached_tokens: 639_600,
      search_calls: null, grounding_ok: 31, grounding_failed: 0, est_cost_usd: 0.616,
      segments_total: 27, segments_ok: 27, segments_carried: 0, segments_failed: 0,
      error_summary: null, breakdown: null, created_at: '2026-06-23T16:58:51Z', ...o,
    };
  }

  describe('run-economics formatting', () => {
    it('formats cost to cents with a leading $', () => {
      expect(formatUsd(0.616)).toBe('$0.62');
    });
    it('renders null cost as an em-dash', () => {
      expect(formatUsd(null)).toBe('—');
    });
    it('abbreviates tokens to millions', () => {
      expect(formatTokens(1_640_000)).toBe('1.64M');
    });
    it('computes cache-hit pct from cached/total tokens', () => {
      expect(cacheHitPct(diag({}))).toBe(39);
    });
    it('returns null cache-hit when total tokens absent', () => {
      expect(cacheHitPct(diag({ total_tokens: null }))).toBeNull();
    });
  });
  ```
- [ ] Run — expect FAIL:
  ```bash
  cd frontend/olympus && npm test -- run-economics-row
  ```
- [ ] Create `components/system/run-economics-row.tsx`. Reuse `StatTile` (tabular-nums baked in). The "39% cached" chip is the cost story; render it neutral cyan (chrome), not green (it is not a signed financial value — F5):
  ```tsx
  'use client';

  import { StatTile } from '@/components/observability/shared';
  import type { AtlasRunDiagnostics } from '@/lib/types';

  export function formatUsd(n: number | null): string {
    if (n == null || Number.isNaN(n)) return '—';
    return `$${n.toFixed(2)}`;
  }

  export function formatTokens(n: number | null): string {
    if (n == null || Number.isNaN(n)) return '—';
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
    return `${n}`;
  }

  /** Whole-percent cache-hit, or null when total tokens are unknown. */
  export function cacheHitPct(d: AtlasRunDiagnostics): number | null {
    if (d.total_tokens == null || d.total_tokens === 0) return null;
    return Math.round(((d.cached_tokens ?? 0) / d.total_tokens) * 100);
  }

  export function RunEconomicsRow({ latest }: { latest: AtlasRunDiagnostics }) {
    const cache = cacheHitPct(latest);
    const grounding =
      latest.grounding_ok != null
        ? `${latest.grounding_ok}/${(latest.grounding_ok ?? 0) + (latest.grounding_failed ?? 0)}`
        : '—';
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Cost / run" value={formatUsd(latest.est_cost_usd)} />
        <StatTile
          label="Tokens"
          value={formatTokens(latest.total_tokens)}
          sub={
            cache != null ? (
              <span className="text-[var(--accent)]">{cache}% cached → cheaper</span>
            ) : undefined
          }
        />
        <StatTile label="LLM calls" value={latest.llm_calls != null ? latest.llm_calls : '—'} />
        <StatTile
          label="Grounding"
          value={grounding}
          color={(latest.grounding_failed ?? 0) > 0 ? 'text-fin-amber' : undefined}
        />
      </div>
    );
  }
  ```
- [ ] Mount in `SystemStatus`, reading the **newest** row for economics (the cost of the latest attempt, successful or not — use `diagnostics[0]`):
  ```tsx
  // replace {/* RunEconomicsRow — Task 4 */}
  <RunEconomicsRow latest={diagnostics[0]} />
  ```
  Import: `import { RunEconomicsRow } from './run-economics-row';`
- [ ] Run — expect PASS:
  ```bash
  cd frontend/olympus && npm test -- run-economics-row
  ```
- [ ] Commit:
  ```bash
  git add components/system/run-economics-row.tsx components/system/run-economics-row.test.tsx components/system/system-page.tsx
  git commit -m "feat(olympus): expose run economics (cost/tokens/cache/grounding) on /system (D3)"
  ```

---

### Task 5: Zone 1 — Failed→recovered run-health timeline

**Files:**
- Create `frontend/olympus/lib/run-episodes.ts` (pure grouping logic)
- Create `frontend/olympus/components/system/run-health-timeline.tsx`
- Test `frontend/olympus/lib/run-episodes.test.ts`
- Modify `frontend/olympus/components/system/system-page.tsx` (mount)
**Interfaces:**
- Consumes: `AtlasRunDiagnostics` (`lib/types.ts`).
- Produces: `RunEpisode` type + `groupRunEpisodes(diagnostics): RunEpisode[]`; `RunHealthTimeline({ diagnostics })`.

**Grounding:** the 2026-06-23 pair is the canonical episode — run `28038765604` (`failed`, `error_summary: "chain/hermes: …ON CONFLICT…"`) at 16:34, then run `28041585974` (`ok`) at 16:43, **same `run_date` + same `run_type` (baseline)**. Grouping key = `(run_date, run_type)`. An episode that ends `ok` after ≥1 failure is "recovered"; render as red→green with "N attempts · recovered" — not two anonymous rows. Render as a vertical event list (the spec forbids a sparse 30-row skeleton when few runs exist).

- [ ] Write the failing test `lib/run-episodes.test.ts`:
  ```ts
  import { describe, expect, it } from 'vitest';
  import { groupRunEpisodes } from './run-episodes';
  import type { AtlasRunDiagnostics } from './types';

  function diag(o: Partial<AtlasRunDiagnostics>): AtlasRunDiagnostics {
    return {
      run_id: 'r', run_type: 'baseline', run_date: '2026-06-23', model: null, status: 'ok',
      started_at: null, finished_at: null, duration_s: null, llm_calls: null,
      prompt_tokens: null, completion_tokens: null, total_tokens: null, cached_tokens: null,
      search_calls: null, grounding_ok: null, grounding_failed: null, est_cost_usd: null,
      segments_total: 27, segments_ok: 27, segments_carried: 0, segments_failed: 0,
      error_summary: null, breakdown: null, created_at: '2026-06-23T16:43:00Z', ...o,
    };
  }

  describe('groupRunEpisodes', () => {
    it('collapses a failed→ok pair on the same date+type into one recovered episode', () => {
      const rows = [
        diag({ run_id: 'ok', status: 'ok', created_at: '2026-06-23T16:43:00Z' }),
        diag({ run_id: 'fail', status: 'failed', created_at: '2026-06-23T16:34:00Z',
          error_summary: 'chain/hermes: ON CONFLICT' }),
      ];
      const eps = groupRunEpisodes(rows);
      expect(eps).toHaveLength(1);
      expect(eps[0].attempts).toBe(2);
      expect(eps[0].outcome).toBe('recovered');
      expect(eps[0].runDate).toBe('2026-06-23');
    });

    it('keeps distinct date+type pairs as separate episodes', () => {
      const eps = groupRunEpisodes([
        diag({ run_id: 'a', run_date: '2026-06-24', run_type: 'delta', status: 'degraded' }),
        diag({ run_id: 'b', run_date: '2026-06-23', run_type: 'baseline', status: 'ok' }),
      ]);
      expect(eps).toHaveLength(2);
      expect(eps[0].outcome).toBe('degraded'); // newest episode first
    });

    it('marks an all-failed episode as failed', () => {
      const eps = groupRunEpisodes([diag({ status: 'failed' })]);
      expect(eps[0].outcome).toBe('failed');
    });
  });
  ```
- [ ] Run — expect FAIL:
  ```bash
  cd frontend/olympus && npm test -- run-episodes
  ```
- [ ] Create `lib/run-episodes.ts`. Episodes keyed on `(run_date|run_type)`; attempts ordered oldest→newest within; outcome from the final (newest) attempt; "recovered" iff final is ok AND ≥1 earlier attempt was not ok. Episodes returned newest-first by their latest attempt's `created_at`:
  ```ts
  import type { AtlasRunDiagnostics } from './types';

  export type RunOutcome = 'ok' | 'recovered' | 'degraded' | 'failed';

  export interface RunEpisode {
    key: string;
    runDate: string | null;
    runType: string | null;
    attempts: number;
    outcome: RunOutcome;
    latest: AtlasRunDiagnostics;
    errorSummary: string | null;
  }

  function classify(status: string | null): 'ok' | 'degraded' | 'failed' {
    const s = (status ?? '').toLowerCase();
    if (s.includes('ok') || s.includes('success') || s === 'complete' || s === 'completed') return 'ok';
    if (s.includes('degrad') || s.includes('partial') || s.includes('carr')) return 'degraded';
    return 'failed';
  }

  function ts(d: AtlasRunDiagnostics): number {
    return d.created_at ? Date.parse(d.created_at) : 0;
  }

  export function groupRunEpisodes(diagnostics: AtlasRunDiagnostics[]): RunEpisode[] {
    const byKey = new Map<string, AtlasRunDiagnostics[]>();
    for (const d of diagnostics) {
      const key = `${d.run_date ?? '?'}|${d.run_type ?? '?'}`;
      const arr = byKey.get(key) ?? [];
      arr.push(d);
      byKey.set(key, arr);
    }
    const episodes: RunEpisode[] = [];
    for (const [key, attemptsUnsorted] of byKey) {
      const attempts = [...attemptsUnsorted].sort((a, b) => ts(a) - ts(b)); // oldest → newest
      const latest = attempts[attempts.length - 1];
      const finalClass = classify(latest.status);
      const hadFailure = attempts.slice(0, -1).some((a) => classify(a.status) !== 'ok');
      const outcome: RunOutcome =
        finalClass === 'ok' ? (hadFailure ? 'recovered' : 'ok') : finalClass;
      episodes.push({
        key,
        runDate: latest.run_date,
        runType: latest.run_type,
        attempts: attempts.length,
        outcome,
        latest,
        errorSummary: attempts.find((a) => a.error_summary)?.error_summary ?? null,
      });
    }
    return episodes.sort((a, b) => ts(b.latest) - ts(a.latest)); // newest episode first
  }
  ```
- [ ] Run — expect PASS:
  ```bash
  cd frontend/olympus && npm test -- run-episodes
  ```
- [ ] Create the presentational `components/system/run-health-timeline.tsx` (vertical event list; dot color per outcome per F5 — green=ok/recovered, amber=degraded, red=failed; cyan is reserved for chrome so it is NOT used for status dots):
  ```tsx
  'use client';

  import { SectionCard } from '@/components/observability/shared';
  import { groupRunEpisodes, type RunEpisode, type RunOutcome } from '@/lib/run-episodes';
  import type { AtlasRunDiagnostics } from '@/lib/types';

  const DOT: Record<RunOutcome, string> = {
    ok: 'bg-fin-green',
    recovered: 'bg-fin-green',
    degraded: 'bg-fin-amber',
    failed: 'bg-fin-red',
  };

  function summary(ep: RunEpisode): string {
    const parts = [ep.runType ?? 'run'];
    if (ep.attempts > 1) parts.push(`${ep.attempts} attempts`);
    parts.push(ep.outcome);
    return parts.join(' · ');
  }

  export function RunHealthTimeline({ diagnostics }: { diagnostics: AtlasRunDiagnostics[] }) {
    const episodes = groupRunEpisodes(diagnostics);
    if (!episodes.length) return null;
    return (
      <SectionCard title="Run health" subtitle="Recent pipeline runs, grouped by day — retries collapse into one episode.">
        <ol className="flex flex-col gap-3">
          {episodes.map((ep) => (
            <li key={ep.key} className="flex items-start gap-3">
              <span className={`mt-1.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full ${DOT[ep.outcome]}`} aria-hidden />
              <div className="min-w-0">
                <p className="text-sm text-text-primary">
                  <span className="font-medium">{ep.runDate ?? '—'}</span>{' '}
                  <span className="text-text-secondary">— {summary(ep)}</span>
                </p>
                {ep.outcome !== 'ok' && ep.errorSummary ? (
                  <p className="mt-0.5 truncate text-xs text-text-muted" title={ep.errorSummary}>
                    {ep.errorSummary}
                  </p>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      </SectionCard>
    );
  }
  ```
- [ ] Mount in `SystemStatus`:
  ```tsx
  // replace {/* RunHealthTimeline — Task 5 */}
  <RunHealthTimeline diagnostics={diagnostics} />
  ```
  Import: `import { RunHealthTimeline } from './run-health-timeline';`
- [ ] Run the suite — expect PASS:
  ```bash
  cd frontend/olympus && npm test -- run-episodes system-page
  ```
- [ ] Commit:
  ```bash
  git add lib/run-episodes.ts lib/run-episodes.test.ts components/system/run-health-timeline.tsx components/system/system-page.tsx
  git commit -m "feat(olympus): narrate failed→recovered runs as one episode on /system"
  ```

---

### Task 6: Zone 1 — Per-phase health strip from `breakdown` jsonb

**Files:**
- Create `frontend/olympus/lib/run-phase-health.ts` (pure parser)
- Create `frontend/olympus/components/system/per-phase-health-strip.tsx`
- Test `frontend/olympus/lib/run-phase-health.test.ts`
- Modify `frontend/olympus/components/system/system-page.tsx` (mount)
**Interfaces:**
- Consumes: `AtlasRunDiagnostics` (`lib/types.ts`); `breakdown: Record<string, unknown> | null`.
- Produces: `PhaseHealth` type + `parsePhaseHealth(breakdown): PhaseHealth[]`; `PerPhaseHealthStrip({ latest })`.

**Grounding (live jsonb shape, verified):** `breakdown` holds keys `phase1_outputs`, `phase2_outputs`, `phase3_output` (NOTE: phase 3 is singular `_output`, the rest plural `_outputs`), `phase4_outputs`, `phase5_outputs`, each `{ ok, failed, carried }`. The parser must accept both `phaseN_output` and `phaseN_outputs`. Stage names mirror Pipeline's vocabulary (the spec: "mirrors Pipeline's stage vocabulary"); per the spec's Pipeline mapping, phases 1–5 are the Research stage fan-outs. Map each `phaseN` to a human label (`Phase 1` … `Phase 5`) and order numerically.

- [ ] Write the failing test `lib/run-phase-health.test.ts` (fixture mirrors the verified live `breakdown`):
  ```ts
  import { describe, expect, it } from 'vitest';
  import { parsePhaseHealth } from './run-phase-health';

  const breakdown = {
    phase1_outputs: { ok: 5, failed: 0, carried: 1 },
    phase2_outputs: { ok: 2, failed: 0, carried: 0 },
    phase3_output: { ok: 1, failed: 0, carried: 0 }, // singular in live data
    phase4_outputs: { ok: 3, failed: 0, carried: 2 },
    phase5_outputs: { ok: 8, failed: 0, carried: 5 },
    cached_tokens: 2028160,
    by_kind: {},
  };

  describe('parsePhaseHealth', () => {
    it('extracts phases 1–5 in numeric order, accepting singular phase3_output', () => {
      const phases = parsePhaseHealth(breakdown);
      expect(phases.map((p) => p.phase)).toEqual([1, 2, 3, 4, 5]);
      expect(phases[0]).toMatchObject({ phase: 1, ok: 5, carried: 1, failed: 0 });
      expect(phases[2]).toMatchObject({ phase: 3, ok: 1 });
    });
    it('returns [] for null/non-object breakdown', () => {
      expect(parsePhaseHealth(null)).toEqual([]);
      expect(parsePhaseHealth({ by_kind: {} })).toEqual([]);
    });
    it('ignores non-phase keys', () => {
      expect(parsePhaseHealth({ cached_tokens: 1, models: [] })).toEqual([]);
    });
  });
  ```
- [ ] Run — expect FAIL:
  ```bash
  cd frontend/olympus && npm test -- run-phase-health
  ```
- [ ] Create `lib/run-phase-health.ts`. Match keys `^phase(\d+)_outputs?$`; coerce `{ok,failed,carried}` defensively (jsonb values are `unknown`):
  ```ts
  export interface PhaseHealth {
    phase: number;
    ok: number;
    failed: number;
    carried: number;
  }

  const PHASE_KEY = /^phase(\d+)_outputs?$/;

  function num(v: unknown): number {
    return typeof v === 'number' && Number.isFinite(v) ? v : 0;
  }

  export function parsePhaseHealth(breakdown: Record<string, unknown> | null): PhaseHealth[] {
    if (!breakdown || typeof breakdown !== 'object') return [];
    const out: PhaseHealth[] = [];
    for (const [key, raw] of Object.entries(breakdown)) {
      const m = key.match(PHASE_KEY);
      if (!m || raw == null || typeof raw !== 'object') continue;
      const v = raw as Record<string, unknown>;
      out.push({
        phase: Number(m[1]),
        ok: num(v.ok),
        failed: num(v.failed),
        carried: num(v.carried),
      });
    }
    return out.sort((a, b) => a.phase - b.phase);
  }
  ```
- [ ] Run — expect PASS:
  ```bash
  cd frontend/olympus && npm test -- run-phase-health
  ```
- [ ] Create `components/system/per-phase-health-strip.tsx`. A segmented bar (one segment per phase) sized by total outputs; green=ok, amber=carried, red=failed (F5 — these are health states, not signed values, so amber/red are the caution/failure semantics, which is permitted). Renders nothing when the parse is empty (element-absent discipline):
  ```tsx
  'use client';

  import { SectionCard } from '@/components/observability/shared';
  import { parsePhaseHealth } from '@/lib/run-phase-health';
  import type { AtlasRunDiagnostics } from '@/lib/types';

  export function PerPhaseHealthStrip({ latest }: { latest: AtlasRunDiagnostics }) {
    const phases = parsePhaseHealth(latest.breakdown);
    if (!phases.length) return null;
    return (
      <SectionCard
        title="Per-phase health"
        subtitle="Outputs produced per research phase — ok, carried forward, or failed — for the latest run."
      >
        <div className="flex flex-col gap-2">
          {phases.map((p) => {
            const total = p.ok + p.carried + p.failed || 1;
            return (
              <div key={p.phase} className="flex items-center gap-3 text-xs">
                <span className="w-16 shrink-0 text-text-muted">Phase {p.phase}</span>
                <span className="flex h-2 flex-1 overflow-hidden rounded-full bg-bg-secondary" aria-hidden>
                  <span className="bg-fin-green" style={{ width: `${(p.ok / total) * 100}%` }} />
                  <span className="bg-fin-amber" style={{ width: `${(p.carried / total) * 100}%` }} />
                  <span className="bg-fin-red" style={{ width: `${(p.failed / total) * 100}%` }} />
                </span>
                <span className="w-20 shrink-0 text-right tabular-nums text-text-secondary">
                  {p.ok}/{total}
                  {p.carried > 0 ? <span className="text-fin-amber"> ·{p.carried}c</span> : null}
                </span>
              </div>
            );
          })}
        </div>
      </SectionCard>
    );
  }
  ```
- [ ] Mount in `SystemStatus` (reads newest row's breakdown):
  ```tsx
  // replace {/* PerPhaseHealthStrip — Task 6 */}
  <PerPhaseHealthStrip latest={diagnostics[0]} />
  ```
  Import: `import { PerPhaseHealthStrip } from './per-phase-health-strip';`
- [ ] Run — expect PASS:
  ```bash
  cd frontend/olympus && npm test -- run-phase-health system-page
  ```
- [ ] Commit:
  ```bash
  git add lib/run-phase-health.ts lib/run-phase-health.test.ts components/system/per-phase-health-strip.tsx components/system/system-page.tsx
  git commit -m "feat(olympus): per-phase health strip from breakdown jsonb on /system"
  ```

---

### Task 7: Zone 2 — "How it works" narrative + persistence table + Pipeline link

**Files:**
- Create `frontend/olympus/components/system/how-it-works.tsx`
- Modify `frontend/olympus/components/system/system-page.tsx` (mount Zone 2)
**Interfaces:**
- Consumes: `buildPipelineHref({ date?, stage?, node? })` (`lib/pipeline-links.ts`); `SectionCard` (`@/components/observability/shared`); `next/link`.
- Produces: `HowItWorks()` (presentational).

This replaces the deleted phase tables + 14-card file-path map + flow strip. Pure presentational — no test cycle, but the JSX is real. The persistence table is the ONE table Pipeline does not cover (what a run writes to the DB). The Pipeline link uses the locked grammar (no stage/node → just `/pipeline`).

- [ ] Create `components/system/how-it-works.tsx`:
  ```tsx
  'use client';

  import Link from 'next/link';
  import { ArrowRight } from 'lucide-react';
  import { SectionCard } from '@/components/observability/shared';
  import { buildPipelineHref } from '@/lib/pipeline-links';

  const PERSISTS: { what: string; where: string; note: string }[] = [
    { what: 'Research segments', where: 'documents', note: 'One row per segment (alt-data, macro, sectors, asset classes)' },
    { what: 'Daily digest', where: 'documents + daily_snapshots', note: 'The read — headline, regime bias, digest markdown' },
    { what: 'Analyst & deliberation notes', where: 'documents', note: 'Per-ticker analyst verdicts and PM⇄analyst debates' },
    { what: 'Portfolio decisions', where: 'positions + decision_log', note: 'The booked book and each signed call with its thesis' },
    { what: 'Run diagnostics', where: 'atlas_run_diagnostics', note: 'Cost, tokens, grounding, per-phase outcomes (this page)' },
  ];

  export function HowItWorks() {
    return (
      <div className="space-y-6">
        <SectionCard title="How it works">
          <p className="max-w-3xl text-sm leading-relaxed text-text-secondary">
            Each run, <span className="text-text-primary">Atlas</span> researches the market across
            parallel phases — alternative data, institutional flows, macro, asset classes, and sectors —
            and synthesizes a daily read. <span className="text-text-primary">Hermes</span> then
            deliberates: it frames theses, screens candidates, runs per-ticker analysts and PM⇄analyst
            debates, and sizes risk. The result is a booked portfolio with a signed decision behind every
            position.
          </p>
          <Link
            href={buildPipelineHref({})}
            className="inline-flex items-center gap-1.5 text-sm text-[var(--accent)] hover:underline"
          >
            See the full graph
            <ArrowRight size={14} />
          </Link>
        </SectionCard>

        <SectionCard
          title="What a run persists"
          subtitle="Every run is durable — these are the tables it writes, the source of truth the dashboard reads."
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-left text-xs text-text-muted">
                  <th className="py-2 pr-4 font-medium">What</th>
                  <th className="py-2 pr-4 font-medium">Where</th>
                  <th className="py-2 font-medium">Notes</th>
                </tr>
              </thead>
              <tbody>
                {PERSISTS.map((r) => (
                  <tr key={r.what} className="border-b border-border-subtle/50">
                    <td className="py-2 pr-4 text-text-primary">{r.what}</td>
                    <td className="py-2 pr-4 font-mono text-xs text-text-secondary">{r.where}</td>
                    <td className="py-2 text-text-muted">{r.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      </div>
    );
  }
  ```
- [ ] Mount Zone 2 in `SystemPage` (after `SystemStatus`), replacing the `{/* Zone 2 … */}` comment:
  ```tsx
  <HowItWorks />
  ```
  Import: `import { HowItWorks } from './how-it-works';`
- [ ] Verify compile + tests:
  ```bash
  cd frontend/olympus && npx tsc --noEmit && npm test -- system-page
  ```
  Expected: PASS.
- [ ] Commit:
  ```bash
  git add components/system/how-it-works.tsx components/system/system-page.tsx
  git commit -m "feat(olympus): de-duplicated How-it-works prose + persistence table on /system"
  ```

---

### Task 8: Zone 2 — Operator-controls disclosure (F8)

**Files:**
- Create `frontend/olympus/components/system/operator-controls.tsx`
- Modify `frontend/olympus/components/system/how-it-works.tsx` (mount the disclosure)
**Interfaces:**
- Consumes: nothing external (native `<details>`); `lucide-react` `ChevronDown`/`Terminal` (already in repo).
- Produces: `OperatorControls()` (presentational, collapsed by default).

Engine internals — model routing as prose, run cadence flags — live behind ONE collapsed disclosure for self-hosters (F8). Never hero content. Use native `<details>` (zero JS, static-export-safe, keyboard-accessible).

- [ ] Create `components/system/operator-controls.tsx`. The CLI cadence note and model-routing prose come from the deleted `/architecture` content (cadence tiers + model list), re-voiced and demoted:
  ```tsx
  'use client';

  import { ChevronDown, Terminal } from 'lucide-react';

  const FLAGS: { flag: string; desc: string }[] = [
    { flag: '--baseline', desc: 'Full pipeline — every research phase regenerated from scratch' },
    { flag: '--delta', desc: 'Lightweight refresh — only changed segments re-run (~20–30% of baseline cost)' },
    { flag: '--monthly', desc: 'Month-end synthesis across the period’s baselines and deltas' },
  ];

  export function OperatorControls() {
    return (
      <details className="glass-card group p-0">
        <summary className="flex cursor-pointer list-none items-center gap-2 p-4 text-sm text-text-secondary">
          <Terminal size={14} className="text-text-muted" />
          <span className="font-medium text-text-primary">Operator controls</span>
          <span className="text-text-muted">— for self-hosters running the pipeline</span>
          <ChevronDown size={14} className="ml-auto transition-transform group-open:rotate-180" aria-hidden />
        </summary>
        <div className="space-y-4 border-t border-border-subtle p-4 text-sm">
          <p className="text-text-muted">
            Runs are invoked from the command line. Model routing is automatic — chat phases use the
            configured reasoning model, web-search phases route to a grounding model.
          </p>
          <ul className="space-y-1.5">
            {FLAGS.map((f) => (
              <li key={f.flag} className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
                <code className="shrink-0 font-mono text-xs text-[var(--accent)]">{f.flag}</code>
                <span className="text-text-muted">{f.desc}</span>
              </li>
            ))}
          </ul>
        </div>
      </details>
    );
  }
  ```
- [ ] Mount in `how-it-works.tsx` at the end of the returned `<div className="space-y-6">`:
  ```tsx
  <OperatorControls />
  ```
  Import: `import { OperatorControls } from './operator-controls';`
- [ ] Verify:
  ```bash
  cd frontend/olympus && npx tsc --noEmit && npm run lint
  ```
  Expected: PASS.
- [ ] Commit:
  ```bash
  git add components/system/operator-controls.tsx components/system/how-it-works.tsx
  git commit -m "feat(olympus): tuck CLI flags behind Operator-controls disclosure (F8)"
  ```

---

### Task 9: Relocate Attribution → Performance and Position-risk → Holdings; fix stale RunHealthTab copy; retire `atlas_run_health` read

**Files:**
- Modify `frontend/olympus/app/observability/page.tsx` (drop Attribution + Position-risk tabs)
- Modify `frontend/olympus/lib/observability-queries.ts` (drop the `atlas_run_health` view read + attribution/positions reads now owned elsewhere; keep `decision_log`)
- Delete `frontend/olympus/components/observability/RunHealthTab.tsx` (replaced by Zone-1 timeline + strip on `/system`)
- Test `frontend/olympus/components/observability/AttributionTab.test.tsx` stays in place (Attribution lands on Performance in Phase 3, which owns its tests) — **do not delete the component or its test**; only unmount it from the observability route.
**Interfaces:**
- Consumes: `ObservabilityData` (trimmed); `DecisionScorecardTab` (unchanged).
- Produces: a trimmed `fetchObservabilityData()` (no `runHealth`, no `runHealthAvailable`).

**Spec mandate:** "move Attribution → Performance and Position-risk → Holdings (System keeps only engine internals)". Performance (Phase 3) and Holdings (Phase 1) own the relocated tabs and their tests; this task **removes them from the observability route only** and stops reading the stripping `atlas_run_health` view. The stale/false "migration 041 pending / requires owner sign-off" copy lived in `RunHealthTab`'s `available===false` branch — deleting the component removes it (the spec's "fix the stale RunHealthTab empty-state copy" — fixed by replacement on `/system`).

> **Relocation handoff (cross-surface — note for the orchestrator):** the **Position-risk diagnostics** belong on Holdings (Phase 1 — `AllocationsPositionsTable`/`PositionDrilldown`) and **Attribution** on Performance (Phase 3 tear sheet). This task leaves `AttributionTab.tsx` and `PositionRiskTab.tsx` on disk so those surfaces can import/relocate them; it only unmounts them from `/observability`. Do **not** delete those two components here.

- [ ] Update the failing expectation first — the observability page test (if present) asserts four tabs. Check and update:
  ```bash
  cd frontend/olympus && ls app/observability/*.test.* components/observability/*.test.* 2>/dev/null
  ```
  If an observability page test asserts the Attribution/Position-risk tabs, update it to assert only `Decision Scorecard` remains; run it to confirm it FAILS against current code first, then passes after the edit below. (`AttributionTab.test.tsx` is a component test and stays green — it tests the component in isolation, not the route.)
- [ ] In `app/observability/page.tsx`, reduce `TABS` to the Scorecard only and drop the unused tab branches + imports:
  ```tsx
  import { Target } from 'lucide-react';
  import AtlasLoader from '@/components/AtlasLoader';
  import { SUBPAGE_MAX, SubpageStickyTabBar, subpageTabButtonClass } from '@/components/subpage-tab-bar';
  import DecisionScorecardTab from '@/components/observability/DecisionScorecardTab';
  import { EmptyState } from '@/components/observability/shared';
  import { fetchObservabilityData, type ObservabilityData } from '@/lib/observability-queries';

  type ObservabilityTab = 'scorecard';

  const TABS: { id: ObservabilityTab; label: string; icon: typeof Target }[] = [
    { id: 'scorecard', label: 'Decision Scorecard', icon: Target },
  ];
  ```
  And in the body, render only the scorecard branch (remove the `attribution`/`risk`/`health` branches):
  ```tsx
  {activeTab === 'scorecard' && <DecisionScorecardTab decisions={data.decisions} />}
  ```
  Update the page subtitle to drop the attribution/risk/health promise:
  ```tsx
  <p className="text-sm text-text-muted">
    Does the agent make money, and is it well-calibrated? The decision track record — every signed
    call and its realized alpha.
  </p>
  ```
- [ ] In `lib/observability-queries.ts`, trim `ObservabilityData` and `fetchObservabilityData` so they no longer read the stripping `atlas_run_health` view (System reads `atlas_run_diagnostics` directly now) and no longer fetch attribution/positions (owned by Performance/Holdings). Keep the `decision_log` read and the `safeSelect` helper. New shape:
  ```ts
  export interface ObservabilityData {
    decisions: TableRow<'decision_log'>[];
  }
  ```
  ```ts
  export async function fetchObservabilityData(): Promise<ObservabilityData> {
    if (!isSupabaseConfigured() || !supabase) {
      throw new Error(
        'Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY). ' +
          'Observability data cannot be loaded.'
      );
    }
    const decisionsRes = await safeSelect<TableRow<'decision_log'>>('decision_log', (sb) =>
      sb
        .from('decision_log')
        .select(
          'id,run_id,run_date,ticker,stance,conviction,thesis,benchmark,holding_days,status,actual_return,alpha,reflection,resolved_at,created_at'
        )
        .order('run_date', { ascending: false })
        .limit(DECISION_LIMIT)
    );
    return { decisions: decisionsRes.rows };
  }
  ```
  Remove the now-unused `RUN_HEALTH_LIMIT`, `ATTRIBUTION_LIMIT`, `POSITIONS_LIMIT` constants, the `latestDateRows` helper, and the `ViewRow` import. Update the file's header comment to drop the `atlas_run_health` / migration-041 reference (it described the stripping view this surface no longer reads).
- [ ] Delete the dead component (its stale "migration 041 pending" copy goes with it):
  ```bash
  cd frontend/olympus && git rm components/observability/RunHealthTab.tsx
  ```
- [ ] Verify nothing else imports the removed surface:
  ```bash
  cd frontend/olympus && grep -rn "RunHealthTab\|runHealth\|atlas_run_health\|attributionDate\|positionsDate" app/ components/ lib/ | grep -v node_modules
  ```
  Expected: only the **`/system`** components (none reference these names) and `lib/database.types.ts`'s `atlas_run_health` view type (leave the type; it is harmless and Phase 0 owns `database.types.ts`). If `app/page.tsx`/`command-palette.tsx` referenced `fetchObservabilityData`'s dropped fields, fix those call sites here.
- [ ] Run the full suite — expect PASS (AttributionTab.test.tsx still green; observability page test updated):
  ```bash
  cd frontend/olympus && npm test && npx tsc --noEmit
  ```
- [ ] Commit:
  ```bash
  git add app/observability/page.tsx lib/observability-queries.ts
  git commit -m "refactor(olympus): drop relocated Attribution/Position-risk + stale run-health view from observability route"
  ```

---

### Task 10: Final verification + backend issue notes

**Files:** none (verification + documentation).
**Interfaces:** none.

- [ ] Full green run from `frontend/olympus`:
  ```bash
  cd frontend/olympus && npm test && npm run lint && npx tsc --noEmit && npm run build
  ```
  Expected: tests PASS, lint clean, types clean, static export builds (`/system` and `/architecture` both emit; `/architecture` is the redirect shell).
- [ ] Confirm F5 token hygiene on the new surface — no off-palette literals introduced:
  ```bash
  cd frontend/olympus && grep -rn "fin-blue\|fin-purple\|rgba(59,130,246)\|#a78bfa\|border-\${" components/system/ app/system/
  ```
  Expected: **no matches** (cyan = `var(--accent)`, fin-green/red/amber used only for status/financial semantics).
- [ ] **Backend issues to file** (the System surface depends on these; reference in the PR body, do not block on them):
  - The Zone-1 run-economics/timeline/strip all assume seeded, well-formed `atlas_run_diagnostics` rows. The spec's program-level **issue #2 `backtest-seed`** (D2) also seeds `nav_history` + resolved `decision_log`; not a hard dependency for System (System renders fully on the live single-day diagnostics), but note it: `Fixes #<backtest-seed>` placeholder.
  - No System-specific new backend issue is required — the `atlas_run_diagnostics` base table and `breakdown` jsonb already exist and carry every field this surface reads (verified live: cost, tokens, `breakdown.cached_tokens`, `breakdown.by_kind.chat.cached_tokens`, `phaseN_output(s)`, `errors[]`).
- [ ] PR body must include the issue linkage (`task/<N>-slug` branch or `Fixes #N`) per repo convention, and note the relocation handoff: "Attribution component preserved for Performance (Phase 3); Position-risk component preserved for Holdings (Phase 1); both unmounted from /observability here."
