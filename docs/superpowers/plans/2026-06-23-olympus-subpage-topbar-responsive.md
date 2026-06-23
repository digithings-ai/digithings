# Olympus subpage top-bar responsive — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared Olympus subpage top-bar full-bleed on wide screens and collapse its tabs into a `☰ Sections` menu on mobile, with zero callsite changes.

**Architecture:** Self-contained refactor of `frontend/olympus/components/subpage-tab-bar.tsx`. Split the single sticky div into a full-width outer wrapper (chrome) + a `SUBPAGE_MAX`-capped inner wrapper (content). Add a `md:hidden` menu trigger with local `open` state; tabs render once in a container that is an inline wrapping row at `≥ md` and an absolute dropdown panel below `md`. The mobile-nav idiom (lucide `Menu`/`X`, `aria-expanded`/`aria-controls`, `md:hidden` backdrop, close-on-route-change) is reused but state stays local.

**Tech Stack:** Next.js 16 App Router, React 19 client component, Tailwind v4 (stock breakpoints), lucide-react, Vitest 4 (`node` environment + `react-dom/server` `renderToStaticMarkup`).

## Global Constraints

- `SUBPAGE_MAX` keeps its exact value `'max-w-[1600px] mx-auto w-full px-4 md:px-6'` — do not change it; other components consume it.
- Collapse breakpoint is **`md`** (768px) — matches `MobileAppBar` (`md:hidden`, 72px) and the existing `max-md:top-[72px]` offset.
- New optional prop `menuLabel?: string` defaults to `"Sections"`. **No callsite passes it; no callsite changes at all.**
- Do not touch `app-shell-context.tsx`, `sidebar.tsx`, `mobile-app-bar.tsx`, or any of the four callsites (`app/observability/page.tsx`, `app/research/ResearchClient.tsx`, `components/portfolio/PortfolioSectionNav.tsx`, `components/twelve-x/TwelveXClient.tsx`).
- z-index ordering: dropdown panel `z-30`, trigger button `relative z-30`, backdrop `z-[19]` — all must stay below `MobileAppBar` (`z-[997]`) and the main drawer (`z-[999]`).
- `subpageTabButtonClass` and `SUBPAGE_MAX` exports are unchanged; add a new exported pure helper `subpageTabsContainerClass(open: boolean): string`.
- Tests use the repo's pattern: vitest `node` env, `renderToStaticMarkup`, `vi.mock('next/navigation', ...)` for `usePathname`. No jsdom/RTL.
- ruff/pandas rules are backend-only; this is TS. Keep eslint clean (line length 100).

## File Structure

- `frontend/olympus/components/subpage-tab-bar.tsx` (modify) — the only source file. Exports: `SUBPAGE_MAX` (unchanged), `subpageTabButtonClass` (unchanged), **new** `subpageTabsContainerClass(open)`, `SubpageStickyTabBar` (refactored).
- `frontend/olympus/components/subpage-tab-bar.test.tsx` (create) — helper unit tests + `renderToStaticMarkup` structural tests.

All commands run from `frontend/olympus/` (the Next workspace). `node_modules` is symlinked there as in prior twelve-x work.

---

### Task 1: Pure helper `subpageTabsContainerClass(open)`

**Files:**
- Modify: `frontend/olympus/components/subpage-tab-bar.tsx` (add the exported helper after `subpageTabButtonClass`)
- Test: `frontend/olympus/components/subpage-tab-bar.test.tsx` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `subpageTabsContainerClass(open: boolean): string` — the className for the tabs container. Visibility token is `flex` when `open`, `hidden` when closed; always includes `md:flex` (tabs visible at `≥ md` regardless of `open`); desktop layout (`flex-row flex-wrap`) is unprefixed base; the mobile dropdown panel chrome is entirely `max-md:`-gated.

- [ ] **Step 1: Write the failing tests**

Create `frontend/olympus/components/subpage-tab-bar.test.tsx`:

```tsx
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  usePathname: () => '/olympus/twelve-x',
}));

import { SubpageStickyTabBar, subpageTabsContainerClass } from './subpage-tab-bar';

describe('subpageTabsContainerClass', () => {
  it('is visible (flex, not hidden) when open', () => {
    const cls = subpageTabsContainerClass(true);
    expect(cls).toContain('flex');
    expect(cls).not.toContain('hidden');
  });

  it('is hidden when closed', () => {
    expect(subpageTabsContainerClass(false)).toContain('hidden');
  });

  it('always shows tabs at >= md regardless of open', () => {
    expect(subpageTabsContainerClass(true)).toContain('md:flex');
    expect(subpageTabsContainerClass(false)).toContain('md:flex');
  });

  it('gates the dropdown-panel chrome behind max-md so it stops at md', () => {
    const cls = subpageTabsContainerClass(false);
    expect(cls).toContain('max-md:absolute');
    expect(cls).toContain('max-md:flex-col');
    // panel chrome must not leak to desktop (no unprefixed absolute/border/shadow)
    expect(cls).not.toMatch(/(^| )absolute( |$)/);
  });
});
```

