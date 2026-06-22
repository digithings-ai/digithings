import type { ElementType } from 'react';
import { LayoutDashboard, PieChart, BookOpen, Activity } from 'lucide-react';

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
 */
export const NAV: NavItem[] = [
  { href: '/', label: 'Today', icon: LayoutDashboard },
  { href: '/portfolio', label: 'Portfolio', icon: PieChart },
  { href: '/why', label: 'Why', icon: BookOpen },
  { href: '/system', label: 'System', icon: Activity, demoted: true },
];
