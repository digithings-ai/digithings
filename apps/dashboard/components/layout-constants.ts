/**
 * Shared structural class strings for the dashboard operator surface.
 *
 * This is the dashboard's `lib/layout.ts` equivalent (see
 * `docs/superpowers/structure/dashboard.md` §0): the repeated page/section
 * grammar lives here once, in token-backed utilities only, so pages assemble
 * from one language instead of re-inventing `font-display text-xl …` per file.
 *
 * No colour, type-scale or spacing decision should be made in a page file; a
 * page names a structural role (`PAGE`, `PAGE_HEADER`, `SECTION`) and this
 * module owns the dress. The refinement pass changes these strings in one place.
 */

/** Shared page width and horizontal padding for dashboard workspaces. */
export const SUBPAGE_MAX = 'max-w-[1600px] mx-auto w-full px-4 md:px-6';

/** The page container: full-height column at the shared width. */
export const PAGE = `flex min-h-full flex-col ${SUBPAGE_MAX}`;

/** The page header band: one eyebrow, one h1, one lede — never two of any. */
export const PAGE_HEADER = 'space-y-1 pb-3 pt-1';

/** A small mono micro-label above an h1 (e.g. "Portfolio · ledger"). */
export const EYEBROW = 'font-mono text-[11px] uppercase tracking-wide text-ink-mute';

/** The route h1: small mono, one per page. */
export const H1 = 'font-mono text-lg font-medium tracking-tight text-ink md:text-xl';

/** The one-line lede under an h1. */
export const LEDE = 'max-w-2xl text-sm text-ink-soft';

/** A content section: a heading plus its body, stacked. */
export const SECTION = 'space-y-3';

/** A section heading (h2), the only level below h1. */
export const SECTION_HEAD = 'font-mono text-xs uppercase tracking-wide text-ink-mute';

/**
 * The explicit desktop offset the main region must carry under the fixed
 * sidebar (260px expanded / 72px collapsed — the literal widths live in
 * `components/sidebar.tsx`, since Tailwind extracts literal class strings and
 * cannot see an interpolated `md:pl-[${n}px]`).
 *
 * The sidebar is `fixed` (out of flow), so `main` cannot rely on the chrome
 * happening to reserve space — the offset is stated here and asserted in
 * `components/app-frame.test.tsx` so the "content under the sidebar" regression
 * (plan §8, critical) cannot return.
 */
export function mainOffsetClass(sidebarCollapsed: boolean): string {
  return sidebarCollapsed ? 'md:pl-[72px]' : 'md:pl-[260px]';
}
