import type { ElementType } from 'react';
import { LayoutDashboard, PieChart, GitBranch, Activity, Globe } from 'lucide-react';

export interface NavItem {
  href: string;
  label: string;
  icon: ElementType<{ size?: number }>;
  /** System is the demoted operator footnote — pinned bottom, muted (desktop). */
  demoted?: boolean;
}

/**
 * The portfolio-owner spine: glance → why → full, four destinations.
 * Single source of truth consumed by both the desktop sidebar and the mobile
 * app bar so they can never drift.
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
  { href: '/system', label: 'System', icon: Activity, demoted: true },
];

/**
 * Pathname prefixes that stay LIVE when the live data backend is down (the
 * DB-unavailable gate). Two kinds of routes are exempt:
 *   - operator surfaces that must stay reachable to diagnose / reconfigure:
 *     '/system' (how-it-works lives inside system-page) and '/settings';
 *   - static legacy redirect routes that never touch Supabase, so gating them
 *     would only swallow a redirect.
 * Pathnames are app-relative (basePath '/olympus' is stripped by usePathname).
 */
export const DB_EXEMPT_PREFIXES = [
  '/system',
  '/settings',
  // twelve-x reads its own research feed (isTwelveXConfigured), not the main
  // Olympus backend — the shell's DB gate must not swallow it (#1664).
  '/twelve-x',
  '/architecture',
  '/library',
  '/observability',
  '/performance',
  '/research',
  '/strategy',
  '/portfolio/theses',
] as const;

/** True when `pathname` should stay live even while the backend is unreachable. */
export function isDbExempt(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  return DB_EXEMPT_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}
