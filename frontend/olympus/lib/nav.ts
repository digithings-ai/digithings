import type { ElementType } from 'react';
import { LayoutDashboard, PieChart, GitBranch, Activity, Globe, Library } from 'lucide-react';

export interface NavItem {
  href: string;
  label: string;
  icon: ElementType<{ size?: number }>;
  /** System is the demoted operator footnote — pinned bottom, muted (desktop). */
  demoted?: boolean;
}

/**
 * Product chrome spine (vision brief 2026-08-25): Brief → Portfolio → Corpus →
 * Pipeline → FX Hub, with System demoted. Single source of truth for desktop
 * sidebar + mobile app bar.
 *
 * Corpus | Book | Profile lives under /corpus. Portfolio Tearsheet | Ledger |
 * Period are Portfolio sub-routes. FX Hub (/twelve-x) is permanent since #1664.
 */
export const NAV: NavItem[] = [
  { href: '/', label: 'Brief', icon: LayoutDashboard },
  { href: '/portfolio', label: 'Portfolio', icon: PieChart },
  { href: '/corpus', label: 'Corpus', icon: Library },
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
  // Corpus chrome is mostly typed-gap / house-seed identity; keep reachable
  // when the main dashboard DB gate is down (#2644).
  '/corpus',
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
