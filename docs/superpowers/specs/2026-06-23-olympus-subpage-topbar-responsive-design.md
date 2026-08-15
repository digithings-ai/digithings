# Olympus subpage top-bar — full-bleed + mobile menu (design)

- **Date:** 2026-06-23
- **Status:** Approved design / spec (pre-implementation)
- **Surface:** Olympus shared subpage tab-bar (`frontend/olympus/components/subpage-tab-bar.tsx`)
- **Relationship:** This is **Part B** of the twelve-x Today work. Part A (the Today snapshot redesign, PR #1002) is separate and already open. Part B is its own branch (`feat/olympus-subpage-topbar-responsive`) off `develop` and its own PR.

## 1. Goal

Fix two responsiveness defects in the shared subpage top-bar so it behaves consistently with the rest of Olympus:

1. **Wide screens (> 1600px):** the bar's glass background and bottom border are capped at 1600px and centered, so on wide monitors the divider floats with empty gutters and reads as unfinished. The bar's *chrome* should span the full viewport while its *content* stays aligned to the 1600px page-content width.
2. **Narrow / mobile screens:** the tab items use `flex flex-wrap` and wrap onto multiple lines. They should instead **collapse into a menu button** (a "☰ Sections" dropdown), consistent with the app's existing mobile-nav idiom.

## 2. Context (what exists today)

`components/subpage-tab-bar.tsx` is the single shared component, used by all subpages via `children`:

- `app/observability/page.tsx`, `app/research/ResearchClient.tsx`, `components/portfolio/PortfolioSectionNav.tsx`, `components/twelve-x/TwelveXClient.tsx`.
- The bar is rendered as a **sibling** of the capped content `<div className={SUBPAGE_MAX}>`, and applies `SUBPAGE_MAX` to *itself*. Its parent is the full-width main scroll container — so a full-width outer wrapper needs no negative-margin hack.
- Tab children are heterogeneous: `<Link>` (research/observability/portfolio navigate by route) and stateful `<button>` (twelve-x calls `setTab`, changing `?tab=` not the pathname).
- Current markup (lines 28–34):
  ```tsx
  <div className={`sticky z-20 shrink-0 border-b border-border-subtle bg-bg-glass/95 backdrop-blur-md ${topClass} ${SUBPAGE_MAX} py-3`} role="navigation" aria-label={ariaLabel}>
    <div className="flex flex-wrap gap-2">{children}</div>
  </div>
  ```
- `SUBPAGE_MAX = 'max-w-[1600px] mx-auto w-full px-4 md:px-6'` is consumed by other components too — its value **does not change**.
- An established mobile-nav idiom exists in `components/mobile-app-bar.tsx` + `components/sidebar.tsx` + `components/app-shell-context.tsx`: lucide `Menu`/`X`, `aria-expanded`/`aria-controls`, a `md:hidden` backdrop (`fixed inset-0 … onClick=close`), and close-on-route-change. Part B **reuses the idiom** but keeps its own local state (it does not touch `app-shell-context`).
- Tailwind v4, stock breakpoints (`md` = 768px). `MobileAppBar` is `md:hidden` (present < 768px) and 72px tall — the bar's existing `max-md:top-[72px]` offset already accounts for it. The mobile menu therefore collapses at the **`md`** breakpoint, matching where the main mobile nav appears.

## 3. Approach

**Self-contained refactor of `subpage-tab-bar.tsx` only. Zero callsite changes.** (Rejected alternatives: hoisting toggle state into `app-shell-context` — global state for a per-page dropdown is overkill; a data-driven `tabs` prop rewrite — would force converting all four callsites incl. twelve-x's stateful tabs, and the chosen static "Sections" trigger needs no tab data. YAGNI.)

## 4. Design

### 4.1 Full-bleed chrome, capped content

Split the single sticky div into outer (full width) + inner (capped):

- **Outer** `<div role="navigation" aria-label=…>`: `sticky z-20 shrink-0 border-b border-border-subtle bg-bg-glass/95 backdrop-blur-md` + `topClass`. **No `max-w`.** Spans the full-width parent → background + border reach the viewport edges.
- **Inner** `<div>`: `SUBPAGE_MAX` + `relative py-3`. Holds the trigger + tabs. `relative` anchors the absolute mobile dropdown.

`SUBPAGE_MAX` and its other consumers are untouched.

### 4.2 Mobile menu (`< md`)

Inside the inner container, tabs render **once** in a container whose layout is driven by breakpoint + open state; a trigger button toggles it below `md`.

- **Trigger button** (`md:hidden`): `☰` + label (lucide `Menu` when closed, `X` when open), `aria-expanded={open}`, `aria-controls="subpage-tabs"`, `aria-label` toggling "Open/Close sections menu". Styled to match `mobile-app-bar.tsx`'s toggle (`rounded-lg border border-border-subtle … hover:bg-white/[0.06]`).
- **Tabs container** (`id="subpage-tabs"`): one element, classes from a pure helper `subpageTabsContainerClass(open)`. Strategy: **desktop layout is the unprefixed base; the mobile dropdown panel is expressed entirely with `max-md:` so it auto-stops at `md` and needs no `md:` reset.**
  - Visibility: `${open ? 'flex' : 'hidden'}` (base) + `md:flex` — at `≥ md` the tabs always show regardless of `open`; below `md` they show only when open.
  - Desktop layout (base): `flex-row flex-wrap gap-2`.
  - Mobile panel (`max-md:` only): `flex-col absolute left-0 right-0 top-full mt-1 rounded-lg border border-border-subtle bg-bg-glass/95 backdrop-blur-md p-2 shadow-lg z-30`. Because these are `max-md:`-gated, they vanish at `≥ md` automatically — no `md:bg-transparent`/`md:static`/etc. needed.
- **Children** render unchanged inside that container (works for `<Link>` and `<button>` alike), stacked vertically in the panel, inline at `≥ md`. `subpageTabButtonClass` is unchanged (`sm:` sizing preserved).
- **Close on:** tab click (panel `onClick={() => setOpen(false)}` — covers stateful buttons), route change (`usePathname()` effect — covers `<Link>`), `Escape` keydown (listener active only while open), and a `md:hidden` backdrop tap (`fixed inset-0 z-[19]`, the `sidebar.tsx` idiom).
- New optional prop `menuLabel?: string`, default `"Sections"`. No callsite passes it.
- `≥ md`: trigger hidden, backdrop never shown, tabs inline — visually identical to today.

### 4.3 State & accessibility

- Local `const [open, setOpen] = useState(false)` — no global context.
- `'use client'` already present; add `useState`, `useEffect`, `usePathname` (next/navigation), lucide `Menu`/`X` imports.
- Trigger ↔ panel wired via `aria-expanded` + `aria-controls`/`id`; `Escape` and backdrop give keyboard + pointer dismissal.

## 5. Components / files

- **Modify:** `components/subpage-tab-bar.tsx` — split outer/inner, add trigger + dropdown + state, export new pure helper `subpageTabsContainerClass(open: boolean): string`.
- **Create:** `components/subpage-tab-bar.test.tsx` — unit tests (see §6).
- **No other files change.** All four callsites are untouched.

## 6. Testing

Matches the repo's vitest `node` environment + `renderToStaticMarkup` pattern (e.g. `components/overview/as-of-badge.test.tsx`); no jsdom/RTL.

- **Pure helper `subpageTabsContainerClass(open)`:** `open === true` → contains `flex` and not the closed `hidden`; `open === false` → contains `hidden`; both contain `md:flex` (always visible at `≥ md` regardless of `open`).
- **`renderToStaticMarkup(<SubpageStickyTabBar>{tabs}</…>)`** (initial closed state):
  - children render (tab labels present);
  - a trigger button with `aria-expanded="false"` and `md:hidden`;
  - **outer** wrapper has `border-b` but **not** `max-w-[1600px]`;
  - an **inner** wrapper **has** `max-w-[1600px]`;
  - tabs container carries the closed (`hidden`) + `md:flex` classes.
- **Interactive behavior** (click-open, tab-click/Esc/backdrop/route close) is **render-verified** on the dev server at wide (~2000px), desktop (~1280px), and mobile (~390px) widths — `renderToStaticMarkup` cannot exercise effects/clicks.
- Gate: `next build` green, twelve-x + shell `tsc`/`eslint` clean, full vitest suite green (new + existing component tests).

## 7. Non-goals

- No change to `SUBPAGE_MAX`'s value or to page-content max width.
- No data-driven `tabs` prop; no active-section label in the trigger (the chosen design uses a static "Sections" trigger).
- No change to the main sidebar / `MobileAppBar` / `app-shell-context`.
- Part A (Today snapshot) is out of scope here.

## 8. Risks

- **Sticky + full-bleed outer:** the outer keeps `sticky` + `topClass`; only `max-w` moves to the inner. Verify stickiness and the `max-md:top-[72px]` offset still hold under the `MobileAppBar`.
- **Dropdown overlay z-index:** panel `z-30` and backdrop `z-[19]` must sit above page content but below the main mobile drawer (`z-[999]`) and `MobileAppBar` (`z-[997]`) — confirmed lower, so the main nav still wins.
- **Tailwind class precedence:** the closed-state `hidden` must be overridden by `md:flex`; ordering verified by the pure-helper test + render check.
