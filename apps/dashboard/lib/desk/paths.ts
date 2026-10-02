/**
 * Chrome path → dashboard-api endpoint.
 *
 * A digiquant pane read is a `DigiquantRead` from `client.ts`.
 * The reads are dashboard-api, market closes, and
 * `GET /v1/tables/:table`. Chrome may say `/book` or `/movers`; the client
 * still calls `GET /portfolio` or derives movers. Do not add those routes.
 */

export const DESK_ENDPOINTS = {
  portfolio: '/portfolio',
  allocations: '/allocations',
  brief: '/brief',
  performance: '/performance',
  kpisLive: '/kpis/live',
  navSeries: '/nav-series',
  benchmarks: '/benchmarks',
  ledger: '/ledger',
} as const;

export type DeskEndpoint = (typeof DESK_ENDPOINTS)[keyof typeof DESK_ENDPOINTS];

/** Allowlist from dashboard-api CONTRACT §7. Unknown names are not a route. */
export const DESK_TABLES = [
  'daily_snapshots',
  'positions',
  'instruments',
  'theses',
  'portfolio_metrics',
  'documents',
  'position_events',
  'macro_series_observations',
  'decision_log',
  'run_health',
  'position_attribution',
  'run_event_trace',
  'public_accounting_nav_history',
  'thesis_vehicles',
  'analyst_coverage',
  'public_daily_realized_attribution',
] as const;

export type DeskTableName = (typeof DESK_TABLES)[number];

export function tableEndpoint(table: string): string {
  return `/v1/tables/${table}`;
}

export type DeskPathMode = 'live+stub' | 'client-derived' | 'live' | 'missing' | 'direct';

export type DeskClientName =
  | 'getBrief'
  | 'getPortfolio'
  | 'getAllocations'
  | 'deriveMovers'
  | 'getTable'
  | 'getPerformance'
  | 'getNavSeries'
  | 'getLedger'
  | 'fetchVelaBars'
  | 'none';

export interface DeskPathEntry {
  chromePath: string;
  pane: string;
  /** HTTP path on dashboard-api. Null when the pane has no envelope route. */
  endpoint: string | null;
  /** Extra reads the pane also calls. Still not a second fake route. */
  also?: readonly string[];
  mode: DeskPathMode;
  client: DeskClientName;
  tables?: readonly DeskTableName[];
}

