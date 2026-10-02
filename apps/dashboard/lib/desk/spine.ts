/**
 * Desk spines and path chrome.
 *
 * Chrome paths may say `/book` and `/movers` as segments. There is no
 * `/book` or `/movers` route in this slice. Rail hrefs stay on real pages
 * or on `?pane=` / `?desk=` aliases. Slice B owns the DigiCon client map.
 */

import { normalizePathname } from '@/lib/pathname';

export type DeskId = 'house' | 'rates-watch' | 'fx-hub';

export type DeskBadge = 'wip' | 'soon';

export type DeskBanner = {
  badge: DeskBadge;
  title: string;
  body: string;
};

export type RailNode = {
  id: string;
  label: string;
  href: string;
  badge?: DeskBadge;
  banner?: DeskBanner;
  children?: RailNode[];
};

export type ChromeSegment = {
  label: string;
  href: string;
};

export type LocationChrome = {
  deskId: DeskId;
  segments: ChromeSegment[];
  banner: DeskBanner | null;
  activeRailId: string;
};

export type DeskPathJump = {
  id: string;
  title: string;
  hint: string;
  href: string;
};

const RATES_BODY =
  'Rates watch is not a second book. This desk is a layout placeholder and does not read the house portfolio.';

const TOOL_BODY =
  'This tool is a labeled placeholder. It does not embed a vendor terminal and it does not invent quotes.';

const STRATEGY_BODY =
  'Strategies are not deployed from this desk. Nothing here places an order or shows a track record.';

const THEME_BODY =
  'Theme uses the saved desk preference (system, light, or dark) under dashboard-theme. This entry does not add a second control.';

const INTEGRATIONS_BODY =
  'Integrations are not connected. This entry does not issue keys or embed Gloomberg or LuxAlgo.';

function banner(badge: DeskBadge, title: string, body: string): DeskBanner {
  return { badge, title, body };
}

function ratesNode(id: string, label: string): RailNode {
  return {
    id,
    label,
    href: `/?desk=rates-watch&section=${id}`,
    badge: 'wip',
    banner: banner('wip', `${label} is not available`, RATES_BODY),
  };
}

export const RATES_WATCH_SPINE: readonly RailNode[] = [
  ratesNode('digest', 'digest'),
  ratesNode('watchlist', 'watchlist'),
  ratesNode('theses', 'theses'),
  ratesNode('run', 'run'),
  ratesNode('config', 'config'),
];

export const FX_HUB_SPINE: readonly RailNode[] = [
  { id: 'today', label: 'today', href: '/twelve-x' },
  { id: 'consensus', label: 'consensus', href: '/twelve-x?tab=consensus' },
  { id: 'trades', label: 'trades', href: '/twelve-x?tab=trades' },
  { id: 'matrix', label: 'matrix', href: '/twelve-x?tab=matrix' },
  { id: 'events', label: 'events', href: '/twelve-x?tab=events' },
  { id: 'how-it-works', label: 'how it works', href: '/twelve-x?tab=how-it-works' },
];

function soon(id: string, label: string, href: string, title: string, body = TOOL_BODY): RailNode {
  return {
    id,
    label,
    href,
    badge: 'soon',
    banner: banner('soon', title, body),
  };
}