> Note: the `SubpageStickyTabBar` import is used by Task 2's tests added to this same file; importing it now is harmless and keeps one test file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend/olympus && npx vitest run components/subpage-tab-bar.test.tsx`
Expected: FAIL — `subpageTabsContainerClass` is not exported (`SyntaxError`/`undefined is not a function`).

- [ ] **Step 3: Implement the helper**

In `frontend/olympus/components/subpage-tab-bar.tsx`, add after the `subpageTabButtonClass` function (before `SubpageStickyTabBar`):

```tsx
/**
 * Classes for the tabs container. Desktop layout is the unprefixed base; the
 * mobile dropdown panel is expressed entirely with `max-md:` so it auto-stops
 * at the `md` breakpoint and needs no `md:` reset. `md:flex` keeps tabs visible
 * at >= md regardless of `open`; below md they show only when `open`.
 */
export function subpageTabsContainerClass(open: boolean): string {
  return `gap-2 flex-row flex-wrap md:flex ${open ? 'flex' : 'hidden'} max-md:flex-col max-md:absolute max-md:left-0 max-md:right-0 max-md:top-full max-md:mt-1 max-md:rounded-lg max-md:border max-md:border-border-subtle max-md:bg-bg-glass/95 max-md:backdrop-blur-md max-md:p-2 max-md:shadow-lg max-md:z-30`;
}
```

- [ ] **Step 4: Run the helper tests to verify they pass**

Run: `cd frontend/olympus && npx vitest run components/subpage-tab-bar.test.tsx -t subpageTabsContainerClass`
Expected: PASS (4 tests). The `SubpageStickyTabBar` describe block does not exist yet, so only the helper tests run under the `-t` filter.

- [ ] **Step 5: Commit**

```bash
git add frontend/olympus/components/subpage-tab-bar.tsx frontend/olympus/components/subpage-tab-bar.test.tsx
git commit -m "feat(olympus): add subpageTabsContainerClass responsive helper"
```

---

### Task 2: Refactor `SubpageStickyTabBar` (full-bleed + mobile menu)

**Files:**
- Modify: `frontend/olympus/components/subpage-tab-bar.tsx` (rewrite imports + `SubpageStickyTabBar`)
- Test: `frontend/olympus/components/subpage-tab-bar.test.tsx` (append structural tests)

**Interfaces:**
- Consumes: `subpageTabsContainerClass(open)` and `SUBPAGE_MAX` from Task 1 / existing.
- Produces: `SubpageStickyTabBar` with props `{ children, 'aria-label'?, topOffset?: 'app' | 'none', menuLabel?: string }`. Renders a full-width outer `<div role="navigation">` (chrome, no `max-w`) wrapping a `SUBPAGE_MAX relative py-3` inner `<div>` that holds a `md:hidden` trigger button, an optional backdrop, and the tabs container.

- [ ] **Step 1: Write the failing structural tests**

Append to `frontend/olympus/components/subpage-tab-bar.test.tsx`:

```tsx
function renderBar(): string {
  return renderToStaticMarkup(
    createElement(
      SubpageStickyTabBar,
      { 'aria-label': 'Test sections' },
      createElement('a', { href: '/a', key: 'a' }, 'Alpha'),
      createElement('a', { href: '/b', key: 'b' }, 'Bravo'),
    ),
  );
}

describe('SubpageStickyTabBar', () => {
  it('renders its tab children', () => {
    const html = renderBar();
    expect(html).toContain('Alpha');
    expect(html).toContain('Bravo');
  });

  it('renders a collapsed mobile menu trigger', () => {
    const html = renderBar();
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-controls="subpage-tabs"');
    expect(html).toContain('Sections');
  });

  it('outer wrapper is full-bleed: has the border, sticky, but no width cap', () => {
    const html = renderBar();
    const firstClass = html.match(/class="([^"]*)"/)?.[1] ?? '';
    expect(firstClass).toContain('sticky');
    expect(firstClass).toContain('border-b');
    expect(firstClass).not.toContain('max-w-[1600px]');
  });

  it('inner wrapper caps content at 1600px', () => {
    expect(renderBar()).toContain('max-w-[1600px]');
  });

  it('respects a custom menuLabel', () => {
    const html = renderToStaticMarkup(
      createElement(SubpageStickyTabBar, { menuLabel: 'Views' }, createElement('a', { href: '/a' }, 'A')),
    );
    expect(html).toContain('Views');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend/olympus && npx vitest run components/subpage-tab-bar.test.tsx -t SubpageStickyTabBar`
Expected: FAIL — current bar has no trigger (`aria-expanded` absent) and the outer wrapper still carries `max-w-[1600px]`.

- [ ] **Step 3: Rewrite the component**

