---
# Settings Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (- [ ]) syntax.
**Goal:** Turn the Settings stub (Docs link + theme toggle + decorative ⌘K) into a compact single-owner CONTROL + STATUS panel — a canonical data-freshness Status block (F7 `AsOfBadge`), the unchanged Appearance tri-toggle, an About/System card (version + friendly host + fixed Docs link), and a real palette-opening affordance — in two presentations (tight popover, fuller page) from one shared component.
**Architecture:** `SettingsContent` becomes a **pure presentational** component taking freshness/version/host/palette props (so the existing `renderToStaticMarkup` test stays provider-free), wrapped by the two existing callers that own the context reads. The popover (`SidebarSettings`) and full page (`app/settings/page.tsx`) both read `useDashboard()` (freshness) + `useAppShell()` (palette open) and pass props down, sharing a `variant` so the page can breathe wider while the popover stays tight.
**Tech Stack:** Next.js 16 static export (`output:export`, `basePath /olympus`), React 19, Tailwind v4 `@theme` tokens, lucide-react, vitest (`renderToStaticMarkup`), `@supabase/supabase-js` via the shared dashboard context.

## Global Constraints
- **Static export.** `output:export`, `basePath /olympus`. No server components, no runtime env reads beyond `process.env.NEXT_PUBLIC_*` (inlined at build). No new routes — Settings already owns `/settings`.
- **Tailwind v4 tokens only.** Dark-first; cyan-phosphor `--accent` `#3DD6C4`; `--font-display` Instrument Serif; Geist sans/mono; `glass-card`, `bg-bg-primary/secondary/glass`, `border-border-subtle`, `text-text-primary/secondary/muted`, semantic `text-fin-green/red/amber`.
- **F5 token rule (verbatim):** cyan `--accent` `#3DD6C4` for links/chrome/the single conviction encoding/the live-fresh dot only; `fin-green`/`fin-red` *strictly* for signed financial values; `fin-amber` for caution/stale/carried/mixed-regime; **no gradients** beyond the existing faint regime wash; **no decorative numbering** unless it encodes the system's own priority. Settings has **no financial values** → fin-green/red must not appear here; stale = `fin-amber` only. **Purge the `fin-blue` literals** currently in `settings-content.tsx` (the active Docs link `border-fin-blue/40 bg-fin-blue/10 text-fin-blue` and the three theme buttons `bg-fin-blue/20 text-fin-blue`) — re-tokenize to cyan `--accent`.
- **Empty-state discipline.** Status card with no run renders the calm element-specific line **"No pipeline runs yet"** — never an em-dash, never a fabricated date. No time-series elements live on Settings, so no `≥2 points` gates apply here.
- **Keep tests green.** 150+ plumbing + page tests must stay green; `settings-content.test.tsx` is updated as part of this work. Run `npx vitest run` from `frontend/olympus`. Follow existing eslint/prettier conventions (ruff is Python-only).
- **F8 PM-voice copy.** Every string an investor/PM reads is product voice; operator detail (the raw host string is fine, but never the anon key) stays minimal. UTC is **explicitly labelled** everywhere a timestamp appears.
- **Phase 0 is a hard dependency.** This plan **consumes** the canonical `components/shared/as-of-badge.tsx` (F7) and the `app-shell-context` palette controls (F2). It does **not** create them and does **not** touch the `/architecture → /system` Docs hotfix (already landed on this branch at `004ac495`; `settings-content.tsx` already links `/system`). Do not re-do the hotfix.
- **Out of scope (do NOT add):** accounts/login, multi-user/roles, notification prefs, API-key management, CSV/JSON export. No auth exists (anon-key + RLS, single-owner self-hosted).
---

## Phase 0 interfaces this plan CONSUMES (do not redefine)

```tsx
// components/shared/as-of-badge.tsx  (F7 canonical; created by Phase 0)
export function AsOfBadge({ date, createdAt, now, staleHours }: {
  date: string | null; createdAt?: string | null; now?: Date; staleHours?: number;  // default 48h
}): JSX.Element | null;
// createdAt present → true-age path (snapshot-staleness.ts isStale/formatAge); else date-only fresh window.
```
```ts
// components/app-shell-context.tsx  (F2; created by Phase 0) — additions on AppShellContextValue:
//   commandPaletteOpen: boolean; openCommandPalette(): void; closeCommandPalette(): void;
export function useAppShell(): AppShellContextValue;  // existing accessor, now exposes the palette controls
```
Already in-repo (verified): `lib/snapshot-staleness.ts` (`isStale`, `formatAge`, `DEFAULT_SNAPSHOT_STALENESS_HOURS=48`); `useDashboard()` in `lib/dashboard-context.tsx` returns `{ data: DashboardData | null, loading, error }`; `DashboardProvider` wraps the whole shell (Settings popover + `/settings` page both render inside it); `components/ui.tsx` `Badge` (`variant: 'default'|'blue'|'green'|'red'|'amber'`); `SUBPAGE_MAX` in `components/subpage-tab-bar.tsx`; `process.env.NEXT_PUBLIC_OLYMPUS_VERSION` (used today at `components/app-frame.tsx:46`, fallback `'v0.1 · dev'`); `process.env.NEXT_PUBLIC_SUPABASE_URL`.

