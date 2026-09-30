import type { ElementType } from 'react';
import { Building2, GitBranch, Globe, LayoutDashboard, PieChart, Settings } from 'lucide-react';
import { NAV_ALIASES } from '@/lib/nav';
import { settingsTabsVisible } from '@/lib/entitlements';
import type { PlanTier } from '@/lib/entitlements';

/** Width mode the shell gives `main` for a route (page header can override). */
export type LayoutMode = 'contained' | 'fluid' | 'canvas';

export interface NavChild {
  id: string;
  label: string;
  /** App-relative path (no basePath). */
  path: string;
  /** Query param that selects this child, e.g. `tab=theses`. */
  param?: { key: string; value: string };
  /** Hash id that selects this child (settings tabs). */
  hash?: string;
  /** The child that reads as current when no sibling matches. */
  isDefault?: boolean;
  /** Extra pathname prefixes that keep this child current. */
  alsoPaths?: readonly string[];
}

export interface NavGroupItem {
  id: string;
  label: string;
  href: string;
  icon: ElementType<{ className?: string }>;
  children: NavChild[];
  /** Pathname prefixes that belong to this destination. */
  owns: readonly string[];
  layout: LayoutMode;
  title: string;
}

const owns = (href: string) => NAV_ALIASES[href] ?? [href];

const portfolio: NavGroupItem = {
  id: 'portfolio',
  label: 'Portfolio',
  href: '/portfolio',
  icon: PieChart,
  owns: owns('/portfolio'),
  layout: 'contained',
  title: 'Portfolio',
  children: [
    { id: 'holdings', label: 'Holdings', path: '/portfolio', isDefault: true },
    {
      id: 'theses',
      label: 'Theses',
      path: '/portfolio',
      param: { key: 'tab', value: 'theses' },
      alsoPaths: ['/portfolio/theses'],
    },
    { id: 'tearsheet', label: 'Tearsheet', path: '/portfolio/performance', alsoPaths: ['/performance'] },
    { id: 'attribution', label: 'Attribution', path: '/portfolio/attribution' },
    { id: 'ledger', label: 'Ledger', path: '/portfolio/ledger' },
  ],
};

const fxTab = (id: string, label: string, isDefault = false): NavChild => ({
  id,
  label,
  path: '/twelve-x',
  ...(isDefault ? { isDefault: true } : { param: { key: 'tab', value: id } }),
});

const fxHub: NavGroupItem = {
  id: 'twelve-x',
  label: 'FX Hub',
  href: '/twelve-x',
  icon: Globe,
  owns: owns('/twelve-x'),
  layout: 'contained',
  title: 'FX Hub',
  children: [
    fxTab('today', 'Today', true),
    fxTab('consensus', 'Consensus'),
    fxTab('trades', 'Trades'),
    fxTab('matrix', 'Matrix'),
    fxTab('events', 'Events'),
    fxTab('how-it-works', 'How it works'),
  ],
};

const houseTab = (id: string, label: string, isDefault = false): NavChild => ({
  id,
  label,
  path: '/house',
  ...(isDefault ? { isDefault: true } : { param: { key: 'tab', value: id } }),
});

const house: NavGroupItem = {
  id: 'house',
  label: 'House',
  href: '/house',
  icon: Building2,
  owns: ['/house'],
  layout: 'contained',
  title: 'House',
  children: [houseTab('corpus', 'Corpus', true), houseTab('book', 'Book'), houseTab('profile', 'Profile')],
};

export const WORKSPACE: readonly NavGroupItem[] = [
  {
    id: 'brief',
    label: 'Brief',
    href: '/',
    icon: LayoutDashboard,
    owns: ['/'],
    layout: 'contained',
    title: 'Brief',
    children: [],
  },
  portfolio,
  {
    id: 'pipeline',
    label: 'Pipeline',
    href: '/pipeline',
    icon: GitBranch,
    owns: owns('/pipeline'),
    layout: 'canvas',
    title: 'Pipeline',
    children: [],
  },
  fxHub,
];

export const REFERENCE: readonly NavGroupItem[] = [house];

export function settingsGroup(tier: PlanTier | null): NavGroupItem {
  const tabs = tier ? settingsTabsVisible(tier) : [];
  return {
    id: 'settings',
    label: 'Settings',
    href: '/settings',
    icon: Settings,
    owns: ['/settings'],
    layout: 'contained',
    title: 'Settings',
    children: tabs.map((t, i) => ({
      id: t.id,
      label: t.label,
      path: '/settings',
      hash: t.id,
      isDefault: i === 0,
    })),
  };
}

/** App-relative pathname without basePath or trailing slash. */
export function normalizePath(pathname: string | null | undefined, basePath = '/dashboard'): string {
  let path = (pathname ?? '').replace(/\/+$/, '') || '/';
  if (basePath && (path === basePath || path.startsWith(`${basePath}/`))) {
    path = path.slice(basePath.length) || '/';
  }
  return path;
}

export function ownsPath(item: NavGroupItem, path: string): boolean {
  if (item.href === '/') return path === '/';
  return item.owns.some((p) => path === p || path.startsWith(`${p}/`));
}

/** Which destination (workspace, reference or settings) a pathname belongs to. */
export function destinationFor(path: string): NavGroupItem | null {
  return [...WORKSPACE, ...REFERENCE, settingsGroup(null)].find((g) => ownsPath(g, path)) ?? null;
}

/** Static title for a route so the prerendered HTML always carries an h1. */
export function titleFor(pathname: string | null | undefined, basePath?: string): string {
  return destinationFor(normalizePath(pathname, basePath))?.title ?? 'Dashboard';
}

export function layoutFor(pathname: string | null | undefined, basePath?: string): LayoutMode {
  return destinationFor(normalizePath(pathname, basePath))?.layout ?? 'contained';
}

/** The id of the current child of `group`, given the live URL state. */
export function activeChildId(
  group: NavGroupItem,
  path: string,
  search: string,
  hash: string
): string | null {
  if (!ownsPath(group, path)) return null;
  const params = new URLSearchParams(search);
  const hashId = hash.replace(/^#/, '').split(/[?&]/, 1)[0];
  const match = group.children.find((c) => {
    if (c.hash) return c.hash === hashId;
    if (c.param) return path === c.path && params.get(c.param.key) === c.param.value;
    return false;
  });
  if (match) return match.id;
  const byPath = group.children.find(
    (c) =>
      !c.param &&
      !c.hash &&
      !c.isDefault &&
      (path === c.path || path.startsWith(`${c.path}/`) || c.alsoPaths?.some((p) => path === p || path.startsWith(`${p}/`)))
  );
  if (byPath) return byPath.id;
  const alsoParam = group.children.find((c) => c.alsoPaths?.some((p) => path === p || path.startsWith(`${p}/`)));
  if (alsoParam) return alsoParam.id;
  return group.children.find((c) => c.isDefault)?.id ?? null;
}

export function childHref(child: NavChild): string {
  if (child.param) return `${child.path}?${child.param.key}=${child.param.value}`;
  if (child.hash) return `${child.path}#${child.hash}`;
  return child.path;
}
