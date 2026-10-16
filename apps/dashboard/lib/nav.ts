import type { ElementType } from 'react';
import { Globe } from 'lucide-react';

export interface NavItem {
  href: string;
  label: string;
  icon: ElementType<{ size?: number }>;
  /** Optional muted/pinned-bottom footnote item (desktop). Unused while spine is four + FX. */
  demoted?: boolean;
}

/**
 * This release the dashboard shell is FX Hub only.
 * Brief, portfolio, and pipeline are the brief desk at `/app`
 * (`apps/digiquant-web`). The sidebar and the mobile drawer both read this
 * list, so they cannot drift.
 *
 * FX Hub stays at `/twelve-x` (base path `/dashboard`). Do not retarget it.
 */
export const NAV: NavItem[] = [{ href: '/twelve-x', label: 'FX Hub', icon: Globe }];

/**
 * Pathname prefixes that stay LIVE when the live data backend is down (the
 * DB-unavailable gate). Two kinds of routes are exempt:
 *   - `/settings`, which must stay reachable to diagnose / reconfigure.
 *     Pipeline stays behind the DB gate (`isDbExempt('/pipeline')` is false).
 *   - static legacy redirect routes that never touch Supabase, so gating them
 *     would only swallow a redirect.
 * Pathnames are app-relative (basePath '/dashboard' is stripped by usePathname).
 */
export const DB_EXEMPT_PREFIXES = [
  '/system', // legacy redirect → /pipeline
  '/settings',
  // twelve-x reads its own research feed (isTwelveXConfigured), not the main
  // dashboard backend — the shell's DB gate must not swallow it (#1664).
  '/twelve-x',
  '/architecture',
  '/library',
  '/observability',
  '/performance',
  '/research',
  '/strategy',
  '/portfolio/theses',
  // House chrome declares corpus/profile contracts; corpus sample keys fail soft.
  '/house',
] as const;

/** True when `pathname` should stay live even while the backend is unreachable. */
export function isDbExempt(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  return DB_EXEMPT_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}
