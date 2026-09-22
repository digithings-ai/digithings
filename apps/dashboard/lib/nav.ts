import type { ElementType } from 'react';
import { LayoutDashboard, PieChart, GitBranch, Globe } from 'lucide-react';
import { normalizePathname } from '@/lib/pathname';

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
 * Legacy pathnames the dashboard still serves but that immediately client-
 * redirect to their replacement route. Kept as data (not scattered regexes) so
 * the nav→route map has ONE source of truth and the route-map test can assert
 * no *advertised* destination is in here — a destination that silently
 * redirects is the route-collapse bug the plan calls out (§8).
 *
 * Keyed by the app-relative pathname (basePath '/dashboard' is stripped by
 * usePathname). Values keep their query form; `navItemForPath` strips it.
 */
export const LEGACY_REDIRECTS: Readonly<Record<string, string>> = {
  '/system': '/pipeline', // run health moved to Pipeline
  '/research': '/pipeline',
  '/library': '/pipeline',
  '/observability': '/pipeline',
  '/architecture': '/pipeline',
  '/strategy': '/portfolio?tab=theses',
  '/performance': '/portfolio/performance',
  '/portfolio/period': '/portfolio/performance', // Period inspect retired (#3060)
};

/** True when the pathname is a served-but-redirecting legacy route. */
export function isLegacyRedirectPath(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  return normalizePathname(pathname) in LEGACY_REDIRECTS;
}

/**
 * The nav→route resolver: which NAV destination a pathname belongs to, or null
 * when it is not a nav destination at all.
 *
 * Deliberately derived from `NAV` + `LEGACY_REDIRECTS` rather than hand-written
 * per-route regexes. A live route that is neither a NAV item nor a redirect to
 * one resolves to null — it must NOT be silently attributed to a destination it
 * does not render (the `/why` collapse this replaces). Family routes keep their
 * parent (`/portfolio/ledger` → `/portfolio`).
 */
export function navItemForPath(pathname: string | null | undefined, basePath = ''): string | null {
  if (!pathname) return null;
  const norm = normalizePathname(pathname);
  const base = normalizePathname(basePath);
  const rel = base !== '/' && (norm === base || norm.startsWith(`${base}/`))
    ? norm.slice(base.length) || '/'
    : norm;

  const target = LEGACY_REDIRECTS[rel];
  if (target) return navItemForPath(target.split('?')[0], '');

  for (const item of NAV) {
    if (item.href === '/') {
      if (rel === '/') return '/';
      continue;
    }
    if (rel === item.href || rel.startsWith(`${item.href}/`)) return item.href;
  }
  return null;
}

/**
 * Pathname prefixes that stay LIVE when the live data backend is down (the
 * DB-unavailable gate). The explicit list covers operator and static-summary
 * surfaces:
 *   - operator surfaces that must stay reachable to diagnose / reconfigure:
 *     '/pipeline' (run health panel) and '/settings';
 *   - surfaces that read their own feed or declare their own contracts and so
 *     fail soft rather than through the main dashboard fetch: '/twelve-x'
 *     (#1664), '/house';
 *   - '/portfolio/theses', which conditionally renders a thesis deep link and
 *     otherwise redirects.
 *
 * Legacy redirect routes (`LEGACY_REDIRECTS`) are ALSO exempt by derivation —
 * gating one would only swallow its redirect. Deriving that set is the fix for
 * the over-reach this list previously had (a redirect route missing from the
 * hand-written list was replaced by the empty state). The effective exempt set
 * is pinned exactly in `lib/nav.test.ts`.
 */
export const DB_EXEMPT_PREFIXES = [
  '/pipeline', // operator surface: run-health panel must stay reachable DB-down
  '/settings',
  // twelve-x reads its own research feed (isTwelveXConfigured), not the main
  // dashboard backend — the shell's DB gate must not swallow it (#1664).
  '/twelve-x',
  // House chrome declares corpus/profile contracts; corpus sample keys fail soft.
  '/house',
  '/portfolio/theses',
] as const;

/** True when `pathname` should stay live even while the backend is unreachable. */
export function isDbExempt(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  if (isLegacyRedirectPath(pathname)) return true;
  return DB_EXEMPT_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}