---

## Task 1: Surface the last-run timestamp on `PortfolioMeta` (`last_run_at`)

The Status card needs the **wall-clock UTC timestamp** of the latest run ("Jun 23, 16:13 UTC · 20h ago"), not just the run *date*. `daily_snapshots.created_at` is already selected by `getFullDashboardData` (`lib/queries.ts:461` — `select('id,date,run_type,baseline_date,snapshot,digest_markdown,created_at')`) but dropped before reaching any component: `PortfolioMeta.last_updated` is only `snapshot.date` (a `YYYY-MM-DD` string, set at `lib/queries.ts:1013`). Add `last_run_at` (the `created_at` ISO timestamp) so `AsOfBadge`'s `createdAt` true-age path can fire. This is the only data-layer change Settings needs; Theses/Holdings/System widening is owned by their own plans (F1).

**Files:**
- Modify: `frontend/olympus/lib/types.ts` (`PortfolioMeta`, lines 191–200)
- Modify: `frontend/olympus/lib/queries.ts` (`lastRunAt` helper near meta assembly; meta object at lines ~1010–1015)
- Test: `frontend/olympus/lib/queries.last-run-at.test.ts` (new)

**Interfaces:**
- Consumes: `daily_snapshots.created_at` (`string | null`, already in the `select`); `snapshot: TableRow<'daily_snapshots'>` local in `getFullDashboardData`.
- Produces: `PortfolioMeta.last_run_at: string | null` — ISO datetime of the latest snapshot's `created_at`, consumed by Tasks 4/5. `last_updated` (date) unchanged.

Steps:
- [ ] Add the field to the type. In `lib/types.ts`, inside `interface PortfolioMeta` (after `last_updated`):
  ```ts
  /** Run *date* (YYYY-MM-DD) of the latest daily_snapshots row driving this dashboard. */
  last_updated: string | null;
  /** Wall-clock UTC timestamp (daily_snapshots.created_at) of that run — for true-age freshness. */
  last_run_at: string | null;
  ```
- [ ] Add an exported pure helper to `lib/queries.ts` near the meta assembly (so it is unit-testable without the Supabase round-trip):
  ```ts
  /** The latest run's wall-clock timestamp for freshness readouts (daily_snapshots.created_at). */
  export function lastRunAt(snapshot: Pick<TableRow<'daily_snapshots'>, 'created_at'>): string | null {
    return snapshot.created_at ?? null;
  }
  ```
- [ ] Write the failing test `lib/queries.last-run-at.test.ts`:
  ```ts
  import { describe, expect, it } from 'vitest';
  import { lastRunAt } from './queries';

  describe('lastRunAt', () => {
    it('lifts created_at off the snapshot row', () => {
      expect(lastRunAt({ created_at: '2026-06-23T16:13:04Z' })).toBe('2026-06-23T16:13:04Z');
    });
    it('returns null when the run has no created_at', () => {
      expect(lastRunAt({ created_at: null })).toBeNull();
    });
  });
  ```
- [ ] Run `npx vitest run lib/queries.last-run-at.test.ts` (from `frontend/olympus`). Expect FAIL if the helper isn't added yet, PASS once it is — sequence so you see one real red (e.g. assert the wrong value first, or add the test before the helper).
- [ ] Wire the helper into the returned meta in `getFullDashboardData` (`lib/queries.ts` ~line 1013), right after `last_updated`:
  ```ts
        last_updated: snapshot.date ?? latestPosDate,
        last_run_at: lastRunAt(snapshot),
        benchmarks: Object.keys(benchmarks),
  ```
