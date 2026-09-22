/** Shared page width and horizontal padding for dashboard workspaces. */
export const SUBPAGE_MAX = 'max-w-[1600px] mx-auto w-full px-4 md:px-6';

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
