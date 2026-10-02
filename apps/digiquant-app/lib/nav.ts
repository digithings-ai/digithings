/**
 * Navigation tree — one source for the drop-down menu, the pinned sidebar,
 * the command line and routing. A page IS its slash-path.
 * Structure follows the canvas mock's spine; `status` mirrors its [wip]/[soon] tags.
 */
export type NavNode = {
  path: string;
  label: string;
  status?: 'wip' | 'soon';
  children?: NavNode[];
  /** Set from the access manifest when the caller can see but not open the page: the tag to show ("brief", "12x"). */
  lock?: string;
};

export type NavGroup = { title: string | null; items: NavNode[] };

export const NAV: NavGroup[] = [
  {
    title: null,
    items: [
      { path: '/brief', label: 'Brief' },
      {
        path: '/portfolio',
        label: 'Portfolio',
        children: [
          { path: '/portfolio/holdings', label: 'Holdings' },
          { path: '/portfolio/attribution', label: 'Attribution' },
          { path: '/portfolio/ledger', label: 'Ledger' },
          { path: '/portfolio/tearsheet', label: 'Tearsheet' },
          { path: '/portfolio/theses', label: 'Theses' },
        ],
      },
      { path: '/pipeline', label: 'Pipeline' },
      {
        path: '/strategies',
        label: 'Strategies',
        status: 'wip',
        children: [
          { path: '/strategies/detail', label: 'Detail' },
          { path: '/strategies/deploy', label: 'Deploy' },
        ],
      },
    ],
  },
  {
    title: 'tools',
    items: [
      { path: '/tools/terminal', label: 'Terminal', status: 'soon' },
      { path: '/tools/luxalgo', label: 'LuxAlgo', status: 'soon' },
      { path: '/tools/charts', label: 'Charts', status: 'wip' },
      { path: '/tools/chat', label: 'digichat', status: 'wip' },
      {
        path: '/fx',
        label: 'FX Hub',
        status: 'soon',
        children: [
          { path: '/fx/ideas', label: 'Ideas' },
          { path: '/fx/watch', label: 'Watch' },
          { path: '/fx/rates', label: 'Rates' },
          { path: '/fx/settings', label: 'Settings' },
        ],
      },
    ],
  },
  {
    title: null,
    items: [
      {
        path: '/settings',
        label: 'Settings',
        children: [{ path: '/settings/paper', label: 'Paper' }],
      },
    ],
  },
];

export const HOME = '/brief';

/** Every page (parents and leaves) in menu order. */
export function flatPages(): NavNode[] {
  const out: NavNode[] = [];
  const walk = (n: NavNode) => {
    out.push(n);
    n.children?.forEach(walk);
  };
  NAV.forEach((g) => g.items.forEach(walk));
  return out;
}

export function findPage(path: string): NavNode | undefined {
  return flatPages().find((p) => p.path === path);
}

/** Case-insensitive match on path or label, for the command line. */
export function searchPages(q: string, all: NavNode[] = flatPages()): NavNode[] {
  const needle = q.trim().toLowerCase().replace(/^\//, '');
  if (!needle) return all;
  return all.filter((p) => p.path.toLowerCase().includes(needle) || p.label.toLowerCase().includes(needle));
}

/** Top-level section that owns a path (`/portfolio/ledger` → `/portfolio`). */
export function sectionOf(path: string): string {
  return '/' + (path.split('/').filter(Boolean)[0] ?? '');
}