- [ ] Run `npx vitest run lib/queries.last-run-at.test.ts` — expect PASS. Then `npx tsc --noEmit` — clean (every `PortfolioMeta` construction site now needs `last_run_at`; the only site is this one).
- [ ] `git add -A && git commit -m "feat(olympus): surface last_run_at on PortfolioMeta for Settings freshness"` (Fixes #<frontend redesign umbrella issue — no NEW backend issue: created_at already exists; reference the umbrella tracking issue, not a Closes>).

---

## Task 2: Make `SettingsContent` a pure presentational component (props in)

`SettingsContent` is rendered in two live places (popover `sidebar-settings.tsx`, page `app/settings/page.tsx`) and in the test via `renderToStaticMarkup` with **no provider** (`settings-content.test.tsx` mocks only `next/navigation` + `theme-provider`). To add freshness (needs `useDashboard`) and a palette opener (needs `useAppShell`) without forcing the test to mock two more contexts — and to keep the component a clean unit — push all data in via props and let the two callers own the context reads.

**Files:**
- Modify: `frontend/olympus/components/settings-content.tsx`
- Test: `frontend/olympus/components/settings-content.test.tsx` (update to the props API)

**Interfaces:**
- Consumes: nothing new yet (Task 3 fills the cards).
- Produces:
  ```tsx
  export interface SettingsContentProps {
    /** Tighter spacing for the sidebar popover; slightly fuller for the page. */
    variant?: 'popover' | 'page';
    /** Latest run date (YYYY-MM-DD) and wall-clock UTC timestamp — for the Status card. */
    lastRunDate: string | null;
    lastRunAt: string | null;
    /** Latest run type (baseline | delta) for the Status sub-line; null when unknown. */
    runType: 'baseline' | 'delta' | null;
    /** Build label and friendly data-source host for the About card. */
    version: string;
    dataSourceHost: string | null;
    /** Open the command palette (About card affordance). null disables it (e.g. SSR/test). */
    onOpenPalette?: (() => void) | null;
    onNavigate?: () => void;
  }
  export function SettingsContent(props: SettingsContentProps): JSX.Element;
  ```

Steps:
- [ ] Update the test FIRST to the new props shape (the failing red). Replace the `render()` helper in `settings-content.test.tsx`:
  ```ts
  function render(overrides: Partial<Parameters<typeof SettingsContent>[0]> = {}): string {
    return renderToStaticMarkup(
      createElement(SettingsContent, {
        lastRunDate: '2026-06-23',
        lastRunAt: '2026-06-23T16:13:04Z',
        runType: 'baseline',
        version: 'v0.4.0',
        dataSourceHost: 'abcdefgh.supabase.co',
        ...overrides,
      })
    );
  }
  ```
  Keep the two existing assertions (`All settings` hidden on `/settings/`; theme `aria-pressed`). Add:
  ```ts
  it('shows the build version and friendly data-source host in About', () => {
    const html = render();
    expect(html).toContain('v0.4.0');
    expect(html).toContain('abcdefgh.supabase.co');
  });

  it('renders the empty-state line when no run is recorded', () => {
    const html = render({ lastRunDate: null, lastRunAt: null, runType: null });
    expect(html).toContain('No pipeline runs yet');
  });

  it('links Docs to /system, never /architecture', () => {
    const html = render();
    expect(html).toContain('href="/system"');
    expect(html).not.toContain('/architecture');
  });

  it('uses no off-palette fin-blue literals', () => {
    expect(render()).not.toContain('fin-blue');
  });
  ```
- [ ] Run `npx vitest run components/settings-content.test.tsx` — expect FAIL (props API not implemented; `fin-blue` still present; no About/Status copy).
- [ ] Rewrite the top of `settings-content.tsx`. Replace the import block:
  ```tsx
  'use client';

  import Link from 'next/link';
  import { usePathname } from 'next/navigation';
  import { Database, Search } from 'lucide-react';
  import { useAtlasTheme } from '@/components/theme-provider';
  import { AsOfBadge } from '@/components/shared/as-of-badge';
  import { normalizePathname } from '@/lib/pathname';
  ```
  (Drop `Keyboard`; add `Search` for the palette affordance and `AsOfBadge` for Status.) Declare `SettingsContentProps` (from the Interfaces block) above the component, then change the signature:
  ```tsx
  export function SettingsContent({
    variant = 'popover',
    lastRunDate,
    lastRunAt,
    runType,
    version,
    dataSourceHost,
    onOpenPalette,
    onNavigate,
  }: SettingsContentProps) {
    const pathname = usePathname();
    const { theme, setTheme } = useAtlasTheme();
    const sys = systemActive(pathname);
    const settings = settingsActive(pathname);
  ```
  (`usePathname`/`useAtlasTheme` stay inside — both already mocked by the test; `variant` is consumed for spacing in Task 5.)
- [ ] Re-tokenize the existing Docs link + theme buttons cyan (F5), so the `fin-blue` assertion can pass once the structure is in place: active Docs `border-fin-blue/40 bg-fin-blue/10 text-fin-blue` → `border-accent/40 bg-accent/10 text-accent`; each theme button `bg-fin-blue/20 text-fin-blue` → `bg-accent/20 text-accent`. Leave inactive states untouched.
- [ ] Run `npx vitest run components/settings-content.test.tsx` — still FAIL on Status/About copy (cards land in Task 3); `fin-blue` + Docs-href assertions now pass. This intermediate red is expected; the commit happens at the end of Task 3 when the file compiles with all props consumed.

---

## Task 3: Status / data-freshness card + About / System card (the marquee)

The two new cards. **Status** is the canonical "is this current / which build" audit block: `AsOfBadge` on the run date + true-age, an explicit UTC line, and the **"No pipeline runs yet"** empty state. **About** carries the build version, a friendly host label (never the anon key), the fixed `/system` Docs link (folded in from the old standalone Docs section), and the real ⌘K affordance replacing the decorative row.

**Files:**
- Modify: `frontend/olympus/components/settings-content.tsx` (card bodies + `formatRunStamp` helper)
- Test: `frontend/olympus/components/settings-content.test.tsx` (Task 2 assertions go green)

**Interfaces:**
- Consumes: `AsOfBadge({ date, createdAt })` (F7); `isStale`/`formatAge` indirectly via `AsOfBadge`; `SettingsContentProps` (Task 2).
- Produces: rendered Status + About cards consumed by both presentations.

Steps:
- [ ] **Status card** — insert as the FIRST section inside the returned wrapper `<div>`, above Appearance. UTC explicitly labelled; empty state calm:
  ```tsx
  <div>
    <p className="text-[10px] font-medium text-text-muted mb-2">Status</p>
    {lastRunDate ? (
      <div className="rounded-lg border border-border-subtle bg-bg-secondary/50 px-3 py-2.5 space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-text-secondary">Last run</span>
          <AsOfBadge date={lastRunDate} createdAt={lastRunAt} />
        </div>
        <p className="font-mono text-[11px] text-text-muted">
          {formatRunStamp(lastRunDate, lastRunAt)} UTC
          {runType ? <span className="text-text-secondary"> · {runType}</span> : null}
        </p>
      </div>
    ) : (
      <div className="rounded-lg border border-border-subtle bg-bg-secondary/50 px-3 py-2.5">
        <p className="text-xs text-text-muted">No pipeline runs yet</p>
      </div>
    )}
  </div>
  ```
- [ ] Add the `formatRunStamp` pure helper at the bottom of `settings-content.tsx`, alongside the existing `systemActive`/`settingsActive`. UTC getters keep it deterministic regardless of viewer locale (matches the spec's "UTC everywhere, explicitly labelled"):
  ```tsx
  /** "2026-06-23" + "2026-06-23T16:13:04Z" → "Jun 23, 16:13". Date-only when no timestamp. */
  function formatRunStamp(date: string, createdAt: string | null): string {
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const dm = date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    const day = dm ? `${months[Number(dm[2]) - 1] ?? dm[2]} ${Number(dm[3])}` : date;
    if (!createdAt) return day;
    const ts = Date.parse(createdAt);
    if (Number.isNaN(ts)) return day;
    const d = new Date(ts);
    const hh = String(d.getUTCHours()).padStart(2, '0');
    const mm = String(d.getUTCMinutes()).padStart(2, '0');
    return `${day}, ${hh}:${mm}`;
  }
  ```
- [ ] **About / System card** — DELETE the old standalone `Docs` section (`<div><p>…Docs…</p>…</div>` wrapping the `/system` link + `All settings` link) AND the decorative `Shortcuts` section (`<div><p>…Shortcuts…</p>…</div>` with the bare `⌘K` `<kbd>`), and add this as the LAST section:
  ```tsx
  <div>
    <p className="text-[10px] font-medium text-text-muted mb-2">About</p>
    <div className="rounded-lg border border-border-subtle bg-bg-secondary/50 divide-y divide-border-subtle">
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <span className="text-xs text-text-secondary">Build</span>
        <span className="font-mono text-[11px] text-text-muted">{version}</span>
      </div>
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <span className="text-xs text-text-secondary">Data source</span>
        <span className="font-mono text-[11px] text-text-muted truncate max-w-[55%]" title={dataSourceHost ?? undefined}>
          {dataSourceHost ?? 'not configured'}
        </span>
      </div>
      {onOpenPalette ? (
        <button
          type="button"
          onClick={() => { onOpenPalette(); onNavigate?.(); }}
          className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-text-secondary hover:bg-white/[0.04] hover:text-text-primary transition-colors"
        >
          <Search size={14} className="shrink-0 text-text-muted" aria-hidden />
          <span>Search</span>
          <kbd className="ml-auto font-mono px-1.5 py-0.5 rounded border border-border-subtle bg-bg-primary text-text-primary">⌘K</kbd>
        </button>
      ) : null}
      <Link
        href="/system"
        onClick={onNavigate}
        className={`flex items-center gap-2 px-3 py-2 text-xs font-medium transition-colors ${
          sys ? 'text-accent' : 'text-text-secondary hover:bg-white/[0.04] hover:text-text-primary'
        }`}
      >
        <Database size={14} className="shrink-0" aria-hidden />
        <span>How it works</span>
      </Link>
    </div>
    {!settings ? (
      <Link
        href="/settings"
        onClick={onNavigate}
        className="mt-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-text-secondary border border-border-subtle hover:bg-white/[0.04] hover:text-text-primary transition-colors"
      >
        All settings
      </Link>
    ) : null}
  </div>
  ```
  (The "All settings" link keeps its existing behavior — visible only off `/settings` — so the test's first assertion still holds. Docs now lives in About with the fixed `/system` href and re-tokenized cyan active state. The decorative ⌘K row is gone; the only ⌘K is the live opener.)
- [ ] Run `npx vitest run components/settings-content.test.tsx` — expect PASS (all six assertions). If the empty-state test fails, confirm `lastRunDate: null` selects the `No pipeline runs yet` branch.
- [ ] `npx tsc --noEmit` (from `frontend/olympus`) — clean (all props consumed; `formatRunStamp` typed).
- [ ] `git add -A && git commit -m "refactor(olympus): rebuild Settings as a Status + Appearance + About panel"`.

---

## Task 4: Wire the popover wrapper (`SidebarSettings`) — context → props

`SidebarSettings` already renders `<SettingsContent onNavigate=…/>`. It must now read `useDashboard()` for freshness/host and the Phase 0 palette controls from `useAppShell()`, and pass them down. Popover keeps the tight `variant="popover"`.

**Files:**
- Modify: `frontend/olympus/components/sidebar-settings.tsx`
- Create: `frontend/olympus/lib/data-source-host.ts`

**Interfaces:**
- Consumes: `useDashboard()` → `data.portfolio.meta.{last_updated,last_run_at,latest_snapshot_run_type}` (Task 1); `useAppShell()` → `openCommandPalette` (Phase 0 F2); `process.env.NEXT_PUBLIC_OLYMPUS_VERSION`; `dataSourceHost()` (below).
- Produces: a fully-propped popover render.

Steps:
- [ ] Create the shared host helper `lib/data-source-host.ts` (reused by Task 5):
  ```ts
  /** Friendly host label for the data source — the Supabase URL's hostname, never the anon key. */
  export function dataSourceHost(): string | null {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    if (!url) return null;
    try {
      return new URL(url).host;
    } catch {
      return null;
    }
  }
  ```
- [ ] Add imports to `sidebar-settings.tsx`: `import { useDashboard } from '@/lib/dashboard-context';` and `import { dataSourceHost } from '@/lib/data-source-host';`.
- [ ] Read the data inside the component body — extend the existing `const { setMobileNavOpen } = useAppShell();` line:
  ```tsx
  const { setMobileNavOpen, openCommandPalette } = useAppShell();
  const { data } = useDashboard();
  const meta = data?.portfolio?.meta ?? null;
  ```
- [ ] Pass props into the `SettingsContent` rendered inside the `panel` const:
  ```tsx
  <SettingsContent
    variant="popover"
    lastRunDate={meta?.last_updated ?? null}
    lastRunAt={meta?.last_run_at ?? null}
    runType={meta?.latest_snapshot_run_type ?? null}
    version={process.env.NEXT_PUBLIC_OLYMPUS_VERSION ?? 'v0.1 · dev'}
    dataSourceHost={dataSourceHost()}
    onOpenPalette={() => {
      setOpen(false);
      setMobileNavOpen(false);
      openCommandPalette();
    }}
    onNavigate={() => {
      setOpen(false);
      setMobileNavOpen(false);
    }}
  />
  ```
- [ ] `npx tsc --noEmit` (from `frontend/olympus`) — clean. If `openCommandPalette` is not on `AppShellContextValue`, Phase 0 (F2) has not merged — STOP and rebase on Phase 0 (this plan depends on it).
- [ ] `git add -A && git commit -m "feat(olympus): wire Settings popover to live freshness + command palette"`.

---

## Task 5: Wire the page presentation (`app/settings/page.tsx`) — fuller layout

The page today is the popover stretched to `max-w-md`. Give it the `variant="page"` presentation: a wider card, the same `SettingsContent`, the same context-derived props. `SettingsContent` reads `variant` for spacing density only (popover `space-y-5` / page `space-y-6`) — no structural fork, honoring the slop guard against stamping one composition.

**Files:**
- Modify: `frontend/olympus/app/settings/page.tsx`
- Modify: `frontend/olympus/components/settings-content.tsx` (consume `variant` for spacing only)

**Interfaces:**
- Consumes: same as Task 4 (`useDashboard`, `dataSourceHost`, env version, `useAppShell().openCommandPalette`).
- Produces: the `/settings` page render.

Steps:
- [ ] Consume `variant` in `settings-content.tsx` for spacing density only — change the outer wrapper:
  ```tsx
  <div className={variant === 'page' ? 'space-y-6' : 'space-y-5'}>
  ```
  (The only behavioral use of `variant`; cards are identical so page/popover never drift.)
- [ ] Rewrite `app/settings/page.tsx` to a client component supplying props (it now reads context):
  ```tsx
  'use client';

  import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
  import { SettingsContent } from '@/components/settings-content';
  import { useDashboard } from '@/lib/dashboard-context';
  import { useAppShell } from '@/components/app-shell-context';
  import { dataSourceHost } from '@/lib/data-source-host';

  export default function SettingsPage() {
    const { data } = useDashboard();
    const { openCommandPalette } = useAppShell();
    const meta = data?.portfolio?.meta ?? null;
    return (
      <div className={`${SUBPAGE_MAX} py-6 md:py-8`}>
        <h1 className="text-xl font-semibold text-text-primary mb-6">Settings</h1>
        <div className="glass-card p-6 max-w-lg">
          <SettingsContent
            variant="page"
            lastRunDate={meta?.last_updated ?? null}
            lastRunAt={meta?.last_run_at ?? null}
            runType={meta?.latest_snapshot_run_type ?? null}
            version={process.env.NEXT_PUBLIC_OLYMPUS_VERSION ?? 'v0.1 · dev'}
            dataSourceHost={dataSourceHost()}
            onOpenPalette={openCommandPalette}
          />
        </div>
      </div>
    );
  }
  ```
  (`max-w-md` → `max-w-lg` so the page reads as a fuller panel, not the popover stretched. No `onNavigate` — leaving `/settings` does not need to close a popover.)
- [ ] `npx tsc --noEmit` (from `frontend/olympus`) — clean.
- [ ] `npx vitest run` (from `frontend/olympus`) — full suite PASS (150+ plumbing + page tests stay green; `settings-content.test.tsx` green; `queries.last-run-at.test.ts` green).
- [ ] `npm run build` (from `frontend/olympus`) — `output:export` succeeds and `/olympus/settings` is emitted (confirms the new `'use client'` page builds statically). Run any project lint script per existing conventions.
- [ ] `git add -A && git commit -m "feat(olympus): give /settings a fuller multi-card presentation"`.

---

## Verification (run before claiming done)
- [ ] `npx vitest run` (from `frontend/olympus`) — all green, including the rewritten `settings-content.test.tsx` (six assertions: All-settings hide, theme aria-pressed, version+host, empty-state line, `/system` Docs href + no `/architecture`, no `fin-blue`) and `queries.last-run-at.test.ts`.
- [ ] `npx tsc --noEmit` — clean.
- [ ] `npm run build` — `output:export` succeeds; `/settings` renders.
- [ ] Grep guard: `grep -rn "fin-blue\|/architecture\|text-fin-purple\|Keyboard" frontend/olympus/components/settings-content.tsx` returns nothing (F5 token rule + decorative-⌘K removal + dead Docs href all gone).
- [ ] Visual smoke (if local): popover shows Status (live or "No pipeline runs yet"), Appearance tri-toggle unchanged, About with build + host + ⌘K opening the palette + Docs → `/system`; `/settings` page shows the same cards in a wider layout.