export const HOUSE_SPINE: readonly RailNode[] = [
  {
    id: 'brief',
    label: 'brief',
    href: '/',
    children: [
      { id: 'decision', label: 'decision', href: '/?pane=decision' },
      { id: 'signals', label: 'signals', href: '/?pane=signals' },
      { id: 'book', label: 'book', href: '/?pane=book' },
      { id: 'movers', label: 'movers', href: '/?pane=movers' },
      { id: 'breaks', label: 'breaks', href: '/?pane=breaks' },
      soon('gloomberg', 'gloomberg', '/?pane=gloomberg', 'Gloomberg is a layout placeholder'),
      soon('luxalgo', 'luxalgo', '/?pane=luxalgo', 'LuxAlgo is a layout placeholder'),
      { id: 'run', label: 'run', href: '/?pane=run' },
    ],
  },
  {
    id: 'portfolio',
    label: 'portfolio',
    href: '/portfolio',
    children: [
      { id: 'holdings', label: 'holdings', href: '/portfolio' },
      { id: 'theses', label: 'theses', href: '/portfolio?tab=theses' },
      { id: 'tearsheet', label: 'tearsheet', href: '/portfolio/performance' },
      { id: 'ledger', label: 'ledger', href: '/portfolio/ledger' },
      { id: 'attribution', label: 'attribution', href: '/portfolio/attribution' },
    ],
  },
  { id: 'pipeline', label: 'pipeline', href: '/pipeline' },
  {
    id: 'tools',
    label: 'tools',
    href: '/?pane=terminal',
    children: [
      soon('terminal', 'terminal', '/?pane=terminal', 'Gloomberg terminal is a layout placeholder'),
      soon('charts', 'charts', '/?pane=charts', 'Charts land with the Vela pane'),
    ],
  },
  {
    id: 'strategies',
    label: 'strategies',
    href: '/?pane=strategies',
    badge: 'wip',
    banner: banner('wip', 'Strategies are not live', STRATEGY_BODY),
  },
  {
    id: 'settings',
    label: 'settings',
    href: '/settings',
    children: [
      { id: 'profile', label: 'profile', href: '/settings#profile' },
      { id: 'pipeline-settings', label: 'pipeline', href: '/settings#pipeline' },
      { id: 'keys', label: 'keys', href: '/settings#keys' },
      { id: 'brokers', label: 'brokers', href: '/settings#brokers' },
      soon(
        'integrations',
        'integrations',
        '/?pane=integrations',
        'Integrations are not connected',
        INTEGRATIONS_BODY,
      ),
      soon('theme', 'theme', '/?pane=theme', 'Theme stays on the desk preference', THEME_BODY),
      { id: 'notifications', label: 'notifications', href: '/settings#notifications' },
      { id: 'billing', label: 'billing', href: '/settings#billing' },
      { id: 'about', label: 'about', href: '/settings#about' },
    ],
  },
  { id: 'fx-hub', label: 'FX Hub', href: '/twelve-x' },
];

export const DESK_OPTIONS: readonly {
  id: DeskId;
  label: string;
  href: string;
  badge?: DeskBadge;
}[] = [
  { id: 'house', label: 'house', href: '/' },
  { id: 'rates-watch', label: 'rates watch', href: '/?desk=rates-watch', badge: 'wip' },
  { id: 'fx-hub', label: 'FX Hub', href: '/twelve-x' },
];

const SPINES: Record<DeskId, readonly RailNode[]> = {
  house: HOUSE_SPINE,
  'rates-watch': RATES_WATCH_SPINE,
  'fx-hub': FX_HUB_SPINE,
};

export function railForDesk(deskId: DeskId, fxHubOnly = false): readonly RailNode[] {
  if (fxHubOnly) {
    return [
      ...FX_HUB_SPINE,
      { id: 'account', label: 'account', href: '/settings' },
    ];
  }
  return SPINES[deskId];
}

export function formatChromePath(segments: readonly { label: string }[]): string {
  return segments.map((segment) => segment.label).join(' / ');
}

function paramsOf(search: string): URLSearchParams {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  return new URLSearchParams(raw);
}

function hashId(hash: string): string {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  return raw.split(/[?&]/, 1)[0] ?? '';
}

function findNode(nodes: readonly RailNode[], id: string): RailNode | undefined {
  for (const node of nodes) {
    if (node.id === id) return node;
    if (node.children) {
      const child = findNode(node.children, id);
      if (child) return child;
    }
  }
  return undefined;
}

const PIPELINE_PREFIXES = [
  '/pipeline',
  '/why',
  '/research',
  '/library',
  '/system',
  '/observability',
  '/architecture',
];

