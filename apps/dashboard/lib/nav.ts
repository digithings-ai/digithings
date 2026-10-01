import type { ElementType } from 'react';
import { LayoutDashboard, PieChart, GitBranch, Globe } from 'lucide-react';

export interface NavItem {
  href: string;
  label: string;
  icon: ElementType<{ size?: number }>;
  /** Optional muted/pinned-bottom footnote item (desktop). Unused while spine is four + FX. */
  demoted?: boolean;
}

/**
 * The portfolio-owner spine: glance → why → full, plus FX Hub.
 * Single source of truth consumed by both the desktop sidebar and the mobile
 * app bar so they can never drift.
 *
 * System was removed from top-level nav — run health lives on Pipeline (date
 * stats) and Brief (timeline). Legacy `/system` redirects to `/pipeline`.
 *
 * The FX Hub suite (/twelve-x) is a permanent destination since the
 * #1664 dashboard integration (previously env-gated behind
 * NEXT_PUBLIC_TWELVEX_ENABLED and rendered standalone).
 */
export const NAV: NavItem[] = [
  { href: '/', label: 'Brief', icon: LayoutDashboard },
  { href: '/portfolio', label: 'Portfolio', icon: PieChart },
  { href: '/pipeline', label: 'Pipeline', icon: GitBranch },
  { href: '/twelve-x', label: 'FX Hub', icon: Globe },
];

/**
 * Legacy routes folded into a spine destination: while the visitor is on one
 * of these the owning NAV entry reads as current. Pipeline replaced Why +
 * System and absorbs the research/library/observability/architecture routes;
 * Portfolio absorbs the old Performance route (now a tab).
 */
export const NAV_ALIASES: Record<string, readonly string[]> = {
  '/portfolio': ['/portfolio', '/performance'],
  '/pipeline': ['/pipeline', '/why', '/research', '/library', '/system', '/observability', '/architecture'],
  '/twelve-x': ['/twelve-x'],
};

/**
 * The NAV href a pathname belongs to, or null (e.g. /settings, auth routes).
 * `pathname` may or may not carry the basePath and may carry a trailing slash.
 */
export function activeNavHref(pathname: string | null | undefined, basePath = '/dashboard'): string | null {
  if (!pathname) return null;
  let path = pathname.replace(/\/+$/, '') || '/';
  if (basePath && (path === basePath || path.startsWith(`${basePath}/`))) {
    path = path.slice(basePath.length) || '/';
  }
  if (path === '/') return '/';
  for (const [href, prefixes] of Object.entries(NAV_ALIASES)) {
    if (prefixes.some((p) => path === p || path.startsWith(`${p}/`))) return href;
  }
  return null;
}

/**
 * Pathname prefixes that stay LIVE when the live data backend is down (the
 * DB-unavailable gate). Two kinds of routes are exempt:
 *   - operator surfaces that must stay reachable to diagnose / reconfigure:
 *     '/pipeline' (run health panel) and '/settings';
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