In `frontend/olympus/components/subpage-tab-bar.tsx`, replace the top-of-file imports and the `SubpageStickyTabBar` function. The file's `'use client'`, `SUBPAGE_MAX`, `subpageTabButtonClass`, and `subpageTabsContainerClass` stay as they are.

Replace the import line:

```tsx
import type { ReactNode } from 'react';
```

with:

```tsx
import { useEffect, useState, type ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { Menu, X } from 'lucide-react';
```

Replace the entire `SubpageStickyTabBar` function with:

```tsx
/** Sticks under the main scroll so in-page tabs stay visible (Portfolio, Research). */
export function SubpageStickyTabBar({
  children,
  'aria-label': ariaLabel = 'Section navigation',
  topOffset = 'app',
  menuLabel = 'Sections',
}: {
  children: ReactNode;
  'aria-label'?: string;
  topOffset?: 'app' | 'none';
  menuLabel?: string;
}) {
  const topClass = topOffset === 'none' ? 'top-0' : 'max-md:top-[72px] md:top-0';
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // Close the mobile menu on route change (covers <Link> tabs).
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Close on Escape while the menu is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <div
      className={`sticky z-20 shrink-0 border-b border-border-subtle bg-bg-glass/95 backdrop-blur-md ${topClass}`}
      role="navigation"
      aria-label={ariaLabel}
    >
      <div className={`${SUBPAGE_MAX} relative py-3`}>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="relative z-30 flex items-center gap-2 rounded-lg border border-border-subtle px-3 py-1.5 text-sm font-medium text-text-primary hover:bg-white/[0.06] md:hidden"
          aria-expanded={open}
          aria-controls="subpage-tabs"
          aria-label={open ? 'Close sections menu' : 'Open sections menu'}
        >
          {open ? <X size={18} strokeWidth={2} /> : <Menu size={18} strokeWidth={2} />}
          <span>{menuLabel}</span>
        </button>
        {open ? (
          <div
            className="fixed inset-0 z-[19] md:hidden"
            onClick={() => setOpen(false)}
            aria-hidden
          />
        ) : null}
        <div id="subpage-tabs" className={subpageTabsContainerClass(open)} onClick={() => setOpen(false)}>
          {children}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the full test file to verify it passes**

Run: `cd frontend/olympus && npx vitest run components/subpage-tab-bar.test.tsx`
Expected: PASS (all helper + structural tests, ~9 tests).

- [ ] **Step 5: Typecheck and lint**

Run: `cd frontend/olympus && npx tsc --noEmit -p tsconfig.json && npx eslint components/subpage-tab-bar.tsx components/subpage-tab-bar.test.tsx`
Expected: tsc reports no NEW errors in these files (a pre-existing `lib/security-headers.test.ts` TS7016/7006 pair is known and unrelated); eslint exits 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/olympus/components/subpage-tab-bar.tsx frontend/olympus/components/subpage-tab-bar.test.tsx
git commit -m "feat(olympus): full-bleed subpage top-bar + mobile menu collapse"
```

---

## Post-implementation verification (controller, not a task)

After both tasks land, the controller verifies the whole branch:

1. `cd frontend/olympus && npx vitest run` — full suite green (new + existing component tests).
2. `cd frontend/olympus && npx next build` — green; `/twelve-x`, `/research`, `/observability`, `/portfolio` prerender without error.
3. Dev-server render verification (browser) at three widths on a subpage with tabs (e.g. `/twelve-x`):
   - **~2000px wide:** the bar's glass background + bottom border reach both viewport edges; tabs centered, aligned to the 1600px content column.
   - **~1280px desktop:** tabs inline exactly as before; no trigger button.
   - **~390px mobile:** only `☰ Sections` shows; tapping opens a dropdown listing the tabs; tapping a tab / outside / `Esc` closes it; the bar still sits below the 72px `MobileAppBar`.
   - Console clean (0 errors).

## Self-Review (writing-plans step)

- **Spec coverage:** §4.1 full-bleed → Task 2 outer/inner split (tested). §4.2 mobile menu → Task 2 trigger + dropdown + close handlers; visibility logic → Task 1 helper (tested). §4.3 state/a11y → Task 2 `useState`/`usePathname`/`Escape`/`aria-*`. §5 files → both tasks. §6 testing → Task 1 helper tests + Task 2 structural tests + controller render verification. §7 non-goals → Global Constraints (no callsite/shell/SUBPAGE_MAX changes). §8 risks → Global Constraints (z-index ordering) + render verification (sticky/offset, class precedence).
- **Placeholder scan:** none — every code step has complete code and exact commands.
- **Type consistency:** `subpageTabsContainerClass(open: boolean): string` is defined in Task 1 and consumed in Task 2 with the same signature; `menuLabel` default `"Sections"` is consistent between the component and the test; `aria-controls="subpage-tabs"` matches the container `id="subpage-tabs"`.