function isPipelinePath(path: string): boolean {
  return PIPELINE_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );
}

const BRIEF_PANES = new Set(['decision', 'signals', 'book', 'movers', 'breaks', 'run']);

export function locationChrome(pathname: string, search = '', hash = ''): LocationChrome {
  const path = normalizePathname(pathname || '/');
  const params = paramsOf(search);
  const deskParam = params.get('desk');
  const pane = params.get('pane');
  const section = params.get('section');
  const tab = params.get('tab');

  if (deskParam === 'rates-watch') {
    const id = findNode(RATES_WATCH_SPINE, section ?? '')?.id ?? 'digest';
    const node = findNode(RATES_WATCH_SPINE, id)!;
    return {
      deskId: 'rates-watch',
      segments: [
        { label: 'rates watch', href: '/?desk=rates-watch' },
        { label: node.label, href: node.href },
      ],
      banner: node.banner ?? null,
      activeRailId: node.id,
    };
  }

  if (path === '/twelve-x' || path.startsWith('/twelve-x/')) {
    const node = findNode(FX_HUB_SPINE, tab ?? '') ?? FX_HUB_SPINE[0];
    return {
      deskId: 'fx-hub',
      segments: [
        { label: 'FX Hub', href: '/twelve-x' },
        { label: node.label, href: node.href },
      ],
      banner: null,
      activeRailId: node.id,
    };
  }

  if (pane) {
    const node = findNode(HOUSE_SPINE, pane);
    if (node?.banner) {
      const parent = parentOf(HOUSE_SPINE, pane);
      const segments: ChromeSegment[] = [{ label: 'house', href: '/' }];
      if (parent && parent.id !== node.id) {
        segments.push({ label: parent.label, href: parent.href });
      }
      segments.push({ label: node.label, href: node.href });
      return {
        deskId: 'house',
        segments,
        banner: node.banner,
        activeRailId: node.id,
      };
    }
    if (node && BRIEF_PANES.has(node.id)) {
      return {
        deskId: 'house',
        segments: [
          { label: 'house', href: '/' },
          { label: 'brief', href: '/' },
          { label: node.label, href: node.href },
        ],
        banner: null,
        activeRailId: node.id,
      };
    }
  }

  if (path === '/' || path === '/house') {
    return {
      deskId: 'house',
      segments: [
        { label: 'house', href: '/' },
        { label: 'brief', href: '/' },
      ],
      banner: null,
      activeRailId: 'brief',
    };
  }

  if (path === '/portfolio' || path === '/performance') {
    if (path === '/performance' || tab === 'tearsheet') {
      return portfolioChrome('tearsheet');
    }
    if (tab === 'theses') return portfolioChrome('theses');
    if (tab === 'ledger') return portfolioChrome('ledger');
    if (tab === 'attribution') return portfolioChrome('attribution');
    return portfolioChrome('holdings');
  }

  if (path === '/portfolio/theses' || path.startsWith('/portfolio/theses/')) {
    return portfolioChrome('theses');
  }
  if (path === '/portfolio/performance' || path.startsWith('/portfolio/performance/')) {
    return portfolioChrome('tearsheet');
  }
  if (path === '/portfolio/ledger' || path.startsWith('/portfolio/ledger/')) {
    return portfolioChrome('ledger');
  }
  if (path === '/portfolio/attribution' || path.startsWith('/portfolio/attribution/')) {
    return portfolioChrome('attribution');
  }
  if (path === '/portfolio/period' || path.startsWith('/portfolio/period/')) {
    return portfolioChrome('tearsheet');
  }
  if (path === '/portfolio/tickers' || path.startsWith('/portfolio/tickers/')) {
    return {
      deskId: 'house',
      segments: [
        { label: 'house', href: '/' },
        { label: 'portfolio', href: '/portfolio' },
        { label: 'dossier', href: '/portfolio/tickers' },
      ],
      banner: null,
      activeRailId: 'holdings',
    };
  }

  if (isPipelinePath(path)) {
    return {
      deskId: 'house',
      segments: [
        { label: 'house', href: '/' },
        { label: 'pipeline', href: '/pipeline' },
      ],
      banner: null,
      activeRailId: 'pipeline',
    };
  }

  if (path === '/settings' || path.startsWith('/settings/')) {
    const id = hashId(hash);
    const settings = findNode(HOUSE_SPINE, 'settings');
    const child = settings?.children?.find((item) => item.id === id || item.href.endsWith(`#${id}`));
    const segments: ChromeSegment[] = [
      { label: 'house', href: '/' },
      { label: 'settings', href: '/settings' },
    ];
    if (child && child.id !== 'settings') {
      segments.push({ label: child.label, href: child.href });
    }
    return {
      deskId: 'house',
      segments,
      banner: null,
      activeRailId: child?.id ?? 'settings',
    };
  }

  if (path === '/strategy' || path.startsWith('/strategy/')) {
    const node = findNode(HOUSE_SPINE, 'strategies')!;
    return {
      deskId: 'house',
      segments: [
        { label: 'house', href: '/' },
        { label: 'strategies', href: node.href },
      ],
      banner: node.banner ?? null,
      activeRailId: 'strategies',
    };
  }

  return {
    deskId: 'house',
    segments: [
      { label: 'house', href: '/' },
      { label: 'brief', href: '/' },
    ],
    banner: null,
    activeRailId: 'brief',
  };
}