export const DESK_PATHS: readonly DeskPathEntry[] = [
  {
    chromePath: '/house/brief',
    pane: 'Decision',
    endpoint: DESK_ENDPOINTS.brief,
    mode: 'live+stub',
    client: 'getBrief',
  },
  {
    chromePath: '/house/brief/book',
    pane: 'Book allocation',
    endpoint: DESK_ENDPOINTS.portfolio,
    mode: 'live+stub',
    client: 'getPortfolio',
  },
  {
    chromePath: '/house/brief/movers',
    pane: 'Movers',
    endpoint: null,
    also: [DESK_ENDPOINTS.allocations, '/v1/market/closes'],
    mode: 'client-derived',
    client: 'deriveMovers',
  },
  {
    chromePath: '/house/brief/signals',
    pane: 'Signals to resolve',
    endpoint: tableEndpoint('theses'),
    mode: 'live',
    client: 'getTable',
    tables: ['theses'],
  },
  {
    chromePath: '/house/brief/breaks',
    pane: 'What could break the view',
    endpoint: tableEndpoint('theses'),
    mode: 'live',
    client: 'getTable',
    tables: ['theses'],
  },
  {
    chromePath: '/house/brief/run',
    pane: 'Run health',
    endpoint: tableEndpoint('run_health'),
    mode: 'live',
    client: 'getTable',
    tables: ['run_health', 'run_event_trace'],
  },
  {
    chromePath: '/house/brief/gloomberg',
    pane: 'Quote strip',
    endpoint: null,
    mode: 'missing',
    client: 'none',
  },
  {
    chromePath: '/house/brief/luxalgo',
    pane: 'Price chart',
    endpoint: null,
    mode: 'live',
    client: 'fetchVelaBars',
  },
  {
    chromePath: '/house/portfolio/holdings',
    pane: 'Positions',
    endpoint: DESK_ENDPOINTS.allocations,
    mode: 'live+stub',
    client: 'getAllocations',
  },
  {
    chromePath: '/house/portfolio/holdings/:ticker',
    pane: 'Symbol',
    endpoint: DESK_ENDPOINTS.allocations,
    mode: 'live',
    client: 'getAllocations',
  },
  {
    chromePath: '/house/portfolio/theses',
    pane: 'Thesis list',
    endpoint: tableEndpoint('theses'),
    mode: 'live',
    client: 'getTable',
    tables: ['theses', 'thesis_vehicles'],
  },
  {
    chromePath: '/house/portfolio/tearsheet',
    pane: 'Tearsheet',
    endpoint: DESK_ENDPOINTS.performance,
    also: [DESK_ENDPOINTS.navSeries],
    mode: 'live+stub',
    client: 'getPerformance',
  },
  {
    chromePath: '/house/portfolio/ledger',
    pane: 'Fills',
    endpoint: DESK_ENDPOINTS.ledger,
    mode: 'live+stub',
    client: 'getLedger',
  },
  {
    chromePath: '/house/portfolio/attribution',
    pane: 'Attribution',
    endpoint: tableEndpoint('position_attribution'),
    mode: 'live',
    client: 'getTable',
    tables: ['position_attribution', 'public_daily_realized_attribution'],
  },
  {
    chromePath: '/house/pipeline',
    pane: 'Pipeline',
    endpoint: tableEndpoint('run_health'),
    mode: 'live',
    client: 'getTable',
    tables: ['run_health', 'documents', 'run_event_trace'],
  },
  {
    chromePath: '/house/settings/brokers',
    pane: 'Paper brokers',
    endpoint: null,
    mode: 'direct',
    client: 'none',
  },
  {
    chromePath: '/house/settings/keys',
    pane: 'Desk keys',
    endpoint: null,
    mode: 'direct',
    client: 'none',
  },
  {
    chromePath: '/house/settings/theme',
    pane: 'Theme',
    endpoint: null,
    mode: 'direct',
    client: 'none',
  },
  {
    chromePath: '/fx-hub',
    pane: 'FX hub',
    endpoint: null,
    mode: 'direct',
    client: 'none',
  },
  {
    chromePath: '/house/strategies',
    pane: 'Strategies',
    endpoint: null,
    mode: 'missing',
    client: 'none',
  },
  {
    chromePath: '/rates-watch/digest',
    pane: 'Rates digest',
    endpoint: null,
    mode: 'missing',
    client: 'none',
  },
];

/**
 * Short chrome labels that still resolve to a canonical desk path.
 * `/book` is not `GET /book`. `/movers` is not `GET /movers`.
 */
export const DESK_PATH_ALIASES: Readonly<Record<string, string>> = {
  '/book': '/house/brief/book',
  '/movers': '/house/brief/movers',
};

function canonicalChromePath(chromePath: string): string {
  return DESK_PATH_ALIASES[chromePath] ?? chromePath;
}

/** Resolve a chrome path, including `/book` and `/movers` aliases and a ticker suffix. */
export function resolveDeskPath(chromePath: string): DeskPathEntry | undefined {
  const canonical = canonicalChromePath(chromePath);
  const exact = DESK_PATHS.find((entry) => entry.chromePath === canonical);
  if (exact) return exact;
  const tickerPrefix = '/house/portfolio/holdings/';
  if (canonical.startsWith(tickerPrefix) && canonical.length > tickerPrefix.length) {
    return DESK_PATHS.find((entry) => entry.chromePath === '/house/portfolio/holdings/:ticker');
  }
  return undefined;
}