function portfolioChrome(id: string): LocationChrome {
  const node = findNode(HOUSE_SPINE, id);
  return {
    deskId: 'house',
    segments: [
      { label: 'house', href: '/' },
      { label: 'portfolio', href: '/portfolio' },
      { label: node?.label ?? id, href: node?.href ?? '/portfolio' },
    ],
    banner: null,
    activeRailId: id,
  };
}

function parentOf(nodes: readonly RailNode[], id: string, parent?: RailNode): RailNode | undefined {
  for (const node of nodes) {
    if (node.id === id) return parent;
    if (node.children) {
      const found = parentOf(node.children, id, node);
      if (found) return found;
    }
  }
  return undefined;
}

/** Palette rows so ⌘K can jump by the path the top chrome prints. */
export const DESK_PATH_JUMPS: readonly DeskPathJump[] = [
  { id: 'go-house', title: 'house / brief', hint: 'Desk path', href: '/' },
  {
    id: 'path-holdings',
    title: 'house / portfolio / holdings',
    hint: 'Desk path',
    href: '/portfolio',
  },
  {
    id: 'path-theses',
    title: 'house / portfolio / theses',
    hint: 'Desk path',
    href: '/portfolio?tab=theses',
  },
  {
    id: 'path-tearsheet',
    title: 'house / portfolio / tearsheet',
    hint: 'Desk path',
    href: '/portfolio/performance',
  },
  {
    id: 'path-ledger',
    title: 'house / portfolio / ledger',
    hint: 'Desk path',
    href: '/portfolio/ledger',
  },
  {
    id: 'path-attribution',
    title: 'house / portfolio / attribution',
    hint: 'Desk path',
    href: '/portfolio/attribution',
  },
  { id: 'path-pipeline', title: 'house / pipeline', hint: 'Desk path', href: '/pipeline' },
  {
    id: 'path-rates',
    title: 'rates watch / digest',
    hint: 'Layout placeholder',
    href: '/?desk=rates-watch',
  },
  { id: 'path-fx', title: 'FX Hub / today', hint: 'Desk path', href: '/twelve-x' },
];

export function railLabels(nodes: readonly RailNode[]): string[] {
  const labels: string[] = [];
  for (const node of nodes) {
    labels.push(node.label);
    if (node.children) labels.push(...railLabels(node.children));
  }
  return labels;
}
